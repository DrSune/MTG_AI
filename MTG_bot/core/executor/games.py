"""Round-14a: the random-policy full-M21 game harness (the executor's own
systemic verification, and the first real PC-7 measurement).

Why this module exists (plan /02 §14a): unit tests prove atoms, the goldens
prove compilation. Nothing but *playing* proves that casts, triggers, layers,
durations, replacements and the turn skeleton compose without a crash, on
cards no test author picked. PC-7 (``game_turn_survival``) has been the Phase-2
gate since T0 for exactly that reason.

Three moving parts.

**Deck supply** (:func:`compile_supply`, :func:`build_deck`). The compiled
pool is the same path ``tools/measure_grammar.py`` uses (same ingest, same
registry, same 305 goldens verified read-only). Decks are 60-card seeded
random multisets, duplicates up to :data:`MAX_COPIES`, with one honest bias
stated plainly: the first :data:`MIN_MANA_SOURCES` cards are mana sources (the
five M21 basics first, then the fix lands and the 34 ADD_MANA producers),
because a deck that cannot cast anything measures the shuffle and not the
engine. This is a stress test of compiled cards, not a format tournament — the
``all`` pool deliberately keeps the 19 engine-flagged cards, so their loud
raises are data. ``engine`` deals from the 12e gated pass' 286 engine-supported
cards (where a raise is always a bug); ``castable`` narrows to what the
executor can actually put into play (a land, or a card carrying a
``SpellAbility`` node), which is where the deep cross-cutting bugs live.

**The policy** (:class:`RandomPolicy`). It plays through the *query surface*:
:func:`legal_casts` for the land drop and the spells,
:func:`legal_activations` for activations, :func:`spell_target_slots` /
:func:`legal_targets` with :func:`validate_target_selection` for targets, and
:func:`optional_offer` / :func:`choose_options` / :func:`verb_choose_options`
for every decision inside an effect tree. That makes the C15 contract
load-bearing: if a game of random play ever needs a decision the query surface
cannot enumerate, the harness would have to invent one — and it raises instead,
which is the finding. What the policy additionally reads is IR *shape* (to
know how many decisions the tree will ask for, in what order — the runtime
takes one flat positional ``decisions`` tuple) and the pending-trigger queue
(no query exposes "what is about to fire"); both are documented at their sites.

Batch style, no priority simulation: ``begin_turn`` (which now draws, CR 504.5-c
— this harness found that missing) then up to :data:`MAX_ACTS_PER_STEP` acts in
one FIRST_MAIN batch, then ``end_turn``. v1 has no combat, so FIRST_MAIN stands
in for both mains, and a game with no attackers is a legal Magic game (nobody is
obliged to attack), which is why survival is measurable before arc 3 lands.

**Stats + crash ledger** (:func:`run_games`). Per seed: turns survived, whether
the full cap was reached, how the game ended, the act digest, and on a crash the
exception class, the raising frame, the last three cards the policy touched and
the stack contents at the moment of the raise. Every crash becomes a seed-pinned
repro test in ``test_executor_games.py``; ``--repro SEED`` replays one game with
the traceback printed.

Known ceilings the harness deliberately does NOT hide (all in
``KNOWLEDGE/2026-09-30/03``): mana is never emptied between steps (there is no
CR 305.2 rule in the executor, so survival is optimistic), the CR 121.3
draw-from-empty loss is a harness-side state check (13a left it out of the
verbs), and a spell with more than one TARGET selector has no designation
channel, which the policy filters rather than hands the engine a broken cast.

Run it::

    .venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool all
    .venv/bin/python -m MTG_bot.core.executor.games --seeds 1 --pool all --repro 3
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    DelayedTrigger,
    Effect,
    OptionalEffect,
    QConst,
    Quantity,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    Verb,
    Zone,
    ZoneKind,
    walk,
)
from MTG_bot.core.compiler.compiler import PoolCompile, compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor import SUPPORTED_VERBS_V2, Executor, activate
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter, resolve
from MTG_bot.core.executor.query import (
    ActivationOption,
    CastOption,
    TargetSlot,
    choose_options,
    legal_activations,
    legal_casts,
    legal_targets,
    optional_offer,
    spell_target_slots,
    validate_target_selection,
    verb_choose_options,
)
from MTG_bot.core.executor.selectors import role_player
from MTG_bot.core.executor.stack import cast, play_land
from MTG_bot.core.identity import CardIdentity, Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_LIBRARY, GameWorld

REPO = Path(__file__).resolve().parents[3]
SET_CODE = "M21"

# ------------------------------------------------------------------ the rules
DECK_SIZE = 60
OPENING_HAND = 7
TURN_CAP = 60
MAX_COPIES = 4
MIN_MANA_SOURCES = 10
MAX_ACTS_PER_STEP = 10

# Policy weights. Constants, not knobs: a seed must identify ONE policy, or the
# replay pin in test_executor_games.py is meaningless.
TAP_MANA_P = 0.75  # tap a legal mana source
CAST_P = 0.7  # cast a spell the query says is payable
ACTIVATE_P = 0.4  # run a non-mana activation
PASS_P = 0.15  # walk away from the batch (beginner's luck)

# The two CR-fixed decision vocabularies the query surface does NOT enumerate:
# SCRY's per-card placement and ADD_MANA's any-colour pick. They are static
# sets, not state-dependent populations, so mirroring the literal is not an
# engine read — but the mirror is still a contract the harness should not have
# to keep (/03 row B-5).
SCRY_VOCAB = ("top", "bottom")
MANA_COLOR_VOCAB = ("W", "U", "B", "R", "G", "C")
# The fire/skip tail on every trigger stream, for the demand an op's OWN
# queued triggers create mid-drain: see RandomPolicy.trigger_decisions.
TRIGGER_TAIL = 24

_BASICS = ("Plains", "Island", "Swamp", "Mountain", "Forest")


# ----------------------------------------------------------------- pool side
@dataclass(frozen=True)
class CardMeta:
    """Deck-construction view of one compiled card, flattened once per process
    so a 100-seed run compiles the pool exactly once."""

    oracle_id: str
    name: str
    type_line: str
    mana_value: int
    is_land: bool
    produces_mana: bool
    has_spell_node: bool
    engine_supported: bool
    is_basic: bool

    @property
    def mana_capable(self) -> bool:
        """Can add mana to its controller's pool: a land's ``{T}: Add`` or a
        mana rock's compiled ADD_MANA atom."""
        return self.is_land or self.produces_mana

    @property
    def playable(self) -> bool:
        """The executor can put this card into play: a land drop, or a spell
        with a ``SpellAbility`` node. The 14a corpus ceiling is that most
        permanents have no such node (/03 row B-1), so they are uncastable."""
        return self.is_land or self.has_spell_node


