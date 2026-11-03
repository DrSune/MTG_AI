"""A rule-based player for the bench protocol: the fixed anchor opponent and the BC teacher.

It is deliberately simple and deterministic (no RNG), and it reads only what its seat may know:
the public board, its own hand, and the cards an ask offers. Its rules, in order of the asks:

* act: tap all mana first (pools never empty, so it is free), play a land, cast the highest
  mana value spell (kicked when offered), activate a planeswalker, otherwise pass. A harmful
  non-damage spell is not cast while the opponent controls no creature. Other activated
  abilities are never used.
* target: a harmful source (damage, destroy, exile, tap, -N/-N, ...) aims at the opponent's best
  creature, then the opponent; a helpful one at its own best creature, then itself.
* attack: attack unless an untapped opposing creature that can block it would kill it and
  survive.
* block: a free kill, else chump the biggest attacker when the attack is lethal, else a block
  it survives, else no block.
* scry/discard/sacrifice/mana/one_of: small land-count and mana-value rules (see the methods).
"""

from __future__ import annotations

from typing import Any

from MTG_bot.core.ability_tree import to_dict
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND
from tools.selfplay.features import _handle, ir_tokens

HARM_VERBS = {
    "Verb.DEAL_DAMAGE", "Verb.DESTROY", "Verb.EXILE", "Verb.TAP", "Verb.MILL", "Verb.LOSE_LIFE",
    "Verb.COUNTER_SPELL", "Verb.SACRIFICE", "Verb.DISCARD", "Verb.GAIN_CONTROL", "Verb.FIGHT",
    "Verb.MOVE_ZONE", "Verb.REMOVE_COUNTER",
}
_TOKENS_CACHE: dict[str, frozenset] = {}


def _record_tokens(executor: Any, oracle_id: str) -> frozenset:
    hit = _TOKENS_CACHE.get(oracle_id)
    if hit is None:
        rec = executor.binder.records.get(oracle_id)
        if rec is None:
            hit = frozenset()
        else:
            hit = frozenset(ir_tokens({"abilities": [to_dict(a) for a in rec.abilities]}))
        _TOKENS_CACHE[oracle_id] = hit
    return hit


def is_harmful(executor: Any, handle: Handle | None) -> bool:
    if handle is None or handle not in executor.world.cards:
        return True
    toks = _record_tokens(executor, executor.world.cards[handle].identity.oracle_id)
    if toks & HARM_VERBS:
        return True
    return "Verb.MODIFY_PT" in toks and "num:neg" in toks


def deals_damage(executor: Any, handle: Handle | None) -> bool:
    if handle is None or handle not in executor.world.cards:
        return False
    toks = _record_tokens(executor, executor.world.cards[handle].identity.oracle_id)
    return "Verb.DEAL_DAMAGE" in toks or "Verb.LOSE_LIFE" in toks


