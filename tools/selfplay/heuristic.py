"""A rule-based player for the bench protocol: the fixed anchor opponent and the BC teacher.

It is deliberately simple and deterministic (no RNG), and it reads only what its seat may know:
the public board, its own hand, and the cards an ask offers. Its rules, in order of the asks:

* act (in both main phases): play a land, cast the highest mana value spell (kicked when
  offered, the largest X, never X = 0; the menu pays from lands and mana rocks), activate a
  planeswalker, otherwise pass. A harmful non-damage spell is not cast while the opponent
  controls no creature. A creature's or a Treasure's mana is used only when its mana makes a
  spell in hand castable, never a mana-cost filter (Prismite). Other activated abilities are
  never used. In the first main phase, when the spell it would cast reads whether it attacked
  this turn (raid) and it has a creature that can attack, it passes instead: that spell and the
  rest of its plays come in the second main phase, after the attack.
* target: a harmful source (damage, destroy, exile, tap, -N/-N, ...) aims at the opponent's best
  creature, then the opponent; a helpful one at its own best creature, then itself.
* attack: attack unless an untapped opposing creature that can block it would kill it and
  survive.
* block: a free kill, else chump the biggest attacker when the attack is lethal, else a block
  it survives, else no block.
* scry/discard/sacrifice/mana/one_of: small land-count and mana-value rules (see the methods).
* name: the opponent's most expensive card in a public zone (battlefield, graveyard, exile).
* mulligan (CR 103.5): keep a hand of five cards or fewer, and a bigger one that holds at least
  two lands and at least two other cards; otherwise mulligan. The card a mulligan puts on the
  bottom: a land while the hand holds more lands than other cards (a copy of the land it holds
  most of), otherwise its highest mana value other card.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from MTG_bot.core.ability_tree import (
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostSacrifice,
    DeclareAttackersEvent,
    FAtom,
    FAtomPred,
    SpellAbility,
    is_mana_ability,
    to_dict,
    walk,
)
from MTG_bot.core.executor.legality import (
    SECOND_MAIN,
    ManaTap,
    _cost_has_x,
    _mana_atom_output,
    _with_trial_mana,
    ctx_for,
    legal_attackers,
    plan_mana_taps,
    spell_castable,
    spell_record,
)
from MTG_bot.core.executor.query import spell_target_slots
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, ZONE_HAND
from tools.selfplay.features import _handle, ir_tokens

HARM_VERBS = {
    "Verb.DEAL_DAMAGE", "Verb.DESTROY", "Verb.EXILE", "Verb.TAP", "Verb.MILL", "Verb.LOSE_LIFE",
    "Verb.COUNTER_SPELL", "Verb.SACRIFICE", "Verb.DISCARD", "Verb.GAIN_CONTROL", "Verb.FIGHT",
    "Verb.MOVE_ZONE", "Verb.REMOVE_COUNTER",
}
_TOKENS_CACHE: dict[str, frozenset] = {}
_RAID_CACHE: dict[str, bool] = {}


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
    # -N/-N: the compiler writes PtDelta(direction=DECREASE) with a positive magnitude now
    return "Verb.MODIFY_PT" in toks and ("num:neg" in toks or "PtDirection.DECREASE" in toks)


def reads_raid(executor: Any, handle: Handle) -> bool:
    """The card's text reads whether its controller attacked this turn (raid: "if you attacked
    this turn", compiled as EVENT_THIS_TURN over a DeclareAttackersEvent, conditions.py)."""
    oid = executor.world.cards[handle].identity.oracle_id
    hit = _RAID_CACHE.get(oid)
    if hit is None:
        rec = executor.binder.records.get(oid)
        hit = _RAID_CACHE[oid] = rec is not None and any(
            isinstance(n, FAtom) and n.pred is FAtomPred.EVENT_THIS_TURN
            and isinstance(n.event, DeclareAttackersEvent) for n in walk(rec))
    return hit


