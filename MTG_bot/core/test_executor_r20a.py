"""Round-20a regression tests: the wave-3 keyword/trigger/prevention batch.

Each test pins one r20a root cause and the machinery that fixed it:

1. LIFELINK (anointed_chorister / Blood Glutton / Indulging Patrician):
   the compiler folds the keyword into CardRecord.keywords with NO
   ability row, so the EXECUTOR derives the life gain — both damage
   lanes (player and card) route the dealt amount through the GAIN_LIFE
   verb lane when the source carries LIFELINK through the layer
   registry; a vetoed (prevented) mark gains nothing.
2. PROWESS (jeskai_elder / Mistral Singer): the trigger drain
   constructs the canonical node for every layer-registry HOLDER —
   a noncreature cast pings +1/+1 until EoT, a creature cast is silent,
   cleanup ends the buff.
3. BATTALION (makeshift_battalion): attacking with a group of at least
   three (CR 508.2 gate via the journal's declare group) places one
   +1/+1 counter; attacking alone places none.
4. GRANTED triggers (Infernal Scarring): a TriggeredAbility row parked
   in the layer registry by GRANT_ABILITY drains on its event — the
   dies-granted draw fires.
5. PREVENT_EFFECT damage consumer (Pack Leader): a live
   DamageDealtEvent prevention record vetoes the card-side mark BEFORE
   apply, leaves a DAMAGE_PREVENTED row, and a combat-scoped record
   ignores non-combat damage.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CreatureDiesEvent,
    DamageDealtEvent,
    DurationEot,
    DurationPermanent,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    card_id,
    record_of,
    reset_oracle_ids,
)

CREATURE_F = None  # filters use UNIV / the binding rig's helpers


def atom(verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


class R20aCase(unittest.TestCase):
    """Shared rig: p0/p1, battlefield slots via _bf(), casts via _cast()."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        for color in "WUBRG":
            self.world.players[self.p0].mana_pool[color] = 5

    def _card(
        self,
        name,
        *,
        kw=(),
        p="2",
        t="2",
        type_line="Creature",
        zone=ZONE_BATTLEFIELD,
        seat=None,
        cmc=2,
    ):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line=type_line,
            power=p,
            toughness=t,
            cmc=cmc,
            keywords=kw,
        )
        return self.world.add_card(ident, seat if seat is not None else self.p0, zone)

    def _pt(self, handle):
        card = self.world.cards[handle]
        return self.ex.ledger.effective_pt(card.identity, handle, dict(card.counters))

    def _life(self, seat):
        return self.world.players[seat].life

    def _cast(self, handle, kind=SpellKind.INSTANT):
        # The casting pipeline reads the compiled SpellAbility from the
        # attached record — a hand card without one is an illegal cast.
        ident = self.world.cards[handle].identity
        self.ex.attach_card(
            handle,
            record_of([SpellAbility(kind=kind)], name=ident.name, oid=ident.oracle_id),
        )
        cast(self.ex, self.p0, handle)
        self.ex.fire_triggers()

    def _combat(self, seat, attackers):
        answers = {
            f"attack:{h}": ("ATTACK" if h in attackers else "DECLINE")
            for h in self.world.cards
            if self.world.cards[h].identity.power is not None
        }

        def answer(vocab, what):
            got = next(
                (
                    v
                    for k, v in answers.items()
                    if what == k or what.startswith(k + ":")
                ),
                None,
            )
            if got is None:
                got = "NONE" if what.startswith("block:") else vocab[0]
            return got if got in vocab else vocab[0]

        self.ex.decisions.provider = answer
        try:
            self.ex.combat_step(seat)
        finally:
            self.ex.decisions.provider = None


# ------------------------------------------------------------ 1. lifelink


