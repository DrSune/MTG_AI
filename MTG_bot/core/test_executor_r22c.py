"""The loyalty-activation feed, and three executor readings of given filters.

The journal emits one ABILITY_ACTIVATED row per activation at the payment
point of legality.activate, mana abilities included, carrying the paid
loyalty delta (None for a non-loyalty ability). :class:`TriggerBinder`
matches ``AbilityActivatedEvent`` nodes against it (``kind=LOYALTY`` keys
on the cost): actor over the activating player (the row's cause), source
over the permanent (the row's subject — Keral Keep Disciples' "a Chandra
planeswalker").

The other classes pin what the executor answers for a given filter:

* Shrine census (the sanctum census-X family): ``TYPE_EQ "Shrine"`` counts
  the Shrines; ``NAME_EQ "Shrine"`` is the EXACT card name, so it counts 0.
* Adherent of Hope's condition is evaluated against the single trigger
  subject: True for a Basri planeswalker, False for Adherent itself.
* Chandra's Pyreling: the DAMAGE row carries subject = victim, cause =
  dealer, data = the amount ONLY, so a universal filter also matches damage
  dealt to your OWN creature.
"""

import unittest

from MTG_bot.core.ability_tree import (
    AbilityActivatedEvent,
    AbilityKind,
    ActivatedAbility,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostLoyalty,
    CostTap,
    DamageDealtEvent,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    QCount,
    QUnbounded,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.binding import KIND_ABILITY_ACTIVATED
from MTG_bot.core.executor.events import KIND_DAMAGE
from MTG_bot.core.executor.legality import activate, ctx_for
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
from MTG_bot.core.test_executor_binding import (
    BF_ANY,
    BF_YOU,
    UNIV,
    atom,
    card_id,
    gain,
    record_of,
    reset_oracle_ids,
)


def _oid(seq: int) -> str:
    return f"{seq:08x}-1111-2222-3333-444444444444"


def _pw(name: str, subtype: str, loyalty: int):
    """A Chandra/Basri-shaped planeswalker identity (no power/toughness,
    a loyalty ledger, an em-dash subtype word — the real type-line shape
    the SUBTYPE_EQ lane reads)."""
    return CardIdentity(
        oracle_id=_oid(loyalty + 700),
        name=name,
        type_line=f"Legendary Planeswalker — {subtype}",
        cmc=3,
        loyalty=str(loyalty),
    )


def add_mana_atom(color="R", n=1) -> Atom:
    """A life-neutral activation payload: the tests count LIFE to prove
    the TRIGGER fired, so the ability's own effect must never touch it."""
    return Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("amount", QConst(n)),
                ("color", color),
                ("controller", ControllerRef.YOU),
            )
        ),
    )


