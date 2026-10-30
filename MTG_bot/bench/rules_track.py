"""Track R, rules prediction: from a board and scripted actions, predict the resulting state.

It measures world-model fidelity, i.e. whether a model understands how the components in
``primer.py`` act and interact. The ground truth is the engine on the scripted scenario packs
(``tools/scenarios``). Only packs the engine passes are used: their expectations were authored
from the printed cards and the rules, and the engine agrees with them.

**Faithful or excluded.** Every step is rendered into words, or the item is excluded with the
reason listed by ``coverage``. The track never guesses. Exclusions:
- ability indexes that cannot be mapped to an oracle line;
- choices given as opaque numbers;
- combat damage-order and trample lanes;
- packs that expect an engine error.

**Self-check at build time.** For each item the steps are replayed on a fresh runner, and the
state readers here must reproduce every gold value. A mismatch is a reader bug, counted as
``reader_mismatch``; the tests require zero.

**Scoring and §17.** ``all_keys`` accuracy is null-favourable: a "nothing changes" answerer
(``NullAnswerer``) scores well, because most keys do not move. The headline is therefore
``delta`` accuracy, over the keys whose gold differs from the initial state, where the null
answerer scores exactly 0.

**Contamination.** The packs are in a public repository, so this is the public development split.
Items carry the canary; the masked variant replaces every card name (``masking.py``); the masking
gap is reported.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from MTG_bot.bench import CANARY
from MTG_bot.bench.masking import NameMasker
from MTG_bot.bench.protocol import ability_line
from MTG_bot.bench.view import OracleIndex
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

PACK_DIR = Path(__file__).resolve().parents[2] / "tools" / "scenarios"
LANES = ("life", "zone", "counters", "tapped", "hand", "tokens", "power", "toughness", "battlefield_pt", "damage", "mana_pool")
EXPLAINED_WORDS = {"ATTACK", "DECLINE", "top", "bottom", "fire", "skip", "PASS", "PAY", "NONE"}
WORD_TEXT = {"fire": "yes", "skip": "no", "top": "keep it on top", "bottom": "put it on the bottom"}


class Unrenderable(ValueError):
    pass


@dataclass
class Item:
    id: str
    set_code: str
    variant: str
    prompt: str
    gold: dict[str, dict[str, Any]]
    initial: dict[str, dict[str, Any]]
    canary: str = CANARY

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "set": self.set_code, "variant": self.variant, "canary": self.canary,
                "prompt": self.prompt, "gold": self.gold, "initial": self.initial}


@dataclass
class Coverage:
    packs: int = 0
    items: int = 0
    excluded: Counter[str] = field(default_factory=Counter)
    reader_mismatch: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ readers


def read_state(runner: Any, labels: dict[str, str], gold_shape: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The current value of every key in ``gold_shape``, read the way ``ScenarioRunner.check`` reads it."""
    world, ex = runner.world, runner.ex
    by_label = {label: runner.handles[key] for key, label in labels.items()}
    out: dict[str, dict[str, Any]] = {}
    for lane, keys in gold_shape.items():
        got: dict[str, Any] = {}
        for k in keys:
            if lane == "life":
                got[k] = world.players[runner.seats[int(k)]].life
            elif lane == "hand":
                got[k] = len(world.players[runner.seats[int(k)]].zone(ZONE_HAND).entries)
            elif lane == "mana_pool":
                pool = world.players[runner.seats[int(k)]].mana_pool
                got[k] = {c: n for c, n in sorted(pool.items()) if n}
            elif lane == "zone":
                # "ceased", as ScenarioRunner.check reads it: a token that left the battlefield
                # ceased to exist (CR 704.5d) and is in no zone.
                h = by_label[k]
                got[k] = world.zone_of(h).kind if h in world.cards else "ceased"
            elif lane == "counters":
                got[k] = {c: n for c, n in sorted(world.cards[by_label[k]].counters.items())}
            elif lane == "tapped":
                got[k] = bool(world.cards[by_label[k]].tapped)
            elif lane in ("power", "toughness"):
                h = by_label[k]
                p, t = ex.ledger.effective_pt(world.cards[h].identity, h, world.cards[h].counters)
                got[k] = p if lane == "power" else t
            elif lane == "tokens":
                got[k] = sum(
                    1 for h, c in world.cards.items()
                    if c.identity.name == k and world.zone_of(h).kind == ZONE_BATTLEFIELD
                    and (getattr(c.identity, "is_token", False) or getattr(ex.binder.handle_record.get(h), "is_token", False))
                )
            elif lane == "battlefield_pt":
                found = [h for h, c in world.cards.items() if c.identity.name == k and world.zone_of(h).kind == ZONE_BATTLEFIELD]
                if len(found) != 1:
                    got[k] = None
                else:
                    h = found[0]
                    got[k] = list(ex.ledger.effective_pt(world.cards[h].identity, h, world.cards[h].counters))
        if lane == "damage":
            reverse = {h: label for label, h in by_label.items()}
            got = {reverse.get(h, str(h)): n for h, n in sorted(ex.damage.items(), key=lambda kv: str(kv[0])) if n}
        out[lane] = got
    return out


