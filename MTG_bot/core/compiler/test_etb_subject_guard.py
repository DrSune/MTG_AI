"""Corpus guard: no ETB-trigger subject is ever ``None``.

A ``ZoneChangeEvent`` whose ``to_zone`` is the battlefield fires on ANY
object entering when ``subject`` is ``None``, which is wrong for every real
trigger: it is anchored either on its own permanent (``FAtom(IS_SOURCE)``)
or on a described class (``FAnd(TYPE_EQ/CONTROLLER_IS/...)``, Garruk's
Uprising). The test pins the whole compiled M21 pool.
"""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from MTG_bot.core import ability_tree as T
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

_M21 = Path(__file__).resolve().parents[2] / "data" / "M21.json"


def _iter_etb_violations(obj: object) -> list[T.ZoneChangeEvent]:
    """Return every TriggeredAbility ETB ZoneChangeEvent with subject None."""
    violations: list[T.ZoneChangeEvent] = []

    def walk(node: object) -> None:
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            if isinstance(node, T.TriggeredAbility):
                ev = node.event
                if (
                    isinstance(ev, T.ZoneChangeEvent)
                    and ev.to_zone.kind is T.ZoneKind.BATTLEFIELD
                    and (ev.from_zone is None or ev.from_zone.kind is T.ZoneKind.ANY)
                    and ev.subject is None
                ):
                    violations.append(ev)
            for field in dataclasses.fields(node):
                walk(getattr(node, field.name))
        elif isinstance(node, (list, tuple, set, frozenset)):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(obj)
    return violations


class TestEtbSubjectGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21)
        cls.compiled = compile_pool(cls.pool, build_full_registry())

    def test_no_etb_trigger_has_subject_none(self) -> None:
        offenders: list[str] = []
        for oid, result in self.compiled.results.items():
            found = _iter_etb_violations(result.card)
            if found:
                offenders.append(
                    f"{self.pool[oid].identity.name} ({oid}): "
                    f"{len(found)} ETB trigger(s) with subject=None"
                )
        self.assertEqual(
            offenders,
            [],
            f"ETB-trigger subject=None regression (audit 09-29/04 P0-2): {offenders}",
        )

    def test_detector_flags_synthetic_none_subject(self) -> None:
        # The walker detects the bad shape (the guard is not vacuous).
        bad = T.TriggeredAbility(
            event=T.ZoneChangeEvent(
                from_zone=T.Zone(T.ZoneKind.ANY, T.ControllerRef.ANY),
                to_zone=T.Zone(T.ZoneKind.BATTLEFIELD, T.ControllerRef.YOU),
            ),
            condition=None,
            effect=T.Atom(verb=T.Verb.LOSE_GAME, args=T.AtomArgs()),
        )
        good = T.TriggeredAbility(
            event=T.ZoneChangeEvent(
                from_zone=T.Zone(T.ZoneKind.ANY, T.ControllerRef.ANY),
                to_zone=T.Zone(T.ZoneKind.BATTLEFIELD, T.ControllerRef.YOU),
                subject=T.FAtom(pred=T.FAtomPred.IS_SOURCE),
            ),
            condition=None,
            effect=T.Atom(verb=T.Verb.LOSE_GAME, args=T.AtomArgs()),
        )
        self.assertEqual(len(_iter_etb_violations(bad)), 1)
        self.assertEqual(_iter_etb_violations(good), [])


if __name__ == "__main__":
    unittest.main()
