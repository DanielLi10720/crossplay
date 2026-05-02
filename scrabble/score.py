"""Score plays: premiums, cross-words, bingo (+50)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from scrabble.board import BOARD_SIZE, Bonus, Board, letter_points


@dataclass(frozen=True)
class NewTile:
    """A tile placed from the rack this turn."""

    r: int
    c: int
    ch: str  # uppercase letter on board
    from_blank: bool  # rack was '?'; face value 0 for scoring


def word_bonus_mult(b: Bonus) -> int:
    if b in (Bonus.DW, Bonus.CENTER):
        return 2
    if b == Bonus.TW:
        return 3
    return 1


def letter_bonus_mult(b: Bonus) -> int:
    if b == Bonus.DL:
        return 2
    if b == Bonus.TL:
        return 3
    return 1


def _face_value(board: Board, new_pos: Dict[Tuple[int, int], NewTile], r: int, c: int, ch: str) -> int:
    if (r, c) in new_pos:
        nt = new_pos[(r, c)]
        return 0 if nt.from_blank else letter_points(nt.ch)
    return letter_points(ch)


def _score_line(
    board: Board,
    new_pos: Dict[Tuple[int, int], NewTile],
    dr: int,
    dc: int,
    r0: int,
    c0: int,
    chs: Sequence[str],
) -> int:
    w_mult = 1
    total = 0
    r, c = r0, c0
    for ch in chs:
        face = _face_value(board, new_pos, r, c, ch)
        lm = 1
        bon = board.bonus_at(r, c)
        if (r, c) in new_pos:
            lm = letter_bonus_mult(bon)
            wm = word_bonus_mult(bon)
            if wm > 1:
                w_mult *= wm
        total += face * lm
        r += dr
        c += dc
    return total * w_mult


def _merged_get(
    board: Board, new_pos: Dict[Tuple[int, int], NewTile], r: int, c: int
) -> Optional[str]:
    if (r, c) in new_pos:
        return new_pos[(r, c)].ch
    return board.get(r, c)


def _perpendicular_cross_score(
    board: Board,
    new_pos: Dict[Tuple[int, int], NewTile],
    r2: int,
    c2: int,
    dr_cross: int,
    dc_cross: int,
) -> Tuple[Tuple[int, int, int, int], int]:
    """
    Returns ((start_r, start_c, dr, dc), score) for the perpendicular word through
    (r2, c2), or score 0 if no cross-word (length <= 1).
    """
    up_r, up_c = r2 - dr_cross, c2 - dc_cross
    dn_r, dn_c = r2 + dr_cross, c2 + dc_cross
    has_up = (
        0 <= up_r < BOARD_SIZE
        and 0 <= up_c < BOARD_SIZE
        and _merged_get(board, new_pos, up_r, up_c)
    )
    has_dn = (
        0 <= dn_r < BOARD_SIZE
        and 0 <= dn_c < BOARD_SIZE
        and _merged_get(board, new_pos, dn_r, dn_c)
    )
    if not has_up and not has_dn:
        return (0, 0, 0, 0), 0

    rr, cc = r2, c2
    while (
        0 <= rr - dr_cross < BOARD_SIZE
        and 0 <= cc - dc_cross < BOARD_SIZE
        and _merged_get(board, new_pos, rr - dr_cross, cc - dc_cross)
    ):
        rr -= dr_cross
        cc -= dc_cross
    start_r, start_c = rr, cc

    cross: List[str] = []
    rr, cc = start_r, start_c
    while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE:
        ch = _merged_get(board, new_pos, rr, cc)
        if not ch:
            break
        cross.append(ch)
        rr += dr_cross
        cc += dc_cross
    if len(cross) <= 1:
        return (0, 0, 0, 0), 0
    scr = _score_line(board, new_pos, dr_cross, dc_cross, start_r, start_c, cross)
    return (start_r, start_c, dr_cross, dc_cross), scr


def score_play(
    board: Board,
    direction: str,
    start_r: int,
    start_c: int,
    word: str,
    new_tiles: Sequence[NewTile],
) -> int:
    """
    Total score for a play. `word` is the main word from (start_r, start_c)
    along 'H' (dc=1) or 'V' (dr=1). Must match board letters where tiles exist.
    """
    if direction not in "HV":
        raise ValueError("direction must be 'H' or 'V'")
    dr, dc = (0, 1) if direction == "H" else (1, 0)

    new_pos: Dict[Tuple[int, int], NewTile] = {(t.r, t.c): t for t in new_tiles}
    if len(new_pos) != len(new_tiles):
        raise ValueError("Duplicate new tile positions")

    main_chars: List[str] = []
    r, c = start_r, start_c
    for ch in word:
        if r >= BOARD_SIZE or c >= BOARD_SIZE:
            raise ValueError("Word extends off board")
        existing = board.get(r, c)
        if existing is not None:
            if existing.upper() != ch.upper():
                raise ValueError(f"Board mismatch at {r},{c}: {existing!r} vs {ch!r}")
            main_chars.append(existing)
        else:
            main_chars.append(ch)
        r += dr
        c += dc

    total = _score_line(board, new_pos, dr, dc, start_r, start_c, main_chars)

    dr_cross, dc_cross = (1, 0) if direction == "H" else (0, 1)
    seen: Set[Tuple[int, int, int, int]] = set()
    for t in new_tiles:
        key, s = _perpendicular_cross_score(board, new_pos, t.r, t.c, dr_cross, dc_cross)
        if s == 0:
            continue
        if key in seen:
            continue
        seen.add(key)
        total += s

    if len(new_tiles) == 7:
        total += 50
    return total