def _gold(pack: dict, labels: dict[str, str]) -> dict[str, dict[str, Any]]:
    expect = pack.get("expect", {})
    gold: dict[str, dict[str, Any]] = {}
    for lane in LANES:
        if lane not in expect:
            continue
        values: Any = expect[lane]
        if lane in ("zone", "counters", "tapped", "power", "toughness"):
            values = {labels[k]: v for k, v in values.items()}
        if lane == "damage":
            values = {labels.get(k, k): n for k, n in values.items() if n}
        if lane == "counters":
            values = {k: dict(sorted(v.items())) for k, v in values.items()}
        if lane == "tapped":
            values = {k: bool(v) for k, v in values.items()}
        if lane == "mana_pool":
            values = {k: {c: n for c, n in sorted(dict(v).items()) if n} for k, v in values.items()}
        if lane == "battlefield_pt":
            values = {k: list(v) for k, v in values.items()}
        gold[lane] = dict(values)
    return gold


# -------------------------------------------------------------------- render


def _render_state(runner: Any, labels: dict[str, str], name: Callable[[str], str], text: Callable[[str], str], oracle: OracleIndex) -> str:
    world, ex = runner.world, runner.ex
    reverse = {runner.handles[k]: label for k, label in labels.items()}
    seen: dict[str, str] = {}

    def obj(h: Any) -> str:
        card = world.cards[h]
        nm = name(card.identity.name)
        txt = oracle.text(card.identity.oracle_id) or (card.identity.oracle_text or "")
        if txt:
            seen.setdefault(nm, text(txt).replace("\n", " / "))
        bits = [f"{reverse[h]} {nm}" if h in reverse else nm]
        if card.identity.power is not None and world.zone_of(h).kind == ZONE_BATTLEFIELD:
            p, t = ex.ledger.effective_pt(card.identity, h, card.counters)
            bits.append(f"{p}/{t}")
        elif card.identity.power is not None:
            bits.append(f"{card.identity.power}/{card.identity.toughness}")
        if card.tapped:
            bits.append("tapped")
        if card.counters:
            bits.append("counters " + ",".join(f"{k}={v}" for k, v in sorted(card.counters.items()) if v))
        if ex.damage.get(h):
            bits.append(f"damage {ex.damage[h]}")
        host = ex.attachments.get(h)
        if host is not None:
            bits.append(f"attached to {reverse.get(host, name(world.cards[host].identity.name))}")
        return " ".join(bits)

    lines = [f"It is seat {world.player_order.index(world.active_player)}'s turn."]
    for seat, ph in enumerate(world.player_order):
        player = world.players[ph]
        pool = ", ".join(f"{c}{n}" for c, n in sorted(player.mana_pool.items()) if n) or "empty"
        lines.append(f"Seat {seat}: life {player.life}; mana pool {pool}.")
        for label, kind, top_first in (("hand", ZONE_HAND, False), ("battlefield", ZONE_BATTLEFIELD, False),
                                       ("graveyard", ZONE_GRAVEYARD, False), ("exile", ZONE_EXILE, False),
                                       ("library, top first", ZONE_LIBRARY, True)):
            entries = list(player.zone(kind).entries)
            if top_first:
                entries = entries[::-1]
            lines.append(f"  {label}: " + ("; ".join(obj(h) for h in entries) or "(none)"))
    lines.append("Card texts:")
    lines += [f"  {nm}: {txt}" for nm, txt in sorted(seen.items())]
    return "\n".join(lines)


def _words(words: Sequence[str], labels: dict[str, str], *, allow_players: bool = False) -> list[str]:
    out = []
    for w in words:
        if w in labels:
            out.append(labels[w])
        elif w in EXPLAINED_WORDS:
            out.append(WORD_TEXT.get(w, w))
        elif allow_players and isinstance(w, str) and w.startswith("player:"):
            out.append(f"seat {w.split(':', 1)[1]}")
        else:
            raise Unrenderable("opaque decision word")
    return out