class LifelinkTest(R20aCase):
    def test_card_lane_gains_life(self):
        src = self._card("Chorister", kw=("LIFELINK",))
        prey = self._card("Prey", seat=self.p1, t="10")
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, amount=QConst(4), target=_bf_sel()),
            source=src,
            controller=self.p0,
            bindings={"target": prey},
        )
        self.assertEqual(self.ex.damage.get(prey), 4)
        self.assertEqual(self._life(self.p0), 24)

    def test_plain_source_gains_nothing(self):
        src = self._card("Plain Ogre")
        prey = self._card("Prey", seat=self.p1, t="10")
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, amount=QConst(4), target=_bf_sel()),
            source=src,
            controller=self.p0,
            bindings={"target": prey},
        )
        self.assertEqual(self.ex.damage.get(prey), 4)
        self.assertEqual(self._life(self.p0), 20)

    def test_player_lane_gains_life(self):
        src = self._card("Glutton", kw=("LIFELINK",))
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, amount=QConst(3), target=_player_sel()),
            source=src,
            controller=self.p0,
            bindings={"target": self.p1},
        )
        self.assertEqual(self._life(self.p1), 17)
        self.assertEqual(self._life(self.p0), 23)

    def test_vetoed_mark_gains_nothing(self):
        # Prevention runs BEFORE lifelink: a prevented mark is no mark.
        src = self._card("Glutton", kw=("LIFELINK",))
        shield = self._card("Ward", kw=("VIGILANCE",))
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(
                Verb.PREVENT_EFFECT,
                condition=FAnd(()),
                event=DamageDealtEvent(amount=_unbounded(), filter=FAnd(())),
                duration=DurationPermanent(),
            ),
            source=shield,
            controller=self.p0,
            bindings={"target": shield},
        )
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, amount=QConst(2), target=_bf_sel()),
            source=src,
            controller=self.p0,
            bindings={"target": shield},
        )
        self.assertNotIn(shield, self.ex.damage)
        self.assertEqual(self._life(self.p0), 20)
        self.assertTrue(any(e[1] == "DAMAGE_PREVENTED" for e in self.ex.events))


def _unbounded():
    from MTG_bot.core.ability_tree import QUnbounded

    return QUnbounded()


def _bf_sel():
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(()),
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _player_sel():
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(()),
        Zone(ZoneKind.PLAYER, ControllerRef.OPPONENT),
    )


# ------------------------------------------------------------- 2. prowess


class ProwessTest(R20aCase):
    def test_noncreature_cast_pings(self):
        elder = self._card("Elder", kw=("PROWESS",))
        spell = self._card("Zap", type_line="Instant", zone=ZONE_HAND)
        self.ex.begin_turn(self.p0)
        self.assertEqual(self._pt(elder), (2, 2))
        self._cast(spell)
        self.assertEqual(self._pt(elder), (3, 3))
        self._cast(
            self._card("Zap2", type_line="Sorcery", zone=ZONE_HAND),
            kind=SpellKind.SORCERY,
        )
        self.assertEqual(self._pt(elder), (4, 4))

    def test_creature_cast_is_silent(self):
        elder = self._card("Elder", kw=("PROWESS",))
        critter = self._card("Antler Back", type_line="Creature", zone=ZONE_HAND)
        self.ex.begin_turn(self.p0)
        self._cast(critter, kind=SpellKind.CREATURE)
        self.assertEqual(self._pt(elder), (2, 2))

    def test_ping_ends_at_cleanup(self):
        elder = self._card("Elder", kw=("PROWESS",))
        spell = self._card("Zap", type_line="Instant", zone=ZONE_HAND)
        self.ex.begin_turn(self.p0)
        self._cast(spell)
        self.assertEqual(self._pt(elder), (3, 3))
        self.ex.end_turn()
        self.assertEqual(self._pt(elder), (2, 2))

    def test_off_battlefield_holder_is_skipped(self):
        # The drain gates on the battlefield: a hand card with the keyword
        # never gains a counter off its owner's own casts.
        elder = self._card("Elder", kw=("PROWESS",), zone=ZONE_HAND)
        spell = self._card("Zap", type_line="Instant", zone=ZONE_HAND)
        self.ex.begin_turn(self.p0)
        self._cast(spell)
        self.assertEqual(dict(self.world.cards[elder].counters), {})


# ----------------------------------------------------------- 3. battalion


