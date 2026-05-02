"""Board model, premium squares, and tile values (North American Scrabble)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, List, Optional, Tuple

BOARD_SIZE = 15


class Bonus(IntEnum):
    """Square multiplier; CENTER is opening star (double-word)."""

    NORMAL = 0
    DL = 1
    TL = 2
    DW = 3
    TW = 4
    CENTER = 5  # treated as DW in scoring


# NASPA tile values (standard)
LETTER_VALUES: dict[str, int] = {
    "A": 1,
    "B": 3,
    "C": 3,
    "D": 2,
    "E": 1,
    "F": 4,
    "G": 2,
    "H": 4,
    "I": 1,
    "J": 8,
    "K": 5,
    "L": 1,
    "M": 3,
    "N": 1,
    "O": 1,
    "P": 3,
    "Q": 10,
    "R": 1,
    "S": 1,
    "T": 1,
    "U": 1,
    "V": 4,
    "W": 4,
    "X": 8,
    "Y": 4,
    "Z": 10,
}


def letter_points(ch: str) -> int:
    """Face value; blanks on board (lowercase) score 0."""
    if not ch:
        return 0
    if ch.islower():
        return 0
    return LETTER_VALUES.get(ch.upper(), 0)


def normalize_board_letter(ch: str) -> Optional[str]:
    """Single cell: '' / '.' -> empty; else one-letter A–Z or a–z (blank)."""
    if not ch:
        return None
    s = ch.strip()
    if not s or s in ".-_":
        return None
    if len(s) != 1:
        raise ValueError(f"Expected one character, got {ch!r}")
    if s.isalpha():
        return s
    raise ValueError(f"Invalid letter: {ch!r}")


def rack_from_string(s: str) -> List[str]:
    """
    Parse rack string: A–Z and ? for blank. Spaces ignored.
    Returns list of single-char strings (uppercase letters and '?').
    """
    out: List[str] = []
    for c in s.upper().replace(" ", ""):
        if c.isalpha():
            out.append(c)
        elif c == "?":
            out.append("?")
    return out


def default_bonuses() -> List[List[Bonus]]:
    """Official 15×15 premium layout (1-based descriptions -> 0-based grid)."""
    b: List[List[Bonus]] = [
        [Bonus.NORMAL for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
    ]

    def tw(r: int, c: int) -> None:
        b[r][c] = Bonus.TW

    def dw(r: int, c: int) -> None:
        b[r][c] = Bonus.DW

    def tl(r: int, c: int) -> None:
        b[r][c] = Bonus.TL

    def dl(r: int, c: int) -> None:
        b[r][c] = Bonus.DL

    # Triple word corners / mid-edges
    for r, c in (
        (0, 0),
        (0, 7),
        (0, 14),
        (7, 0),
        (7, 14),
        (14, 0),
        (14, 7),
        (14, 14),
    ):
        tw(r, c)

    # Double word
    for r, c in (
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
        (7, 7),
        (10, 10),
        (11, 11),
        (12, 12),
        (13, 13),
        (1, 13),
        (2, 12),
        (3, 11),
        (4, 10),
        (10, 4),
        (11, 3),
        (12, 2),
        (13, 1),
    ):
        dw(r, c)
    b[7][7] = Bonus.CENTER

    # Triple letter
    for r, c in (
        (1, 5),
        (1, 9),
        (5, 1),
        (5, 5),
        (5, 9),
        (5, 13),
        (9, 1),
        (9, 5),
        (9, 9),
        (9, 13),
        (13, 5),
        (13, 9),
    ):
        tl(r, c)

    # Double letter
    for r, c in (
        (0, 3),
        (0, 11),
        (2, 6),
        (2, 8),
        (3, 0),
        (3, 7),
        (3, 14),
        (6, 2),
        (6, 6),
        (6, 8),
        (6, 12),
        (7, 3),
        (7, 11),
        (8, 2),
        (8, 6),
        (8, 8),
        (8, 12),
        (11, 0),
        (11, 7),
        (11, 14),
        (12, 6),
        (12, 8),
        (14, 3),
        (14, 11),
    ):
        dl(r, c)

    return b


@dataclass
class Board:
    """15×15 game board: letters and premium per cell."""

    letters: List[List[Optional[str]]] = field(
        default_factory=lambda: [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    )
    bonuses: List[List[Bonus]] = field(default_factory=default_bonuses)

    def copy(self) -> Board:
        letters = [row[:] for row in self.letters]
        bonuses = [row[:] for row in self.bonuses]
        return Board(letters=letters, bonuses=bonuses)

    def get(self, r: int, c: int) -> Optional[str]:
        return self.letters[r][c]

    def is_empty(self, r: int, c: int) -> bool:
        return self.letters[r][c] is None

    def bonus_at(self, r: int, c: int) -> Bonus:
        return self.bonuses[r][c]

    def any_tiles_placed(self) -> bool:
        return any(self.letters[r][c] for r in range(BOARD_SIZE) for c in range(BOARD_SIZE))

    def squares_with_tiles(self) -> Iterable[Tuple[int, int]]:
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.letters[r][c]:
                    yield r, c