def _render_step(step: dict, labels: dict[str, str], runner: Any, supply: Any, oracle: OracleIndex, text: Callable[[str], str]) -> str:
    op = step["op"]

    def L(key: str) -> str:
        return labels.get(key, key)
    if step.get("expect_raise"):
        raise Unrenderable("expects an engine error")
    if op == "life":
        return f"Seat {step['seat']}'s life total becomes {step['set']}."
    if op == "deal_damage":
        return f"{L(step['source'])} deals {step['amount']} damage to {L(step['target'])}."
    if op == "fight":
        return f"{L(step['source'])} fights {L(step['target'])}."
    if op == "loyalty":
        return f"{L(step['key'])}'s loyalty becomes {step['set']}."
    if op == "end_turn":
        return "The turn ends (end step and cleanup)."
    if op == "advance_turn":
        return "The next turn begins (untap, upkeep, draw)."
    if op == "play":
        return f"Seat {step.get('seat', 0)} plays the land {L(step['key'])}."
    if op == "enter":
        return f"{L(step['key'])} is put onto the battlefield from its owner's hand{' tapped' if step.get('tapped') else ''}."
    if op == "enchant":
        return f"{L(step['aura'])} becomes attached to {L(step['host'])}."
    choices = ""
    if step.get("decisions") and op != "combat":
        choices = " Choices made during this step, in the order asked: " + ", ".join(
            _words(step["decisions"], labels, allow_players=op == "cast")
        ) + "."
    if op == "cast":
        key = step.get("key") or f"cast_{step['real']}"
        targets = [L(k) for k in step.get("targets", ())]
        targets += [f"seat {w.split(':', 1)[1]}" for w in step.get("decisions", ()) if isinstance(w, str) and w.startswith("player:")]
        x = f" with X = {step['x']}" if step.get("x") is not None else ""
        kick = " with kicker paid" if step.get("kicked") else ""
        tgt = f" targeting {', '.join(targets)}" if targets else ""
        return f"Seat {step.get('controller', 0)} casts {L(key)}{x}{kick}{tgt}; it resolves.{choices}"
    if op == "activate":
        handle = runner.handles[step["key"]]
        ident = runner.world.cards[handle].identity
        result = supply.pool.results.get(ident.oracle_id)
        line = ability_line(result.card if result else None, oracle.text(ident.oracle_id), int(step.get("idx", 0)))
        if line is None:
            raise Unrenderable("ability index not mappable to an oracle line")
        targets = [L(k) for k in step.get("targets", ())]
        tgt = f" targeting {', '.join(targets)}" if targets else ""
        return f'Seat {step.get("seat", 0)} activates {L(step["key"])}\'s ability "{text(line)}"{tgt}; it resolves.{choices}'
    if op == "combat":
        if any(step.get(k) for k in ("order", "trample", "policy")):
            raise Unrenderable("combat damage-order/trample lanes")
        if step.get("decisions"):
            _words(step["decisions"], labels)
        attackers = [L(k) for k, go in step.get("attack", {}).items() if go]
        blocks = [f"{L(b)} blocks {L(a)}" for b, a in step.get("block", {}).items() if a is not None]
        mays = [f"{L(k)}: {'yes' if go else 'no'}" for k, go in step.get("may", {}).items()]
        out = f"Combat on seat {step.get('seat', 0)}'s turn. Attacking: {', '.join(attackers) or 'nobody'} (no other creature attacks)."
        out += f" Blocks: {'; '.join(blocks) or 'none'} (no other creature blocks)."
        if mays:
            out += f" Optional effects: {'; '.join(mays)}."
        if step.get("decisions"):
            out += " Other choices, in the order asked: " + ", ".join(_words(step["decisions"], labels)) + "."
        return out + " Combat damage is dealt and the combat phase ends."
    raise Unrenderable(f"unknown op {op}")


QUESTION = {
    "life": "life total of seat {k}",
    "hand": "number of cards in seat {k}'s hand",
    "mana_pool": "mana pool of seat {k}, as {{color: amount}} without zeros",
    "zone": "zone of {k} (battlefield, hand, graveyard, exile, library or stack)",
    "counters": "counters on {k}, as {{kind: number}} ({{}} if none)",
    "tapped": "whether {k} is tapped (true or false)",
    "power": "current power of {k}",
    "toughness": "current toughness of {k}",
    "tokens": "number of tokens named {k} on the battlefield",
    "battlefield_pt": "current [power, toughness] of the one permanent named {k} on the battlefield",
}


