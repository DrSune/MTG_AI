"""No phantom asks: a decision site whose offer surface has one word does not ask.

A single option the bounds force is CONSUMED, never presented as a decision
(the rule ``stack._plan_cast_designation`` follows for forced
auto-designation, CR 601.2c). Every decision generator (the runtime Choose
lane, the may lane + its query-narrowed optional_offer sites) goes through
the shared primitive ``executor.offers.offer_or_autopick``:

1. a Choose clamped to ONE option set from a multi-option menu asks
   nothing — the option runs silently, the consumption rides the stream's
   journal (not ask_log), and the resulting state is IDENTICAL to the
   world that answered the (phantom) ask;
2. a may-offer the query narrowed to ("skip",) auto-skips: the provider is
   NEVER called (no degenerate training row is even capturable), ask_log
   stays clean;
3. two may-offers on ONE source carry DISTINCT site tags (the site
   digest) and per-(vocab, what) FIFO primings pair to their OWN sites;
4. multi-candidate surfaces STILL ask (no over-autopick);
5. an EMPTY offer surface raises explicitly (the zero-candidate edge is a
   site-contract error);
6. MAY_DONE reads an auto-consumed offer from the journal (the
   "you may pay {2}. If you do" rider with an empty pool answers FALSE,
   it does not re-ask and does not go loud).
"""

import unittest

