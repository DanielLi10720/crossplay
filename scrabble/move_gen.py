"""Anchor + GADDAG move generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Sequence, Set, Tuple

from scrabble.board import BOARD_SIZE, Board
from scrabble.gaddag import Gaddag
from scrabble.score import NewTile, score_play

ALL_MASK = (1 << 26) - 1


@dataclass
class Play:
    direction: str  # 'H' or 'V'
    row: int
    col: int
    word: str
    new_tiles: Tuple[NewTile, ...]
    score: int = 0

    def summary(self) -> str:
        if self.direction == "H":
            pos = f"{self.row + 1}{chr(ord('A') + self.col)}"
        else:
            pos = f"{chr(ord('A') + self.col)}{self.row + 1}"
        return f"{pos} {self.word} {self.score}"

    def detail(self) -> str:
        pts = ", ".join(
            f"({t.r + 1},{chr(ord('A') + t.c)})={t.ch}{'*' if t.from_blank else ''}"
            for t in self.new_tiles
        )
        return f"{self.summary()}  | {pts}"


def _cell_u(board: Board, r: int, c: int) -> str:
    ch = board.get(r, c)
    if not ch:
        return ""
    return ch.upper()


def _mask_for_vertical_cross(board: Board, r: int, c: int, words: Set[str]) -> int:
    above: List[str] = []
    rr = r - 1
    while rr >= 0 and board.get(rr, c):
        above.append(_cell_u(board, rr, c))
        rr -= 1
    above_str = "".join(reversed(above))
    below: List[str] = []
    rr = r + 1
    while rr < BOARD_SIZE and board.get(rr, c):
        below.append(_cell_u(board, rr, c))
        rr += 1
    below_str = "".join(below)
    if not above_str and not below_str:
        return ALL_MASK
    mask = 0
    for i in range(26):
        L = chr(65 + i)
        w = above_str + L + below_str
        if len(w) >= 2 and w in words:
            mask |= 1 << i
    return mask


def _mask_for_horizontal_cross(board: Board, r: int, c: int, words: Set[str]) -> int:
    left: List[str] = []
    cc = c - 1
    while cc >= 0 and board.get(r, cc):
        left.append(_cell_u(board, r, cc))
        cc -= 1
    left_str = "".join(reversed(left))
    right: List[str] = []
    cc = c + 1
    while cc < BOARD_SIZE and board.get(r, cc):
        right.append(_cell_u(board, r, cc))
        cc += 1
    right_str = "".join(right)
    if not left_str and not right_str:
        return ALL_MASK
    mask = 0
    for i in range(26):
        L = chr(65 + i)
        w = left_str + L + right_str
        if len(w) >= 2 and w in words:
            mask |= 1 << i
    return mask


def cross_masks(board: Board, words: Set[str]) -> Tuple[List[List[int]], List[List[int]]]:
    """(mask_for_horizontal_main, mask_for_vertical_main)."""
    mh = [[ALL_MASK for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    mv = [[ALL_MASK for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if not board.is_empty(r, c):
                continue
            mh[r][c] = _mask_for_vertical_cross(board, r, c, words)
            mv[r][c] = _mask_for_horizontal_cross(board, r, c, words)
    return mh, mv


def anchors_row(board: Board, r: int) -> List[int]:
    out: List[int] = []
    any_tiles = board.any_tiles_placed()
    for c in range(BOARD_SIZE):
        if not board.is_empty(r, c):
            continue
        if not any_tiles:
            if (r, c) == (7, 7):
                out.append(c)
            continue
        ok = False
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and board.get(nr, nc):
                ok = True
                break
        if ok:
            out.append(c)
    return out


def _rack_options(rack: List[str], letter: str) -> List[Tuple[List[str], bool]]:
    opts: List[Tuple[List[str], bool]] = []
    if letter in rack:
        nr = rack.copy()
        nr.remove(letter)
        opts.append((nr, False))
    if "?" in rack:
        nr = rack.copy()
        nr.remove("?")
        opts.append((nr, True))
    return opts


def _transpose_board(board: Board) -> Board:
    t = board.copy()
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            t.letters[r][c] = board.letters[c][r]
            t.bonuses[r][c] = board.bonuses[c][r]
    return t


def find_moves(
    board: Board,
    rack: Sequence[str],
    g: Gaddag,
    word_set: Set[str],
    top_n: int = 50,
) -> List[Play]:
    rack_list = [
        str(x).upper()
        for x in rack
        if x == "?" or (len(str(x)) == 1 and str(x).isalpha())
    ]
    if not rack_list:
        return []
    mh, mv = cross_masks(board, word_set)
    seen: Set[Tuple[str, int, int, str]] = set()
    acc: List[Play] = []

    def add_play(
        direction: str,
        start_r: int,
        start_c: int,
        word: str,
        nts: List[Tuple[int, int, str, bool]],
    ) -> None:
        if not nts:
            return
        if not board.any_tiles_placed():
            if not any(r == 7 and c == 7 for (r, c, _, _) in nts):
                return
        key = (direction, start_r, start_c, word)
        if key in seen:
            return
        seen.add(key)
        tiles = tuple(NewTile(r, c, ch, fb) for (r, c, ch, fb) in nts)
        try:
            sc = score_play(board, direction, start_r, start_c, word, tiles)
        except ValueError:
            return
        acc.append(Play(direction, start_r, start_c, word, tiles, sc))

    def run_horizontal(
        b: Board,
        cross_m: List[List[int]],
        direction_out: str,
        cell_map: Callable[[int, int], Tuple[int, int]],
        map_tile: Callable[[Tuple[int, int, str, bool]], Tuple[int, int, str, bool]],
    ) -> None:
        def map_start(tr: int, lc: int) -> Tuple[int, int]:
            return cell_map(tr, lc)

        for row in range(BOARD_SIZE):
            for ac in anchors_row(b, row):
                tiles_left: List[str] = []
                cc = ac - 1
                while cc >= 0 and b.get(row, cc):
                    tile = b.get(row, cc)
                    assert tile is not None
                    tiles_left.append(tile)
                    cc -= 1
                node = 0
                bad = False
                for ch in tiles_left:
                    nxt = g.transition(node, ord(ch.upper()) - 65)
                    if nxt is None:
                        bad = True
                        break
                    node = nxt
                if bad:
                    continue
                after_sep = g.sep_child(node)
                left_limit = 0
                scan = ac - 1 - len(tiles_left)
                while scan >= 0 and b.is_empty(row, scan):
                    left_limit += 1
                    scan -= 1

                def record(end_col: int, new_pts_local: List[Tuple[int, int, str, bool]]) -> None:
                    if not new_pts_local:
                        return
                    if not any(cc2 == ac for (_, cc2, _, _) in new_pts_local):
                        return
                    lc = min(c for (_, c, _, _) in new_pts_local)
                    while lc > 0 and b.get(row, lc - 1):
                        lc -= 1
                    rc = end_col
                    while rc + 1 < BOARD_SIZE and b.get(row, rc + 1):
                        rc += 1
                    chars: List[str] = []
                    for col in range(lc, rc + 1):
                        ch = b.get(row, col)
                        if ch:
                            chars.append(ch.upper())
                        else:
                            found = None
                            for (rr, cc2, l2, _) in new_pts_local:
                                if rr == row and cc2 == col:
                                    found = l2.upper()
                                    break
                            if found is None:
                                return
                            chars.append(found)
                    word = "".join(chars)
                    if len(word) < 2:
                        return
                    nts_orig = [map_tile(t) for t in new_pts_local]
                    sr, sc = map_start(row, lc)
                    add_play(direction_out, sr, sc, word, nts_orig)

                def extend_right(
                    node_id: int,
                    c: int,
                    rack_now: List[str],
                    new_pts: List[Tuple[int, int, str, bool]],
                ) -> None:
                    if c < BOARD_SIZE and b.is_empty(row, c):
                        if g.is_terminal(node_id) and new_pts:
                            if any(cc2 == ac for (_, cc2, _, _) in new_pts):
                                record(c - 1, new_pts)
                    if c >= BOARD_SIZE:
                        return
                    cell = b.get(row, c)
                    if cell:
                        n2 = g.transition(node_id, ord(cell.upper()) - 65)
                        if n2 is None:
                            return
                        extend_right(n2, c + 1, rack_now, new_pts)
                        return
                    if not rack_now:
                        return
                    for lk, n2 in g.iter_letter_edges(node_id):
                        if not (cross_m[row][c] & (1 << lk)):
                            continue
                        L = chr(65 + lk)
                        for nrack, was_blank in _rack_options(rack_now, L):
                            extend_right(n2, c + 1, nrack, new_pts + [(row, c, L, was_blank)])

                def left_part(
                    node_id: int,
                    limit: int,
                    placed_left: int,
                    rack_now: List[str],
                    left_pts: List[Tuple[int, int, str, bool]],
                ) -> None:
                    sep_n = g.sep_child(node_id)
                    if sep_n is not None:
                        extend_right(sep_n, ac, rack_now, left_pts.copy())
                    if limit <= 0:
                        return
                    for lk, next_n in g.iter_letter_edges(node_id):
                        col = ac - 1 - placed_left
                        if col < 0:
                            continue
                        if not (cross_m[row][col] & (1 << lk)):
                            continue
                        L = chr(65 + lk)
                        for nrack, was_blank in _rack_options(rack_now, L):
                            left_part(
                                next_n,
                                limit - 1,
                                placed_left + 1,
                                nrack,
                                left_pts + [(row, col, L, was_blank)],
                            )

                if tiles_left:
                    if after_sep is not None:
                        extend_right(after_sep, ac, rack_list, [])
                else:
                    left_part(0, left_limit, 0, rack_list, [])

    run_horizontal(
        board,
        mh,
        "H",
        lambda r, c: (r, c),
        lambda t: t,
    )

    bt = _transpose_board(board)
    mvt = [[mv[c][r] for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)]

    run_horizontal(
        bt,
        mvt,
        "V",
        lambda tr, tc: (tc, tr),
        lambda t: (t[1], t[0], t[2], t[3]),
    )

    acc.sort(key=lambda p: p.score, reverse=True)
    return acc[:top_n]
