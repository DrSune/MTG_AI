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
:func:`legal_targets` with :func:`validate_target_selection` for targets
(including the 14b synthesized TARGET_PLAYER coordinate slot — the opponent
population the ENGINE's own rule requires, so no CR-rule mirror lives
here anymore). Effect decisions never pre-enumerate anything (14b, B-4
rebuild): the policy registers its seeded uniform choice as the executor's
ask-time :attr:`~MTG_bot.core.executor.decisions.DecisionStream.provider`,
and the engine hands it the exact vocabulary at the exact moment of demand
— the same enumeration the query surface exposes, delivered where it is
needed. That is the C15 contract strengthened, not weakened: the policy's
vocabulary is the engine's own at the ask site, a may-offer arrives
already narrowed by the query oracle (CR 117.3), and a demand with no
answer still raises — which is the finding.

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
    BackFace,
    CardRecord,
    ControllerRef,
    QConst,
    Quantity,
    SpellAbility,
    Verb,
    Zone,
    ZoneKind,
    walk,
)
from MTG_bot.core.compiler.compiler import PoolCompile, compile_pool
from MTG_bot.core.compiler.coverage import (
    ShapeGap,
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.executor import SUPPORTED_VERBS_V2, Executor, activate
from MTG_bot.core.executor.events import KIND_STALL_BREAK
from MTG_bot.core.executor.query import (
    ActivationOption,
    CastOption,
    TargetSlot,
    activation_target_slots,
    legal_activations,
    legal_casts,
    spell_target_slots,
    validate_target_selection,
)
from MTG_bot.core.executor.stack import cast, play_land
from MTG_bot.core.identity import CardIdentity, Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

REPO = Path(__file__).resolve().parents[3]
SET_CODE = "M21"

# ------------------------------------------------------------------ the rules
DECK_SIZE = 60
OPENING_HAND = 7
TURN_CAP = 60
MAX_COPIES = 4
MIN_MANA_SOURCES = 10
MAX_ACTS_PER_STEP = 10

# Stall rule (KNOWLEDGE/2026-10-05/11, anchor CR 104.4b): a game whose
# WORLD FINGERPRINT is unchanged across REPEAT_ROUNDS consecutive rounds
# of the same seat is an unbreakable repeated loop — MTG's ruling for
# that is a DRAW for every player in the loop, and a game that cannot
# end is also what stalls training. We break it early. Pure state
# comparison: no wall-clock, no RNG in the rule, so a seed still
# identifies one game. WHY 3: one repeat proves nothing (a full
# untap/draw/end-turn cycle returns MOST quiet worlds to a similar
# state); two consecutive zero-progress round trips is the minimum
# evidence that the loop is self-sustaining, and the third identical
# observation costs the harness nothing (the fingerprint is O(bf size +
# zone sizes) per turn). A threshold of 2 false-fires on
# draw-absorbing shuffles; 3 is the smallest honest number, and the
# corpus scan (100 seeds, pool=all) shows ZERO legit games tripping it.
REPEAT_ROUNDS = 3

# Policy weights. Constants, not knobs: a seed must identify ONE policy, or the
# replay pin in test_executor_games.py is meaningless.
TAP_MANA_P = 0.75  # tap a legal mana source
CAST_P = 0.7  # cast a spell the query says is payable
ACTIVATE_P = 0.4  # run a non-mana activation
PASS_P = 0.15  # walk away from the batch (beginner's luck)

# The 14b rebuild deleted the two mirrored CR vocabularies (SCRY top/bottom,
# ADD_MANA any-colour) and the fire/skip trigger tail: the decision channel
# now hands the policy the exact vocabulary at the ask (/03 rows B-4/B-5).

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
    #: /99: pool entries whose PRINTED SHAPE raises ``StateCorruptionError``
    #: (the strict compile has no tolerance). Census-consistent ``ShapeGap``
    #: rows — the same ledger the coverage report writes — so an excluded
    #: card is REGISTERED here, never silent. Empty for every clean pool
    #: (all of M21; ZNR carries exactly one: Nighthawk Scavenger, P/T "1+*",
    #: whose power is defined by a card-type census the current quantity
    #: grammar cannot express — see KNOWLEDGE/2026-10-18/99).
    shape_gaps: tuple[ShapeGap, ...] = ()


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
    * ``compiled`` — castable AND fully compiled: no unparsed sentence, no
      ambiguity, no unparsed back face. The other modes deal partly compiled
      cards with their unparsed text silently missing (B-28, against
      DESIGN_CARD_POOL.md:219); this one plays only cards whose whole text is in
      the tree. It equals ``castable`` on M21; it is how a new set (M20, KHM)
      is played honestly while its grammar rounds run (KNOWLEDGE /159).
    """
    if mode not in ("all", "engine", "castable", "compiled"):
        raise ValueError(f"unknown pool_mode {mode!r} (all|engine|castable|compiled)")
    started = time.perf_counter()
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_code}.json")
    registry = build_full_registry()
    # /99 (KNOWLEDGE/2026-10-18/99): a card whose PRINTED SHAPE the compiler
    # honestly refuses (StateCorruptionError — today the whole ZNR supply
    # hangs on exactly one: Nighthawk Scavenger, power "1+*", defined as
    # "1 plus the number of card types among cards in your opponents'
    # graveyards" — a derived census quantity the frozen Quantity grammar
    # has no atom for; implementing it is a grammar round, NOT a parse
    # kludge that would silently misstate the card). The strict compile
    # stays strict — a raise inside a game is still always a bug — but the
    # SUPPLY excludes the refusing shape and registers it as census-
    # consistent ShapeGap rows (the coverage-report ledger, never a silent
    # drop). M21 has zero shape gaps: the fast path below runs unchanged
    # and its supply stays byte-identical.
    shape_gaps: tuple[ShapeGap, ...] = ()
    try:
        pool = compile_pool(raw, registry)
    except StateCorruptionError:
        _tolerated, gap_rows = _compile_pool_tolerant(raw, registry)
        dropped = {gap.card for gap in gap_rows}
        raw = {oid: rc for oid, rc in raw.items() if oid not in dropped}
        pool = compile_pool(raw, registry)
        shape_gaps = tuple(gap_rows)
        for gap in gap_rows:
            print(
                f"supply[{set_code}]: shape-gap exclusion {gap.name!r}: {gap.error}",
                file=sys.stderr,
            )
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
        # ZND-2f §3 (phantom defense, /106 amendment 3): the BackFace
        # subtree is EXCLUDED — an UNPLAYABLE face's {T}: Add {B} must
        # never set produces_mana for the card (gold:false-shaped phantom
        # mana). The face-playability wave (owner-gated) revisits this.
        verbs = frozenset(
            node.verb for node in walk(record, skip=BackFace) if isinstance(node, Atom)
        )
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
    elif mode == "compiled":
        deckable = tuple(
            sorted(
                oid
                for oid in playable_engine
                if not (
                    pool.results[oid].unparsed
                    or pool.results[oid].ambiguities
                    or pool.results[oid].back_face_unparsed
                )
            )
        )
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
        shape_gaps=shape_gaps,
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
        # r19a (Chandra, Heart of Fire): the compiled record carries the
        # printed starting loyalty, but this conversion silently DROPPED it,
        # so binder._register's loyalty seed (which reads identity.loyalty)
        # never ran and every cast planeswalker entered with an empty
        # counters map. One field, one path — the seed itself is unchanged.
        loyalty=str(record.loyalty) if record.loyalty is not None else None,
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

    # -- decisions (14b, B-4 rebuild)
    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        """The ask-time decision provider registered on the executor's
        :class:`DecisionStream` (the B-4 ruling's zero-prediction lane).

        The engine hands the EXACT vocabulary at the exact demand site —
        may-offers arrive already narrowed by the query oracle (CR 117.3,
        ``query.optional_offer`` is the ask vocabulary now), scry arrives
        ``('top','bottom')``, any-colour mana arrives the colour vocab —
        so the policy draws uniformly from the enumeration it is GIVEN
        and mirrors no vocabulary of its own (the four 14a mirrors are
        deleted: /03 row B-5 closed). A non-member answer would raise in
        the stream; exhaustion raises too (C15: no default, the tripwire
        stands). Determinism: this consumes only ``self.rng``, and the
        engine asks in a deterministic order, so one seed still identifies
        the whole decision history (the replay pin relies on that)."""
        return self.rng.choice(list(vocab))

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
        play_land(game.executor, seat, row.handle)
        self._log(game, "land", name)
        if game.trace is not None:
            game.trace.record_action(seat, "land-drop", name, row.handle, ())

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
        # B-8/B-5 CLOSED 14b: "target opponent" now rides the SYNTHESIZED
        # coordinate slot of the query (engine CR population), so the
        # opponent-seat mirror and the _names_a_player IR probe are gone —
        # the designation above came from the slot like any other.
        if any(slot.synthetic for slot in slots):
            game.player_target_designations += 1
        cast(
            executor,
            seat,
            row.handle,
            kicked=row.kicked,
            targets=tuple(targets),
        )
        self._log(game, "cast", name, f"{len(targets)}t")
        if game.trace is not None:
            game.trace.record_action(
                seat, "cast", name, row.handle, tuple(targets), f"{len(targets)}t"
            )

    def play_activation(
        self, game: Game, seat: Handle, option: ActivationOption
    ) -> None:
        executor = game.executor
        name = game.name_of(option.source)
        game.attempted = f"act:{name}#{option.ability_idx}"
        # r23a (Liliana's Steward): the activation twin of the spell lane's
        # slot question — TARGET-mode Selectors AND the synthesized
        # TARGET_PLAYER coordinate the old Selector-only walk was blind to.
        slots = list(
            activation_target_slots(
                executor,
                option.ability.effect,
                source=option.source,
                seat=seat,
            )
        )
        if len(slots) > 1:
            game.multi_target_skips += 1
            game.unsupported_rows.add((option.source, option.ability_idx))
            return
        targets = self.select_targets(slots)
        if targets is None:
            game.infeasible_skips += 1
            return
        activate(
            executor,
            option.source,
            option.ability_idx,
            seat=seat,
            targets=tuple(targets),
        )
        self._log(game, "act", name, f"#{option.ability_idx}")
        if game.trace is not None:
            game.trace.record_action(
                seat,
                "activate",
                name,
                option.source,
                tuple(targets),
                f"#{option.ability_idx}",
            )

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
        if game.trace is not None:
            game.trace.record_turn(seat)
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


# ------------------------------------------------------------------- tracing
def _card_view(world: GameWorld, handle: Handle) -> dict[str, Any]:
    """The viewer-facing view of one card instance: identity + the per-
    instance vector (tapped, counters) + printed P/T. Serialization ONLY —
    no engine reads this, so it can never move a replay."""
    card = world.cards[handle]
    ident = card.identity
    pt = None
    if ident.power is not None or ident.toughness is not None:
        pt = f"{ident.power or '*'}/{ident.toughness or '*'}"
    return {
        "handle": str(handle),
        "name": ident.name,
        "oracle_id": ident.oracle_id,
        "type_line": ident.type_line,
        "tapped": bool(card.tapped),
        "pt": pt,
        "counters": dict(card.counters),
    }


def world_snapshot(executor: Executor) -> dict[str, Any]:
    """The full-state snapshot folded into every action entry.

    THE SAME DUMPS the :meth:`Executor.state_fingerprint` hashes, written
    out as JSON instead of into a sha256: per-player zones (hand REVEALED —
    this is an audit tool), battlefield views, life, the stack frames
    bottom→top, and the replayed-state ledgers. Full snapshots land only
    on action entries, which bounds a 60-turn game file at well under the
    5 MB budget.
    """
    world = executor.world
    players: list[dict[str, Any]] = []
    for seat in world.player_order:
        player = world.players[seat]
        bf = [_card_view(world, h) for h in player.zone(ZONE_BATTLEFIELD).entries]
        hand = [_card_view(world, h) for h in player.zone(ZONE_HAND).entries]
        players.append(
            {
                "seat": player.seat,
                "handle": str(seat),
                "name": player.name,
                "life": player.life,
                "mana": {str(k): v for k, v in player.mana_pool.items()},
                "battlefield": bf,
                "hand": hand,
                "library": len(player.zone(ZONE_LIBRARY).entries),
                "graveyard": [
                    c["name"]
                    for c in (
                        _card_view(world, h) for h in player.zone("graveyard").entries
                    )
                ],
                "exile": [
                    c["name"]
                    for c in (
                        _card_view(world, h) for h in player.zone("exile").entries
                    )
                ],
                "command": len(player.zone("command").entries),
            }
        )
    stack = [
        {
            "handle": str(f.handle),
            "name": world.cards[f.handle].identity.name
            if f.handle in world.cards
            else str(f.handle),
            "controller": str(f.controller),
            "kind": f.spell_kind,
            "x": f.x_value,
            "targets": [game_name(world, h) for h in f.declared_targets],
            "modes": list(f.mode_choices),
        }
        for f in executor.stack.frames
    ]
    return {
        "turn": world.turn,
        "phase": executor.phase,
        "active": str(world.active_player) if world.active_player else None,
        "players": players,
        "stack": stack,
        "ledger": [repr(row) for row in executor.ledger.dump()],
        "stack_dump": [repr(row) for row in executor.stack.dump()],
        "land_plays": {str(seat): list(v) for seat, v in executor.land_ledger.items()},
    }


def game_name(world: GameWorld, handle: object) -> str:
    """Human-readable name for a handle string or Handle (viewer labels)."""
    if isinstance(handle, str) and ":" in handle:
        namespace, _, index = handle.partition(":")
        if namespace == "card":
            try:
                parsed = Handle("card", int(index))
            except ValueError:  # pragma: no cover - dump() writes ns:int
                return handle
            card = world.cards.get(parsed)
            if card is not None:
                return f"{card.identity.name} ({handle})"
    return str(handle)


class TraceRecorder:
    """Ordered per-game trace export for the replay viewer (additive only:
    every hook is a list append on a completed action — no engine read is
    reordered and no rng stream is touched, so the fingerprint of a traced
    game equals the fingerprint of the untraced one).

    Entries merge, in order: (a) policy action starts, (b) decision asks
    captured at the ask-time provider (with the EXACT vocabulary the engine
    asked with — the candidate list), (c) journal event rows, plus a full
    state snapshot after every action.
    """

    def __init__(
        self,
        supply: Supply,
        decks: tuple[tuple[str, ...], ...],
        turn_cap: int,
    ) -> None:
        self.supply = supply
        self.decks = decks
        self.turn_cap = turn_cap
        self.game: Game | None = None
        self.entries: list[dict[str, Any]] = []
        self.libraries: dict[str, list[dict[str, str]]] = {}
        self._pending: list[dict[str, Any]] = []
        self._journal_pos = 0
        self._ask_pos = 0

    # -- installation ----------------------------------------------------
    def attach(self, game: Game) -> None:
        self.game = game
        self._journal_pos = len(game.executor.journal.dump())
        self._ask_pos = len(game.executor.decisions.ask_log)

    def wrap(self, answer: Any) -> Any:
        """Provider-lane recorder: logs (vocab, what, answer) at the ask.

        Pool/FIFO-lane asks never reach a provider; they are caught by the
        ask_log diff in :meth:`_decision_lanes_check` instead (none occur
        on this harness's path, but the count check makes that measured,
        not assumed)."""

        def provider(vocab: tuple[str, ...], what: str) -> str:
            out = answer(vocab, what)
            self._pending.append(
                {
                    "type": "decision",
                    "vocab": list(vocab),
                    "what": what,
                    "candidates": list(vocab),
                    "answer": out,
                }
            )
            return out

        return provider

    # -- capture sites ----------------------------------------------------
    def note_library(self, world: GameWorld, seat: Handle) -> None:
        """Library order at game start, per seat (post-shuffle, pre-draw)."""
        self.libraries[str(seat)] = [
            {
                "handle": str(h),
                "name": world.cards[h].identity.name,
                "oracle_id": world.cards[h].identity.oracle_id,
            }
            for h in world.players[seat].zone(ZONE_LIBRARY).entries
        ]

    def record_turn(self, seat: Handle) -> None:
        assert self.game is not None
        world = self.game.world
        self.entries.append(
            {
                "type": "turn",
                "turn": world.turn,
                "seat": world.player_order.index(seat),
                "phase": self.game.executor.phase,
            }
        )

    def record_action(
        self,
        actor: Handle,
        kind: str,
        card: str,
        handle: Handle,
        targets: tuple[Handle, ...],
        detail: str = "",
    ) -> None:
        assert self.game is not None
        game = self.game
        world = game.world
        ident = world.cards[handle].identity if handle in world.cards else None
        self.entries.append(
            {
                "type": "action",
                "turn": world.turn,
                "phase": game.executor.phase,
                "seat": world.player_order.index(actor),
                "kind": kind,
                "card": card,
                "handle": str(handle),
                "oracle_id": ident.oracle_id if ident else None,
                "targets": [str(t) for t in targets],
                "target_names": [game_name(world, t) for t in targets],
                "detail": detail,
            }
        )
        self._drain_lanes()
        entry = self.entries[-1]
        entry["snapshot"] = world_snapshot(game.executor)

    # -- between-entry merge ----------------------------------------------
    def _drain_lanes(self) -> None:
        assert self.game is not None
        game = self.game
        world = game.world
        self.entries.extend(self._pending)
        self._pending = []
        rows = game.executor.journal.dump()
        for clock, kind, subject, cause, verb, data in rows[self._journal_pos :]:
            self.entries.append(
                {
                    "type": "event",
                    "clock": clock,
                    "kind": kind,
                    "subject": game_name(world, subject),
                    "cause": game_name(world, cause),
                    "verb": verb,
                    "data": data,
                }
            )
        self._journal_pos = len(rows)
        self._ask_pos = len(game.executor.decisions.ask_log)

    def finalise(self, outcome: GameOutcome) -> dict[str, Any]:
        """Flush trailing lanes and assemble the whole game document."""
        assert self.game is not None
        game = self.game
        self._drain_lanes()
        decklists = []
        for i, deck in enumerate(self.decks):
            counts: dict[str, int] = {}
            for oid in deck:
                counts[oid] = counts.get(oid, 0) + 1
            decklists.append(
                {
                    "player": i,
                    "cards": [
                        {
                            "name": self.supply.metas[oid].name,
                            "oracle_id": oid,
                            "count": n,
                        }
                        for oid, n in sorted(
                            counts.items(), key=lambda kv: self.supply.metas[kv[0]].name
                        )
                    ],
                }
            )
        return {
            "seed": game.seed,
            "pool": game.pool_mode,
            "turn_cap": self.turn_cap,
            "determinism": "fully seeded: deck deal, shuffle (engine verb), "
            "policy rng and the ask-time decision provider all derive from "
            "this one seed — replaying the seed replays every decision",
            "decklists": decklists,
            "libraries": self.libraries,
            "outcome": {
                "reason": outcome.reason,
                "survived": outcome.survived,
                "turns": outcome.turns,
                "acts": outcome.acts,
                "fingerprint": outcome.fingerprint,
            },
            "final_snapshot": world_snapshot(game.executor),
            "entries": self.entries,
        }


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
    # 16b: seats whose life crossed 0 DURING a COMBAT phase (combat
    # deaths, reported separately from executor crashes - the meaning of
    # a "survived" game shifted the moment games could die by fighting).
    combat_losses: int = 0
    # The act in flight when the world raised: the completed-act digest cannot
    # name the card at fault, because the raise usually happens BEFORE the act
    # is logged (during target enumeration, or inside the op itself).
    attempted: str = ""
    # 14g: optional trace recorder (export-only; None keeps every historical
    # game byte-identical — the hooks below are guarded on this field).
    trace: TraceRecorder | None = None
    # Stall rule (2026-10-05/11): seat -> (that seat's previous turn-top
    # world fingerprint, identical-observation streak so far). A round trip
    # with ANY net change anywhere resets the streak to 1.
    stall_seen: dict[Handle, tuple[tuple, int]] = field(default_factory=dict)
    # Search substrate (KNOWLEDGE/2026-10-10/67): a fork resumed with
    # ``_play(..., resumed=True)`` at a boundary INSIDE an open turn sets one
    # of these so the loop re-enters at exactly the stop point — PRE_COMBAT
    # (acts played) skips one take_acts call, POST_COMBAT (combat done) skips
    # one combat_step call. Defaults False keep every historical game
    # byte-identical.
    skip_next_acts: bool = False
    skip_next_combat: bool = False

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


def _setup_game(
    seed: int,
    supply: Supply,
    decks: tuple[tuple[str, ...], ...],
    trace: TraceRecorder | None = None,
) -> Game:
    world = GameWorld(num_players=2, start_life=20, master_seed=seed)
    executor = Executor(world)
    executor.attach_pool(
        supply.pool
    )  # oracle-id bridge: everything later attaches by it
    for seat, deck in zip(world.player_order, decks, strict=True):
        shuffled_library(executor, seat, deck)
        if trace is not None:
            trace.note_library(world, seat)  # pre-draw order, engine shuffle
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
    combat_losses: int = 0  # 16b: life-crossed-0 during a COMBAT phase
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
            "combat_losses": self.combat_losses,
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
    trace_path: Path | str | None = None,
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
    # 14g trace: created BEFORE setup so it can note the pre-draw library
    # order; attach() right after so journal/ask baselines start at zero.
    recorder = TraceRecorder(supply, decks, turn_cap) if trace_path else None
    game = _setup_game(seed, supply, decks, trace=recorder)
    if recorder is not None:
        recorder.attach(game)
        game.trace = recorder
    outcome = GameOutcome(
        seed=seed,
        pool_mode=pool_mode,
        deck_a=_deck_label(decks[0], supply),
        deck_b=_deck_label(decks[1], supply),
    )
    policy = RandomPolicy(seed)
    if recorder is not None:
        # _play registers ``policy.answer`` as the ask-time provider;
        # masking the instance attribute with the recorder's wrapper lets
        # the trace capture (vocab, what, answer) at every ask WITHOUT
        # changing what answer() does (the wrapper is transparent).
        policy.answer = recorder.wrap(policy.answer)
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
    outcome.combat_losses = game.combat_losses
    outcome.survived = game.turns >= turn_cap
    if recorder is not None:
        path = Path(trace_path)  # type: ignore[arg-type]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(recorder.finalise(outcome), default=str), encoding="utf-8"
        )
    return outcome


def _stall_fingerprint(executor: Executor) -> tuple:
    """The STALL detector's world fingerprint (stall rule, 2026-10-05/11).

    Deliberately NARROWER and cheaper than :meth:`Executor.state_fingerprint`
    (which replays every atom): this is a PROGRESS probe, not a replay
    digest. Per seat, in ``player_order``: life total; the battlefield
    multiset with each permanent's (oracle id, tapped, counters, printed
    P/T); the hand / library / graveyard SIZES; plus the global "stack
    empty" bit. SIZES, not contents, on purpose: a card that shuffles
    itself back to the library rewrites the library ORDER every cycle
    (engine shuffle consumes the seeded stream) while the game makes zero
    progress — pinning the order would let exactly the loop this rule
    exists for defeat the comparison. The observation point is fixed (top
    of the acting seat's turn, post-untap/post-draw, pre-act), so
    legitimate churn — life totals, counters, taps that survive the
    owner's next untap step, graveyard growth — always moves at least one
    component. Honest limitation, documented: fingerprint repetition by
    itself is the trigger; we do NOT separately verify that the same
    ACTIONS recurs (a state-identity loop with different recurring
    actions is still a zero-progress loop by the CR 104.4b spirit, and a
    full round trip of identical world state IS the observable content of
    "the same actions recurs")."""
    world = executor.world
    seats = []
    for seat in world.player_order:
        player = world.players[seat]
        battlefield = []
        for handle in player.zone(ZONE_BATTLEFIELD).entries:
            card = world.cards[handle]
            ident = card.identity
            battlefield.append(
                (
                    ident.oracle_id,
                    bool(card.tapped),
                    tuple(sorted(card.counters.items())),
                    (ident.power, ident.toughness),
                )
            )
        seats.append(
            (
                player.life,
                tuple(sorted(battlefield)),
                len(player.zone(ZONE_HAND).entries),
                len(player.zone(ZONE_LIBRARY).entries),
                len(player.zone(ZONE_GRAVEYARD).entries),
            )
        )
    return (tuple(seats), len(executor.stack.frames) == 0)


def _play(
    game: Game,
    policy: RandomPolicy,
    order: list[Handle],
    turn_cap: int,
    resumed: bool = False,
    stop_after: Any = None,
) -> None:
    """The turn loop. Turn 1 opens with ``begin_turn``; every later turn goes
    through ``advance_turn`` so the CR 500.7 extra-turn queue is popped (and the
    seat is the ENGINE's choice, read back off ``active_player``, not ours).

    Search substrate (KNOWLEDGE/2026-10-10/67, purely additive: every default
    keeps historical games byte-identical): ``resumed=True`` starts the loop on
    an ALREADY-OPEN turn (a fork taken at a turn-top boundary, i.e. after the
    acting seat's ``begin_turn``/draw step, before its acts);
    ``stop_after(game, boundary)`` is consulted at the CLEAN boundaries — the
    three points where no executor call is in flight: ``"turn_top"`` (a seat's
    turn has just opened, pre-stall-check, pre-acts), ``"pre_combat"`` (that
    seat's acts are done, its combat has not started) and ``"post_combat"``
    (its combat ended, still its turn). Returning True returns from the loop
    right there with the position consistent.

    The stall rule (KNOWLEDGE/2026-10-05/11) rides at the top of every turn:
    one :func:`_stall_fingerprint` per turn, compared against the SAME
    seat's previous turn-top observation (a per-seat streak = comparison
    one FULL round later, when that seat acts again — the only fixed
    phase point both players' churn is inside). :data:`REPEAT_ROUNDS`
    identical consecutive per-seat observations end the game as a STALL
    draw, CR 104.4b's practical generalisation."""
    executor = game.executor
    world = executor.world
    # 14b (B-4): the policy IS the executor's decision answerer — the
    # engine asks with the exact vocabulary at every demand site. The
    # registration lives HERE so every driver (play_game and --repro)
    # gets it.
    executor.decisions.provider = policy.answer
    if not resumed:
        executor.begin_turn(order[0])
        game.note_draw_step(order[0])
    while True:
        seat = world.active_player
        assert seat is not None  # begin_turn/advance_turn always set it
        # The synthetic first iteration of an IN-TURN resume (skip flags set)
        # is the re-entered boundary itself, never a fresh turn top: neither
        # the turn_top stop nor the stall bookkeeping double-fires there.
        resuming = game.skip_next_acts or game.skip_next_combat
        if not resuming and stop_after is not None and stop_after(game, "turn_top"):
            return
        if game.skip_next_acts:
            game.skip_next_acts = False  # a PRE_COMBAT resume skips one act pass
        else:
            # --- stall rule: per-seat round fingerprint streak (CR 104.4b) ---
            fingerprint = _stall_fingerprint(executor)
            previous, streak = game.stall_seen.get(seat, (None, 0))
            streak = streak + 1 if fingerprint == previous else 1
            game.stall_seen[seat] = (fingerprint, streak)
            if streak >= REPEAT_ROUNDS:
                game.turns = world.turn
                executor.journal.emit(
                    KIND_STALL_BREAK, None, seat, "STALL", (REPEAT_ROUNDS,)
                )
                game.reason = (
                    f"STALL (CR 104.4b repeated-loop draw: world fingerprint "
                    f"unchanged for {REPEAT_ROUNDS} consecutive rounds)"
                )
                return
            policy.take_acts(game, seat)
        if game.skip_next_combat:
            game.skip_next_combat = False  # a POST_COMBAT resume skips one phase
        elif executor.turn_open:
            if stop_after is not None and stop_after(game, "pre_combat"):
                return
            # 16b: the COMBAT phase rides between the main phase and the
            # end step - guarded on turn_open because an END_TURN atom
            # played during take_acts already closed the turn (no combat
            # after the end of the turn, CR). The life deltas across the
            # phase are counted separately (combat deaths vs crashes is
            # the semantic shift the engine numbers report).
            before = {s: world.players[s].life for s in world.player_order}
            executor.combat_step(seat)
            for s, life in before.items():
                if life > 0 and world.players[s].life <= 0:
                    game.combat_losses += 1
            if stop_after is not None and stop_after(game, "post_combat"):
                return
        game.skip_next_combat = False  # turn was closed before any combat skip
        game.turns = world.turn
        reason = game.over_reason()
        if reason is not None:
            game.reason = reason
            return
        if game.turns >= turn_cap:
            game.reason = f"turn cap {turn_cap} reached (no loser)"
            return
        executor.end_turn()
        late = game.over_reason()  # an end-of-turn sweep can be what kills a seat
        if late is not None:
            game.reason = late
            return
        executor.advance_turn()
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
    trace_dir: Path | str | None = None,
) -> dict[str, Any]:
    """The PC-7 v1 measurement: ``n_seeds`` games on one pool.

    ``survival_pct`` is the share of games that played the full turn cap with no
    loser and no crash. ``coverage_fired`` counts the cards that executed at
    least one mutation across the whole batch, against the dealt pool AND
    against the 286 engine-supported set. ``crashes`` collapses by exception +
    frame, so fifty seeds with one root cause become one ledger row."""
    supply = supply or get_supply(pool_mode)
    trace_root = Path(trace_dir) if trace_dir else None
    if trace_root is not None:
        trace_root.mkdir(parents=True, exist_ok=True)
    outcomes = [
        play_game(
            seed,
            pool_mode,
            deck_pairs_seed,
            turn_cap,
            supply=supply,
            trace_path=None
            if trace_root is None
            else trace_root / f"game_{pool_mode}_s{seed}.json",
        )
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
        # 16b: combat deaths counted SEPARATELY from crashes - a game
        # ending early because a seat was FIGHTED to 0 is a semantics
        # outcome, not an engine defect.
        "combat_losses": sum(game.combat_losses for game in outcomes),
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
        (
            f"combat: deaths-by-combat-damage={stats['combat_losses']} "
            "(reported apart from crashes)"
        ),
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
    parser.add_argument(
        "--trace",
        default=None,
        metavar="DIR",
        help="write a per-game replay trace JSON (game_<pool>_s<seed>.json) "
        "into DIR — full snapshots after every action, for the viewer",
    )
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
    stats = run_games(
        args.seeds,
        args.pool,
        args.deck_pairs_seed,
        args.turns,
        trace_dir=args.trace,
    )
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
