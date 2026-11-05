"""What one seat may know at one decision, encoded as small numpy arrays.

The visibility rule is the bench's (``MTG_bot/bench/view.py``): the decider's own hand, every
public zone (battlefields, graveyards, exile, command, stack), counts of hidden zones, plus the
cards the engine offers to the decider or shows it (a scried card, a searched library). Engine
handles never reach the network; they are only used to point an option at an entity.

One decision encodes to (shapes; E = card entities, K = options):

* ``cards_i``  int16  [E, 5]   card vocab id, zone, controller, owner, attached-to entity
* ``cards_f``  float32[E, CF]  flags, type line, colours, keywords, P/T, damage, counters, cost
* ``players_f``float32[2, PF]  me then the opponent: life, zone counts, mana pool, board counts
* ``glob_f``   float32[GF]     turn, whose turn, stack size, ask details
* ``ask_i``    int32  [1]      ask kind
* ``opts_i``   int32  [K, 4]   option type, entity ref, second entity ref, ability index
* ``opts_f``   float32[K, 2]   number value, kicked

Entity refs index the entity list ``[me, opponent, cards...]`` plus one (0 = no entity).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from MTG_bot.core.ability_tree import Phase, to_dict
from MTG_bot.core.executor.events import KIND_TURN_PHASE, KIND_ZONE_CHANGE
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_COMMAND,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

PAD, UNK = 0, 1

ASK_KINDS = (
    "pad", "act", "attack", "block", "target", "choose", "one_of", "may", "scry", "mana",
    "order", "trample", "policy", "cw", "counter", "pay", "sacrifice", "discard", "tap", "name",
    "other",
)
ASK_INDEX = {k: i for i, k in enumerate(ASK_KINDS)}

ZONES = ("pad", ZONE_HAND, ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_EXILE, "stack", ZONE_COMMAND,
         ZONE_LIBRARY)
ZONE_INDEX = {z: i for i, z in enumerate(ZONES)}

KEYWORDS = (
    "FLYING", "VIGILANCE", "FLASH", "REACH", "LIFELINK", "TRAMPLE", "PROWESS", "HEXPROOF",
    "DEFENDER", "PROTECTION", "DOUBLE_STRIKE", "HASTE", "INDESTRUCTIBLE", "DEATHTOUCH",
    "FIRST_STRIKE", "MENACE", "ENCHANT", "FIGHT", "TREASURE", "WARD",
)
KW_INDEX = {k: i for i, k in enumerate(KEYWORDS)}
TYPES = ("Land", "Creature", "Artifact", "Enchantment", "Planeswalker", "Instant", "Sorcery",
         "Legendary")
COLORS = ("W", "U", "B", "R", "G")

# cards_f layout
F_TAPPED, F_SICK, F_ATTACKING, F_BLOCKING, F_BLOCKED, F_DECL_ATTACK, F_DECL_BLOCK = range(7)
F_TOKEN, F_ASK_SOURCE, F_OFFERED, F_REVEALED, F_ATTACHED, F_HAS_PT = range(7, 13)
F_TYPE0 = 13
F_COLOR0 = F_TYPE0 + len(TYPES)
F_KW0 = F_COLOR0 + len(COLORS)
F_KW_OTHER = F_KW0 + len(KEYWORDS)
F_POWER, F_TOUGH, F_DAMAGE, F_P1, F_M1, F_LOYALTY, F_COUNTERS, F_CMC, F_DECL_BLOCKERS = range(
    F_KW_OTHER + 1, F_KW_OTHER + 10
)
CF = F_DECL_BLOCKERS + 1
PF = 16
GF = 8

OPTION_TYPES = (
    "pad", "PASS", "TAP_ALL_MANA", "land", "cast", "cast_kicked", "activate", "ATTACK",
    "DECLINE", "NONE", "card", "player", "DONE", "fire", "skip", "top", "bottom",
    "W", "U", "B", "R", "G", "C", "number", "cast_at", "PAY", "AS_BLOCKED", "UNBLOCKED",
    "other",
)
OPT_INDEX = {k: i for i, k in enumerate(OPTION_TYPES)}

#: The option menus are capped at this size. A larger ask is answered by the fallback agent and
#: never trained on (counted as ``overflow``). A capacity limit, not a strategy limit.
MAX_OPTIONS = 64
#: Graveyard and exile keep their newest cards when the entity list would exceed MAX_CARDS.
MAX_CARDS = 112
GRAVE_KEEP = 16
EXILE_KEEP = 10

_CARD_RE = re.compile(r"card:(\d+)")


# ------------------------------------------------------------------------------ card table


def _bucket(value: Any) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "num:?"
    return f"num:{n}" if 0 <= n <= 5 else ("num:6+" if n > 5 else "num:neg")


def ir_tokens(node: Any) -> list[str]:
    """Pre-order tokens of a ``to_dict`` tree: tags, enum values, roles, strings, bucketed
    numbers. A card's own name never appears. (Same scheme as ``tools/k1/train.py``.)"""
    out: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            tag = value.get("tag")
            if "name" in value and len(value) == 2 and tag:
                out.append(f"{tag}.{value['name']}")
                return
            if tag == "QConst":
                out.append(_bucket(value.get("value")))
                return
            if tag:
                out.append(tag)
            for key, child in value.items():
                if key == "tag" or child in (None, [], {}, ""):
                    continue
                if key == "pairs":
                    for role, item in child:
                        out.append(f"role:{role}")
                        visit(item)
                    continue
                if key in ("name", "oracle_id", "type_line"):
                    continue
                out.append(f"@{key}")
                visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, bool):
            out.append(f"bool:{value}")
        elif isinstance(value, int):
            out.append(_bucket(value))
        elif isinstance(value, str):
            out.append(f"str:{value}")

    visit(node)
    return out


