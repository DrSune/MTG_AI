"""Name masking: the contamination probe (docs/DESIGN_BENCHMARK.md §5).

A model that has read every Magic card ever printed can answer from memory instead of from the
text in front of it. Masking replaces every card name, including inside oracle text, with a
stable salted label (``C017``). The score difference between real and masked names, the masking
gap, measures how much a model leans on memorised card knowledge rather than the rules text.

Rules:
- full names map to labels ranked by ``sha256(salt:name)``, so the labels say nothing about the
  card;
- a legendary short name ("Kaervek" of "Kaervek, the Spiteful") takes the full name's label when
  only one card has it, otherwise its own label. That keeps self-references pointing at the card
  and planeswalker subtypes consistent;
- basic land and token names are kept, because they double as types ("Forest you control",
  "a 1/1 Soldier token").

Honest limit: multi-word legendary names written differently inside other cards' text are not
caught. ``leaks`` measures what survives instead of assuming nothing does.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable

BASIC_LAND_NAMES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"})


class NameMasker:
    def __init__(self, names: Iterable[str], salt: str, keep: Iterable[str] = ()) -> None:
        kept = set(keep) | BASIC_LAND_NAMES
        full = sorted({n for n in names if n and n not in kept})
        ranked = sorted(full, key=lambda n: hashlib.sha256(f"{salt}:{n}".encode()).hexdigest())
        self._labels: dict[str, str] = {n: f"C{i + 1:03d}" for i, n in enumerate(ranked)}
        shorts = Counter(n.split(",", 1)[0] for n in full if "," in n)
        extra = 0
        for name in full:
            if "," not in name:
                continue
            short = name.split(",", 1)[0].strip()
            if not short or short in self._labels or short in kept:
                continue
            if shorts[short] == 1:
                self._labels[short] = self._labels[name]
            else:
                extra += 1
                self._labels[short] = f"S{extra:03d}"
        # Longest first, so "Basri Ket" is replaced before "Basri"; whole words only.
        terms = sorted(self._labels, key=len, reverse=True)
        self._pattern = (
            re.compile(r"(?<![\w])(" + "|".join(re.escape(t) for t in terms) + r")(?![\w])")
            if terms
            else None
        )

    def label(self, name: str) -> str:
        # A name outside the pool (a pack's synthetic "Garruk Omenbound") still has its known
        # terms masked: found by the leak test on 2026-10-24.
        return self._labels.get(name) or self.mask(name)

    def mask(self, text: str) -> str:
        if not text or self._pattern is None:
            return text
        return self._pattern.sub(lambda m: self._labels[m.group(1)], text)

    def leaks(self, text: str) -> list[str]:
        """Masked terms that still appear in ``text`` (empty for a clean masking)."""
        if not text or self._pattern is None:
            return []
        return sorted({m.group(1) for m in self._pattern.finditer(text)})