class BattalionTest(R20aCase):
    def test_group_of_three_places_counter(self):
        b = self._card("Battalion", kw=("BATTALION",))
        g1 = self._card("Goose One")
        g2 = self._card("Goose Two")
        self.ex.begin_turn(self.p0)
        self._combat(self.p0, {b, g1, g2})
        self.assertEqual(dict(self.world.cards[b].counters), {"PLUS_1_PLUS_1": 1})
        self.assertEqual(self._pt(b), (3, 3))

    def test_attacking_alone_places_none(self):
        b = self._card("Battalion", kw=("BATTALION",))
        self._card("Goose One")
        self.ex.begin_turn(self.p0)
        self._combat(self.p0, {b})  # only the battalion attacker
        self.assertEqual(dict(self.world.cards[b].counters), {})


# ------------------------------------------------- 4. granted triggers


class GrantedTriggerTest(R20aCase):
    def test_granted_dies_trigger_draws(self):
        aura = self._card("Scarring")
        host = self._card("Host")
        self.ex.begin_turn(self.p0)
        # the library opens AFTER begin_turn's own draw, so the granted
        # draw below is the only card that can reach the hand
        lib = self.world.add_card(card_id("Book"), self.p0, ZONE_LIBRARY)
        hand_before = len(self.zone(ZONE_HAND))
        self.ex.execute(
            atom(
                Verb.GRANT_ABILITY,
                target=_bf_sel(),
                ability=TriggeredAbility(
                    CreatureDiesEvent(FAnd(())),
                    None,
                    atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
                ),
                duration=DurationPermanent(),
            ),
            source=aura,
            controller=self.p0,
            bindings={"target": host},
        )
        killer = self._card("Killer", p="4")
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, amount=QConst(4), target=_bf_sel()),
            source=killer,
            controller=self.p0,
            bindings={"target": host},
        )
        self.assertNotIn(host, self.ex.damage)  # dead: the mark rode down
        self.assertEqual(len(self.zone(ZONE_HAND)), hand_before + 1)
        self.assertIn(lib, self.zone(ZONE_HAND))

    def zone(self, kind):
        return self.world.players[self.p0].zone(kind).entries


# ----------------------------------------------------------- 5. prevent


class PreventionConsumerTest(R20aCase):
    def test_record_vetoes_its_targets_mark(self):
        holder = self._card("Leader")
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(
                Verb.PREVENT_EFFECT,
                condition=FAnd(()),
                event=DamageDealtEvent(amount=_unbounded(), filter=FAnd(())),
                duration=DurationEot(),
            ),
            source=holder,
            controller=self.p0,
            bindings={"target": holder},
        )
        attacker = self._card("Raid", seat=self.p1)
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                amount=QConst(2),
                target=_bf_sel(),
            ),
            source=attacker,
            controller=self.p1,
            bindings={"target": holder},
        )
        self.assertNotIn(holder, self.ex.damage)
        self.assertTrue(any(e[1] == "DAMAGE_PREVENTED" for e in self.ex.events))

    def test_other_cards_still_marked(self):
        holder = self._card("Leader")
        victim = self._card("Safari", seat=self.p1, t="10")
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(
                Verb.PREVENT_EFFECT,
                condition=FAnd(()),
                event=DamageDealtEvent(amount=_unbounded(), filter=FAnd(())),
                duration=DurationPermanent(),
            ),
            source=holder,
            controller=self.p0,
            bindings={"target": holder},
        )
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                amount=QConst(2),
                target=_bf_sel(),
            ),
            source=self.p0,
            controller=self.p0,
            bindings={"target": victim},
        )
        self.assertEqual(self.ex.damage.get(victim), 2)
        self.assertNotIn(holder, self.ex.damage)

    def test_combat_scoped_record_ignores_noncombat(self):
        holder = self._card("Leader", t="10")
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(
                Verb.PREVENT_EFFECT,
                condition=FAnd(()),
                event=DamageDealtEvent(
                    amount=_unbounded(), filter=FAnd(()), combat=True
                ),
                duration=DurationPermanent(),
            ),
            source=holder,
            controller=self.p0,
            bindings={"target": holder},
        )
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                amount=QConst(2),
                target=_bf_sel(),
            ),
            source=self.p0,
            controller=self.p0,
            bindings={"target": holder},
        )
        # Non-combat damage is OUTSIDE the record's scope: it marks.
        self.assertEqual(self.ex.damage.get(holder), 2)


if __name__ == "__main__":
    unittest.main()