from MTG_bot.core.ability_tree import (
    Choose,
    Conditional,
    Cost,
    CostManaGeneric,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Seq,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.offers import offer_or_autopick
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import (
    BF_YOU,
    atom,
    card_id,
    enter,
    etb_trigger,
    gain,
    record_of,
    reset_oracle_ids,
)

PAY_2 = atom(Verb.PAY, cost=Cost(parts=(CostManaGeneric(QConst(2)),)))


class PhantomCase(unittest.TestCase):
    """p0: Alpha (2/2) on the battlefield, 4-card library; p1 plain."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=41)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        for i in (1, 2, 3, 4):
            self.world.add_card(card_id(f"L{i}"), self.p0)
        self.ex = Executor(self.world)

    def life(self):
        return self.world.players[self.p0].life

    def spy(self):
        """Install a recording provider; returns the list of (vocab, what)."""
        asked: list[tuple[tuple[str, ...], str]] = []

        def provider(vocab, what):
            asked.append((tuple(vocab), what))
            return vocab[0]

        self.ex.decisions.provider = provider
        return asked


class TestChooseClampIsSilent(PhantomCase):
    def test_clamped_choose_never_asks_and_state_matches_answering(self):
        # Choose + QConst(2) over a TWO-option menu: the bounds clamp
        # (min=max=2 over |options|=2) leaves exactly ONE legal option set,
        # so the vocab is ("0",) — a phantom ask. The primitive consumes it.
        asked = self.spy()
        self.ex.apply_effect(
            Choose(QConst(2), (gain(1), gain(2))),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(asked, [], "single-option choose still asked")
        self.assertEqual(self.ex.decisions.ask_log, [], "phantom polluted ask_log")
        self.assertEqual(self.life(), 23)
        # journal shows the silent consume under the choose site tag.
        self.assertEqual(len(self.ex.decisions.journal), 1)
        what, answer = self.ex.decisions.journal[0]
        self.assertTrue(what.startswith(f"choose:{self.alpha}:"))
        self.assertEqual(answer, "0")

    def test_phantom_eats_no_supply_and_state_matches_answering(self):
        # The forced choose consults NO supply lane (provider untouched,
        # pool word stays parked), so it cannot eat the pool word scripted
        # for the may site: the may site still gets its scripted "fire" —
        # and the world matches the world that had answered the phantom by
        # hand (both consume option-set "0" = gain 1 AND gain 2 = +3).
        asked: list[tuple[tuple[str, ...], str]] = []

        def provider(vocab, what):
            asked.append((tuple(vocab), what))
            return vocab[0]

        self.ex.decisions.provider = provider
        self.ex.apply_effect(
            Seq(steps=(Choose(QConst(2), (gain(1), gain(2))), OptionalEffect(gain(5)))),
            source=self.alpha,
            controller=self.p0,
            decisions=("fire",),
        )
        self.assertEqual(self.life(), 20 + 3 + 5)
        self.assertEqual(asked, [], "forced surface consulted the provider")
        self.assertEqual(
            [(w.split(":")[0], a) for w, a in self.ex.decisions.ask_log],
            [("may", "fire")],
        )


class TestNarrowedMayOffer(PhantomCase):
    def test_skip_only_offer_autoskips_without_an_ask(self):
        # "You may pay {2}" with an empty pool: optional_offer narrows to
        # ("skip",) (CR 117.3). Billing that as a decision is a phantom
        # ask — the provider must never even SEE it.
        asked = self.spy()
        self.ex.apply_effect(
            OptionalEffect(inner=PAY_2), source=self.alpha, controller=self.p0
        )
        self.assertEqual(asked, [], "narrowed may-offer was billed as a decision")
        self.assertEqual(self.ex.decisions.ask_log, [])
        self.assertEqual(
            self.ex.decisions.journal, [(may_tag(self.alpha, PAY_2), "skip")]
        )

    def test_may_done_reads_the_silent_skip(self):
        # The rider shape ("you may pay {2}. If you do, gain 5") with no
        # mana: the offer auto-skips and MAY_DONE answers FALSE from the
        # journal — no re-ask, no loud "unanswered question".
        asked = self.spy()
        self.ex.apply_effect(
            Seq(
                steps=(
                    OptionalEffect(inner=PAY_2),
                    Conditional(FAtom(FAtomPred.MAY_DONE), gain(5)),
                )
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(asked, [])
        self.assertEqual(self.life(), 20, "gated tail must not run")


class TestTwoMayOffersOneSource(PhantomCase):
    """Minimal 2-trigger scenario: one carrier card whose TWO ETB triggers
    each hold a may-offer. The per-site digest tag separates them (under a
    bare ``may:<source>`` tag FIFO primings would mispair)."""

    def setUp(self):
        super().setUp()
        self.recipient = self.world.add_card(
            card_id("Recipient", "1", "1"), self.p0, ZONE_HAND
        )
        a, b = OptionalEffect(gain(2)), OptionalEffect(gain(1))
        rec = record_of(
            [etb_trigger(a), etb_trigger(b)],
            name="Twin",
            oid=self.world.cards[self.recipient].identity.oracle_id,
        )
        self.ex.attach_card(self.recipient, rec)
        self.tag_a = f"may:{self.recipient}:{site_digest(a)}"
        self.tag_b = f"may:{self.recipient}:{site_digest(b)}"

    def _enter_and_life(self):
        self.ex.execute(
            enter(BF_YOU),
            source=self.recipient,
            controller=self.p0,
            bindings={"cards": [self.recipient]},
        )
        return self.life()

    def test_tags_are_distinct(self):
        self.assertNotEqual(self.tag_a, self.tag_b)

    def test_primings_pair_to_their_own_sites(self):
        self.ex.decisions.push(("fire", "skip"), self.tag_a, "fire")
        self.ex.decisions.push(("fire", "skip"), self.tag_b, "skip")
        self.assertEqual(self._enter_and_life(), 22, "A-primed fire must run A")

    def test_swapped_priming_pairs_the_other_way(self):
        self.ex.decisions.push(("fire", "skip"), self.tag_a, "skip")
        self.ex.decisions.push(("fire", "skip"), self.tag_b, "fire")
        self.assertEqual(self._enter_and_life(), 21, "B-primed fire must run B")

    def test_both_asks_reach_ask_log_under_their_own_tags(self):
        self.ex.decisions.push(("fire", "skip"), self.tag_a, "fire")
        self.ex.decisions.push(("fire", "skip"), self.tag_b, "fire")
        self._enter_and_life()
        whats = [w for w, _ in self.ex.decisions.ask_log if w.startswith("may:")]
        self.assertEqual(sorted(whats), sorted([self.tag_a, self.tag_b]))


class TestMultiCandidateStillAsks(PhantomCase):
    def test_two_option_choose_still_asks(self):
        from MTG_bot.core.ability_tree import Choose

        asked = self.spy()
        self.ex.apply_effect(
            Choose(QConst(1), (gain(1), gain(2))),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(len(asked), 1, "over-autopick: a real decision vanished")
        self.assertEqual(asked[0][0], ("0", "1"))

    def test_full_may_vocab_still_asks(self):
        asked = self.spy()
        self.ex.apply_effect(
            OptionalEffect(inner=gain(2)), source=self.alpha, controller=self.p0
        )
        self.assertEqual(len(asked), 1, "over-autopick: fire/skip was silenced")
        self.assertEqual(asked[0][0], ("fire", "skip"))


class _StubCtx:
    """Minimal demand-site stand-in for the primitive's own contract."""

    stream = None

    def __init__(self):
        self.seen: list[tuple[tuple[str, ...], str]] = []

    def take_decision(self, vocab, what):
        self.seen.append((tuple(vocab), what))
        return vocab[0]


class TestEmptyOfferSurface(unittest.TestCase):
    def test_zero_candidate_raises_explicitly(self):
        ctx = _StubCtx()
        with self.assertRaises(ValueError) as cm:
            offer_or_autopick(ctx, (), "choose:src:x")
        self.assertIn("EMPTY offer surface", str(cm.exception))
        self.assertEqual(ctx.seen, [], "empty vocab must never reach take_decision")


def may_tag(source, inner) -> str:
    """The site tag contract: may:<source>:<digest of the OptionalEffect>."""
    return f"may:{source}:{site_digest(OptionalEffect(inner))}"


if __name__ == "__main__":
    unittest.main()