@dataclass
class Supply:
    """One compiled pool plus its deck-building view."""

    mode: str
    pool: PoolCompile
    metas: dict[str, CardMeta]
    deckable: tuple[str, ...]
    engine_ids: frozenset[str]
    playable_engine_ids: frozenset[str]
    pool_seconds: float


_SUPPLY_CACHE: dict[str, Supply] = {}


def get_supply(mode: str = "all", set_code: str = SET_CODE) -> Supply:
    """Process-wide compile cache — one 305-card compile per mode per run."""
    supply = _SUPPLY_CACHE.get(f"{mode}:{set_code}")
    if supply is None:
        supply = compile_supply(mode, set_code)
        _SUPPLY_CACHE[f"{mode}:{set_code}"] = supply
    return supply


def compile_supply(mode: str = "all", set_code: str = SET_CODE) -> Supply:
    """Compile the set the way the measurement harness does and build the deck
    view. ``mode`` picks the dealt set:

    * ``all`` — every non-token, non-emblem card (the 19 engine-flagged cards
      included on purpose: flag-not-degrade cuts both ways, and a loud raise
      inside a game is exactly the data this harness exists to collect).
    * ``engine`` — the honest 286 from the 12e gated pass (``supported_verbs=
      SUPPORTED_VERBS_V2``), where a raise is always a bug.
    * ``castable`` — engine-supported AND put-into-playable by the executor.
    """
    if mode not in ("all", "engine", "castable"):
        raise ValueError(f"unknown pool_mode {mode!r} (all|engine|castable)")
    started = time.perf_counter()
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_code}.json")
    registry = build_full_registry()
    pool = compile_pool(raw, registry)
    # The 12e second pass, exactly as tools/measure_grammar.py runs it: the
    # ungated pass stamps every card supported (the template's True default),
    # so the 286 number ONLY exists in the gated fold.
    gated = compile_pool(raw, registry, supported_verbs=set(SUPPORTED_VERBS_V2))
    engine_ids = frozenset(
        oid for oid, res in gated.results.items() if res.legality.engine_supported
    )
    metas: dict[str, CardMeta] = {}
    for oid, res in pool.results.items():
        record = res.card
        if oid in pool.emblems or record.is_token:
            continue  # emblems and tokens are created, never dealt
        verbs = frozenset(node.verb for node in walk(record) if isinstance(node, Atom))
        metas[oid] = CardMeta(
            oracle_id=oid,
            name=record.name,
            type_line=record.type_line,
            mana_value=record.mana_value,
            is_land="Land" in record.type_line,
            produces_mana=Verb.ADD_MANA in verbs,
            has_spell_node=any(
                isinstance(ability, SpellAbility) for ability in record.abilities
            ),
            engine_supported=oid in engine_ids,
            is_basic=record.name in _BASICS,
        )
    playable_engine = frozenset(
        oid for oid, meta in metas.items() if meta.engine_supported and meta.playable
    )
    if mode == "all":
        deckable = tuple(sorted(metas))
    elif mode == "engine":
        deckable = tuple(sorted(oid for oid in engine_ids if oid in metas))
    else:
        deckable = tuple(sorted(playable_engine))
    if not deckable:
        raise ValueError(f"pool_mode {mode!r} has no deckable cards")
    return Supply(
        mode=mode,
        pool=pool,
        metas=metas,
        deckable=deckable,
        engine_ids=engine_ids,
        playable_engine_ids=playable_engine,
        pool_seconds=time.perf_counter() - started,
    )


def identity_of(record: CardRecord) -> CardIdentity:
    """The world-side printed identity of a compiled record. One conversion,
    both directions consistent: :func:`durations.parse_pt` reads printed P/T
    off the identity while the cost fold reads the record, so the two can never
    disagree about the same card (the pitfall this avoids is TYPE_EQ reading a
    type_line the record does not carry)."""
    return CardIdentity(
        oracle_id=record.oracle_id,
        name=record.name,
        type_line=record.type_line,
        set_code=SET_CODE,
        colors=tuple(record.colors),
        cmc=record.mana_value,
        power=_printed_pt(record.power),
        toughness=_printed_pt(record.toughness),
        keywords=tuple(str(item.keyword.name) for item in record.keywords),
    )


def _printed_pt(quantity: Quantity | None) -> str | None:
    """A literal printed P/T as the frozen identity wants it; anything dynamic
    (QProp/QX-class) or absent is ``None``, which is exactly what
    :func:`durations.parse_pt` documents for a non-numeric printing."""
    if isinstance(quantity, QConst):
        return str(quantity.value)
    return None


def build_deck(deck_seed: int, supply: Supply) -> tuple[str, ...]:
    """A seeded 60-card multiset out of ``supply.deckable``.

    Composition, stated honestly (these are stress decks, not tournament
    decks): the first :data:`MIN_MANA_SOURCES` slots are mana sources — the
    five basics in name order, then the remaining mana-capable cards shuffled —
    so every deck can pay for *something*; the rest is a uniform seeded sample
    of the dealt pool; at most :data:`MAX_COPIES` of any card; duplicates are
    otherwise encouraged, because a 60-card deck drawn out of ~300 cards makes
    each game exercise a different slice of the corpus."""
    rng = random.Random(deck_seed)
    metas = supply.metas
    mana = [oid for oid in supply.deckable if metas[oid].mana_capable]
    basics = [oid for oid in mana if metas[oid].is_basic]
    others = [oid for oid in mana if not metas[oid].is_basic]
    rng.shuffle(others)

    copies: dict[str, int] = {}
    deck: list[str] = []

    def take(oid: str) -> None:
        copies[oid] = copies.get(oid, 0) + 1
        deck.append(oid)

    for oid in basics + others:
        if len(deck) >= MIN_MANA_SOURCES:
            break
        if copies.get(oid, 0) < MAX_COPIES:
            take(oid)
    if len(deck) < MIN_MANA_SOURCES:
        # Loud, not a silently dealt 0-mana deck. The 14a pool has 23 lands and
        # 34 ADD_MANA producers, so this only fires on a pool with no mana.
        raise ValueError(
            f"deck {deck_seed}: only {len(deck)} mana-capable cards available, "
            f"need {MIN_MANA_SOURCES} (pool_mode={supply.mode!r})"
        )
    while len(deck) < DECK_SIZE:
        oid = supply.deckable[rng.randrange(len(supply.deckable))]
        if copies.get(oid, 0) < MAX_COPIES:
            take(oid)
    rng.shuffle(deck)
    return tuple(deck)


