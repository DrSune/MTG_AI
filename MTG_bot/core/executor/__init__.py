"""The core state-visible executor (rounds 12a–12d, plan /06 §12a–§12d).

``Executor(world)`` runs compiled ability IR against the Phase-0
:class:`~MTG_bot.core.state.GameWorld`: :meth:`Executor.execute` for one
Atom, :meth:`Executor.apply_effect` for an Effect tree (Seq /
OptionalEffect / Conditional — the decision-bearing nodes; Choose consumes
its decision at runtime from 12d (index into ``query.choose_options``'
ORDER contract — see that docstring); EachPlayer runs per-player
sub-executions with the CONTROLLER rotated (14f; the templates compile the
inner effect YOU-relative); Repeat remains not-implemented and RAISES at
dispatch; DelayedTrigger SCHEDULES into the
12b binder, C22). 12b adds the living-ability half:

  * :meth:`Executor.attach_card` / :meth:`Executor.attach_pool` — compiled
    records bind to world Handles (oracle-id bridge, identity checked);
    leaving the battlefield detaches, re-entering re-registers;
  * an :class:`~MTG_bot.core.executor.events.EventJournal` — every Atom
    boundary diffs the world and emits the structured events triggers
    subscribe to (zone moves, C18 dies snapshots, draws, counters, taps,
    damage, life, turn phases);
  * :meth:`Executor.fire_triggers` / the auto-drain at the end of every
    public op — matched triggers resolve through the world's APNAP
    ``order_key``, in Handle-tie-broken order, until the queue empties
    (``MAX_TRIGGER_FIRES`` tripwire: a self-retriggering source is
    QUARANTINED and flagged in ``trigger_loops``, never run).
    12c adds the decision half: :mod:`executor.legality` (activation
    legality, the CR-checked cost fold, ``pay_costs`` through the
    journalled verbs, the folded ``activate`` move) and
    :mod:`executor.query` (the Slate-shaped query surface —
    ``legal_activations``/``legal_targets``/``choose_options``/
    ``optional_offer``, the C15/C17 enumerations; DESIGN_ACTION_SPACE
    §1.3/§1.4/§5.5/§8.3).
    12d adds the duration + continuous half: :mod:`executor.durations`
    (the full Duration vocab on the ledger — WHILE condition cycles,
    UNTIL_NEXT_STEP ticks, UNTIL_LEAVES zone interception, UNTIL_NEXT_
    TURN begin-turn expiry, all tombstoned for the audit dump),
    :mod:`executor.layers` (StaticAbility/KeywordAbility continuous
    layers: anthems recompute over the set, keyword_of / granted_abilities
    oracles, GRANT_ABILITY/LOSE_ABILITY verbs, PT payloads materialized
    into the single ledger PT stack) and :mod:`executor.replacements`
    (ReplacementAbility interceptor — Nine Lives' damage-to-you consumed
    before the world mutation, action journalled; PREVENT_EFFECT veto
    records with the UNTAP-step consumer live, combat-side exposed).
    The turn skeleton gains its UNTAP step: ``begin_turn`` untaps the
    active player's permanents except those a live prevention vetoes
    (Frost Breath freeze — survives exactly one untap tick), journalling
    every untap as a TapStateEvent, then expires the step-scoped durations.
    13a gives the same skeleton a **phase clock** (``Executor.phase`` /
    ``turn_open``, the honest sorcery-window gate), an **extra-turn queue**
    (``advance_turn`` pops it before rotating, CR 500.7 stand-in), an
    ``END_TURN`` request flag consumed by the op loop, a ``lost_players``
    ledger and the CR 606.3 ``loyalty_clock`` the legality gate reads.

Design mandates:

  * **flag, don't degrade** — every unsupported verb/effect/quantity/pred
    raises ``NotImplementedError`` at dispatch, naming the node; the
    executor never guesses a silent no-op (LOOK_AT/REVEAL are recorded,
    legitimate no-ops).
  * **explicit decisions** — every controller decision is answered
    externally (C15): an explicit per-op ``decisions`` pool for a KNOWN
    tree, or the 14b vocabulary-addressed stream (per-(vocab, what) FIFO
    / ask-time provider, :mod:`executor.decisions`) which needs no
    pre-enumeration of what an op will arm (B-4 ruling). Exhaustion raises.
  * **executor-owned randomness** — the only randomness is a
    :class:`random.Random` seeded from ``sha256(master_seed:op_seq:tag)``;
    two executors fed the same ops replay byte-identically (P12). The
    replay fingerprint is ``world.fingerprint()`` + the
    :class:`DurationLedger` dump + the 12a event log + the 12b journal and
    binder dumps (ruling 1: the ledger IS replayed state, since state.py
    stays frozen).
  * ``SUPPORTED_VERBS_V1`` is the frozen round-12 capability **contract** —
    the literal 24-verb set v1 goldens were measured against, pinned as a
    version so a later round's handler cannot silently widen a v1 gate.
    ``SUPPORTED_VERBS_V2`` is the honest **live** capability set, derived
    from the dispatch table so the two can never drift. Neither is wired
    into ``compile_pool`` gating (that is 12e's job).

13a brought the library/turn verbs into the live set: ``DRAW`` (the atom the
v1 scope list excluded — now a real handler over :meth:`GameWorld.draw`; the
library->hand ``MOVE_ZONE`` idiom cards compile to stays equally valid),
``SEARCH`` (the Cultivate compile), and the turn-flow four ``FLIP_COIN`` /
``END_TURN`` / ``EXTRA_TURN`` / ``LOSE_GAME``, which mutate **executor-side**
ledgers (the frozen :class:`GameWorld` carries no flip/turn/loss fields) and
are therefore the only verbs needing an executor-backed context.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    CounterKind,
    DelayedTrigger,
    EachPlayer,
    Effect,
    EtBState,
    FAnd,
    Keyword,
    OptionalEffect,
    Phase,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    Step,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import PoolCompile
from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES, TriggerBinder
from MTG_bot.core.executor.decisions import DecisionStream, site_digest
from MTG_bot.core.executor.durations import DurationLedger, PtChange
from MTG_bot.core.executor.events import (
    KIND_COMBAT_DAMAGE,
    KIND_DECLARE_ATTACKERS,
    KIND_DECLARE_BLOCKERS,
    KIND_TAP_STATE,
    KIND_ZONE_CHANGE,
    EventJournal,
    GameEvent,
)
from MTG_bot.core.executor.layers import GrantedAbility, LayerRecord, LayerRegistry
from MTG_bot.core.executor.legality import (
    ManaLedger,
    PaymentPlan,
    ability_playable,
    activate,
    block_pair_blocked_reason,
    blocker_askable,
    build_payment_plan,
    legal_attackers,
    mandated_attackers,
    mandated_to_be_blocked,
    pay_costs,
    spell_castable,
    spell_record,
)
from MTG_bot.core.executor.offers import offer_or_autopick
from MTG_bot.core.executor.quantity import Binding, ExecCtx, eval_filter
from MTG_bot.core.executor.query import (
    ActivationOption,
    CastOption,
    OptionChoice,
    TargetSlot,
    choose_options,
    legal_activations,
    legal_casts,
    legal_search,
    legal_targets,
    optional_offer,
    rest_of,
    spell_target_slots,
    validate_target_selection,
    verb_choose_options,
)
from MTG_bot.core.executor.replacements import (
    PreventionRecord,
    ReplacementRecord,
    ReplacementRegistry,
)
from MTG_bot.core.executor.selectors import (
    atom_target_slot_key as _atom_target_slot_key,
)
from MTG_bot.core.executor.selectors import (
    players_for_ref,
    resolve_selector,
)
from MTG_bot.core.executor.stack import (
    SpellObject,
    SpellStack,
    cast,
    cast_card,
    is_land_card,
    land_playable,
    open_combat_window,
    park,
    play_land,
    stack_zone,
)
from MTG_bot.core.executor.verbs import HANDLERS, run_atom, token_oracle_id
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_STACK, GameWorld

# The v1 capability CONTRACT — the round-12 24-verb set every v1 golden and
# the round-12 cross-check were measured against.  Deliberately a literal
# now, not a derivation: 13a grew the dispatch table (DRAW, SEARCH and the
# turn-flow four), and a versioned contract must not widen just because a
# later round shipped a handler.  ``SUPPORTED_VERBS_V2`` is the live set.
SUPPORTED_VERBS_V1 = frozenset(
    {
        Verb.MOVE_ZONE,
        Verb.EXILE,
        Verb.SACRIFICE,
        Verb.DESTROY,
        Verb.DISCARD,
        Verb.MILL,
        Verb.GAIN_LIFE,
        Verb.LOSE_LIFE,
        Verb.DEAL_DAMAGE,
        Verb.TAP,
        Verb.UNTAP,
        Verb.PUT_COUNTER,
        Verb.REMOVE_COUNTER,
        Verb.MODIFY_PT,
        Verb.SET_PT,
        Verb.CREATE_TOKEN,
        Verb.ADD_MANA,
        Verb.SCRY,
        Verb.SHUFFLE,
        Verb.LOOK_AT,
        Verb.REVEAL,
        Verb.GRANT_ABILITY,
        Verb.LOSE_ABILITY,
        Verb.PREVENT_EFFECT,
    }
)

# The 12e capability set: exactly the verbs ``run_atom`` dispatches to a real
# handler today (round-12 cross-check against all 48 corpus verbs).  Derived,
# never retyped: 12b/12d brought GRANT_ABILITY, LOSE_ABILITY and
# PREVENT_EFFECT, and 13a brought the library/turn verbs (DRAW, SEARCH,
# FLIP_COIN, END_TURN, EXTRA_TURN, LOSE_GAME), and 16a brought FIGHT
# (CR 701.12, the damage-exchange orphan verb).  The remaining non-dispatched
# verbs (CAST, COUNTER_SPELL, PHASE_OUT/PHASE_IN, COPY,
# MANDATE_ATTACK, MANDATE_BLOCK, PAY, ATTACH, GAIN_CONTROL, ...)
# stay outside: event-node-only or out-of-contract internals (ruling 6),
# flagged by ``compile_pool(supported_verbs=...)``, never faked.
SUPPORTED_VERBS_V2 = frozenset(HANDLERS)

Event = tuple[object, ...]

# 14a: the CR 504.5-c turn draw, as the IR node the turn skeleton runs for the
# active player. A module-level constant because ``Atom`` is frozen — one
# node shared by every turn, never re-constructed, so the DRAW atom is
# byte-identical across replays. ``ControllerRef.YOU`` resolves through
# :func:`selectors.role_player` to the context's controller, which the
# skeleton sets to the active seat (:meth:`Executor._turn_draw`).
_TURN_DRAW = Atom(
    verb=Verb.DRAW,
    args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
)

# 16b: the player-side target of one combat-damage atom — the same
# PLAYER-zone TARGET Selector shape the player-damage tests use
# (test_executor_verbs L200); the dealer rides ctx.source (the journal's
# cause column), the recipient is the bound handle (14c B-16: a bound
# handle outranks the selector — a PLAYER handle bound to a PLAYER-zone
# selector is returned as-is).
_PLAYER_TARGET = Selector(
    QConst(1),
    SelectorMode.TARGET,
    FAnd(children=()),
    zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),),
)

# 16c: the CARD lane of the combat-damage atom. A player-zone selector is
# deliberately BLIND to a binding (the 16a Brash rule in role_handles), so
# a blocker recipient must be announced through a battlefield-zone TARGET
# selector — binding-first — or the wave would keep landing on the
# defending player no matter what was assigned.
_CARD_TARGET = Selector(
    QConst(1),
    SelectorMode.TARGET,
    FAnd(children=()),
    zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
)


def _combat_damage_atom(amount: int, recipient: object) -> Atom:
    """One DEAL_DAMAGE atom of ``amount`` to the announced recipient. A
    builder, not a constant: the amount is per-dealer, the RECIPIENT picks
    the lane (16c — blockers take their announced share, the attacked
    object takes the rest; pre-16c every combat atom was the unblocked
    player shape), and the frozen-Atom discipline keeps every atom of one
    damage step byte-identical across replays."""
    target = _PLAYER_TARGET if str(recipient).startswith("player:") else _CARD_TARGET
    return Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(pairs=(("amount", QConst(amount)), ("target", target))),
    )


__all__ = [
    "MAX_TRIGGER_FIRES",
    "SUPPORTED_VERBS_V1",
    "SUPPORTED_VERBS_V2",
    "ActivationOption",
    "Binding",
    "CastOption",
    "DurationLedger",
    "Event",
    "EventJournal",
    "ExecCtx",
    "Executor",
    "GameEvent",
    "GrantedAbility",
    "LayerRecord",
    "LayerRegistry",
    "ManaLedger",
    "OptionChoice",
    "PaymentPlan",
    "PreventionRecord",
    "PtChange",
    "ReplacementRecord",
    "ReplacementRegistry",
    "SpellObject",
    "SpellStack",
    "TargetSlot",
    "TriggerBinder",
    "ability_playable",
    "activate",
    "build_payment_plan",
    "cast",
    "cast_card",
    "choose_options",
    "is_land_card",
    "land_playable",
    "legal_activations",
    "legal_casts",
    "legal_search",
    "legal_targets",
    "optional_offer",
    "park",
    "pay_costs",
    "play_land",
    "rest_of",
    "spell_castable",
    "spell_record",
    "spell_target_slots",
    "stack_zone",
    "validate_target_selection",
    "verb_choose_options",
]


class Executor:
    """Runs IR against one :class:`GameWorld` (mutable across calls, like
    the world itself). One Executor per world/replay; a replay is a fresh
    Executor fed the same atom/attach/turn sequence."""

    def __init__(self, world: GameWorld) -> None:
        if not isinstance(world, GameWorld):
            raise ValueError(
                f"Executor: world must be a GameWorld, got {type(world).__name__}"
            )
        self.world = world
        self.ledger = DurationLedger()
        self.events: list[Event] = []
        self.token_counts: dict[str, int] = {}
        # 16a (CR 120.6): damage MARKED on cards. The frozen GameWorld has
        # no damage field, so the marks are executor-side replayed state
        # (ruling 1: folded into state_fingerprint, removed at the cleanup
        # step and when the permanent leaves the battlefield).
        self.damage: dict[Handle, int] = {}
        # CR 702.26 (2026-10-29): PHASED-OUT permanents. Phasing is a status
        # of the permanent (CR 110.5), not a zone: the card stays in its
        # battlefield zone, no zone-change event happens (702.26d), and the
        # engine's battlefield readers leave it out (it is treated as though
        # it does not exist, 702.26b). handle -> (the player who controlled
        # it when it phased out: it phases in during that player's untap
        # step, CR 502.1; the permanent it phased out indirectly with, or
        # None when it phased out directly, 702.26g). Replayed state, folded
        # into state_fingerprint when non-empty.
        self.phased_out: dict[Handle, tuple[Handle, Handle | None]] = {}
        # r23a (Wildwood Scourge, CR 614.1c): the X declared by a spell's
        # cast (601.2f) travels to that permanent's ETB firings. stack.cast
        # records the declared X as the spell ENTERS the battlefield; the
        # binder's _ctx hands it to the firing's ExecCtx (x_value) for that
        # entry ONLY, consuming it. Cleared when the permanent leaves the
        # battlefield so a graveyard re-entry (reanimation) is NOT cast-
        # context: its ETB firing reads X = 0 (CR 107.3b; binding._ctx).
        self.etb_x: dict[Handle, int] = {}
        # r23a (Rin and Seri): LOUD refusals of the guarded-static lane —
        # a StaticAbility whose payload is not layer-parseable (12e) is
        # skipped at battlefield attach and recorded here (handle + the
        # engine's own message). NOT folded into state_fingerprint: it is
        # a pure derivation of the world + records, never a hidden
        # decision. Coverage reporting and the scenario packs assert it.
        self.unparseable_statics: list[str] = []
        # r23a (Chandra's Incinerator, games seeds 17/50): the tripwire
        # guard's loud ledger. A self-retriggering trigger source hits the
        # drain tripwire; the guard QUARANTINES the source (its queued and
        # future firings are dropped) and records the event here — "flag
        # it, never run it", the drain continues instead of killing the
        # game. Like unparseable_statics this is a coverage-visible record,
        # NOT folded into state_fingerprint (the quarantine set itself,
        # which is state, rides the fold through the binder).
        self.trigger_loops: list[str] = []
        # r24/r24a (ZNR fuzz, /111+/112): LOUD refusals of the live-game
        # guard. An effect whose anaphora (``result``/``target``) reads a
        # register no producer in this execution wrote is a compiler
        # mis-fold (unparsed antecedent sentence), not a game bug: the
        # guarded lanes skip the failing step, the spell still resolves,
        # and the refusal is recorded here (lane + card + the engine's
        # own message, deduped by key with an OCCURRENCES count per key
        # — distinct same-message atoms sharing one key stay visible
        # through ``unresolved_effect_counts``). Queryable, surfacing
        # pending: the ledger has NO consumer yet (cards stay
        # engine_supported=True; the compiler-wave fold gates are the
        # fix). Same contract as unparseable_statics / trigger_loops:
        # NOT folded into state_fingerprint, and only
        # selectors.referent_absent refusals (dedicated error TYPE +
        # exact site message) are caught — every other error still
        # propagates.
        self.unresolved_effects: list[str] = []
        self.unresolved_effect_counts: dict[str, int] = {}
        self.journal = EventJournal(world, self.ledger)
        # 12d registries (built BEFORE the binder: the binder's lifecycle
        # hooks reach them during attach).
        self.layers = LayerRegistry(self)
        self.replacements = ReplacementRegistry(self)
        self.binder = TriggerBinder(self)
        self._op_seq = 0
        self._turn_started = False
        # ------------------------------------------------------ 13a turn state
        # The frozen GameWorld has no phase/turn-flow/loss fields, so the
        # turn skeleton owns this ledger (ruling 1: replayed state lives on
        # the executor, and every field below is in state_fingerprint).
        # ``phase`` is the last phase marker recorded (None before the first
        # begin_turn); ``turn_open`` is the "a turn is in progress" flag the
        # legality gates read.
        self.phase: str | None = None
        self.turn_open = False
        # CR 500.7: EXTRA_TURN pushes onto the FRONT (the most recently
        # created turn is taken first), advance_turn pops index 0.
        self.extra_turn_queue: list[Handle] = []
        # CR 500.7: extra turns are inserted after a turn, so the normal turn
        # order resumes from the seat of the last NORMAL turn, never from an
        # extra turn's player. None until advance_turn first rotates (the
        # first turn is the normal turn of whoever began it).
        self.normal_turn_seat: Handle | None = None
        # LOSE_GAME ledger (the emptied-library CR 121.3 loss is the later
        # state-check phase, not a verb).
        self.lost_players: list[Handle] = []
        # CR 606.3: handle -> turn of that permanent's last loyalty act.
        self.loyalty_clock: dict[Handle, int] = {}
        # FLIP_COIN's winner, read by the FLIP_WON conditional of a
        # separate ability row (Tavern Swindler compiles to two).
        self.last_flip_won_by: Handle | None = None
        # END_TURN's deferred close (consumed by the op loop).
        self.end_turn_requested = False
        self._closing_turn = False
        # ------------------------------------------------- 13b stack + mana
        # The spell stack (LIFO frames, CR 405): no-interaction v1 pushes
        # only during a cast, but the container, the ZONE_STACK parking and
        # the fingerprint fold are permanent (risk-1: a future response
        # window reads SpellObject frames, not a re-derived world).
        self.stack = SpellStack()
        # CR 305.1 once-per-turn land gate: seat -> (turn, plays);
        # extra_land_plays is the 13c ADD_LAND_PLAY hook (Azusa), 0 today.
        self.land_ledger: dict[Handle, tuple[int, int]] = {}
        self.extra_land_plays = 0
        # The segment mirror of the frozen mana pool (THIS_MANA
        # restrictions; tags EMPTY everywhere in the 12a/12b corpus, which
        # is what keeps their totals-path replay pins byte-identical).
        self.mana_ledger = ManaLedger()
        # CHOOSE_NAME's write-side (Runed Halo): source permanent -> the
        # chosen name, read back by the NAME_CHOSEN filter predicate.
        self.name_choices: dict[Handle, str] = {}
        # ------------------------------------------------- 13c emblems + attachments
        # Granted emblems are replayed state that is NOT world cards (an
        # emblem never enters a zone): (owner, emblem oracle_id) -> the
        # synthetic Handle("emblem", n) the binder bound its triggers to.
        # The key doubles as the CR 113.7 idempotence gate: a second copy
        # of the same emblem does nothing.
        self.emblems: dict[tuple[Handle, str], Handle] = {}
        self._emblem_seq = 0
        # Attachment relation (auras/equipment): AURA handle -> HOST handle.
        # The frozen CardState has no attachment field, so the table lives
        # here; IS_ATTACHED_TO_SOURCE reads it and the binder drops every
        # edge touching a handle that leaves the battlefield.
        self.attachments: dict[Handle, Handle] = {}
        # r20c (Malefic Scythe): LAST-KNOWN-INFORMATION snapshot of the
        # attachment relation at a HOST's battlefield departure — HOST ->
        # sorted auras/equipment that were attached to it. The journal
        # writes ZONE_CHANGE before CREATURE_DIES in the same diff sweep,
        # so by the time a dies-trigger's IS_ATTACHED_TO_SOURCE filter is
        # judged the live table is already pruned; the LKI row is that
        # object's own departure-time truth (CR 400.7's information-
        # timestamp doctrine). Replaced wholesale per sweep keyed on the
        # departing host — a re-entry/dying captures fresh truth. Derived
        # state replayed from the same detaches, so it is NOT part of the
        # replay fingerprint (pin-stable).
        self.detach_lki: dict[Handle, tuple[Handle, ...]] = {}
        # V31b follow-up (CR 603.10a: leaves-the-battlefield abilities look back
        # in time): the departed permanent's last known (power, toughness,
        # counters), captured as it leaves the battlefield and before its
        # counters cease to exist (CR 122.2), so "When this creature dies, you
        # gain life equal to its power" (Conclave Mentor) and "if it had a +1/+1
        # counter on it" (Basri's Lieutenant) read the object as it last existed.
        # Dropped when the card re-enters (a new object, CR 400.7). Derived state
        # replayed from the same departures, NOT in the fingerprint (the
        # detach_lki precedent above).
        self.departed_lki: dict[
            Handle, tuple[int | None, int | None, dict[str, int]]
        ] = {}
        # r20c (Speaker of the Heavens): the game's STARTING life per seat,
        # snapshotted at executor construction — the fact the frozen world
        # takes as a ``start_life`` parameter but never stores. LIFE_LEAD_-
        # OVER_START_GE reads current minus this (the journal cannot
        # reconstruct the lead: a non-damage life loss leaves no row). The
        # replay rebuilds the world at the same start_life
        # (games.py:1017), so the snapshot is replay-identical and stays
        # OUT of the replay fingerprint.
        self.starting_life: dict[Handle, int] = {
            p: world.players[p].life for p in world.player_order
        }
        # -------------------------------------------------- 16e control overlay
        # GAIN_CONTROL (CR 611, 110.2): the frozen GameWorld derives
        # controller_of from the ZONE OWNER and R16-4 DENIED the additive
        # hook there, so control changes are executor-side replayed state
        # (ruling 1: folded into state_fingerprint). ``control_entries`` is
        # the source of truth — one row per live GAIN_CONTROL application
        # (seq, creature, controller, expiry tag, anchor, turn gained);
        # ``control_overlay`` is the DERIVED effective-controller map the
        # executor read sites consult (later entries win, CR 613.2
        # timestamps), and ``control_gained_turn`` the CR 302.6 sickness
        # clock (control-based, not ownership-based). A creature with no
        # entry reads its zone owner, which is why the empty overlay keeps
        # every pre-16e replay byte-identical.
        self.control_entries: list[
            tuple[int, Handle, Handle, str, Handle | None, int]
        ] = []
        self._control_seq = 0
        self.control_overlay: dict[Handle, Handle] = {}
        self.control_gained_turn: dict[Handle, int] = {}
        # --------------------------------------------------- 16b combat state
        # The frozen GameWorld has no combat fields, so the attack record
        # is executor-side replayed state (ruling 1, folded into
        # state_fingerprint): the current attackers in declaration order,
        # each one's ATTACKED object (v1: the defending player — blocker
        # and planeswalker assignment are 16c), the phase's defending seat,
        # and the declare-window flag the enters-attacking token path
        # reads (CR 508.1i). ``mandates`` is the DISPATCHED MANDATE_ATTACK
        # ledger (the static shape lives as layers' "mandate" records).
        self.attackers: list[Handle] = []
        self.attacked: dict[Handle, Handle] = {}
        self.defending_player: Handle | None = None
        self.declaring = False
        self._declare_group = 0
        self.mandates: set[Handle] = set()
        # -------------------------------------------------- 16c block state
        # ``blocked_by``: attacker -> the creatures blocking it, in DECLARE
        # order (CR 509.1b: one attacker per blocker, so a handle appears in
        # exactly one list; multiple blockers per attacker ARE legal — the
        # assignment order is asked per attacker, CR 510.1). Cleared with
        # the attack record at end of combat; replayed state (ruling 1).
        self.blocked_by: dict[Handle, list[Handle]] = {}
        # DISPATCHED MANDATE_BLOCK ledger (the static shape rides layers'
        # "mandate_block" records; Canopy Stalker's rule line).
        self.mandate_block: set[Handle] = set()
        # DISPATCHED DAMAGE_ASSIGN_POLICY scopes (GRANT_ABILITY-carried
        # statics read through layers.policy_as_unblocked; the dispatch
        # shape records the scope word here keyed by its source).
        self.damage_policies: dict[Handle, str] = {}
        # The combat-damage wave flag: set for the atom boundaries inside
        # one combat-damage substep so record_atom marks the DAMAGE rows
        # (amount, True) — the DamageDealtEvent ``combat`` scope (16c,
        # Garruk's Harbinger / Subira's delayed trigger).
        self._combat_wave_open = False
        # r22b (Teferi's Ageless Insight): the CR 504.5 draw-step register.
        # _draw_step_open is True ONLY while :meth:`_turn_draw` runs; the
        # ordinal map counts the draws that happened inside that window per
        # player (_v_draw stamps, NOT_FIRST_DRAW_THIS_STEP reads, see
        # quantity.py). Transient like the combat flag — never fingerprinted.
        self._draw_step_open = False
        self.draw_step_ordinal: dict[Handle, int] = {}
        # Deathtouch marks (CR 702.2b): a creature carrying ANY damage
        # marked by a deathtouch source dies at the state check even below
        # lethal; the flag rides the ledger beside the amount.
        self.damage_deathtouch: set[Handle] = set()
        # Public alias of the seeded factory (the binder builds ExecCtxs too).
        self.rng = self._rng
        # 14b: the vocabulary-addressed decision channel (B-4 ruling). One
        # stream per executor/replay: FIFO priming, ask-time provider and
        # the ask log ride EVERY context the executor builds — effect ops,
        # trigger firings, payments, replacement actions — which is what
        # lets a policy answer a demand a running op armed mid-drain.
        self.decisions = DecisionStream()

    # ------------------------------------------------------------------ rng

    def _rng(self, tag: str) -> random.Random:
        """The executor-owned seeded factory: no wall-clock, no globals —
        the same (master_seed, op_seq, tag) always yields the same stream."""
        seed = hashlib.sha256(
            f"{self.world.master_seed}:{self._op_seq}:{tag}".encode()
        ).hexdigest()
        return random.Random(int(seed, 16))

    # -------------------------------------------------------------- context

    def _ctx(
        self,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Binding] | None,
        decisions: Sequence[str],
        x_value: int | None = None,
    ) -> ExecCtx:
        if not isinstance(source, Handle) or not isinstance(controller, Handle):
            raise ValueError("Executor: source and controller must be Handles")
        return ExecCtx(
            world=self.world,
            ledger=self.ledger,
            controller=controller,
            source=source,
            bindings=dict(bindings or {}),
            decisions=tuple(decisions),
            events=self.events,
            rng=self._rng,
            token_counts=self.token_counts,
            # 12d: the registries ride on every effect context (layer
            # verbs, the damage-replacement interceptor).
            layers=self.layers,
            replacements=self.replacements,
            executor=self,
            x_value=x_value,
            stream=self.decisions,
            # 14d (B-7): the journal rides on every effect context too (the
            # history preds answer identically from a query ctx or a firing
            # ctx — §8.3 query/runtime identity over the SAME rows).
            journal=self.journal,
        )

    def _cast_ctx(
        self,
        handle: Handle,
        seat: Handle,
        bindings: dict[str, Binding],
        decisions: Sequence[str],
        x: int | None,
    ) -> ExecCtx:
        """13b: the spell-resolution context — the ordinary effect context
        with the cast's declared X bound (CR 601.2f: X was chosen with the
        total cost; the effect's ``{X}`` readings resolve off it)."""
        return self._ctx(
            source=handle,
            controller=seat,
            bindings=bindings,
            decisions=decisions,
            x_value=x,
        )

    def mana_permission(self, seat: Handle) -> bool:
        """ALL_YOURS for ``seat`` (Orrery's "you may spend mana as though
        it were mana of any color") — the live layer query in one place so
        plan-building never reaches into the registry directly."""
        return self.layers.all_yours_live(seat)

    # ------------------------------------------------------------ execution

    def execute(
        self,
        atom: Atom,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Binding] | None = None,
        decisions: Sequence[str] = (),
    ) -> tuple[Event, ...]:
        """Run one Atom; returns the 12a events this call appended.
        Unsupported verbs raise ``NotImplementedError`` at dispatch. The
        atom's world changes are journalled; any trigger the change arms
        drains afterwards (APNAP). Trigger-drain decisions arrive through
        the executor's vocabulary-addressed stream (14b, B-4) — the old
        positional ``trigger_decisions`` kwarg is deleted: it could not
        carry demands the op itself armed."""
        if not isinstance(atom, Atom):
            raise ValueError(
                f"Executor: execute needs an Atom, got {type(atom).__name__}"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source, controller=controller, bindings=bindings, decisions=decisions
        )
        start = len(self.events)
        self._run_effect(atom, ctx)
        self._settle()
        self._consume_end_turn()
        return tuple(self.events[start:])

    def apply_effect(
        self,
        effect: Effect,
        *,
        source: Handle,
        controller: Handle,
        bindings: dict[str, Binding] | None = None,
        decisions: Sequence[str] = (),
        slot_designations: dict[str, tuple[Handle, ...]] | None = None,
        x_value: int | None = None,
    ) -> tuple[Event, ...]:
        """Run an Effect tree; the per-op pool ``decisions`` covers the
        KNOWN tree in ask order, and every demand it cannot serve reaches
        the executor's vocabulary-addressed stream (14b). OptionalEffect
        asks the query-narrowed offer vocab (``fire``/``skip``), Seq runs
        its steps, Conditional judges the pred against the *source*
        handle (r19b: or the previous sentence's revealed card when a
        look window is open), Choose (12d: ONE decision token = the index of the chosen
        option-set in ``query.choose_options`` order), EachPlayer (14f:
        one sub-execution per denoted player, controller rotated — the
        inner effect is compiled YOU-relative, so the rotation IS the
        rebinding) and DelayedTrigger (scheduled, C22) are wired; Repeat
        raises as an unimplemented node (12e). ``x_value`` is an activated
        ability's announced X (CR 107.3a; ``legality.activate``'s X lane),
        None for every effect with no X."""
        if not isinstance(
            effect,
            (
                Atom,
                Seq,
                OptionalEffect,
                Conditional,
                DelayedTrigger,
                Choose,
                EachPlayer,
            ),
        ):
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12e)"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source,
            controller=controller,
            bindings=bindings,
            decisions=decisions,
            x_value=x_value,
        )
        if slot_designations:
            # V25: an activation's per-target designations (legality.activate),
            # the same per-slot map the cast lane sets on a multi-target spell.
            ctx.slot_designations = slot_designations
            ctx.designation_union = tuple(
                sorted({h for one in slot_designations.values() for h in one})
            )
        start = len(self.events)
        self._run_effect(effect, ctx)
        self._settle()
        self._consume_end_turn()
        return tuple(self.events[start:])

    @staticmethod
    def _partition_step(step: object) -> bool:
        """r19a (Cultivate) partition scan, one encoding (shared by the
        ``_run_effect`` Seq branch and the guarded lane): a partition
        MOVE_ZONE is one whose ``cards`` Selector is ONE_OF/REST."""
        if not isinstance(step, Atom) or step.verb is not Verb.MOVE_ZONE:
            return False
        sel = step.args.get("cards")
        return isinstance(sel, Selector) and sel.mode in (
            SelectorMode.ONE_OF,
            SelectorMode.REST,
        )

    def _run_guarded_effect(self, effect: Effect, ctx: ExecCtx, lane: str) -> None:
        """r24/r24a (ZNR fuzz, /111+/112): the LIVE-GAME effect runner
        with the dangling-anaphora guard (spell resolution lanes
        cast/cast_card/aura + the trigger-firing lane). Runs
        ``_run_effect``; if the effect refuses because its
        ``result``/``target`` anaphora has NO producer in this execution
        (a compiler mis-fold: the antecedent clause was never compiled —
        Acquisitions Expert's dangling discard, Shell Shield's dangling
        kicker hexproof), the step is skipped and the refusal recorded
        on ``unresolved_effects`` — the spell still resolves / the game
        still plays (the r23a unparseable-statics law: lose the
        mis-shaped half, not the match). r24a (adversarial gate): (i) the
        skip matches ONLY the dedicated ReferentAbsentError types with
        the exact site message (selectors.referent_absent) — a look-alike
        message, the QProp referent refusal or anything else PROPAGATES;
        (ii) CR 609.7 do-as-much-as-possible: a TOP-LEVEL ``Seq`` runs
        step-by-step, so a dangling MID-step skips that step and the
        TAIL still executes. Boundary, stated honestly: the granularity
        is the top level only — a nested inner Seq (or Optional/
        Conditional wrapper) that fails mid-way is skipped AT WHOLE-STEP
        granularity, its remaining inner steps lost with it; only the
        compiler-wave fold gates make either shape moot. Every other
        error propagates unchanged, and the unit contract (unset referent
        reads RAISE) stays byte-identical on the raw ``_run_effect``
        lane the tests pin.
        """
        from MTG_bot.core.executor.selectors import referent_absent
        from MTG_bot.core.executor.stack import face_cast_absent

        steps = effect.steps if isinstance(effect, Seq) else (effect,)
        saved_partition = ctx.search_partition
        if isinstance(effect, Seq):
            # the Seq branch's SEARCH-designation context, reproduced so
            # the guarded per-step lane behaves identically to a raw
            # Seq run (r19a partition law).
            ctx.search_partition = saved_partition or any(
                self._partition_step(step) for step in steps
            )
        try:
            for step in steps:
                depth = self.journal.open_depth()
                try:
                    self._run_effect(step, ctx)
                except (NotImplementedError, ValueError) as exc:
                    if not (referent_absent(exc) or face_cast_absent(exc)):
                        raise
                    # V23: the skipped step's atom boundary never closes.
                    self.journal.drop_open(depth)
                    src = ctx.source
                    name = (
                        self.world.cards[src].identity.name
                        if src in self.world.cards
                        else "?"
                    )
                    # /115: the ledger entry IS the trace (r24a pattern —
                    # a guard skip journals nothing, it registers).
                    flag = f"{lane} {name}: {exc}"
                    if flag not in self.unresolved_effect_counts:
                        self.unresolved_effects.append(flag)
                        self.unresolved_effect_counts[flag] = 1
                    else:
                        self.unresolved_effect_counts[flag] += 1
        finally:
            ctx.search_partition = saved_partition

    def _run_effect(self, effect: Effect, ctx: ExecCtx) -> None:
        if isinstance(effect, Atom):
            # 12b: the journalled Atom boundary — snapshot, run, diff. This
            # is the ONLY place world mutations happen on the executor path,
            # so the journal sees every trigger-relevant change without a
            # single verbs.py edit.
            before = self.journal.snapshot()
            start = len(self.events)
            # r19c (Rookie Mistake / Hunter's Edge): on a MULTI-slot spell
            # each TARGET atom acts on ITS OWN designation — the shared
            # union binding cannot serve two populations, so the Atom lane
            # shadows bindings["target"] to the atom's slot (repr-matched,
            # the same identity key spell_target_slots dedupes on) for the
            # duration of run_atom. QProp(referent='target') anaphora reads
            # through the shadow, so "…equal to THAT creature's power"
            # means the atom's own target, never the sorted-first of a
            # union. IS_ANY_TARGET is exempt via ExecCtx.designation_union.
            # Single-slot spells: slot_designations is None, zero change.
            designations = ctx.slot_designations
            slot_key = (
                _atom_target_slot_key(effect, designations) if designations else None
            )
            shadow_prev: Binding | None = None
            if slot_key is not None and designations is not None:
                shadow_prev = ctx.bindings.get("target")
                ctx.bindings["target"] = list(designations[slot_key])
            try:
                run_atom(effect, ctx)
            finally:
                if slot_key is not None:
                    if shadow_prev is None:
                        ctx.bindings.pop("target", None)
                    else:
                        ctx.bindings["target"] = shadow_prev
            new_events = self.journal.record_atom(
                before,
                ctx.source,
                effect.verb.name,
                self.events[start:],
                combat=self._combat_wave_open,
            )
            # 12d hook 1: the UNTIL_LEAVES zone interceptor. Every zone
            # change the journal just saw gets its anchor checked — a
            # permanent leaving the battlefield terminal-expires the
            # durations anchored on it (return does not restore, r5).
            self._on_zone_changes(new_events)
            # 12d hook 2: damage replacements consumed during the atom run
            # (C24: the damage never applied) queue their ACTION here, so
            # it journalled as ITS OWN atom boundary — one diff per
            # mutation, no double-emitted events.
            while ctx.pending_replacements:
                entry = ctx.pending_replacements.pop(0)
                repl_bindings: dict[str, Binding] | None = None
                counter_reg: tuple[CounterKind, int] | None = None
                if isinstance(entry, tuple):
                    if len(entry) == 4:
                        # r22b (Conclave Mentor): a counter-placement
                        # consumer queued (record, receiving card, kind,
                        # amount) — the action's referent binds to the
                        # card AND the COUNTER_COUNT prop register carries
                        # the replaced event's count (ADD(QProp(event,
                        # COUNTER_COUNT), 1) reads it, quantity.py).
                        repl, event_card, counter_kind, counter_n = entry
                        repl_bindings = {"event": [event_card]}
                        counter_reg = (counter_kind, counter_n)
                    else:
                        # r20b (Containment Priest): a zone-change consumer
                        # queued (record, moving card) — the action's
                        # referent selector ("exile it") resolves against
                        # the binding the die lane uses.
                        repl, event_card = entry
                        repl_bindings = {"event": [event_card]}
                else:
                    repl = entry
                inner = self._ctx(
                    source=repl.source,
                    controller=repl.controller,
                    bindings=repl_bindings,
                    decisions=(),
                )
                if counter_reg is not None:
                    inner.event_counter_count = counter_reg[1]
                # r19a: the CR 614.4a chain guard travels with the action —
                # the record that consumed THIS event cannot consume the
                # event its own action produces.
                inner.replaced_seq = ctx.replaced_seq | {repl.seq}
                self._run_effect(repl.action, inner)
        elif isinstance(effect, Seq):
            # r19a (Cultivate): when a partition MOVE_ZONE (the ONE_OF pick
            # / REST complement) appears among the steps, a SEARCH atom in
            # this sequence DESIGNATES instead of delivering — the
            # partition re-searches the found set and would find nothing
            # the SEARCH had already moved. Shallow scan: the corpus'
            # partition idiom is a flat sibling chain (the compiler emits
            # SEARCH/REVEAL/MOVE/MOVE/SHUFFLE as direct steps).
            partition = any(self._partition_step(step) for step in effect.steps)
            saved = ctx.search_partition
            ctx.search_partition = saved or partition
            try:
                for step in effect.steps:
                    self._run_effect(step, ctx)
            finally:
                ctx.search_partition = saved
        elif isinstance(effect, OptionalEffect):
            # 14b (B-5, query/runtime identity): the ASK vocabulary is the
            # query surface's own narrowed optional_offer — the policy gets
            # exactly what a query would answer ("may pay {2}" with an
            # empty pool offers only skip, CR 117.3, so a provider can never
            # answer fire where firing is illegal). The site tag keys the
            # answer to THIS ability's offer (B-4 vocabulary addressing):
            # T5-F1 adds the OFFER digest, so two may-offers on ONE source
            # are two sites (the source-only tag mispaired their FIFO
            # primings), and a skip-narrowed surface is auto-consumed by
            # the shared phantom gate instead of billed as a decision.
            offer = optional_offer(
                self,
                effect,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            if (
                offer_or_autopick(ctx, offer, f"may:{ctx.source}:{site_digest(effect)}")
                == "fire"
            ):
                self._run_effect(effect.inner, ctx)
        elif isinstance(effect, Conditional):
            # r19b (Track Down): the compiler's sentence convention
            # (templates_b5b _build_if_it_type_then: "Conditional whose
            # subject is the previous sentence's revealed card") — when the
            # preceding atom was a LOOK_AT/REVEAL, the pred judges the
            # revealed card, not the ability source (whose types could
            # never match "is a creature or land" and silently killed the
            # DRAW tail). run_atom cleared the window on every other verb,
            # so every bare Conditional keeps the ctx.source subject.
            subj = ctx.look_window[0] if ctx.look_window else ctx.source
            if eval_filter(effect.pred, subj, ctx):
                self._run_effect(effect.then_effect, ctx)
            elif effect.else_effect is not None:
                self._run_effect(effect.else_effect, ctx)
        elif isinstance(effect, Choose):
            # 12d runtime consumption — ORDER CONTRACT (query.OptionChoice
            # docstring): the decision token is str(i), the i-th OPTION-SET
            # of query.choose_options (size-ascending, index-lex). One
            # decision picks the whole set (a k-choose is one compound
            # choice, C15: the Slate's OPTION:PTR* slot is one token).
            opts = choose_options(
                self,
                effect,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            vocab = tuple(str(i) for i in range(len(opts)))
            # r19c (Return to Nature, CR 601.2b): a mode DECLARED at cast
            # time (the cast lane consumed the ORDER token before the
            # targets — modes before targets) arrives as a pre-chosen
            # token; asking again would bill the pack for a decision the
            # caster already made. Empty everywhere else — every pre-19c
            # Choose keeps asking its token at resolution, byte-unchanged.
            if ctx.prechosen_modes:
                pick = ctx.prechosen_modes.pop(0)
                if pick not in vocab:
                    raise ValueError(
                        f"executor: choose: declared mode {pick!r} not in {vocab}"
                    )
            else:
                # T5-F1 (CR 601.2b, stack.py:442's rule in the decision
                # channel): a menu whose bounds clamp to ONE option set
                # ("choose two" over two options) is FORCED — the shared
                # phantom gate consumes it silently and journals the pick;
                # a 1-candidate ask is a §10 phantom, never a decision.
                pick = offer_or_autopick(
                    ctx,
                    vocab,
                    f"choose:{ctx.source}:{site_digest(tuple(o.option_idxs for o in opts))}",
                )
            for idx in opts[int(pick)].option_idxs:
                self._run_effect(effect.options[idx], ctx)
        elif isinstance(effect, EachPlayer):
            # 14f (B-20): "each opponent …" (Goremand's ETB sacrifice,
            # Keral Keep Disciples' damage, Pursued Whale's tokens, Thieves'
            # Guild Enforcer's mills — the four corpus faces, ALL_OPPONENTS).
            # One sub-execution per denoted player with the CONTROLLER
            # rotated: the templates compile the inner effect YOU-relative
            # (b2a/b2b ruling — Goremand's SACRIFICE filter CONTROLLER_IS
            # YOU, MILL's controller role, Zone(PLAYER,YOU)), so rotation
            # IS the rebinding; the spell's designations stay visible
            # (bindings carried, never rewritten). Iteration order is
            # players_for_ref's seat order; CR 800.2 runs each-player
            # effects APN-first — in the duel the two coincide, and the
            # seat-order reading is the documented convention (doc
            # 09-30/09), never a silent rule. The per-op decision POOL
            # cursor rides across the sub-contexts (one positional supply
            # answers every station in ask order, byte-identical to the
            # single-context consumption the 12a-era pins use) and is
            # written back; the vocabulary-addressed stream lanes are
            # executor-owned and need no forwarding. Each inner atom
            # journals its own boundary under the stable source.
            for player in players_for_ref(effect.ref, ctx):
                inner = self._ctx(
                    source=ctx.source,
                    controller=player,
                    bindings=ctx.bindings,
                    decisions=ctx.decisions,
                    x_value=ctx.x_value,
                )
                inner.decision_idx = ctx.decision_idx
                self._run_effect(effect.effect, inner)
                ctx.decision_idx = inner.decision_idx
        elif isinstance(effect, DelayedTrigger):
            # C22: schedule into the journal matcher (12b), expire at Eot.
            self.binder.schedule_delayed(effect, ctx.source, ctx.controller)
        else:  # pragma: no cover - apply_effect pre-checks the node type
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12e)"
            )

    def _on_zone_changes(self, events: list[GameEvent]) -> None:
        """UNTIL_LEAVES expiry: a tracked anchor leaving the battlefield
        terminal-expires every duration anchored on it (ledger entries,
        layer records, prevention records). Deterministic: the journal's
        emit order."""
        for event in events:
            if event.kind != KIND_ZONE_CHANGE or event.subject is None:
                continue
            from_state = event.zone_move[0]
            if (
                from_state == ZONE_BATTLEFIELD
                and event.zone_move[1] != ZONE_BATTLEFIELD
                and event.subject in self.world.cards
            ):
                state = self.world.cards[event.subject]
                power, toughness = self.ledger.effective_pt(
                    state.identity, event.subject, state.counters
                )
                self.departed_lki[event.subject] = (power, toughness, dict(state.counters))
            elif event.zone_move[1] == ZONE_BATTLEFIELD:
                self.departed_lki.pop(event.subject, None)  # a new object (CR 400.7)
            if event.zone_move[1] != ZONE_BATTLEFIELD and event.subject in self.world.cards:
                # V31b, CR 122.2: "Counters on an object are not retained if that
                # object moves from one zone to another ... they simply cease to
                # exist." The journal row above was emitted first, so a dies row's
                # was-P/T still folds them (the C18 snapshot). A battlefield entry
                # keeps what its entry stamped (the loyalty seed, EtBState counters).
                self.world.cards[event.subject].counters.clear()
            if from_state != ZONE_BATTLEFIELD:
                if event.zone_move[1] == ZONE_BATTLEFIELD:
                    # 17a: the symmetric ENTER branch — the compiled
                    # EtBState node ("enters the battlefield tapped",
                    # "enters with a soul counter") finally gets its
                    # consumer. CR 614.1c: the entered state is stamped
                    # as the permanent enters, BEFORE its ETB triggers
                    # go on the stack (the settle order below already
                    # matches: this runs, then binder drains).
                    self._apply_etb_state(event.subject)
                continue
            anchor = event.subject
            self.ledger.expire_leaves(anchor)
            self.layers.expire_leaves(anchor)
            self.replacements.expire_leaves(anchor)
            self.etb_x.pop(anchor, None)  # r23a: cast-X leaves with it
            self.damage.pop(anchor, None)  # 16a: CR 120.6, marks leave with it
            self.damage_deathtouch.discard(anchor)  # 16c: the flag rides along
            # 16c: a departing permanent leaves no trace in the block record
            # (a dead blocker stops blocking, a dead attacker forgets).
            self.blocked_by.pop(anchor, None)
            for blockers in self.blocked_by.values():
                if anchor in blockers:
                    blockers.remove(anchor)
            self.mandates.discard(anchor)
            self.mandate_block.discard(anchor)
            # B-59: the timed (resolved-layer) twin of the two discards
            # above; a returning creature is a new object (CR 400.7).
            self.layers.forget_departed(anchor)
            self.damage_policies.pop(anchor, None)
            # 16e: a departing permanent drops every control entry keyed on
            # it — as CREATURE (the stolen card itself) or as ANCHOR (the
            # aura/source whose leaving ends the effect, CR 611.3's duration
            # reading for Enthralling Hold's missing Duration node).
            self._expire_control(creature=anchor, anchor=anchor)

    def _apply_etb_state(self, card: Handle) -> None:
        """Stamp the compiled EtBState node on a permanent the journal
        just saw ENTER the battlefield: the tapped flag and any initial
        counters (CR 614.1c — part of the entering state, not a trigger,
        so no TAP event is emitted and nothing is re-journalled; the
        move's own journal row already carries the entry). A card whose
        record is not registered has no declared entered state."""
        record = self.binder.records.get(self.world.cards[card].identity.oracle_id)
        if record is None:
            return
        for node in record.abilities:
            if not isinstance(node, EtBState):
                continue
            if node.condition is not None:
                # ZND-1e (CR 614.1c): gated entering state — "if this
                # creature entered the battlefield kicked ..." (Cragplate
                # Baloth's 4 +1/+1 counters). The judged handle is the
                # entering permanent itself and it is ALREADY on the
                # battlefield (this hook runs off the entry's journalled
                # row), so WAS_KICKED takes its PERMANENT lane: the answer
                # is bound to THIS entry's provenance — an entry from the
                # stack carries that cast's kick, a re-entry (blink
                # return, put-enter) or a token was never cast and reads
                # False. The counters below therefore never RE-apply on a
                # return (CR 400.7: the returning object was not kicked).
                from MTG_bot.core.executor.legality import ctx_for

                ctx = ctx_for(
                    self,
                    source=card,
                    controller=self.world.controller_of(card),
                    x_value=self.etb_x.get(card),
                )
                if not eval_filter(node.condition, card, ctx):
                    continue
            if node.tapped:
                self.world.cards[card].tapped = True
            for kind, quantity in node.initial_counters:
                # m21-fidelity (2026-10-29): "enters with X +1/+1 counters"
                # (Wildwood Scourge, the X hydras) — CR 614.1c, the count is
                # part of the entering state. X is the value the spell was cast
                # with (stack.cast records it in etb_x as the spell lands); an
                # object that entered without being cast has X 0 (CR 107.3g). A
                # negative result gives no counters (107.1b).
                from MTG_bot.core.executor.legality import ctx_for
                from MTG_bot.core.executor.quantity import resolve

                qctx = ctx_for(
                    self,
                    source=card,
                    controller=self.world.controller_of(card),
                    x_value=self.etb_x.get(card, 0),
                )
                n = quantity.value if isinstance(quantity, QConst) else max(0, resolve(quantity, qctx))
                if not n:
                    continue
                # CR 122.6: counters an object is given as it enters ARE counters
                # put on it, so a counter-placement replacement applies (Conclave
                # Mentor: "that many plus one"). Same consult and action run as the
                # PUT_COUNTER lane's drain (the action's referent is the entering
                # card, its COUNTER_COUNT register the entering count).
                repl = self.replacements.replacement_for_counter_placement(qctx, card, kind, n)
                if repl is not None:
                    inner = self._ctx(
                        source=repl.source,
                        controller=repl.controller,
                        bindings={"event": [card]},
                        decisions=(),
                    )
                    inner.event_counter_count = n
                    inner.replaced_seq = qctx.replaced_seq | {repl.seq}
                    self._run_effect(repl.action, inner)
                    continue
                counters = self.world.cards[card].counters
                counters[kind.name] = counters.get(kind.name, 0) + n

    # -------------------------------------------------------- 12b: triggers

    def attach_card(self, handle: Handle, compiled: object) -> int:
        """Bind the compiled record's TriggeredAbility nodes to a world
        card (CardRecord or CompileResult — the oracle-id bridge is
        identity-checked). Returns the number of triggers bound."""
        return self.binder.attach_card(handle, compiled)

    def attach_pool(self, pool: PoolCompile) -> int:
        """Register a PoolCompile by oracle id and attach every registered
        card already on the battlefield."""
        return self.binder.attach_pool(pool)

    def fire_triggers(self) -> int:
        """Drain the pending trigger queue (APNAP, Handle-tie-broken).
        Decisions arrive through the executor's stream (14b): may-offers
        hit the vocabulary-addressed lanes, nothing positional is consumed.
        Returns the number of firings."""
        self.binder.on_events()
        return self.binder.fire_all()

    # ------------------------------------ 16a: damage marks + state checks

    def mark_damage(self, card: Handle, n: int, deathtouch: bool = False) -> None:
        """Mark ``n`` damage on a card (CR 120.4). The mark STAYS — marked
        until the permanent leaves the battlefield (CR 120.6) or the cleanup
        step removes it (CR 514.2); destruction is the state-based check
        below, never the dealing of the damage itself. 16c: ``deathtouch``
        (CR 702.2b) — damage from a deathtouch source is LETHAL damage no
        matter the amount, so the flag rides the ledger for the SBA."""
        if n <= 0:
            return
        self.damage[card] = self.damage.get(card, 0) + n
        if deathtouch:
            self.damage_deathtouch.add(card)

    def _lethal_creatures(self) -> list[Handle]:
        """CR 704.5a + 704.3 read over the battlefield (Handle-sorted,
        ruling 5): a creature marked with damage >= its LIVE toughness dies
        unless it has indestructible (CR 702.12b); toughness <= 0 kills even
        an indestructible creature. A permanent with no toughness (lands,
        non-creature artifacts) is not a creature-side death at all."""
        dying: list[Handle] = []
        for player in self.world.player_order:
            for card in self.battlefield(player):  # CR 702.26b
                identity = self.world.cards[card].identity
                _power, toughness = self.ledger.effective_pt(
                    identity, card, self.world.cards[card].counters
                )
                if toughness is None:
                    continue
                if (
                    toughness <= 0
                    or (
                        self.damage.get(card, 0) >= toughness
                        or card in self.damage_deathtouch  # 16c CR 702.2b
                    )
                    and not (self.layers.keyword_of(card, Keyword.INDESTRUCTIBLE))
                ):
                    dying.append(card)
        return sorted(dying)

    def _cease_tokens(self) -> list[Handle]:
        """V35 (CR 704.5d: "If a token is in a zone other than the battlefield, it
        ceases to exist"; 111.7, 111.8). A dead, bounced or exiled token is not a
        card in a graveyard, hand or exile: it leaves the world, so graveyard counts
        and "target creature card from your graveyard" never see it. A token on the
        stack is not a thing in this engine (spell copies are not tokens). No journal
        row: ceasing to exist is not a zone change and triggers nothing. Returns the
        tokens removed (Handle-sorted)."""
        world = self.world
        gone: list[Handle] = []
        for player in world.player_order:
            for kind, zone in world.players[player].zones.items():
                if kind in (ZONE_BATTLEFIELD, ZONE_STACK):
                    continue
                for card in list(zone.entries):
                    if world.cards[card].identity.is_token:
                        zone.entries.remove(card)
                        gone.append(card)
        for card in gone:
            del world.cards[card]
            self.binder.handle_record.pop(card, None)
            self.attachments.pop(card, None)
        return sorted(gone)

    def _unattached_auras(self) -> list[Handle]:
        """CR 704.5q (16e): an Aura on the battlefield that isn't attached
        is put into its owner's graveyard. Attachment state is the
        executor's one ``attachments`` table (the IS_ATTACHED_TO_SOURCE
        oracle); the binder drops edges whose host left, so a MISSING edge
        is the unattached read. Detection is the ENCHANT keyword on the
        printed identity (the aura marker — equipment carry EQUIP and are
        NOT swept: an unattached Equipment legally stays on the
        battlefield, CR 301.5). The graveyard lands in the last
        controller's zone: the frozen world has no owner axis, the same
        documented stand-in the planeswalker-loyalty check uses."""
        world = self.world
        out: list[Handle] = []
        for player in world.player_order:
            for card in self.battlefield(player):  # CR 702.26b
                if "ENCHANT" not in world.cards[card].identity.keywords:
                    continue
                host = self.attachments.get(card)
                if (
                    host is None
                    or host not in world.cards
                    or world.zone_of(host).kind != ZONE_BATTLEFIELD
                ):
                    out.append(card)
        return sorted(out)

    def _zero_loyalty_walkers(self) -> list[Handle]:
        """r21a (CR 704.5h): planeswalkers on the battlefield with 0 or
        less loyalty. Damage is the SECOND path to zero next to the pay-
        ment path (which still runs its own immediate check in legality,
        because the generic counter verb deletes a zeroed key); a missing
        ledger key therefore reads the printed loyalty, never 0 — the
        13a ``_loyalty_of`` twin. V31 (CR 704.5i): the counter verb now keeps
        a zeroed LOYALTY key, so counter removal (Pestilent Haze) and a loyalty
        cost paid down to 0 reach this check too."""
        from MTG_bot.core.executor.legality import _loyalty_of

        world = self.world
        out: list[Handle] = []
        for player in world.player_order:
            for card in self.battlefield(player):  # CR 702.26b
                state = world.cards.get(card)
                if state is None or state.identity.loyalty is None:
                    continue
                if _loyalty_of(world, card) <= 0:
                    out.append(card)
        return sorted(out)

    def _state_checks(self) -> int:
        """The 16a state-based action sweep (CR 704.3: repeat until the
        table is stable), run at every settle point — the end of each
        public op. Lethal creatures die when the thing that hurt them
        finishes, not inside the damage atom (the 12a instant-lethal
        stand-in is retired). Each kill batch is journalled as its OWN atom
        boundary (cause ``None``: an SBA has no card behind it, coverage
        credits none) so dies-triggers see the C18 was-PT snapshot, then
        those firings drain before the next scan. r21a: the sweep is also
        the zero-loyalty planeswalker lane (CR 704.5h) — damage-driven
        walkers are buried here, the same graveyard-move SBA reading the
        frozen-world stand-in already uses for the other lanes."""
        fired = 0
        while True:
            # V35 (CR 704.5d, 111.7): a token off the battlefield ceases to exist.
            # Its leave triggers already fired (the drain before this sweep, or the
            # previous iteration's), as 111.7 says they do.
            self._cease_tokens()
            self.layers.recompute()  # live keywords/toughness must be current
            dying = self._lethal_creatures()
            unattached = self._unattached_auras()  # 16e CR 704.5q
            walkers = self._zero_loyalty_walkers()  # r21a CR 704.5h
            if not dying and not unattached and not walkers:
                return fired
            before = self.journal.snapshot()
            start = len(self.events)
            # r19b (Scorching Dragonfire): dies-window replacements consult
            # BEFORE the graveyard move (C24 replacement-before-apply, the
            # die-lane twin of the damage/life hooks in verbs.py). A matched
            # death is NOT moved — the record's ACTION (the exile) runs as
            # its own journalled atom in this iteration's drain below.
            # v1 GAP (documented): the consumed death emits no
            # BATTLEFIELD->GRAVEYARD diff, so events.py's KIND_CREATURE_DIES
            # never fires for a replaced death — dies-triggers stay silent
            # for it (the real CR 614.8 reading differs; no corpus card's
            # scenario depends on the pair yet, so this stays a flagged
            # stand-in, never a fake CREATURE_DIES row).
            replaced: list[tuple[Handle, ReplacementRecord]] = []
            for card in dying:
                repl = self.replacements.replacement_for_death(card)
                if repl is not None:
                    replaced.append((card, repl))
                    self.events.append(
                        (len(self.events), "STATE_CHECK", str(card), "DIES_REPLACED")
                    )
                    continue
                self.damage.pop(card, None)
                self.damage_deathtouch.discard(card)
                self.world.move_to_zone(
                    card, self.world.controller_of(card), ZONE_GRAVEYARD
                )
                self.events.append((len(self.events), "STATE_CHECK", str(card), "DIES"))
            for card in unattached:
                if card not in self.world.cards:
                    continue  # an aura killed in this same batch
                self.attachments.pop(card, None)
                self.world.move_to_zone(
                    card, self.world.controller_of(card), ZONE_GRAVEYARD
                )
                self.events.append(
                    (len(self.events), "STATE_CHECK", str(card), "UNATTACHED")
                )
            for card in walkers:
                if card not in self.world.cards:
                    continue  # a walker killed in this same batch
                if any(card == c for c, _repl in replaced):
                    continue  # a creature-walker whose death is already replaced
                # r21a: the zeroed LOYALTY key is DELETED on the way out
                # (generic-counter-verb convention): the battlefield re-
                # entry seeds via setdefault (binding.py 13a), and a stale
                # 0 would ride the re-entry into an instant second death.
                # An exile replacement below is a way out too.
                self.world.cards[card].counters.pop("LOYALTY", None)
                # B-62, CR 704.5i + 700.4: the zero-loyalty SBA puts the
                # walker into its owner's graveyard from the battlefield, so
                # it DIES and the dies-window replacements apply exactly as
                # in the lethal-creature lane above ("if that creature or
                # planeswalker would die this turn, exile it instead":
                # Obliterating Bolt, Scorching Dragonfire). The record's
                # filter decides which objects it covers.
                repl = self.replacements.replacement_for_death(card)
                if repl is not None:
                    replaced.append((card, repl))
                    self.events.append(
                        (len(self.events), "STATE_CHECK", str(card), "DIES_REPLACED")
                    )
                    continue
                self.damage.pop(card, None)
                self.damage_deathtouch.discard(card)
                self.world.move_to_zone(
                    card, self.world.controller_of(card), ZONE_GRAVEYARD
                )
                self.events.append(
                    (len(self.events), "STATE_CHECK", str(card), "ZERO_LOYALTY")
                )
            new_events = self.journal.record_atom(
                before, None, "STATE_CHECK", self.events[start:]
            )
            self._on_zone_changes(new_events)
            # r19b: drain the consumed deaths — each replacement's ACTION is
            # its OWN atom boundary (the _run_effect damage-lane pattern),
            # with the CR 614.4a guard on the inner ctx and the dead card
            # bound as the ``event`` referent its selector reads. The drain
            # runs BEFORE the trigger drain so no firing sees a limbo
            # creature still marked lethal on the battlefield.
            for card, repl in replaced:
                inner = self._ctx(
                    source=repl.source,
                    controller=repl.controller,
                    bindings={"event": [card]},
                    decisions=(),
                )
                inner.replaced_seq = frozenset({repl.seq})
                self._run_effect(repl.action, inner)
            self.binder.on_events()
            fired += self.binder.fire_all()

    def _settle(self) -> int:
        """Match the journal's new events and drain — the end of every
        public op. With nothing attached this is a no-op (12a behaviour).
        12d: the settle tail is also the recompute point — WHILE-condition
        truth is re-evaluated on the ledger, and the layer registry
        re-reads the set (new/lost members, condition toggles) and rebuilds
        the keyword / granted-ability oracles. All of it is pure function
        of the journal's final state, so replays are byte-identical."""
        self.binder.on_events()
        fired = self.binder.fire_all()
        # 16a: the state-based lethal-damage check sits at the settle point
        # (CR 704.3), so execute / apply_effect / end_turn all drain it.
        fired += self._state_checks()
        self.ledger.settle_while(self._while_eval)
        self.layers.recompute()
        return fired

    def _consume_end_turn(self) -> None:
        """13a: an END_TURN atom only SETS the request flag (mid-op state
        must not change under the atoms still running); the close happens at
        the op boundary through the ONE turn skeleton, so there is exactly
        one end-of-turn path (markers, sweeps, delayed-trigger expiry). A
        nested apply_effect (payment step, replacement action) consuming the
        flag first is harmless — the flag is single-shot."""
        if not self.end_turn_requested:
            return
        self.end_turn_requested = False
        if self.turn_open and not self._closing_turn:
            # Re-entrancy guard: a trigger fired BY the close may itself
            # request END_TURN; the turn is already closing, so that request
            # is consumed as a no-op rather than recursing.
            self._closing_turn = True
            try:
                self.end_turn()
            finally:
                self._closing_turn = False

    def _while_eval(self, change: object, meta: object) -> bool:
        """The ledger WHILE evaluator: the condition (a state predicate,
        StaticAbility convention) judged against the recording anchor in
        the recording controller's coordinates. An anchor that has left
        the world's card set can only be FALSE."""
        from MTG_bot.core.executor.durations import DurationMeta

        assert isinstance(meta, DurationMeta)
        if meta.anchor is None or meta.anchor not in self.world.cards:
            return False
        ctx = self._ctx(
            source=meta.anchor,
            controller=meta.controller if meta.controller is not None else meta.anchor,
            bindings=None,
            decisions=(),
        )
        assert meta.condition is not None
        return eval_filter(meta.condition, meta.anchor, ctx)

    # ------------------------------------------------- 12b/12d: turn skeleton
    #
    # The MINIMAL executor-owned turn: active rotation + world.turn clock +
    # the UNTAP STEP (12d) + phase markers. 16b adds the COMBAT phase
    # (:meth:`Executor.combat_step`, driven between the main-phase acts
    # and end_turn by the harness); the markers the frozen grammar has
    # triggers for: UPKEEP + FIRST_MAIN + COMBAT at the beginning of a
    # turn's work, END_TURN at the end of one. The untap step is a
    # RULE step, not an Atom: it mutates the
    # world directly and journalls one TapStateEvent per untap, so
    # "whenever a creature untaps" triggers and the fingerprint see it.

    def begin_turn(self, player: Handle) -> int:
        """Begin ``player``'s turn: active rotation, turn clock, the UNTAP
        step (12d), UPKEEP and FIRST_MAIN markers, per-turn event trackers
        reset; drains triggers. Returns the firing count."""
        if player not in self.world.players:
            raise ValueError(f"begin_turn: {player} is not a player of this world")
        if self._turn_started:
            self.world.turn += 1
        self._turn_started = True
        self.world.active_player = player
        self.turn_open = True
        # The UNTAP step has no grammar phase marker (Phase is the closed
        # {UPKEEP, FIRST_MAIN, COMBAT, END_TURN} vocab), so the clock sits
        # at UPKEEP across it — nothing can activate during a rule step.
        self.phase = Phase.UPKEEP.name
        self.journal.begin_turn(player)
        self._untap_step(player)
        # UNTIL_NEXT_TURN expiry: the recorded owner's turn is beginning —
        # the precise next-turn-start end the 12a ledger deferred (the
        # binder's DELAYED windows keep their documented Eot stand-in).
        self.ledger.expire_until_next_turn(player)
        self.layers.expire_until_next_turn(player)
        self.replacements.expire_until_next_turn(player)
        self.journal.record_turn_phase(Phase.UPKEEP.name)
        self.phase = Phase.UPKEEP.name
        # 14a: the DRAW step (CR 504.5-c), journalled INSIDE the skeleton so
        # 'whenever you draw' triggers and the fingerprint see it, and AFTER
        # the UPKEEP marker so beginning-of-upkeep triggers keep their CR
        # ordering ahead of draw triggers.
        self._turn_draw(player)
        self.journal.record_turn_phase(Phase.FIRST_MAIN.name)
        self.phase = Phase.FIRST_MAIN.name
        return self._settle()

    def _turn_draw(self, player: Handle) -> None:
        """The CR 504.5-c draw step of the active player (14a).

        The frozen grammar has no phase-marker draw — the DRAW *verb* is the
        corpus idiom (`library -> hand`), so the skeleton runs the shared
        :data:`_TURN_DRAW` atom inline through the same journalled path a
        card's own draw uses: the DRAW handler calls
        :meth:`GameWorld.draw` and the journal auto-detects the
        library->hand move as a MOVE_ZONE atom boundary.

        Two deliberate omissions, both the skeleton's existing discipline:
        no nested ``_settle`` (the turn has exactly ONE settle, the one at
        the tail of :meth:`begin_turn`, and a draw-armed trigger already
        drains there in clock order behind the UPKEEP marker) and no nested
        ``_consume_end_turn`` (an END_TURN requested by such a trigger
        closes at the next op boundary, never mid-skeleton). An empty
        library no-ops here (CR 121.2 through ``_v_draw``); CR 121.3's
        'draw from empty = loss' is a STATE CHECK, not a verb (13a ruling),
        and belongs to the caller's loss scan, not to this step.

        ``source`` is the seat: no permanent drew this card, and the
        journal's cause column records the seat, which is what
        a 'you drew' trigger's APNAP controller already is."""
        self._op_seq += 1
        ctx = self._ctx(source=player, controller=player, bindings=None, decisions=())
        # r22b: the draw-step window. _v_draw stamps draw_step_ordinal only
        # while this flag is open; NOT_FIRST_DRAW_THIS_STEP (Teferi's Ageless
        # Insight condition, quantity.py) answers per that register. Cleared
        # unconditionally — a draw-armed trigger firing later sees the
        # window shut (CR 504.5: the register is scoped to the step).
        self._draw_step_open = True
        self.draw_step_ordinal = {}
        try:
            self._run_effect(_TURN_DRAW, ctx)
        finally:
            self._draw_step_open = False

    def _untap_step(self, player: Handle) -> int:
        """The 12d untap step. Every tapped permanent the ACTIVE player
        controls untaps — except one a live PREVENT/UNTIL_NEXT_STEP record
        vetoes (Frost Breath's freeze; no defender-style exclusions exist
        pre-combat, and there are none in the frozen data for this step).
        APNAP note: untap is a simultaneous rule action, not a player
        choice — the Handle-sorted loop is the deterministic stand-in for
        the simultaneous replacement (documented, no player interaction
        is involved, so no APNAP ordering applies).
        AFTER the tick: UNTIL_NEXT_STEP(UNTAP) records are consumed by the
        step they just survived and terminal-expire — the freeze therefore
        survives EXACTLY one untap tick (pinned). Returns the untap count.

        CR 502.1 (2026-10-29): the phasing turn-based action comes FIRST, so
        a permanent that phases in here untaps in the same step (502.3); a
        permanent still phased out does not exist and does not untap."""
        world = self.world
        self._phasing_step(player)
        untapped = 0
        for card in sorted(world.cards):
            state = world.cards[card]
            if not state.tapped:
                continue
            if world.zone_of(card).kind != ZONE_BATTLEFIELD:
                continue
            if card in self.phased_out:  # CR 702.26b
                continue
            if self.controller_of(card) != player:  # 16e overlay-aware
                continue
            if self.replacements.prevents_untap(card):
                continue
            state.tapped = False
            self.journal.emit(KIND_TAP_STATE, card, None, "UNTAP_STEP", (False,))
            untapped += 1
        controller_of = self.controller_of
        self.replacements.expire_at_step(Step.UNTAP, player, controller_of)
        self.layers.expire_at_step(Step.UNTAP, player, controller_of)
        self.ledger.expire_at_step(Step.UNTAP, player, controller_of)
        return untapped

    # ------------------------------------------------- 16b: the COMBAT phase
    #
    # FIRST_MAIN -> COMBAT -> SECOND_MAIN -> END. R16-1 (doc /11): the
    # phase runs UNINTERRUPTED - no opponent response window (our instants
    # are own-turn-only by construction, so nothing illegal is claimed);
    # the CR 704.3 honesty is the SBA sweep at every settle point between
    # the damage steps and the phase hand-off. 16c ships the blocker step
    # (CR 509), the damage-assignment asks (CR 510), TRAMPLE, DEATHTOUCH
    # and the Herald AS_UNBLOCKED policy; the remaining documented v1
    # limit: planeswalker attack assignment (players only — the binary
    # attack ask names no attacked object and no corpus card needs a PW
    # attack, doc 14).
    # v1 limits, documented per the R16-1 mandate: no chain spells, no
    # flash responses.

    def combat_step(self, seat: Handle) -> int:
        """Run the active player's whole COMBAT phase (CR 506-511 v1):
        the beginning-of-combat marker (the Phase.COMBAT cards fire), the
        declare-attackers step (one binary ask per legal creature, whole-
        set validated, mandates narrowing the vocab), the declare-blockers
        step (CR 509: one ask per defending creature, candidates = the
        attackers it may legally block plus NONE, CR 509.1a untapped-only,
        whole-assignment validated), the combat damage step(s) with the
        first/double-strike split and the CR 510 assignment asks, and the
        end of combat. Returns the trigger-firing count. A creature with no
        legal declaration is never asked (it cannot attack); a mandatory
        attacker's ask is ATTACK-only (C15 - the policy is never offered
        an illegal answer)."""
        world = self.world
        if not self.turn_open:
            raise ValueError(f"combat_step: no turn is open ({seat})")
        if world.active_player != seat:
            raise ValueError(f"combat_step: {seat} is not the active player")
        opponents = [p for p in world.player_order if p != seat]
        if not opponents:
            raise ValueError(f"combat_step: {seat} has no defending player")
        self.defending_player = opponents[0]
        fired = 0
        # Beginning of combat (TurnPhaseEvent COMBAT - the BINDING 16b
        # feed: Battle-Rattle Shaman, Dire Fleet Warmonger, Adherent of
        # Hope, the Basri Ket / Liliana Waker emblems).
        self.journal.record_turn_phase(Phase.COMBAT.name)
        self.phase = Phase.COMBAT.name
        fired += self._settle()
        # Declare attackers (CR 508.1). The declare window stays open
        # across the post-declare settle so enters-attacking tokens the
        # attack triggers create JOIN the attack (CR 508.1i).
        self._op_seq += 1
        self._declare_group = self._op_seq
        self.declaring = True
        try:
            self._declare_attackers(seat)
            fired += self._settle()
        finally:
            self.declaring = False
        # Declare blockers (CR 509, 16c) - after the attack-trigger drain
        # (CR 508.3: the triggers resolve BEFORE the blocking player gets
        # the declaration duty), before any damage step.
        fired += self._declare_blockers(seat)
        # CR 509.4: the declare-blockers turn-based action ends, both
        # players get passes, and the BLOCK triggers (Snarespinner's
        # "blocks a creature with flying" pump, Gloom Sower's life swap,
        # Elder Gargaroth's choice) resolve BEFORE the combat damage step.
        fired += self._settle()
        # RUNG-2 (CR 506.4/510's first slice, 2026-10-05): the combat
        # INSTANT window — after declare-blockers and its settle, before
        # the damage step, both seats may answer the fight with a legal
        # instant (kill the blocker before it fights, pump the defender
        # over a lethal threshold, snipe the attacker). One round in
        # player order, no priority re-asks (the rung-1 narrowing); a
        # no-attacker combat has no declare-blockers or damage step, so
        # there is nothing to respond to and no ask is made (C15). The
        # cast's own settle removes dead creatures and folds pumped P/T
        # into the ledger BEFORE _combat_damage reads it.
        if self.attackers:
            open_combat_window(self)
        fired += self._combat_damage(seat)
        # End of combat: the settle is the R16-1 SBA pass; the attack
        # record closes with the phase (CR 506.4 - nothing "is attacking"
        # once combat ended, and IS_ATTACKING reads exactly that).
        fired += self._settle()
        self.attackers = []
        self.attacked = {}
        self.blocked_by = {}
        self.defending_player = None
        # V26 (CR 511.3: as the end of combat step ends, all creatures are removed
        # from combat): re-read the statics that select attacking or blocking
        # creatures ("Attacking creatures you control get +1/+0", Warded
        # Battlements) now that nothing is attacking; the last recompute ran inside
        # the settle above, while the attack record still stood.
        self.ledger.settle_while(self._while_eval)
        self.layers.recompute()
        # The frozen grammar's Phase vocab has no SECOND_MAIN member, so
        # the marker is executor-clock-only: the legality gates read the
        # phase string and correctly stop offering FIRST_MAIN activations.
        self.phase = "SECOND_MAIN"
        return fired

    def _declare_attackers(self, seat: Handle) -> None:
        """The CR 508.1 binary asks + the whole-set check, then the
        declaration commit: tap everything that declared except the
        vigilance carriers (CR 702.53a), journalled as TapState rows
        BEFORE the declare rows (a "becomes tapped" trigger sits UNDER
        the attack triggers, CR 508.1m), then one DECLARE_ATTACKERS row
        per attacker - shared declare-group id, the binder's CR 603.2
        dedup key. Tapped creatures are legal attackers (tapping to
        declare is not a cost); sickness reads the journal (legality.py).
        """
        world = self.world
        candidates = legal_attackers(self, seat)
        mandated = mandated_attackers(self, seat) & set(candidates)
        chosen: list[Handle] = []
        for card in candidates:
            # T5-F1 (§10): a MANDATED attacker (furor/must-attack) has a
            # one-word surface — not a decision. The phantom gate consumes
            # ATTACK silently and journals it; the pack/provider cannot
            # decline what CR forces, and no 1-candidate ask is billed.
            vocab = ("ATTACK",) if card in mandated else ("ATTACK", "DECLINE")
            ctx = self._ctx(source=card, controller=seat, bindings=None, decisions=())
            if offer_or_autopick(ctx, vocab, f"attack:{card}:{world.turn}") == "ATTACK":
                chosen.append(card)
        # Whole-set validation of the ASSEMBLED set. The asks mutate no
        # state, so re-deriving legality is a re-check and the mandate
        # inclusion was narrowed at the ask - either failure here is an
        # engine invariant violation, not a policy error to repair.
        legal_now = set(legal_attackers(self, seat))
        if not set(chosen) <= legal_now:
            raise RuntimeError(
                f"executor: declare-attackers set check failed for {seat} - "
                f"{[str(c) for c in chosen if c not in legal_now]} are not "
                "legal attackers"
            )
        if not mandated <= set(chosen):
            raise RuntimeError(
                f"executor: MANDATE_ATTACK violated - "
                f"{[str(c) for c in sorted(mandated - set(chosen))]} had to "
                "attack (asks were narrowed, this cannot happen)"
            )
        if not chosen:
            return
        defender = self.defending_player
        assert defender is not None  # combat_step opens the phase with one
        for card in chosen:
            self.attackers.append(card)
            self.attacked[card] = defender
            if self.layers.keyword_of(card, Keyword.VIGILANCE):
                continue
            world.cards[card].tapped = True
            self.journal.emit(KIND_TAP_STATE, card, None, "ATTACK_STEP", (True,))
        for card in chosen:
            self.journal.emit(
                KIND_DECLARE_ATTACKERS,
                card,
                None,
                "ATTACK_STEP",
                (self._declare_group,),
            )

    # ------------------------------------------------ 16c: declare blockers

    def _declare_blockers(self, seat: Handle) -> int:
        """CR 509 v1 (16c). ONE ask per defending creature that could legal-
        ly block at least one attacker, Handle-sorted (C16), site
        ``block:<card>:<turn>``: the vocabulary is the attackers that perma-
        nent may block (CR 509.1a untapped-only, CR 509.1b one attacker per
        blocker, reach/menace/protection and the PREVENT_EFFECT restrictions
        — Tome Anima "can't be blocked", Pirate "can't block", Shacklegeist
        "can block only creatures with flying", Subira's activated target)
        plus the NONE option. /115 (seed 1269): a word is offered ONLY
        when committing it keeps the WHOLE assignment completable — a
        bipartite match exists assigning the not-yet-asked candidates so
        every menace attacker ends at 0 or 2+ blockers (CR 702.113) and
        every must-be-blocked attacker ends blocked (CR 509.1h); NONE is
        offered under exactly the same test. The old gate counted
        remaining CANDIDATES instead of pair-LEGAL completions and so
        offered a lone blocker the menace word no later blocker could
        legally pair behind. A blocker with NO completable word is
        skipped silently (no ask, no phantom); a must-block attacker it
        can still legally take is salvaged instead. Never dropped when
        the answer would merely be inadvisable (C15). Tapped/defender
        creatures are never asked; a
        creature legal against nothing is never asked. Each committed pair
        emits one DECLARE_BLOCKERS row (subject = the blocker — the
        DeclareBlockersEvent feed: filter/subject read the blocker, blocked
        reads the attacker; BecomesBlockedEvent answers the same rows for
        the blocked-side source). The settle after the step drains the
        block triggers (Elder Gargaroth's choice, Snarespinner's +2/+0)
        before any damage step (CR 509.4)."""
        world = self.world
        defender = self.defending_player
        attackers = self._live_attackers(seat)
        if defender is None or not attackers:
            return 0
        assigned: dict[Handle, list[Handle]] = {}
        candidates = sorted(
            card
            for card in sorted(world.cards)
            if self.controller_of(card) == defender
            and world.zone_of(card).kind == ZONE_BATTLEFIELD
            and blocker_askable(self, card, attackers)
        )
        if not candidates:
            return 0
        mandated = mandated_to_be_blocked(self) & set(attackers)
        by_word = {str(a): a for a in attackers}
        # /115 (seed 1269): the pair matrix is precomputed once — asks
        # mutate no state, so the legality picture is fixed for the step.
        pair_ok: dict[Handle, set[Handle]] = {
            blocker: {
                attacker
                for attacker in attackers
                if block_pair_blocked_reason(self, blocker, attacker) is None
            }
            for blocker in candidates
        }
        menace = {
            attacker
            for attacker in attackers
            if self.layers.keyword_of(attacker, Keyword.MENACE)
        }

        def completable(
            partial: dict[Handle, list[Handle]], tail: list[Handle]
        ) -> bool:
            """CR-legal completion exists: can every candidate still
            uncommitted (this blocker's tail included) still be assigned
            or held so that each menace attacker ends at 0 or 2+ blockers
            and every mandated attacker ends blocked? Reduced to bipartite
            matching (Kuhn): an unassigned mandated non-menace attacker
            demands ONE slot, a mandated menace at 0 demands TWO, an
            in-progress menace demands its SECOND; free slots absorb the
            rest."""
            need: dict[Handle, int] = {}
            for attacker in attackers:
                count = len(partial.get(attacker, ()))
                if attacker in mandated and count == 0:
                    need[attacker] = 2 if attacker in menace else 1
                elif attacker in menace and count == 1:
                    need[attacker] = 1
            slots = [attacker for blocker in tail for attacker in pair_ok[blocker]]
            for attacker, quota in need.items():
                if slots.count(attacker) < quota:
                    return False
            match: dict[Handle, Handle] = {}  # attacker -> matched blocker
            reach: set[Handle] = set()

            def augment(attacker: Handle) -> bool:
                for blocker in tail:
                    if blocker in reach or attacker not in pair_ok[blocker]:
                        continue
                    reach.add(blocker)
                    if blocker not in match:
                        match[blocker] = attacker
                        return True
                    if augment(match[blocker]):
                        match[blocker] = attacker
                        return True
                return False

            for attacker, quota in need.items():
                for _ in range(quota):
                    reach.clear()
                    if not augment(attacker):
                        return False
            return True

        asked: set[Handle] = set()
        skipped: set[Handle] = set()
        for position, blocker in enumerate(candidates):
            tail = candidates[position + 1 :]
            legal = [
                attacker
                for attacker in attackers
                if attacker in pair_ok[blocker]
                and completable(
                    {**assigned, attacker: [*assigned.get(attacker, []), blocker]},
                    tail,
                )
            ]
            forced = [
                attacker
                for attacker in legal
                if attacker in mandated and not assigned.get(attacker)
            ]
            if forced:
                vocab = tuple(str(a) for a in forced)
            else:
                words = [str(a) for a in legal]
                if completable(assigned, tail):
                    words.append("NONE")
                vocab = tuple(words)
                if not words:
                    # No word for this blocker: nothing it could do keeps
                    # the assignment CR-completable. Salvage first — a
                    # mandated attacker it can legally take, if any.
                    salvage = [
                        attacker
                        for attacker in attackers
                        if attacker in pair_ok[blocker]
                        and attacker in mandated
                        and not assigned.get(attacker)
                        and attacker not in menace
                    ]
                    if salvage:
                        vocab = tuple(str(a) for a in salvage)
                    else:
                        # Silent skip: no ask, no assignment, no journal
                        # row. The blocker simply has no legal voice in
                        # this step (seed 1269's lone blocker vs menace).
                        skipped.add(blocker)
                        continue
            asked.add(blocker)
            ctx = self._ctx(
                source=blocker, controller=defender, bindings=None, decisions=()
            )
            # T5-F1 (§10): the menace/must-block narrowing can leave ONE
            # legal pair with no NONE word — a forced block is consumed by
            # the phantom gate, not presented as a decision.
            answer = offer_or_autopick(ctx, vocab, f"block:{blocker}:{world.turn}")
            if answer == "NONE":
                continue
            attacker = by_word[answer]
            reason = block_pair_blocked_reason(self, blocker, attacker)
            if reason is not None:
                raise RuntimeError(
                    f"executor: declare-blockers committed an illegal pair "
                    f"{blocker} -> {attacker}: {reason} (asks mutate no state, "
                    "so this is an engine bug, not a policy answer)"
                )
            assigned.setdefault(attacker, []).append(blocker)
        # Whole-assignment validation (asks mutate nothing, so re-deriving
        # legality is a re-check; a violation is an engine invariant breach).
        for attacker, blockers in assigned.items():
            if self.layers.keyword_of(attacker, Keyword.MENACE) and len(blockers) < 2:
                raise RuntimeError(
                    f"executor: menace attacker {attacker} was blocked by "
                    f"exactly one creature {[str(b) for b in blockers]} "
                    "(CR 702.113 — the ask narrowing should have prevented "
                    "this)"
                )
        for attacker in mandated:
            if assigned.get(attacker):
                continue
            assignable = {
                card
                for card in asked
                if block_pair_blocked_reason(self, card, attacker) is None
            }
            free = assignable - {b for bs in assigned.values() for b in bs}
            # /115 menace-aware: a mandated MENACE attacker is only
            # "assignable" where TWO free blockers exist — one free
            # blocker is not a violated mandate, it is CR 702.113 making
            # the mandate unfulfillable (must-block reads "if able").
            need = 2 if attacker in menace else 1
            if len(free) >= need:
                raise RuntimeError(
                    f"executor: MANDATE_BLOCK violated - {attacker} had to be "
                    f"blocked and {len(free)} free legal blocker"
                    f"s existed (need {need})"
                )
        fired = 0
        for attacker in sorted(assigned):
            for blocker in assigned[attacker]:
                self.blocked_by.setdefault(attacker, []).append(blocker)
                self.journal.emit(
                    KIND_DECLARE_BLOCKERS,
                    blocker,
                    None,
                    "BLOCK_STEP",
                    (attacker, self._declare_group),
                )
        return fired

    def join_attack(self, creature: Handle) -> None:
        """CR 508.1i - a creature PUT ONTO THE BATTLEFIELD ATTACKING
        (Falconer Adept's Bird, Basri Ket's [-2] Soldier) joins the open
        attack record with its own declare row, no legality pass (it was
        never declared). Outside the declare window the verb path never
        calls this."""
        if self.defending_player is None or creature in self.attackers:
            return
        self.attackers.append(creature)
        self.attacked[creature] = self.defending_player
        self.journal.emit(
            KIND_DECLARE_ATTACKERS,
            creature,
            None,
            "ATTACK_STEP",
            (self._declare_group,),
        )

    def _live_attackers(self, seat: Handle) -> list[Handle]:
        """The attack record minus anything that left or changed sides -
        SBA-swept attackers simply stop existing for the next step."""
        world = self.world
        return [
            card
            for card in self.attackers
            if card in world.cards
            and world.zone_of(card).kind == ZONE_BATTLEFIELD
            and self.controller_of(card) == seat
        ]

    def _combat_damage(self, seat: Handle) -> int:
        """CR 702.7/702.8 first-strike / double-strike split. If anything
        ATTACKING OR BLOCKING has first or double strike there is a FIRST
        COMBAT DAMAGE STEP for the FS union DS carriers, then the settle's
        SBA sweep (a killer first strike buries its victim before the
        normal step), then the NORMAL step for the non-FS dealers plus the
        surviving DS carriers. 16c: the dealer set is BOTH SIDES of the
        attack (CR 510.1a — blockers assign to the attacker they blocked,
        in the same simultaneous step; the 16b attacker-only wave is
        superseded). Every damage atom is the 16a DEAL_DAMAGE funnel -
        the C24 replacement site intercepts (Nine Lives reads combat damage
        exactly like any other), marks ride the ledger, lethality is the
        settle's SBA. Each dealer's assignment obeys CR 510 (below) -
        blockers first up to lethal, TRAMPLE excess by asked partition,
        the Herald policy able to route it past blockers as though
        unblocked."""
        dealers = self._combat_dealers()

        def live(items: list[Handle]) -> list[Handle]:
            return [
                h
                for h in items
                if h in self.world.cards
                and self.world.zone_of(h).kind == ZONE_BATTLEFIELD
            ]

        first = {h for h in dealers if self.layers.keyword_of(h, Keyword.FIRST_STRIKE)}
        doubled = {
            h for h in dealers if self.layers.keyword_of(h, Keyword.DOUBLE_STRIKE)
        }
        fired = 0
        if first or doubled:
            fired += self._damage_wave(seat, sorted(first | doubled))
            dealers = live(dealers)  # a first-strike kill removes the dealer
        normal = [h for h in dealers if h not in first or h in doubled]
        fired += self._damage_wave(seat, sorted(normal))
        return fired

    def _combat_dealers(self) -> list[Handle]:
        """Everyone assigning combat damage: the live attackers plus every
        live blocker (a creature blocks exactly one attacker, CR 509.1b,
        so its recipient is determined; a multi-blocker pile contributes
        each blocker once)."""
        out = set(self.attackers)
        for blockers in self.blocked_by.values():
            out.update(blockers)
        return sorted(
            h
            for h in out
            if h in self.world.cards and self.world.zone_of(h).kind == ZONE_BATTLEFIELD
        )

    def _assign_damage(
        self, dealer: Handle, power: int, controller: Handle
    ) -> tuple[tuple[int, Handle], ...]:
        """CR 510.1 v1 (16c): one dealer's legal assignment announcement.

        * UNBLOCKED: everything to the ATTACKED object (v1: the defending
          player — planeswalker attacking is the documented players-only
          boundary, doc 14).
        * BLOCKED, but every blocker has left combat (B-61): the creature
          is still blocked (CR 509.1h), so it assigns NO combat damage
          (CR 510.1c), unless it has trample, which assigns all of it to
          the attacked object (CR 702.19e); the Herald policy below may
          still route it there. A double striker whose first-strike damage
          killed its blocker is the common case.
        * Herald policy (Garruk, Savage Herald's −7 grant, AS_UNBLOCKED):
          "you may have this creature assign its combat damage as though it
          weren't blocked" — an ASK (the "may"), site
          ``policy:<card>:<turn>``, vocabulary AS_BLOCKED/UNBLOCKED. The
          creature REMAINS blocked (the block triggers already fired and
          stand; CR 506.5a-style blocked status is untouched) — the policy
          only reroutes the ASSIGNMENT.
        * Multiple blockers: the ORDER is asked per attacker (site
          ``order:<card>:<turn>``) as a POSITIONAL pick from the Handle-
          sorted remaining candidates at each slot — the exact decision
          surface of the permutation index, with a ≤n-word vocabulary at
          every ask (a literal 6-permutation cap would raise inside live
          games at the 4th blocker: the gate demands zero crashes).
        * LETHAL per blocker is toughness-minus-marked (CR 704.2, the
          marked ledger keeps the first-strike step's scars) or 1 from a
          DEATHTOUCH dealer (CR 702.2b).
        * TRAMPLE (CR 702.9): once every blocker is covered lethal, the
          excess is asked RECIPIENT BY RECIPIENT in order — each blocker
          gets ``trample:<card>:<slot>:<turn>`` from 0..remaining, the
          defending player takes the rest (the composition space of the
          announcement, enumerated with ≤(excess+1)-word vocabularies).
        * Without trample the whole damage must hit the blockers: greedy
          lethal-first in order, the final survivor soaking any excess.
        """
        world = self.world
        defender = self.defending_player
        assert defender is not None  # combat_step opens the phase with one
        if dealer not in self.attackers:
            # 16c blocker-side dealer: a blocker assigns to the ONE attacker
            # it blocked (CR 510.1a). If that attacker has already left
            # combat (a first-strike kill), the blocker deals NOTHING -
            # there is no trample-style carryover for a blocker whose
            # prey is gone (CR 510.1, absent an attacking-object reading).
            blocked = next(
                (a for a, bs in self.blocked_by.items() if dealer in bs), None
            )
            if (
                blocked is None
                or blocked not in world.cards
                or world.zone_of(blocked).kind != ZONE_BATTLEFIELD
            ):
                return ()
            return ((power, blocked),)
        attacked = self.attacked.get(dealer, defender)
        if dealer not in self.blocked_by:
            return ((power, attacked),)  # unblocked
        # B-61, CR 509.1h: the blocked_by entry outlives its blockers (a
        # departing blocker is removed from the list, the key stays), so an
        # empty live list here still means BLOCKED.
        blockers = [
            b
            for b in self.blocked_by[dealer]
            if b in world.cards and world.zone_of(b).kind == ZONE_BATTLEFIELD
        ]
        if not blockers and self.layers.keyword_of(dealer, Keyword.TRAMPLE):
            return ((power, attacked),)  # CR 702.19e: all of it tramples over
        as_unblocked = (
            self.layers.policy_as_unblocked(dealer)
            or self.damage_policies.get(dealer) == "AS_UNBLOCKED"
        )
        if as_unblocked:
            ctx = self._ctx(
                source=dealer,
                controller=controller,
                bindings=None,
                decisions=(),
            )
            if (
                ctx.take_decision(
                    ("AS_BLOCKED", "UNBLOCKED"), f"policy:{dealer}:{world.turn}"
                )
                == "UNBLOCKED"
            ):
                return ((power, attacked),)
        if not blockers:
            # B-61, CR 510.1c: blocked with no creature blocking it, no
            # trample: it assigns no combat damage. Before the fix this
            # case sent the whole damage to the player.
            return ()
        ordered = list(blockers)
        if len(ordered) > 1:
            picked: list[Handle] = []
            remaining = sorted(ordered)
            for slot in range(len(ordered)):
                vocab = tuple(str(i) for i in range(len(remaining)))
                ctx = self._ctx(
                    source=dealer,
                    controller=controller,
                    bindings=None,
                    decisions=(),
                )
                # T5-F1 (§10): the LAST slot has exactly one remaining
                # creature — the phantom gate consumes the trivial "0"
                # instead of asking for the obvious.
                answer = offer_or_autopick(
                    ctx, vocab, f"order:{dealer}:{slot}:{world.turn}"
                )
                chosen = remaining[int(answer)]
                picked.append(chosen)
                remaining.remove(chosen)
            ordered = picked
        deathtouch = self.layers.keyword_of(dealer, Keyword.DEATHTOUCH)

        def lethal_of(b: Handle) -> int:
            if deathtouch:
                return 1  # CR 702.2b: any nonzero damage from the source
            _p, toughness = self.ledger.effective_pt(
                world.cards[b].identity, b, world.cards[b].counters
            )
            return max(1, (toughness or 1) - self.damage.get(b, 0))

        if not self.layers.keyword_of(dealer, Keyword.TRAMPLE):
            plan: list[tuple[int, Handle]] = []
            left = power
            for b in ordered:
                share = min(lethal_of(b), left)
                if share:
                    plan.append((share, b))
                left -= share
                if left == 0:
                    break
            if left:  # no trample: the last blocker absorbs the excess
                plan[-1] = (plan[-1][0] + left, plan[-1][1])
            return tuple(plan)
        needs = [lethal_of(b) for b in ordered]
        covered = sum(needs)
        if power <= covered:  # not enough to reach lethal everywhere: greedy
            plan = []
            left = power
            for b, need in zip(ordered, needs):
                share = min(need, left)
                if share:
                    plan.append((share, b))
                left -= share
            return tuple(plan)
        plan = [(need, b) for b, need in zip(ordered, needs) if need]
        excess = power - covered
        for slot, b in enumerate(ordered):
            if excess == 0:
                break
            vocab = tuple(str(v) for v in range(excess + 1))
            ctx = self._ctx(
                source=dealer, controller=controller, bindings=None, decisions=()
            )
            give = int(
                ctx.take_decision(vocab, f"trample:{dealer}:{slot}:{world.turn}")
            )
            if give:
                # MERGE into the blocker's lethal entry (never a duplicate
                # recipient row - one announcement line per receiver)
                for i, (a, h) in enumerate(plan):
                    if h == b:
                        plan[i] = (a + give, b)
                        break
                else:
                    plan.append((give, b))
                excess -= give
        if excess:
            plan.append((excess, attacked))
        # CR 510.1: damage assignment is simultaneous within the step; the
        # canonical row order keeps the journal deterministic.
        return tuple(sorted(plan, key=lambda p: (p[1].namespace, p[1].index)))

    def _damage_wave(self, seat: Handle, dealers: list[Handle]) -> int:
        """One combat-damage substep: EVERY dealer's legal assignment is
        announced first (CR 510.1: all announcements, then all damage —
        nothing a later dealer's ask could read has mutated yet), then the
        atoms run inside ONE op boundary (simultaneous, CR 506/510 — no
        trigger can intervene between two attackers), each dealer's atoms
        journalled under ITS OWN cause (16a attribution fix), each damage-
        bearing dealer emits ONE COMBAT_DAMAGE row carrying the whole as-
        signment (CR 603.2: one "deals combat damage" event per dealer,
        however it splits), and the settle after the wave is the step's SBA
        + trigger drain. CR 120.7: a 0-power attacker deals no damage at
        all — no life change, no DAMAGE row, no combat-damage event."""
        defender = self.defending_player
        assert defender is not None
        strikes: list[tuple[Handle, tuple[tuple[int, Handle], ...]]] = []
        for dealer in dealers:
            identity = self.world.cards[dealer].identity
            power, _toughness = self.ledger.effective_pt(
                identity, dealer, self.world.cards[dealer].counters
            )
            if not power or power < 0:
                # 0, a negative, or an unmaterialized * : CR 120.7 - not
                # dealt at all. The negative lane became REACHABLE with the
                # Rung-2 combat window (a -X/-X instant cast between the
                # declaration and the damage step can push a dealer's
                # effective power below zero); damage is never negative.
                continue
            plan = self._assign_damage(dealer, power, self.controller_of(dealer))
            if not plan:
                # 16c: a blocker whose attacker left combat deals nothing -
                # no damage, no COMBAT_DAMAGE event (CR 120.7's reading).
                continue
            strikes.append((dealer, plan))
        if not strikes:
            return 0
        self._op_seq += 1
        self._combat_wave_open = True
        try:
            for dealer, plan in strikes:
                for amount, recipient in plan:
                    ctx = self._ctx(
                        source=dealer,
                        controller=self.controller_of(dealer),
                        bindings={"target": recipient},
                        decisions=(),
                    )
                    self._run_effect(_combat_damage_atom(amount, recipient), ctx)
        finally:
            self._combat_wave_open = False
        for dealer, plan in strikes:
            self.journal.emit(
                KIND_COMBAT_DAMAGE,
                dealer,
                dealer,
                "COMBAT_DAMAGE",
                (plan,),
            )
        return self._settle()

    def advance_turn(self) -> int:
        """End the active turn (if one is open) and begin the next one.

        CR 500.7: extra turns are added directly after the turn they were
        created in, the most recently created first (EXTRA_TURN pushes onto
        the front of ``extra_turn_queue``), so a pending extra turn is
        popped before the round-robin. The round-robin itself continues
        from the last NORMAL turn's seat (``normal_turn_seat``): after
        p1's extra turn inserted into p0's turn comes p1's own turn, not
        p0's. The open turn is closed FIRST, so an extra turn created in
        its end step is the next turn too. Returns the combined firings.

        ``normal_turn_seat`` is not folded into :meth:`state_fingerprint`:
        it is a function of the folded history (the EXTRA_TURN rows and
        the journal's turn markers), like ``starting_life``."""
        order = self.world.player_order
        if self.world.active_player is None or not self._turn_started:
            nxt = order[0]
        else:
            if self.turn_open:
                # An END_TURN atom already closed the turn inside the op —
                # never emit a second END_TURN marker for it.
                self.end_turn()
            if self.extra_turn_queue:
                if self.normal_turn_seat is None:
                    # The extras follow the first turn, a normal turn.
                    self.normal_turn_seat = self.world.active_player
                nxt = self.extra_turn_queue.pop(0)
            else:
                base = self.normal_turn_seat
                if base is None:
                    base = self.world.active_player
                assert base is not None
                nxt = order[(order.index(base) + 1) % len(order)]
                self.normal_turn_seat = nxt
        return self.begin_turn(nxt)

    def end_turn(self) -> int:
        """END_TURN marker FIRST (end-step triggers see the pre-expiry
        state), trigger drain, THEN the end-of-turn expiry sweep: Eot
        ledger entries, Eot-tagged LAYER records (12d: until-end-of-turn
        grants die here) and Eot-tagged PREVENTION records, and the
        turn-window delayed triggers (C22). Returns the firing count."""
        self.phase = Phase.END_TURN.name
        self.turn_open = False
        self.journal.record_turn_phase(Phase.END_TURN.name)
        fired = self._settle()
        self.ledger.sweep_at_eot()
        self.layers.sweep_at_eot()
        self.replacements.sweep_at_eot()
        self._expire_control(eot=True)  # 16e: Traitorous Greed's DurationEot
        self.damage.clear()  # 16a: CR 514.2 — cleanup removes marked damage
        self.damage_deathtouch.clear()  # 16c: the deathtouch flag rides along
        self.binder.expire_delayed()
        # Rebuild the oracles after the sweep — a granted keyword that
        # expired at end of turn must not survive into next turn's
        # keyword_of/legal_activations.
        self.layers.recompute()
        return fired

    # ---------------------------------------------------- 13c emblem / attach

    def get_emblem(self, owner: Handle, emblem: CardRecord) -> Handle | None:
        """Grant ``owner`` their emblem (CR 113.7). Returns the synthetic
        handle, or ``None`` when the owner ALREADY has this emblem (a
        second copy does nothing — the idempotence gate, visible as the
        duplicate event row in the verb handler). The emblem is executor
        replayed state, not a world card: its triggers bind to the owner
        through the binder, its statics anchor to the owner in the layer
        registry, and both are folded into the fingerprint."""
        key = (owner, emblem.oracle_id)
        if key in self.emblems:
            return None
        handle = Handle("emblem", self._emblem_seq)
        self._emblem_seq += 1
        self.emblems[key] = handle
        self.binder.bind_emblem(handle, emblem, owner)
        self.layers.recompute()  # emblem statics are live the moment it lands
        return handle

    def attach_aura(self, aura: Handle, host: Handle) -> None:
        """Record that ``aura`` (equipment/aura permanent) is attached to
        ``host`` — the API half of the IS_ATTACHED_TO_SOURCE oracle (the
        corpus has no enchantment/equipment cast surface in v1, so
        attachment is an explicit op, replayed and fingerprint-folded;
        CR 303.4-style leave-detachment is automatic in the binder)."""
        if aura not in self.world.cards or host not in self.world.cards:
            raise ValueError(
                f"attach_aura: both ends must be world cards ({aura}, {host})"
            )
        if aura == host:
            raise ValueError(f"attach_aura: {aura} cannot attach to itself")
        self.attachments[aura] = host
        self.layers.recompute()  # "equipped creature" scopes re-read the table

    # ------------------------------------------------ CR 702.26 phasing

    def battlefield(self, player: Handle) -> list[Handle]:
        """The permanents that exist on ``player``'s battlefield, in zone
        order: the zone's entries minus the phased-out ones (CR 702.26b, a
        phased-out permanent is treated as though it does not exist). The
        executor's own battlefield sweeps read this; every selector and
        query enumeration filters through ``selectors.enumerate_zone``."""
        entries = self.world.players[player].zone(ZONE_BATTLEFIELD).entries
        if not self.phased_out:
            return list(entries)
        return [card for card in entries if card not in self.phased_out]

    def phase_out(self, handles: Sequence[Handle]) -> list[Handle]:
        """Phase out ``handles`` (CR 702.26b): each permanent among them that
        exists on the battlefield gets the phased-out status, recorded with
        the player who controls it now (CR 502.1: it phases in during that
        player's next untap step). Not a zone change (702.26d): the card
        keeps its zone, counters, tapped state, attachments and control, a
        token stays, and no zone-change trigger sees it. Auras and Equipment
        attached to it phase out with it, indirectly (702.26g; 702.26h: an
        object phasing out both ways phases out indirectly), and every one
        of them is removed from combat (506.4). Returns the permanents that
        phased out directly, Handle-sorted."""
        world = self.world
        direct = sorted(
            {
                card
                for card in handles
                if card.namespace == "card"
                and card in world.cards
                and world.zone_of(card).kind == ZONE_BATTLEFIELD
                and card not in self.phased_out
            }
        )
        if not direct:
            return []
        indirect: dict[Handle, Handle] = {}
        frontier = list(direct)
        while frontier:
            host = frontier.pop(0)
            for attached, attached_to in sorted(self.attachments.items()):
                if (
                    attached_to == host
                    and attached not in indirect
                    and attached not in self.phased_out
                    and attached in world.cards
                    and world.zone_of(attached).kind == ZONE_BATTLEFIELD
                ):
                    indirect[attached] = host
                    frontier.append(attached)
        directly = [card for card in direct if card not in indirect]
        for card in directly:
            self.phased_out[card] = (self.controller_of(card), None)
        for attached, host in indirect.items():
            self.phased_out[attached] = (self.controller_of(attached), host)
        gone = set(directly) | set(indirect)
        self._remove_from_combat(gone)
        self.events.append(
            (len(self.events), "PHASE_OUT", tuple(str(card) for card in sorted(gone)))
        )
        self.layers.recompute()
        return directly

    def _remove_from_combat(self, cards: set[Handle]) -> None:
        """CR 506.4: the permanents stop attacking and blocking. An attacker
        whose blocker left stays blocked (CR 509.1h): its entry keeps its
        key, the same rule ``_on_zone_changes`` applies to a departure."""
        if not cards:
            return
        self.attackers = [card for card in self.attackers if card not in cards]
        for card in cards:
            self.attacked.pop(card, None)
            self.blocked_by.pop(card, None)
        for blockers in self.blocked_by.values():
            blockers[:] = [card for card in blockers if card not in cards]

    def _phasing_step(self, player: Handle) -> list[Handle]:
        """CR 502.1 / 702.26a, the first turn-based action of ``player``'s
        untap step: every permanent that phased out under ``player``'s
        control phases in (702.26c); one that phased out indirectly comes
        back with the permanent it is attached to, never by itself
        (702.26g). The other half of 502.1, permanents WITH phasing phasing
        out, has no carrier: no card in the pools has the phasing keyword.
        Nothing can stop a phase-in here yet: Teferi, Timeless Voyager's
        "they can't phase in" compiles to a ZoneChangeEvent that a status
        change never produces (docs/BACKLOG.md). Returns what phased in."""
        returning = sorted(
            card
            for card, (controller, host) in self.phased_out.items()
            if host is None and controller == player
        )
        back: list[Handle] = []
        for card in returning:
            queue = [card]
            while queue:
                current = queue.pop(0)
                if self.phased_out.pop(current, None) is None:
                    continue
                back.append(current)
                queue.extend(
                    sorted(
                        attached
                        for attached, (_controller, host) in self.phased_out.items()
                        if host == current
                    )
                )
        if back:
            self.events.append(
                (len(self.events), "PHASE_IN", tuple(str(card) for card in back))
            )
            self.layers.recompute()
        return back

    # -------------------------------------------------- 16e control overlay

    def controller_of(self, handle: Handle) -> Handle:
        """The EFFECTIVE controller of a card (16e): the GAIN_CONTROL
        overlay wins over the zone-owner read. OWNER-semantic call sites
        (graveyard/exile destination, owner-of-source, library to search)
        keep reading ``world.controller_of`` — a stolen permanent still
        dies to its owner's graveyard (CR 400.7e)."""
        override = self.control_overlay.get(handle)
        return override if override is not None else self.world.controller_of(handle)

    def gain_control(
        self,
        creature: Handle,
        controller: Handle,
        tag: str,
        anchor: Handle | None = None,
    ) -> bool:
        """Record one GAIN_CONTROL application (the verb handler's write
        side). ``tag`` is the duration_tag vocabulary: "Eot" rows sweep at
        end_turn, "Permanent"/"Anchor" rows ride until their ``anchor``
        permanent (or the creature itself) leaves the battlefield. Returns
        whether the EFFECTIVE controller actually changed (the handler's
        journal row and the CR 506.4a combat removal key on it)."""
        self.control_entries.append(
            (
                self._control_seq,
                creature,
                controller,
                tag,
                anchor,
                self.world.turn,
            )
        )
        self._control_seq += 1
        return self._recompute_control()

    def _expire_control(
        self,
        *,
        creature: Handle | None = None,
        anchor: Handle | None = None,
        eot: bool = False,
    ) -> bool:
        """Drop matching entries and re-derive (leave expiry + EoT sweep).
        Returns whether any effective controller changed."""
        before = len(self.control_entries)
        self.control_entries = [
            entry
            for entry in self.control_entries
            if not (
                (creature is not None and entry[1] == creature)
                or (anchor is not None and entry[4] == anchor)
                or (eot and entry[3] == "Eot")
            )
        ]
        return (
            self._recompute_control() if len(self.control_entries) != before else False
        )

    def _recompute_control(self) -> bool:
        """Rebuild the derived overlay and sickness clock from the live
        entries; report whether ANY effective controller changed. CR 506.4a:
        a permanent changing controllers during combat is removed from
        combat — attackers, attacked record, and every block edge. The
        sickness clock takes the EARLIEST live turn under the winning
        controller (two stacked entries for the same controller never
        re-inflict summoning sickness)."""
        prev = self.control_overlay
        overlay: dict[Handle, Handle] = {}
        gained: dict[Handle, int] = {}
        for _seq, creature, controller, _tag, _anchor, turn in self.control_entries:
            if overlay.get(creature) == controller:
                gained[creature] = min(gained[creature], turn)
            else:
                gained[creature] = turn
            overlay[creature] = controller
        self.control_overlay = overlay
        changed = [
            c
            for c in sorted(set(prev) | set(overlay), key=str)
            if prev.get(c) != overlay.get(c)
        ]
        # CR 302.6: every CHANGE of effective controller starts a fresh
        # continuous-control period NOW (a returned owner is a new period
        # too — the journal ZONE_CHANGE path cannot see control changes,
        # so the marker dict carries both directions).
        for creature in changed:
            gained[creature] = self.world.turn
        self.control_gained_turn = gained
        for creature in changed:
            if creature in self.attackers:
                self.attackers.remove(creature)
            self.attacked.pop(creature, None)
            self.blocked_by.pop(creature, None)
            for blockers in self.blocked_by.values():
                if creature in blockers:
                    blockers.remove(creature)
        return bool(changed)

    # ------------------------------------------------------------ replay id

    def state_fingerprint(self) -> str:
        """World fingerprint + ledger dump + event log + the 12b journal
        and binder dumps + the 12d layer and replacement registries
        (ruling 1): equal iff every replayed atom and every fired trigger
        produced the same state transitions."""
        h = hashlib.sha256()
        h.update(self.world.fingerprint().encode())
        h.update(repr(self.ledger.dump()).encode())
        for event in self.events:
            h.update(repr(event).encode())
            h.update(b"\n")
        for row in self.journal.dump():
            h.update(repr(row).encode())
            h.update(b"\n")
        h.update(repr(self.binder.dump()).encode())
        h.update(repr(self.layers.dump()).encode())
        h.update(repr(self.replacements.dump()).encode())
        # 16a: damage marks are replayed state too (ruling 1, CR 120.6).
        h.update(repr(sorted(self.damage.items())).encode())
        # CR 702.26 (2026-10-29): the phased-out status is replayed state.
        # Folded only when some permanent is phased out, so every replay
        # without phasing keeps its fingerprint bytes.
        if self.phased_out:
            h.update(
                repr(
                    tuple(
                        (str(card), str(controller), str(host))
                        for card, (controller, host) in sorted(self.phased_out.items())
                    )
                ).encode()
            )
        # r23a: the cast-declared X ledger rides the same fold.
        h.update(repr(sorted(map(str, self.etb_x.items()))).encode())
        # 16c: the deathtouch flag rides the same fold (CR 702.2b kills).
        h.update(repr(sorted(map(str, self.damage_deathtouch))).encode())
        # 16b: the attack record + the dispatched mandate ledger are
        # replayed state under the same ruling — a replay that attacked
        # with a different set, or lost an "attacks if able" rule, MUST
        # differ here.
        h.update(
            repr(
                (
                    tuple(str(a) for a in self.attackers),
                    tuple(sorted((str(k), str(v)) for k, v in self.attacked.items())),
                    str(self.defending_player),
                    self.declaring,
                    self._declare_group,
                    tuple(sorted(map(str, self.mandates))),
                    # 16c: the block record, the must-block ledger and the
                    # dispatched damage-assignment policies are the same
                    # kind of replayed combat state.
                    tuple(
                        sorted(
                            (str(k), tuple(str(b) for b in bs))
                            for k, bs in self.blocked_by.items()
                        )
                    ),
                    tuple(sorted(map(str, self.mandate_block))),
                    tuple(sorted((str(k), v) for k, v in self.damage_policies.items())),
                )
            ).encode()
        )
        # 13a: the turn ledger is replayed state too (same ruling).
        h.update(
            repr(
                (
                    self.phase,
                    self.turn_open,
                    tuple(self.extra_turn_queue),
                    tuple(self.lost_players),
                    tuple(sorted(self.loyalty_clock.items())),
                    self.last_flip_won_by,
                    self.end_turn_requested,
                )
            ).encode()
        )
        # 13b: the STACK COMPLETENESS FOLD. state.py's fingerprint loop
        # iterates PLAYER_ZONES and ZONE_STACK is NOT one of them (L48:
        # "the stack is shared, so it is not in this list"), so a card
        # parked on the stack is invisible to world.fingerprint() BY
        # DESIGN — this fold is what closes that hole: two worlds
        # differing only by a stack card MUST differ here (pinned by
        # test_stack_visible_in_executor_fingerprint). The land ledger,
        # mana segments and chosen names are executor-side replayed
        # state under the same ruling.
        h.update(repr(self.stack.dump()).encode())
        h.update(
            repr(
                tuple(sorted((str(s), v) for s, v in self.land_ledger.items()))
            ).encode()
        )
        h.update(repr(self.extra_land_plays).encode())
        h.update(repr(self.mana_ledger.dump()).encode())
        h.update(
            repr(
                tuple(sorted((str(s), n) for s, n in self.name_choices.items()))
            ).encode()
        )
        # 13c: the emblems table (owner-keyed synthetic handles) and the
        # attachment edges are replayed state under the same ruling — a
        # replay that granted a different emblem set or missed an
        # attachment MUST differ here.
        h.update(
            repr(
                tuple(
                    sorted(
                        ((str(owner), oid), str(handle))
                        for (owner, oid), handle in self.emblems.items()
                    )
                )
            ).encode()
        )
        h.update(
            repr(
                tuple(sorted((str(a), str(h_)) for a, h_ in self.attachments.items()))
            ).encode()
        )
        # 16e: the control overlay (derived) rides the fingerprint beside
        # the entries that produce it (seq + gained-turn make the fold
        # order-independent and expiry-sensitive).
        h.update(
            repr(
                tuple(sorted((str(a), str(c)) for a, c in self.control_overlay.items()))
            ).encode()
        )
        h.update(
            repr(
                tuple(
                    (
                        seq,
                        str(creature),
                        str(controller),
                        tag,
                        str(anchor),
                        turn,
                    )
                    for seq, creature, controller, tag, anchor, turn in (
                        self.control_entries
                    )
                )
            ).encode()
        )
        return h.hexdigest()

    # Alias the module-level helpers that tests and callers reach through
    # the package face.
    resolve_selector = staticmethod(resolve_selector)
    token_oracle_id = staticmethod(token_oracle_id)
