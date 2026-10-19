"""r25 — grammar round 11 executor lanes (batch 6, 2026-10-02).

Two engine faces for the ratified additive members (ruling:
KNOWLEDGE/2026-10-02/10-grammar-round-ruling.md):

* R11-1 ``FAtomPred.OPPONENT_OF`` (quantity._eval_atom +
  binding._player_subject_verdict): the DESTINATION predicate for
  "deals noncombat damage to an opponent" (Chandra's Pyreling /
  Chandra's Incinerator). Player-total — a player outside ``who``'s
  side passes, a player on it never does, and a CARD subject never
  passes at all (CR 109.5). CONTROLLER_IS would be the WRONG carrier:
  over a card subject it reads the card's controller, firing Pyreling
  on damage to an opponent's creature — the negative pinned below and
  in the promoted ``chandras_pyreling_opponent_filter`` pack.
* R11-2 ``CREATE_TOKEN`` optional ``controller`` role (verbs.
  _v_create_token): the anaphoric creator — "ITS CONTROLLER creates
  a … token" (Secure the Scene / Angelic Ascension s2). Resolves
  through the same role_players lane LOSE_LIFE uses for the referent
  reads; a resolution naming zero or several players raises, never
  guesses. WITHOUT the role the verb mints at ctx.controller — the
  whole pre-round-11 corpus, pinned as the regression face.
"""

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DamageDealtEvent,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.quantity import _eval_atom
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import (
    UNIV,
    BindingCase,
    atom,
    card_id,
    gain,
)

UNIV_PLAYER = Zone(ZoneKind.PLAYER, ControllerRef.ANY)


def opponent_of(who: ControllerRef | Selector = ControllerRef.YOU) -> FAtom:
    return FAtom(pred=FAtomPred.OPPONENT_OF, who=who)