def shuffled_library(
    executor: Executor, seat: Handle, deck: tuple[str, ...]
) -> tuple[Handle, ...]:
    """Deal ``deck`` into the seat's library, then randomise it with the
    EXECUTOR's own seeded shuffle (the SHUFFLE verb — a journalled atom whose
    randomness comes from ``sha256(master_seed:op_seq:tag)``, so library order
    is a function of the master seed and replays byte-identically). Library
    order is load-bearing for draw, scry and 'reveal the top card', which is
    why it goes through the engine's shuffle and not a harness ``random``."""
    world = executor.world
    for oid in deck:
        world.add_card(
            identity_of(executor.binder.records[oid]), seat, zone=ZONE_LIBRARY
        )
    executor.execute(
        Atom(
            verb=Verb.SHUFFLE,
            args=AtomArgs(pairs=(("zone", Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),)),
        ),
        source=seat,
        controller=seat,
    )
    return tuple(world.players[seat].zone(ZONE_LIBRARY).entries)


# --------------------------------------------------------------- policy side
@dataclass
class Act:
    """One policy act — the unit the crash ledger attributes a crash to."""

    turn: int
    seat: int
    kind: str
    card: str
    detail: str = ""

    def digest(self) -> str:
        return f"{self.kind}:{self.card}" + (f"({self.detail})" if self.detail else "")


