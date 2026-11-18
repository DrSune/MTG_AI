"""An attachment stays legal or ends (CR 303.4c, 704.5m, 704.5n): engine wave W1, cause B
(KNOWLEDGE/2026-11-18/215 §5, faults F44 and the rider F32).

* F44: the state-based actions put an Aura into its owner's graveyard when the object it is
  attached to is one its enchant ability no longer allows, read as the Aura's controller sees it
  (CR 704.5m): "Enchant creature you control" once its controller lost control of the creature.
  End to end: the packs of ``aura_stays_on_a_host_its_enchant_no_longer_allows`` (Dub on
  Riddleform once its animation ends; Oakenform on a creature Masterful Replication made a copy of
  a noncreature artifact).
* F32: an Equipment the same check unattaches (704.5n) was still attached as a creature dying in
  that check left (CR 704.3: the actions are simultaneous), so "Whenever equipped creature dies"
  sees it (Malefic Scythe's shape).
"""

from __future__ import annotations

from dataclasses import replace

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CreatureDiesEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    TriggeredAbility,
    Verb,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import CREATURE, BindingCase, gain, record_of
from MTG_bot.core.test_executor_verbs import atom, card_id, target_sel

_YOU = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)


class AnAurasHostMustStayLegal(BindingCase):
    def setUp(self):
        super().setUp()
        identity = replace(card_id("Training", type_line="Enchantment — Aura"), keywords=("ENCHANT",))
        self.aura = self.world.add_card(identity, self.p0, ZONE_BATTLEFIELD)
        enchant = KeywordAbility(keyword=Keyword.ENCHANT, params=(FAnd((CREATURE, _YOU)),))
        record = replace(record_of([], name="Training", oid=identity.oracle_id),
                         type_line="Enchantment — Aura", types=("Enchantment",), subtypes=("Aura",),
                         keywords=(enchant,), power=None, toughness=None)
        self.ex.attach_card(self.aura, record)
        self.ex.attach_aura(self.aura, self.watch)
        self.thief = self.world.add_card(card_id("Thief", "1", "1"), self.p1, ZONE_BATTLEFIELD)

    def _steal(self):
        steal = atom(Verb.GAIN_CONTROL, target=target_sel(), controller=ControllerRef.YOU, duration=DurationEot())
        self.ex.execute(steal, source=self.thief, controller=self.p1, bindings={"target": [self.watch]})

    def test_enchant_creature_you_control_falls_off_a_stolen_creature(self):
        """F44 (Setessan Training with Traitorous Greed): its controller no longer controls the
        creature, so the Aura is attached to an illegal object and goes to the graveyard."""
        self._steal()
        self.assertEqual(self.world.zone_of(self.aura).kind, ZONE_GRAVEYARD)
        self.assertNotIn(self.aura, self.ex.attachments)
        # it was attached to the creature as it left (CR 704.3): its last known information says so
        self.assertEqual(self.ex.departed_lki[self.aura].host, self.watch)

    def test_a_host_it_still_allows_keeps_it(self):
        self.ex.fire_triggers()
        self.assertEqual(self.ex.attachments.get(self.aura), self.watch)


class AnEquipmentUnattachedAsItsCreatureDies(BindingCase):
    def test_equipped_creature_dies_in_the_check_that_unattaches_it(self):
        """F32: the Equipment is itself a creature (704.5n: it can't equip one) and its creature
        has lethal damage: one check kills the creature and unattaches the Equipment, and the
        creature died equipped (CR 704.3, LastKnown.attached)."""
        identity = replace(card_id("Scythe", "1", "1", type_line="Artifact Creature — Equipment"),
                           keywords=("EQUIP",))
        scythe = self.world.add_card(identity, self.p0, ZONE_BATTLEFIELD)
        dies = TriggeredAbility(CreatureDiesEvent(filter=FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE)), None, gain(1))
        self.ex.attach_card(scythe, record_of([dies], name="Scythe", oid=identity.oracle_id))
        self.ex.attach_aura(scythe, self.watch)
        self.ex.mark_damage(self.watch, 2)
        self.ex.fire_triggers()
        self.assertEqual(self.world.zone_of(self.watch).kind, ZONE_GRAVEYARD)
        self.assertNotIn(scythe, self.ex.attachments)
        self.assertEqual(self.life(self.p0), 21)
