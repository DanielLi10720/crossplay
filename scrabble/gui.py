"""Tkinter GUI for the Scrabble move finder."""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from scrabble.board import BOARD_SIZE, Bonus, Board, default_bonuses, normalize_board_letter, rack_from_string
from scrabble.gaddag import Gaddag, load_words_from_file
from scrabble.move_gen import Play, find_moves

# Index matches Bonus enum value 0..5
BONUS_LABELS = ("Normal", "DL", "TL", "DW", "TW", "Star")

# Vertical offset so row-0 premium combobox fits above the letter cell
BOARD_TOP_PAD = 22


def _bonus_bg(label: str) -> str:
    idx = BONUS_LABELS.index(label) if label in BONUS_LABELS else 0
    styles = ("#f5f5f5", "#c8e6c9", "#66bb6a", "#ffccbc", "#ff7043", "#ffe082")
    return styles[idx]


class ScrabbleGui:
    def __init__(self) -> None:
        # #region agent log
        _ts = int(__import__("time").time() * 1000)
        _disp = os.environ.get("DISPLAY")
        _dbg = {
            "H1_DISPLAY_missing": not _disp,
            "H2_ssh_without_DISPLAY": bool(os.environ.get("SSH_CONNECTION")) and not _disp,
            "H3_wayland_but_no_DISPLAY": bool(os.environ.get("WAYLAND_DISPLAY")) and not _disp,
            "H4_stdin_is_tty": __import__("sys").stdin.isatty(),
            "H5_XDG_SESSION_TYPE": os.environ.get("XDG_SESSION_TYPE"),
            "DISPLAY_repr": repr(_disp)[:120],
            "WAYLAND_DISPLAY_repr": repr(os.environ.get("WAYLAND_DISPLAY"))[:120],
        }
        _lp = Path("/home/dl4247/crossplay/.cursor/debug-b6cda5.log")
        _lp.parent.mkdir(parents=True, exist_ok=True)
        _lp.open("a", encoding="utf-8").write(
            json.dumps(
                {
                    "sessionId": "b6cda5",
                    "runId": "pre-fix",
                    "hypothesisId": "H1-H5",
                    "location": "scrabble/gui.py:ScrabbleGui.__init__:preTk",
                    "message": "probe before Tk()",
                    "data": _dbg,
                    "timestamp": _ts,
                }
            )
            + "\n"
        )
        # #endregion
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            # #region agent log
            _ts_e = int(__import__("time").time() * 1000)
            _lp.open("a", encoding="utf-8").write(
                json.dumps(
                    {
                        "sessionId": "b6cda5",
                        "runId": "post-fix",
                        "hypothesisId": "TclExit",
                        "location": "scrabble/gui.py:ScrabbleGui.__init__:Tk TclError",
                        "message": "Tk() failed; exiting with guidance",
                        "data": {"tcl_error": str(exc)[:200]},
                        "timestamp": _ts_e,
                    }
                )
                + "\n"
            )
            # #endregion
            sys.stderr.write(
                "scrabble-gui needs a GUI display (X11/Wayland). Tkinter reported:\n"
                f"  {exc}\n\n"
                "If you are on SSH, reconnect with X11 forwarding (e.g. ssh -Y …) or set DISPLAY to your desktop session.\n"
                "On a machine with no display, try: xvfb-run -a scrabble-gui\n"
            )
            raise SystemExit(1) from exc
        self.root.title("Scrabble move finder")
        self.root.geometry("1150x760")

        self.gaddag: Optional[Gaddag] = None
        self.word_set: set[str] = set()
        self._plays_cache: List[Play] = []
        self._snapshot_letters: Optional[List[List[Optional[str]]]] = None

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
        canvas = tk.Canvas(
            canvas_holder,
            width=30 * BOARD_SIZE + 40,
            height=BOARD_TOP_PAD + 34 * BOARD_SIZE + 36,
        )
        vs = ttk.Scrollbar(canvas_holder, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vs.set)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._letter_entries: List[List[tk.Entry]] = []
        self._bonus_vars: List[List[tk.StringVar]] = []
        base = default_bonuses()
        cell_w, cell_h = 34, 34
        y_off = BOARD_TOP_PAD
        for r in range(BOARD_SIZE):
            tk.Label(canvas, text=str(r + 1), width=2).place(x=4, y=y_off + 16 + r * cell_h)
            row_e: List[tk.Entry] = []
            row_sv: List[tk.StringVar] = []
            for c in range(BOARD_SIZE):
                bcell = base[r][c]
                label = BONUS_LABELS[int(bcell)]
                sv = tk.StringVar(value=label)
                row_sv.append(sv)
                cb = ttk.Combobox(
                    canvas,
                    textvariable=sv,
                    values=BONUS_LABELS,
                    width=5,
                    state="readonly",
                    font=("TkDefaultFont", 7),
                )
                cb.place(x=22 + c * cell_w, y=y_off + 2 + r * cell_h, width=cell_w - 2, height=18)
                ent = tk.Entry(canvas, width=2, justify="center", relief=tk.FLAT, bd=1)
                ent.place(x=28 + c * cell_w, y=y_off + 20 + r * cell_h, width=22, height=22)
                ent.configure(bg=_bonus_bg(label))

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
        self.tree.bind("<<TreeviewSelect>>", self._preview_selected_move)

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
        self._snapshot_letters = [[board.letters[r][c] for c in range(BOARD_SIZE)] for r in range(BOARD_SIZE)]
        self._plays_cache = plays
        for i in self.tree.get_children():
            self.tree.delete(i)
        for p in plays:
            self.tree.insert("", tk.END, values=(p.score, p.summary(), p.detail()))
        self.status_var.set(f"{len(plays)} moves (cap {topn})")

    def _preview_selected_move(self, _evt: Optional[tk.Event] = None) -> None:
        if not self._plays_cache or self._snapshot_letters is None:
            return
        sel = self.tree.selection()
        if not sel:
            return
        try:
            idx = self.tree.index(sel[0])
        except tk.TclError:
            return
        if idx < 0 or idx >= len(self._plays_cache):
            return
        play = self._plays_cache[idx]
        snap = self._snapshot_letters
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                ent = self._letter_entries[r][c]
                ent.delete(0, tk.END)
                ch = snap[r][c]
                if ch:
                    ent.insert(0, ch)
        for nt in play.new_tiles:
            ch_disp = nt.ch.lower() if nt.from_blank else nt.ch
            ent = self._letter_entries[nt.r][nt.c]
            ent.delete(0, tk.END)
            ent.insert(0, ch_disp)
            lab = self._bonus_vars[nt.r][nt.c].get()
            ent.configure(bg=_bonus_bg(lab))

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
