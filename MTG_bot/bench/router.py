"""``SeatRouter``: per-seat agents inside the engine's own game loop.

``_play`` (``core/executor/games.py`` ``_play_turns``) takes one policy object: it registers
``policy.answer`` as the decision provider for every seat and calls ``policy.take_acts(game,
seat)`` once in each main phase, before and after combat (CR 505.1). The router satisfies that
contract and dispatches each call to the right seat's driver:
- engine asks go to the seat the engine names (``protocol.resolve_ask_seat``);
- the act window goes to the active seat.

The act window offers PASS and the engine's menu (``core/executor/menu.py``: land drops, casts
with their kicker and X rows, non-mana activations from the battlefield and the hand, priced with
automatic payment from the pool, free sources and then costly ones; mana abilities are activated
while paying, never rows). Its limits are registered as scaffolds in BACKLOG. The router labels the
rows for its seat and asks:
- **Targets are asked slot by slot, one question per pick** (CR 601.2c: each word "target" is
  announced in turn), site ``pick:<source>:<slot>:<picks so far>``, over the candidates
  ``stack.slot_options`` leaves: none already picked for that slot (CR 115.3) and none that would
  leave a later slot without a legal target, so no illegal pair is ever offered. DONE ends a slot
  once it has its minimum (an "up to" slot may stay empty). A slot with exactly one legal filler
  is filled without asking, as the engine's own phantom gate does (``offers.py``). The rig
  reads the targets chosen so far in ``targets_so_far``.
- **X and modes come first** (CR 601.2b): X is part of the row (``cast:<card>:x<N>``), and a modal
  spell's modes are announced by ``stack.cast_modes`` (the engine's ``choose:`` question over the
  legal mode sets) before only the chosen modes' targets are asked.
- **At most ``MAX_ACTS_PER_STEP`` acts per window**, the engine's own cap: one window per main
  phase, the prompt naming which.

The router consumes no randomness, so a raw ``RandomPolicy`` behind it reproduces
``play_game`` exactly (``test_router.py``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
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
from MTG_bot.core.executor.games import MAX_ACTS_PER_STEP, Act
from MTG_bot.core.executor.legality import SECOND_MAIN
from MTG_bot.core.executor.menu import Row, menu, perform
from MTG_bot.core.executor.query import spell_target_slots
from MTG_bot.core.executor.stack import cast_modes, slot_options

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
        #: The targets chosen so far in the declaration being asked (``_targets``), every
        #: earlier slot's and this slot's earlier picks; rig.py puts them in the AskContext.
        self.targets_so_far: tuple[Handle, ...] = ()

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
        the same size in one window starts at the top again; without it the index would point
        under the viewed window, at a card its owner has not seen."""
        k = self._scry_index[what]
        tail = what.rsplit(":", 1)[-1]
        return k % int(tail) if tail.isdigit() and int(tail) > 0 else k

    def _context(self, what: str, seat: Handle, i: int) -> str:
        """Extra facts the decider legitimately has for this ask."""
        kind, count = ask_kind(what), what.rsplit(":", 1)[-1]
        if kind == "mulligan":  # mulligan:<seat>:<mulligans taken> (games.mulligans)
            order = "first" if self.game.world.player_order[0] == seat else "second"
            return f"You play {order}. Mulligans taken so far: {count}."
        if kind == "mulligan_bottom":  # mulligan_bottom:<seat>:<cards still to put there>
            return f"Cards still to put on the bottom, this one included: {count}."
        if kind != "scry":
            return ""
        # The k-th scry ask of one scry is about the k-th card from the top, which the scrying
        # player is looking at (verbs._v_scry asks top-first before moving anything).
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
        main = "second main phase (after combat)" if game.executor.phase == SECOND_MAIN else "first main phase"
        prompt = f"Your {main}: choose an action. PASS ends this main phase."
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
                prompt=prompt,
                options=tuple(option for option, _ in menu),
                refuse=0,
            )
            option, payload = menu[self._decide(driver, ask)]
            if option.token == "PASS":
                break
            self._execute(game, seat, i, option, payload)
        game.digest.append(f"T{game.world.turn}.end")

    def _act_menu(self, game: Game, seat: Handle, i: int) -> list[tuple[Option, Any]]:
        """PASS and the engine's menu (``executor.menu``), each row labelled for the seat."""
        executor = game.executor
        lens = self.lenses[i]
        out: list[tuple[Option, Any]] = [(Option("PASS", "PASS: end this main phase"), None)]
        for row in menu(executor, seat, hidden=self.stats[i]):
            out.append((Option(row.token, self._label(executor, lens, row)), row))
        return out

    def _label(self, executor: Any, lens: SeatLens, row: Row) -> str:
        name = lens.describe(executor, row.handle)
        if row.kind == "land":
            return f"play land {name}"
        if row.kind == "cast":
            if row.slots is None:
                more = " (then choose its mode)"
            else:
                more = " (then choose targets)" if any(not s.forced for s in row.slots) else ""
            kicked = " with kicker" if row.kicked else ""
            x = "" if row.x is None else f" with X = {row.x}"
            return f"cast {name}{kicked}{x}{more}"
        text = ability_line(self._record_of(row.handle), executor_text(lens, executor, row.handle), row.ability_idx)
        what = f'"{lens.text(text)}"' if text else f"ability #{row.ability_idx} (see the card text)"
        return f"activate {name}: {what}"

    def _targets(self, game: Game, slots: Sequence[Any], i: int, source: Handle) -> tuple:
        """The designation, asked slot by slot (CR 601.2c; the module docstring): one slot's
        targets, or for several slots one tuple per slot (``stack.designate_slots``)."""
        executor = game.executor
        lens = self.lenses[i]
        name = lens.describe(executor, source)
        groups: list[tuple[Handle, ...]] = []
        for j, slot in enumerate(slots):
            picked: list[Handle] = []
            if slot.forced:
                picked = list(slot_options(slots, tuple(groups)))[: slot.max_count]
            while not slot.forced and len(picked) < slot.max_count:
                remaining = slot_options(slots, tuple(groups), picked)
                if not remaining:
                    break
                options = [Option(str(c), lens.describe(executor, c, offered=True)) for c in remaining]
                refuse = None
                if len(picked) >= slot.min_count:
                    refuse = len(options)
                    options.append(Option("DONE", "no more targets"))
                self.targets_so_far = (*(h for g in groups for h in g), *picked)
                prompt = f"Choose a target for {name}."
                if len(slots) > 1:
                    so_far = ", ".join(lens.describe(executor, h) for h in self.targets_so_far)
                    prompt = f"Choose target {j + 1} of {len(slots)} for {name}" + (
                        f" (chosen so far: {so_far})." if so_far else ".")
                ask = Ask(
                    seat=i,
                    kind="target",
                    site=f"pick:{source}:{j}:{len(picked)}",
                    prompt=prompt,
                    options=tuple(options),
                    refuse=refuse,
                )
                token = options[self._decide(self.drivers[i], ask)].token
                if token == "DONE":
                    break
                picked.append(next(c for c in remaining if str(c) == token))
            groups.append(tuple(sorted(picked)))
        self.targets_so_far = ()
        return groups[0] if len(slots) == 1 else tuple(groups)

    def _execute(self, game: Game, seat: Handle, i: int, option: Option, row: Row) -> None:
        executor = game.executor
        name = game.name_of(row.handle)
        if row.kind == "land":
            game.attempted = f"land:{name}"
            perform(executor, seat, row)
            self._log(i, "land", row.handle)
            return
        if row.kind == "activate":
            targets = self._targets(game, row.slots, i, row.handle) if row.slots else ()
            game.attempted = f"act:{name}#{row.ability_idx}"
            perform(executor, seat, row, targets)
            self._log(i, "act", row.handle, f"#{row.ability_idx}")
            return
        modes: tuple[int, ...] = ()
        slots = row.slots
        if slots is None:
            # A modal spell. The mode ask goes through the engine channel (this
            # router answers it, routed to this seat), then its own slots are designated.
            _token, modes, _rest = cast_modes(executor, seat, row.handle, row.node, pay=row.pay)
            slots = spell_target_slots(executor, row.node, spell_handle=row.handle, seat=seat, modes=modes, pay=row.pay)
        targets = self._targets(game, slots, i, row.handle) if slots else ()
        flat = targets if len(slots) <= 1 else tuple(h for group in targets for h in group)
        game.attempted = f"cast:{name}"
        if not perform(executor, seat, row, targets, modes):
            # Each candidate is priced alone; several targets can together cost more than the
            # sources pay (two taxed targets, CR 601.2f): the cast is illegal and nothing
            # happens. Counted.
            self.stats[i]["unpayable_targets"] += 1
            return
        self._log(i, "cast", row.handle, f"{len(flat)}t" + ("" if row.x is None else f":x{row.x}"))
