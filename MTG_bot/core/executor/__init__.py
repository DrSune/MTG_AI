"""The executor: runs compiled ability IR against a :class:`~MTG_bot.core.state.GameWorld`.

``Executor(world)`` keeps the game state the world has no fields for (durations, layers,
replacements, the event journal and trigger binder, turn, combat and stack state, damage marks,
control changes, phasing, emblems, attachments) and runs:

  * :meth:`Executor.execute` (one Atom) and :meth:`Executor.apply_effect` (an Effect tree: Seq,
    OptionalEffect, Conditional, Choose, EachPlayer, DelayedTrigger);
  * the turn skeleton: :meth:`~Executor.begin_turn` (untap, upkeep and draw steps),
    :meth:`~Executor.combat_step`, :meth:`~Executor.end_turn` (end and cleanup steps) and
    :meth:`~Executor.advance_turn` (turn order, extra turns);
  * :meth:`~Executor.attach_card` / :meth:`~Executor.attach_pool`, which bind a card's compiled
    abilities through the :class:`TriggerBinder`.

Each Atom runs inside an atom boundary: the :class:`EventJournal` diffs the world around it and
emits the events triggers match on. A top-level op ends by settling: state-based actions, then
the matched triggers in APNAP order, with the check repeated after each one. A self-retriggering
source is quarantined and listed in ``trigger_loops`` instead of looping
(``binding.MAX_TRIGGER_FIRES``). Casting, costs, legality and the legal-move enumerations live in
:mod:`.stack`, :mod:`.legality` and :mod:`.query`.

Design rules:

  * **flag, don't degrade**: an unsupported verb, effect node (Repeat), quantity or predicate
    raises ``NotImplementedError`` naming it; the executor never guesses a silent no-op.
  * **explicit decisions**: every choice is answered from outside, by the per-op ``decisions``
    pool or the executor's vocabulary-addressed :class:`~.decisions.DecisionStream`; an ask
    nothing answers raises. An offer with one legal answer is taken without asking
    (:func:`~.offers.offer_or_autopick`).
  * **executor-owned randomness**: the only randomness is a :class:`random.Random` seeded from
    ``sha256(master_seed:op_seq:tag)``, so two executors fed the same ops replay identically,
    with equal :meth:`Executor.state_fingerprint`.
  * ``SUPPORTED_VERBS_V2`` is the set of verbs with a handler, derived from the dispatch table;
    ``compile_pool(supported_verbs=...)`` marks a card that uses any other verb
    engine-unsupported.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from itertools import combinations

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
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    OptionalEffect,
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
from MTG_bot.core.executor.binding import TriggerBinder
from MTG_bot.core.executor.decisions import DecisionStream, site_digest
from MTG_bot.core.executor.durations import DurationLedger
from MTG_bot.core.executor.events import (
    KIND_COMBAT_DAMAGE,
    KIND_DECLARE_ATTACKERS,
    KIND_DECLARE_BLOCKERS,
    KIND_GAME_LOST,
    KIND_TAP_STATE,
    KIND_ZONE_CHANGE,
    EventJournal,
    GameEvent,
)
from MTG_bot.core.executor.layers import LayerRegistry
from MTG_bot.core.executor.legality import (
    BEGIN_COMBAT,
    CLEANUP,
    COMBAT_DAMAGE,
    DECLARE_ATTACKERS,
    DECLARE_BLOCKERS,
    DRAW,
    END_OF_COMBAT,
    END_STEP,
    FIRST_MAIN,
    FIRST_STRIKE_DAMAGE,
    SECOND_MAIN,
    TURN_ENDED,
    UNTAP,
    UPKEEP,
    ManaLedger,
    ability_playable,
    activate,
    block_pair_blocked_reason,
    blocker_askable,
    legal_attackers,
    mandated_attackers,
    mandated_to_be_blocked,
    protected_from,
)
from MTG_bot.core.executor.offers import offer_or_autopick
from MTG_bot.core.executor.quantity import Binding, ExecCtx, LastKnown, eval_filter
from MTG_bot.core.executor.query import choose_options, optional_offer
from MTG_bot.core.executor.replacements import ReplacementRecord, ReplacementRegistry
from MTG_bot.core.executor.returns import ReturnRegistry, ReturnRow
from MTG_bot.core.executor.selectors import (
    atom_target_slot_key as _atom_target_slot_key,
)
from MTG_bot.core.executor.selectors import players_for
from MTG_bot.core.executor.stack import SpellStack
from MTG_bot.core.executor.verbs import HANDLERS, damage_source, run_atom
from MTG_bot.core.identity import Handle, HandleSpace
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_STACK,
    GameWorld,
)

# The live capability set: exactly the verbs ``run_atom`` dispatches to a handler, derived from
# the table so the two cannot drift. A card using any other verb is flagged by
# ``compile_pool(supported_verbs=...)``, never faked.
SUPPORTED_VERBS_V2 = frozenset(HANDLERS)

Event = tuple[object, ...]

# The CR 504.1 turn draw, the IR node the turn skeleton runs for the active player. Atoms are
# immutable, so one node serves every turn. ``ControllerRef.YOU`` resolves through
# :func:`selectors.role_player` to the context's controller, which the skeleton sets to the
# active seat (:meth:`Executor._turn_draw`).
_TURN_DRAW = Atom(
    verb=Verb.DRAW,
    args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
)

# CR 402.2: a player's maximum hand size, "normally seven". The rule itself, not a tuning knob:
# no compiled card changes it ("You have no maximum hand size" compiles nowhere;
# docs/BACKLOG.md B-96).
MAX_HAND_SIZE = 7

# CR 514.1, 701.9a: the cleanup step's discard, the same hand-to-
# graveyard MOVE_ZONE shape a discard cost pays (legality.pay_costs). The
# cards the active player chose ride in through the ``cards`` binding, so the
# placeholder selector is never resolved.
_CLEANUP_DISCARD = Atom(
    verb=Verb.MOVE_ZONE,
    args=AtomArgs(
        pairs=(
            (
                "cards",
                Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    FAnd(()),
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
            ),
            ("controller", ControllerRef.YOU),
            ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
            ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
        )
    ),
)

# The player lane of a combat-damage atom. The dealer is ctx.source (the journal's cause
# column); the recipient is the bound player handle, which a PLAYER-zone TARGET selector
# returns as-is.
_PLAYER_TARGET = Selector(
    QConst(1),
    SelectorMode.TARGET,
    FAnd(children=()),
    zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),),
)

# "A planeswalker": the live type-line test the attack options read.
_IS_PLANESWALKER = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker")

# The card lane of a combat-damage atom. A PLAYER-zone selector turns a bound card into that
# card's controller (the Brash Taunter rule in ``selectors.resolve_selector``), so a creature or
# planeswalker recipient goes through a battlefield-zone TARGET selector, which keeps the card.
_CARD_TARGET = Selector(
    QConst(1),
    SelectorMode.TARGET,
    FAnd(children=()),
    zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
)

# CR 610.3: the zones an "until" return goes back to, in the fixed order the batch moves them
# (one MOVE_ZONE per zone), and their IR kinds.
_RETURN_ZONES = (ZONE_BATTLEFIELD, ZONE_HAND, ZONE_GRAVEYARD, ZONE_EXILE)
_RETURN_ZONE_KIND = {
    ZONE_BATTLEFIELD: ZoneKind.BATTLEFIELD,
    ZONE_HAND: ZoneKind.HAND,
    ZONE_GRAVEYARD: ZoneKind.GRAVEYARD,
    ZONE_EXILE: ZoneKind.EXILE,
}


#: The step after each step whose successor does not depend on the game (CR 500.1;
#: Executor._next_step decides the rest).
_NEXT_STEP = {
    UNTAP: UPKEEP,
    UPKEEP: DRAW,
    DRAW: FIRST_MAIN,
    FIRST_MAIN: BEGIN_COMBAT,
    BEGIN_COMBAT: DECLARE_ATTACKERS,
    FIRST_STRIKE_DAMAGE: COMBAT_DAMAGE,
    COMBAT_DAMAGE: END_OF_COMBAT,
    END_OF_COMBAT: SECOND_MAIN,
    SECOND_MAIN: END_STEP,
    END_STEP: CLEANUP,
}


def _combat_damage_atom(amount: int, recipient: object) -> Atom:
    """One DEAL_DAMAGE atom of ``amount`` to the announced recipient: a player takes the
    player lane, a card (a blocker, a blocked attacker, a planeswalker) the card lane."""
    target = _PLAYER_TARGET if str(recipient).startswith("player:") else _CARD_TARGET
    return Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(pairs=(("amount", QConst(amount)), ("target", target))),
    )


__all__ = [
    "MAX_HAND_SIZE",
    "SUPPORTED_VERBS_V2",
    "Executor",
    "GameOver",
    "ability_playable",
    "activate",
]


# Predicates that test an object's own characteristics.
_CHARACTERISTIC_PREDS = frozenset(
    {
        FAtomPred.TYPE_EQ,
        FAtomPred.SUBTYPE_EQ,
        FAtomPred.SUPERTYPE_EQ,
        FAtomPred.COLOR_HAS,
        FAtomPred.COLOR_IN,
        FAtomPred.COLOR_COUNT_GE,
        FAtomPred.CMC_LE,
        FAtomPred.CMC_GE,
        FAtomPred.NAME_EQ,
        FAtomPred.IS_PERMANENT,
        FAtomPred.IS_TOKEN,
        FAtomPred.POWER_LE,
        FAtomPred.POWER_GE,
    }
)


def _tests_characteristics_only(pred: object) -> bool:
    """Every leaf of the filter is a characteristic test (FAnd/FOr/FNot)."""
    if isinstance(pred, (FAnd, FOr)):
        return bool(pred.children) and all(
            _tests_characteristics_only(c) for c in pred.children
        )
    if isinstance(pred, FNot):
        return _tests_characteristics_only(pred.inner)
    return isinstance(pred, FAtom) and pred.pred in _CHARACTERISTIC_PREDS


def _ends_in_optional(effect: object) -> bool:
    """Does a Seq step end in an ``OptionalEffect`` (a bare optional, or a Seq
    whose last step is one, through nested Seqs)? Such a step's may-offer
    keeps its own "If you do" record; any other step is a mandatory
    antecedent whose record the Seq runner writes."""
    if isinstance(effect, OptionalEffect):
        return True
    if isinstance(effect, Seq) and effect.steps:
        return _ends_in_optional(effect.steps[-1])
    return False


def _conditional_subject(pred: object, ctx: ExecCtx) -> Handle | None:
    """What a bare Conditional's predicate is judged on, when the
    predicate only tests an object's characteristics: the object the previous
    sentence acted on (the result register, written by the atom just before:
    ``ctx.result_fresh``), None when that register names no single object;
    after a sentence that names no object ("you gain 1 life"), the object the
    trigger's event names (Overgrowth Elemental's "If that creature was an
    Elemental": the creature that died, not the Elemental whose ability it
    is). The ability's source otherwise (a history predicate such as See the
    Truth's "if this spell was cast from anywhere other than your hand")."""
    if _tests_characteristics_only(pred):
        if ctx.result_fresh:
            handles = ctx.binding_handles("result") or []
            return handles[0] if len(handles) == 1 else None
        event = [h for h in ctx.binding_handles("event") or [] if h.namespace == "card"]
        if len(event) == 1:
            return event[0]
        if len(event) > 1:
            # A gathered event (ability_tree.gathers_objects) names several objects: no "it".
            raise NotImplementedError(
                "executor: a bare Conditional after a sentence that names no object, under an "
                "event that gathered several objects, has no object to judge"
            )
    return ctx.source