class RandomPolicy:
    """Uniform-random play over the query surface, one seeded stream.

    Shuffles, act picks and effect decisions all come from ``rng``, so a seed
    identifies the whole game (the replay pin relies on that); the executor
    keeps its own seeded stream for engine-side randomness (RANDOM selectors,
    coin flips), which the policy never touches.
    """

    def __init__(self, seed: int, max_acts: int = MAX_ACTS_PER_STEP) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.max_acts = max_acts
        self.acts: list[Act] = []
        self.turn = 0
        self.seat_index = 0

    # -- randomness helpers

    def choose(self, items: Any) -> Any:
        return self.rng.choice(list(items))

    def coin(self) -> bool:
        return self.rng.random() < 0.5

    # -- decisions
    def effect_decisions(
        self,
        executor: Executor,
        effect: Effect | None,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Any] | None = None,
        x_value: int | None = None,
    ) -> tuple[str, ...]:
        """The decision stream an effect tree will consume, built by walking
        the tree in the order the runtime walks it.

        Why the walk exists: :meth:`Executor.apply_effect` takes ONE flat
        ``decisions`` tuple and consumes it positionally, so a caller must know
        which decision comes next. The walk mirrors ``_run_effect`` exactly —
        it descends only into the branch that actually runs, because a skipped
        ``OptionalEffect`` consumes nothing downstream of it, and an untaken
        ``Conditional`` branch must not contribute tokens either.

        Every *vocabulary* still comes from the query surface
        (:func:`optional_offer`, :func:`choose_options`,
        :func:`verb_choose_options`); only SCRY and any-colour ADD_MANA use a
        mirrored CR literal (:data:`SCRY_VOCAB`, :data:`MANA_COLOR_VOCAB`). An
        effect node the executor has not implemented raises the SAME
        ``NotImplementedError`` the runtime would raise — the harness mirrors
        the gate, it never pre-empts a crash with a guess.

        Two honest limits, both in /03: a ``Conditional`` predicate that reads
        the binder's trigger-event context (``event_amount``) can evaluate
        differently here, and a decision demanded by a trigger that this op
        *queues* cannot be enumerated before the op starts (only the fire/skip
        tail of :meth:`trigger_decisions` covers it)."""
        if effect is None:  # an effect-less SpellAbility carrier (T3 r3)
            return ()
        out: list[str] = []
        ctx = ctx_for(
            executor,
            source=source,
            controller=controller,
            bindings=bindings,
            x_value=x_value,
        )

        def descend(node: Effect) -> None:
            if isinstance(node, Atom):
                out.extend(self._atom_decisions(executor, node, ctx))
            elif isinstance(node, Seq):
                for step in node.steps:
                    descend(step)
            elif isinstance(node, OptionalEffect):
                offer = optional_offer(
                    executor,
                    node,
                    source=source,
                    controller=controller,
                    bindings=bindings,
                )
                pick = offer[0] if len(offer) == 1 else self.choose(offer)
                out.append(pick)
                if pick == "fire":
                    descend(node.inner)
            elif isinstance(node, Conditional):
                if eval_filter(node.pred, source, ctx):
                    descend(node.then_effect)
                elif node.else_effect is not None:
                    descend(node.else_effect)
            elif isinstance(node, Choose):
                opts = choose_options(
                    executor,
                    node,
                    source=source,
                    controller=controller,
                    bindings=bindings,
                )
                idx = self.rng.randrange(len(opts))
                out.append(str(idx))  # the 12d ORDER contract
                for option_idx in opts[idx].option_idxs:
                    descend(node.options[option_idx])
            elif isinstance(node, DelayedTrigger):
                return  # scheduled into the binder; no decision at schedule time
            else:
                raise NotImplementedError(
                    f"executor: effect {type(node).__name__} not implemented (12e)"
                )

        descend(effect)
        return tuple(out)

    def _atom_decisions(
        self, executor: Executor, atom: Atom, ctx: Any
    ) -> tuple[str, ...]:
        verb = atom.verb
        if verb is Verb.ADD_MANA:
            color = atom.args.get("color")
            if color is None or color == "ANY":
                return (self.choose(MANA_COLOR_VOCAB),)
            return ()
        if verb is Verb.SCRY:
            # One decision per card actually scried, top first (verbs._v_scry);
            # a library shorter than the scry is clamped there, so clamp here.
            player = self._actor(atom, ctx)
            size = len(executor.world.players[player].zone(ZONE_LIBRARY).entries)
            count = atom.args.get("count")
            want = (
                size
                if not isinstance(count, Quantity)
                else min(resolve(count, ctx), size)
            )
            return tuple(self.choose(SCRY_VOCAB) for _ in range(max(want, 0)))
        if verb is Verb.CHOOSE:
            rows = verb_choose_options(
                executor,
                atom,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            return (str(self.rng.randrange(len(rows))),)
        if verb is Verb.CHOOSE_NAME:
            names = sorted(
                {
                    card.identity.name
                    for card in executor.world.cards.values()
                    if not card.identity.is_token
                }
            )
            if not names:  # the handler's own raise shape; keep it loud
                raise ValueError("CHOOSE_NAME has no enumerable candidates")
            return (self.choose(names),)
        return ()

    @staticmethod
    def _actor(atom: Atom, ctx: Any) -> Handle:
        try:
            return role_player(ctx, atom, "controller")
        except NotImplementedError:  # a referent-selector scry: the controller
            return ctx.controller

    def trigger_decisions(self, executor: Executor) -> tuple[str, ...]:
        """The stream for a trigger drain: the pending firings first, in the
        binder's documented ``_pop_next`` order, gated by the trigger condition
        exactly as ``_fire`` gates it; then a random fire/skip tail.

        The tail is the honest answer to a structural hole (/03 row B-4). The
        executor drains triggers *inside* every public op, so an op's own
        queued triggers can demand a decision the policy could not enumerate
        before the op began — and no query surface exposes 'what is about to
        fire'. A may-offer in such a trigger is served by the tail (fire/skip
        are the only tokens always in vocabulary); a SCRY / Choose /
        CHOOSE_NAME demanded mid-drain raises, and that crash is the finding.
        Pending-firing demand is the one part the harness can enumerate: the
        queue is public world state and the choice values still come from the
        query surface."""
        binder = executor.binder
        pending = sorted(
            executor.world.triggers,
            key=lambda instance: (
                instance.controller_seat,
                instance.clock,
                str(instance.source),
                binder.firings[instance.clock].seq
                if instance.clock in binder.firings
                else -1,
            ),
        )
        out: list[str] = []
        for instance in pending:
            payload = binder.firings.get(instance.clock)
            if payload is None:  # pragma: no cover - queue rows carry payloads
                continue
            bindings: dict[str, Any] = {}
            subject = payload.event.subject
            if subject is not None:
                bindings["event"] = subject
                if payload.event.kind == "CREATURE_DIES":
                    bindings["result"] = subject  # C18 was-snapshot, as _ctx does
            ability = payload.node
            if ability.condition is not None:
                gate = ctx_for(
                    executor,
                    source=payload.source,
                    controller=payload.controller,
                    bindings=bindings,
                )
                if not eval_filter(
                    ability.condition,
                    subject if subject is not None else payload.source,
                    gate,
                ):
                    continue
            out.extend(
                self.effect_decisions(
                    executor,
                    ability.effect,
                    source=payload.source,
                    controller=payload.controller,
                    bindings=bindings,
                )
            )
        out.extend("fire" if self.coin() else "skip" for _ in range(TRIGGER_TAIL))
        return tuple(out)

    # -- targets
    def select_targets(self, slots: list[TargetSlot]) -> tuple[Handle, ...] | None:
        """One legal designation for a spell's / ability's TARGET slots: every
        candidate and cardinality from the :class:`TargetSlot` the query
        produced, canonicalised into Handle order and re-validated through the
        query's own oracle before it is handed over. ``None`` = 'this row is not
        designable right now' (an infeasible population), which the caller
        counts and skips."""
        chosen: list[Handle] = []
        for slot in slots:
            if slot.min_count > len(slot.candidates):
                return None
            want = self.rng.randint(slot.min_count, max(slot.min_count, slot.max_count))
            want = min(want, len(slot.candidates))
            picked = sorted(self.rng.sample(list(slot.candidates), want))
            if validate_target_selection(slot, picked) is not None:
                return None
            chosen.extend(picked)
        return tuple(chosen)

    # -- the act surface
    @staticmethod
    def is_mana_activation(option: ActivationOption) -> bool:
        """'Tap it for mana' recognised from the IR of the option the query
        handed over (the very ``ActivatedAbility`` the executor will run), not
        from a card-name table."""
        atoms = [node for node in walk(option.ability.effect) if isinstance(node, Atom)]
        return bool(atoms) and all(
            node.verb in (Verb.ADD_MANA, Verb.TAP) for node in atoms
        )

    def mana_activations(
        self, options: list[ActivationOption]
    ) -> list[ActivationOption]:
        return [option for option in options if self.is_mana_activation(option)]

    def other_activations(
        self, options: list[ActivationOption]
    ) -> list[ActivationOption]:
        mana = {
            (option.source, option.ability_idx)
            for option in self.mana_activations(options)
        }
        return [
            option
            for option in options
            if (option.source, option.ability_idx) not in mana
        ]

    def pick_spell(self, game: Game, rows: list[CastOption]) -> CastOption:
        """Half the time the most expensive payable row, otherwise uniform — a
        policy that always dumped its whole hand would empty it and stop
        exercising the cast path."""

        def cmc(row: CastOption) -> int:
            return game.world.cards[row.handle].identity.cmc or 0

        return max(rows, key=cmc) if self.coin() else self.choose(rows)

    # -- the three acts
    def play_land(self, game: Game, seat: Handle, row: CastOption) -> None:
        name = game.name_of(row.handle)
        game.attempted = f"land:{name}"
        play_land(
            game.executor,
            seat,
            row.handle,
            trigger_decisions=self.trigger_decisions(game.executor),
        )
        self._log(game, "land", name)

    def play_cast(self, game: Game, seat: Handle, row: CastOption) -> None:
        executor = game.executor
        node = row.node
        assert isinstance(node, SpellAbility)  # a non-land legal_casts row has one
        name = game.name_of(row.handle)
        game.attempted = f"cast:{name}"
        slots = spell_target_slots(executor, node, spell_handle=row.handle, seat=seat)
        if len(slots) > 1:
            # v1 has ONE designation tuple per cast, so a multi-slot spell cannot
            # be designated (``stack._validate_spell_targets`` raises
            # NotImplementedError on it). Declining it is a legality decision the
            # policy is entitled to make from the public slot query — and it is
            # counted, so the ceiling is measured instead of hidden (/03 B-3).
            game.multi_target_skips += 1
            game.unsupported_rows.add((row.handle,))
            return
        targets = self.select_targets(slots)
        if targets is None:
            game.infeasible_skips += 1
            return
        if not slots and targets == () and self._names_a_player(node.effect):
            # B-8: a "target opponent" spell (Duress, Cancel, Kitesail
            # Freebooter, Peer into the Abyss) compiles to a
            # ControllerRef.TARGET_PLAYER coordinate with NO Selector, so the slot
            # query correctly answers "no slots" and the policy has nothing to
            # designate — and resolution then raises in players_for_ref because the
            # binding was never made. Designating it is a CR-fixed rule rather than
            # a choice in a 2-player game (an opponent seat of the caster, exactly
            # what ``stack._validate_spell_targets`` re-checks, and that check stays
            # the oracle: a wrong pick still raises). Mirroring a static rule is the
            # same category as :data:`SCRY_VOCAB`; the gap the ledger asks the
            # ENGINE to close is a query that exposes it.
            targets = tuple(
                sorted(other for other in executor.world.player_order if other != seat)
            )
            game.player_target_designations += 1
        decisions = self.effect_decisions(
            executor,
            node.effect,
            source=row.handle,
            controller=seat,
            bindings=self._cast_bindings(targets),
            x_value=None,
        )
        cast(
            executor,
            seat,
            row.handle,
            targets=tuple(targets),
            decisions=decisions,
            trigger_decisions=self.trigger_decisions(executor),
        )
        self._log(game, "cast", name, f"{len(targets)}t")

    def play_activation(
        self, game: Game, seat: Handle, option: ActivationOption
    ) -> None:
        executor = game.executor
        name = game.name_of(option.source)
        game.attempted = f"act:{name}#{option.ability_idx}"
        slots = [
            legal_targets(
                executor.world,
                executor,
                selector,
                source=option.source,
                controller=seat,
            )
            for selector in self._target_selectors(option.ability.effect)
        ]
        if len(slots) > 1:
            game.multi_target_skips += 1
            game.unsupported_rows.add((option.source, option.ability_idx))
            return
        targets = self.select_targets(slots)
        if targets is None:
            game.infeasible_skips += 1
            return
        decisions = self.effect_decisions(
            executor,
            option.ability.effect,
            source=option.source,
            controller=seat,
            # the same mirror for activations (stack.py:497 writes this binding)
            bindings=self._cast_bindings(targets),
        )
        activate(
            executor,
            option.source,
            option.ability_idx,
            seat=seat,
            targets=tuple(targets),
            decisions=decisions,
            trigger_decisions=self.trigger_decisions(executor),
        )
        self._log(game, "act", name, f"#{option.ability_idx}")

    @staticmethod
    def _cast_bindings(targets: tuple[Handle, ...]) -> dict[str, Any] | None:
        """The binding dict the cast is about to install — ``stack.cast`` writes
        ``bindings["target"] = sorted(targets)`` (stack.py:386) before running the
        effect, so a pre-cast enumeration of a target-scoped pool (Duress's
        'You choose a card from it' = Zone(HAND, TARGET_PLAYER)) has to see the
        same thing or it enumerates a different population than the runtime
        will. Mirroring the engine's own write, not inventing one."""
        chosen = sorted(targets)
        return {"target": chosen} if chosen else None

    @staticmethod
    def _names_a_player(effect: Effect | None) -> bool:
        """Does this tree read the TARGET_PLAYER coordinate channel? (Both the
        bare-ControllerRef shape and a Zone whose controller is TARGET_PLAYER.)"""
        if effect is None:
            return False
        for node in walk(effect):
            if not isinstance(node, Atom):
                continue
            for _role, value in node.args.pairs:
                if value is ControllerRef.TARGET_PLAYER:
                    return True
                if (
                    isinstance(value, Zone)
                    and value.controller is ControllerRef.TARGET_PLAYER
                ):
                    return True
        return False

    @staticmethod
    def _target_selectors(effect: Effect | None) -> tuple[Selector, ...]:
        """The TARGET-mode selectors of an ACTIVATED ability — the per-slot
        question :func:`spell_target_slots` asks for a spell, asked here against
        the IR object the ``ActivationOption`` already carries."""
        seen: list[Selector] = []
        if effect is None:  # pragma: no cover - ActivatedAbility.effect is required
            return ()
        for node in walk(effect):
            if not isinstance(node, Atom):
                continue
            for _role, value in node.args.pairs:
                if (
                    isinstance(value, Selector)
                    and value.mode is SelectorMode.TARGET
                    and not any(value == other for other in seen)
                ):
                    seen.append(value)
        return tuple(seen)

    # -- the turn
    def take_acts(self, game: Game, seat: Handle) -> None:
        """One FIRST_MAIN batch: at most :data:`MAX_ACTS_PER_STEP` acts, then
        stop. Land drop first (CR 305.1 allows exactly one, and
        :func:`legal_casts` stops offering it after that), then a weighted roll
        between tapping mana, casting, activating, and walking away.

        The pass is not decoration: a policy that always acts can deadlock on a
        sacrifice-into-a-dies-trigger loop, and MTG's answer is 'you may do
        nothing'. Every candidate set is a query-surface list; only the *choice
        among* legal rows is the policy's."""
        executor = game.executor
        world = executor.world
        self.turn = world.turn
        self.seat_index = world.player_order.index(seat)
        for _ in range(self.max_acts):
            if game.over_reason() is not None:
                return
            rows = legal_casts(world, executor, seat)
            lands = [row for row in rows if row.land]
            spells = [
                row
                for row in rows
                if not row.land and (row.handle,) not in game.unsupported_rows
            ]
            options = [
                option
                for option in legal_activations(world, executor, seat)
                if (option.source, option.ability_idx) not in game.unsupported_rows
            ]
            if lands:
                self.play_land(game, seat, self.choose(lands))
                continue
            if self.rng.random() < PASS_P:
                break
            taps = self.mana_activations(options)
            if taps and self.rng.random() < TAP_MANA_P:
                self.play_activation(game, seat, self.choose(taps))
                continue
            if spells and self.rng.random() < CAST_P:
                self.play_cast(game, seat, self.pick_spell(game, spells))
                continue
            others = self.other_activations(options)
            if others and self.rng.random() < ACTIVATE_P:
                self.play_activation(game, seat, self.choose(others))
                continue
            break
        game.digest.append(f"T{self.turn}.end")

    def _log(self, game: Game, kind: str, card: str, detail: str = "") -> None:
        act = Act(self.turn, self.seat_index, kind, card, detail)
        self.acts.append(act)
        game.acts += 1
        game.digest.append(f"T{self.turn}.{act.digest()}")


# ---------------------------------------------------------------- game runner
@dataclass
class Game:
    """One 2-player game of the compiled corpus: the world, the executor, and
    the counters the report needs."""

    executor: Executor
    seed: int
    pool_mode: str
    digest: list[str] = field(default_factory=list)
    acts: int = 0
    turns: int = 0
    multi_target_skips: int = 0
    infeasible_skips: int = 0
    player_target_designations: int = 0
    empty_library_losers: set[Handle] = field(default_factory=set)
    # Rows the v1 designation channel cannot serve (>1 TARGET selector), learned
    # once and then filtered out of every later query batch. Counted, never
    # silent: ``multi_target_skips`` is a measured coverage ceiling.
    unsupported_rows: set[tuple[object, ...]] = field(default_factory=set)
    reason: str = ""
    # The act in flight when the world raised: the completed-act digest cannot
    # name the card at fault, because the raise usually happens BEFORE the act
    # is logged (during target enumeration, or inside the op itself).
    attempted: str = ""

    @property
    def world(self) -> GameWorld:
        return self.executor.world

    def name_of(self, handle: Handle) -> str:
        card = self.world.cards.get(handle)
        return str(handle) if card is None else card.identity.name

    def note_draw_step(self, seat: Handle) -> None:
        """CR 121.3, harness-side: the draw step just ran (14a's
        :meth:`Executor._turn_draw`), so an EMPTY library now means that player
        lost the game the next time they would draw — which is this moment.
        13a ruled the emptied-library loss a STATE CHECK, not a verb, and no
        state check exists for it yet, so the harness owns it (/03 row B-6)."""
        if not self.world.players[seat].zone(ZONE_LIBRARY).entries:
            self.empty_library_losers.add(seat)

    def over_reason(self) -> str | None:
        """The loss scan: CR 121.3 life total, the LOSE_GAME verb ledger the
        executor keeps, and the harness's CR 121.3 draw-from-empty losers. Two
        losers at once is a draw; one loser means the OTHER player survived."""
        world = self.world
        losers = [seat for seat in world.player_order if self.is_loser(seat)]
        if not losers:
            return None
        names = ", ".join(
            f"{self.name_of(seat)}({self.loss_kind(seat)})" for seat in losers
        )
        return f"{'draw' if len(losers) == 2 else 'game over'}: {names}"

    def is_loser(self, seat: Handle) -> bool:
        world = self.world
        return (
            seat in self.executor.lost_players
            or seat in self.empty_library_losers
            or world.players[seat].life <= 0
        )

    def loss_kind(self, seat: Handle) -> str:
        if self.world.players[seat].life <= 0:
            return "life<=0"
        if seat in self.executor.lost_players:
            return "LOSE_GAME"
        return "draw from empty library (CR 121.3)"


def _setup_game(seed: int, supply: Supply, decks: tuple[tuple[str, ...], ...]) -> Game:
    world = GameWorld(num_players=2, start_life=20, master_seed=seed)
    executor = Executor(world)
    executor.attach_pool(
        supply.pool
    )  # oracle-id bridge: everything later attaches by it
    for seat, deck in zip(world.player_order, decks, strict=True):
        shuffled_library(executor, seat, deck)
        # Pre-game setup (CR 103.4) goes straight through GameWorld.draw: no
        # permanent is on the battlefield to miss a CARD_DRAWN event, and the
        # DRAW verb is a game action the skeleton now owns.
        world.draw(seat, OPENING_HAND)
    return Game(executor=executor, seed=seed, pool_mode=supply.mode)


def coverage_of(game: Game) -> tuple[set[str], set[str]]:
    """``(battlefield names, fired names)`` read out of the JOURNAL, i.e. the
    engine's own record of what happened rather than the policy's opinion.

    ``fired`` = every card that was the cause of at least one journalled
    mutation row — the mission's 'abilities that executed >=1 action'. A purely
    passive static or an anthem never appears in it, which is why coverage sits
    below the pool size and is reported next to the battlefield count, never
    instead of it."""
    world = game.world
    battlefield: set[str] = set()
    fired: set[str] = set()
    for card in world.cards:
        if world.zone_of(card).kind == ZONE_BATTLEFIELD:
            battlefield.add(world.cards[card].identity.name)
    for row in game.executor.journal.dump():
        _clock, kind, _subject, cause, cause_verb, _data = row
        if cause_verb in ("CAST", "PLAY_LAND", "TURN_PHASE", None):
            continue
        if kind == "TURN_PHASE":
            continue
        handle = _handle_from_str(str(cause))
        if handle is not None and handle in world.cards:
            fired.add(world.cards[handle].identity.name)
    return battlefield, fired


def _handle_from_str(text: str) -> Handle | None:
    namespace, _, index = text.partition(":")
    if namespace not in ("card", "emblem"):
        return None
    try:
        return Handle(namespace, int(index))
    except ValueError:  # pragma: no cover - dump() always writes "ns:int"
        return None


@dataclass
class GameOutcome:
    """What one game teaches: survival, cause, coverage, crash evidence."""

    seed: int
    pool_mode: str
    deck_a: str = ""
    deck_b: str = ""
    turns: int = 0
    survived: bool = False
    reason: str = ""
    acts: int = 0
    multi_target_skips: int = 0
    infeasible_skips: int = 0
    player_target_designations: int = 0
    digest: list[str] = field(default_factory=list)
    battlefield_names: set[str] = field(default_factory=set)
    fired_names: set[str] = field(default_factory=set)
    coverage_error: str = ""
    fingerprint: str = ""
    crash: dict[str, Any] | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "pool": self.pool_mode,
            "turns": self.turns,
            "survived": self.survived,
            "reason": self.reason,
            "acts": self.acts,
            "fired": len(self.fired_names),
            "coverage_error": self.coverage_error,
            "fingerprint": self.fingerprint,
            "crash": None
            if self.crash is None
            else {k: self.crash[k] for k in _CRASH_KEYS},
        }


