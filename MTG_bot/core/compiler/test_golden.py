"""Tests for the T5 golden write/verify module (golden.py).

One shared M21 ingest + one shared registry in ``setUpClass``.  Write runs
and drift-detection verifies target ``tempfile`` roots so the production
tree is never *rewritten* by the test suite; the committed-baseline test
reads the production ``MTG_bot/core/golden`` tree exactly like the
harness's default verify-only path.  Covers PC-4 (write-then-verify
stability, single-byte tamper + missing + stale detection, and a stable
committed baseline) and PC-9 (fingerprint-multiset determinism across
independent compilations).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from MTG_bot.core.compiler.coverage import PINNED_ENTRIES, build_full_registry
from MTG_bot.core.compiler.golden import (
    GOLDEN_ROOT,
    fingerprint_multiset,
    verify_goldens,
    write_goldens,
)
from MTG_bot.core.compiler.ingest import ingest_pool

_M21 = Path(__file__).resolve().parents[2] / "data" / "M21.json"

_STALE_NAME = "zz-stale-test-entry"


class TestGoldens(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21)
        cls.registry = build_full_registry()

    def _fresh_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="golden_test_"))
        self.addCleanup(shutil.rmtree, root)
        return root

    def _first_oid(self) -> str:
        """A deterministic oracle id present in the pool."""
        return min(self.pool)

    def test_write_then_verify_stable(self) -> None:
        root = self._fresh_root()
        written = write_goldens(self.pool, self.registry, "M21", root=root)
        self.assertEqual(written, PINNED_ENTRIES)
        directory = root / "M21"
        self.assertEqual(len(list(directory.glob("*.json"))), PINNED_ENTRIES)
        # PC-4: a fresh write followed by a recompile+compare is stable.
        self.assertEqual(verify_goldens(self.pool, self.registry, "M21", root=root), [])

    def test_verify_missing_dir_reports_single_diff(self) -> None:
        root = self._fresh_root()
        self.assertEqual(
            verify_goldens(self.pool, self.registry, "M21", root=root),
            [f"golden dir {root / 'M21'} does not exist"],
        )

    def test_verify_detects_mismatch_and_stale(self) -> None:
        root = self._fresh_root()
        write_goldens(self.pool, self.registry, "M21", root=root)
        directory = root / "M21"
        oid = self._first_oid()
        (directory / f"{oid}.json").write_text('{"broken": true}', encoding="utf-8")
        (directory / f"{_STALE_NAME}.json").write_text(
            '{"stale": true}', encoding="utf-8"
        )
        diffs = verify_goldens(self.pool, self.registry, "M21", root=root)
        self.assertEqual(len(diffs), 2)
        self.assertIn(f"{oid}: content mismatch", diffs)
        self.assertIn(f"{_STALE_NAME}: stale", diffs)

    def test_verify_detects_single_byte_tamper(self) -> None:
        """PC-4 instrument null test: flip exactly ONE byte in a written
        golden; verify_goldens (the harness's actual measurement path) must
        report at least one diff naming that entry."""
        root = self._fresh_root()
        write_goldens(self.pool, self.registry, "M21", root=root)
        path = root / "M21" / f"{self._first_oid()}.json"
        content = path.read_text(encoding="utf-8")
        flipped = ("[" if content[0] != "[" else "{") + content[1:]
        self.assertNotEqual(flipped, content)
        path.write_text(flipped, encoding="utf-8")
        diffs = verify_goldens(self.pool, self.registry, "M21", root=root)
        self.assertGreaterEqual(len(diffs), 1)
        self.assertIn(f"{self._first_oid()}: content mismatch", diffs)

    def test_committed_baseline_verify_zero_diffs(self) -> None:
        """The harness's actual default path: verify the fresh compile
        against the COMMITTED goldens under the production GOLDEN_ROOT
        (no root override, read-only).  A clean tree with an up-to-date
        baseline must yield exactly 0 diffs — and this test fails on
        real drift, so the harness PASS is meaningful."""
        directory = GOLDEN_ROOT / "M21"
        self.assertTrue(directory.is_dir(), "committed golden baseline missing")
        self.assertEqual(
            len(list(directory.glob("*.json"))),
            PINNED_ENTRIES,
            "committed baseline must cover every pool entry",
        )
        self.assertEqual(
            verify_goldens(self.pool, self.registry, "M21"),
            [],
            "fresh compile must match the committed golden baseline",
        )

    def test_pc9_fingerprint_multiset_deterministic(self) -> None:
        first = fingerprint_multiset(self.pool, self.registry)
        second = fingerprint_multiset(self.pool, self.registry)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 0)
        self.assertEqual(sum(first.values()), PINNED_ENTRIES)


if __name__ == "__main__":
    unittest.main()
