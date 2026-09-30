"""Structured world-event journal for the executor (round 12b, /06 §12b).

The 12a verb handlers mutate the :class:`~MTG_bot.core.state.GameWorld`
directly and log coarse 12a tuples; 12b needs *rule-relevant* events — the
things triggers subscribe to. The derivation is the mission's diff-inspect:
every executor write goes through an Atom dispatch, so the journal takes a
world snapshot before each atom, and after the handler returns it diffs
zones / tapped flags / counters / life to emit the structured events. No
verbs.py change is needed — the handlers stay pure state-writers. (The one
thing the diff cannot see is non-lethal card damage, which leaves no state
trace; the 12a event tuples already carry its amount, so it rides in as the
handlers' "returned info".)

Every event carries the mission's four-tuple contract:

  * ``clock``   — the journal's own monotonic counter (deterministic; the
    world's ``tick`` stays reserved for TriggerInstance ordering),
  * ``kind``    — one of the ``KIND_*`` tags,
  * ``data``    — the kind-specific payload tuple,
  * ``cause`` / ``cause_verb`` — the C24 do-continuation handle of the
    ability that made it happen (plus the verb tag, e.g. a SACRIFICE cause
    turns a zone change into a sacrifice).

**C18**: ``CREATURE_DIES`` snapshots the subject's type line, effective P/T
and owner *at event time* — the was-snapshot a dies trigger must see even
though the world has already moved the card.

Turn trackers (draw ordinals per controller) live here because the draw
ordinal is event data; ``begin_turn`` resets them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from MTG_bot.core.ability_tree import Phase
from MTG_bot.core.executor.durations_min import DurationLedger
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

# Journal event kinds — each maps onto the IR EventSpec node(s) that can
# subscribe to it in binding.py.
KIND_ZONE_CHANGE = "ZONE_CHANGE"
KIND_CREATURE_DIES = "CREATURE_DIES"
KIND_COUNTER_PLACED = "COUNTER_PLACED"
KIND_TAP_STATE = "TAP_STATE"
KIND_CARD_DRAWN = "CARD_DRAWN"
KIND_DAMAGE = "DAMAGE"
KIND_LIFE_GAINED = "LIFE_GAINED"
KIND_TURN_PHASE = "TURN_PHASE"
# 13b: the cast feed (CastSpellEvent triggers subscribe; the emitter is
# stack.cast/cast_card, ordinals per controller per turn — the twin of the
# draw ordinal) and the LOSE_GAME audit row (13a quirk fix: the loss was an
# executor-ledger append ONLY, invisible to the structured journal — now it
# is a GameEvent row, and the generic dump() folds it into the fingerprint).
KIND_CAST = "CAST"
KIND_GAME_LOST = "GAME_LOST"
# 16b: the combat feeds. DECLARE_ATTACKERS carries ONE row per declared
# attacker (subject = the attacker; the grammar's DeclareAttackersEvent
# filter is subject-scoped) — the shared data[0] declare-group id lets the
# binder queue one trigger instance per ABILITY per declaration (CR 603.2:
# "Whenever you attack with two or more..." triggers once on the whole
# declare action, once per creature for IS_SOURCE filters).
# COMBAT_DAMAGE carries one row per creature that dealt combat damage
# (subject = the dealer — CombatDamageEvent's filter reads the dealer);
# 16c: the row carries the WHOLE legal assignment ((amount, recipient)
# pairs) so one "deals combat damage" event stays ONE event however the
# damage splits across blockers and player.
# 16c: DECLARE_BLOCKERS carries ONE row per block declaration PAIR
# (subject = the BLOCKER, data = (attacker, declare-group)) — the
# DeclareBlockersEvent feed: ``filter``/``subject`` read the blocker,
# ``blocked`` reads the attacker; the same rows answer BecomesBlockedEvent
# (whose blocked-side participant must be the trigger's source, the
# grammar's anchored reading — Gloom Sower).
KIND_DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
KIND_DECLARE_BLOCKERS = "DECLARE_BLOCKERS"
KIND_COMBAT_DAMAGE = "COMBAT_DAMAGE"

# state.py zone-kind strings used by the diff's rule checks.
# (ZONE_KIND_TO_STATE — the IR->state map — lives in selectors.py.)


def parse_handle_tag(tag: str) -> Handle:
    """``"card:5"`` -> ``Handle("card", 5)`` — reverses the 12a tuple's
    stringified handles so damage tuples can be re-attached to subjects."""
    namespace, _, index = tag.partition(":")
    return Handle(namespace, int(index))


@dataclass(frozen=True)
class GameEvent:
    """One structured world event.

    ``data`` layouts (subject/cause/clock are the common spine):

      * ZONE_CHANGE   — ``(from_state|None, to_state, owner_before,
        owner_after)``; ``from_state=None`` marks a created object (token).
      * CREATURE_DIES — ``(from_state, owner_before, was_type_line,
        was_power, was_toughness)`` (C18 was-snapshot).
      * COUNTER_PLACED— ``(counter_kind_name, n)``
      * TAP_STATE     — ``(tapped_bool,)``
      * CARD_DRAWN    — ``(drawer, ordinal_this_turn)``
      * DAMAGE        — ``(amount,)`` or ``(amount, True)`` when the damage
        is COMBAT damage (16c, the DamageDealtEvent ``combat`` scope);
        subject may be a player handle.
      * LIFE_GAINED   — ``(amount,)``
      * TURN_PHASE    — ``(phase_name, active_player)``, subject None.
      * CAST          — ``(caster, ordinal_this_turn, spell_kind,
        from_zone, x_value)``, subject the spell card (13b).
      * GAME_LOST     — ``(reason,)`` , subject the player (13b audit row).
      * DECLARE_ATTACKERS — ``(declare_group,)``, subject the declared
        attacker; one row per attacker, group shared per declaration (16b).
      * DECLARE_BLOCKERS — ``(attacker, declare_group)``, subject the
        BLOCKING creature (16c, the DeclareBlockersEvent /
        BecomesBlockedEvent feed).
      * COMBAT_DAMAGE — ``(assignments,)`` where ``assignments`` is the
        dealer's canonical ``((amount, recipient), ...)`` tuple — 16b
        carried the single ``(amount, recipient)`` pair (no blockers);
        16c keeps ONE row per dealer however the assignment splits
        (the CombatDamageEvent feed).
    """

    clock: int
    kind: str
    subject: Handle | None
    cause: Handle | None
    cause_verb: str
    data: tuple[object, ...] = ()

    # Typed views onto the documented per-kind data layouts (one cast
    # site per shape, right here, instead of one per matcher branch).

    @property
    def zone_move(self) -> tuple[str | None, str, Handle | None, Handle]:
        return cast("tuple[str | None, str, Handle | None, Handle]", self.data)

    @property
    def dies(self) -> tuple[str, Handle, str, int | None, int | None]:
        return cast("tuple[str, Handle, str, int | None, int | None]", self.data)

    @property
    def counter(self) -> tuple[str, int]:
        return cast("tuple[str, int]", self.data)

    @property
    def tapped_new(self) -> bool:
        return cast(bool, self.data[0])

    @property
    def draw(self) -> tuple[Handle, int]:
        return cast("tuple[Handle, int]", self.data)

    @property
    def amount(self) -> int:
        return cast(int, self.data[0])

    @property
    def is_combat(self) -> bool:
        """DAMAGE rows only (16c): the optional second data element marks
        COMBAT damage (CR 609.2 — the DamageDealtEvent ``combat`` scope);
        pre-16c rows and plain DEAL_DAMAGE rows stay a 1-tuple and read
        False."""
        return len(self.data) > 1 and bool(self.data[1])

    @property
    def phase(self) -> tuple[str, Handle]:
        return cast("tuple[str, Handle]", self.data)

    @property
    def cast(self) -> tuple[Handle, int, str, str | None, int | None]:
        """CAST payload: (caster, ordinal_this_turn, spell_kind,
        from_zone, x_value) — the 13b cast feed."""
        return cast("tuple[Handle, int, str, str | None, int | None]", self.data)

    @property
    def declare_group(self) -> int:
        """DECLARE_ATTACKERS payload: the declaration-group id shared by
        every attacker row of one declare-attackers action (16b)."""
        return cast(int, self.data[0])

    @property
    def declare_blockers(self) -> tuple[Handle, int]:
        """DECLARE_BLOCKERS payload: (blocked attacker, declare-group id)
        with the row's SUBJECT as the blocking creature (16c)."""
        return cast("tuple[Handle, int]", self.data)

    @property
    def combat_damage(self) -> tuple[tuple[tuple[int, Handle], ...]]:
        """COMBAT_DAMAGE payload: the dealer's canonical assignment tuple
        ``((amount, recipient), ...)`` wrapped so the row stays ONE event
        per dealer (16c; 16b's single-pair shape is the 1-element case)."""
        return cast("tuple[tuple[tuple[int, Handle], ...]]", self.data)


@dataclass
class _Snapshot:
    """One world snapshot taken at an Atom boundary."""

    zones: dict[Handle, tuple[Handle, str]]  # card -> (zone owner, kind)
    tapped: dict[Handle, bool]
    counters: dict[Handle, dict[str, int]]
    life: dict[Handle, int]


class EventJournal:
    """The executor-side structured event log + turn trackers (12b)."""

    def __init__(self, world: GameWorld, ledger: DurationLedger) -> None:
        self.world = world
        self.ledger = ledger
        self.events: list[GameEvent] = []
        self.draw_counts: dict[Handle, int] = {}
        # 13b: per-controller per-turn cast ordinal (CastSpellEvent.ordinal
        # — "your second spell each turn"), reset by begin_turn exactly
        # like the draw ordinal.
        self.cast_counts: dict[Handle, int] = {}
        self._clock = 0

    # ------------------------------------------------------------- emitting

    @property
    def clock(self) -> int:
        """The journal's monotonic event clock (12d: the deterministic
        timestamp the layer registry stamps onto materialized ledger
        entries, so layer modifiers interleave with verb modifiers on one
        timeline)."""
        return self._clock

    def emit(
        self,
        kind: str,
        subject: Handle | None,
        cause: Handle | None,
        cause_verb: str,
        data: tuple[object, ...] = (),
    ) -> GameEvent:
        """Public emit for turn-skeleton state changes (the 12d untap step:
        not an Atom, but a rule-relevant TapStateEvent the journal must
        carry for Triggers and the fingerprint)."""
        return self._emit(kind, subject, cause, cause_verb, data)

    def _emit(
        self,
        kind: str,
        subject: Handle | None,
        cause: Handle | None,
        cause_verb: str,
        data: tuple[object, ...] = (),
    ) -> GameEvent:
        self._clock += 1
        event = GameEvent(self._clock, kind, subject, cause, cause_verb, data)
        self.events.append(event)
        return event

    def record_turn_phase(self, phase_name: str) -> GameEvent:
        """A turn-skeleton phase marker (begin/end turn, 12b minimal)."""
        return self.emit_phase(phase_name)

    def emit_phase(self, phase_name: str) -> GameEvent:
        active = self.world.active_player
        return self._emit(KIND_TURN_PHASE, None, active, "TURN", (phase_name, active))

    def emit_cast(
        self,
        spell: Handle,
        caster: Handle,
        spell_kind: str,
        from_zone: str | None,
        x_value: int | None,
    ) -> GameEvent:
        """The CAST row (13b): emitted by the casting pipeline at 601.2h —
        after payment, before resolution — so "whenever you cast" triggers
        queue ABOVE the spell (they resolve first, CR 603.2). The ordinal
        is per-caster per-turn (the CastSpellEvent.ordinal vocabulary),
        journalled IN the row so a replay re-derives the same ordinals."""
        self.cast_counts[caster] = self.cast_counts.get(caster, 0) + 1
        return self._emit(
            KIND_CAST,
            spell,
            spell,
            "CAST",
            (caster, self.cast_counts[caster], spell_kind, from_zone, x_value),
        )

    def begin_turn(self, player: Handle) -> None:
        """Reset per-turn event trackers for a new turn (12b skeleton)."""
        self.draw_counts = {}
        self.cast_counts = {}  # 13b: the cast ordinal joins the reset
        del player  # the active-player bookkeeping lives on the world.

    def turn_window(self) -> list[GameEvent]:
        """The "this turn" slice for the journal-backed filter predicates
        (14d, B-7): every event AFTER the most recent begin-turn UPKEEP
        marker. ``begin_turn`` emits that marker after its trackers reset,
        so the window is exactly the turn the reset opened — the previous
        turn's rows (and its END_TURN marker) are out, and the UNTAP
        step's TapState rows sit BEFORE the marker by 12d's ordering (no
        turn-history predicate reads untaps, and the CR-correct clock
        position is what the marker discipline preserves). With no marker
        yet — a journal before any ``begin_turn`` — the whole log is the
        window: the honest whole-history reading of a turn-less test
        world, never a silent empty answer. Deterministic and
        fingerprinted: the journal IS state (14d purity note — a query
        reading history is no less pure than one reading zone lists)."""
        events = self.events
        for i in range(len(events) - 1, -1, -1):
            e = events[i]
            if e.kind == KIND_TURN_PHASE and e.data[0] == Phase.UPKEEP.name:
                return events[i + 1 :]
        return list(events)

    # ------------------------------------------------------------- diffing

    def snapshot(self) -> _Snapshot:
        world = self.world
        zones: dict[Handle, tuple[Handle, str]] = {}
        for player in world.player_order:
            for kind, zone in world.players[player].zones.items():
                for card in zone.entries:
                    zones[card] = (player, kind)
        return _Snapshot(
            zones=zones,
            tapped={c: s.tapped for c, s in world.cards.items()},
            counters={c: dict(s.counters) for c, s in world.cards.items()},
            life={p: world.players[p].life for p in world.player_order},
        )

    def record_atom(
        self,
        before: _Snapshot,
        cause: Handle | None,
        cause_verb: str,
        new_12a_tuples: list[tuple[object, ...]],
        combat: bool = False,
    ) -> list[GameEvent]:
        """Diff the world against ``before`` and emit every triggered-rule
        event the atom caused. Returns the newly appended events."""
        start = len(self.events)
        world = self.world
        after = self.snapshot()

        # --- zone membership: moves, ETBs, deaths, draws, token creates.
        for card, (owner, kind) in after.zones.items():
            was = before.zones.get(card)
            from_state = was[1] if was else None
            if was is not None and was == (owner, kind):
                continue
            self._emit(
                KIND_ZONE_CHANGE,
                card,
                cause,
                cause_verb,
                (from_state, kind, was[0] if was else None, owner),
            )
            if from_state == ZONE_LIBRARY and kind == ZONE_HAND:
                self.draw_counts[owner] = self.draw_counts.get(owner, 0) + 1
                self._emit(
                    KIND_CARD_DRAWN,
                    card,
                    cause,
                    cause_verb,
                    (owner, self.draw_counts[owner]),
                )
            if from_state == ZONE_BATTLEFIELD and kind == ZONE_GRAVEYARD:
                identity = world.cards[card].identity
                was_power, was_toughness = self.ledger.effective_pt(identity, card)
                self._emit(
                    KIND_CREATURE_DIES,
                    card,
                    cause,
                    cause_verb,
                    (
                        from_state,
                        was[0] if was else owner,
                        identity.type_line,
                        was_power,
                        was_toughness,
                    ),
                )

        # --- tapped flags: TapStateEvent feed.
        for card, tapped in after.tapped.items():
            if card in before.tapped and before.tapped[card] != tapped:
                self._emit(KIND_TAP_STATE, card, cause, cause_verb, (tapped,))

        # --- counters: CounterPlacedEvent feed (removals have no trigger
        # vocabulary in the frozen grammar, so they emit nothing).
        for card, counters in after.counters.items():
            was = before.counters.get(card, {})
            for name, value in sorted(counters.items()):
                gained = value - was.get(name, 0)
                if gained > 0:
                    self._emit(
                        KIND_COUNTER_PLACED,
                        card,
                        cause,
                        cause_verb,
                        (name, gained),
                    )

        # --- life: gains are events; DEAL_DAMAGE losses are damage.
        for player in world.player_order:
            was_life = before.life.get(player)
            now_life = after.life[player]
            if was_life is None or was_life == now_life:
                continue
            if now_life > was_life:
                self._emit(
                    KIND_LIFE_GAINED,
                    player,
                    cause,
                    cause_verb,
                    (now_life - was_life,),
                )
            elif cause_verb == "DEAL_DAMAGE":
                self._emit(
                    KIND_DAMAGE,
                    player,
                    cause,
                    cause_verb,
                    (was_life - now_life, True) if combat else (was_life - now_life,),
                )

        # --- non-lethal card damage leaves no state trace: the 12a handler
        # tuples carry its amount (the "handlers already return info" path).
        for entry in new_12a_tuples:
            if entry[1] in ("DAMAGE", "DAMAGE_LETHAL"):
                subject = parse_handle_tag(str(entry[2]))
                if subject.namespace == "card":
                    self._emit(
                        KIND_DAMAGE,
                        subject,
                        cause,
                        cause_verb,
                        (entry[3], True) if combat else (entry[3],),
                    )

        return self.events[start:]

    # ---------------------------------------------------------- canonical

    def dump(self) -> tuple[tuple[object, ...], ...]:
        """Deterministic view for the replay fingerprint."""
        return tuple(
            (
                e.clock,
                e.kind,
                str(e.subject),
                str(e.cause),
                e.cause_verb,
                repr(e.data),
            )
            for e in self.events
        )