@dataclass
class CardTable:
    """Card vocabulary (oracle id -> row) and each row's component tokens.

    Row 0 is padding and row 1 the unknown card. ``ir`` holds each row's component-token ids
    (truncated to ``max_ir``); the network embeds a card as name embedding + component bag, so
    a card outside the vocabulary still has its components when the table is extended.
    """

    oracle_ids: list[str]
    names: list[str]
    ir_vocab: list[str]
    ir: list[list[int]]
    max_ir: int = 128
    index: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.index = {oid: i for i, oid in enumerate(self.oracle_ids)}

    @classmethod
    def from_records(cls, records: dict[str, Any], max_ir: int = 128) -> CardTable:
        oids = ["<pad>", "<unk>"] + sorted(records)
        names = ["<pad>", "<unk>"] + [records[o].name for o in oids[2:]]
        token_lists = [[], []]
        for oid in oids[2:]:
            rec = records[oid]
            tree = {"abilities": [to_dict(a) for a in rec.abilities],
                    "keywords": [to_dict(k) for k in rec.keywords]}
            face = [f"type:{t}" for t in rec.types] + [f"sub:{t}" for t in rec.subtypes]
            face += [f"mv:{_bucket(rec.mana_value)}"]
            token_lists.append(face + ir_tokens(tree))
        vocab = ["<pad>"] + sorted({t for toks in token_lists for t in toks})
        vi = {t: i for i, t in enumerate(vocab)}
        ir = [[vi[t] for t in toks][:max_ir] for toks in token_lists]
        return cls(oids, names, vocab, ir, max_ir)

    def row(self, oracle_id: str) -> int:
        return self.index.get(oracle_id, UNK)

    def ir_array(self) -> np.ndarray:
        out = np.zeros((len(self.ir), self.max_ir), dtype=np.int64)
        for i, ids in enumerate(self.ir):
            out[i, : len(ids)] = ids
        return out

    def to_json(self) -> dict[str, Any]:
        return {"oracle_ids": self.oracle_ids, "names": self.names, "ir_vocab": self.ir_vocab,
                "ir": self.ir, "max_ir": self.max_ir}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> CardTable:
        return cls(d["oracle_ids"], d["names"], d["ir_vocab"], d["ir"], d["max_ir"])


# ------------------------------------------------------------------------------ encoder


@dataclass
class AskContext:
    """Facts about the current decision that the game rig knows and the engine state does not
    show yet: the card being scried, attackers declared so far this combat, blocks so far."""

    revealed: Handle | None = None
    declared_attackers: frozenset = frozenset()
    declared_blocks: dict = field(default_factory=dict)  # blocker -> attacker
    picked: int = 0


_STATIC_CACHE: dict[int, tuple] = {}
# The cache holds each identity it has seen (so an id cannot be reused while cached, which keeps
# the `is` check sound), and the engine makes new identity objects every game: unbounded, it
# leaked ~31 identities per game, ~60 MB per PPO update across the workers, and a 22-hour run
# stopped on its memory floor (2026-11-05, KNOWLEDGE/2026-11-03/183 §32). Bounded: when full it
# is cleared and refilled (a refill costs microseconds per identity).
_CACHE_MAX = 8192


def _static(identity: Any) -> tuple:
    """Per-identity constants (type flags, colours, printed keywords, printed P/T, cost)."""
    key = id(identity)
    hit = _STATIC_CACHE.get(key)
    if hit is not None and hit[0] is identity:
        return hit[1]
    if len(_STATIC_CACHE) >= _CACHE_MAX:
        _STATIC_CACHE.clear()
    tl = identity.type_line or ""
    types = [1.0 if t in tl else 0.0 for t in TYPES]
    colors = [1.0 if c in (identity.colors or ()) else 0.0 for c in COLORS]
    p = _int_or_none(identity.power)
    t = _int_or_none(identity.toughness)
    val = (types, colors, tuple(identity.keywords or ()), p, t, float(identity.cmc or 0),
           identity.oracle_id, bool(identity.is_token), "Creature" in tl)
    _STATIC_CACHE[key] = (identity, val)
    return val


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class _OptCache(dict):
    """Parsed option tokens. Bounded like _STATIC_CACHE: tokens pair per-game handles
    ("cast:card:12@card:40"), so the set of distinct tokens keeps growing slowly."""

    def __missing__(self, tok: str) -> tuple:
        if len(self) >= 4 * _CACHE_MAX:
            self.clear()
        val = _parse_option(tok)
        self[tok] = val
        return val


def _parse_option(tok: str) -> tuple:
    """token -> (type, handle, second handle, ability index, number, kicked)."""
    if tok in OPT_INDEX and tok not in ("land", "cast", "activate", "card", "player", "number",
                                        "cast_at", "other", "pad", "cast_kicked"):
        return OPT_INDEX[tok], None, None, 0, 0.0, 0.0
    if tok.startswith("land:"):
        return OPT_INDEX["land"], _handle(tok[5:]), None, 0, 0.0, 0.0
    if tok.startswith("cast:"):
        rest = tok[5:]
        kicked = rest.endswith(":k")
        if kicked:
            rest = rest[:-2]
        return (OPT_INDEX["cast_kicked" if kicked else "cast"], _handle(rest), None, 0, 0.0,
                1.0 if kicked else 0.0)
    if tok.startswith("act:"):
        parts = tok.split(":")
        h = _handle(f"{parts[1]}:{parts[2]}") if len(parts) >= 3 else None
        idx = int(parts[3]) if len(parts) >= 4 and parts[3].lstrip("-").isdigit() else 0
        return OPT_INDEX["activate"], h, None, max(-4, min(idx, 15)), 0.0, 0.0
    if "@" in tok:
        a, _, b = tok.partition("@")
        return OPT_INDEX["cast_at"], _handle(a), _handle(b), 0, 0.0, 0.0
    if tok.startswith("card:"):
        return OPT_INDEX["card"], _handle(tok), None, 0, 0.0, 0.0
    if tok.startswith("player:"):
        return OPT_INDEX["player"], _handle(tok), None, 0, 0.0, 0.0
    if tok.lstrip("-").isdigit():
        return OPT_INDEX["number"], None, None, 0, float(int(tok)), 0.0
    return OPT_INDEX["other"], None, None, 0, 0.0, 0.0


