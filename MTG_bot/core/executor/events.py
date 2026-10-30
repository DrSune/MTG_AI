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

from collections.abc import Sequence
from dataclasses import dataclass, field
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
# B3a (BUGCATCH D1, seed 12 "Life Goes On"): the life-LOSS feed. A life
# DECREASE that is not dealt damage (Verb.LOSE_LIFE — "you lose 3 life",
# the corpus' life-as-cost lane) previously left ZERO journal rows: the
# diff emitted a decrease only under cause_verb == "DEAL_DAMAGE" (as a
# DAMAGE row), so a LOSE_LIFE resolution was invisible and the replay
# fingerprint could not reconstruct life history. LIFE_LOST is its OWN
# kind — never a DAMAGE row (CR 118.5: losing life is not dealt damage;
# no DamageDealtEvent may subscribe to a loss) and never a negative
# LIFE_GAINED row (binding.py dispatches LifeGainedEvent by kind, so a
# negative gain row would fire "whenever you gain life" triggers).
KIND_LIFE_LOST = "LIFE_LOST"
KIND_TURN_PHASE = "TURN_PHASE"
# 13b: the cast feed (CastSpellEvent triggers subscribe; the emitter is
# stack.cast/cast_card, ordinals per controller per turn — the twin of the
# draw ordinal) and the LOSE_GAME audit row (13a quirk fix: the loss was an
# executor-ledger append ONLY, invisible to the structured journal — now it
# is a GameEvent row, and the generic dump() folds it into the fingerprint).
KIND_CAST = "CAST"
KIND_GAME_LOST = "GAME_LOST"
# Stall rule (2026-10-05/11): the STALL_BREAK audit row. Emitted by the
# GAME LOOP (games._play), never a verb — the harness-side twin of the
# GAME_LOST pattern: the terminal call is not an atom, but the journal
# must carry it or a stalled game's fingerprint would not record WHY it
# ended. ONE row per ended game: subject None (the whole game, no
# object), cause the seat whose per-round fingerprint streak tripped the
# rule, cause_verb "STALL", data (repeat_rounds,) — pure state, no clock.
KIND_STALL_BREAK = "STALL_BREAK"
# 16b: the combat feeds. DECLARE_ATTACKERS carries ONE row per declared
# attacker (subject = the attacker; the grammar's DeclareAttackersEvent
# filter is subject-scoped) — the shared data[0] declare-group id lets the
# binder queue one trigger instance per ABILITY per declaration (CR 603.2:
# "Whenever you attack with two or more..." triggers once on the whole
# declare action, once per creature for IS_SOURCE filters).
# COMBAT_DAMAGE carries one row per creature that dealt combat damage
# (subject = the dealer); R2 fold (/140): it is a journal/audit feed only —
# trigger lanes subscribe the DAMAGE rows (DamageDealtEvent, combat=True);
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
# r20b (Warden of the Woods): the TARGET designation feed. One row per
# DESIGNATED object at the designation point (CR 601.2c for spells,
# 602.2b for activated abilities, the 18b trigger channel for triggered
# abilities — the three lanes that own a designation; TARGET-mode effect
# selectors READ a designation, they never make one, so they emit
# nothing). Subject = the designated object (the TargetingEvent filter
# reads it, IS_SOURCE = "whenever THIS becomes the target"); data carries
# (source_object, actor) for the audit trail.
KIND_TARGETING = "TARGETING"
# R5-7 (it replaces r22c's LOYALTY_ACTIVATED feed): the activation feed. ONE
# row per activated ability activated, mana abilities included (CR 602.2,
# 605.3b), emitted at the payment point in legality.activate. Subject = the
# object whose ability it is (the AbilityActivatedEvent ``source`` filter
# reads it — Keral's "a Chandra planeswalker"); cause = the activating player
# (the node's ``actor``); data = (ability index, the 605.1a mana-ability
# verdict, the paid loyalty delta or None when it is not a loyalty ability),
# which the node's ``kind`` reads.
KIND_ABILITY_ACTIVATED = "ABILITY_ACTIVATED"
# T5-D (Sanctum of All family): an ability TRIGGERED. SYNTHETIC-ONLY
# kind — never journalled (the matcher feeds AbilityTriggerEvent nodes
# from _queue at firing-queue time), so no golden/fingerprint bytes move.
KIND_ABILITY_TRIGGERED = "ABILITY_TRIGGERED"
# RUNG-1 (response-window arc, /11 §13b follow-through): the counter-
# window feed. WINDOW_OPEN carries ONE row per seat that was ASKED for a
# response to a stack frame (subject = the framed spell, cause = the
# responding seat, data = the offered vocabulary — PASS plus the payable
# counters it holds; a seat with nothing to offer is never asked and
# gets NO row, C15). WINDOW_PASS is the same seat's explicit refusal
# row (the scripted audit — an unanswered window cannot silently exist).
# COUNTER is the flag row of a countered frame (subject = the countered
# spell, cause = the countering spell card). KICKBACK is the "unless its
# controller pays <cost>" site of a COUNTER_SPELL resolution: one row
# per counter WITH an unless cost, WHETHER OR NOT a decision was asked
# (an unpayable payer is never asked — the row then carries the honest
# "UNPAYABLE" witness instead of a fabricated answer).
KIND_WINDOW_OPEN = "WINDOW_OPEN"
KIND_WINDOW_PASS = "WINDOW_PASS"
KIND_COUNTER = "COUNTER"
KIND_KICKBACK = "KICKBACK"

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
      * LIFE_LOST     — ``(amount,)``, subject the player; a non-damage
        life DECREASE (B3a, the LOSE_LIFE feed; the amount is the actual
        delta after the verb's 0-clamp)
      * TURN_PHASE    — ``(phase_name, active_player)``, subject None.
      * CAST          — ``(caster, ordinal_this_turn, spell_kind,
        from_zone, x_value, kicked)`` (ZND-1e appended the paid/not-paid
        flag, CR 702.27a — WAS_KICKED's carrier), subject the spell
        card (13b).
      * GAME_LOST     — ``(reason,)`` , subject the player (13b audit row).
      * STALL_BREAK   — ``(repeat_rounds,)``, subject None, cause the seat
        whose streak fired (stall-rule audit row, 2026-10-05/11).
      * DECLARE_ATTACKERS — ``(declare_group,)``, subject the declared
        attacker; one row per attacker, group shared per declaration (16b).
      * DECLARE_BLOCKERS — ``(attacker, declare_group)``, subject the
        BLOCKING creature (16c, the DeclareBlockersEvent /
        BecomesBlockedEvent feed).
      * COMBAT_DAMAGE — ``(assignments,)`` where ``assignments`` is the
        dealer's canonical ``((amount, recipient), ...)`` tuple — 16b
        carried the single ``(amount, recipient)`` pair (no blockers);
        16c keeps ONE row per dealer however the assignment splits
        (journal feed since the R2 fold — triggers read the DAMAGE rows).
      * TARGETING     — ``(source_object, actor)``, subject the designated
        object (r20b, the TargetingEvent feed). ``cause_verb == "TARGET"``
        is the CR designation feed. ``cause_verb == "ONE_OF"`` /
        ``"REST"`` are partition-designation audit rows: they journal the
        chosen set for branch coverage but intentionally do not fire
        TargetingEvent triggers, because "choose one of them" is not a
        target designation (CR 115.4).
      * ABILITY_ACTIVATED — ``(ability_idx, mana, loyalty)``, subject the
        object whose activated ability was activated, cause the activating
        player; ``mana`` is the CR 605.1a verdict, ``loyalty`` the paid
        loyalty delta or None for a non-loyalty ability (R5-7, the
        AbilityActivatedEvent feed; one row per activation, mana included).
      * WINDOW_OPEN   — ``(vocab,)``, subject the framed spell, cause the
        asked seat (RUNG-1, the response-window audit; one row per seat
        actually asked).
      * WINDOW_PASS   — ``()``, subject the framed spell, cause the
        passing seat (RUNG-1).
      * COUNTER       — ``()``, subject the countered spell card, cause
        the countering spell card (RUNG-1's flag row).
      * KICKBACK      — ``(answer,)``, subject the framed spell, cause
        the countering spell card; answer is the PAY/PASS decision the
        payer gave, or ``"UNPAYABLE"`` when the payer could not pay the
        unless cost and was therefore never asked (RUNG-1, C15-honest).
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
    def cast(self) -> tuple[Handle, int, str, str | None, int | None, bool]:
        """CAST payload: (caster, ordinal_this_turn, spell_kind,
        from_zone, x_value, kicked) — the 13b cast feed with the ZND-1e
        paid/not-paid flag (CR 702.27a)."""
        return cast("tuple[Handle, int, str, str | None, int | None, bool]", self.data)

    @property
    def kicked(self) -> bool:
        """CAST rows only (ZND-1e, CR 702.27a): was the kicker cost paid?
        A short (pre-ZND-1e) payload reads False — a spell with no kicker
        cost was never kicked, which is the truth."""
        return len(self.data) > 5 and bool(self.data[5])

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

    @property
    def activation(self) -> tuple[int, bool, int | None]:
        """ABILITY_ACTIVATED payload (R5-7): (ability index, the 605.1a
        mana-ability verdict, the paid loyalty delta — signed, CR 606.4 — or
        None when the ability is not a loyalty ability)."""
        return cast("tuple[int, bool, int | None]", self.data)


@dataclass
class _Snapshot:
    """One world snapshot taken at an Atom boundary."""

    zones: dict[Handle, tuple[Handle, str]]  # card -> (zone owner, kind)
    tapped: dict[Handle, bool]
    counters: dict[Handle, dict[str, int]]
    life: dict[Handle, int]
    # V23: raw DAMAGE tuples (by executor-event index) that a boundary nested
    # inside this one already journalled; this boundary must not emit them again.
    consumed_raw: set[int] = field(default_factory=set)


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
        # V23: the atom boundaries open right now, outermost first (snapshot opens
        # one, record_atom closes it). A boundary can open inside another: a CAST
        # atom casts and resolves a spell, a PAY atom or a spell's additional cost
        # pays through journalled verbs. Closing an inner boundary folds its changes
        # into every boundary around it, so each change is journalled exactly once.
        # Transient: empty between ops.
        self._open: list[_Snapshot] = []

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
        kicked: bool = False,
    ) -> GameEvent:
        """The CAST row (13b): emitted by the casting pipeline at 601.2h —
        after payment, before resolution — so "whenever you cast" triggers
        queue ABOVE the spell (they resolve first, CR 603.2). The ordinal
        is per-caster per-turn (the CastSpellEvent.ordinal vocabulary),
        journalled IN the row so a replay re-derives the same ordinals.

        ZND-1e: the trailing ``kicked`` flag journals CR 702.27a's choice
        (paid / not paid) with the row itself — WAS_KICKED reads it back
        from the judged object's own CAST row, so a replay re-derives the
        same answer. ``False`` keeps the pre-ZND-1e row shape's meaning
        (a non-kicker spell was never kicked, CR 702.27a)."""
        self.cast_counts[caster] = self.cast_counts.get(caster, 0) + 1
        return self._emit(
            KIND_CAST,
            spell,
            spell,
            "CAST",
            (
                caster,
                self.cast_counts[caster],
                spell_kind,
                from_zone,
                x_value,
                bool(kicked),
            ),
        )

    def emit_targeting(
        self,
        source_object: Handle,
        actor: Handle,
        designated: Sequence[Handle],
        *,
        cause_verb: str = "TARGET",
    ) -> None:
        """The TARGETING rows (r20b): one per designated object, Handle-
        sorted (the determinism law — designation sets are canonical order,
        mirroring declared_targets' sorted tuple). Empty designations emit
        nothing (a targetless cast/ability has no targeting event, CR
        115.4's self-clause included).

        H4 Scope C adds a separate lane for ONE_OF/REST partition choices:
        those rows use ``cause_verb="ONE_OF"`` or ``"REST"`` so branch
        coverage can distinguish the partition cardinalities from CR target
        designations without pretending a partition choice is a legal
        target event.
        """
        for target in sorted(designated):
            self._emit(
                KIND_TARGETING,
                target,
                source_object,
                cause_verb,
                (source_object, actor),
            )

    def emit_ability_activation(
        self,
        source: Handle,
        actor: Handle,
        ability_idx: int,
        *,
        mana: bool,
        loyalty: int | None,
    ) -> GameEvent:
        """The ABILITY_ACTIVATED row (R5-7, the AbilityActivatedEvent feed):
        one per activation, mana abilities included — legality.activate calls
        this right after the costs are paid. Subject = the object whose
        ability it is, cause = the activating player."""
        return self._emit(
            KIND_ABILITY_ACTIVATED,
            source,
            actor,
            "ACTIVATE",
            (ability_idx, bool(mana), loyalty),
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
        """Open an atom boundary: the world as it is now. ``record_atom`` closes it."""
        snap = self._capture()
        self._open.append(snap)
        return snap

    def open_depth(self) -> int:
        """V23: how many boundaries are open (the guarded effect lane's mark)."""
        return len(self._open)

    def drop_open(self, depth: int) -> None:
        """V23: forget the boundaries opened above ``depth`` whose atom raised and
        will never close (the guarded lane skips a dangling step and goes on)."""
        del self._open[depth:]

    def _capture(self) -> _Snapshot:
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
        after = self._capture()

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
            if from_state == ZONE_LIBRARY and kind == ZONE_HAND and cause_verb == "DRAW":
                # V23 (CR 121.1, 121.5): only a draw is a draw. A card put into a
                # hand from a library without the word "draw" (a search, Garruk's
                # reveal-and-put, a tutor) is a zone change, not a CARD_DRAWN row.
                # Every draw runs through a DRAW atom (_v_draw; the turn's draw is
                # the _TURN_DRAW atom), whose boundary moves nothing else.
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
                # r19a: the was-snapshot folds counters too (a 2/2 that died
                # with a +1/+1 counter on it DIED a 3/3 — Gadrak's C18 row).
                was_power, was_toughness = self.ledger.effective_pt(
                    identity, card, world.cards[card].counters
                )
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

        # --- life: gains are events; DEAL_DAMAGE losses are damage; every
        # other decrease (LOSE_LIFE, life-as-cost) is a LIFE_LOST row.
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
            else:
                # B3a: the amount is the ACTUAL state delta (the verb's
                # 0-clamp included), same clock/ordering spine as the
                # DAMAGE/LIFE_GAINED rows above, so a journal fold
                # (start + ΣLIFE_GAINED − ΣDAMAGE − ΣLIFE_LOST)
                # reconstructs the final life exactly.
                self._emit(
                    KIND_LIFE_LOST,
                    player,
                    cause,
                    cause_verb,
                    (was_life - now_life,),
                )

        # --- non-lethal card damage leaves no state trace: the 12a handler
        # tuples carry its amount (the "handlers already return info" path).
        consumed: set[int] = set()
        for entry in new_12a_tuples:
            if entry[1] in ("DAMAGE", "DAMAGE_LETHAL"):
                subject = parse_handle_tag(str(entry[2]))
                if subject.namespace == "card":
                    if entry[0] in before.consumed_raw:
                        continue  # V23: a nested boundary journalled it already
                    consumed.add(entry[0])
                    self._emit(
                        KIND_DAMAGE,
                        subject,
                        cause,
                        cause_verb,
                        (entry[3], True) if combat else (entry[3],),
                    )

        self._close(before, after, consumed | before.consumed_raw)
        return self.events[start:]

    def _close(self, before: _Snapshot, after: _Snapshot, consumed: set[int]) -> None:
        """V23: close ``before``'s boundary and fold what it journalled into every
        boundary still open around it, so the enclosing atom's own diff no longer
        sees those changes. Before this, a creature sacrificed as a spell's
        additional cost died twice (the SACRIFICE atom, then the cast's park
        boundary), and a spell cast by a CAST atom journalled its draws, moves and
        damage twice (Teferi's Tutelage milled 8 for 2 draws).

        Only the keys THIS boundary changed are folded, so an enclosing atom's own
        change made before the nested atom (a mana ability tapped raw inside a PAY
        atom) still shows in the enclosing diff. Not covered: the enclosing atom
        changes an object and the nested atom then changes the same object again;
        the enclosing change is folded away (no corpus atom does that)."""
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i] is before:
                del self._open[i:]  # anything above it never closed (it raised)
                break
        else:
            return  # not an open boundary: nothing encloses it
        if not self._open:
            return
        zones = [
            c
            for c in set(before.zones) | set(after.zones)
            if before.zones.get(c) != after.zones.get(c)
        ]
        tapped = [
            c
            for c in set(before.tapped) | set(after.tapped)
            if before.tapped.get(c) != after.tapped.get(c)
        ]
        counters = [
            c
            for c in set(before.counters) | set(after.counters)
            if before.counters.get(c) != after.counters.get(c)
        ]
        life = [p for p in after.life if before.life.get(p) != after.life[p]]
        for outer in self._open:
            for c in zones:
                if c in after.zones:
                    outer.zones[c] = after.zones[c]
                else:
                    outer.zones.pop(c, None)
            for c in tapped:
                if c in after.tapped:
                    outer.tapped[c] = after.tapped[c]
                else:
                    outer.tapped.pop(c, None)
            for c in counters:
                if c in after.counters:
                    outer.counters[c] = dict(after.counters[c])
                else:
                    outer.counters.pop(c, None)
            for p in life:
                outer.life[p] = after.life[p]
            outer.consumed_raw |= consumed

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