class HeuristicAgent:
    name = "heuristic"

    def decide(self, ask: Any, obs: Any) -> int:
        n = len(ask.options)
        if n == 1:
            return 0
        self.ex = obs.executor
        self.world = self.ex.world
        self.me = self.world.player_order[ask.seat]
        self.opp = self.world.player_order[1 - ask.seat]
        tokens = [o.token for o in ask.options]
        method = getattr(self, f"_{ask.kind}", None)
        if method is not None:
            idx = method(ask, tokens, obs)
            if idx is not None:
                return idx
        return self._first_non_refuse(ask)

    # ------------------------------------------------------------------ helpers

    def _first_non_refuse(self, ask: Any) -> int:
        for i in range(len(ask.options)):
            if i != ask.refuse:
                return i
        return 0

    def _pt(self, h: Handle) -> tuple[int, int]:
        card = self.world.cards[h]
        p, t = self.ex.ledger.effective_pt(card.identity, h, card.counters)
        return int(p or 0), int(t or 0)

    def _kw(self, h: Handle) -> tuple[str, ...]:
        return self.ex.layers.keywords(h)

    def _bf(self, player: Handle) -> list[Handle]:
        zone = self.world.players[player].zones.get(ZONE_BATTLEFIELD)
        return list(zone.entries) if zone else []

    def _controlled(self, player: Handle) -> list[Handle]:
        overlay = self.ex.control_overlay
        out = []
        for p in (self.me, self.opp):
            for h in self._bf(p):
                if overlay.get(h, p) == player:
                    out.append(h)
        return out

    def _is(self, h: Handle, kind: str) -> bool:
        return kind in (self.world.cards[h].identity.type_line or "")

    def _value(self, h: Handle) -> float:
        card = self.world.cards[h]
        p, t = self._pt(h) if self._is(h, "Creature") else (0, 0)
        return 2 * p + t + float(card.identity.cmc or 0)

    def _lands(self, player: Handle) -> int:
        return sum(1 for h in self._controlled(player) if self._is(h, "Land"))

    def _hand(self) -> list[Handle]:
        zone = self.world.players[self.me].zones.get(ZONE_HAND)
        return list(zone.entries) if zone else []

    # -------------------------------------------------------------------- asks

    def _act(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        if "TAP_ALL_MANA" in tokens:
            return tokens.index("TAP_ALL_MANA")
        lands = [i for i, t in enumerate(tokens) if t.startswith("land:")]
        if lands:
            return lands[0]
        opp_creatures = any(self._is(h, "Creature") for h in self._controlled(self.opp))
        best, best_key = None, None
        for i, t in enumerate(tokens):
            if not t.startswith("cast:"):
                continue
            kicked = t.endswith(":k")
            h = _handle(t[5:-2] if kicked else t[5:])
            if h is None or h not in self.world.cards:
                continue
            ident = self.world.cards[h].identity
            if not self._is(h, "Creature") and is_harmful(self.ex, h) and not opp_creatures \
                    and not deals_damage(self.ex, h) and not self._is(h, "Planeswalker"):
                continue  # removal with nothing to remove
            key = (ident.cmc or 0, kicked, -i)
            if best_key is None or key > best_key:
                best, best_key = i, key
        if best is not None:
            return best
        for i, t in enumerate(tokens):
            if t.startswith("act:"):
                h = _handle(":".join(t.split(":")[1:3]))
                if h is not None and h in self.world.cards and self._is(h, "Planeswalker"):
                    return i
        return tokens.index("PASS") if "PASS" in tokens else None

    def _target(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        src = None
        for part in (ask.site,):
            hs = [p for p in part.split(":")]
            for j in range(len(hs) - 1):
                if hs[j] == "card" and hs[j + 1].isdigit():
                    src = Handle("card", int(hs[j + 1]))
                    break
        harmful = is_harmful(self.ex, src)
        best, best_score = None, None
        for i, t in enumerate(tokens):
            if t == "DONE":
                continue
            h = _handle(t)
            if h is None:
                continue
            score = self._target_score(h, harmful)
            if best_score is None or score > best_score:
                best, best_score = i, score
        if "DONE" in tokens and (best_score is None or best_score < 0):
            return tokens.index("DONE")
        return best

    def _target_score(self, h: Handle, harmful: bool) -> float:
        if h.namespace == "player":
            mine = h == self.me
            if harmful:
                return -20.0 if mine else 5.0 + (10.0 if self.world.players[h].life <= 5 else 0)
            return 6.0 if mine else -20.0
        if h not in self.world.cards:
            return -50.0
        mine = self.ex.controller_of(h) == self.me
        on_bf = self.world.zone_of(h).kind == ZONE_BATTLEFIELD
        v = self._value(h) if on_bf else float(self.world.cards[h].identity.cmc or 0)
        creature_bonus = 10.0 if self._is(h, "Creature") else 3.0
        if harmful:
            return (creature_bonus + v) if not mine else -(10.0 + v)
        return (creature_bonus + v) if mine else -(10.0 + v)

    def _attack(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        if "ATTACK" not in tokens or "DECLINE" not in tokens:
            return None
        h = _handle(":".join(ask.site.split(":")[1:3]))
        if h is None or h not in self.world.cards:
            return tokens.index("ATTACK")
        p, t = self._pt(h)
        if p <= 0:
            return tokens.index("DECLINE")
        flying = "FLYING" in self._kw(h)
        for b in self._controlled(self.opp):
            if not self._is(b, "Creature") or self.world.cards[b].tapped:
                continue
            bk = self._kw(b)
            if flying and "FLYING" not in bk and "REACH" not in bk:
                continue
            bp, bt = self._pt(b)
            kills = bp >= t or ("DEATHTOUCH" in bk and bp > 0)
            survives = bt > p and not ("DEATHTOUCH" in self._kw(h) and p > 0)
            if kills and survives:
                return tokens.index("DECLINE")
        return tokens.index("ATTACK")

    def _block(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        if "NONE" not in tokens:
            return None
        me_h = _handle(":".join(ask.site.split(":")[1:3]))
        if me_h is None or me_h not in self.world.cards:
            return tokens.index("NONE")
        p, t = self._pt(me_h)
        my_dt = "DEATHTOUCH" in self._kw(me_h)
        life = self.world.players[self.me].life
        atk = []
        for i, tok in enumerate(tokens):
            a = _handle(tok)
            if a is not None and a in self.world.cards:
                ap, at = self._pt(a)
                adt = "DEATHTOUCH" in self._kw(a)
                atk.append((i, a, ap, at, adt))
        incoming = sum(ap for _, a, ap, _, _ in atk) + sum(
            self._pt(a)[0] for a in self.ex.attackers if all(a != x[1] for x in atk))
        lethal = incoming >= life
        free = [x for x in atk if (t > x[2] and not x[4]) and (p >= x[3] or (my_dt and p > 0))]
        if free:
            return max(free, key=lambda x: (x[2] + x[3], -x[0]))[0]
        if lethal and atk:
            return max(atk, key=lambda x: (x[2], -x[0]))[0]
        survive = [x for x in atk if t > x[2] and not x[4]]
        if survive:
            return max(survive, key=lambda x: (x[2], -x[0]))[0]
        return tokens.index("NONE")

    def _may(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        return tokens.index("fire") if "fire" in tokens else None

    def _scry(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        card = getattr(getattr(obs, "ctx", None), "revealed", None)
        if card is None or card not in self.world.cards or "top" not in tokens:
            return None
        lands = self._lands(self.me)
        is_land = self._is(card, "Land")
        hand_lands = sum(1 for h in self._hand() if self._is(h, "Land"))
        if is_land and lands + hand_lands >= 6:
            return tokens.index("bottom")
        if not is_land and lands + hand_lands <= 2:
            return tokens.index("bottom")
        return tokens.index("top")

    def _mana(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        need = {c: 0 for c in "WUBRG"}
        for h in self._hand():
            cost = self.world.cards[h].identity.mana_cost or ""
            for c in need:
                need[c] += cost.count(c)
        best = max((c for c in "WUBRG" if c in tokens), key=lambda c: need[c], default=None)
        return tokens.index(best) if best is not None else None

    def _discard(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        cards = [(i, _handle(t)) for i, t in enumerate(tokens)]
        cards = [(i, h) for i, h in cards if h is not None and h in self.world.cards]
        if not cards:
            return None
        if self._lands(self.me) >= 5:
            lands = [i for i, h in cards if self._is(h, "Land")]
            if lands:
                return lands[0]
        return max(cards, key=lambda x: (float(self.world.cards[x[1]].identity.cmc or 0), -x[0]))[0]

    def _sacrifice(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        cards = [(i, _handle(t)) for i, t in enumerate(tokens)]
        cards = [(i, h) for i, h in cards if h is not None and h in self.world.cards]
        if not cards:
            return None
        return min(cards, key=lambda x: (not self.world.cards[x[1]].identity.is_token,
                                         self._value(x[1]), x[0]))[0]

    def _one_of(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        cards = [(i, _handle(t)) for i, t in enumerate(tokens)]
        cards = [(i, h) for i, h in cards if h is not None and h in self.world.cards]
        if not cards:
            return None
        return max(cards, key=lambda x: (float(self.world.cards[x[1]].identity.cmc or 0), -x[0]))[0]

    def _trample(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        nums = [(i, int(t)) for i, t in enumerate(tokens) if t.lstrip("-").isdigit()]
        return max(nums, key=lambda x: x[1])[0] if nums else None

    def _policy(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        return tokens.index("UNBLOCKED") if "UNBLOCKED" in tokens else None

    def _pay(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        return tokens.index("PAY") if "PAY" in tokens else None
