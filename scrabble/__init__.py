"""Scrabble move-finding engine (GADDAG + optional Qt GUI)."""

from scrabble.board import Board, Bonus, BOARD_SIZE
from scrabble.gaddag import Gaddag
from scrabble.move_gen import find_moves
from scrabble.play_validate import ValidatedPlay, validate_manual_play
from scrabble.score import score_play

__all__ = [
    "Board",
    "Bonus",
    "BOARD_SIZE",
    "Gaddag",
    "find_moves",
    "score_play",
    "ValidatedPlay",
    "validate_manual_play",
]
