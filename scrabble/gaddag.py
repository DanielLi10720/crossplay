"""GADDAG (directed acyclic word graph) for Scrabble move generation."""

from __future__ import annotations

from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

SEP = -1  # separator between reversed left part and right part


class Gaddag:
    """
    GADDAG from Steven Gordon's representation.
    For word w and split index i (0 <= i <= len(w)):
        path = reverse(w[:i]) + SEP + w[i:]
    """

    __slots__ = ("_nodes", "_terminal")

    def __init__(self) -> None:
        self._nodes: List[Dict[int, int]] = [{}]
        self._terminal: List[bool] = [False]

    def node_count(self) -> int:
        return len(self._nodes)

    @staticmethod
    def _letter_key(ch: str) -> int:
        o = ord(ch.upper())
        if not (65 <= o <= 90):
            raise ValueError(f"Bad letter: {ch!r}")
        return o - 65

    def _new_node(self) -> int:
        self._nodes.append({})
        self._terminal.append(False)
        return len(self._nodes) - 1

    def insert(self, word: str) -> None:
        w = word.strip().upper()
        if not w or not w.isalpha():
            return
        n = len(w)
        for i in range(n + 1):
            prefix_rev = w[:i][::-1]
            suffix = w[i:]
            node = 0
            for ch in prefix_rev:
                lk = self._letter_key(ch)
                nxt = self._nodes[node].get(lk)
                if nxt is None:
                    nxt = self._new_node()
                    self._nodes[node][lk] = nxt
                node = nxt
            nxt = self._nodes[node].get(SEP)
            if nxt is None:
                nxt = self._new_node()
                self._nodes[node][SEP] = nxt
            node = nxt
            for ch in suffix:
                lk = self._letter_key(ch)
                nxt = self._nodes[node].get(lk)
                if nxt is None:
                    nxt = self._new_node()
                    self._nodes[node][lk] = nxt
                node = nxt
            self._terminal[node] = True

    def build_from_words(self, words: Iterable[str]) -> None:
        for w in words:
            self.insert(w)

    @classmethod
    def from_file(cls, path: str, encoding: str = "utf-8") -> Gaddag:
        g = cls()
        with open(path, "r", encoding=encoding, errors="replace") as f:
            for line in f:
                w = line.strip()
                if not w or w.startswith("#"):
                    continue
                g.insert(w)
        return g

    def is_terminal(self, node: int) -> bool:
        return self._terminal[node]

    def transition(self, node: int, key: int) -> Optional[int]:
        return self._nodes[node].get(key)

    def iter_letter_edges(self, node: int) -> Iterator[Tuple[int, int]]:
        for k, v in self._nodes[node].items():
            if k != SEP:
                yield k, v

    def sep_child(self, node: int) -> Optional[int]:
        return self._nodes[node].get(SEP)


def load_words_from_file(path: str) -> Set[str]:
    s: Set[str] = set()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            w = line.strip().upper()
            if w and w.isalpha() and 2 <= len(w) <= 15:
                s.add(w)
    return s
