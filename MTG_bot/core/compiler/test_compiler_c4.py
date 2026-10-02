"""C4 compiler campaign — creature cast-lane emission pins (2026-10-02).

Roadmap batch 4: ``compile_card``'s creature branch now ALWAYS assembles a
SpellAbility(CREATURE) — the cast lane that ``legality.cast`` requires
(legality.py ``cast:not_a_spell``). Effect sentences fold into it as before;
a plain creature with no effect sentence gets an effect-less carrier
(``effect=None``, the additional-costs-card precedent). Token creatures stay
excluded — tokens are never cast (``is_token`` branch wins first).

Goldens moved under the audited ADDITIVE-EMISSION form (ratified): 147
creature goldens each gained EXACTLY one appended SpellAbility(CREATURE)
node, keys=[abilities] only, 158 files byte-identical (pre-snapshot
/tmp/golden_pre_c4, audit /tmp/opencode/c4_inventory_audit.py).

Known engine follow-up (NOT a compiler gap, red-as-intended suspect):
FLASH window honoring — spell_window_reason(legality.py:1101) consults only
the SpellKind, never Keyword.FLASH; see
tools/audit/suspects/flash_window_engine_gap.json.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    SpellAbility,
    SpellKind,
    TriggeredAbility,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

_M21_PATH = Path(__file__).resolve().parents[2] / "data" / "M21.json"

_WATCHDOG = "6a0419c3-4bfa-46c1-932b-fe10f2fa2ad7"  # abilities=[] pre-C4, plain
_CORPSE = "fea95888-e16a-4209-9cd4-623f7f4d2f67"  # abilities=[] pre-C4, plain
_HOUNDMASTER = "88939cb3-5f61-4857-95cb-9446c6c1f1aa"  # ETB trigger + bestow
_GOREMAND = "0f80f061-6304-4c7b-ab53-f406385e39df"  # cost-carrier, pre-green
_SPARKHUNTER = "1306c72f-fc6b-470b-a95e-0364e0e30ac7"  # cost-carrier, pre-green
_BLACKGUARD = "8ccd20c7-b7fc-4ab1-a98b-3bbcc2079339"  # FLASH + activated
_ANGEL = "40c64f08-ab2f-4933-8e0e-d1a1c729008f"  # token creature


class CreatureSpellNodeEmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.registry = build_full_registry()

    def compile(self, oid: str):
        return compile_card(self.pool[oid], self.registry).card

    @staticmethod
    def spell_nodes(card) -> list[SpellAbility]:
        return [a for a in card.abilities if isinstance(a, SpellAbility)]

    def test_plain_creature_gets_effectless_carrier(self):
        """Alpine Watchdog: printed Vigilance keyword only, abilities=[]
        pre-C4. Now carries exactly one effect-less SpellAbility(CREATURE)
        as its cast lane — keyword abilities are NOT spell effects."""
        card = self.compile(_WATCHDOG)
        nodes = self.spell_nodes(card)
        self.assertEqual(len(nodes), 1)
        self.assertIs(nodes[0].kind, SpellKind.CREATURE)
        self.assertIsNone(nodes[0].effect)
        self.assertEqual(nodes[-1], card.abilities[-1])  # appended, not injected

    def test_empty_abilities_corpus_creature_gains_exactly_one_node(self):
        """Walking Corpse: compiled with abilities=[] entirely pre-C4.
        Delta = +1 SpellAbility carrier, nothing else."""
        card = self.compile(_CORPSE)
        self.assertEqual(len(card.abilities), 1)
        node = card.abilities[0]
        if not isinstance(node, SpellAbility):  # narrows + falsifies
            self.fail(f"Walking Corpse carrier is {type(node).__name__}")
        self.assertIs(node.kind, SpellKind.CREATURE)

    def test_trigger_bearing_creature_keeps_trigger_and_gains_carrier(self):
        """Alpine Houndmaster: its ETB trigger must stay OUTSIDE the spell
        node (cast effect is none) and stay FIRST — the carrier is appended,
        so trigger-first order (printed sentence order) is falsifiable."""
        card = self.compile(_HOUNDMASTER)
        triggers = [a for a in card.abilities if isinstance(a, TriggeredAbility)]
        self.assertGreaterEqual(len(triggers), 1)
        nodes = self.spell_nodes(card)
        self.assertEqual(len(nodes), 1)
        self.assertIsNone(nodes[0].effect)
        self.assertEqual(card.abilities[-1], nodes[0])

    def test_additional_cost_carrier_not_duplicated(self):
        """Goremand + Sparkhunter Masticore (the two pre-C4 exceptions,
        goldens byte-IDENTICAL across C4): their SpellAbility is the
        additional-costs carrier (effect=None + one Cost). The always-emit
        change must produce THE SAME single node (carrier now assembled in
        the creature branch, the printed additional cost attaches to it) —
        never a second effect-less carrier next to the costed one."""
        for oid in (_GOREMAND, _SPARKHUNTER):
            card = self.compile(oid)
            nodes = self.spell_nodes(card)
            self.assertEqual(len(nodes), 1, card.name)
            self.assertIsNone(nodes[0].effect, card.name)
            self.assertEqual(len(nodes[0].additional_costs), 1, card.name)

    def test_token_creature_gets_no_spell_node(self):
        """Angel is a token: never cast, never gets a cast lane. The C4
        emission must not leak into the token branch."""
        card = self.compile(_ANGEL)
        self.assertTrue(card.is_token)
        self.assertEqual(self.spell_nodes(card), [])

    def test_corpus_every_non_token_creature_has_a_cast_lane(self):
        """The systemic promise: legality.cast's SpellAbility requirement
        is satisfiable for EVERY non-token creature in the pool — and the
        kind is CREATURE (not the SORCERY fallback of the else-branch)."""
        missing, wrong_kind = [], []
        for oid, raw in self.pool.items():
            if raw.is_emblem or raw.is_token or "Creature" not in raw.types:
                continue
            card = self.compile(oid)
            nodes = self.spell_nodes(card)
            if not nodes:
                missing.append(raw.identity.name)
            elif nodes[0].kind is not SpellKind.CREATURE:
                wrong_kind.append(raw.identity.name)
        self.assertEqual(missing, [])
        self.assertEqual(wrong_kind, [])


if __name__ == "__main__":
    unittest.main()
