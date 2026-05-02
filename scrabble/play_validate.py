"""Validate a manual play (preview tiles) against board, lexicon, and rack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from scrabble.board import BOARD_SIZE, Board
from scrabble.score import NewTile, score_play


def _merged_cell(committed: Board, new_pos: Dict[Tuple[int, int], NewTile], r: int, c: int) -> Optional[str]:
    if (r, c) in new_pos:
        nt = new_pos[(r, c)]
        return nt.ch.lower() if nt.from_blank else nt.ch
    return committed.get(r, c)


def _word_for_lex(s: str) -> str:
    return "".join(ch.upper() for ch in s)


def _span_horizontal(
    committed: Board, new_pos: Dict[Tuple[int, int], NewTile], r0: int
) -> Tuple[str, int, int, bool]:
    cols = [c for c in range(BOARD_SIZE) if _merged_cell(committed, new_pos, r0, c)]
    if not cols:
        return "", 0, 0, False
    min_c, max_c = min(cols), max(cols)
    for c in range(min_c, max_c + 1):
        if not _merged_cell(committed, new_pos, r0, c):
            return "", 0, 0, False
    for (r, c) in new_pos:
        if r != r0 or c < min_c or c > max_c:
            return "", 0, 0, False
    chars: List[str] = []
    for c in range(min_c, max_c + 1):
        if (r0, c) in new_pos:
            nt = new_pos[(r0, c)]
            chars.append(nt.ch.upper())
        else:
            ex = committed.get(r0, c)
            if not ex:
                return "", 0, 0, False
            chars.append(ex)
    return "".join(chars), r0, min_c, True


def _span_vertical(
    committed: Board, new_pos: Dict[Tuple[int, int], NewTile], c0: int
) -> Tuple[str, int, int, bool]:
    rows = [r for r in range(BOARD_SIZE) if _merged_cell(committed, new_pos, r, c0)]
    if not rows:
        return "", 0, 0, False
    min_r, max_r = min(rows), max(rows)
    for r in range(min_r, max_r + 1):
        if not _merged_cell(committed, new_pos, r, c0):
            return "", 0, 0, False
    for (r, c) in new_pos:
        if c != c0 or r < min_r or r > max_r:
            return "", 0, 0, False
    chars: List[str] = []
    for r in range(min_r, max_r + 1):
        if (r, c0) in new_pos:
            nt = new_pos[(r, c0)]
            chars.append(nt.ch.upper())
        else:
            ex = committed.get(r, c0)
            if not ex:
                return "", 0, 0, False
            chars.append(ex)
    return "".join(chars), min_r, c0, True


def _perpendicular_word(
    committed: Board,
    new_pos: Dict[Tuple[int, int], NewTile],
    r2: int,
    c2: int,
    dr: int,
    dc: int,
) -> str:
    rr, cc = r2, c2
    while (
        0 <= rr - dr < BOARD_SIZE
        and 0 <= cc - dc < BOARD_SIZE
        and _merged_cell(committed, new_pos, rr - dr, cc - dc)
    ):
        rr -= dr
        cc -= dc
    letters: List[str] = []
    while 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE:
        ch = _merged_cell(committed, new_pos, rr, cc)
        if not ch:
            break
        letters.append(ch.upper())
        rr += dr
        cc += dc
    return "".join(letters)


def _rack_allows_play(tiles: Sequence[NewTile], rack: Sequence[str]) -> Optional[str]:
    pool: List[str] = [str(x).upper() for x in rack if x is not None]
    need: List[NewTile] = list(tiles)
    while need:
        t = need.pop()
        if t.from_blank:
            if "?" in pool:
                pool.remove("?")
            else:
                return "Rack has no blank for this play"
        else:
            L = t.ch.upper()
            if L in pool:
                pool.remove(L)
            else:
                return f"Rack missing letter {L}"
    return None


def _covers_center(start_r: int, start_c: int, direction: str, word: str) -> bool:
    dr, dc = (0, 1) if direction == "H" else (1, 0)
    for i in range(len(word)):
        r, c = start_r + i * dr, start_c + i * dc
        if r == 7 and c == 7:
            return True
    return False


def _connected_to_board(committed: Board, new_pos: Dict[Tuple[int, int], NewTile]) -> bool:
    for (r, c) in new_pos:
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and committed.get(rr, cc):
                return True
    return False


@dataclass(frozen=True)
class ValidatedPlay:
    direction: str
    start_r: int
    start_c: int
    word: str
    new_tiles: Tuple[NewTile, ...]
    score: int


def validate_manual_play(
    committed: Board,
    new_tiles: Sequence[NewTile],
    rack: Sequence[str],
    word_set: set[str],
) -> Union[ValidatedPlay, str]:
    """
    Returns ValidatedPlay on success, or a short error string.
    Lexicon words are matched uppercase; `word_set` should contain uppercase words.
    """
    if not new_tiles:
        return "No tiles placed"
    new_pos = {(t.r, t.c): t for t in new_tiles}
    if len(new_pos) != len(new_tiles):
        return "Duplicate tile positions"

    for (r, c) in new_pos:
        if committed.get(r, c) is not None:
            return "Cannot preview on an occupied square"

    rows = {t.r for t in new_tiles}
    cols = {t.c for t in new_tiles}
    direction: str
    word: str
    sr: int
    sc: int

    if len(rows) == 1 and len(cols) == 1:
        r0, c0 = next(iter(new_pos))
        h_word, h_sr, h_sc, h_ok = _span_horizontal(committed, new_pos, r0)
        v_word, v_sr, v_sc, v_ok = _span_vertical(committed, new_pos, c0)
        h_valid = h_ok and len(h_word) >= 2
        v_valid = v_ok and len(v_word) >= 2
        if h_valid and v_valid:
            direction, word, sr, sc = "H", h_word, h_sr, h_sc
        elif h_valid:
            direction, word, sr, sc = "H", h_word, h_sr, h_sc
        elif v_valid:
            direction, word, sr, sc = "V", v_word, v_sr, v_sc
        else:
            return "Incomplete or too-short word"
    elif len(rows) == 1:
        r0 = next(iter(rows))
        word, sr, sc, ok = _span_horizontal(committed, new_pos, r0)
        if not ok or len(word) < 2:
            return "Invalid horizontal play (gaps or too short)"
        direction = "H"
    elif len(cols) == 1:
        c0 = next(iter(cols))
        word, sr, sc, ok = _span_vertical(committed, new_pos, c0)
        if not ok or len(word) < 2:
            return "Invalid vertical play (gaps or too short)"
        direction = "V"
    else:
        return "All new tiles must be in one row or column"

    opening = not committed.any_tiles_placed()
    if opening:
        if not _covers_center(sr, sc, direction, word):
            return "Opening play must cover the center star"
    else:
        if not _connected_to_board(committed, new_pos):
            return "Play must touch an existing tile"

    w_lex = _word_for_lex(word)
    if w_lex not in word_set:
        return f"Main word {w_lex!r} not in lexicon"

    dr_cross, dc_cross = (1, 0) if direction == "H" else (0, 1)
    for t in new_tiles:
        cross = _perpendicular_word(committed, new_pos, t.r, t.c, dr_cross, dc_cross)
        if len(cross) >= 2 and cross not in word_set:
            return f"Cross word {cross!r} not in lexicon"

    rack_err = _rack_allows_play(new_tiles, rack)
    if rack_err:
        return rack_err

    tiles_tuple = tuple(new_tiles)
    try:
        score_total = score_play(committed, direction, sr, sc, word, tiles_tuple)
    except ValueError as e:
        return str(e)

    return ValidatedPlay(direction, sr, sc, word, tiles_tuple, score_total)
