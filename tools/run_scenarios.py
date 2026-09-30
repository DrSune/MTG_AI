#!/usr/bin/env python3
"""Round-16a validation-pack runner (BINDING plan §16a, R16-1).

A pack is a SMALL deterministic world-script: a handful of cards, one or
two scripted engine actions, and a post-condition block. It is the
executable form of "show me the rules interaction actually works" —
scenario packs prove the 16a behaviours end to end through the REAL
executor (compiled trigger IR included), not just the unit fixtures.

Usage:
    .venv/bin/python tools/run_scenarios.py [--dir tools/scenarios]

Exit code 0 = every pack passed. A failing expect prints the pack, the
key and observed-vs-expected — nothing else.

Pack vocabulary (all keys required as noted):
  world   : {"life": int, "seed": int}
  cards   : [{"key": str, "zone": "hand"|"battlefield", "controller": 0|1,
              "real": "<pool card name>"  OR
              "name"/"power"/"toughness"/"type" (synthetic)}]
  mana    : {"0": {"G": 5}, ...}            optional, per seat index
  steps   : [{"op": "deal_damage"|"fight", "source": key, "target": key
              [, "amount": int]},
             {"op": "cast", "real": name, "x": int?, "targets": [key...],
              "decisions": [str...]},
             {"op": "end_turn"}]
  expect  : {"life": {"0": int...}, "zone": {key: zone...},
             "damage": {key: int...}}  — damage is the 16a mark ledger
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    GameWorld,
)

ZONE_OF_NAME = {
    "battlefield": ZONE_BATTLEFIELD,
    "hand": ZONE_HAND,
    "graveyard": ZONE_GRAVEYARD,
    "exile": ZONE_EXILE,
}
UNIV = FAnd(())


class PackError(Exception):
    pass


def _atom(verb, **roles):
    from MTG_bot.core.ability_tree import Atom, AtomArgs

    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _bf_target():
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        UNIV,
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


class ScenarioRunner:
    def __init__(self, pack: dict, supply):
        self.pack = pack
        world_cfg = pack.get("world", {})
        self.world = GameWorld(
            num_players=2,
            start_life=world_cfg.get("life", 20),
            master_seed=world_cfg.get("seed", 7),
        )
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.seats = [self.p0, self.p1]
        self.ex = Executor(self.world)
        self.handles: dict[str, Any] = {}
        synth = 0
        for card in pack["cards"]:
            if "real" in card:
                record = None
                for oid, meta in supply.metas.items():
                    if meta.name == card["real"]:
                        record = supply.pool.results[oid].card
                        break
                if record is None:
                    raise PackError(f"pool has no card {card['real']!r}")
                identity = identity_of(record)
            else:
                synth += 1
                identity = CardIdentity(
                    oracle_id=f"9{synth:07d}-1111-2222-3333-444444444444",
                    name=card["name"],
                    type_line=card.get("type", "Creature"),
                    power=card.get("power"),
                    toughness=card.get("toughness"),
                    cmc=card.get("cmc", 2),
                )
            zone = ZONE_OF_NAME[card.get("zone", "battlefield")]
            self.handles[card["key"]] = self.world.add_card(
                identity, self.seats[card["controller"]], zone
            )
        # The real cards' triggers/abilities register from the compiled pool.
        self.registered = self.ex.attach_pool(supply.pool)
        for seat, colors in pack.get("mana", {}).items():
            for color, n in colors.items():
                self.world.players[self.seats[int(seat)]].mana_pool[color] = n
        self.ex.turn_open = True
        self.ex.phase = "FIRST_MAIN"
        self.world.active_player = self.p0

    def run_step(self, step: dict) -> None:
        op = step["op"]
        if op in ("deal_damage", "fight"):
            verb = Verb.DEAL_DAMAGE if op == "deal_damage" else Verb.FIGHT
            roles: dict[str, Any] = {"target": _bf_target()}
            if op == "deal_damage":
                roles["amount"] = QConst(step["amount"])
            self.ex.execute(
                _atom(verb, **roles),
                source=self.handles[step["source"]],
                controller=self.seats[step.get("controller", 0)],
                bindings={"target": self.handles[step["target"]]},
            )
        elif op == "cast":
            spell_key = step.get("key") or f"cast_{step['real']}"
            if spell_key not in self.handles:
                raise PackError(f"no hand card {spell_key!r} — add it under cards")
            cast(
                self.ex,
                self.seats[step.get("controller", 0)],
                self.handles[spell_key],
                x=step.get("x"),
                targets=tuple(self.handles[k] for k in step.get("targets", ())),
                decisions=tuple(step.get("decisions", ())),
            )
        elif op == "end_turn":
            self.ex.end_turn()
        else:
            raise PackError(f"unknown op {op!r}")

    def check(self) -> list[str]:
        fails = []
        for seat, life in self.pack.get("expect", {}).get("life", {}).items():
            got = self.world.players[self.seats[int(seat)]].life
            if got != life:
                fails.append(f"life[{seat}]: expected {life}, got {got}")
        for key, zone in self.pack.get("expect", {}).get("zone", {}).items():
            got = self.world.zone_of(self.handles[key]).kind
            if got != ZONE_OF_NAME[zone]:
                fails.append(f"zone[{key}]: expected {zone}, got {got}")
        want = {
            self.handles[k]: n
            for k, n in self.pack.get("expect", {}).get("damage", {}).items()
        }
        if self.ex.damage != want:
            got = {str(k): v for k, v in self.ex.damage.items()}
            exp = {
                k: n for k, n in self.pack.get("expect", {}).get("damage", {}).items()
            }
            fails.append(f"damage marks: expected {exp}, got {got}")
        return fails


def run_pack(path: Path, supply) -> list[str]:
    pack = json.loads(path.read_text())
    try:
        runner = ScenarioRunner(pack, supply)
    except PackError as e:
        return [f"setup: {e}"]
    for step in pack["steps"]:
        try:
            runner.run_step(step)
        except Exception as e:  # noqa: BLE001 — a crash IS the failure the pack hunts
            return [f"step {step}: {type(e).__name__}: {e}"]
    return runner.check()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--dir", default=str(REPO / "tools" / "scenarios"))
    args = ap.parse_args(argv)
    packs = sorted(Path(args.dir).glob("*.json"))
    if not packs:
        print(f"error: no packs in {args.dir}", file=sys.stderr)
        return 2
    supply = get_supply("all")
    failures = 0
    for path in packs:
        fails = run_pack(path, supply)
        if fails:
            failures += 1
            print(f"FAIL {path.name}")
            for line in fails:
                print(f"     {line}")
        else:
            print(f"PASS {path.name}")
    print(f"{len(packs) - failures}/{len(packs)} packs passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