class LoyaltyFeedCase(unittest.TestCase):
    """The activation row of a loyalty ability and the Keral-style
    subscription (ABILITY_ACTIVATED rows, AbilityActivatedEvent of kind
    LOYALTY)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=22)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.chandra = self.world.add_card(
            _pw("Cinder Chandra", "Chandra", 3), self.p0, ZONE_BATTLEFIELD
        )
        self.basri = self.world.add_card(
            _pw("Basri Alpha", "Basri", 5), self.p0, ZONE_BATTLEFIELD
        )
        self.herald = self.world.add_card(
            card_id("Herald of the Sanctum"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)
        # Keral Keep Disciples' shape, printed names swapped: "whenever you
        # activate a loyalty ability of a CHANDRA planeswalker, gain 1 life."
        self.ex.attach_card(
            self.herald,
            record_of(
                [
                    TriggeredAbility(
                        event=AbilityActivatedEvent(
                            source=FAtom(FAtomPred.SUBTYPE_EQ, string_value="Chandra"),
                            kind=AbilityKind.LOYALTY,
                            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        ),
                        condition=None,
                        effect=gain(1),
                    )
                ],
                name="Herald",
                oid=self.world.cards[self.herald].identity.oracle_id,
            ),
        )
        plus = ActivatedAbility(
            cost=Cost(parts=(CostLoyalty(1),)), effect=add_mana_atom()
        )
        self.ex.attach_card(self.chandra, record_of([plus], oid=_oid(703)))
        self.ex.attach_card(self.basri, record_of([plus], oid=_oid(705)))

    def loyalty_rows(self):
        """The activation rows of LOYALTY abilities (a paid delta journalled)."""
        return [
            e
            for e in self.ex.journal.events
            if e.kind == KIND_ABILITY_ACTIVATED and e.activation[2] is not None
        ]

    def test_loyalty_symbol_paid_journals_one_row(self):
        activate(self.ex, self.chandra, 0, seat=self.p0)
        rows = self.loyalty_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.subject, self.chandra)  # the permanent
        self.assertEqual(row.cause, self.p0)  # the activating player
        self.assertEqual(row.activation, (0, False, 1))  # idx, not mana (606), paid +1

    def test_chandra_activation_fires_the_keral_trigger(self):
        activate(self.ex, self.chandra, 0, seat=self.p0)
        self.ex.fire_triggers()
        self.assertEqual(self.world.players[self.p0].life, 21)

    def test_basri_activation_journals_but_never_matches_chandra(self):
        # The feed is subtype-agnostic (every paid symbol journalls a row);
        # the negative half lives in the FILTER, exactly like the pack.
        activate(self.ex, self.basri, 0, seat=self.p0)
        self.ex.fire_triggers()
        rows = self.loyalty_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].subject, self.basri)
        self.assertEqual(self.world.players[self.p0].life, 20)

    def test_tap_activation_journals_a_non_loyalty_row(self):
        # ONE row per activation, mana abilities included. CR 606.2: no
        # loyalty symbol in the cost, so the row carries no delta, and the
        # LOYALTY-kind Keral trigger stays silent — the kind keys on the
        # cost, never on the permanent's type.
        spare = self.world.add_card(card_id("Spare"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            spare,
            record_of(
                [
                    ActivatedAbility(
                        cost=Cost(parts=(CostTap(),)), effect=add_mana_atom()
                    )
                ],
                name="Spare",
                oid=self.world.cards[spare].identity.oracle_id,
            ),
        )
        activate(self.ex, spare, 0, seat=self.p0)
        self.assertEqual(self.loyalty_rows(), [])
        rows = [e for e in self.ex.journal.events if e.kind == KIND_ABILITY_ACTIVATED]
        self.assertEqual([(r.subject, r.cause, r.activation) for r in rows], [
            (spare, self.p0, (0, True, None))  # a mana ability (605.1a)
        ])
        self.ex.fire_triggers()
        self.assertEqual(self.world.players[self.p0].life, 20)


class ShrineCensusCase(unittest.TestCase):
    """The Shrine census (the sanctum census-X family): TYPE_EQ counts the
    Shrines; NAME_EQ is the exact card name and counts none."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=23)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        for i in (1, 2):
            self.world.add_card(
                CardIdentity(
                    oracle_id=_oid(800 + i),
                    name=f"Sanctum Test {i}",
                    type_line="Land — Shrine",
                    cmc=1,
                ),
                self.p0,
                ZONE_BATTLEFIELD,
            )
        # A non-Shrine land keeps the census honest about scope, too.
        self.world.add_card(
            CardIdentity(oracle_id=_oid(899), name="Quiet Lake", type_line="Land"),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex = Executor(self.world)

    def census_gain(self, census_filter: FAtom) -> Atom:
        return Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "amount",
                        QCount(
                            Selector(
                                QUnbounded(), SelectorMode.ALL, census_filter, zones=(BF_YOU,)
                            )
                        ),
                    ),
                )
            ),
        )

    def test_type_eq_shrine_census_counts_the_shrines(self):
        # The type-line census the compiler emits (templates_b2a
        # _shrine_count): 2 shrines.
        effect = self.census_gain(FAtom(FAtomPred.TYPE_EQ, string_value="Shrine"))
        self.ex.apply_effect(
            effect, source=next(iter(sorted(self.world.cards))), controller=self.p0
        )
        self.assertEqual(self.world.players[self.p0].life, 22)

    def test_name_eq_shrine_census_is_an_honest_zero(self):
        # NAME_EQ means the EXACT card name (grammar docstring: "cards
        # named Frantic Inventory"). No card is named "Shrine", so 0 is the
        # CORRECT answer.
        effect = self.census_gain(FAtom(FAtomPred.NAME_EQ, string_value="Shrine"))
        self.ex.apply_effect(
            effect, source=next(iter(sorted(self.world.cards))), controller=self.p0
        )
        self.assertEqual(self.world.players[self.p0].life, 20)