class GameOver(Exception):
    """The game ended at a state-based-action check (CR 704.3): at most one
    player is still in it (CR 104.2a: that player wins; 104.4a: when all the
    remaining players lose at once, the game is a draw). Raised by
    :meth:`Executor._player_losses` so that no game action follows the check:
    no trigger resolves, no damage step or turn step comes next. Who lost,
    and why, is in ``Executor.lost_players`` and the GAME_LOST journal rows.
    The game driver (``games._play``) catches it."""


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
        # CR 120.6: damage marked on permanents. GameWorld has no damage
        # field, so the marks live here as replayed state (folded into
        # state_fingerprint), removed in the cleanup step and when the
        # permanent leaves the battlefield.
        self.damage: dict[Handle, int] = {}
        # CR 702.26: PHASED-OUT permanents. Phasing is a status
        # of the permanent (CR 110.5), not a zone: the card stays in its
        # battlefield zone, no zone-change event happens (702.26d), and the
        # engine's battlefield readers leave it out (it is treated as though
        # it does not exist, 702.26b). handle -> (the player who controlled
        # it when it phased out: it phases in during that player's untap
        # step, CR 502.1; the permanent it phased out indirectly with, or
        # None when it phased out directly, 702.26g). Replayed state, folded
        # into state_fingerprint when non-empty.
        self.phased_out: dict[Handle, tuple[Handle, Handle | None]] = {}
        # CR 614.1c (Wildwood Scourge): the X declared by a spell's cast
        # (601.2f) travels to that permanent's ETB firings. stack.cast
        # records it as the spell enters the battlefield; the binder's _ctx
        # hands it to the firings of that entry (x_value). Cleared when the
        # permanent leaves the battlefield, so an entry without a cast
        # (reanimation) reads X = 0 (CR 107.3b).
        self.etb_x: dict[Handle, int] = {}
        # Refusals of the guarded static lane: a StaticAbility whose payload
        # the layers cannot parse (Rin and Seri) is skipped at battlefield
        # attach and recorded here (handle and the engine's message). Not
        # folded into state_fingerprint: it derives from the world and the
        # records, never a hidden decision. Only tests read it.
        self.unparseable_statics: list[str] = []
        # The trigger-loop tripwire's record. A self-retriggering source
        # (Chandra's Incinerator eating its own damage rows) is
        # quarantined, its queued and future firings dropped, and listed
        # here; the drain goes on with everything else. Like
        # unparseable_statics it is not folded into state_fingerprint; the
        # quarantine set itself is, through the binder's dump.
        self.trigger_loops: list[str] = []
        # Refusals recorded instead of raised, as "<lane> <card>: <message>"
        # rows, deduplicated, with ``unresolved_effect_counts`` counting the
        # repeats: the steps the live-game guard skipped
        # (:meth:`_run_guarded_effect`: an effect whose ``result``/``target``
        # anaphora reads a register nothing in this execution wrote, a
        # compiler mis-fold rather than a game bug) and the cast lane's
        # refused designations (``query.register_cast_gap``). Only tests
        # read it. Not folded into state_fingerprint.
        self.unresolved_effects: list[str] = []
        self.unresolved_effect_counts: dict[str, int] = {}
        self.journal = EventJournal(world, self.ledger)
        # Dies rows record the controller as of death through the control
        # overlay (a bound method, so a deepcopy fork rebinds it).
        self.journal.controller_override = self._overlay_controller
        # CR 610.3: objects moved "until" an event, waiting to return.
        # Replayed state, folded into state_fingerprint while non-empty.
        self.returns = ReturnRegistry()
        # Built before the binder: its lifecycle hooks reach them during
        # attach.
        self.layers = LayerRegistry(self)
        self.replacements = ReplacementRegistry(self)
        self.binder = TriggerBinder(self)
        self._op_seq = 0
        # CR 704.3, 603.3: how many effects are resolving right now. A public op
        # (execute / apply_effect) started inside a resolution is part of it
        # (legality.pay_costs paying a cost an effect asks for, verbs._v_pay):
        # it does not settle, so no state-based action is checked and no
        # trigger is put on the stack until the outermost op settles. Zero
        # between ops, so not fingerprinted.
        self._resolving = 0
        self._turn_started = False
        # ---------------------------------------------------------- turn state
        # GameWorld has no phase, turn-flow or loss fields, so the turn
        # skeleton keeps them here; state_fingerprint folds the replayed
        # ones. ``phase`` is the last phase marker recorded (None before the
        # first begin_turn); ``turn_open`` is the "a turn is in progress"
        # flag (begin_turn to TURN_ENDED, its end and cleanup steps included):
        # the legality gates read it, and the sorcery window is the phase's
        # (MAIN_PHASES) besides.
        self.phase: str | None = None
        self.turn_open = False
        # The step machine (CR 117, 500-514; see begin_turn): whether the step's
        # turn-based actions ran, who holds priority, how many players passed in
        # succession, and the creatures that had first or double strike as the
        # first combat damage step began (CR 510.4). Folded into the fingerprint.
        self.tba_done = False
        self.priority_holder: Handle | None = None
        self.passes = 0
        # the trigger-loop tripwire (:meth:`_resolve_top`): triggered abilities resolved since
        # the stack was last empty, and per source
        self._loop_fires = 0
        self._loop_sources: dict[Handle, int] = {}
        self.step_actions: dict[Handle, int] = {}
        self.first_strikers: frozenset[Handle] | None = None
        # Who passes priority (DESIGN_PRIORITY §11). Driven: a game loop asks the
        # player who holds it at every priority point (games._play_turns). Not
        # driven (a unit test, a pack's set-up, a tool): an op ends with both
        # players passing until the stack is down to where it was. Set by the
        # driver, not replayed state.
        self.driven = False
        # CR 103.8a: the first player skips the draw of their first turn.
        # A function of the turn counter, so not folded.
        self._skip_draw = False
        # CR 500.7: EXTRA_TURN pushes onto the FRONT (the most recently
        # created turn is taken first), advance_turn pops index 0.
        self.extra_turn_queue: list[Handle] = []
        # CR 500.7: extra turns are inserted after a turn, so the normal turn
        # order resumes from the seat of the last NORMAL turn, never from an
        # extra turn's player. None until advance_turn first rotates (the
        # first turn is the normal turn of whoever began it).
        self.normal_turn_seat: Handle | None = None
        # The players who lost: a LOSE_GAME effect (verbs._v_lose_game) or
        # the CR 704.5a/b state-based actions (_player_losses).
        self.lost_players: list[Handle] = []
        # CR 704.5b: the players who attempted to draw from an empty library
        # since the last state-based-action check (_v_draw adds, the check
        # reads and clears). Empty between ops, so not fingerprinted.
        self.drew_from_empty: set[Handle] = set()
        # CR 606.3: handle -> turn of that permanent's last loyalty act.
        self.loyalty_clock: dict[Handle, int] = {}
        # FLIP_COIN's winner, read by the FLIP_WON conditional of a
        # separate ability row (Tavern Swindler compiles to two).
        self.last_flip_won_by: Handle | None = None
        # END_TURN's close, made at the op boundary that follows the atom
        # (_consume_end_turn).
        self.end_turn_requested = False
        # CR 724.1a: the journal length when the first END_TURN atom of the
        # request ran; folded into the fingerprint while a request is open.
        self.end_turn_mark = 0
        # -------------------------------------------------------- stack + mana
        # The spell stack (CR 405): LIFO StackObject frames, folded into the
        # fingerprint.
        self.stack = SpellStack()
        # Handles of the abilities put on the stack (CR 113.1b: an ability on
        # the stack is an object of its own, not its source). Not folded: the
        # count is a function of the journalled activations and firings.
        self.ability_handles = HandleSpace("ability")
        # CR 305.1 once-per-turn land gate: seat -> (turn, plays).
        # extra_land_plays widens the allowance; nothing writes it outside
        # tests (ADD_LAND_PLAY registers a layer instead), so it stays 0.
        self.land_ledger: dict[Handle, tuple[int, int]] = {}
        self.extra_land_plays = 0
        # The segment mirror of the world's mana pool: which mana carries a
        # spend restriction (THIS_MANA).
        self.mana_ledger = ManaLedger()
        # CHOOSE_NAME's write-side (Runed Halo): source permanent -> the
        # chosen name, read back by the NAME_CHOSEN filter predicate.
        self.name_choices: dict[Handle, str] = {}
        # CHOOSE_NAME's read-side: the format's card pool,
        # every card a deck builder of this game could have used (name, printed
        # type line), set by games._setup_game. Public information: the names
        # offered never depend on the game's hidden zones. Empty in a rig with
        # no format (unit tests, scenario packs): the world's names then.
        self.name_pool: tuple[tuple[str, str], ...] = ()
        # ----------------------------------------------- emblems + attachments
        # Granted emblems are replayed state that is NOT world cards (an
        # emblem never enters a zone): the synthetic Handle("emblem", n) the
        # binder bound its abilities to -> (owner, emblem oracle_id).
        self.emblems: dict[Handle, tuple[Handle, str]] = {}
        self._emblem_seq = 0
        # Attachment relation (auras/equipment): AURA handle -> HOST handle.
        # CardState has no attachment field, so the table lives
        # here; IS_ATTACHED_TO_SOURCE reads it and the binder drops every
        # edge touching a handle that leaves the battlefield.
        self.attachments: dict[Handle, Handle] = {}
        # Last-known information of the attachment relation as a host leaves
        # the battlefield: HOST -> the sorted Auras and Equipment attached to
        # it then (Malefic Scythe). The journal writes ZONE_CHANGE before
        # CREATURE_DIES in the same diff sweep, so by the time a dies
        # trigger's IS_ATTACHED_TO_SOURCE filter is judged the live table is
        # already pruned; this row is the departure-time truth (CR 400.7).
        # Replaced per departing host. Derived from the same detaches, so not
        # in the fingerprint.
        self.detach_lki: dict[Handle, tuple[Handle, ...]] = {}
        # The one last-known-information snapshot of each permanent that left the
        # battlefield (quantity.LastKnown: power, toughness, counters, keywords with
        # the granted ones, controller), captured as it leaves, before its counters
        # cease (CR 122.2), its effects end (CR 400.7) and its control entries
        # expire. Read through quantity.departed_lki / last_known by what needs the
        # object as it last existed: "When this creature dies, you gain life equal
        # to its power" (Conclave Mentor), "if it had a +1/+1 counter on it"
        # (Basri's Lieutenant), damage a sacrificed source deals with its granted
        # deathtouch (CR 113.7a), "its controller" and "that player" (CR 608.2h),
        # the controller of its own dies trigger (CR 603.3a, 603.10a). Dropped when
        # the card re-enters (a new object, CR 400.7). Derived state replayed from
        # the same departures, NOT in the fingerprint (the detach_lki precedent).
        self.departed_lki: dict[Handle, LastKnown] = {}
        # Each seat's starting life, snapshotted at construction: GameWorld
        # takes ``start_life`` as a parameter but does not store it.
        # LIFE_LEAD_OVER_START_GE (Speaker of the Heavens) reads current life
        # minus this; the journal cannot reconstruct the lead, since a
        # non-damage life loss leaves no row. A replay rebuilds the world at
        # the same start_life (games._setup_game), so the snapshot stays out
        # of the fingerprint.
        self.starting_life: dict[Handle, int] = {
            p: world.players[p].life for p in world.player_order
        }
        # ----------------------------------------------------- control overlay
        # GAIN_CONTROL (CR 611, 110.2): GameWorld derives controller_of from
        # the zone's owner and has no control field, so control changes are
        # replayed state here, folded into state_fingerprint.
        # ``control_entries`` is the source of truth, one row per live
        # GAIN_CONTROL application (seq, creature, controller, expiry tag,
        # anchor, turn gained); ``control_overlay`` is the derived
        # effective-controller map the executor's read sites consult (later
        # entries win, CR 613.2 timestamps), and ``control_gained_turn`` the
        # CR 302.6 sickness clock: the turn of each creature's last change of
        # effective controller. A creature with no entry is controlled by its
        # zone's owner.
        self.control_entries: list[
            tuple[int, Handle, Handle, str, Handle | None, int]
        ] = []
        self._control_seq = 0
        self.control_overlay: dict[Handle, Handle] = {}
        self.control_gained_turn: dict[Handle, int] = {}
        # -------------------------------------------------------- combat state
        # GameWorld has no combat fields, so the attack record is replayed
        # state here, folded into state_fingerprint: the attackers in
        # declaration order, what each attacks (the defending player or a
        # planeswalker that player controls), the defending seat, and the
        # declare-window flag the enters-attacking token path reads (CR
        # 508.1i). ``mandates`` is the DISPATCHED MANDATE_ATTACK ledger (the
        # static shape lives as layers' "mandate" records).
        self.attackers: list[Handle] = []
        self.attacked: dict[Handle, Handle] = {}
        self.defending_player: Handle | None = None
        self.declaring = False
        self._declare_group = 0
        self.mandates: set[Handle] = set()
        # --------------------------------------------------------- block state
        # ``blocked_by``: attacker -> the creatures blocking it, in DECLARE
        # order (CR 509.1b: one attacker per blocker, so a handle appears in
        # exactly one list; multiple blockers per attacker ARE legal — the
        # assignment order is asked per attacker, CR 510.1). Cleared with
        # the attack record at end of combat; replayed state.
        self.blocked_by: dict[Handle, list[Handle]] = {}
        # DISPATCHED MANDATE_BLOCK ledger (the static shape rides layers'
        # "mandate_block" records; Canopy Stalker's rule line).
        self.mandate_block: set[Handle] = set()
        # DISPATCHED DAMAGE_ASSIGN_POLICY scopes (GRANT_ABILITY-carried
        # statics read through layers.policy_as_unblocked; the dispatch
        # shape records the scope word here keyed by its source).
        self.damage_policies: dict[Handle, str] = {}
        # The combat-damage wave flag: the op number of the combat damage
        # step being dealt (0 outside one), set for the atom boundaries inside
        # it so record_atom marks the DAMAGE rows (amount, step) — the
        # DamageDealtEvent ``combat`` scope (Garruk's Harbinger, Subira's
        # delayed trigger), and the one damage event the step is (CR 510.2).
        self._combat_wave_open = 0
        # The draw step's register (Teferi's Ageless Insight).
        # _draw_step_open is True only while :meth:`_turn_draw` runs; the
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
        # The vocabulary-addressed decision channel. One stream per
        # executor: FIFO priming, ask-time provider and the ask log ride
        # every context the executor builds (effect ops, trigger firings,
        # payments, replacement actions), which is what lets a policy answer
        # a demand a running op armed mid-drain.
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
            # The registries ride on every effect context (layer verbs, the
            # damage-replacement interceptor).
            layers=self.layers,
            replacements=self.replacements,
            executor=self,
            x_value=x_value,
            stream=self.decisions,
            # The journal too, so the history predicates answer identically
            # from a query context and a firing context (the same rows).
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
        """The spell-resolution context: the ordinary effect context
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
        """Run one Atom; returns the ``events`` rows this call appended.
        Unsupported verbs raise ``NotImplementedError`` at dispatch. The
        atom's world changes are journalled; any trigger the change arms
        drains afterwards (APNAP). Trigger decisions arrive through the
        executor's decision stream: the caller cannot know in advance
        which triggers the op arms."""
        if not isinstance(atom, Atom):
            raise ValueError(
                f"Executor: execute needs an Atom, got {type(atom).__name__}"
            )
        self._op_seq += 1
        ctx = self._ctx(
            source=source, controller=controller, bindings=bindings, decisions=decisions
        )
        start = len(self.events)
        self._run_resolution(atom, ctx)
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
        known tree in ask order, and every demand it cannot serve reaches
        the executor's decision stream. OptionalEffect asks the
        query-narrowed offer (``fire``/``skip``), Seq runs its steps,
        Conditional judges its predicate (the subject: the revealed card
        while a look window is open, else :func:`_conditional_subject`),
        Choose takes ONE decision token (the index of the chosen option
        set in ``query.choose_options`` order), EachPlayer runs one
        sub-execution per denoted player with that player as controller
        (the inner effect is compiled YOU-relative, so the rotation IS the
        rebinding) and DelayedTrigger is scheduled on the binder; any other
        node (Repeat) raises ``NotImplementedError``. ``x_value`` is an
        activated ability's announced X (CR 107.3a; ``legality.activate``'s
        X lane), None for every effect with no X."""
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
            # An activation's per-target designations (legality.activate), the
            # same per-slot map the cast lane sets on a multi-target spell.
            ctx.slot_designations = slot_designations
            ctx.designation_union = tuple(
                sorted({h for one in slot_designations.values() for h in one})
            )
        start = len(self.events)
        self._run_resolution(effect, ctx)
        return tuple(self.events[start:])

    def _run_resolution(self, effect: Effect, ctx: ExecCtx) -> None:
        """Run a public op's effect, then settle, unless the op was started inside another
        resolution (CR 704.3: state-based actions are checked only when a player would
        receive priority; CR 603.3: triggered abilities are put on the stack then too).
        Paying a cost an effect asks for ("You may pay 2 life. If you do, ...") runs each
        payment step as an op; settling there would run the player-loss check in the middle
        of the resolution (paying down to 0 life before the effect gains life back would end
        the game) and resolve the payment's triggers before the rest of the effect. Such an
        op leaves its events to the outermost op's settle, whose journal pass sees them
        (TriggerBinder.on_events reads every unseen row)."""
        nested = self._resolving > 0
        self._resolving += 1
        try:
            self._run_effect(effect, ctx)
        finally:
            self._resolving -= 1
        if not nested:
            self._finish_op()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """An action or a resolution, with no priority point inside it (CR
        601.2, 602.2: casting a spell or activating an ability, its costs paid
        included; CR 608.2: an object resolving). The ops run inside it do not
        settle, as ops started inside a resolution do not
        (:meth:`_run_resolution`); the triggers they cause wait for the next
        priority point and go on the stack above whatever is there."""
        self._resolving += 1
        try:
            yield
        finally:
            self._resolving -= 1

    @staticmethod
    def _partition_step(step: object) -> bool:
        """The partition scan (Cultivate), shared by the ``_run_effect`` Seq
        branch and the guarded lane: a partition MOVE_ZONE is one whose
        ``cards`` Selector is ONE_OF/REST."""
        if not isinstance(step, Atom) or step.verb is not Verb.MOVE_ZONE:
            return False
        sel = step.args.get("cards")
        return isinstance(sel, Selector) and sel.mode in (
            SelectorMode.ONE_OF,
            SelectorMode.REST,
        )

    def _run_guarded_effect(self, effect: Effect, ctx: ExecCtx, lane: str) -> None:
        """The live-game effect runner (spell resolution in the ``cast`` and
        ``cast_card`` lanes, an Aura's included, and the ``trigger`` lane):
        ``_run_effect`` with the dangling-anaphora guard. When a step
        refuses because its ``result``/``target`` anaphora has no producer
        in this execution (a compiler mis-fold: the antecedent clause was
        never compiled, as in Acquisitions Expert's discard), the step is
        skipped and the refusal recorded on ``unresolved_effects``; the
        spell still resolves and the game goes on. Only the dedicated
        refusals are skipped (``selectors.referent_absent``,
        ``stack.face_cast_absent``: the error type and the exact site
        message); every other error propagates. CR 609.7: a top-level
        ``Seq`` runs step by step, so a
        skipped step does not stop the rest. Only the top level: a nested
        Seq (or Optional/Conditional wrapper) that fails part-way is skipped
        whole. The raw ``_run_effect`` keeps raising, as the unit tests pin.
        """
        from MTG_bot.core.executor.selectors import referent_absent
        from MTG_bot.core.executor.stack import face_cast_absent

        steps = effect.steps if isinstance(effect, Seq) else (effect,)
        saved_partition = ctx.search_partition
        saved_found = ctx.search_found  # the found set is Seq-scoped too
        if isinstance(effect, Seq):
            # the Seq branch's SEARCH-designation context, reproduced so
            # the guarded per-step lane behaves identically to a raw
            # Seq run.
            ctx.search_partition = saved_partition or any(
                self._partition_step(step) for step in steps
            )
        self._resolving += 1  # CR 704.3: see _run_resolution
        try:
            for step in steps:
                depth = self.journal.open_depth()
                before = (len(self.events), len(self.journal.events))
                try:
                    self._run_effect(step, ctx)
                    self._note_step_done(step, before, ctx)
                except (NotImplementedError, ValueError) as exc:
                    if not (referent_absent(exc) or face_cast_absent(exc)):
                        raise
                    # The skipped step's atom boundary never closes.
                    self.journal.drop_open(depth)
                    # A skipped step was not done (an "If you do" after it
                    # must not read an older step's record).
                    self._note_step_done(
                        step, (len(self.events), len(self.journal.events)), ctx
                    )
                    src = ctx.source
                    name = (
                        self.world.cards[src].identity.name
                        if src in self.world.cards
                        else "?"
                    )
                    # A guard skip journals nothing: this ledger entry is
                    # its only trace.
                    flag = f"{lane} {name}: {exc}"
                    if flag not in self.unresolved_effect_counts:
                        self.unresolved_effects.append(flag)
                        self.unresolved_effect_counts[flag] = 1
                    else:
                        self.unresolved_effect_counts[flag] += 1
        finally:
            self._resolving -= 1
            ctx.search_partition = saved_partition
            ctx.search_found = saved_found

    def _note_step_done(
        self, step: Effect, before: tuple[int, int], ctx: ExecCtx
    ) -> None:
        """CR 118.12: "[Do something]. If you do, [effect]" asks whether a
        MANDATORY step actually happened, exactly as it asks of an optional
        one. After each step of a sequence, a step that does not end in an
        OptionalEffect records whether it changed anything (journal or event
        rows) under the ability's may-site, which MAY_DONE reads; an optional
        step keeps the record its own OptionalEffect branch wrote. A step
        that changed nothing was not done (Archfiend's Vessel's "exile it"
        after the Vessel left the battlefield, CR 400.7)."""
        if not _ends_in_optional(step):
            ctx.may_done[f"may:{ctx.source}"] = (
                len(self.events),
                len(self.journal.events),
            ) != before

    def _run_effect(self, effect: Effect, ctx: ExecCtx) -> None:
        if isinstance(effect, Atom):
            # The journalled Atom boundary: snapshot, run, diff. The journal
            # derives the trigger-relevant world changes from the diff; a
            # verb handler emits a row itself only for an event the world
            # does not show (a countered spell).
            before = self.journal.snapshot()
            start = len(self.events)
            # Rookie Mistake, Hunter's Edge: on a MULTI-slot spell
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
            # CR 120.1, 120.2b: a DEAL_DAMAGE atom that names its dealer
            # journals that object as the damage's cause, so "whenever a
            # creature deals damage" readers see the creature, not the spell.
            # Read before the atom runs, in the same bindings the verb sees.
            cause = ctx.source
            if effect.verb is Verb.DEAL_DAMAGE and isinstance(
                effect.args.get("dealer"), Selector
            ):
                cause = damage_source(ctx, effect) or ctx.source
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
                cause,
                effect.verb.name,
                self.events[start:],
                combat=self._combat_wave_open,
            )
            # The zone-change bookkeeping: a permanent leaving the
            # battlefield ends what is anchored on it (a return does not
            # restore it), one entering gets its entered state.
            self._on_zone_changes(new_events)
            # Replacements consumed during the atom run (the replaced event
            # never happened) queue their ACTION here, so it is journalled
            # as ITS OWN atom boundary — one diff per mutation, no
            # double-emitted events.
            while ctx.pending_replacements:
                entry = ctx.pending_replacements.pop(0)
                repl_bindings: dict[str, Binding] | None = None
                counter_reg: tuple[CounterKind, int] | None = None
                amount_reg: int | None = None
                if isinstance(entry, tuple):
                    if len(entry) == 4:
                        # Conclave Mentor: a counter-placement
                        # consumer queued (record, receiving card, kind,
                        # amount) — the action's referent binds to the
                        # card AND the COUNTER_COUNT prop register carries
                        # the replaced event's count (ADD(QProp(event,
                        # COUNTER_COUNT), 1) reads it, quantity.py).
                        repl, event_card, counter_kind, counter_n = entry
                        repl_bindings = {"event": [event_card]}
                        counter_reg = (counter_kind, counter_n)
                    elif len(entry) == 3:
                        # Angel of Vitality: a life-gain consumer queued
                        # (record, gaining player, amount) — the action's
                        # "that much life" is the replaced event's amount
                        # (ADD(QProp(event, AMOUNT), 1)), the event register
                        # a trigger firing carries too (binding._ctx).
                        repl, event_player, amount_reg = entry
                        repl_bindings = {"event": [event_player]}
                    else:
                        # Containment Priest: a zone-change consumer
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
                inner.event_amount = amount_reg
                # The CR 614.5 chain guard travels with the action: the
                # record that consumed THIS event cannot consume the event
                # its own action produces.
                inner.replaced_seq = ctx.replaced_seq | {repl.seq}
                self._run_effect(repl.action, inner)
        elif isinstance(effect, Seq):
            # Cultivate: when a partition MOVE_ZONE (the ONE_OF pick
            # / REST complement) appears among the steps, a SEARCH atom in
            # this sequence DESIGNATES instead of delivering — the
            # partition re-searches the found set and would find nothing
            # the SEARCH had already moved. Shallow scan: the corpus'
            # partition idiom is a flat sibling chain (the compiler emits
            # SEARCH/REVEAL/MOVE/MOVE/SHUFFLE as direct steps).
            partition = any(self._partition_step(step) for step in effect.steps)
            saved = ctx.search_partition
            saved_found = ctx.search_found  # the found set is Seq-scoped too
            ctx.search_partition = saved or partition
            try:
                for step in effect.steps:
                    before = (len(self.events), len(self.journal.events))
                    self._run_effect(step, ctx)
                    self._note_step_done(step, before, ctx)
            finally:
                ctx.search_partition = saved
                ctx.search_found = saved_found
        elif isinstance(effect, OptionalEffect):
            # The ASK vocabulary is the query surface's own narrowed
            # optional_offer, so the policy gets exactly what a query would
            # answer ("may pay {2}" with an empty pool offers only skip, CR
            # 117.3: a provider can never answer fire where firing is
            # illegal). The site tag carries the offer's digest, so two
            # may-offers on one source are two sites, and a skip-only offer
            # is taken without asking.
            offer = optional_offer(
                self,
                effect,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            done = False
            if (
                offer_or_autopick(ctx, offer, f"may:{ctx.source}:{site_digest(effect)}")
                == "fire"
            ):
                before = (len(self.events), len(self.journal.events))
                self._run_effect(effect.inner, ctx)
                # CR 118.12: "If you do" asks whether the optional
                # action was carried out, not what was answered: an action
                # that changed nothing (a discard with no legal card, a
                # sacrifice with nothing to sacrifice) was not done.
                done = (len(self.events), len(self.journal.events)) != before
            ctx.may_done[f"may:{ctx.source}"] = done
        elif isinstance(effect, Conditional):
            # The compiler's sentence convention
            # (templates_b5b._build_if_it_type_then: "Conditional whose
            # subject is the previous sentence's revealed card"): when the
            # preceding atom was a LOOK_AT/REVEAL, the pred judges the
            # revealed card, not the ability source (Track Down's "if it's
            # a creature or land card"). run_atom closes the window after
            # every other verb. A bare Conditional judges ctx.source, unless
            # the predicate tests only an object's characteristics ("If it
            # was a creature card", Scavenging Ooze): then "it" is the
            # object the previous sentence acted on, the result register,
            # read as it last existed (CR 608.2h). No such object means the
            # condition is false (CR 608.2b).
            subj = (
                ctx.look_window[0]
                if ctx.look_window
                else _conditional_subject(effect.pred, ctx)
            )
            if subj is not None and eval_filter(effect.pred, subj, ctx):
                self._run_effect(effect.then_effect, ctx)
            elif effect.else_effect is not None:
                self._run_effect(effect.else_effect, ctx)
        elif isinstance(effect, Choose):
            # ORDER CONTRACT (query.OptionChoice docstring): the decision
            # token is str(i), the i-th OPTION-SET of query.choose_options
            # (size-ascending, index-lex). One decision picks the whole set:
            # a k-choose is one compound choice.
            opts = choose_options(
                self,
                effect,
                source=ctx.source,
                controller=ctx.controller,
                bindings=ctx.bindings,
            )
            vocab = tuple(str(i) for i in range(len(opts)))
            # CR 601.2b (Return to Nature): a mode DECLARED at cast time
            # (the cast lane consumed the ORDER token before the targets —
            # modes before targets) arrives as a pre-chosen token and is not
            # asked again. Every other Choose asks its token at resolution.
            if ctx.prechosen_modes:
                pick = ctx.prechosen_modes.pop(0)
                if pick not in vocab:
                    raise ValueError(
                        f"executor: choose: declared mode {pick!r} not in {vocab}"
                    )
            else:
                # CR 601.2b: a menu whose bounds clamp to ONE option set
                # ("choose two" over two options) is FORCED: it is taken
                # without asking and the pick journalled.
                pick = offer_or_autopick(
                    ctx,
                    vocab,
                    f"choose:{ctx.source}:{site_digest(tuple(o.option_idxs for o in opts))}",
                )
            for idx in opts[int(pick)].option_idxs:
                self._run_effect(effect.options[idx], ctx)
        elif isinstance(effect, EachPlayer):
            # "Each opponent …" (Goremand's ETB sacrifice, Pursued Whale's
            # tokens): one sub-execution per denoted player with the
            # CONTROLLER rotated. The templates compile the inner effect
            # YOU-relative (Goremand's SACRIFICE filter CONTROLLER_IS YOU,
            # MILL's controller role, Zone(PLAYER,YOU)), so rotation IS the
            # rebinding; the spell's designations stay visible (bindings
            # carried, never rewritten). A referent ref ("that creature's
            # controller", Transmogrify) is the controller of the object it
            # names (CR 608.2h). Players go in players_for_ref's
            # seat order, not APNAP order (CR 101.4); the two differ only
            # when a later seat is active. The per-op decision POOL cursor
            # rides across the sub-contexts (one positional supply answers
            # every ask in order) and is written back; the stream lanes are
            # executor-owned and need no forwarding. Each inner atom
            # journals its own boundary under the stable source.
            for player in players_for(effect.ref, ctx):
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
            if effect.reflexive:
                # CR 603.12: it triggers now, on what this resolution did (the Conditional
                # around it checked); it goes on the stack at the next priority point.
                self.binder.fire_reflexive(effect, ctx)
            else:
                # Scheduled on the binder's journal matcher; expires at end of turn.
                self.binder.schedule_delayed(effect, ctx.source, ctx.controller)
        else:  # pragma: no cover - apply_effect pre-checks the node type
            raise NotImplementedError(
                f"executor: effect {type(effect).__name__} not implemented (12e)"
            )

    def _on_zone_changes(self, events: list[GameEvent]) -> None:
        """The bookkeeping for the zone changes one atom boundary journalled, in
        the journal's emit order.

        A permanent leaving the battlefield is a new object in its new zone
        (CR 400.7): its last-known information is snapshotted, then what was
        keyed on it ends (durations, P/T changes, layer, prevention and
        control records, marked damage, its place in combat) and it is
        untapped. A card moving anywhere but the battlefield loses its
        counters (CR 122.2). A permanent entering gets its compiled entered
        state (CR 614.1c).

        CR 610.3: the rows a MOVE_ZONE "until" staged in this
        boundary get their entry clocks first; then every row anchored on a
        permanent that left the battlefield here ends, and those objects
        return together after the whole batch is processed (610.3d)."""
        self.returns.complete(events)
        due: list[ReturnRow] = []
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
                self.departed_lki[event.subject] = LastKnown(
                    power,
                    toughness,
                    dict(state.counters),
                    self.layers.keywords(event.subject),
                    self.controller_of(event.subject),  # before the control entries end
                    self._op_seq,
                    # before _remove_from_combat below
                    self.attacked.get(event.subject) if event.subject in self.attackers else None,
                )
                # CR 400.7: the object in its new zone is a new object, so the P/T
                # effects applied to the old one end here (a dead creature card is
                # printed: Carrion Grub); grants, preventions and control end below.
                # Handles are stable across zones, so the records keyed on this one
                # are cut. The snapshot above answers for the old object.
                self.ledger.forget(event.subject)
                self.layers.forget_materialized(event.subject)
            elif event.zone_move[1] == ZONE_BATTLEFIELD:
                self.departed_lki.pop(event.subject, None)  # a new object (CR 400.7)
            if event.zone_move[1] != ZONE_BATTLEFIELD and event.subject in self.world.cards:
                # CR 122.2: "Counters on an object are not retained if that
                # object moves from one zone to another ... they simply cease to
                # exist." The journal row above was emitted first, so a dies row's
                # was-P/T still folds them. A battlefield entry keeps what its
                # entry stamped (the loyalty seed, EtBState counters).
                self.world.cards[event.subject].counters.clear()
            if from_state != ZONE_BATTLEFIELD:
                if event.zone_move[1] == ZONE_BATTLEFIELD:
                    # The compiled EtBState node ("enters the battlefield
                    # tapped", "enters with a soul counter", "As this
                    # enchantment enters, choose a card name"). CR 614.1c:
                    # the entered state is stamped as the permanent
                    # enters, BEFORE its ETB triggers go on the stack (this
                    # runs at the atom boundary, the binder drains at the
                    # settle).
                    self._apply_etb_state(event.subject)
                continue
            anchor = event.subject
            self.ledger.expire_leaves(anchor)
            self.layers.expire_leaves(anchor)
            self.replacements.expire_leaves(anchor)
            self.etb_x.pop(anchor, None)  # the cast X leaves with it
            # CR 400.7: so does the name it chose as it entered; a return is a new object that
            # chooses again.
            self.name_choices.pop(anchor, None)
            self.damage.pop(anchor, None)  # CR 120.6: marks leave with it
            self.damage_deathtouch.discard(anchor)  # the deathtouch flag too
            # Status leaves with the permanent. CR 110.5d: cards not on the
            # battlefield are neither tapped nor untapped; 110.5b: a permanent
            # enters untapped unless something says otherwise (an "enters
            # tapped" stamp lands after the move). One CardState spans every
            # zone, so without this a creature bounced, exiled or reanimated
            # while tapped would come back tapped.
            if anchor in self.world.cards:
                self.world.cards[anchor].tapped = False
            # CR 506.4: a permanent that leaves the battlefield is removed
            # from combat: a dead attacker stops attacking (it leaves the
            # attack record) and a dead blocker stops blocking.
            self._remove_from_combat({anchor})
            self.mandates.discard(anchor)
            self.mandate_block.discard(anchor)
            # The timed (resolved-layer) twin of the two discards above; a
            # returning creature is a new object (CR 400.7). The same for the
            # resolved preventions and replacement designations.
            self.layers.forget_departed(anchor)
            self.replacements.forget_departed(anchor)
            self.damage_policies.pop(anchor, None)
            # A departing permanent drops every control entry keyed on
            # it — as CREATURE (the stolen card itself) or as ANCHOR (the
            # aura/source whose leaving ends the effect, CR 611.3's duration
            # reading for Enthralling Hold's missing Duration node).
            self._expire_control(creature=anchor, anchor=anchor)
            if event.zone_move[1] != ZONE_BATTLEFIELD:
                # CR 610.3: "until ~ leaves the battlefield" ends.
                due.extend(self.returns.end_leaves(anchor))
        if due:
            self._run_returns(due)

    def _run_returns(self, rows: list[ReturnRow]) -> None:
        """CR 610.3: the second one-shot effect of a zone move
        "until" an event, created immediately after that event.

        Each row whose object is still the object the move put there returns
        it to its previous zone, its owner's: a card that left that zone since
        is a new object and stays where it is (400.7), and a token has ceased
        to exist (704.5d). It goes onto the battlefield under its owner's
        control (610.3c: ``Zone(..., OWNER)``). The rows that ended together
        return together (610.3d): one MOVE_ZONE per destination zone moves all
        of that zone's objects at once, through the normal move path, so
        replacement effects apply (614: Containment Priest exiles a returning
        creature instead) and a returning Aura's owner chooses what it
        enchants as it enters, or it stays in exile (303.4f-g,
        ``_v_move_zone``)."""
        live = [
            row
            for row in sorted(rows, key=lambda r: r.seq)
            if self.returns.still_there(self, row)
        ]
        for zone in _RETURN_ZONES:
            group = [row for row in live if row.previous_zone == zone]
            if not group:
                continue
            first = group[0]
            atom = Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(len(group)),
                                SelectorMode.TARGET,
                                FAnd(()),
                                zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                            ),
                        ),
                        ("destination", Zone(_RETURN_ZONE_KIND[zone], ControllerRef.OWNER)),
                    )
                ),
            )
            ctx = self._ctx(
                source=first.source,
                controller=first.controller,
                bindings={"cards": [row.card for row in group]},
                decisions=(),
            )
            self._run_effect(atom, ctx)

    def run_as_enters(self, card: Handle, effect: Effect) -> None:
        """Run ``card``'s "As this enters" effect (an EtBState ``effect``). CR 614.1c, 614.12a:
        "As this enchantment enters, choose a card name" is a replacement effect, not a trigger:
        its controller chooses as it enters, without the stack and before anyone receives
        priority, so the permanent is never on the battlefield with the choice unmade (Runed
        Halo's protection reads it). The entry hook (:meth:`_apply_etb_state`) runs it before the
        entered tapped state and counters; the card probe runs it alone on its board's card,
        which is put on the battlefield without entering.

        Only the choice verb whose cards have tests (CHOOSE_NAME) runs. Any other effect would run
        inside the zone-change bookkeeping (:meth:`_on_zone_changes`) with nothing testing it
        there, so it raises until a card that needs it (Sutured Ghoul, Devouring Hellion, Rescuer
        Sphinx) brings its own tests."""
        if not (isinstance(effect, Atom) and effect.verb is Verb.CHOOSE_NAME):
            raise NotImplementedError(
                "executor: an \"As this enters\" effect runs only as CHOOSE_NAME; "
                f"{effect!r:.80} would run inside the zone-change bookkeeping, untested there"
            )
        self._run_effect(
            effect,
            self._ctx(source=card, controller=self.controller_of(card), bindings=None, decisions=()),
        )

    def _apply_etb_state(self, card: Handle) -> None:
        """Stamp the compiled EtBState node on a permanent the journal
        just saw ENTER the battlefield: what is done as it enters (its
        ``effect``, :meth:`run_as_enters`), then the tapped flag
        and any initial counters (CR 614.1c — part of the entering state, not
        a trigger, so no TAP event is emitted and nothing is re-journalled;
        the move's own journal row already carries the entry). A card whose
        record is not registered has no declared entered state."""
        record = self.binder.records.get(self.world.cards[card].identity.oracle_id)
        if record is None:
            return
        for node in record.abilities:
            if not isinstance(node, EtBState):
                continue
            if node.condition is not None:
                # CR 614.1c: gated entering state — "if this
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
            if node.effect is not None:
                self.run_as_enters(card, node.effect)
            if node.tapped:
                self.world.cards[card].tapped = True
            for kind, quantity in node.initial_counters:
                # "Enters with X +1/+1 counters"
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
                if self.replacements.prevents_counter_placement(qctx, card, kind) is not None:
                    continue  # CR 122.6: entering with counters is putting them on it (Blightbeetle)
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

    # ------------------------------------------------------------- triggers

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
        """Put the waiting triggers on the stack and let both players pass
        until it is empty (:meth:`_settle`). Decisions arrive through the
        executor's stream: may-offers hit the vocabulary-addressed lanes,
        nothing positional is consumed. Returns the number of triggered
        abilities resolved."""
        return self._settle()

    # ----------------------------------------- damage marks + state checks

    def mark_damage(self, card: Handle, n: int, deathtouch: bool = False) -> None:
        """Mark ``n`` damage on a card (CR 120.4). The mark STAYS — marked
        until the permanent leaves the battlefield (CR 120.6) or the cleanup
        step removes it (CR 514.2); destruction is the state-based check
        below, never the dealing of the damage itself. ``deathtouch``
        (CR 702.2b): damage from a deathtouch source is LETHAL damage no
        matter the amount, so the flag rides the ledger for the SBA."""
        if n <= 0:
            return
        self.damage[card] = self.damage.get(card, 0) + n
        if deathtouch:
            self.damage_deathtouch.add(card)

    def _lethal_creatures(self) -> list[Handle]:
        """CR 704.5f-h read over the battlefield (Handle-sorted): a
        creature marked with damage >= its LIVE toughness, or with any
        deathtouch damage, dies unless it has indestructible (CR 702.12b);
        toughness <= 0 kills even an indestructible creature. A permanent
        with no toughness (lands, non-creature artifacts) is not a
        creature-side death at all."""
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
                        or card in self.damage_deathtouch  # CR 702.2b
                    )
                    and not (self.layers.keyword_of(card, Keyword.INDESTRUCTIBLE))
                ):
                    dying.append(card)
        return sorted(dying)

    def _cease_tokens(self) -> list[Handle]:
        """CR 704.5d: "If a token is in a zone other than the battlefield, it
        ceases to exist" (111.7, 111.8). A dead, bounced or exiled token is not a
        card in a graveyard, hand or exile: it leaves the world, so graveyard counts
        and "target creature card from your graveyard" never see it. A token on the
        stack is not a thing in this engine (spell copies are not tokens). No journal
        row: ceasing to exist is not a zone change and triggers nothing. Returns the
        tokens removed (Handle-sorted).

        State-based actions run before triggered abilities resolve (CR 117.5),
        so a token's own leave triggers can still be queued here. A token
        a queued firing names (its source, or its event's subject or cause) waits
        for the next check after that firing resolves: the engine keeps it as the
        last-known information those triggers read (CR 603.10a)."""
        world = self.world
        pending = self.binder.pending_references()
        gone: list[Handle] = []
        for player in world.player_order:
            for kind, zone in world.players[player].zones.items():
                if kind in (ZONE_BATTLEFIELD, ZONE_STACK):
                    continue
                for card in list(zone.entries):
                    if world.cards[card].identity.is_token and card not in pending:
                        zone.entries.remove(card)
                        gone.append(card)
        for card in gone:
            del world.cards[card]
            self.binder.handle_record.pop(card, None)
            self.attachments.pop(card, None)
        return sorted(gone)

    def _unattached_auras(self) -> list[Handle]:
        """CR 704.5m: an Aura on the battlefield that isn't attached
        is put into its owner's graveyard. Attachment state is the
        executor's one ``attachments`` table (the IS_ATTACHED_TO_SOURCE
        oracle); the binder drops edges whose host left, so a MISSING edge
        is the unattached read. Detection is the ENCHANT keyword on the
        printed identity (the aura marker — equipment carry EQUIP and are
        NOT swept: an unattached Equipment legally stays on the
        battlefield, CR 301.5). The Aura goes to the graveyard of the player
        whose battlefield holds it: the world has no owner field, so that
        zone's player stands in for the owner, as in the other lanes of the
        check."""
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
                    # CR 702.16c, 704.5m: an Aura attached to a permanent with
                    # protection from it is attached to an illegal object.
                    or protected_from(self, host, card)
                ):
                    out.append(card)
        return sorted(out)

    def _protected_equipment(self) -> list[Handle]:
        """CR 704.5n: the Equipment attached to an illegal permanent (Handle-sorted).
        The sweep unattaches them; they stay on the battlefield, and the next
        recompute ends the equipped bonuses. Illegal means (CR 301.5, 301.5c): the
        host is not a creature (Riddleform once its "until end of turn" animation
        ends), the Equipment is itself a creature (nothing here has reconfigure),
        or the host has protection from the Equipment (CR 702.16d). Creature
        is the live type line, the GRANT_TYPE overlay included: the TYPE_EQ
        reading attack legality uses. A phased-out Equipment does not exist (CR
        702.26b)."""
        world = self.world
        creature = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        freed: list[Handle] = []
        for card, host in self.attachments.items():
            if (
                card not in world.cards
                or "EQUIP" not in world.cards[card].identity.keywords
                or world.zone_of(card).kind != ZONE_BATTLEFIELD
                or card in self.phased_out
            ):
                continue
            ctx = self._ctx(
                source=card, controller=self.controller_of(card), bindings=None, decisions=()
            )
            if (
                not eval_filter(creature, host, ctx)
                or eval_filter(creature, card, ctx)
                or protected_from(self, host, card)
            ):
                freed.append(card)
        return sorted(freed)

    def _zero_loyalty_walkers(self) -> list[Handle]:
        """CR 704.5i: planeswalkers on the battlefield with 0 or less
        loyalty, whatever brought it there: damage, counter removal
        (Pestilent Haze) or a loyalty cost paid down to 0 (the counter verb
        keeps a zeroed LOYALTY key). A missing key reads the printed
        loyalty, never 0 (``legality._loyalty_of``)."""
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

    def _legend_rule_groups(self) -> list[tuple[Handle, list[Handle]]]:
        """CR 704.5j, the legend rule: every ``(player, permanents)``
        where that player controls two or more legendary permanents with the
        same name, Handle-sorted inside, in APNAP order of the choosing
        players (CR 101.4) and then by name. Legendary is the printed
        supertype word plus any live GRANT_TYPE overlay (the SUPERTYPE_EQ
        reading); control is the effective one (the GAIN_CONTROL overlay).
        A token copy is a legendary permanent like any other."""
        from MTG_bot.core.executor.quantity import _type_line_tokens
        from MTG_bot.core.executor.selectors import apnap_order

        world = self.world
        named: dict[tuple[Handle, str], list[Handle]] = {}
        for zone_player in world.player_order:
            for card in world.players[zone_player].zone(ZONE_BATTLEFIELD).entries:
                identity = world.cards[card].identity
                words = set(_type_line_tokens(identity.type_line))
                words.update(self.layers.type_overlay(card))
                if "Legendary" not in words:
                    continue
                named.setdefault((self.controller_of(card), identity.name), []).append(card)
        groups = [(p, name, sorted(cards)) for (p, name), cards in named.items() if len(cards) > 1]
        order = apnap_order(world, sorted({p for p, _name, _cards in groups}))
        groups.sort(key=lambda g: (order.index(g[0]), g[1]))
        return [(p, cards) for p, _name, cards in groups]

    def _legend_rule_losers(self, groups: list[tuple[Handle, list[Handle]]]) -> list[Handle]:
        """CR 704.5j: the player chooses which one stays, asked under
        ``legend:<seat>:<digest>`` over the same-name permanents (the
        vocabulary is the live group, two or more, so never a phantom); the
        rest are returned, to be put into their owners' graveyards."""
        losers: list[Handle] = []
        for player, cards in groups:
            vocab = tuple(str(h) for h in cards)
            ctx = self._ctx(source=player, controller=player, bindings=None, decisions=())
            kept = ctx.take_decision(vocab, f"legend:{player}:{site_digest(vocab)}")
            losers.extend(h for h in cards if str(h) != kept)
        return sorted(losers)

    def _player_losses(self) -> None:
        """The player-loss state-based actions, the first lane of every check
        (CR 704.3): a player with 0 or less life (704.5a), or who attempted to
        draw from an empty library since the last check (704.5b), loses. Each
        loser joins ``lost_players`` with a GAME_LOST row saying why. When at
        most one player is left, the game is over (CR 104.2a; everyone at
        once is a draw, 104.4a) and :class:`GameOver` ends it at this check.
        A LOSE_GAME effect ended a two-player game when it resolved, so nobody
        else loses at the check after it."""
        players = self.world.player_order
        remaining = [p for p in players if p not in self.lost_players]
        if len(remaining) > 1:
            for player in remaining:
                if self.world.players[player].life <= 0:
                    why = "LIFE"
                elif player in self.drew_from_empty:
                    why = "EMPTY_LIBRARY"
                else:
                    continue
                self.lost_players.append(player)
                self.journal.emit(KIND_GAME_LOST, player, None, "STATE_CHECK", (why,))
        self.drew_from_empty.clear()
        if self.lost_players and sum(p not in self.lost_players for p in players) <= 1:
            raise GameOver(", ".join(str(p) for p in self.lost_players))

    def _state_checks(self) -> int:
        """The state-based action check (CR 704.3), run at every settle
        point: player losses (704.5a/b), tokens off the battlefield
        (704.5d), lethal creatures (704.5f-h), unattached Auras (704.5m),
        zero-loyalty planeswalkers (704.5i), the legend rule (704.5j) and
        illegally attached Equipment (704.5n). Lethal creatures die here,
        when the thing that hurt them has finished, not inside the damage
        atom. Every action of one check happens at once (704.3), so the
        legend-rule choices are made before anything moves, and each batch
        is journalled as its OWN atom boundary (cause ``None``: an SBA has
        no card behind it, coverage credits none) so dies triggers see the
        was-P/T snapshot.

        CR 704.3, 117.5: the check repeats until no action applies BEFORE
        any triggered ability resolves. The triggers a batch causes (a
        creature's dies trigger) are matched and queued here, and the
        settle resolves them afterwards, checking again after each one.
        Returns the number of batches performed."""
        batches = 0
        while True:
            # CR 704.5a/b: a player who loses here ends a two-player game.
            self._player_losses()
            # CR 704.5d, 111.7: a token off the battlefield ceases to exist;
            # one whose leave triggers are still queued waits for them.
            self._cease_tokens()
            self.layers.recompute()  # live keywords/toughness must be current
            dying = self._lethal_creatures()
            unattached = self._unattached_auras()  # CR 704.5m
            walkers = self._zero_loyalty_walkers()  # CR 704.5i
            legends = self._legend_rule_groups()  # CR 704.5j
            freed = self._protected_equipment()  # CR 704.5n
            if (
                not dying
                and not unattached
                and not walkers
                and not legends
                and not freed
            ):
                return batches
            # A permanent another lane of this check already removes is not
            # moved twice (a lethally damaged copy the player did not keep).
            taken = set(dying) | set(unattached) | set(walkers)
            legend_losers = [
                h for h in self._legend_rule_losers(legends) if h not in taken
            ]
            before = self.journal.snapshot()
            start = len(self.events)
            # CR 704.5n: checked in the same snapshot as the other actions
            # (CR 704.3, simultaneous); the Equipment stays on the battlefield and
            # the next pass, after the recompute, sees the equipped bonuses gone.
            for card in freed:
                host = self.attachments.pop(card)
                self.events.append(
                    (len(self.events), "STATE_CHECK", str(card), f"UNATTACHED:{host}")
                )
            # Dies-window replacements (Scorching Dragonfire) are consulted
            # BEFORE the graveyard move, the die-lane twin of the damage and
            # life replacements in verbs.py. A matched death is NOT moved —
            # the record's ACTION (the exile) runs as its own journalled atom
            # in this iteration's drain below. A replaced death emits no
            # BATTLEFIELD->GRAVEYARD diff, so no CREATURE_DIES row.
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
                # The zeroed LOYALTY key is DELETED on the way out (an exile
                # replacement below is a way out too); a battlefield re-entry
                # seeds the printed loyalty with setdefault
                # (TriggerBinder._register).
                self.world.cards[card].counters.pop("LOYALTY", None)
                # CR 704.5i + 700.4: the zero-loyalty SBA puts the
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
            for card in legend_losers:
                # CR 704.5j: the ones not kept go to their owners'
                # graveyards. From the battlefield to a graveyard is dying
                # (CR 700.4), so the dies-window replacements apply as in the
                # lanes above. A walker's loyalty key goes with it (a new
                # object on re-entry, the zero-loyalty lane's convention).
                self.world.cards[card].counters.pop("LOYALTY", None)
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
                    (len(self.events), "STATE_CHECK", str(card), "LEGEND_RULE")
                )
            new_events = self.journal.record_atom(
                before, None, "STATE_CHECK", self.events[start:]
            )
            self._on_zone_changes(new_events)
            # Drain the consumed deaths — each replacement's ACTION is
            # its OWN atom boundary (the _run_effect damage-lane pattern),
            # with the CR 614.5 guard on the inner ctx and the dead card
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
            # Queue the triggers this batch caused; they resolve once the
            # check is stable (the settle's drain).
            self.binder.on_events()
            batches += 1

    def _priority_check(self) -> None:
        """CR 117.5, the check made each time a player would receive
        priority: the state-based actions (CR 704.3, repeated until none
        applies), then every ability that triggered since the last check goes
        on the stack (CR 603.3, ``TriggerBinder.put_waiting``), and again,
        until neither happens. Putting a trigger on the stack can itself
        trigger ("becomes the target"). While an effect ends the turn the
        binder holds the triggers (CR 724.1c)."""
        while True:
            self.binder.on_events()
            self._state_checks()
            if self.binder.hold or not self.world.triggers:
                break
            self.binder.put_waiting()
        if not self.stack.frames:  # the tripwire counts since the stack was last empty
            self._loop_fires, self._loop_sources = 0, {}

    def _resolve_top(self) -> int:
        """The top object of the stack resolves (CR 608, ``stack.resolve_top``), behind the
        trigger-loop tripwire every driver shares (the undriven :meth:`_settle` and the game
        loop's :meth:`all_pass`): once ``MAX_TRIGGER_FIRES`` triggered abilities have resolved
        since the stack was last empty, the source that resolved most is quarantined instead
        (its objects leave the stack and its firings stop, ``TriggerBinder.quarantine``), and
        play goes on. Returns 1 when a triggered ability resolved, else 0."""
        from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES
        from MTG_bot.core.executor.stack import resolve_top

        top = self.stack.frames[-1]
        triggered = top.spell_kind == "TRIGGERED"
        if triggered:
            if self._loop_fires >= MAX_TRIGGER_FIRES:
                self.binder.quarantine(self._loop_sources)
                self._loop_fires = 0
                return 0
            assert top.source is not None
            self._loop_sources[top.source] = self._loop_sources.get(top.source, 0) + 1
            self._loop_fires += 1
        resolve_top(self)
        return int(triggered)

    def _settle(self, floor: int = 0) -> int:
        """Both players pass until the stack is down to ``floor`` objects
        (DESIGN_PRIORITY §11, the undriven auto-pass): at each priority point
        the CR 117.5 check (:meth:`_priority_check`), then the top object
        resolves (CR 117.4, 608; ``stack.resolve_top``), and an effect that
        ended the turn ends it there (CR 724.1). A spell an effect casts
        outside a game loop resolves inside that resolution, down to the
        depth it found (``stack.cast_card``). Returns the number of triggered
        abilities resolved.

        The trigger-loop tripwire is :meth:`_resolve_top`'s, shared with the
        game loop's :meth:`all_pass`.

        The settle tail is also the recompute point: WHILE-condition truth is
        re-evaluated on the ledger, and the layer registry re-reads the set
        (new/lost members, condition toggles) and rebuilds the keyword /
        granted-ability oracles. All of it is a pure function of the
        journal's final state, so replays are byte-identical."""
        fired = 0
        while True:
            self._priority_check()
            if len(self.stack.frames) <= floor:
                break
            fired += self._resolve_top()
            self._consume_end_turn()
        self.ledger.settle_while(self._while_eval)
        self.layers.recompute()
        return fired

    def _finish_op(self) -> None:
        """The end of a public op. CR 724.1: when the op's own effect
        ended the turn, the turn ends BEFORE any settle, so the abilities
        its resolution triggered cease to exist (724.1a) instead of
        resolving; otherwise, outside a game loop, both players pass
        (:meth:`_settle`), then any request a trigger made during it ends
        the turn. In a game loop the loop gives priority next (CR 117.3c).
        An op made inside an action or a resolution (:meth:`atomic`: a mana
        ability activated while paying) leaves all of it to the action's
        end."""
        if self._resolving:
            return
        if self._consume_end_turn() or self.driven:
            return
        self._settle()
        self._consume_end_turn()

    @contextmanager
    def holding_priority(self) -> Iterator[None]:
        """Outside a game loop: the ops made inside end with their player keeping
        priority (CR 117.3c) and nobody passing, so what they put on the stack
        waits there for the next op to respond to. An op made after it ends
        with both players passing until the stack is empty, as usual."""
        was, self.driven = self.driven, True
        try:
            yield
        finally:
            self.driven = was

    def all_pass(self) -> None:
        """Every player passes in succession (CR 117.4), after the CR 117.5
        check: the top object of the stack resolves and the active player
        receives priority (CR 117.3b); with an empty stack the step ends. The
        resolution is behind the trigger-loop tripwire (:meth:`_resolve_top`)."""
        self._priority_check()
        self.passes = 0
        if not self.stack.frames:
            self._end_step()
            return
        self._resolve_top()
        if self._consume_end_turn():
            return  # a fresh cleanup step, where no player has received priority yet
        if self.phase != TURN_ENDED:
            self.priority_holder = self.world.active_player

    def _consume_end_turn(self) -> bool:
        """An END_TURN atom only SETS the request flag (mid-op state
        must not change under the atoms still running); the turn ends at the
        op boundary (:meth:`_finish_op`) through :meth:`_end_the_turn`.
        Returns whether the turn ended here. In every step of the turn, its
        end and cleanup steps included: the objects still on the stack are
        exiled at once (CR 724.1b), never left to resolve while the step
        runs on (KNOWLEDGE/2026-11-12/197: Discontinuity in the end step let
        a removal spell below it resolve). Outside a turn there is no turn
        to end and the request is dropped."""
        if not self.end_turn_requested:
            return False
        self.end_turn_requested = False
        if not self.turn_open:
            return False
        self._end_the_turn()
        return True

    def _end_the_turn(self) -> int:
        """CR 724.1: an effect ends the turn. 724.1a-d run first
        (:meth:`_end_the_turn_process`); then the game skips straight to the
        cleanup step (724.1d). The end step is skipped, so no END_TURN
        marker is journalled and "at the beginning of the end step"
        abilities do not trigger (724.1e). The triggers from the process
        resolve in the cleanup step, and another cleanup step follows
        (724.1f, CR 514.3a). The turn is still in progress until its cleanup
        ends. Returns the firing count."""
        self._end_the_turn_process()
        self.declaring = False
        self._begin_step(CLEANUP)
        if self.driven:
            return 0  # the game loop runs the cleanup step
        return self.pass_until(TURN_ENDED)

    def _end_the_turn_process(self) -> None:
        """CR 724.1a-d, the part of ending the turn before its cleanup step.
        724.1a: the abilities that triggered before the process began and
        were never put onto the stack cease to exist. 724.1b: every object
        on the stack is exiled. 724.1c: state-based actions are checked, and
        no triggered ability is put onto the stack (the binder holds the
        firings for the cleanup step). 724.1d: the current step ends, so
        unspent mana empties (CR 500.5), and every creature leaves
        combat."""
        self.end_turn_requested = False
        self.binder.cease_triggered_before(self.end_turn_mark)
        self._exile_the_stack()
        self.binder.hold = True
        try:
            self._state_checks()
        finally:
            self.binder.hold = False
        self.empty_mana_pools()  # 724.1d: the current step ends (CR 500.5)
        self._leave_combat()  # 724.1d: every creature leaves combat (defending player too)

    def _exile_the_stack(self) -> None:
        """CR 724.1b: every object on the stack is exiled, the resolving one
        included. A resolving spell goes to exile at its own put
        (stack.resolve_top). A spell still waiting on the stack below it is
        exiled here and its object removed, so the cast that pushed it never
        resolves it; an ability on the stack ceases to exist."""
        frames = list(self.stack.frames)
        if not frames:
            return
        self.stack.frames.clear()  # removed from the stack: none resolves
        before = self.journal.snapshot()
        start = len(self.events)
        for frame in frames:
            if frame.spell_kind in ("ACTIVATED", "TRIGGERED"):
                continue  # an ability is no card: it ceases to exist
            if self.world.zone_of(frame.handle).kind == ZONE_STACK:
                self.world.move_to_zone(frame.handle, frame.controller, ZONE_EXILE)
                self.events.append(
                    (len(self.events), "MOVE", str(frame.handle), "stack->exile")
                )
        self._on_zone_changes(
            self.journal.record_atom(before, None, "END_TURN", self.events[start:])
        )

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

    # -------------------------------------------------------- turn skeleton
    #
    # The executor-owned turn: active rotation, the world.turn clock and the
    # step machine below (every step of CR 500.1, with priority), and the
    # phase markers the grammar has triggers for: UPKEEP, FIRST_MAIN and
    # COMBAT at the beginning of a turn's work, END_TURN at the end of one.
    # The untap step is a RULE step, not an Atom: it mutates the world
    # directly and journals one TapStateEvent per untap, so "whenever a
    # creature untaps" triggers and the fingerprint see it.

    def begin_turn(self, player: Handle) -> int:
        """Begin ``player``'s turn: active rotation, turn clock, per-turn event
        trackers reset, then the untap, upkeep and draw steps (CR 502-504) with
        both players passing (the undriven auto-pass, DESIGN_PRIORITY §11), up
        to the first main phase with an empty stack. Returns how many triggered
        abilities resolved. Each step resolves its own triggers: the upkeep's
        before the draw step (CR 503.1a, 504), the draw step's before the main
        phase. The first turn of a two-player game has no draw step (CR
        103.8a)."""
        self.start_turn(player)
        return self.pass_until(FIRST_MAIN)

    def start_turn(self, player: Handle) -> None:
        """``player``'s turn begins (active rotation, turn clock, per-turn
        event trackers reset) with its untap step; a game loop then runs it
        (CR 500.1)."""
        if player not in self.world.players:
            raise ValueError(f"begin_turn: {player} is not a player of this world")
        # CR 103.8a: in a two-player game the player who plays first skips the
        # draw step of their first turn (103.8c: in other multiplayer games
        # nobody skips it).
        self._skip_draw = not self._turn_started and len(self.world.player_order) == 2
        if self._turn_started:
            self.world.turn += 1
        self._turn_started = True
        self.world.active_player = player
        self.turn_open = True
        self.journal.begin_turn(player)
        self._begin_step(UNTAP)

    # ------------------------------------------------ the step machine (CR 500-514, 117)
    #
    # ``phase`` is the current step (legality's step names), ``tba_done`` whether
    # its turn-based actions ran, ``priority_holder`` and ``passes`` CR 117's
    # priority: who holds it and how many players passed in succession; and
    # ``first_strikers`` the creatures that had first or double strike as the
    # first combat damage step began (CR 510.4). All of it is replayed state,
    # folded into state_fingerprint, so a game stopped at a priority point
    # resumes there. ``begin_turn``, ``combat_attacks``, ``combat_blocks``,
    # ``end_turn`` and ``advance_turn`` run it with both players passing.

    def _begin_step(self, step: str) -> None:
        self.phase = step
        self.tba_done = False
        self.priority_holder = None
        self.passes = 0
        self.step_actions = {}

    def pass_priority(self) -> None:
        """The player holding priority passes (CR 117.3d): the next player in
        turn order receives it, or, every player having passed in succession,
        :meth:`all_pass`. In a game loop; the loop gives priority next."""
        self.passes += 1
        if self.passes >= len(self.world.player_order):
            self.all_pass()
            return
        order = self.world.player_order
        assert self.priority_holder is not None
        self.priority_holder = order[(order.index(self.priority_holder) + 1) % len(order)]

    def acted(self, seat: Handle) -> None:
        """``seat``, holding priority, cast a spell, activated an ability or
        played a land: it receives priority again (CR 117.3c), and the passes
        in succession start over. Counted per player and step (the act cap,
        ``games.MAX_ACTS_PER_STEP``)."""
        self.priority_holder = seat
        self.passes = 0
        self.step_actions[seat] = self.step_actions.get(seat, 0) + 1

    def _to_priority(self) -> bool:
        """Run the game on until a player receives priority (CR 117.3a-b): the
        current step's turn-based actions if they have not run, a step in which
        nobody receives priority ended at once, then the CR 117.5 check. False
        when the turn has ended instead."""
        while self.phase != TURN_ENDED:
            if not self.tba_done:
                self.tba_done = True
                if not self._turn_based_actions():
                    self._end_step()
                    continue
                self.priority_holder = self.world.active_player
                self.passes = 0
            self._priority_check()
            return True
        return False

    def pass_until(self, step: str, *, waiting: bool = False) -> int:
        """Both players pass at every priority point (the undriven auto-pass)
        until ``step`` holds priority with an empty stack, or the turn has
        ended. ``waiting``: stop at ``step``'s next priority point instead,
        before anyone passes there. Called before the step begins, that is
        its first: its turn-based actions done and what they triggered on
        the stack (CR 117.3b, 117.5), where a game loop asks the active
        player (games._play_turns). Returns how many triggered abilities
        resolved."""
        fired = 0
        while self._to_priority():
            if waiting and self.phase == step:
                break
            fired += self._settle()
            if self.phase in (step, TURN_ENDED):
                break
            self._end_step()  # every player passed with an empty stack (CR 117.4)
        return fired

    def _turn_based_actions(self) -> bool:
        """The current step's turn-based actions (CR 703.4). Returns whether
        players receive priority in it: not in the untap step (CR 502.4), and in
        a cleanup step only when state-based actions or triggers happen there
        (CR 514.3a)."""
        step = self.phase
        active = self.world.active_player
        if step == UNTAP:
            assert active is not None
            self._untap_step(active)
            # "Until your next turn" ends as the turn begins (CR 611.2a); zone
            # moves "until your next turn" return now (CR 610.3). What they
            # trigger waits for the upkeep (CR 503.1a).
            self.ledger.expire_until_next_turn(active)
            self.layers.expire_until_next_turn(active)
            self.replacements.expire_until_next_turn(active)
            returning = self.returns.end_next_turn(active)
            if returning:
                self._run_returns(returning)
            return False
        if step == DRAW:
            # The draw (CR 504.1), journalled inside the skeleton so "whenever
            # you draw" triggers and the fingerprint see it.
            assert active is not None
            self._turn_draw(active)
            return True
        if step == BEGIN_COMBAT:
            # CR 506.2: in a two-player game the non-active player defends.
            self.defending_player = next(
                (p for p in self.world.player_order if p != active), None
            )
        if step in (UPKEEP, FIRST_MAIN, BEGIN_COMBAT, END_STEP):
            # The marker "at the beginning of ..." triggers read.
            self.journal.record_turn_phase(step)
            return True
        if step == DECLARE_ATTACKERS:
            # CR 508.1. The declare window stays open for the whole step, so the
            # enters-attacking tokens attack triggers create join the attack
            # (CR 508.1i).
            assert active is not None
            self._op_seq += 1
            self._declare_group = self._op_seq
            self.declaring = True
            self._declare_attackers(active)
            return True
        if step == DECLARE_BLOCKERS:
            assert active is not None
            self._declare_blockers(active)  # CR 509
            return True
        if step == FIRST_STRIKE_DAMAGE:
            # CR 510.4: only creatures with first or double strike deal damage
            # in the first combat damage step.
            self.first_strikers = frozenset(h for h in self._combat_dealers() if self._strikes_first(h))
            self._damage_wave(sorted(self.first_strikers))
            return True
        if step == COMBAT_DAMAGE:
            # CR 510.4: after a first-strike step, the creatures that had
            # neither first nor double strike as it began, and those that have
            # double strike now.
            done = self.first_strikers or frozenset()
            self._damage_wave(
                [
                    h
                    for h in self._combat_dealers()
                    if h not in done or self.layers.keyword_of(h, Keyword.DOUBLE_STRIKE)
                ]
            )
            return True
        if step == CLEANUP:
            return self._cleanup_actions()
        return True  # END_OF_COMBAT, the main phases: no turn-based action

    def _strikes_first(self, creature: Handle) -> bool:
        return self.layers.keyword_of(creature, Keyword.FIRST_STRIKE) or self.layers.keyword_of(
            creature, Keyword.DOUBLE_STRIKE
        )

    def _next_step(self, step: str) -> str:
        """The step after ``step`` (CR 500.1): no draw step in the first turn of
        a two-player game (CR 103.8a), no blockers and no damage without
        attackers (CR 508.8), a first-strike damage step when a creature in
        combat has first or double strike (CR 510.4), another cleanup step after
        one in which players received priority (CR 514.3a)."""
        if step == UPKEEP and self._skip_draw:
            return FIRST_MAIN  # CR 103.8a: the first player skips the draw step of the first turn
        if step == DECLARE_ATTACKERS:
            return DECLARE_BLOCKERS if self.attackers else END_OF_COMBAT
        if step == DECLARE_BLOCKERS:
            if any(self._strikes_first(h) for h in self._combat_dealers()):
                return FIRST_STRIKE_DAMAGE
            return COMBAT_DAMAGE
        if step == CLEANUP:
            return CLEANUP if self.priority_holder is not None else TURN_ENDED
        return _NEXT_STEP[step]

    def _end_step(self) -> None:
        """The current step ends (CR 500.4: unspent mana empties; CR 511.3: the
        end of combat removes every creature from combat) and the next begins.
        A turn ended by an effect is ended at the op boundary after it
        (``_consume_end_turn``); one still open here ends the same way."""
        if self._consume_end_turn():
            return
        step = self.phase
        self.empty_mana_pools()
        if step == DECLARE_ATTACKERS:
            self.declaring = False
        if step == END_OF_COMBAT:
            self._leave_combat()
        nxt = self._next_step(step)
        if nxt == TURN_ENDED:
            self.turn_open = False
        self._begin_step(nxt)

    def _jump_to(self, step: str) -> None:
        """A driver that skips ahead (``combat_attacks`` from a second main
        phase, ``end_turn`` before combat): the current step ends, combat
        included, and ``step`` begins."""
        self.empty_mana_pools()
        self.declaring = False
        if self.attackers or self.defending_player is not None:
            self._leave_combat()
        self._begin_step(step)

    def _leave_combat(self) -> None:
        """CR 511.3: as the end of combat step ends, all creatures are removed
        from combat. The attack record closes with the phase (CR 506.4: nothing
        "is attacking" once combat ended, and IS_ATTACKING reads exactly that);
        the statics that select attacking or blocking creatures ("Attacking
        creatures you control get +1/+0", Warded Battlements) are read again."""
        self.attackers = []
        self.attacked = {}
        self.blocked_by = {}
        self.defending_player = None
        self.first_strikers = None
        self.ledger.settle_while(self._while_eval)
        self.layers.recompute()

    def _cleanup_actions(self) -> bool:
        """The cleanup step's turn-based actions (CR 514.1-514.2), then CR
        514.3a: when state-based actions or triggers happen, players receive
        priority (True) and another cleanup step follows.

        514.1: the active player discards down to their maximum hand size
        (:meth:`_discard_to_hand_size`). 514.2: the end-of-turn expiry sweep:
        Eot ledger entries, Eot-tagged LAYER records (until-end-of-turn grants
        die here), PREVENTION records and control entries, the turn-window
        delayed triggers, marked damage, and the zone moves "until end of turn"
        return (CR 610.3). What the discard or the returns trigger waits for
        the 514.3a check, after the sweep."""
        self._discard_to_hand_size()
        self.ledger.sweep_at_eot()
        self.layers.sweep_at_eot()
        self.replacements.sweep_at_eot()
        self._expire_control(eot=True)  # Traitorous Greed's DurationEot
        self.damage.clear()  # CR 514.2 — cleanup removes marked damage
        self.damage_deathtouch.clear()  # the deathtouch flag too
        returning = self.returns.end_eot()
        if returning:
            self._run_returns(returning)
        self.binder.expire_delayed()
        # Rebuild the oracles after the sweep — a granted keyword that
        # expired at end of turn must not survive into next turn's
        # keyword_of/legal_activations.
        self.layers.recompute()
        journalled = len(self.journal.events)
        self._priority_check()  # CR 514.3a
        return bool(self.stack.frames) or len(self.journal.events) != journalled

    def _turn_draw(self, player: Handle) -> None:
        """The CR 504.1 draw of the active player's draw step.

        The grammar has no draw-step phase marker, so the skeleton runs the
        shared :data:`_TURN_DRAW` atom inline through the same journalled
        path a card's own draw uses: the DRAW handler calls
        :meth:`GameWorld.draw`, and the journal's diff of that atom boundary
        emits the zone change and the CARD_DRAWN row.

        Two deliberate omissions: no nested ``_settle`` (:meth:`begin_turn`
        settles right after this step, so the draw step's triggers resolve
        before the main phase) and no nested ``_consume_end_turn`` (an
        END_TURN requested by such a trigger closes at the next op boundary,
        never mid-skeleton). An
        empty library draws nothing here; ``_v_draw`` records the attempt
        and the state-based check of that settle makes the player lose (CR
        704.5b, :meth:`_player_losses`).

        ``source`` is the seat: no permanent drew this card, and the
        journal's cause column records the seat, which is what
        a 'you drew' trigger's APNAP controller already is."""
        self._op_seq += 1
        ctx = self._ctx(source=player, controller=player, bindings=None, decisions=())
        # The draw-step window. _v_draw stamps draw_step_ordinal only
        # while this flag is open; NOT_FIRST_DRAW_THIS_STEP (Teferi's Ageless
        # Insight condition, quantity.py) answers per that register. Cleared
        # unconditionally — a draw-armed trigger firing later sees the
        # window shut (the register is scoped to the step).
        self._draw_step_open = True
        self.draw_step_ordinal = {}
        try:
            self._run_effect(_TURN_DRAW, ctx)
        finally:
            self._draw_step_open = False

    def _untap_step(self, player: Handle) -> int:
        """The untap step. Every tapped permanent the ACTIVE player
        controls untaps — except one a live PREVENT/UNTIL_NEXT_STEP record
        vetoes (Frost Breath's freeze). Untapping is one simultaneous rule
        action, not a player choice, so the Handle-sorted loop is just its
        deterministic order (no APNAP ordering applies).
        AFTER the tick: UNTIL_NEXT_STEP(UNTAP) records are consumed by the
        step they just survived and terminal-expire — the freeze therefore
        survives EXACTLY one untap tick. Returns the untap count.

        CR 502.1: the phasing turn-based action comes FIRST, so
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
            if self.controller_of(card) != player:  # the effective controller
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

    # ------------------------------------------------------ the COMBAT phase
    #
    # The beginning of combat, declare attackers (each attacks the defending
    # player or a planeswalker that player controls, CR 506.2, 508.1b; the
    # attack ask names the choice), declare blockers (CR 509), the combat
    # damage step or steps with the CR
    # 510 assignment asks (TRAMPLE, DEATHTOUCH, the Herald AS_UNBLOCKED
    # policy) and the end of combat, each a step of the machine with its
    # priority point (CR 117.3a, 704.3).

    def combat_step(self, seat: Handle) -> int:
        """Run the active player's whole COMBAT phase (CR 506-511) with both
        players passing: :meth:`combat_attacks` then :meth:`combat_blocks`; the
        split is the search substrate's ``pre_blocks`` boundary (games._play).
        Returns the trigger-firing count."""
        return self.combat_attacks(seat) + self.combat_blocks(seat)

    def combat_attacks(self, seat: Handle) -> int:
        """The beginning of combat step (CR 507: the marker "at the beginning
        of combat" triggers read) and the declare attackers step (CR 508: one
        ask per legal creature, whole-set validated, mandates narrowing the
        vocab; a creature with no legal declaration is never asked, a mandatory
        attacker is not offered DECLINE), with both players passing, up to the
        declared attack with an empty stack. Leaves ``attackers`` and
        ``defending_player`` set for :meth:`combat_blocks`. Returns the
        trigger-firing count."""
        self.start_combat(seat)
        return self.pass_until(DECLARE_ATTACKERS)

    def start_combat(self, seat: Handle) -> None:
        """``seat``'s combat phase begins, after the checks: its beginning of
        combat step (CR 507) starts, unless that step or the declare attackers
        step is already the current one. Nobody passes here; a driver runs
        the steps (:meth:`combat_attacks`, or :meth:`pass_until`)."""
        world = self.world
        if not self.turn_open:
            raise ValueError(f"combat_step: no turn is open ({seat})")
        if self.phase in (END_STEP, CLEANUP):
            raise ValueError(f"combat_step: this turn's combat is over ({self.phase})")
        if world.active_player != seat:
            raise ValueError(f"combat_step: {seat} is not the active player")
        if not any(p != seat for p in world.player_order):
            raise ValueError(f"combat_step: {seat} has no defending player")
        if self.phase not in (BEGIN_COMBAT, DECLARE_ATTACKERS):
            self._jump_to(BEGIN_COMBAT)

    def combat_blocks(self, seat: Handle) -> int:
        """The rest of the combat phase with both players passing (CR 509-511):
        declare blockers (CR 509: one ask per defending creature, candidates =
        the attackers it may legally block plus NONE, CR 509.1a untapped-only,
        whole-assignment validated), the combat damage step or steps with the
        CR 510 assignment asks (TRAMPLE, DEATHTOUCH, the Herald AS_UNBLOCKED
        policy), and the end of combat, up to the second main phase (CR 505.1).
        No blockers and no damage without attackers (CR 508.8). Returns the
        trigger-firing count; nothing when the turn has already ended."""
        del seat  # the active player's combat, as declared
        if self.phase == TURN_ENDED:
            return 0
        return self.pass_until(SECOND_MAIN)

    def _declare_attackers(self, seat: Handle) -> None:
        """The CR 508.1 asks + the whole-set check, then the
        declaration commit: tap everything that declared except the
        vigilance carriers (CR 702.20a), journalled as TapState rows
        BEFORE the declare rows (a "becomes tapped" trigger sits UNDER
        the attack triggers, CR 508.1m), then one DECLARE_ATTACKERS row
        per attacker - shared declare-group id, the binder's CR 603.2
        dedup key. Only untapped creatures are candidates (CR 508.1a;
        the tap that follows is not a cost, CR 508.1f); sickness reads the
        journal (legality.py).
        """
        world = self.world
        candidates = legal_attackers(self, seat)
        mandated = mandated_attackers(self, seat) & set(candidates)
        defender = self.defending_player
        assert defender is not None  # combat_step opens the phase with one
        # CR 506.2, 508.1b: when the defending player controls
        # planeswalkers, the active player announces what each attacker
        # attacks: ATTACK is the defending player, a planeswalker's handle
        # is that planeswalker. With none, the ask keeps its binary shape.
        walkers = self._attackable_walkers()
        chosen: list[Handle] = []
        attacking: dict[Handle, Handle] = {}
        for card in candidates:
            # A MANDATED attacker (must attack) is not offered DECLINE: the
            # policy cannot decline what the rules force, and with no
            # planeswalker to choose its one-word offer is taken without
            # asking. It still chooses what it attacks (CR 508.1d).
            vocab = ("ATTACK",) + tuple(str(w) for w in walkers)
            if card not in mandated:
                vocab += ("DECLINE",)
            ctx = self._ctx(source=card, controller=seat, bindings=None, decisions=())
            answer = offer_or_autopick(ctx, vocab, f"attack:{card}:{world.turn}")
            if answer == "DECLINE":
                continue
            chosen.append(card)
            attacking[card] = next(
                (w for w in walkers if str(w) == answer), defender
            )
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
        for card in chosen:
            self.attackers.append(card)
            self.attacked[card] = attacking[card]
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

    # ----------------------------------------------------- declare blockers

    def _declare_blockers(self, seat: Handle) -> None:
        """CR 509. ONE ask per defending creature that could legal-
        ly block at least one attacker, Handle-sorted, site
        ``block:<card>:<turn>``: the vocabulary is the attackers that perma-
        nent may block (CR 509.1a untapped-only, CR 509.1b one attacker per
        blocker, reach/menace/protection and the PREVENT_EFFECT restrictions
        — Tome Anima "can't be blocked", Pirate "can't block", Shacklegeist
        "can block only creatures with flying", Subira's activated target)
        plus the NONE option. A word (NONE too) is offered ONLY when the
        not-yet-asked candidates can still complete a declaration that
        violates no restriction (every menace attacker at 0 or 2+ blockers,
        CR 702.111b; none past its blocker limit, CR 509.1b) and obeys as
        many requirements as such a declaration can (CR 509.1c: a must-be-
        blocked attacker is one, obeyed by whichever creature blocks it).
        The test is a bipartite match over pair-LEGAL completions
        (``most_obeyed``). Every candidate keeps a word, and none is dropped
        because the answer would merely be inadvisable. Tapped creatures and
        creatures legal against nothing are never asked. Each committed pair
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
            return
        assigned: dict[Handle, list[Handle]] = {}
        candidates = sorted(
            card
            for card in sorted(world.cards)
            if self.controller_of(card) == defender
            and world.zone_of(card).kind == ZONE_BATTLEFIELD
            and blocker_askable(self, card, attackers)
        )
        if not candidates:
            return
        mandated = mandated_to_be_blocked(self) & set(attackers)
        by_word = {str(a): a for a in attackers}
        # The pair matrix is precomputed once — asks mutate no state, so
        # the legality picture is fixed for the step.
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
        # CR 509.1b: "can't be blocked by more than one creature" limits how many creatures may
        # block an attacker. Restrictions add up, so a menace attacker allowed fewer than two
        # blockers can't be blocked at all (CR 702.111b).
        allowed: dict[Handle, int] = {}
        for attacker in attackers:
            limit = self.replacements.blockers_allowed(attacker)
            if limit is None:
                continue
            allowed[attacker] = limit
            if attacker in menace and limit < 2:
                for legal in pair_ok.values():
                    legal.discard(attacker)

        def most_obeyed(partial: dict[Handle, list[Handle]], tail: list[Handle]) -> int | None:
            """CR 509.1c: the most requirements obeyed by a declaration that adds blocks by the
            ``tail`` creatures to ``partial`` and violates no restriction, or None when each such
            declaration violates one (a menace attacker held at one blocker). A must-be-blocked
            attacker is one requirement, obeyed by whichever creatures block it. Only two kinds
            of block matter: the second blocker a held menace attacker must get, and the first
            blocker of each unblocked must-be-blocked attacker (two with menace). Bipartite
            matching (Kuhn) over the tail: the sets of attackers one matching can serve form a
            matroid, so for each choice of the must-be-blocked menace attackers to serve, serving
            the others one at a time serves the most."""
            match: dict[Handle, Handle] = {}  # a tail creature -> the attacker it blocks

            def augment(attacker: Handle, reach: set[Handle]) -> bool:
                for blocker in tail:
                    if blocker in reach or attacker not in pair_ok[blocker]:
                        continue
                    reach.add(blocker)
                    if blocker not in match or augment(match[blocker], reach):
                        match[blocker] = attacker
                        return True
                return False

            held = [a for a in attackers if a in menace and len(partial.get(a, ())) == 1]
            unblocked = [a for a in attackers if a in mandated and not partial.get(a)]
            pairs = [a for a in unblocked if a in menace]
            best: int | None = None
            for size in range(len(pairs) + 1):
                for chosen in combinations(pairs, size):
                    match.clear()
                    if all(augment(a, set()) for a in (*held, *chosen, *chosen)):
                        served = size + sum(augment(a, set()) for a in unblocked if a not in menace)
                        best = served if best is None else max(best, served)
            return None if best is None else len(mandated) - len(unblocked) + best

        # CR 509.1c: the defending player chooses the blocks; the declaration obeys as many
        # requirements as one that violates no restriction can. A word (NONE too) is offered
        # only when the creatures not yet asked can still complete such a declaration, so any
        # creature may be the one that obeys a requirement, and the last that can is left no
        # other word.
        most = most_obeyed({}, candidates)
        for position, blocker in enumerate(candidates):
            tail = candidates[position + 1 :]
            words = [
                str(attacker)
                for attacker in attackers
                if attacker in pair_ok[blocker]
                and (attacker not in allowed or len(assigned.get(attacker, ())) < allowed[attacker])
                and most_obeyed({**assigned, attacker: [*assigned.get(attacker, []), blocker]}, tail)
                == most
            ]
            if most_obeyed(assigned, tail) == most:
                words.append("NONE")
            ctx = self._ctx(
                source=blocker, controller=defender, bindings=None, decisions=()
            )
            # A creature left ONE word (the last that can obey a requirement, or a menace
            # attacker's second blocker) gets it without being asked.
            answer = offer_or_autopick(ctx, tuple(words), f"block:{blocker}:{world.turn}")
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
            if attacker in allowed and len(blockers) > allowed[attacker]:
                raise RuntimeError(
                    f"executor: {attacker} was blocked by {len(blockers)} creatures, more "
                    "than it may be (CR 509.1b — the ask narrowing should have prevented this)"
                )
        if most_obeyed(assigned, []) != most:
            raise RuntimeError(
                f"executor: the blocks obey fewer requirements than the {most} a declaration "
                "can (CR 509.1c — the ask narrowing should have prevented this)"
            )
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

    def join_attack(self, creature: Handle) -> None:
        """CR 508.4 - a creature PUT ONTO THE BATTLEFIELD ATTACKING
        (Falconer Adept's Bird, Basri Ket's [-2] Soldier) joins the open
        attack record with no legality pass. It is attacking, but it was
        never declared, so for trigger events and effects it never
        "attacked" (CR 508.3a): it gets no DECLARE_ATTACKERS row, and no
        attack trigger, battalion group, "that many" count or "attacked
        this turn" history sees it. Outside the declare window the verb path
        never calls this."""
        if self.defending_player is None or creature in self.attackers:
            return
        self.attackers.append(creature)
        # CR 508.4: its controller chooses what it attacks, the
        # defending player or a planeswalker that player controls (the
        # corpus' "tapped and attacking" effects never say which).
        walkers = self._attackable_walkers()
        target = self.defending_player
        if walkers:
            ctx = self._ctx(
                source=creature,
                controller=self.controller_of(creature),
                bindings=None,
                decisions=(),
            )
            vocab = ("ATTACK",) + tuple(str(w) for w in walkers)
            answer = offer_or_autopick(ctx, vocab, f"attack:{creature}:{self.world.turn}")
            target = next((w for w in walkers if str(w) == answer), target)
        self.attacked[creature] = target

    def _attackable_walkers(self) -> list[Handle]:
        """CR 506.2, 506.3: the planeswalkers a creature may attack this
        combat, Handle-sorted: those the defending player controls."""
        return sorted(
            card
            for player in self.world.player_order
            for card in self.world.players[player].zone(ZONE_BATTLEFIELD).entries
            if self._attacked_walker_live(card)
        )

    def _attacked_walker_live(self, card: Handle) -> bool:
        """Is ``card`` a planeswalker the defending player controls, on the
        battlefield and phased in? A planeswalker being attacked that stops
        being one is removed from combat (CR 506.4): it left the battlefield,
        changed controller, phased out or stopped being a planeswalker."""
        world = self.world
        if card not in world.cards or world.zone_of(card).kind != ZONE_BATTLEFIELD:
            return False
        if card in self.phased_out or self.controller_of(card) != self.defending_player:
            return False
        ctx = self._ctx(source=card, controller=self.controller_of(card), bindings=None, decisions=())
        return eval_filter(_IS_PLANESWALKER, card, ctx)

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
        """CR 510.1: one dealer's legal assignment announcement.

        * UNBLOCKED: everything to the ATTACKED object, the defending player
          or a planeswalker (CR 510.1b). A creature whose planeswalker
          was removed from combat attacks nothing (CR 506.4c) and, unblocked,
          assigns no combat damage; with trample its excess can only go to
          its blockers (CR 702.19b, 702.19f).
        * BLOCKED, but every blocker has left combat: the creature
          is still blocked (CR 509.1h), so it assigns NO combat damage
          (CR 510.1c), unless it has trample, which assigns all of it to
          the attacked object (CR 702.19d); the Herald policy below may
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
          ``order:<card>:<slot>:<turn>``) as a POSITIONAL pick from the
          Handle-sorted remaining candidates at each slot — the exact
          decision surface of the permutation index, with a ≤n-word
          vocabulary at every ask (one ask over whole orders would need n!
          words).
        * LETHAL per blocker is toughness-minus-marked (CR 704.2, the
          marked ledger keeps the first-strike step's scars) or 1 from a
          DEATHTOUCH dealer (CR 702.2b).
        * TRAMPLE (CR 702.19): once every blocker is covered lethal, the
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
            # A blocker-side dealer: a blocker assigns to the ONE attacker
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
        attacked: Handle | None = self.attacked.get(dealer, defender)
        if (
            attacked is not None
            and attacked.namespace == "card"
            and not self._attacked_walker_live(attacked)
        ):
            attacked = None  # CR 506.4c: attacking nothing now
        if dealer not in self.blocked_by:
            return ((power, attacked),) if attacked is not None else ()  # unblocked
        # CR 509.1h: the blocked_by entry outlives its blockers (a
        # departing blocker is removed from the list, the key stays), so an
        # empty live list here still means BLOCKED.
        blockers = [
            b
            for b in self.blocked_by[dealer]
            if b in world.cards and world.zone_of(b).kind == ZONE_BATTLEFIELD
        ]
        if not blockers and self.layers.keyword_of(dealer, Keyword.TRAMPLE):
            # CR 702.19d: all of it tramples over (nothing left: no damage)
            return ((power, attacked),) if attacked is not None else ()
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
                return ((power, attacked),) if attacked is not None else ()
        if not blockers:
            # CR 510.1c: blocked with no creature blocking it, no
            # trample: it assigns no combat damage.
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
                # The LAST slot has exactly one remaining creature: its
                # "0" is taken without asking.
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
        if excess and attacked is not None:
            plan.append((excess, attacked))
        elif excess:
            # CR 702.19b/f: its planeswalker left combat, so the excess
            # can only go to the blockers: the last one in order takes it.
            last = ordered[-1]
            for i, (a, h) in enumerate(plan):
                if h == last:
                    plan[i] = (a + excess, last)
                    break
            else:
                plan.append((excess, last))
        # CR 510.1: damage assignment is simultaneous within the step; the
        # canonical row order keeps the journal deterministic.
        return tuple(sorted(plan, key=lambda p: (p[1].namespace, p[1].index)))

    def _damage_wave(self, dealers: list[Handle]) -> None:
        """One combat-damage substep: EVERY dealer's legal assignment is
        announced first (CR 510.1: all announcements, then all damage —
        nothing a later dealer's ask could read has mutated yet), then the
        atoms run inside ONE op boundary (simultaneous, CR 506/510 — no
        trigger can intervene between two attackers), each dealer's atoms
        journalled under ITS OWN cause and with the step's op number
        (CR 510.2: one damage event, which an "is dealt damage" trigger
        counts once per recipient), each damage-
        bearing dealer emits ONE COMBAT_DAMAGE row carrying the whole as-
        signment (CR 603.2: one "deals combat damage" event per dealer,
        however it splits) and gains its lifelink once (CR 120.3f: one
        life-gain event per dealer); the step's priority point that follows checks the
        state-based actions and puts the triggers on the stack. CR 120.7: a 0-power attacker deals no damage at
        all — no life change, no DAMAGE row, no combat-damage event."""
        strikes: list[tuple[Handle, tuple[tuple[int, Handle], ...]]] = []
        for dealer in dealers:
            identity = self.world.cards[dealer].identity
            power, _toughness = self.ledger.effective_pt(
                identity, dealer, self.world.cards[dealer].counters
            )
            if not power or power < 0:
                # 0, a negative, or an unmaterialized * : CR 120.7 - not
                # dealt at all. A -X/-X instant cast after blockers
                # can push a dealer's effective power below zero; damage is
                # never negative.
                continue
            plan = self._assign_damage(dealer, power, self.controller_of(dealer))
            if not plan:
                # A blocker whose attacker left combat deals nothing -
                # no damage, no COMBAT_DAMAGE event (CR 120.7's reading).
                continue
            strikes.append((dealer, plan))
        if not strikes:
            return
        self._op_seq += 1
        self._combat_wave_open = self._op_seq
        try:
            for dealer, plan in strikes:
                # CR 120.3f, 510.2: a dealer's combat damage is dealt at once, so its
                # lifelink is ONE life-gain event however many recipients share it (a
                # trampler and its blocker, two blockers): the dealer's earlier atoms
                # hold what they dealt, its last atom gains the whole. Every atom
                # deals a positive amount from its dealer, so each reaches the gain.
                held: list[int] = []
                for slot, (amount, recipient) in enumerate(plan):
                    ctx = self._ctx(
                        source=dealer,
                        controller=self.controller_of(dealer),
                        bindings={"target": recipient},
                        decisions=(),
                    )
                    if slot < len(plan) - 1:
                        ctx.lifelink_held = held
                    else:
                        ctx.lifelink_carried = sum(held)
                    self._run_effect(_combat_damage_atom(amount, recipient), ctx)
        finally:
            self._combat_wave_open = 0
        for dealer, plan in strikes:
            self.journal.emit(
                KIND_COMBAT_DAMAGE,
                dealer,
                dealer,
                "COMBAT_DAMAGE",
                (plan,),
            )

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
        if self.world.active_player is None or not self._turn_started:
            return self.begin_turn(self.world.player_order[0])
        self.end_turn()
        return self.begin_turn(self.next_turn_seat())

    def next_turn_seat(self) -> Handle:
        """Whose turn is next, once a turn has ended (CR 500.7: a pending extra
        turn first, else the seat after the last normal turn's)."""
        order = self.world.player_order
        if self.extra_turn_queue:
            if self.normal_turn_seat is None:
                # The extras follow the first turn, a normal turn.
                self.normal_turn_seat = self.world.active_player
            return self.extra_turn_queue.pop(0)
        base = self.normal_turn_seat
        if base is None:
            base = self.world.active_player
        assert base is not None
        nxt = order[(order.index(base) + 1) % len(order)]
        self.normal_turn_seat = nxt
        return nxt

    def end_turn(self) -> int:
        """The end step, then the cleanup step (CR 513-514), with both players
        passing, from wherever the turn is: a driver that calls it before
        combat skips what is left of the turn before the end step. The
        END_TURN marker comes first (end-step triggers see the pre-expiry
        state). Returns the firing count.

        A turn that is already over does nothing: an effect ended it (CR
        724.1 skipped its end step and ran its cleanup step), or its end step
        already ran. Drivers call this once per turn whatever happened in it.

        CR 500.4: unspent mana empties as each step and phase ends."""
        if self.phase == TURN_ENDED:
            return 0
        if self.phase not in (END_STEP, CLEANUP):
            self._jump_to(END_STEP)
        return self.pass_until(TURN_ENDED)

    def _discard_to_hand_size(self) -> None:
        """CR 514.1 (a turn-based action, no stack): the active player
        discards down to :data:`MAX_HAND_SIZE` (CR 402.2). The player
        chooses the cards (CR 701.9b): one ask per excess card over the rest
        of the hand, under the discard cost's key shape
        ``discard:<seat>:cleanup:<digest>`` (legality.pay_costs). Every ask
        offers at least eight cards, so none is a forced pick. The chosen
        cards then go to the graveyard together (CR 701.9a) as one journalled
        atom boundary; the triggers they cause wait for the 514.3a settle."""
        player = self.world.active_player
        if player is None:
            return
        hand = self.world.players[player].zone(ZONE_HAND).entries
        excess = len(hand) - MAX_HAND_SIZE
        if excess <= 0:
            return
        ctx = self._ctx(source=player, controller=player, bindings=None, decisions=())
        remaining = sorted(hand)
        chosen: list[Handle] = []
        for _pick in range(excess):
            vocab = tuple(str(card) for card in remaining)
            answer = ctx.take_decision(
                vocab, f"discard:{player}:cleanup:{site_digest(vocab)}"
            )
            pick = next(card for card in remaining if str(card) == answer)
            chosen.append(pick)
            remaining.remove(pick)
        ctx.bindings["cards"] = sorted(chosen)
        self._run_effect(_CLEANUP_DISCARD, ctx)

    def empty_mana_pools(self) -> None:
        """CR 500.5 / 106.4: as a step or phase ends, any unspent mana left in
        a player's mana pool empties (a turn-based action, CR 703.4q). The
        segment mirror (spend restrictions) empties with it, so a restriction
        can never outlive its mana. A non-empty pool leaves an ``EMPTY_MANA``
        audit row on the event log (the PAY_MANA precedent), so the replay
        fingerprint records what was lost. Mana retention ("you don't lose
        this mana as steps and phases end": Upwelling) is not modelled: every
        pool empties."""
        for player in self.world.player_order:
            pool = self.world.players[player].mana_pool
            lost = tuple(sorted((k, v) for k, v in pool.items() if v))
            if lost:
                self.events.append((len(self.events), "EMPTY_MANA", str(player), lost))
            pool.clear()
            self.mana_ledger.segments.pop(player, None)

    # ------------------------------------------------------- emblem / attach

    def get_emblem(self, owner: Handle, emblem: CardRecord) -> Handle:
        """Put a new emblem into ``owner``'s command zone (CR 114.2) and return its synthetic
        handle. Each one is an object of its own, so a second emblem with the same abilities works
        beside the first. The emblem is executor replayed state, not a world card: its triggers
        bind to the owner through the binder, its statics anchor to the owner in the layer
        registry, and both are folded into the fingerprint."""
        handle = Handle("emblem", self._emblem_seq)
        self._emblem_seq += 1
        self.emblems[handle] = (owner, emblem.oracle_id)
        self.binder.bind_emblem(handle, emblem, owner)
        self.layers.recompute()  # emblem statics are live the moment it lands
        return handle

    def attach_aura(self, aura: Handle, host: Handle) -> None:
        """Record that ``aura`` (an Aura or Equipment) is attached to
        ``host``: the table the IS_ATTACHED_TO_SOURCE oracle reads, written
        by the Aura cast and move lanes and the ATTACH verb. Replayed and
        fingerprint-folded; the binder drops the edge when either end
        leaves the battlefield."""
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
        """CR 506.4: the permanents stop attacking and blocking (phasing out,
        leaving the battlefield). An attacker whose blocker left stays
        blocked (CR 509.1h): its entry keeps its key."""
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
        A permanent that "can't phase in" (Teferi, Timeless Voyager's [−8], a
        PhasingEvent prevention) stays out, and so does what is attached to
        it. Returns what phased in."""
        returning = sorted(
            card
            for card, (controller, host) in self.phased_out.items()
            if host is None
            and controller == player
            and not self.replacements.prevents_phase_in(card)
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

    # ------------------------------------------------------ control overlay

    def _overlay_controller(self, handle: Handle) -> Handle | None:
        """The control overlay's controller for ``handle``, None when the
        zone's player controls it (the journal's as-of-death read)."""
        return self.control_overlay.get(handle)

    def controller_of(self, handle: Handle) -> Handle:
        """The EFFECTIVE controller of a card: the GAIN_CONTROL
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
        """Rebuild the derived overlay from the live entries; report whether
        ANY effective controller changed. CR 506.4a: a permanent changing
        controllers during combat is removed from combat — attackers,
        attacked record, and every block edge. The sickness clock (CR 302.6)
        is the turn of each creature's last change of effective controller,
        either way (the owner who got it back is in a fresh period too), and
        nothing else moves it: two stacked entries for the same controller
        never re-inflict summoning sickness, and a recompute caused by some
        other creature never dates a period back to an older entry."""
        prev = self.control_overlay
        latest = {entry[1]: entry for entry in self.control_entries}  # later win (CR 613.2)

        def effective(creature: Handle, seen: frozenset[Handle]) -> Handle:
            # An Aura's "You control enchanted creature" (Enthralling Hold) is the one entry
            # anchored to its source with no duration (verbs._v_gain_control): it is the
            # Aura's own static ability, so its "you" is the Aura's controller now (CR 109.5)
            # and it applies after whatever changes the Aura's control (CR 613.8a). Every
            # other entry, a resolved effect, keeps its controller (CR 611.2c), as does an
            # Aura entry in a dependency loop.
            entry = latest.get(creature)
            if entry is None:
                return self.world.controller_of(creature)
            _seq, _creature, controller, tag, anchor, _turn = entry
            if tag == "Permanent" and anchor is not None and anchor not in seen:
                return effective(anchor, seen | {creature})
            return controller

        overlay = {creature: effective(creature, frozenset()) for creature in latest}
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
            self.control_gained_turn[creature] = self.world.turn
        # CR 109.5, 611.3a: "you" in a permanent's own static, keyword and
        # replacement abilities is its controller NOW, so the records they
        # registered when it entered follow the change (a stolen Blightbeetle
        # protects the thief's creatures). Only the control entries change a
        # battlefield permanent's controller: a permanent entering registers
        # under the controller it enters with.
        for creature in changed:
            if creature not in self.world.cards:
                continue  # a token that ceased to exist (CR 704.5d) has no records left
            controller = self.controller_of(creature)
            self.layers.follow_controller(creature, controller)
            self.replacements.follow_controller(creature, controller)
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
        """World fingerprint + ledger dump + event log + the journal and
        binder dumps + the layer and replacement registries + the other
        executor-side replayed state below (the world has no fields for it):
        equal iff every replayed atom and every fired trigger produced the
        same state transitions."""
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
        # Damage marks (CR 120.6).
        h.update(repr(sorted(self.damage.items())).encode())
        # CR 702.26: the phased-out status.
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
        # CR 610.3: the return registry.
        # Folded only while a row exists, so every replay without an "until"
        # zone move keeps its fingerprint bytes.
        if self.returns.rows:
            h.update(repr(self.returns.dump()).encode())
        # The cast-declared X ledger.
        h.update(repr(sorted(map(str, self.etb_x.items()))).encode())
        # The deathtouch flags (CR 702.2b kills).
        h.update(repr(sorted(map(str, self.damage_deathtouch))).encode())
        # The attack record + the dispatched mandate ledger: a replay that
        # attacked with a different set, or lost an "attacks if able" rule,
        # MUST differ here.
        h.update(
            repr(
                (
                    tuple(str(a) for a in self.attackers),
                    tuple(sorted((str(k), str(v)) for k, v in self.attacked.items())),
                    str(self.defending_player),
                    self.declaring,
                    self._declare_group,
                    tuple(sorted(map(str, self.mandates))),
                    # The block record, the must-block ledger and the
                    # dispatched damage-assignment policies.
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
        # The turn ledger.
        h.update(
            repr(
                (
                    self.phase,
                    self.turn_open,
                    self.tba_done,
                    str(self.priority_holder),
                    self.passes,
                    tuple(sorted((str(k), v) for k, v in self.step_actions.items())),
                    None
                    if self.first_strikers is None
                    else tuple(sorted(map(str, self.first_strikers))),
                    tuple(self.extra_turn_queue),
                    tuple(self.lost_players),
                    tuple(sorted(self.loyalty_clock.items())),
                    self.last_flip_won_by,
                    # The CR 724.1a mark rides the flag while a request is
                    # open; False with none open.
                    self.end_turn_mark if self.end_turn_requested else False,
                )
            ).encode()
        )
        # The stack. GameWorld.fingerprint iterates PLAYER_ZONES, which
        # leaves out the shared ZONE_STACK, so a card parked on the stack is
        # invisible to it; this fold closes that hole: two states differing
        # only by a stack frame MUST differ here (pinned by
        # test_stack_frame_fold_changes_the_fingerprint). Then the land
        # ledger, mana segments and chosen names.
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
        # The emblems table (owner-keyed synthetic handles) and the
        # attachment edges: a replay that granted a different emblem set or
        # missed an attachment MUST differ here.
        h.update(
            repr(
                tuple(
                    sorted(
                        ((str(owner), oid), str(handle))
                        for handle, (owner, oid) in self.emblems.items()
                    )
                )
            ).encode()
        )
        h.update(
            repr(
                tuple(sorted((str(a), str(h_)) for a, h_ in self.attachments.items()))
            ).encode()
        )
        # The control overlay (derived) rides the fingerprint beside
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