_CRASH_KEYS = (
    "exc",
    "message",
    "frame",
    "turn",
    "attempted",
    "recent_acts",
    "stack",
    "repro",
)


def repro_command(
    seed: int, pool_mode: str, deck_pairs_seed: int, turn_cap: int
) -> str:
    """The recipe a ledger row and every repro test carries: one command, one
    process, the crash with its traceback."""
    return (
        f"python -m MTG_bot.core.executor.games --pool {pool_mode} "
        f"--deck-pairs-seed {deck_pairs_seed} --turns {turn_cap} --repro {seed}"
    )


def play_game(
    seed: int,
    pool_mode: str = "all",
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    supply: Supply | None = None,
    raise_on_crash: bool = False,
) -> GameOutcome:
    """One seeded game.

    A crash is never swallowed: the outcome carries the exception class, the
    raising frame, the turn, the last three acts and the stack contents, and the
    game ends right there — this engine has no rollback, and letting a corrupted
    position keep playing would invent a result. ``raise_on_crash`` re-raises
    instead, which is what ``--repro`` and the repro tests use.
    """
    supply = supply or get_supply(pool_mode)
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    outcome = GameOutcome(
        seed=seed,
        pool_mode=pool_mode,
        deck_a=_deck_label(decks[0], supply),
        deck_b=_deck_label(decks[1], supply),
    )
    policy = RandomPolicy(seed)
    order = game.world.player_order
    repro = repro_command(seed, pool_mode, deck_pairs_seed, turn_cap)
    try:
        _play(game, policy, order, turn_cap)
    except BaseException as error:
        outcome.reason = f"crash:{type(error).__name__}"
        outcome.crash = _describe_crash(game, error, policy, repro)
        _safe_coverage(game, outcome)
        if raise_on_crash:
            raise
    else:
        outcome.reason = game.reason
        _safe_coverage(game, outcome)
    outcome.digest = list(game.digest)
    outcome.acts = game.acts
    outcome.turns = game.turns
    outcome.multi_target_skips = game.multi_target_skips
    outcome.infeasible_skips = game.infeasible_skips
    outcome.player_target_designations = game.player_target_designations
    outcome.survived = game.turns >= turn_cap
    return outcome