class AdherentConditionCase(unittest.TestCase):
    """Adherent of Hope's condition shape is evaluated against the single
    subject it is given, not as a "there is a … you control" quantifier."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=24)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.adherent = self.world.add_card(
            card_id("Adherent of Hope"), self.p0, ZONE_BATTLEFIELD
        )
        self.basri = self.world.add_card(
            _pw("Basri Beta", "Basri", 4), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)
        self.condition = FAnd(
            (
                FAtom(FAtomPred.NAME_CONTAINS, string_value="Basri"),
                FAtom(FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        )

    def test_condition_true_for_a_basri_planeswalker_subject(self):
        ctx = ctx_for(self.ex, source=self.adherent, controller=self.p0)
        self.assertTrue(eval_filter(self.condition, self.basri, ctx))

    def test_condition_false_for_the_adherent_itself(self):
        # The executor answers EXACTLY what the filter asks of the one
        # subject it is given — a 2/2 creature named Adherent of Hope. A
        # "count Basri planeswalkers you control" reading is a different
        # tree (CONTROLLER_COUNT_GE).
        ctx = ctx_for(self.ex, source=self.adherent, controller=self.p0)
        self.assertFalse(eval_filter(self.condition, self.adherent, ctx))


class PyrelingFeedCase(unittest.TestCase):
    """Chandra's Pyreling: the DAMAGE row's destination vocabulary ends at
    the subject; a universal filter matches ANY damage, own creatures
    included."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=25)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.dealer = self.world.add_card(card_id("Dealer"), self.p0, ZONE_BATTLEFIELD)
        self.victim = self.world.add_card(card_id("Victim"), self.p0, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)

    def test_damage_row_shape_has_no_destination_beyond_the_subject(self):
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,)),
                amount=QConst(1),
            ),
            source=self.dealer,
            controller=self.p0,
            bindings={"target": self.victim},
        )
        rows = [e for e in self.ex.journal.events if e.kind == KIND_DAMAGE]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.subject, self.victim)  # the DESTINATION —
        self.assertEqual(row.cause, self.dealer)  # the DEALER, nothing else
        self.assertEqual(row.data, (1,))  # noncombat: amount ONLY

    def test_universal_filter_overmatches_honestly(self):
        # A Pyreling node with filter=FAnd(()) (no "to an opponent"
        # clause) and combat=False: dealing 1 to YOUR OWN creature
        # matches.
        pyre = self.world.add_card(card_id("Ash Pyreling"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            pyre,
            record_of(
                [
                    TriggeredAbility(
                        event=DamageDealtEvent(
                            amount=QUnbounded(),
                            filter=UNIV,
                            source=None,
                            combat=False,
                        ),
                        condition=None,
                        effect=gain(1),
                    )
                ],
                name="Ash Pyreling",
                oid=self.world.cards[pyre].identity.oracle_id,
            ),
        )
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_ANY,)),
                amount=QConst(1),
            ),
            source=self.dealer,
            controller=self.p0,
            bindings={"target": self.victim},
        )
        self.ex.fire_triggers()
        self.assertEqual(self.world.players[self.p0].life, 21)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
