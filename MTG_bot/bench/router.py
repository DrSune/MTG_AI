"""``SeatRouter``: per-seat agents inside the engine's own game loop.

``_play`` (``core/executor/games.py:1313``) takes one policy object: it registers
``policy.answer`` as the decision provider for every seat (``:1349``) and calls
``policy.take_acts(game, seat)`` once per turn (``:1380``). The router satisfies that contract and
dispatches each call to the right seat's driver:
- engine asks go to the seat the engine names (``protocol.resolve_ask_seat``);
- the act window goes to the active seat.

The act window mirrors the engine's surface, and its limits are registered as bench scaffolds in
BACKLOG:
- **The menu.** PASS, `TAP_ALL_MANA`, land drops, castable spells (base and kicked) and non-mana
  activations, all from the query surface (``legal_casts``, ``legal_activations``).
- **`TAP_ALL_MANA` is necessary.** Casting pays only from the floating pool (measured 2026-10-24),
  and pools never empty, so tapping everything costs nothing.
- **Rows the engine cannot designate are hidden and counted:** more than one target slot, or a
  slot with too few candidates (``games.py:562-573``). X is always declared 0.
- **Targets are asked one at a time** from the slot's candidates, then validated by the engine's
  oracle (``validate_target_selection``). A slot with exactly one legal filler is filled without
  asking, as the engine's own phantom gate does (``offers.py:47-70``).
- **At most ``MAX_ACTS_PER_STEP`` acts per window**, the engine's own cap.

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
from MTG_bot.core.ability_tree import is_mana_ability
from MTG_bot.core.executor.games import MAX_ACTS_PER_STEP, Act
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.executor.query import (
    activation_target_slots,
    legal_activations,
    legal_casts,
    spell_target_slots,
    validate_target_selection,
)
from MTG_bot.core.executor.stack import cast, play_land

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

    def _context(self, what: str, seat: Handle, i: int) -> str:
        """Extra facts the decider legitimately has for this ask."""
        if ask_kind(what) != "scry":
            return ""
        # The k-th scry ask of one scry is about the k-th card from the top, which the scrying
        # player is looking at (verbs.py:1072-1082 asks top-first before moving anything).
        k = self._scry_index[what]
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
        st = self.stats[i]
        rows = legal_casts(world, executor, seat)
        activations = [
            o
            for o in legal_activations(world, executor, seat)
            if (o.source, o.ability_idx) not in game.unsupported_rows
        ]
        mana = [o for o in activations if self._is_mana(executor, seat, o)]
        mana_keys = {(o.source, o.ability_idx) for o in mana}
        menu: list[tuple[Option, Any]] = [(Option("PASS", "PASS: end your actions this turn"), None)]
        if mana:
            menu.append(
                (Option("TAP_ALL_MANA", f"tap all {len(mana)} available mana abilities (mana stays in your pool)"), ("tap", mana))
            )
        for row in rows:
            name = lens.describe(executor, row.handle)
            if row.land:
                menu.append((Option(f"land:{row.handle}", f"play land {name}"), ("land", row, ())))
                continue
            if (row.handle,) in game.unsupported_rows:
                continue
            assert row.node is not None  # a non-land legal_casts row carries its SpellAbility
            slots = spell_target_slots(executor, row.node, spell_handle=row.handle, seat=seat)
            if len(slots) > 1 or any(s.min_count > len(s.candidates) for s in slots):
                st["hidden_rows"] += 1
                continue
            kicked = " with kicker" if row.kicked else ""
            more = " (then choose targets)" if slots and not slots[0].forced else ""
            menu.append((Option(f"cast:{row.handle}{':k' if row.kicked else ''}", f"cast {name}{kicked}{more}"), ("cast", row, slots)))
        for option in activations:
            if (option.source, option.ability_idx) in mana_keys:
                continue
            slots = list(activation_target_slots(executor, option.ability.effect, source=option.source, seat=seat))
            if len(slots) > 1 or any(s.min_count > len(s.candidates) for s in slots):
                st["hidden_rows"] += 1
                continue
            text = ability_line(
                self._record_of(option.source), executor_text(lens, executor, option.source), option.ability_idx
            )
            what = f'"{lens.text(text)}"' if text else f"ability #{option.ability_idx} (see the card text)"
            menu.append(
                (
                    Option(f"act:{option.source}:{option.ability_idx}", f"activate {lens.describe(executor, option.source)}: {what}"),
                    ("activate", option, slots),
                )
            )
        return menu

    @staticmethod
    def _is_mana(executor: Any, seat: Handle, option: Any) -> bool:
        """A mana ability by CR 605.1a: no target, could add mana, not a loyalty ability, and
        no card moved to or from a library. R5-7: the engine's one classifier decides
        (:func:`~MTG_bot.core.ability_tree.is_mana_ability`), the same one the games driver,
        the activation journal and the NON_MANA activation lock read. A mana ability never
        targets, so TAP_ALL_MANA's ``targets=()`` is always a legal designation (the B-34
        crash, "Tap target creature you don't control" behind TAP_ALL_MANA, cannot recur).
        """
        del executor, seat  # the classification is a property of the ability itself
        return is_mana_ability(option.ability)

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
        if kind == "tap":
            # Each listed mana ability at most once: an untapping or self-refilling mana ability
            # must not loop. That is a rail, not a strategy limit.
            for mana in payload[1]:
                live = {(o.source, o.ability_idx) for o in legal_activations(executor.world, executor, seat)}
                if (mana.source, mana.ability_idx) in live:
                    game.attempted = f"act:{game.name_of(mana.source)}#{mana.ability_idx}"
                    activate(executor, mana.source, mana.ability_idx, seat=seat, targets=())
                    self._log(i, "act", mana.source, f"#{mana.ability_idx}")
            return
        _, row, slots = payload
        source = row.handle if kind in ("land", "cast") else row.source
        targets = self._targets(game, slots, i, source) if slots else ()
        if targets is None:
            return
        if kind == "land":
            game.attempted = f"land:{game.name_of(source)}"
            play_land(executor, seat, source)
            self._log(i, "land", source)
        elif kind == "cast":
            game.attempted = f"cast:{game.name_of(source)}"
            cast(executor, seat, source, kicked=row.kicked, targets=targets)
            self._log(i, "cast", source, f"{len(targets)}t")
        else:
            game.attempted = f"act:{game.name_of(source)}#{row.ability_idx}"
            activate(executor, source, row.ability_idx, seat=seat, targets=targets)
            self._log(i, "act", source, f"#{row.ability_idx}")
