"""The per-object planner, v1 (docs/DESIGN_PLANNER.md §1-§3, §5 step 1).

At each decision of a planning seat the network forecasts, on the token of every object the seat
can plan with, the object's next use from this decision on (the decision's own answer included):
when, the verb, the window and the target. The seat's next decision reads the forecast back as
four columns of the object's card row (``features.C_PLAN_WHEN`` .. ``C_PLAN_TARGET``;
``Tracker.encode``). After the game, the hindsight labels are what actually happened to each
object (``hindsight``), and plan-following trains the policy on its own actions with the
read-back replaced by the previous decision's labels (``Tracker.result``; the losses are
``ppo.planner_terms``). No torch here: the workers run this.

**Plannable objects** (``plannable``): the seat's hand, the permanents it controls (tokens
included) and its cards in other zones a standing permission lets it cast or play
(``permits.playable``: a flashback card in the graveyard, a card an effect lets it play from
exile, a library's top), whichever of them are the decision's entities. Never an unknown card,
never the opponent's object.

**One object** (CR 400.7): a handle and the journal clock of its latest zone change
(``Tracker.obj``). A card that changes zones is a new object: it gets no read-back, and its uses
are not the old object's. The mulligan's moves, which the engine does not journal, are renewed
by the tracker itself (``Tracker._renew``).

**A use** is mechanical (DESIGN_PLANNER §1), read off the seat's own answer (``uses_of``):
- a land, cast or activation row: its card (a cast's or an activation's target is the first one
  its targets' asks pick, ``pick:<source>:0:0``);
- an attack ask answered with an attack: the creature, the target what it attacks;
- a block ask answered with an attacker: the blocker, the target that attacker;
- a sacrifice, discard or exile choice: the object picked (the verb "cost").

**When** (``WHEN``): A1, A2, A3, A4+ are this sequence's uses from this decision on, in order. A
sequence is the seat's run of decisions in one step of one turn with no action of the opponent
in between (an action: a cast, an activation or a land, ``Executor.step_actions``, CR 117.3c).
Then: later this turn; the opponent's next turn and my next turn (the next two turns, by whose
turn the use falls in); the two turns after; later; never (no use: the game ends first, or the
object leaves its zone unused).

**Window** (``window``): read off the decision's own context: the stack's top object and its
controller, whose turn it is, the step.

The vocabularies are hand-chosen discretisations (DESIGN_PLANNER §6; docs/BACKLOG.md
"Scaffolds to remove").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from MTG_bot.bench.protocol import tag_handle
from MTG_bot.core.executor import permits
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE
from MTG_bot.core.executor.legality import (
    BEGIN_COMBAT,
    COMBAT_DAMAGE,
    DECLARE_ATTACKERS,
    DECLARE_BLOCKERS,
    END_OF_COMBAT,
    FIRST_MAIN,
    FIRST_STRIKE_DAMAGE,
    SECOND_MAIN,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND
from tools.selfplay import features as FT

WHEN = ("A1", "A2", "A3", "A4+", "later this turn", "their next turn", "my next turn",
        "two turns after", "later", "never")
A1, A4, LATER_THIS_TURN, THEIR_NEXT_TURN, MY_NEXT_TURN, TWO_TURNS_AFTER, LATER, NEVER = (
    0, 3, 4, 5, 6, 7, 8, 9)
VERBS = ("none", "cast", "land", "activate", "attack", "block", "cost")
V_NONE, V_CAST, V_LAND, V_ACTIVATE, V_ATTACK, V_BLOCK, V_COST = range(len(VERBS))
WINDOWS = ("none", "my main phase", "my combat", "their spell", "their ability", "their combat",
           "other")
W_NONE, W_MAIN, W_MY_COMBAT, W_THEIR_SPELL, W_THEIR_ABILITY, W_THEIR_COMBAT, W_OTHER = range(
    len(WINDOWS))
#: The forecast heads (model.PolicyValueNet.forecast): when, verb and window logits, and the
#: target's: "none", then one per entity of the decision (me, the opponent, the cards), as a
#: target column points (features.C_PLAN_TARGET: 0 none, entity + 1).
HEADS = ("when", "verb", "window", "target")

_COMBAT = frozenset({BEGIN_COMBAT, DECLARE_ATTACKERS, DECLARE_BLOCKERS, FIRST_STRIKE_DAMAGE,
                     COMBAT_DAMAGE, END_OF_COMBAT})
_ROW_VERB = {FT.OPT_INDEX["land"]: V_LAND, FT.OPT_INDEX["cast"]: V_CAST,
             FT.OPT_INDEX["cast_kicked"]: V_CAST, FT.OPT_INDEX["cast_at"]: V_CAST,
             FT.OPT_INDEX["activate"]: V_ACTIVATE}
_COST_ASKS = ("sacrifice", "discard", "exile")
_HAND, _BATTLEFIELD = FT.ZONE_INDEX[ZONE_HAND], FT.ZONE_INDEX[ZONE_BATTLEFIELD]


def window(executor: Any, me: Handle) -> int:
    """The window of a use made at this decision: in response to the opponent's spell or ability
    when it tops the stack; else either player's combat; else my main phase at sorcery speed (the
    stack empty); else another instant-speed point."""
    frames = executor.stack.frames
    if frames and frames[-1].controller != me:
        return W_THEIR_ABILITY if frames[-1].spell_kind in ("ACTIVATED", "TRIGGERED") else W_THEIR_SPELL
    mine = executor.world.active_player == me
    if executor.phase in _COMBAT:
        return W_MY_COMBAT if mine else W_THEIR_COMBAT
    if mine and executor.phase in (FIRST_MAIN, SECOND_MAIN) and not frames:
        return W_MAIN
    return W_OTHER


def uses_of(executor: Any, ask: Any, token: str) -> list[tuple[Handle, int, Handle | None]]:
    """The uses an answer makes, each (object, verb, target or None); a target ask's answer is
    not one (``Tracker.end`` gives it to the use it aims). Only the seat's own decisions: a mana
    ability is no menu row (the engine pays, BACKLOG "Automatic payment"), so a land that only
    pays is never used, and a forced choice the engine fills without asking is no use either."""
    kind = ask.kind
    use = None
    if kind in ("act", "priority"):
        typ, h1, h2 = FT._OPTS[token][:3]
        if typ in _ROW_VERB:
            use = (h1, _ROW_VERB[typ], h2 if typ == FT.OPT_INDEX["cast_at"] else None)
    elif kind == "attack" and token != "DECLINE":  # attack:<creature>:<turn>
        what = executor.defending_player if token == "ATTACK" else FT._handle(token)
        use = (tag_handle(ask.site), V_ATTACK, what)
    elif kind == "block" and token != "NONE":  # block:<blocker>:<turn>, answered with an attacker
        use = (tag_handle(ask.site), V_BLOCK, FT._handle(token))
    elif kind in _COST_ASKS:
        use = (FT._handle(token), V_COST, None)
    # no object, no use: an "up to" sacrifice or discard answered NONE picks nothing, and a
    # phantom use would take an A-slot from every use after it in its sequence
    return [] if use is None or use[0] is None else [use]


def plannable(executor: Any, me: Handle, handles: list[Handle],
              feats: dict[str, np.ndarray]) -> np.ndarray:
    """Which card rows of an encoding are objects the seat can plan with (the module docstring).
    The permitted ones are the engine's own answer, whatever the timing or the mana now
    (``permits.playable``: about 15 µs a decision, measured over six games)."""
    ci = feats["cards_i"]
    zone, ctrl = ci[:, 1], ci[:, 2]
    mask = (ctrl == 1) & ((zone == _HAND) | (zone == _BATTLEFIELD))
    permitted = set(permits.playable(executor, me))
    if permitted:
        mask |= np.array([h in permitted for h in handles[2:]], dtype=bool)
    return mask


def plan_of(keys: np.ndarray, mask: np.ndarray,
            forecast: np.ndarray) -> dict[int, tuple[int, int, int, int | None]]:
    """A decision's forecast, or its hindsight labels (the same shape: [cards, 4] of when, verb,
    window, target: 0 none, entity + 1), by object: when, verb, window and the target's object
    (None for none), for its plannable cards. ``keys``: the decision's entities' objects."""
    out = {}
    for r in np.flatnonzero(mask):
        when, verb, win, t = (int(x) for x in forecast[r])
        out[int(keys[2 + r])] = (when, verb, win, int(keys[t - 1]) if 0 < t <= len(keys) else None)
    return out


def readback(keys: np.ndarray, plan: dict[int, tuple[int, int, int, int | None]]) -> np.ndarray:
    """The read-back columns of a decision's card rows (features.C_PLAN_WHEN .. C_PLAN_TARGET):
    each card's plan when the card is the object the plan is for, its target pointing at the
    entity that is that object now (0 when none is)."""
    out = np.zeros((len(keys) - 2, 4), np.int16)
    if not plan:
        return out
    where = {int(k): j for j, k in enumerate(keys)}
    for r in range(len(keys) - 2):
        p = plan.get(int(keys[2 + r]))
        if p is not None:
            when, verb, win, t = p
            out[r] = (when + 1, verb + 1, win + 1, where[t] + 1 if t in where else 0)
    return out


@dataclass
class Decision:
    """One decision of a recording seat, as hindsight reads it: when it was (``turn``, ``step``
    as an index of features.STEPS or -1, whose turn: ``mine``), its sequence and its window, and
    the uses its answer made, each [object, verb, target object or -1]. A sample, a decision the
    network forecast at, also holds its entities' objects in encode order (``keys``: me, the
    opponent, the cards) and which of its cards were plannable."""

    turn: int
    step: int
    mine: bool
    seq: int
    window: int
    uses: list[list[int]] = field(default_factory=list)
    keys: np.ndarray | None = None
    plannable: np.ndarray | None = None
    sample: bool = False


class Tracker:
    """One planning seat's side of a game (actor.NetAgent): the objects' identities, the latest
    forecast (read back at the next decision) and, when ``keep`` (a seat trained on), a record of
    every decision, for the hindsight labels.

    The agent calls ``begin`` at each ask it answers, ``encode`` when the network decides (with
    the read-back), ``forecast`` with the network's forecast, and ``end`` with its answer."""

    def __init__(self, seat: int, keep: bool = False) -> None:
        self.seat = seat
        self.keep = keep
        self.entry: dict[Handle, int] = {}  # each card's latest zone change, a journal clock
        self.read = 0  # the journal rows read into ``entry``
        self.ids: dict[tuple[Handle, int], int] = {}
        self.plan: dict[int, tuple[int, int, int, int | None]] = {}  # the latest forecast
        self.keys = np.zeros(0, np.int32)  # the last encoding's entities' objects
        self.mask = np.zeros(0, bool)  # and which of its cards were plannable
        self.decisions: list[Decision] = []
        self._sequence: tuple = ()
        self._seq = 0
        self._renewed = 0  # the last clock ``_renew`` gave: negative, so no journal row has it

    def _sync(self, executor: Any) -> None:
        """Read the journal rows since the last call into ``entry``. Incremental, because the
        engine's own reading of CR 400.7 (``returns.moved_since``) scans the journal back from
        its end at every call, and a decision asks it of every entity; the journal only grows."""
        events = executor.journal.events
        for i in range(self.read, len(events)):
            event = events[i]
            if event.kind == KIND_ZONE_CHANGE:
                self.entry[event.subject] = event.clock
        self.read = len(events)

    def obj(self, h: Handle) -> int:
        """The object ``h`` is now (CR 400.7: a zone change makes a new one), as a small int."""
        return self.ids.setdefault((h, self.entry.get(h, 0)), len(self.ids))

    def _renew(self, handles: list[Handle]) -> None:
        """Make each of ``handles`` a new object from now on, for a zone change the journal does
        not record. One engine path makes such moves: the London mulligan (CR 103.5) shuffles
        the hand into the library, draws a new one and puts cards on the bottom by editing the
        zones itself (``games.mulligans``). Without this a card drawn again kept the old hand's
        object: its label at the mulligan was its later use, not "never", and the mulligan's
        forecast was read back onto it (found by the review of 2026-11-18)."""
        for h in handles:
            self._renewed -= 1
            self.entry[h] = self._renewed

    def begin(self, executor: Any) -> None:
        """A decision of the seat: its turn, step, sequence and window (recorded when ``keep``).
        The opponent's actions are the engine's own count of each player's priority actions in
        the step (``Executor.step_actions``, CR 117.3c: a cast, an activation, a land), public as
        the actions are, reset with each step."""
        if not self.keep:
            return
        world = executor.world
        me = world.player_order[self.seat]
        sequence = (world.turn, executor.phase,
                    sum(n for p, n in executor.step_actions.items() if p != me))
        if sequence != self._sequence:
            self._sequence, self._seq = sequence, self._seq + 1
        step = FT.STEPS.index(executor.phase) if executor.phase in FT.STEPS else -1
        self.decisions.append(Decision(world.turn, step, world.active_player == me, self._seq,
                                       window(executor, me)))

    def encode(self, executor: Any, ask: Any, table: FT.CardTable,
               ctx: FT.AskContext | None = None) -> dict[str, np.ndarray]:
        """``features.encode`` with the read-back filled in: the latest forecast for each entity
        still the object it was made for."""
        feats, handles = FT.encode_entities(executor, ask.seat, ask, table, ctx)
        self._sync(executor)
        self.keys = np.array([self.obj(h) for h in handles], np.int32)
        self.mask = plannable(executor, executor.world.player_order[self.seat], handles, feats)
        feats["cards_i"][:, FT.C_PLAN_WHEN:FT.C_PLAN_TARGET + 1] = readback(self.keys, self.plan)
        if self.keep:
            self.decisions[-1].keys, self.decisions[-1].plannable = self.keys, self.mask
        return feats

    def forecast(self, forecast: np.ndarray) -> None:
        """The network's forecast at this decision ([cards, 4], ``plan_of``): the read-back of
        the next one. It replaces the last one whole: the seat's latest forecast is its latest
        decision's, over the objects plannable there, and plan-following's read-back
        (``result``) is built the same way from that decision's labels."""
        self.plan = plan_of(self.keys, self.mask, forecast)
        if self.keep:
            self.decisions[-1].sample = True

    def end(self, executor: Any, ask: Any, idx: int) -> None:
        """The seat answered ``idx``: the uses it made, and, for a mulligan's answer, the objects
        it moves (``_renew``; for every planning seat, since all of them read back)."""
        self._sync(executor)
        token = ask.options[idx].token
        if ask.kind == "mulligan" and token == "mulligan":
            world = executor.world
            self._renew(list(world.players[world.player_order[self.seat]].zone(ZONE_HAND).entries))
        elif ask.kind == "mulligan_bottom":
            self._renew([FT._handle(token)])
        if not self.keep:
            return
        if ask.kind == "target":
            # pick:<source>:<slot>:<picks so far> (router._targets): the first pick of the first
            # slot is the target of the cast or activation of <source> being made
            target = FT._handle(token)
            first = ask.site.startswith("pick:") and ask.site.split(":")[-2:] == ["0", "0"]
            if first and target is not None:
                self._aim(self.obj(tag_handle(ask.site)), self.obj(target))
            return
        self.decisions[-1].uses += [[self.obj(h), verb, -1 if t is None else self.obj(t)]
                                    for h, verb, t in uses_of(executor, ask, token)]

    def _aim(self, source: int, target: int) -> None:
        for d in reversed(self.decisions):
            for use in reversed(d.uses):
                if use[0] == source and use[1] in (V_CAST, V_ACTIVATE) and use[2] < 0:
                    use[2] = target
                    return

    def result(self) -> list[tuple[np.ndarray, np.ndarray | None]]:
        """Per sample, in order: its hindsight labels (``hindsight``), and the read-back
        plan-following trains it on: the previous sample's labels read back onto it as its
        forecast was (None for the first sample)."""
        out: list[tuple[np.ndarray, np.ndarray | None]] = []
        prev = None
        for d, y in zip([d for d in self.decisions if d.sample], hindsight(self.decisions),
                        strict=True):
            x = None if prev is None else readback(d.keys, plan_of(prev[0].keys, prev[0].plannable,
                                                                   prev[1]))
            out.append((y, x))
            prev = (d, y)
        return out


def hindsight(decisions: list[Decision]) -> list[np.ndarray]:
    """The labels of every sample, in order: per card row [when, verb, window, target], the next
    use of the object from that decision on (its own answer included), -1 for a card that is not
    plannable there. The record must run to the game's end: an object with no use after it is
    "never"."""
    uses = [(i, u) for i, d in enumerate(decisions) for u in d.uses]
    nxt: dict[int, int] = {}  # object -> its next use (an index of ``uses``)
    first = len(uses)  # the first use at or after the decision
    out: list[np.ndarray] = []
    for i in range(len(decisions) - 1, -1, -1):
        while first and uses[first - 1][0] >= i:
            first -= 1
            nxt[uses[first][1][0]] = first
        d = decisions[i]
        if not d.sample:
            continue
        y = np.full((len(d.keys) - 2, 4), -1, np.int16)
        where = {int(k): j for j, k in enumerate(d.keys)}
        for r in np.flatnonzero(d.plannable):
            m = nxt.get(int(d.keys[2 + r]))
            if m is None:
                y[r] = (NEVER, V_NONE, W_NONE, 0)
                continue
            at, (_, verb, target) = uses[m]
            u = decisions[at]
            y[r] = (_when(d, u, m - first), verb, u.window,
                    where[target] + 1 if target in where else 0)
        out.append(y)
    return out[::-1]


def _when(d: Decision, u: Decision, k: int) -> int:
    """The bucket of a use made at decision ``u``, seen from decision ``d``; ``k`` uses come
    before it from ``d`` on."""
    if u.turn == d.turn:
        return min(A1 + k, A4) if u.seq == d.seq else LATER_THIS_TURN
    if u.turn - d.turn <= 2:
        return MY_NEXT_TURN if u.mine else THEIR_NEXT_TURN
    return TWO_TURNS_AFTER if u.turn - d.turn <= 4 else LATER


def attach(feats: dict[str, np.ndarray], pair: tuple[np.ndarray, np.ndarray | None] | None) -> None:
    """A training row's planner arrays (ppo.planner_terms), into its features: ``plan_y`` the
    hindsight labels, ``plan_x`` the read-back plan-following trains on and ``plan_m`` 1 when it
    has one. With no ``pair`` (a void game: its future is unknown) the row trains neither."""
    cards = feats["cards_i"].shape[0]
    y, x = pair if pair is not None else (None, None)
    feats["plan_y"] = y if y is not None else np.full((cards, 4), -1, np.int16)
    feats["plan_x"] = x if x is not None else np.zeros((cards, 4), np.int16)
    feats["plan_m"] = np.array([x is not None], np.int8)
