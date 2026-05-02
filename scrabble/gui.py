"""Qt (PySide6) GUI for the Scrabble move finder."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scrabble.board import (
    BOARD_SIZE,
    Bonus,
    Board,
    default_bonuses,
    normalize_board_letter,
    rack_from_string,
)
from scrabble.gaddag import Gaddag, load_words_from_file
from scrabble.move_gen import Play, find_moves
from scrabble.play_validate import ValidatedPlay, validate_manual_play
from scrabble.score import NewTile

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QGroupBox,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QVBoxLayout,
    )
except ImportError as _import_err:  # pragma: no cover - exercised when PySide6 missing
    _PYSIDE_IMPORT_ERROR: Optional[ImportError] = _import_err
    ScrabbleMainWindow = None
else:
    _PYSIDE_IMPORT_ERROR = None

    # Index matches Bonus enum value 0..5
    BONUS_LABELS = ("Normal", "DL", "TL", "DW", "TW", "Star")

    def _bonus_hex(index: int) -> str:
        styles = ("#f5f5f5", "#c8e6c9", "#66bb6a", "#ffccbc", "#ff7043", "#ffe082")
        if 0 <= index < len(styles):
            return styles[index]
        return styles[0]

    def _bonus_brush_for_label(label: str) -> QBrush:
        idx = BONUS_LABELS.index(label) if label in BONUS_LABELS else 0
        return QBrush(QColor(_bonus_hex(idx)))

    class ScrabbleMainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Scrabble move finder")
            self.resize(1150, 760)

            self.gaddag: Optional[Gaddag] = None
            self.word_set: set[str] = set()
            self._plays_cache: List[Play] = []
            self._snapshot_letters: Optional[List[List[Optional[str]]]] = None
            self._board_updating = False
            self._committed_letters: List[List[Optional[str]]] = [
                [None] * BOARD_SIZE for _ in range(BOARD_SIZE)
            ]
            self._preview_tiles: Dict[Tuple[int, int], NewTile] = {}
            self._player_scores: List[int] = [0, 0]
            self._active_player: int = 0  # 0 = P1, 1 = P2

            default_lex = Path(__file__).resolve().parent.parent / "data" / "sample_words.txt"
            self._lexicon_path = str(default_lex) if default_lex.exists() else ""

            self._build_menu()
            self._build_toolbar()
            self._build_central()

            self._default_bonuses = [
                [default_bonuses()[r][c] for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)
            ]

            self._load_lexicon_silent()
            self._reset_premiums()
            self._refresh_board_display()

        def _build_menu(self) -> None:
            file_m = self.menuBar().addMenu("&File")
            file_m.addAction("Open &lexicon…", self._open_lexicon_dialog, QKeySequence.StandardKey.Open)
            file_m.addSeparator()
            file_m.addAction("&Save board JSON…", self._save_state)
            file_m.addAction("&Load board JSON…", self._load_state)
            file_m.addSeparator()
            file_m.addAction("&Quit", self.close, QKeySequence.StandardKey.Quit)

            board_m = self.menuBar().addMenu("&Board")
            board_m.addAction("Clear &letters", self._clear_letters)
            board_m.addAction("&Reset premiums", self._reset_premiums)

        def _build_toolbar(self) -> None:
            tb = QToolBar()
            tb.setMovable(False)
            self.addToolBar(tb)

            self._lex_label = QLabel()
            self._lex_label.setMinimumWidth(180)
            tb.addWidget(self._lex_label)
            self._sync_lex_label()

            tb.addWidget(QLabel("Rack:"))
            self._rack_edit = QLineEdit()
            self._rack_edit.setPlaceholderText("A–Z, ? blank")
            self._rack_edit.setMaximumWidth(140)
            tb.addWidget(self._rack_edit)

            tb.addWidget(QLabel("Top N:"))
            self._topn_spin = QSpinBox()
            self._topn_spin.setRange(1, 500)
            self._topn_spin.setValue(50)
            self._topn_spin.setMaximumWidth(70)
            tb.addWidget(self._topn_spin)

            find_btn = QPushButton("Find moves")
            find_btn.clicked.connect(self._find_moves)
            tb.addWidget(find_btn)

            self._preview_score_label = QLabel("Preview: —")
            self._preview_score_label.setMinimumWidth(220)
            tb.addWidget(self._preview_score_label)

            self._score_turn_label = QLabel()
            self._score_turn_label.setMinimumWidth(260)
            tb.addWidget(self._score_turn_label)
            self._refresh_score_turn_label()

            commit_btn = QPushButton("Commit play")
            commit_btn.clicked.connect(self._commit_preview)
            tb.addWidget(commit_btn)
            cancel_prev_btn = QPushButton("Cancel preview")
            cancel_prev_btn.clicked.connect(self._cancel_preview)
            tb.addWidget(cancel_prev_btn)

            self.setStatusBar(QStatusBar())
            self.statusBar().showMessage("Load a lexicon to begin.")

            self._rack_edit.textChanged.connect(self._on_rack_text_changed)

        def _build_central(self) -> None:
            splitter = QSplitter(Qt.Orientation.Horizontal)

            left_box = QGroupBox(
                "Board — bold = preview; empty squares build preview; "
                "occupied = committed (setup); right-click = premium"
            )
            left_l = QVBoxLayout(left_box)
            self._board_table = QTableWidget(BOARD_SIZE, BOARD_SIZE)
            self._board_table.setHorizontalHeaderLabels(
                [chr(ord("A") + c) for c in range(BOARD_SIZE)]
            )
            self._board_table.setVerticalHeaderLabels([str(r + 1) for r in range(BOARD_SIZE)])
            hdr_h = self._board_table.horizontalHeader()
            hdr_h.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            hdr_v = self._board_table.verticalHeader()
            hdr_v.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            cell = 32
            for i in range(BOARD_SIZE):
                self._board_table.setColumnWidth(i, cell)
                self._board_table.setRowHeight(i, cell)
            self._board_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._board_table.customContextMenuRequested.connect(self._board_context_menu)
            self._board_table.itemChanged.connect(self._on_board_item_changed)
            left_l.addWidget(self._board_table)
            splitter.addWidget(left_box)

            right_box = QGroupBox("Top moves")
            right_l = QVBoxLayout(right_box)
            self._moves_table = QTableWidget(0, 3)
            self._moves_table.setHorizontalHeaderLabels(["Score", "Play", "Detail"])
            self._moves_table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents
            )
            self._moves_table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            self._moves_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            self._moves_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self._moves_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self._moves_table.itemSelectionChanged.connect(self._preview_selected_move)
            right_l.addWidget(self._moves_table)
            splitter.addWidget(right_box)

            splitter.setStretchFactor(0, 2)
            splitter.setStretchFactor(1, 1)
            self.setCentralWidget(splitter)

            self._init_board_cells()

        def _init_board_cells(self) -> None:
            self._board_updating = True
            try:
                base = default_bonuses()
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        lab_idx = int(base[r][c])
                        it = QTableWidgetItem("")
                        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        it.setData(Qt.ItemDataRole.UserRole, lab_idx)
                        it.setBackground(_bonus_brush_for_label(BONUS_LABELS[lab_idx]))
                        flags = (
                            Qt.ItemFlag.ItemIsEnabled
                            | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsEditable
                        )
                        it.setFlags(flags)
                        self._board_table.setItem(r, c, it)
            finally:
                self._board_updating = False

        def _sync_lex_label(self) -> None:
            p = self._lexicon_path.strip()
            if p:
                self._lex_label.setText(f"Lexicon: {Path(p).name}")
                self._lex_label.setToolTip(p)
            else:
                self._lex_label.setText("Lexicon: —")
                self._lex_label.setToolTip("")

        def _open_lexicon_dialog(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open lexicon", "", "Text (*.txt);;All (*.*)"
            )
            if path:
                self._lexicon_path = path
                self._sync_lex_label()
                self._load_lexicon_silent()

        def _load_lexicon_silent(self) -> None:
            path = self._lexicon_path.strip()
            if not path or not os.path.isfile(path):
                self.statusBar().showMessage("Lexicon path missing or not a file.")
                return
            try:
                self.gaddag = Gaddag.from_file(path)
                self.word_set = load_words_from_file(path)
                self.statusBar().showMessage(f"Loaded {len(self.word_set)} words from {path}")
                self._update_preview_status()
            except OSError as e:
                self.statusBar().showMessage(f"Lexicon error: {e}")

        def _set_cell_bonus(self, r: int, c: int, bonus_idx: int) -> None:
            it = self._board_table.item(r, c)
            if not it:
                return
            bonus_idx = max(0, min(len(BONUS_LABELS) - 1, bonus_idx))
            it.setData(Qt.ItemDataRole.UserRole, bonus_idx)
            it.setBackground(_bonus_brush_for_label(BONUS_LABELS[bonus_idx]))

        def _board_context_menu(self, pos) -> None:
            idx = self._board_table.indexAt(pos)
            if not idx.isValid():
                return
            r, c = idx.row(), idx.column()
            menu = QMenu(self)
            for i, lab in enumerate(BONUS_LABELS):
                act = QAction(lab, self)
                act.triggered.connect(lambda checked=False, bi=i: self._set_cell_bonus(r, c, bi))
                menu.addAction(act)
            menu.exec(self._board_table.viewport().mapToGlobal(pos))

        def _on_rack_text_changed(self, _t: str) -> None:
            self._update_preview_status()

        def _refresh_board_display(self) -> None:
            self._board_updating = True
            try:
                base_font = self._board_table.font()
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        it = self._board_table.item(r, c)
                        if not it:
                            continue
                        ch_c = self._committed_letters[r][c]
                        nt = self._preview_tiles.get((r, c))
                        if nt is not None:
                            disp: str = nt.ch.lower() if nt.from_blank else nt.ch
                            bold = True
                        elif ch_c:
                            disp = ch_c
                            bold = False
                        else:
                            disp = ""
                            bold = False
                        it.setText(disp)
                        f = QFont(base_font)
                        f.setBold(bold)
                        it.setFont(f)
            finally:
                self._board_updating = False
            self._update_preview_status()

        def _board_committed_with_bonuses(self) -> Board:
            b = Board()
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    b.letters[r][c] = self._committed_letters[r][c]
                    it = self._board_table.item(r, c)
                    raw_bonus = it.data(Qt.ItemDataRole.UserRole) if it else None
                    bi = int(raw_bonus) if raw_bonus is not None else 0
                    bi = max(0, min(len(BONUS_LABELS) - 1, bi))
                    b.bonuses[r][c] = Bonus(bi)
            return b

        def _update_preview_status(self) -> None:
            if not self._preview_tiles:
                self._preview_score_label.setText("Preview: —")
                return
            if not self.word_set:
                self._preview_score_label.setText("Preview: — (load lexicon)")
                return
            board = self._board_committed_with_bonuses()
            rack = rack_from_string(self._rack_edit.text())
            out = validate_manual_play(
                board, list(self._preview_tiles.values()), rack, self.word_set
            )
            if isinstance(out, ValidatedPlay):
                self._preview_score_label.setText(f"Preview: {out.score} points")
            else:
                short = out if len(out) <= 40 else out[:37] + "…"
                self._preview_score_label.setText(f"Preview: — ({short})")

        def _refresh_score_turn_label(self) -> None:
            p1, p2 = self._player_scores[0], self._player_scores[1]
            turn_n = self._active_player + 1
            self._score_turn_label.setText(f"P1: {p1} | P2: {p2} | Turn: P{turn_n}")

        def _consume_rack_after_play(self, tiles: Sequence[NewTile]) -> None:
            chars: List[str] = []
            for c in self._rack_edit.text().upper().replace(" ", ""):
                if c.isalpha() or c == "?":
                    chars.append(c)
            for t in tiles:
                if t.from_blank:
                    if "?" in chars:
                        chars.remove("?")
                    else:
                        return
                else:
                    L = t.ch.upper()
                    for i, x in enumerate(chars):
                        if x == L:
                            del chars[i]
                            break
                    else:
                        return
            self._rack_edit.setText("".join(chars))

        def _commit_preview(self) -> None:
            if not self._preview_tiles:
                QMessageBox.information(self, "Commit", "No preview tiles to commit.")
                return
            if not self.word_set:
                QMessageBox.warning(self, "Lexicon", "Load a lexicon first.")
                return
            board = self._board_committed_with_bonuses()
            rack = rack_from_string(self._rack_edit.text())
            out = validate_manual_play(
                board, list(self._preview_tiles.values()), rack, self.word_set
            )
            if isinstance(out, str):
                QMessageBox.warning(self, "Invalid play", out)
                return
            for t in out.new_tiles:
                self._committed_letters[t.r][t.c] = (
                    t.ch.lower() if t.from_blank else t.ch
                )
            tiles_merged = out.new_tiles
            self._preview_tiles.clear()
            self._consume_rack_after_play(tiles_merged)
            self._player_scores[self._active_player] += out.score
            self._active_player = 1 - self._active_player
            self._refresh_score_turn_label()
            self._refresh_board_display()

        def _cancel_preview(self) -> None:
            if not self._preview_tiles:
                return
            self._preview_tiles.clear()
            self._refresh_board_display()

        def _on_board_item_changed(self, item: QTableWidgetItem) -> None:
            if self._board_updating:
                return
            r, c = item.row(), item.column()
            txt = item.text().strip()
            if len(txt) > 1:
                self._board_updating = True
                try:
                    item.setText(txt[0])
                finally:
                    self._board_updating = False
                txt = txt[0]
            try:
                norm: Optional[str] = normalize_board_letter(txt) if txt else None
            except ValueError as e:
                QMessageBox.warning(
                    self,
                    "Board",
                    f"Cell ({r + 1},{chr(ord('A') + c)}): {e}",
                )
                self._refresh_board_display()
                return

            if self._committed_letters[r][c] is not None:
                if norm is None:
                    self._committed_letters[r][c] = None
                else:
                    self._committed_letters[r][c] = norm
                self._preview_tiles.pop((r, c), None)
            else:
                if norm is None:
                    self._preview_tiles.pop((r, c), None)
                else:
                    if norm.islower():
                        self._preview_tiles[(r, c)] = NewTile(r, c, norm.upper(), True)
                    else:
                        self._preview_tiles[(r, c)] = NewTile(r, c, norm, False)
            self._refresh_board_display()

        def _clear_letters(self) -> None:
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    self._committed_letters[r][c] = None
            self._preview_tiles.clear()
            self._player_scores = [0, 0]
            self._active_player = 0
            self._refresh_score_turn_label()
            self._refresh_board_display()

        def _reset_premiums(self) -> None:
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    self._set_cell_bonus(r, c, int(self._default_bonuses[r][c]))

        def _find_moves(self) -> None:
            if self.gaddag is None or not self.word_set:
                QMessageBox.warning(self, "Lexicon", "Load a lexicon first.")
                return
            board = self._board_committed_with_bonuses()
            topn = self._topn_spin.value()
            rack = rack_from_string(self._rack_edit.text())
            if not rack:
                QMessageBox.warning(self, "Rack", "Enter rack letters (use ? for blanks).")
                return
            plays = find_moves(board, rack, self.gaddag, self.word_set, top_n=topn)
            self._snapshot_letters = [
                [self._committed_letters[r][c] for c in range(BOARD_SIZE)]
                for r in range(BOARD_SIZE)
            ]
            self._plays_cache = plays

            self._moves_table.setRowCount(len(plays))
            for i, p in enumerate(plays):
                s_item = QTableWidgetItem(str(p.score))
                s_item.setFlags(s_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                s_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self._moves_table.setItem(i, 0, s_item)
                pl_item = QTableWidgetItem(p.summary())
                pl_item.setFlags(pl_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._moves_table.setItem(i, 1, pl_item)
                d_item = QTableWidgetItem(p.detail())
                d_item.setFlags(d_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._moves_table.setItem(i, 2, d_item)
            self.statusBar().showMessage(f"{len(plays)} moves (cap {topn})")

        def _preview_selected_move(self) -> None:
            if not self._plays_cache or self._snapshot_letters is None:
                return
            rows = self._moves_table.selectionModel().selectedRows()
            if not rows:
                return
            idx = rows[0].row()
            if idx < 0 or idx >= len(self._plays_cache):
                return
            play = self._plays_cache[idx]
            conflict = False
            for nt in play.new_tiles:
                if self._committed_letters[nt.r][nt.c] is not None:
                    conflict = True
                    break
            if conflict:
                QMessageBox.warning(
                    self,
                    "Preview",
                    "Selected move overlaps committed tiles; clear those squares first.",
                )
                return
            self._preview_tiles = {(nt.r, nt.c): nt for nt in play.new_tiles}
            self._refresh_board_display()

        def _save_state(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Save board", "", "JSON (*.json)")
            if not path:
                return
            b = self._board_committed_with_bonuses()
            letters = [
                [self._committed_letters[r][c] for c in range(BOARD_SIZE)]
                for r in range(BOARD_SIZE)
            ]
            bonuses = [[int(b.bonuses[r][c]) for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)]
            data = {
                "letters": letters,
                "bonuses": bonuses,
                "rack": self._rack_edit.text(),
                "lexicon": self._lexicon_path,
                "scores": list(self._player_scores),
                "active_player": self._active_player,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.statusBar().showMessage(f"Saved {path}")

        def _load_state(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load board", "", "JSON (*.json);;All (*.*)"
            )
            if not path or not os.path.isfile(path):
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            letters = data.get("letters")
            bonuses = data.get("bonuses")
            if not isinstance(letters, list):
                QMessageBox.critical(self, "Load", "Invalid file")
                return
            self._preview_tiles.clear()
            self._board_updating = True
            try:
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        it = self._board_table.item(r, c)
                        ch: Optional[str] = None
                        if r < len(letters) and c < len(letters[r]):
                            raw = letters[r][c]
                            if raw is not None and str(raw).strip():
                                try:
                                    ch = normalize_board_letter(str(raw).strip()[0])
                                except ValueError:
                                    ch = None
                        self._committed_letters[r][c] = ch
                        if isinstance(bonuses, list) and r < len(bonuses) and c < len(bonuses[r]):
                            if bonuses[r][c] is not None:
                                bi = int(bonuses[r][c])
                                lab_i = bi if 0 <= bi < len(BONUS_LABELS) else 0
                                it.setData(Qt.ItemDataRole.UserRole, lab_i)
                                it.setBackground(_bonus_brush_for_label(BONUS_LABELS[lab_i]))
            finally:
                self._board_updating = False
            raw_scores = data.get("scores")
            if isinstance(raw_scores, list) and len(raw_scores) >= 2:
                try:
                    self._player_scores = [int(raw_scores[0]), int(raw_scores[1])]
                except (TypeError, ValueError):
                    self._player_scores = [0, 0]
            else:
                self._player_scores = [0, 0]
            ap_raw = data.get("active_player")
            if ap_raw is not None:
                try:
                    ai = int(ap_raw)
                    self._active_player = ai if ai in (0, 1) else 0
                except (TypeError, ValueError):
                    self._active_player = 0
            else:
                self._active_player = 0
            self._refresh_score_turn_label()
            if "rack" in data:
                self._rack_edit.setText(str(data["rack"]))
            if data.get("lexicon"):
                self._lexicon_path = str(data["lexicon"])
                self._sync_lex_label()
                self._load_lexicon_silent()
            self._refresh_board_display()
            self.statusBar().showMessage(f"Loaded {path}")


def main() -> None:
    if _PYSIDE_IMPORT_ERROR is not None or ScrabbleMainWindow is None:
        sys.stderr.write(
            "scrabble-gui requires PySide6. Install the GUI extra, for example:\n"
            '  pip install "scrabble-engine[gui]"\n'
            "or from a checkout:\n"
            '  pip install -e ".[gui]"\n'
        )
        raise SystemExit(1) from _PYSIDE_IMPORT_ERROR

    try:
        app = QApplication(sys.argv)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(
            "scrabble-gui needs a GUI display (X11/Wayland). Qt reported:\n"
            f"  {exc}\n\n"
            "If you are on SSH, reconnect with X11 forwarding (e.g. ssh -Y …) "
            "or set DISPLAY to your desktop session.\n"
            "On a machine with no display, try: xvfb-run -a scrabble-gui\n"
        )
        raise SystemExit(1) from exc

    win = ScrabbleMainWindow()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
