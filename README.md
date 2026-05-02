# Scrabble move finder

Python **GADDAG**-based move generation, full **Scrabble scoring** (premiums, cross-words, bingo +50), and an optional **Qt (PySide6)** GUI.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,gui]"
```

The `gui` extra pulls in **PySide6** for `scrabble-gui`. Core library usage does not require it; use `pip install -e ".[dev]"` if you only need the engine and tests.

## GUI

```bash
scrabble-gui
# or
python -m scrabble.gui
```

- Enter **letters** in the 15×15 grid (use **lowercase** for a blank already on the board; it scores 0).
- Set **premium** squares via **right-click** on a cell (or **Board → Reset premiums** for the standard layout).
- **Rack**: letters A–Z and `?` for a blank in the rack (`?` branches over A–Z but is pruned by the GADDAG).
- Open a **lexicon** with **File → Open lexicon** (NASPA-style word list, one word per line). The bundled [`data/sample_words.txt`](data/sample_words.txt) is only for demos/tests — use your own **NWL** file where permitted.

## Library usage

```python
from pathlib import Path
from scrabble import Board, Gaddag, find_moves
from scrabble.gaddag import load_words_from_file

board = Board()
rack = list("RETINAS")
path = Path("data/sample_words.txt")
g = Gaddag.from_file(str(path))
words = load_words_from_file(str(path))
plays = find_moves(board, rack, g, words, top_n=20)
for p in plays:
    print(p.summary(), p.detail())
```

## Tests

```bash
pytest
```

## Legal

Do not redistribute official NWL/TWL files unless you have permission. This project ships **code** and a **small sample lexicon** only.