def _play(game: Game, policy: RandomPolicy, order: list[Handle], turn_cap: int) -> None:
    """The turn loop. Turn 1 opens with ``begin_turn``; every later turn goes
    through ``advance_turn`` so the CR 500.7 extra-turn queue is popped (and the
    seat is the ENGINE's choice, read back off ``active_player``, not ours)."""
    executor = game.executor
    world = executor.world
    executor.begin_turn(order[0], trigger_decisions=policy.trigger_decisions(executor))
    game.note_draw_step(order[0])
    while True:
        seat = world.active_player
        assert seat is not None  # begin_turn/advance_turn always set it
        policy.take_acts(game, seat)
        game.turns = world.turn
        reason = game.over_reason()
        if reason is not None:
            game.reason = reason
            return
        if game.turns >= turn_cap:
            game.reason = f"turn cap {turn_cap} reached (no loser)"
            return
        executor.end_turn(trigger_decisions=policy.trigger_decisions(executor))
        late = game.over_reason()  # an end-of-turn sweep can be what kills a seat
        if late is not None:
            game.reason = late
            return
        executor.advance_turn(trigger_decisions=policy.trigger_decisions(executor))
        nxt = world.active_player
        assert nxt is not None
        game.note_draw_step(nxt)


def _safe_coverage(game: Game, outcome: GameOutcome) -> None:
    """The post-mortem capture: coverage AND the world fingerprint.

    Best effort by design — a second exception out of a half-finished world
    must never REPLACE the crash as the finding, so a failure here is recorded
    as a coverage note and reported. The fingerprint is taken here (and not in
    the happy path only) because the replay pin cares about it for a CRASHED
    game too: two runs of one seed must agree on the state they died in."""
    try:
        outcome.battlefield_names, outcome.fired_names = coverage_of(game)
        outcome.fingerprint = game.executor.state_fingerprint()
    except Exception as error:  # noqa: BLE001 - recorded, see docstring
        outcome.coverage_error = f"{type(error).__name__}: {error}"