def build_items(
    *, masked: bool = False, salt: str = "public-dev", pack_dir: Path = PACK_DIR
) -> tuple[list[Item], Coverage]:
    from tools.run_scenarios import ScenarioRunner, run_pack  # tools/ is a repo package

    oracle = OracleIndex.for_sets("M21", "ZNR")
    masker = NameMasker(oracle.names, salt, keep=oracle.token_names) if masked else None
    name = masker.label if masker else (lambda n: n)
    text = masker.mask if masker else (lambda t: t)
    items, cov = [], Coverage()
    for path in sorted(pack_dir.glob("*.json")):
        cov.packs += 1
        pack = json.loads(path.read_text())
        set_code = str(pack.get("set", "M21"))
        supply = get_supply("all", set_code)
        if run_pack(path, supply):
            cov.excluded["engine disagrees with the pack"] += 1
            continue
        labels = {c["key"]: f"obj{i + 1}" for i, c in enumerate(pack["cards"])}
        gold = _gold(pack, labels)
        if not gold:
            cov.excluded["no scorable lane"] += 1
            continue
        if "ceased" in gold.get("zone", {}).values():
            # 2026-10-30 (vfix2's merge of cards/integration): a token that left the battlefield
            # ceases to exist (CR 704.5d, V35). The zone question offers no answer for that, so
            # the pack is a named exclusion rather than an unanswerable item.
            cov.excluded["a token ceases to exist"] += 1
            continue
        try:
            runner = ScenarioRunner(pack, supply)
            initial_text = _render_state(runner, labels, name, text, oracle)
            steps = [_render_step(s, labels, runner, supply, oracle, text) for s in pack.get("steps", ())]
        except Unrenderable as why:
            cov.excluded[str(why)] += 1
            continue
        initial = read_state(runner, labels, gold)
        replay = ScenarioRunner(pack, supply)
        for step in pack.get("steps", ()):
            replay.run_step(step)
        final = read_state(replay, labels, gold)
        if final != gold:
            cov.reader_mismatch.append(path.stem)
            continue
        questions = []
        for lane, keys in gold.items():
            if lane == "damage":
                questions.append('- "damage": damage marked on each object, as {object: amount}, listing only damaged objects')
                continue
            for k in keys:
                questions.append(f'- "{lane}" / "{name(k) if lane in ("tokens", "battlefield_pt") else k}": ' + QUESTION[lane].format(k=name(k) if lane in ("tokens", "battlefield_pt") else k))
        prompt = "\n".join([
            "Magic: The Gathering rules question. The engine notes in the primer apply.",
            "Initial state:", initial_text, "",
            "Steps, in order:", *(f"{i + 1}. {s}" for i, s in enumerate(steps)), "",
            "After all steps, report:", *questions, "",
            'Answer with one JSON object of the form {"lane": {"key": value}}, using the lane and key names above.',
        ])
        shown = {lane: ({name(k): v for k, v in keys.items()} if lane in ("tokens", "battlefield_pt") else keys) for lane, keys in gold.items()}
        shown_initial = {lane: ({name(k): v for k, v in keys.items()} if lane in ("tokens", "battlefield_pt") else keys) for lane, keys in initial.items()}
        items.append(Item(path.stem, set_code, "masked" if masked else "real", prompt, shown, shown_initial))
        cov.items += 1
    return items, cov


# -------------------------------------------------------------------- score


def _norm(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in value.items() if v not in (0, None) or not isinstance(v, int)}
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, list | tuple):
        return [_norm(v) for v in value]
    return value


def score(item: Item, answer: dict[str, Any]) -> dict[str, Any]:
    """Per-key exact match after normalisation; all-keys accuracy and delta-only accuracy."""
    hits = total = d_hits = d_total = 0
    for lane, keys in item.gold.items():
        got_lane = answer.get(lane, {}) if isinstance(answer, dict) else {}
        if lane == "damage":
            pairs = [("*", keys, got_lane, item.initial.get(lane, {}))]
        else:
            pairs = [(k, v, got_lane.get(k) if isinstance(got_lane, dict) else None, item.initial.get(lane, {}).get(k)) for k, v in keys.items()]
        for _, want, got, before in pairs:
            ok = _norm(got) == _norm(want)
            total += 1
            hits += ok
            if _norm(want) != _norm(before):
                d_total += 1
                d_hits += ok
    return {"all_keys": hits / total if total else 0.0, "delta": d_hits / d_total if d_total else None,
            "keys": total, "delta_keys": d_total}


class NullAnswerer:
    """Predicts that nothing changes: the §17 floor for track R."""

    def answer(self, item: Item) -> dict[str, Any]:
        return item.initial


class OracleAnswerer:
    """Returns the engine's answer: the instrument's own sanity check (must score 1.0)."""

    def answer(self, item: Item) -> dict[str, Any]:
        return item.gold
