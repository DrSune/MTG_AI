"""``SeatRouter``: per-seat agents inside the engine's own game loop.

``_play`` (``core/executor/games.py:1415``) takes one policy object: it registers
``policy.answer`` as the decision provider for every seat (``:1454``) and calls
``policy.take_acts(game, seat)`` once per turn (``:1485``). The router satisfies that contract and
dispatches each call to the right seat's driver:
- engine asks go to the seat the engine names (``protocol.resolve_ask_seat``);
- the act window goes to the active seat.

The act window mirrors the engine's surface, and its limits are registered as bench scaffolds in
BACKLOG:
- **The menu.** PASS, land drops, castable spells (base and kicked; a spell with X has one row
  per X from 0 to the largest payable X, CR 601.2b, 107.3a) and activations, mana abilities
  included except a free source's (below). Tokens: ``land:<card>``, ``cast:<card>[:k][:x<N>]``
  (no ``:x`` for X = 0), ``act:<card>:<ability index>``.
- **Payment is automatic: the pool first, then free sources** (CR 601.2g-h, 605.3a). The engine
  pays only from the floating pool. A free source is a non-creature permanent whose mana ability
  costs only {T} (lands, plain mana rocks). A cast or activation is offered when the pool plus
  the untapped free sources pay its whole cost, a target's cost increase included (CR 601.2f:
  Pursued Whale's {3}, Terror of the Peaks' 3 life, and life only up to the life total, CR
  119.4); choosing it taps the sources ``legality.plan_mana_taps`` picks, by one deterministic
  rule that keeps the most mana options open, and the engine then pays. Every other mana ability
  is its own row that adds to the pool: a creature's (tapped, it cannot attack or block), a
  sacrifice (Treasure), a mana-cost filter (Prismite's {2}). Pool mana lasts until this main
  phase ends (CR 500.5), the only act window of the turn. The engine's response windows pay the
  same way. Which free sources pay is a scaffold (BACKLOG): a learned payment choice removes it.
- **Rows the engine cannot designate are hidden and counted:** more than one target slot, or a
  slot with too few candidates (``games.py:562-573``).
- **Targets are asked one at a time** from the slot's candidates, then validated by the engine's
  oracle (``validate_target_selection``). A slot with exactly one legal filler is filled without
  asking, as the engine's own phantom gate does (``offers.py:47-70``).
- **A modal spell announces its modes first** (CR 601.2b, V17): ``stack.cast_modes`` asks the
  engine's ``choose:`` question over the legal mode sets, then only the chosen modes' targets are
  asked.
- **At most ``MAX_ACTS_PER_STEP`` acts per window**, the engine's own cap.

The router consumes no randomness, so a raw ``RandomPolicy`` behind it reproduces
``play_game`` exactly (``test_router.py``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from itertools import count
from typing import TYPE_CHECKING, Any

from MTG_bot.bench.agents import AgentError, Observation, is_raw
from MTG_bot.bench.protocol import (
    Ask,
    Option,
    ability_line,
    ask_kind,
    engine_ask,
    executor_text,
    resolve_ask_seat,
)
from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    CostTap,
    SpellAbility,
    is_mana_ability,
)
from MTG_bot.core.executor.games import MAX_ACTS_PER_STEP, Act
from MTG_bot.core.executor.legality import (
    _cost_has_x,
    _mana_tap_options,
    ability_playable,
    activate,
    kicker_of,
    plan_mana_taps,
    spell_castable,
    spell_cost,
    spell_record,
    tap_for_payment,
)
from MTG_bot.core.executor.query import (
    activation_target_slots,
    cast_mode_options,
    inert_free_row,
    modal_choose,
    spell_target_slots,
    validate_target_selection,
)
from MTG_bot.core.executor.stack import cast, cast_modes, land_playable, play_land
from MTG_bot.core.state import ZONE_BATTLEFIELD

if TYPE_CHECKING:
    from MTG_bot.bench.view import SeatLens
    from MTG_bot.core.executor.games import Game, Supply
    from MTG_bot.core.identity import Handle


class SeatRouter:
    def __init__(
        self,
        game: Game,
        drivers: Sequence[Any],
        lenses: Sequence[SeatLens],
        *,
        supply: Supply | None = None,
        strict: bool = True,
    ) -> None:
        self.game = game
        self.drivers = list(drivers)
        self.lenses = list(lenses)
        self.supply = supply
        self.strict = strict
        self.stats: list[Counter[str]] = [Counter() for _ in self.drivers]
        self.acts: list[Act] = []  # read by games._describe_crash
        self._scry_index: Counter[str] = Counter()

    # ------------------------------------------------------------- helpers

    def _index(self, seat: Handle) -> int:
        return self.game.world.player_order.index(seat)

    def _decide(self, driver: Any, ask: Ask) -> int:
        st = self.stats[ask.seat]
        st["asks"] += 1
        st[f"ask:{ask.kind}"] += 1
        if ask.leaky:
            st["leaky_asks"] += 1
        idx = driver.decide(ask, Observation(self.lenses[ask.seat], self.game.executor))
        if not isinstance(idx, int) or not 0 <= idx < len(ask.options):
            raise AgentError(f"agent {getattr(driver, 'name', driver)!r} returned {idx!r} for {ask.site}")
        return idx

    def _record_of(self, handle: Handle) -> Any:
        if self.supply is None:
            return None
        oid = self.game.world.cards[handle].identity.oracle_id
        result = self.supply.pool.results.get(oid)
        return result.card if result is not None else None

    def _log(self, seat_index: int, kind: str, handle: Handle, detail: str = "") -> None:
        name = self.game.name_of(handle)
        act = Act(self.game.world.turn, seat_index, kind, name, detail)
        self.acts.append(act)
        self.game.acts += 1
        self.game.digest.append(f"T{self.game.world.turn}.{act.digest()}")

    # --------------------------------------------------------- engine asks

    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        executor = self.game.executor
        seat = resolve_ask_seat(what, executor.decisions.asking_seat, strict=self.strict)
        i = self._index(seat)
        driver = self.drivers[i]
        if is_raw(driver):
            self.stats[i]["asks"] += 1
            self.stats[i][f"ask:{ask_kind(what)}"] += 1
            return driver.answer(vocab, what)
        ask = engine_ask(self.lenses[i], executor, vocab, what, i, context=self._context(what, seat, i))
        return ask.options[self._decide(driver, ask)].token

    def scry_position(self, what: str) -> int:
        """Which card from the top the next ask of this scry is about. The engine asks once per
        card, top first, all n asks under one key ``scry:<player>:<n>`` (verbs._v_scry), and the
        counter resets only when an act window opens, so it is taken modulo n: a second scry of
        the same size in one window starts at the top again. Without the modulo it pointed under
        the viewed window - the wrong card, and one its owner has not seen (3 of 471 scry asks
        in 600 heuristic games, 2026-11-05)."""
        k = self._scry_index[what]
        tail = what.rsplit(":", 1)[-1]
        return k % int(tail) if tail.isdigit() and int(tail) > 0 else k

    def _context(self, what: str, seat: Handle, i: int) -> str:
        """Extra facts the decider legitimately has for this ask."""
        if ask_kind(what) != "scry":
            return ""
        # The k-th scry ask of one scry is about the k-th card from the top, which the scrying
        # player is looking at (verbs.py:1072-1082 asks top-first before moving anything).
        k = self.scry_position(what)
        self._scry_index[what] += 1
        library = self.game.world.players[seat].zone("library").entries
        if k < len(library):
            card = library[-1 - k]
            return f"The card is {self.lenses[i].describe(self.game.executor, card, offered=True)}."
        return ""

    # ----------------------------------------------------------- act window

    def take_acts(self, game: Game, seat: Handle) -> None:
        i = self._index(seat)
        driver = self.drivers[i]
        self._scry_index.clear()
        if is_raw(driver):
            driver.take_acts(game, seat)
            return
        for _ in range(MAX_ACTS_PER_STEP):
            if game.over_reason() is not None:
                return
            if not game.executor.turn_open:
                break  # an effect ended the turn (CR 724.1): the act window is over
            menu = self._act_menu(game, seat, i)
            if len(menu) == 1:  # PASS is the only legal act: not a decision
                break
            ask = Ask(
                seat=i,
                kind="act",
                site=f"act:{seat}:{game.world.turn}",
                prompt="Your main phase: choose an action. PASS ends your actions for this turn.",
                options=tuple(option for option, _ in menu),
                refuse=0,
            )
            option, payload = menu[self._decide(driver, ask)]
            if option.token == "PASS":
                break
            self._execute(game, seat, i, option, payload)
        game.digest.append(f"T{game.world.turn}.end")

    def _act_menu(self, game: Game, seat: Handle, i: int) -> list[tuple[Option, Any]]:
        executor = game.executor
        world = executor.world
        lens = self.lenses[i]
        menu: list[tuple[Option, Any]] = [(Option("PASS", "PASS: end your actions this turn"), None)]
        for handle in sorted(world.players[seat].zone("hand").entries):
            if land_playable(executor, seat, handle) is None:
                menu.append((Option(f"land:{handle}", f"play land {lens.describe(executor, handle)}"), ("land", handle)))
            elif (handle,) not in game.unsupported_rows:
                menu.extend(self._cast_rows(executor, seat, i, handle))
        free = {(taps[0].source, taps[0].ability_idx) for taps in _mana_tap_options(executor, seat)}
        for source, idx, ability in _activated_abilities(executor, seat):
            if (source, idx) in free or (source, idx) in game.unsupported_rows:
                continue  # a free source's mana is paid automatically, never offered as a row
            row = self._activation_row(executor, seat, i, source, idx, ability)
            if row is not None:
                menu.append(row)
        return menu

    def _cast_rows(self, executor: Any, seat: Handle, i: int, handle: Handle) -> list[tuple[Option, Any]]:
        """One row per payable declaration of a spell in hand: base and kicked, and one per X."""
        record = spell_record(executor, handle)
        node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None) if record else None
        if node is None:
            return []
        name = self.lenses[i].describe(executor, handle)
        kicker = kicker_of(record)
        rows: list[tuple[Option, Any]] = []
        for kicked in (False, True) if kicker is not None else (False,):
            extra = tuple(node.additional_costs) + ((kicker.cost,) if kicked else ())
            for x in count() if _cost_has_x(spell_cost(record, extra)) else (None,):

                def pay(targets: Sequence[Handle], kicked: bool = kicked, x: int | None = x) -> bool:
                    return _cast_taps(executor, seat, handle, kicked, x, tuple(targets)) is not None

                if not pay(()):
                    break  # a larger X costs more: no larger X is payable either
                slots: list[Any] | None = None  # a modal spell's slots follow its modes (_execute)
                if modal_choose(node) is None:
                    slots = spell_target_slots(executor, node, spell_handle=handle, seat=seat, pay=pay)
                    designable = len(slots) <= 1 and all(s.min_count <= len(s.candidates) for s in slots)
                    more = " (then choose targets)" if slots and not slots[0].forced else ""
                else:
                    # V17 (CR 601.2b-c): the modes are announced first (an engine ask, in
                    # _execute), and only the chosen modes' targets exist. Offered when some
                    # legal mode set can be designated with one slot at most.
                    designable = any(
                        len(spell_target_slots(executor, node, spell_handle=handle, seat=seat, modes=m, pay=pay)) <= 1
                        for _t, m in cast_mode_options(executor, node, spell_handle=handle, seat=seat, pay=pay)
                    )
                    more = " (then choose its mode)"
                if not designable:
                    self.stats[i]["hidden_rows"] += 1
                    break
                token = f"cast:{handle}{':k' if kicked else ''}{f':x{x}' if x else ''}"
                label = f"cast {name}{' with kicker' if kicked else ''}{'' if x is None else f' with X = {x}'}{more}"
                rows.append((Option(token, label), ("cast", handle, node, kicked, x, slots, pay)))
        return rows

    def _activation_row(
        self, executor: Any, seat: Handle, i: int, source: Handle, idx: int, ability: ActivatedAbility
    ) -> tuple[Option, Any] | None:
        # An ability whose cost taps its own source cannot also tap that source for mana.
        own_tap = any(isinstance(part, CostTap) and part.target is None for part in ability.cost.parts)
        exclude = frozenset({source}) if own_tap else frozenset()
        if _activation_taps(executor, seat, source, idx, exclude) is None:
            return None
        if inert_free_row(executor, ability, source, seat):
            return None  # a phantom option: it could do nothing (Radha's land row)
        mana = is_mana_ability(ability)
        slots = [] if mana else list(activation_target_slots(executor, ability.effect, source=source, seat=seat))
        if len(slots) > 1 or any(s.min_count > len(s.candidates) for s in slots):
            self.stats[i]["hidden_rows"] += 1
            return None
        lens = self.lenses[i]
        text = ability_line(self._record_of(source), executor_text(lens, executor, source), idx)
        what = f'"{lens.text(text)}"' if text else f"ability #{idx} (see the card text)"
        adds = " (adds the mana to your pool)" if mana else ""
        option = Option(f"act:{source}:{idx}", f"activate {lens.describe(executor, source)}: {what}{adds}")
        return option, ("activate", source, idx, slots, exclude)

    def _targets(self, game: Game, slots: Sequence[Any], i: int, source: Handle) -> tuple[Handle, ...] | None:
        chosen: list[Handle] = []
        executor = game.executor
        lens = self.lenses[i]
        for slot in slots:
            if slot.forced:
                picked = sorted(slot.candidates)[: slot.max_count]
            else:
                picked = []
                while len(picked) < min(slot.max_count, len(slot.candidates)):
                    remaining = [c for c in sorted(slot.candidates) if c not in picked]
                    options = [Option(str(c), lens.describe(executor, c, offered=True)) for c in remaining]
                    refuse = None
                    if len(picked) >= slot.min_count:
                        refuse = len(options)
                        options.append(Option("DONE", "no more targets"))
                    ask = Ask(
                        seat=i,
                        kind="target",
                        site=f"pick:{source}:{len(picked)}",
                        prompt=f"Choose a target for {lens.describe(executor, source)}.",
                        options=tuple(options),
                        refuse=refuse,
                    )
                    token = options[self._decide(self.drivers[i], ask)].token
                    if token == "DONE":
                        break
                    picked.append(next(c for c in remaining if str(c) == token))
                picked.sort()
            if validate_target_selection(slot, picked) is not None:
                self.stats[i]["invalid_targets"] += 1
                return None
            chosen.extend(picked)
        return tuple(chosen)

    def _execute(self, game: Game, seat: Handle, i: int, option: Option, payload: Any) -> None:
        executor = game.executor
        kind = payload[0]
        if kind == "land":
            source = payload[1]
            game.attempted = f"land:{game.name_of(source)}"
            play_land(executor, seat, source)
            self._log(i, "land", source)
            return
        if kind == "activate":
            _, source, idx, slots, exclude = payload
            targets = self._targets(game, slots, i, source) if slots else ()
            if targets is None:
                return
            game.attempted = f"act:{game.name_of(source)}#{idx}"
            tap_for_payment(executor, seat, _activation_taps(executor, seat, source, idx, exclude) or ())
            activate(executor, source, idx, seat=seat, targets=targets)
            self._log(i, "act", source, f"#{idx}")
            return
        _, source, node, kicked, x, slots, pay = payload
        modes: tuple[int, ...] = ()
        if slots is None:
            # V17: a modal spell. The mode ask goes through the engine channel (this
            # router answers it, routed to this seat), then its own slots are designated.
            _token, modes, _rest = cast_modes(executor, seat, source, node, pay=pay)
            slots = spell_target_slots(executor, node, spell_handle=source, seat=seat, modes=modes, pay=pay)
            if len(slots) > 1:
                self.stats[i]["hidden_rows"] += 1
                return
        targets = self._targets(game, slots, i, source) if slots else ()
        if targets is None:
            return
        taps = _cast_taps(executor, seat, source, kicked, x, targets)
        if taps is None:
            # Each candidate is priced alone; several picks of one slot can together cost more
            # than the pool and the free sources pay (two taxed targets). Counted; nothing is cast.
            self.stats[i]["unpayable_targets"] += 1
            return
        game.attempted = f"cast:{game.name_of(source)}"
        tap_for_payment(executor, seat, taps)
        cast(executor, seat, source, x=x, kicked=kicked, mode_choices=modes, targets=targets)
        self._log(i, "cast", source, f"{len(targets)}t" + ("" if x is None else f":x{x}"))


def _cast_taps(
    executor: Any, seat: Handle, handle: Handle, kicked: bool, x: int | None, targets: tuple[Handle, ...]
) -> Any:
    """The free sources that pay this declaration's total cost (CR 601.2f-h) with what the pool
    holds: () when the pool pays it, None when nothing does."""
    return plan_mana_taps(
        executor, seat, lambda: spell_castable(executor, seat, handle, x=x, kicked=kicked, targets=targets)[0]
    )


def _activation_taps(executor: Any, seat: Handle, source: Handle, idx: int, exclude: frozenset) -> Any:
    """The free sources, never one in ``exclude``, that pay an activation; as :func:`_cast_taps`."""
    return plan_mana_taps(
        executor, seat, lambda: ability_playable(executor.world, executor, source, idx, seat=seat), exclude=exclude
    )


def _activated_abilities(executor: Any, seat: Handle) -> list[tuple[Handle, int, ActivatedAbility]]:
    """Every activated ability of a permanent ``seat`` controls, printed and granted (a granted one
    is numbered -k-1), in ``legal_activations``' order: its scan, without its price (the pool
    alone)."""
    world = executor.world
    rows: list[tuple[Handle, int, ActivatedAbility]] = []
    for handle in sorted(h for p in world.player_order for h in world.players[p].zone(ZONE_BATTLEFIELD).entries):
        if executor.controller_of(handle) != seat:
            continue
        record = executor.binder.handle_record.get(handle)
        printed = list(enumerate(record.abilities)) if record is not None else []
        granted = [(-k - 1, entry.node) for k, entry in enumerate(executor.layers.granted_activated(handle))]
        rows += [(handle, idx, ab) for idx, ab in printed + granted if isinstance(ab, ActivatedAbility)]
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows
