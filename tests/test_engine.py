"""Tests for scoring and move generation."""

from pathlib import Path

import pytest

from scrabble.board import Bonus, Board
from scrabble.gaddag import Gaddag, load_words_from_file
from scrabble.move_gen import find_moves
from scrabble.play_validate import ValidatedPlay, validate_manual_play
from scrabble.score import NewTile, score_play

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample_words.txt"


@pytest.fixture(scope="module")
def lexicon():
    words = load_words_from_file(str(SAMPLE))
    g = Gaddag.from_file(str(SAMPLE))
    return g, words


def _all_normal_bonuses() -> Board:
    b = Board()
    for r in range(15):
        for c in range(15):
            b.bonuses[r][c] = Bonus.NORMAL
    return b


def test_score_simple_hi_no_premium():
    b = _all_normal_bonuses()
    nt = (NewTile(4, 4, "H", False), NewTile(4, 5, "I", False))
    s = score_play(b, "H", 4, 4, "HI", nt)
    assert s == 5  # H=4 + I=1


def test_double_word_center():
    b = Board()
    nt = (NewTile(7, 7, "H", False), NewTile(7, 8, "I", False))
    s = score_play(b, "H", 7, 7, "HI", nt)
    assert s == 10  # (4+1)*2, star is DW


def test_bingo_adds_50():
    b = _all_normal_bonuses()
    letters = list("TAINTER")
    nt = tuple(NewTile(7, i, letters[i], False) for i in range(7))
    s = score_play(b, "H", 7, 0, "TAINTER", nt)
    assert s == 7 + 50


def test_blank_face_value_zero():
    b = _all_normal_bonuses()
    nt = (NewTile(4, 4, "Z", True), NewTile(4, 5, "A", False))
    s = score_play(b, "H", 4, 4, "ZA", nt)
    assert s == 1  # blank + A


def test_cross_word_vertical_adds_ait():
    b = _all_normal_bonuses()
    b.letters[6][7] = "A"
    b.letters[8][7] = "T"
    b.letters[7][6] = "H"
    nt = (NewTile(7, 7, "I", False),)
    s = score_play(b, "H", 7, 6, "HI", nt)
    assert s == 5 + 3  # HI + AIT, all normal cells


def test_find_moves_opening(lexicon):
    g, words = lexicon
    b = Board()
    plays = find_moves(b, list("HELLO"), g, words, top_n=20)
    assert any(p.word == "HELLO" for p in plays)


def test_find_moves_filters_by_cross(lexicon):
    g, words = lexicon
    b = Board()
    b.letters[6][7] = "A"
    b.letters[8][7] = "T"
    b.letters[7][6] = "H"
    plays = find_moves(b, list("I??????"), g, words, top_n=100)
    assert any(p.word == "HI" for p in plays)


def test_tw_dw_stack_multiplier():
    """Double-word and triple-word multipliers stack for the whole word."""
    b = _all_normal_bonuses()
    b.bonuses[7][7] = Bonus.DW
    b.bonuses[7][8] = Bonus.TW
    nt = (NewTile(7, 7, "A", False), NewTile(7, 8, "A", False))
    s = score_play(b, "H", 7, 7, "AA", nt)
    assert s == (1 + 1) * 2 * 3


def test_score_rejects_board_mismatch():
    b = Board()
    b.letters[7][7] = "X"
    nt = (NewTile(7, 8, "I", False),)
    with pytest.raises(ValueError):
        score_play(b, "H", 7, 7, "HI", nt)


def test_validate_opening_hi(lexicon):
    _, words = lexicon
    b = Board()
    nt = (NewTile(7, 7, "H", False), NewTile(7, 8, "I", False))
    out = validate_manual_play(b, nt, list("HI"), words)
    assert isinstance(out, ValidatedPlay)
    assert out.word == "HI" and out.score == 10


def test_validate_opening_must_cover_center(lexicon):
    _, words = lexicon
    b = Board()
    nt = (NewTile(0, 0, "A", False), NewTile(0, 1, "A", False))
    out = validate_manual_play(b, nt, list("AA"), words)
    assert isinstance(out, str) and "center" in out.lower()


def test_validate_must_connect_to_board(lexicon):
    _, words = lexicon
    b = Board()
    b.letters[0][0] = "A"
    nt = (NewTile(7, 7, "H", False), NewTile(7, 8, "I", False))
    out = validate_manual_play(b, nt, list("HI"), words)
    assert isinstance(out, str) and "touch" in out.lower()


def test_validate_cross_word_not_in_lexicon(lexicon):
    _, words = lexicon
    words2 = set(words)
    words2.discard("AIT")
    b = _all_normal_bonuses()
    b.letters[6][7] = "A"
    b.letters[8][7] = "T"
    b.letters[7][6] = "H"
    nt = (NewTile(7, 7, "I", False),)
    out = validate_manual_play(b, nt, list("I"), words2)
    assert isinstance(out, str) and "AIT" in out


def test_validate_rack_mismatch(lexicon):
    _, words = lexicon
    b = Board()
    nt = (NewTile(7, 7, "H", False), NewTile(7, 8, "I", False))
    out = validate_manual_play(b, nt, list("H"), words)
    assert isinstance(out, str) and "Rack" in out


def test_validate_score_agrees_with_score_play(lexicon):
    _, words = lexicon
    b = _all_normal_bonuses()
    b.letters[6][7] = "A"
    b.letters[8][7] = "T"
    b.letters[7][6] = "H"
    nt = (NewTile(7, 7, "I", False),)
    direct = score_play(b, "H", 7, 6, "HI", nt)
    out = validate_manual_play(b, nt, list("I"), words)
    assert isinstance(out, ValidatedPlay)
    assert out.score == direct


def test_validate_blank_from_rack(lexicon):
    _, words = lexicon
    b = _all_normal_bonuses()
    nt = (NewTile(7, 7, "Z", True), NewTile(7, 8, "A", False))
    out = validate_manual_play(b, nt, list("?A"), words)
    assert isinstance(out, ValidatedPlay)
    assert out.score == score_play(b, "H", 7, 7, "ZA", nt)


def test_validate_cannot_preview_on_occupied_square(lexicon):
    _, words = lexicon
    b = Board()
    b.letters[7][7] = "X"
    nt = (NewTile(7, 7, "H", False),)
    out = validate_manual_play(b, nt, list("H"), words)
    assert isinstance(out, str) and "occupied" in out.lower()


def test_validate_tiles_not_collinear(lexicon):
    _, words = lexicon
    b = Board()
    nt = (NewTile(7, 7, "A", False), NewTile(8, 8, "A", False))
    out = validate_manual_play(b, nt, list("AA"), words)
    assert isinstance(out, str) and ("row" in out.lower() or "column" in out.lower())