def _describe_crash(
    game: Game, error: BaseException, policy: RandomPolicy, repro: str
) -> dict[str, Any]:
    frames = traceback.extract_tb(error.__traceback__)
    last = frames[-1] if frames else None
    return {
        "exc": type(error).__name__,
        "message": str(error),
        "frame": f"{Path(last.filename).name}:{last.lineno} in {last.name}"
        if last
        else "?",
        "turn": game.turns,
        "recent_acts": [act.digest() for act in policy.acts[-3:]],
        "attempted": game.attempted,
        "stack": [
            game.name_of(frame.handle)
            for frame in game.executor.stack.frames
            if frame.handle in game.world.cards
        ],
        "repro": repro,
    }


def deal_decks(
    seed: int, deck_pairs_seed: int, supply: Supply
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Two decks per game, both derived from the ONE master seed, so the seed
    alone identifies the whole game (reproducibility rule: no second stream)."""
    rng = random.Random(f"decks:{deck_pairs_seed}:{seed}")
    return (
        build_deck(rng.randrange(1 << 40), supply),
        build_deck(rng.randrange(1 << 40), supply),
    )


def _deck_label(deck: tuple[str, ...], supply: Supply) -> str:
    return f"{sum(1 for oid in deck if supply.metas[oid].is_land)}L/{len(set(deck))}U"


# ---------------------------------------------------------------------- stats
def run_games(
    n_seeds: int = 10,
    pool_mode: str = "all",
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    supply: Supply | None = None,
) -> dict[str, Any]:
    """The PC-7 v1 measurement: ``n_seeds`` games on one pool.

    ``survival_pct`` is the share of games that played the full turn cap with no
    loser and no crash. ``coverage_fired`` counts the cards that executed at
    least one mutation across the whole batch, against the dealt pool AND
    against the 286 engine-supported set. ``crashes`` collapses by exception +
    frame, so fifty seeds with one root cause become one ledger row."""
    supply = supply or get_supply(pool_mode)
    outcomes = [
        play_game(seed, pool_mode, deck_pairs_seed, turn_cap, supply=supply)
        for seed in range(n_seeds)
    ]
    return summarise(outcomes, supply, turn_cap)


def summarise(
    outcomes: list[GameOutcome], supply: Supply, turn_cap: int
) -> dict[str, Any]:
    survived = [game for game in outcomes if game.survived]
    crashed = [game for game in outcomes if game.crash is not None]
    turns = [game.turns for game in outcomes]
    fired: set[str] = set()
    battlefield: set[str] = set()
    for game in outcomes:
        fired |= game.fired_names
        battlefield |= game.battlefield_names
    pool_names = {supply.metas[oid].name for oid in supply.deckable}
    engine_names = {
        supply.metas[oid].name for oid in supply.engine_ids if oid in supply.metas
    }

    crashes: dict[str, dict[str, Any]] = {}
    for game in crashed:
        crash = game.crash or {}
        key = f"{crash['exc']}@{crash['frame']}"
        row = crashes.setdefault(
            key,
            {
                "exc": crash["exc"],
                "message": str(crash["message"])[:220],
                "frame": crash["frame"],
                "count": 0,
                "seeds": [],
                "cards": set(),
                "attempted": crash["attempted"],
                "recent_acts": crash["recent_acts"],
                "stack": crash["stack"],
                "repro": crash["repro"],
            },
        )
        row["count"] += 1
        row["seeds"].append(game.seed)
        row["cards"].update(game.digest[-4:])
        if crash["attempted"]:
            row["cards"].add(crash["attempted"])
    for row in crashes.values():
        row["cards"] = sorted(row["cards"])[-8:]

    return {
        "pool_mode": supply.mode,
        "deckable": len(supply.deckable),
        "engine_supported": len(supply.engine_ids),
        "playable_engine": len(supply.playable_engine_ids),
        "n_games": len(outcomes),
        "turn_cap": turn_cap,
        "survived": len(survived),
        "survival_pct": round(100.0 * len(survived) / max(len(outcomes), 1), 1),
        "mean_turns": round(sum(turns) / max(len(turns), 1), 2),
        "max_turns": max(turns) if turns else 0,
        "total_acts": sum(game.acts for game in outcomes),
        "multi_target_skips": sum(game.multi_target_skips for game in outcomes),
        "infeasible_skips": sum(game.infeasible_skips for game in outcomes),
        "player_target_designations": sum(
            game.player_target_designations for game in outcomes
        ),
        "coverage_fired": len(fired),
        "coverage_fired_of_pool_pct": round(
            100.0 * len(fired & pool_names) / max(len(pool_names), 1), 1
        ),
        "coverage_fired_of_engine_pct": round(
            100.0 * len(fired & engine_names) / max(len(engine_names), 1), 1
        ),
        "coverage_battlefield": len(battlefield),
        "fired_of_engine": sorted(fired & engine_names),
        "crash_games": len(crashed),
        "crashes": sorted(crashes.values(), key=lambda row: -row["count"]),
        "reasons": _reason_counts(outcomes),
        "rows": [game.as_row() for game in outcomes],
        "pool_compile_seconds": round(supply.pool_seconds, 2),
    }


def _reason_counts(outcomes: list[GameOutcome]) -> dict[str, int]:
    out: dict[str, int] = {}
    for game in outcomes:
        key = game.reason.split("(")[0].strip() or "unspecified"
        out[key] = out.get(key, 0) + 1
    return out


def _stamp() -> str:
    """The report date, timezone-aware (DTZ011) — same convention as
    ``tools/measure_grammar.py``, so a games report and a grammar report
    written the same day carry the same date string."""
    return datetime.now(UTC).date().isoformat()


def format_table(stats: dict[str, Any]) -> str:
    head = (
        f"pool={stats['pool_mode']}  deckable={stats['deckable']}  "
        f"engine_supported={stats['engine_supported']}  "
        f"playable_engine={stats['playable_engine']}"
    )
    survival = (
        f"games={stats['n_games']}  survived={stats['survived']} "
        f"({stats['survival_pct']}%)  mean_turns={stats['mean_turns']}  "
        f"max_turns={stats['max_turns']}  acts={stats['total_acts']}"
    )
    coverage = (
        f"coverage fired>=1 action: {stats['coverage_fired']} cards  "
        f"({stats['coverage_fired_of_pool_pct']}% of the dealt pool, "
        f"{stats['coverage_fired_of_engine_pct']}% of the "
        f"{stats['engine_supported']} engine-supported)  "
        f"battlefield: {stats['coverage_battlefield']}"
    )
    skips = (
        f"skips: multi-target={stats['multi_target_skips']}  "
        f"infeasible-targets={stats['infeasible_skips']}  "
        f"player-targets={stats['player_target_designations']}"
    )
    lines = [
        head,
        survival,
        coverage,
        skips,
        f"endings: {stats['reasons']}",
        f"crash classes: {len(stats['crashes'])} over {stats['crash_games']} games",
    ]
    for row in stats["crashes"]:
        lines.append(
            f"  [{row['count']}x] {row['exc']} at {row['frame']} seeds={row['seeds'][:8]}"
        )
        lines.append(f"        msg: {row['message'][:150]}")
        lines.append(f"        cards: {', '.join(row['cards'][:6])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Random-policy full-M21 game harness (14a)."
    )
    parser.add_argument("--seeds", type=int, default=10, help="games to play")
    parser.add_argument("--pool", default="all", choices=("all", "engine", "castable"))
    parser.add_argument("--deck-pairs-seed", type=int, default=1409)
    parser.add_argument("--turns", type=int, default=TURN_CAP, help="turn cap")
    parser.add_argument(
        "--repro",
        type=int,
        default=None,
        help="replay one seed and let the crash raise",
    )
    parser.add_argument("--out", default=None, help="report JSON path")
    args = parser.parse_args(argv)

    if args.repro is not None:
        supply = get_supply(args.pool)
        decks = deal_decks(args.repro, args.deck_pairs_seed, supply)
        game = _setup_game(args.repro, supply, decks)
        _play(game, RandomPolicy(args.repro), game.world.player_order, args.turns)
        print(
            f"seed {args.repro}: no crash — {game.turns} turns, {game.reason or 'no loser'}"
        )
        return 0

    started = time.perf_counter()
    stats = run_games(args.seeds, args.pool, args.deck_pairs_seed, args.turns)
    stats["wall_seconds"] = round(time.perf_counter() - started, 2)
    print(format_table(stats))

    out_path = (
        Path(args.out) if args.out else REPO / "reports" / f"games_{_stamp()}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(stats)
    payload["argv"] = list(sys.argv[1:])
    out_path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