def referent_target_selector() -> Selector:
    """The compiler's R11-2 emission shape (b5b anaphora template)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(()),
        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
        referent="target",
    )


SOLDIER = TokenSpec(
    name="Soldier",
    type_line="Token — Creature — Soldier",
    types=("Creature",),
    subtypes=("Soldier",),
    power=QConst(1),
    toughness=QConst(1),
    keywords=(),
    abilities=(),
)


class R25Case(BindingCase):
    """BindingCase plus a p1-controlled creature (the negative witness)."""

    def setUp(self):
        super().setUp()
        self.thug = self.world.add_card(
            card_id("Thug", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )

    def ctx(self, controller=None, bindings=None):
        return self.ex._ctx(
            source=self.watch,
            controller=controller if controller is not None else self.p0,
            bindings=bindings or {},
            decisions=(),
        )

    def tokens_of(self, player):
        return [
            h
            for h in self.world.players[player].zone(ZONE_BATTLEFIELD).entries
            if self.world.cards[h].identity.is_token
        ]


class TestOpponentOfEval(R25Case):
    def test_opponent_player_passes(self):
        self.assertTrue(_eval_atom(opponent_of(), self.p1, self.ctx()))

    def test_own_player_fails(self):
        self.assertFalse(_eval_atom(opponent_of(), self.p0, self.ctx()))

    def test_card_subject_never_passes(self):
        # CR 109.5: "damage to an opponent" is damage to a PLAYER. Even
        # the opponent-controlled card fails — this is exactly what
        # CONTROLLER_IS would have wrongly let through.
        self.assertFalse(_eval_atom(opponent_of(), self.thug, self.ctx()))

    def test_referent_who_folds_card_binding_to_its_controller(self):
        # who = referent-target Selector bound to p1's Thug: p0 (not on
        # that side) passes, p1 (that controller) fails.
        ctx = self.ctx(bindings={"target": self.thug})
        self.assertTrue(
            _eval_atom(opponent_of(referent_target_selector()), self.p0, ctx)
        )
        self.assertFalse(
            _eval_atom(opponent_of(referent_target_selector()), self.p1, ctx)
        )


class TestOpponentOfTrigger(R25Case):
    """Pyreling-shape trigger: noncombat damage events with the
    destination filter match ONLY damage dealt to an opponent player."""

    def setUp(self):
        super().setUp()
        self.attach_trigger(
            self.watch,
            DamageDealtEvent(QConst(2), opponent_of(), source=UNIV, combat=False),
            gain(1),
        )

    def _damage(self, subject):
        # The target zone follows the subject sort — a PLAYER-zone TARGET
        # selector refuses a card binding and re-resolves to a player
        # (that re-resolution, not the engine, was the r25 harness bug).
        zone = (
            UNIV_PLAYER
            if subject in (self.p0, self.p1)
            else Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
        )
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(zone,)),
                amount=QConst(2),
            ),
            source=self.watch,
            controller=self.p0,
            bindings={"target": subject},
        )

    def test_damage_to_opponent_player_fires(self):
        self._damage(self.p1)
        self.assertEqual(self.life(self.p0), 21)  # 20 + gain, dmg hit p1

    def test_damage_to_self_does_not_fire(self):
        self._damage(self.p0)
        # The hit lands (20 -> 18); a firing trigger would read 19.
        self.assertEqual(self.life(self.p0), 18)

    def test_damage_to_opponents_creature_does_not_fire(self):
        # The promoted-pack signature: p0's watch deals 2 to p1's Thug —
        # at the pre-R11 vacuous FAnd(()) the trigger fired (+1 life,
        # life stays 20 here with a dead Thug). The destination
        # predicate kills it: the damage is never "to an opponent".
        self._damage(self.thug)
        self.assertEqual(self.life(self.p0), 20)
        self.assertEqual(self.world.zone_of(self.thug).kind, ZONE_GRAVEYARD)


class TestCreateTokenControllerRole(R25Case):
    def test_mints_under_the_referents_controller_not_the_executor(self):
        # Secure-the-Scene shape: p0 casts (ctx.controller = p0), the
        # antecedent is p1's creature -> p1 creates the Soldier.
        self.ex.execute(
            atom(
                Verb.CREATE_TOKEN,
                tokens=SOLDIER,
                count=QConst(1),
                controller=referent_target_selector(),
            ),
            source=self.watch,
            controller=self.p0,
            bindings={"target": self.thug},
        )
        self.assertEqual(len(self.tokens_of(self.p1)), 1)
        self.assertEqual(self.tokens_of(self.p0), [])

    def test_no_role_still_mints_at_ctx_controller(self):
        # Regression face of "optional": every pre-round-11 emission
        # (all 27 CREATE_TOKEN corpus rows) is untouched.
        self.ex.execute(
            atom(Verb.CREATE_TOKEN, tokens=SOLDIER, count=QConst(1)),
            source=self.watch,
            controller=self.p0,
        )
        self.assertEqual(len(self.tokens_of(self.p0)), 1)
        self.assertEqual(self.tokens_of(self.p1), [])

    def test_unbound_referent_raises(self):
        # Zero antecedents is flagged, never guessed — the unbound
        # referent lane answers before the verb's own arity guard.
        with self.assertRaisesRegex(ValueError, "no target binding"):
            self.ex.execute(
                atom(
                    Verb.CREATE_TOKEN,
                    tokens=SOLDIER,
                    count=QConst(1),
                    controller=referent_target_selector(),
                ),
                source=self.watch,
                controller=self.p0,
            )

    def test_multi_player_resolution_raises(self):
        # The printed clause has exactly ONE antecedent; a role that
        # resolves to several players (here: both seats) is flagged.
        with self.assertRaisesRegex(ValueError, "need exactly 1"):
            self.ex.execute(
                atom(
                    Verb.CREATE_TOKEN,
                    tokens=SOLDIER,
                    count=QConst(1),
                    controller=ControllerRef.ANY,
                ),
                source=self.watch,
                controller=self.p0,
            )


if __name__ == "__main__":
    unittest.main()