def _handle(text: str) -> Handle | None:
    ns, _, idx = text.partition(":")
    if ns in ("card", "player", "emblem") and idx.isdigit():
        return Handle(ns, int(idx))
    return None


_OPTS = _OptCache()


def ask_kind_index(kind: str) -> int:
    return ASK_INDEX.get(kind, ASK_INDEX["other"])


def _sick_set(executor: Any) -> set:
    """Handles that entered the battlefield this turn (CR 302.6 read the way
    ``legality._controlled_since_turn_start`` reads it), in one journal pass."""
    events = executor.journal.events
    start = -1
    upkeep = Phase.UPKEEP.name
    for i in range(len(events) - 1, -1, -1):
        row = events[i]
        if row.kind == KIND_TURN_PHASE and row.data[0] == upkeep:
            start = i
            break
    out = set()
    for row in events[start + 1:]:
        if row.kind == KIND_ZONE_CHANGE and row.zone_move[1] == ZONE_BATTLEFIELD:
            out.add(row.subject)
    turn = executor.world.turn
    for h, gained in executor.control_gained_turn.items():
        if gained >= turn:
            out.add(h)
    return out


def encode(executor: Any, seat: int, ask: Any, table: CardTable,
           ctx: AskContext | None = None) -> dict[str, np.ndarray]:
    """Encode one Ask (``MTG_bot/bench/protocol.Ask``) for seat index ``seat``."""
    ctx = ctx or AskContext()
    world = executor.world
    order = world.player_order
    me_h = order[seat]
    opp_h = order[1 - seat]
    rel = {me_h: 1, opp_h: 2}

    # --- referenced handles: the ask's source, options, reveal
    site_cards = _CARD_RE.findall(ask.site)
    source = Handle("card", int(site_cards[0])) if site_cards else None
    if ask.kind == "scry" and ctx.revealed is not None:
        source = ctx.revealed
    parsed = [_OPTS[o.token] for o in ask.options[:MAX_OPTIONS]]
    offered = {p[1] for p in parsed if p[1] is not None and p[1].namespace == "card"}
    offered |= {p[2] for p in parsed if p[2] is not None and p[2].namespace == "card"}

    # --- the visible cards, in a fixed zone order
    ents: list[tuple[Handle, str, Handle]] = []  # (handle, zone, owner)
    for frame in reversed(executor.stack.frames):  # top first
        ents.append((frame.handle, "stack", frame.controller))
    groups = []
    for ph in (me_h, opp_h):
        zones = world.players[ph].zones
        if ph == me_h and ZONE_HAND in zones:
            ents.extend((h, ZONE_HAND, ph) for h in zones[ZONE_HAND].entries)
        if ZONE_BATTLEFIELD in zones:
            ents.extend((h, ZONE_BATTLEFIELD, ph) for h in zones[ZONE_BATTLEFIELD].entries)
        if ZONE_COMMAND in zones:
            ents.extend((h, ZONE_COMMAND, ph) for h in zones[ZONE_COMMAND].entries)
    for ph in (me_h, opp_h):
        zones = world.players[ph].zones
        if ZONE_GRAVEYARD in zones:
            groups.append([(h, ZONE_GRAVEYARD, ph) for h in zones[ZONE_GRAVEYARD].entries])
        if ZONE_EXILE in zones:
            groups.append([(h, ZONE_EXILE, ph) for h in zones[ZONE_EXILE].entries])
    seen = {e[0] for e in ents}
    room = MAX_CARDS - len(ents)
    for g in groups:
        keep = GRAVE_KEEP if g and g[0][1] == ZONE_GRAVEYARD else EXILE_KEEP
        g = [e for e in g if e[0] not in seen]
        # keep the newest; offered cards always stay
        tail = g[-keep:] if len(g) > keep else g
        extra = [e for e in g[:-keep] if e[0] in offered] if len(g) > keep else []
        for e in extra + tail:
            if room <= 0:
                break
            ents.append(e)
            seen.add(e[0])
            room -= 1
    # offered or revealed cards in hidden zones (library search, scry, a revealed hand)
    hidden = [h for h in sorted(offered | ({ctx.revealed} if ctx.revealed else set()), key=str)
              if h not in seen and h in world.cards]
    for h in hidden:
        zone = world.zone_of(h)
        ents.append((h, zone.kind, zone.controller))
        seen.add(h)
    ents = ents[: MAX_CARDS + 8]

    n = len(ents)
    cards_i = np.zeros((n, 5), dtype=np.int32)
    cards_f = np.zeros((n, CF), dtype=np.float32)
    ent_index = {me_h: 0, opp_h: 1}
    for j, (h, _, _) in enumerate(ents):
        ent_index[h] = 2 + j

    sick = _sick_set(executor)
    attackers = set(executor.attackers)
    blocked_by = executor.blocked_by
    blocking = {b for bs in blocked_by.values() for b in bs}
    decl_blockers_on: dict = {}
    for a in ctx.declared_blocks.values():
        decl_blockers_on[a] = decl_blockers_on.get(a, 0) + 1
    overlay = executor.control_overlay
    attachments = executor.attachments
    damage = executor.damage
    ledger = executor.ledger
    layers = executor.layers
    cards = world.cards
    for j, (h, zone, owner) in enumerate(ents):
        card = cards[h]
        ident = card.identity
        types, colors, kws, pp, pt, cmc, oid, is_token, is_creature = _static(ident)
        on_bf = zone == ZONE_BATTLEFIELD
        ctrl = overlay.get(h, owner) if on_bf else owner
        ci = cards_i[j]
        ci[0] = table.row(oid)
        ci[1] = ZONE_INDEX.get(zone, 0)
        ci[2] = rel.get(ctrl, 2)
        ci[3] = rel.get(owner, 2)
        host = attachments.get(h)
        if host is not None and host in ent_index:
            ci[4] = ent_index[host] + 1
        f = cards_f[j]
        if on_bf:
            f[F_TAPPED] = card.tapped
            f[F_SICK] = is_creature and h in sick
            f[F_ATTACKING] = h in attackers
            f[F_BLOCKING] = h in blocking
            f[F_BLOCKED] = bool(blocked_by.get(h))
            f[F_DECL_ATTACK] = h in ctx.declared_attackers
            f[F_DECL_BLOCK] = h in ctx.declared_blocks
            f[F_DECL_BLOCKERS] = decl_blockers_on.get(h, 0)
            f[F_ATTACHED] = host is not None
            kws = layers.keywords(h)
            if pp is not None or pt is not None or ident.power is not None:
                p, t = ledger.effective_pt(ident, h, card.counters)
            else:
                p, t = None, None
            f[F_DAMAGE] = damage.get(h, 0) / 5.0
        else:
            p, t = pp, pt
        f[F_TOKEN] = is_token
        f[F_ASK_SOURCE] = h == source
        f[F_OFFERED] = h in offered
        f[F_REVEALED] = (zone in (ZONE_LIBRARY, ZONE_HAND) and ctrl != me_h) or zone == ZONE_LIBRARY
        f[F_TYPE0:F_TYPE0 + len(TYPES)] = types
        f[F_COLOR0:F_COLOR0 + len(COLORS)] = colors
        for k in kws:
            idx = KW_INDEX.get(k)
            f[F_KW0 + idx if idx is not None else F_KW_OTHER] = 1.0
        if p is not None or t is not None:
            f[F_HAS_PT] = 1.0
            f[F_POWER] = (p or 0) / 5.0
            f[F_TOUGH] = (t or 0) / 5.0
        if card.counters:
            other = 0
            for k, v in card.counters.items():
                if k == "+1/+1":
                    f[F_P1] = v / 3.0
                elif k == "-1/-1":
                    f[F_M1] = v / 3.0
                elif k.lower() == "loyalty":
                    f[F_LOYALTY] = v / 5.0
                else:
                    other += v
            f[F_COUNTERS] = other / 3.0
        f[F_CMC] = cmc / 5.0

    # --- players
    players_f = np.zeros((2, PF), dtype=np.float32)
    active = world.active_player
    for i, ph in enumerate((me_h, opp_h)):
        pl = world.players[ph]
        zones = pl.zones
        bf = zones[ZONE_BATTLEFIELD].entries if ZONE_BATTLEFIELD in zones else []
        lands = creatures = untapped_lands = 0
        for h in bf:
            st = _static(cards[h].identity)
            if st[0][0]:
                lands += 1
                untapped_lands += not cards[h].tapped
            if st[8]:
                creatures += 1
        row = players_f[i]
        row[0] = pl.life / 20.0
        row[1] = len(zones[ZONE_HAND].entries) / 7.0 if ZONE_HAND in zones else 0.0
        row[2] = len(zones[ZONE_LIBRARY].entries) / 40.0 if ZONE_LIBRARY in zones else 0.0
        row[3] = len(zones[ZONE_GRAVEYARD].entries) / 20.0 if ZONE_GRAVEYARD in zones else 0.0
        row[4] = len(zones[ZONE_EXILE].entries) / 10.0 if ZONE_EXILE in zones else 0.0
        pool = pl.mana_pool
        for c_i, c in enumerate(("W", "U", "B", "R", "G", "C")):
            row[5 + c_i] = pool.get(c, 0) / 5.0
        row[11] = ph == active
        row[12] = lands / 10.0
        row[13] = creatures / 10.0
        row[14] = untapped_lands / 10.0
        row[15] = ph in executor.lost_players

    glob_f = np.zeros(GF, dtype=np.float32)
    glob_f[0] = world.turn / 20.0
    glob_f[1] = active == me_h
    glob_f[2] = len(executor.stack.frames) / 3.0
    glob_f[3] = min(len(ask.options), 99) / 10.0
    glob_f[4] = ctx.picked / 3.0
    glob_f[5] = len(ctx.declared_attackers) / 5.0
    glob_f[6] = len(attackers) / 5.0
    glob_f[7] = 1.0 if ask.refuse is not None else 0.0

    k = len(parsed)
    opts_i = np.zeros((k, 4), dtype=np.int32)
    opts_f = np.zeros((k, 2), dtype=np.float32)
    for i, (typ, h1, h2, ab, num, kicked) in enumerate(parsed):
        opts_i[i, 0] = typ
        if h1 is not None:
            opts_i[i, 1] = ent_index.get(h1, -1) + 1
        if h2 is not None:
            opts_i[i, 2] = ent_index.get(h2, -1) + 1
        opts_i[i, 3] = ab + 4
        opts_f[i, 0] = num / 5.0
        opts_f[i, 1] = kicked
    # compact dtypes: these arrays are pickled to the learner and buffered per decision
    return {
        "cards_i": cards_i.astype(np.int16),
        "cards_f": cards_f.astype(np.float16),
        "players_f": players_f.astype(np.float16),
        "glob_f": glob_f.astype(np.float16),
        "ask_i": np.array([ask_kind_index(ask.kind)], dtype=np.int16),
        "opts_i": opts_i.astype(np.int16),
        "opts_f": opts_f.astype(np.float16),
    }