def deals_damage(executor: Any, handle: Handle | None) -> bool:
    if handle is None or handle not in executor.world.cards:
        return False
    toks = _record_tokens(executor, executor.world.cards[handle].identity.oracle_id)
    return "Verb.DEAL_DAMAGE" in toks or "Verb.LOSE_LIFE" in toks


def cast_token(token: str) -> tuple[Handle | None, bool, int]:
    """``cast:<card>[:k][:x<N>]`` (the router's cast row) -> (card, kicked, X)."""
    rest, x = token[5:], 0
    head, sep, tail = rest.rpartition(":x")
    if sep and tail.isdigit():
        rest, x = head, int(tail)
    kicked = rest.endswith(":k")
    return _handle(rest[:-2] if kicked else rest), kicked, x


class HeuristicAgent:
    name = "heuristic"
    colour: str | None = None  # the colour a mana row was chosen for (_mana_row -> _mana)

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
        lands = [i for i, t in enumerate(tokens) if t.startswith("land:")]
        if lands:
            return lands[0]
        best, best_key = None, None
        for i, t in enumerate(tokens):
            if not t.startswith("cast:"):
                continue
            h, kicked, x = cast_token(t)
            if h is None or h not in self.world.cards:
                continue
            if (x == 0 and self._has_x(h)) or self._pointless(h):
                continue  # X = 0 does nothing (Volcanic Geyser deals 0, Wildwood Scourge dies)
            key = ((self.world.cards[h].identity.cmc or 0) + x, kicked, -i)
            if best_key is None or key > best_key:
                best, best_key = i, key
        if best is not None:
            h = cast_token(tokens[best])[0]
            if (self.ex.phase != SECOND_MAIN and "PASS" in tokens and reads_raid(self.ex, h)
                    and legal_attackers(self.ex, self.me)):
                return tokens.index("PASS")  # cast it after the attack (CR 505.1)
            return best
        mana = self._mana_row(tokens)
        if mana is not None:
            return mana
        for i, t in enumerate(tokens):
            if t.startswith("act:"):
                h = _handle(":".join(t.split(":")[1:3]))
                if h is not None and h in self.world.cards and self._is(h, "Planeswalker"):
                    return i
        return tokens.index("PASS") if "PASS" in tokens else None

    def _mana_row(self, tokens: list[str]) -> int | None:
        """A creature's or a sacrifice's mana row (untapping creatures first), only when its mana
        makes a spell in hand one the menu would offer and this player would cast. A mana-cost
        filter (Prismite's {2}: add one) never adds mana, so it is never used. The colour that
        does it answers the mana ask the activation makes (``_mana``)."""
        rows = []
        for i, t in enumerate(tokens):
            parts = t.split(":")
            if parts[0] != "act" or len(parts) != 4:
                continue
            h, idx = _handle(f"{parts[1]}:{parts[2]}"), int(parts[3])
            record = spell_record(self.ex, h) if h is not None and idx >= 0 else None
            if record is None or not is_mana_ability(record.abilities[idx]):
                continue
            cost = record.abilities[idx].cost.parts
            if not any(isinstance(p, (CostManaColor, CostManaGeneric, CostManaHybrid)) for p in cost):
                rows.append((any(isinstance(p, CostSacrifice) for p in cost), i, h, idx))
        if not rows:
            return None
        offered = {cast_token(t)[0] for t in tokens if t.startswith("cast:")}
        short = [h for h in self._hand()
                 if h not in offered and not self._is(h, "Land") and not self._pointless(h)]
        for _sacrifice, i, h, idx in sorted(rows):
            ability = spell_record(self.ex, h).abilities[idx]
            for spell in short:
                colour = self._enabling_colour(h, idx, ability, spell)
                if colour is not None:
                    self.colour = colour
                    return i
        return None

    def _has_x(self, spell: Handle) -> bool:
        record = spell_record(self.ex, spell)
        return record is not None and record.mana_cost is not None and _cost_has_x(record.mana_cost)

    def _pointless(self, spell: Handle) -> bool:
        """Removal with nothing to remove: a harmful non-creature, non-planeswalker spell that deals
        no damage, while the opponent controls no creature."""
        return (not self._is(spell, "Creature") and not self._is(spell, "Planeswalker")
                and is_harmful(self.ex, spell) and not deals_damage(self.ex, spell)
                and not any(self._is(h, "Creature") for h in self._controlled(self.opp)))

    def _enabling_colour(self, source: Handle, idx: int, ability: Any, spell: Handle) -> str | None:
        """The colour of this ability's mana (any colour for a Treasure) with which the menu would
        offer ``spell`` (X at least 1): its total cost payable from the pool and the free sources,
        a target's cost increase included, one target slot at most with a payable candidate. Asked
        of the engine's own planner with the mana added on trial and taken back."""
        got = _mana_atom_output(ability.effect, ctx_for(self.ex, source=source, controller=self.me))
        record = spell_record(self.ex, spell)
        node = next((a for a in record.abilities if isinstance(a, SpellAbility)), None) if record else None
        if got is None or node is None:
            return None
        color, n = got
        x = 1 if self._has_x(spell) else None
        policy = self.ex.layers.this_mana_filter(source)  # Vodalian Arcanist: instants and sorceries
        tags = (policy,) if policy is not None else ()

        def pays(targets: tuple[Handle, ...]) -> bool:
            return plan_mana_taps(
                self.ex, self.me, lambda: spell_castable(self.ex, self.me, spell, x=x, targets=targets)[0]
            ) is not None

        def offered() -> str | None:
            if not pays(()):
                return "short"
            slots = spell_target_slots(self.ex, node, spell_handle=spell, seat=self.me, pay=pays)
            return None if len(slots) <= 1 and all(s.min_count <= len(s.candidates) for s in slots) else "no"

        for c in (color,) if color else "WUBRG":
            if _with_trial_mana(self.ex, self.me, [ManaTap(source, idx, (), (c, n, tags))], offered) is None:
                return c
        return None

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
        colour, self.colour = self.colour, None  # the colour _mana_row chose this mana for
        if colour in tokens:
            return tokens.index(colour)
        need = {c: 0 for c in "WUBRG"}
        for h in self._hand():
            record = spell_record(self.ex, h)
            for part in record.mana_cost.parts if record is not None and record.mana_cost else ():
                if isinstance(part, CostManaColor) and part.color in need:
                    need[part.color] += getattr(part.amount, "value", 1)
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

    def _mulligan(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        hand = self._hand()
        lands = sum(1 for h in hand if self._is(h, "Land"))
        keep = len(hand) <= 5 or (lands >= 2 and len(hand) - lands >= 2)
        return tokens.index("keep" if keep else "mulligan")

    def _mulligan_bottom(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        cards = [(i, _handle(t)) for i, t in enumerate(tokens)]
        cards = [(i, h) for i, h in cards if h is not None and h in self.world.cards]
        lands = [(i, h) for i, h in cards if self._is(h, "Land")]
        others = [(i, h) for i, h in cards if not self._is(h, "Land")]
        if len(lands) > len(others):
            copies = Counter(self.world.cards[h].identity.name for _, h in lands)
            return max(lands, key=lambda x: (copies[self.world.cards[x[1]].identity.name], -x[0]))[0]
        if not others:
            return None
        return max(others, key=lambda x: (float(self.world.cards[x[1]].identity.cmc or 0), -x[0]))[0]

    def _name(self, ask: Any, tokens: list[str], obs: Any) -> int | None:
        seen: dict[str, float] = {}
        for kind in (ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_EXILE):
            zone = self.world.players[self.opp].zones.get(kind)
            for h in zone.entries if zone else ():
                ident = self.world.cards[h].identity
                if not ident.is_token:
                    seen[ident.name] = float(ident.cmc or 0)
        names = set(tokens)
        best = max((n for n in seen if n in names), key=lambda n: (seen[n], n), default=None)
        return tokens.index(best) if best is not None else None
