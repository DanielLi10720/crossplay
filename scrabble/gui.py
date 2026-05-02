"""Tkinter GUI for the Scrabble move finder."""

from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from scrabble.board import BOARD_SIZE, Bonus, Board, default_bonuses, normalize_board_letter, rack_from_string
from scrabble.gaddag import Gaddag, load_words_from_file
from scrabble.move_gen import find_moves

# Index matches Bonus enum value 0..5
BONUS_LABELS = ("Normal", "DL", "TL", "DW", "TW", "Star")


def _bonus_bg(label: str) -> str:
    idx = BONUS_LABELS.index(label) if label in BONUS_LABELS else 0
    styles = ("#f5f5f5", "#c8e6c9", "#66bb6a", "#ffccbc", "#ff7043", "#ffe082")
    return styles[idx]


class ScrabbleGui:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Scrabble move finder")
        self.root.geometry("1150x760")

        self.gaddag: Optional[Gaddag] = None
        self.word_set: set[str] = set()

        default_lex = Path(__file__).resolve().parent.parent / "data" / "sample_words.txt"
        self.lexicon_path = tk.StringVar(value=str(default_lex) if default_lex.exists() else "")
        self.rack_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Load a lexicon to begin.")

        top = ttk.Frame(self.root, padding=6)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Lexicon:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.lexicon_path, width=48).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Browse…", command=self._browse_lexicon).pack(side=tk.LEFT)
        ttk.Button(top, text="Load lexicon", command=self._load_lexicon).pack(side=tk.LEFT, padx=4)

        rack_fr = ttk.Frame(self.root, padding=(6, 0))
        rack_fr.pack(fill=tk.X)
        ttk.Label(rack_fr, text="Rack (A–Z, ? blank):").pack(side=tk.LEFT)
        ttk.Entry(rack_fr, textvariable=self.rack_var, width=18).pack(side=tk.LEFT, padx=4)
        ttk.Label(rack_fr, text="Top N:").pack(side=tk.LEFT, padx=(14, 0))
        self.topn_var = tk.StringVar(value="50")
        ttk.Entry(rack_fr, textvariable=self.topn_var, width=5).pack(side=tk.LEFT, padx=4)

        btn_fr = ttk.Frame(self.root, padding=6)
        btn_fr.pack(fill=tk.X)
        ttk.Button(btn_fr, text="Find moves", command=self._find_moves).pack(side=tk.LEFT)
        ttk.Button(btn_fr, text="Clear letters", command=self._clear_letters).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_fr, text="Reset premiums", command=self._reset_premiums).pack(side=tk.LEFT)
        ttk.Button(btn_fr, text="Save JSON…", command=self._save_state).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_fr, text="Load JSON…", command=self._load_state).pack(side=tk.LEFT)

        ttk.Label(self.root, textvariable=self.status_var).pack(fill=tk.X, padx=8, pady=4)

        pan = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left = ttk.Frame(pan, width=540)
        right = ttk.Frame(pan, width=540)
        pan.add(left, weight=2)
        pan.add(right, weight=1)

        grid_fr = ttk.LabelFrame(left, text="Board (lowercase = blank played as that letter)")
        grid_fr.pack(fill=tk.BOTH, expand=True)

        head = tk.Frame(grid_fr)
        head.pack()
        tk.Label(head, text="", width=1).grid(row=0, column=0)
        for c in range(BOARD_SIZE):
            tk.Label(head, text=chr(ord("A") + c), width=3).grid(row=0, column=1 + c)

        canvas_holder = tk.Frame(grid_fr)
        canvas_holder.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(canvas_holder, width=30 * BOARD_SIZE + 40, height=26 * BOARD_SIZE + 20)
        vs = ttk.Scrollbar(canvas_holder, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vs.set)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._letter_entries: List[List[tk.Entry]] = []
        self._bonus_vars: List[List[tk.StringVar]] = []
        base = default_bonuses()
        cell_w, cell_h = 34, 34
        for r in range(BOARD_SIZE):
            tk.Label(canvas, text=str(r + 1), width=2).place(x=4, y=16 + r * cell_h)
            row_e: List[tk.Entry] = []
            row_sv: List[tk.StringVar] = []
            for c in range(BOARD_SIZE):
                bcell = base[r][c]
                label = BONUS_LABELS[int(bcell)]
                sv = tk.StringVar(value=label)
                row_sv.append(sv)
                ent = tk.Entry(canvas, width=2, justify="center", relief=tk.FLAT, bd=1)
                ent.place(x=28 + c * cell_w, y=12 + r * cell_h, width=22, height=22)
                ent.configure(bg=_bonus_bg(label))
                cb = ttk.Combobox(
                    canvas,
                    textvariable=sv,
                    values=BONUS_LABELS,
                    width=5,
                    state="readonly",
                    font=("TkDefaultFont", 7),
                )
                cb.place(x=22 + c * cell_w, y=30 + r * cell_h, width=cell_w - 2, height=18)

                def make_sel(e: tk.Entry = ent, svar: tk.StringVar = sv):
                    def _on(_evt=None) -> None:
                        e.configure(bg=_bonus_bg(svar.get()))

                    return _on

                cb.bind("<<ComboboxSelected>>", make_sel())
                row_e.append(ent)
            self._letter_entries.append(row_e)
            self._bonus_vars.append(row_sv)

        self._default_bonuses = [[base[r][c] for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)]

        res_fr = ttk.LabelFrame(right, text="Top moves")
        res_fr.pack(fill=tk.BOTH, expand=True)
        cols = ("score", "summary", "detail")
        self.tree = ttk.Treeview(res_fr, columns=cols, show="headings", height=24)
        self.tree.heading("score", text="Score")
        self.tree.heading("summary", text="Play")
        self.tree.heading("detail", text="Detail")
        self.tree.column("score", width=50, anchor="e")
        self.tree.column("summary", width=170, anchor="w")
        self.tree.column("detail", width=380, anchor="w")
        tvsb = ttk.Scrollbar(res_fr, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tvsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tvsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._load_lexicon_silent()
        self._reset_premiums()

    def _browse_lexicon(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if p:
            self.lexicon_path.set(p)

    def _load_lexicon_silent(self) -> None:
        path = self.lexicon_path.get().strip()
        if not path or not os.path.isfile(path):
            self.status_var.set("Lexicon path missing or not a file.")
            return
        try:
            self.gaddag = Gaddag.from_file(path)
            self.word_set = load_words_from_file(path)
            self.status_var.set(f"Loaded {len(self.word_set)} words from {path}")
        except OSError as e:
            self.status_var.set(f"Lexicon error: {e}")

    def _load_lexicon(self) -> None:
        self._load_lexicon_silent()
        messagebox.showinfo("Lexicon", self.status_var.get())

    def _board_from_ui(self) -> Board:
        b = Board()
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                txt = self._letter_entries[r][c].get().strip()
                if txt:
                    txt = txt[0]
                    self._letter_entries[r][c].delete(0, tk.END)
                    self._letter_entries[r][c].insert(0, txt)
                try:
                    b.letters[r][c] = normalize_board_letter(txt)
                except ValueError as e:
                    raise ValueError(f"Cell ({r+1},{chr(ord('A')+c)}): {e}") from e
                name = self._bonus_vars[r][c].get()
                idx = BONUS_LABELS.index(name) if name in BONUS_LABELS else 0
                b.bonuses[r][c] = Bonus(idx)
        return b

    def _clear_letters(self) -> None:
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                self._letter_entries[r][c].delete(0, tk.END)

    def _reset_premiums(self) -> None:
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                lab = BONUS_LABELS[int(self._default_bonuses[r][c])]
                self._bonus_vars[r][c].set(lab)
                self._letter_entries[r][c].configure(bg=_bonus_bg(lab))

    def _find_moves(self) -> None:
        if self.gaddag is None or not self.word_set:
            messagebox.showwarning("Lexicon", "Load a lexicon first.")
            return
        try:
            board = self._board_from_ui()
        except ValueError as e:
            messagebox.showerror("Board", str(e))
            return
        try:
            topn = max(1, min(500, int(self.topn_var.get().strip())))
        except ValueError:
            topn = 50
        rack = rack_from_string(self.rack_var.get())
        if not rack:
            messagebox.showwarning("Rack", "Enter rack letters (use ? for blanks).")
            return
        plays = find_moves(board, rack, self.gaddag, self.word_set, top_n=topn)
        for i in self.tree.get_children():
            self.tree.delete(i)
        for p in plays:
            self.tree.insert("", tk.END, values=(p.score, p.summary(), p.detail()))
        self.status_var.set(f"{len(plays)} moves (cap {topn})")

    def _save_state(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            b = self._board_from_ui()
        except ValueError as e:
            messagebox.showerror("Board", str(e))
            return
        letters = [[b.letters[r][c] for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)]
        bonuses = [[int(b.bonuses[r][c]) for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)]
        data = {
            "letters": letters,
            "bonuses": bonuses,
            "rack": self.rack_var.get(),
            "lexicon": self.lexicon_path.get(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        messagebox.showinfo("Saved", path)

    def _load_state(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path or not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        letters = data.get("letters")
        bonuses = data.get("bonuses")
        if not isinstance(letters, list):
            messagebox.showerror("Load", "Invalid file")
            return
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                self._letter_entries[r][c].delete(0, tk.END)
                ch = letters[r][c]
                if ch:
                    self._letter_entries[r][c].insert(0, str(ch))
                if isinstance(bonuses, list) and bonuses[r][c] is not None:
                    bi = int(bonuses[r][c])
                    lab_bonus = BONUS_LABELS[bi] if 0 <= bi < len(BONUS_LABELS) else "Normal"
                    self._bonus_vars[r][c].set(lab_bonus)
                lab = self._bonus_vars[r][c].get()
                self._letter_entries[r][c].configure(bg=_bonus_bg(lab))
        if "rack" in data:
            self.rack_var.set(str(data["rack"]))
        if data.get("lexicon"):
            self.lexicon_path.set(str(data["lexicon"]))
            self._load_lexicon_silent()
        messagebox.showinfo("Loaded", path)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ScrabbleGui().run()


if __name__ == "__main__":
    main()
