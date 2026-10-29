"""Gate G1: play one card in the real engine on a standard board, in every variant, and say what
happened. docs/PLAN_CARD_ONBOARDING.md.

- Every action goes through the engine's own legality surface (``legal_casts``,
  ``spell_target_slots``, ``legal_activations``, ``activation_target_slots``,
  ``validate_target_selection``): the probe can only do what a real game allows.
- Each variant runs in a fresh world (``tools/run_scenarios.py``'s ``ScenarioRunner``), so variants
  never leak into each other. The board is the same for every card, so traces compare.
- Choices the engine asks for during a variant are answered with the first word, then each other
  word of the first three asks is tried once (depth-one branching).
- The rendered text is what a blind verifier reads (gate G2); its sha256 is what mutation analysis
  compares (gate G3). An exception in any variant is a G1 failure.

Known blind spots (they go to the verifier as NOT EXERCISED, and to spec packs): cards in libraries,
an opponent's turn of actions, keyword-bearing synthetic creatures, cost changes to other spells.
"""

from __future__ import annotations

import hashlib
import itertools
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from run_scenarios import ScenarioRunner

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    CardRecord,
    Choose,
    FAtom,
    FAtomPred,
    Keyword,
    QConst,
    SpellAbility,
    TriggeredAbility,
    walk,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.executor.legality import ability_playable, activate
from MTG_bot.core.executor.query import (
    activation_target_slots,
    legal_activations,
    legal_casts,
    spell_target_slots,
    validate_target_selection,
)
from MTG_bot.core.executor.stack import cast, play_land
from MTG_bot.core.identity import Handle

BASICS = ("Plains", "Island", "Swamp", "Mountain", "Forest")
MAX_PER_ACTION = 8  # variants per action after branching (a probe budget, not a game rule)
MAX_TARGET_SETS = 12
WINDOW = ("counter:", "pay:", "cw:")

# key, zone, seat, name, type line, power, toughness, mana value
BOARD: tuple[tuple[str, str, int, str, str, str | None, str | None, int], ...] = (
    ("you_bear", "battlefield", 0, "Your Bear", "Creature — Bear", "2", "2", 2),
    ("you_giant", "battlefield", 0, "Your Giant", "Creature — Giant", "4", "4", 5),
    ("you_relic", "battlefield", 0, "Your Relic", "Artifact", None, None, 2),
    ("you_charm", "battlefield", 0, "Your Charm", "Enchantment", None, None, 2),
    ("you_spare", "hand", 0, "Your Spare Elf", "Creature — Elf", "3", "3", 3),
    ("you_trick", "hand", 0, "Your Trick", "Instant", None, None, 1),
    ("you_fallen", "graveyard", 0, "Your Fallen Zombie", "Creature — Zombie", "2", "2", 2),
    ("you_used", "graveyard", 0, "Your Used Sorcery", "Sorcery", None, None, 2),
    ("opp_bear", "battlefield", 1, "Opp Bear", "Creature — Bear", "2", "2", 2),
    ("opp_giant", "battlefield", 1, "Opp Giant", "Creature — Giant", "4", "4", 5),
    ("opp_relic", "battlefield", 1, "Opp Relic", "Artifact", None, None, 2),
    ("opp_charm", "battlefield", 1, "Opp Charm", "Enchantment", None, None, 2),
    ("opp_spare", "hand", 1, "Opp Spare Elf", "Creature — Elf", "3", "3", 3),
    ("opp_trick", "hand", 1, "Opp Trick", "Instant", None, None, 1),
    ("opp_fallen", "graveyard", 1, "Opp Fallen Zombie", "Creature — Zombie", "2", "2", 2),
    ("opp_used", "graveyard", 1, "Opp Used Sorcery", "Sorcery", None, None, 2),
)
MANA = {c: 9 for c in "WUBRGC"}


def _seat_name(world: Any, handle: Handle) -> str:
    return "you" if handle == world.player_order[0] else "opp"


@dataclass
class Variant:
    label: str
    asks: list[tuple[str, tuple[str, ...], str]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    error: str | None = None

    def render(self, names: Callable[[str], str]) -> list[str]:
        out = [f"[{self.label}]"]
        if self.error:
            out.append(f"  ERROR: {self.error}")
        for what, vocab, word in self.asks:
            kind = what.split(":", 1)[0]
            shown = ", ".join(names(v) for v in vocab[:10]) + (" ..." if len(vocab) > 10 else "")
            out.append(f"  ask {kind}: [{shown}] -> {names(word)}")
        out += [f"  event: {e}" for e in self.events] or ["  event: (none)"]
        out += [f"  change: {c}" for c in self.changes] or ["  change: (none)"]
        return out


class Probe:
    """One card of one set, probed against one supply (which may carry a draft tree)."""

    def __init__(self, supply: Any, set_code: str, oracle_id: str) -> None:
        self.supply = supply
        self.set_code = set_code
        self.oid = oracle_id
        self.card: CardRecord = supply.pool.results[oracle_id].card
        self.registry = build_full_registry()
        self.extra = self._extra_board()
        self.lands = [n for n in BASICS if any(m.name == n for m in supply.metas.values())]
        self.spells = self._stimulus_spells()

    # ------------------------------------------------------------------ world
    def _extra_board(self) -> list[tuple[str, str, int, str, str, str | None, str | None, int]]:
        """Creatures of every subtype the card's filters name, one per side, so tribal text has
        something to act on."""
        subs = sorted(
            {
                n.string_value
                for n in walk(self.card)
                if isinstance(n, FAtom) and n.pred is FAtomPred.SUBTYPE_EQ and n.string_value
            }
            - {"Bear", "Giant", "Elf", "Zombie"}
        )
        rows = []
        for sub in subs:
            low = sub.lower().replace(" ", "_")
            rows.append((f"you_{low}", "battlefield", 0, f"Your {sub}", f"Creature — {sub}", "2", "2", 2))
            rows.append((f"opp_{low}", "battlefield", 1, f"Opp {sub}", f"Creature — {sub}", "2", "2", 2))
        return rows

    def _stimulus_spells(self) -> dict[str, str]:
        """Real cards of the set to cast as stimuli: the cheapest instant or sorcery whose spell
        has no target and no choice, and the cheapest vanilla creature. Only fully compiled cards
        with no record, so a trace never depends on another card under review."""
        from MTG_bot.core.ability_tree import Selector, SelectorMode

        found: dict[str, tuple[int, str]] = {}
        for oid, meta in self.supply.metas.items():
            if oid == self.oid or not meta.engine_supported or not meta.has_spell_node:
                continue
            res = self.supply.pool.results[oid]
            if res.record is not None or res.unparsed or res.back_face_unparsed or res.ambiguities:
                continue  # stimuli are the compiler's own, fully compiled trees: never a card under review
            rec = res.card
            if rec.mana_cost is None or any(getattr(p, "amount", None) == QX() for p in rec.mana_cost.parts):
                continue
            spell = next((a for a in rec.abilities if isinstance(a, SpellAbility)), None)
            if spell is None:
                continue
            nodes = list(walk(spell))
            if "Creature" in rec.types:
                key = "you_cast_creature"
                if len(rec.abilities) != 1 or rec.keywords or spell.effect is not None:
                    continue
            elif "Instant" in rec.types or "Sorcery" in rec.types:
                key = "you_cast_spell"
                if spell.effect is None or any(
                    isinstance(n, Selector) and n.mode in (SelectorMode.TARGET, SelectorMode.CHOOSE, SelectorMode.ONE_OF)
                    for n in nodes
                ) or any(isinstance(n, Choose) for n in nodes):
                    continue
            else:
                continue
            cand = (rec.mana_value, rec.name)
            if key not in found or cand < found[key]:
                found[key] = cand
        return {k: v[1] for k, v in found.items()}

    def runner(self, where: str | None) -> ScenarioRunner:
        """A fresh standard board; the probed card ``card`` in ``where`` (None: not in the game)."""
        cards: list[dict[str, Any]] = []
        for key, zone, seat, name, type_line, p, t, mv in BOARD + tuple(self.extra):
            row: dict[str, Any] = {"key": key, "zone": zone, "controller": seat, "name": name,
                                   "type": type_line, "cmc": mv}
            if p is not None:
                row.update(power=p, toughness=t)
            cards.append(row)
        if self.lands:
            cards.append({"key": "you_land", "real": self.lands[0], "zone": "battlefield", "controller": 0})
            cards.append({"key": "opp_land", "real": self.lands[-1], "zone": "battlefield", "controller": 1})
            cards.append({"key": "you_land_drop", "real": self.lands[0], "zone": "hand", "controller": 0})
        for key, name in self.spells.items():
            cards.append({"key": key, "real": name, "zone": "hand", "controller": 0})
        if where is not None:
            cards.append({"key": "card", "real": self.card.name, "zone": where, "controller": 0})
        pack = {"world": {"life": 20, "seed": 7}, "set": self.set_code, "cards": cards,
                "mana": {"0": dict(MANA), "1": dict(MANA)}, "steps": []}
        return ScenarioRunner(pack, self.supply)

    def names(self, r: ScenarioRunner) -> Callable[[Any], str]:
        rev = {str(h): k for k, h in r.handles.items()}
        rev[str(r.p0)] = "you"
        rev[str(r.p1)] = "opp"

        handle_re = re.compile(r"(?<![\w:])((?:card|player):\d+)(?![\d])")

        def one(tag: str) -> str:
            if tag in rev:
                return rev[tag]
            ns, _, idx = tag.partition(":")
            h = Handle(ns, int(idx))
            if h in r.world.cards:
                return f"{r.world.cards[h].identity.name}#{idx}"
            return tag

        def name(x: Any) -> str:
            s = str(x)
            if s in rev:
                return rev[s]
            if isinstance(x, Handle) and x in r.world.cards:
                return f"{r.world.cards[x].identity.name}#{x.index}"
            # a word that embeds handles ("card:12@player:1"): whole handle tokens only, so
            # card:2 never matches inside card:25
            return handle_re.sub(lambda m: one(m.group(1)), s)

        return name

    # -------------------------------------------------------------- snapshot
    def snapshot(self, r: ScenarioRunner) -> tuple[dict, dict]:
        world, ex = r.world, r.ex
        name = self.names(r)
        objs = {}
        for h, c in world.cards.items():
            zone = world.zone_of(h).kind
            if zone == "library":
                continue
            pt, kws = None, ()
            if zone == "battlefield":
                kws = tuple(k.name for k in Keyword if ex.layers.keyword_of(h, k))
                if "Creature" in c.identity.type_line:
                    try:
                        pt = tuple(ex.ledger.effective_pt(c.identity, h, c.counters))
                    except Exception:  # noqa: BLE001 — a non-creature permanent
                        pt = None
            objs[name(h)] = (zone, _seat_name(world, world.controller_of(h)), bool(c.tapped),
                             tuple(sorted(dict(c.counters).items())), pt, kws, ex.damage.get(h, 0))
        players = {}
        for seat in world.player_order:
            pl = world.players[seat]
            players[_seat_name(world, seat)] = (
                pl.life, len(pl.zone("hand").entries), len(pl.zone("library").entries),
                tuple(sorted((k, v) for k, v in pl.mana_pool.items() if v)),
            )
        return objs, players

    @staticmethod
    def diff(before: tuple[dict, dict], after: tuple[dict, dict]) -> list[str]:
        out = []
        ob, pb = before
        oa, pa = after
        labels = ("zone", "controller", "tapped", "counters", "P/T", "keywords", "damage")
        for key in sorted(set(ob) | set(oa)):
            a, b = ob.get(key), oa.get(key)
            if a == b:
                continue
            if a is None:
                zone, ctrl, tapped, counters, pt, kws, _dmg = b
                desc = f"{zone}, {ctrl}" + (f", {pt[0]}/{pt[1]}" if pt else "")
                desc += f", {' '.join(kws)}" if kws else ""
                desc += ", tapped" if tapped else ""
                desc += f", counters {dict(counters)}" if counters else ""
                out.append(f"+ {key} ({desc})")
                continue
            if b is None:
                out.append(f"- {key} (gone from {a[0]})")
                continue
            parts = []
            for i, lab in enumerate(labels):
                if a[i] != b[i]:
                    fa, fb = a[i], b[i]
                    if lab == "P/T":
                        fa = "-" if fa is None else f"{fa[0]}/{fa[1]}"
                        fb = "-" if fb is None else f"{fb[0]}/{fb[1]}"
                    if lab == "keywords":
                        gained = sorted(set(fb) - set(fa))
                        lost = sorted(set(fa) - set(fb))
                        parts.append("keywords " + " ".join([f"+{k}" for k in gained] + [f"-{k}" for k in lost]))
                        continue
                    if lab == "counters":
                        fa, fb = dict(fa), dict(fb)
                    parts.append(f"{lab} {fa} -> {fb}")
            out.append(f"{key}: " + "; ".join(parts))
        for seat in sorted(set(pb) | set(pa)):
            a, b = pb.get(seat), pa.get(seat)
            if a == b:
                continue
            parts = []
            for i, lab in enumerate(("life", "hand", "library")):
                if a[i] != b[i]:
                    parts.append(f"{lab} {a[i]} -> {b[i]}")
            if a[3] != b[3]:
                da, db = dict(a[3]), dict(b[3])
                delta = {k: db.get(k, 0) - da.get(k, 0) for k in sorted(set(da) | set(db))}
                parts.append("mana " + " ".join(f"{k}{v:+d}" for k, v in delta.items() if v))
            out.append(f"{seat}: " + "; ".join(parts))
        return out

    def render_event(self, r: ScenarioRunner, e: Any) -> str | None:
        name = self.names(r)
        kind, d = e.kind, tuple(e.data)
        if kind in ("WINDOW_OPEN", "WINDOW_PASS", "TURN_PHASE"):
            return None
        s = name(e.subject) if e.subject is not None else "-"
        c = name(e.cause) if e.cause is not None else "-"
        by = f" (by {c}{'/' + e.cause_verb if e.cause_verb else ''})" if c != "-" else ""
        if kind == "ZONE_CHANGE":
            src = d[0] or "new"
            owner = f", owner {name(d[2])}->{name(d[3])}" if len(d) > 3 and d[2] is not None and d[2] != d[3] else ""
            return f"{s} moves {src} -> {d[1]}{owner}{by}"
        if kind == "DAMAGE":
            return f"{s} is dealt {d[0]} damage{' (combat)' if len(d) > 1 and d[1] else ''}{by}"
        if kind == "CREATURE_DIES":
            return f"{s} dies"
        if kind == "COUNTER_PLACED":
            return f"{s} gets {d[1]} {d[0]} counter(s){by}"
        if kind == "TAP_STATE":
            return f"{s} becomes {'tapped' if d[0] else 'untapped'}{by}"
        if kind == "CARD_DRAWN":
            return f"{name(d[0])} draws {s}"
        if kind in ("LIFE_GAINED", "LIFE_LOST"):
            return f"{s} {'gains' if kind == 'LIFE_GAINED' else 'loses'} {d[0]} life{by}"
        if kind == "CAST":
            return f"{name(d[0])} casts {s}" + (f" (X={d[4]})" if len(d) > 4 and d[4] is not None else "") + (" kicked" if len(d) > 5 and d[5] else "")
        if kind == "TARGETING":
            return f"{s} is targeted{by}"
        def fmt(x: Any) -> str:
            if isinstance(x, tuple):
                return "(" + ", ".join(fmt(y) for y in x) + ")"
            return name(x)

        return f"{kind} {s}{by} {', '.join(fmt(x) for x in d)}".rstrip()

    # ------------------------------------------------------------------ runs
    def run(self, where: str | None, label: str, action: Callable[[ScenarioRunner], None],
            choice: tuple[int, int] | None = None, end_turn: bool = False) -> Variant:
        """One variant in a fresh world. Every ask takes its default (PASS in a response window,
        else the first word), except ask ``choice[0]``, which takes word ``choice[1]``."""
        r = self.runner(where)
        before = self.snapshot(r)
        start = len(r.ex.journal.events)
        v = Variant(label)
        raw_asks: list[tuple[str, tuple[str, ...], str]] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            i = len(raw_asks)
            if choice is not None and i == choice[0] and choice[1] < len(vocab):
                word = vocab[choice[1]]
            elif what.startswith(WINDOW) and "PASS" in vocab:
                word = "PASS"
            else:
                word = vocab[0]
            raw_asks.append((what, tuple(vocab), word))
            return word

        r.ex.decisions.provider = provider
        # Trigger firings are queued, not journalled: spy on the binder's queue to see which of
        # the card's triggered abilities fired (by node position in the card's record).
        queued: list[str] = []
        real_queue = r.ex.binder._queue
        card_h = r.handles.get("card")

        def spy(source, controller, node, event, additional=False):
            if source == card_h:
                idx = next((i for i, ab in enumerate(self.card.abilities) if ab is node or ab == node), "?")
                queued.append(f"card's triggered ability [{idx}] triggers")
            return real_queue(source, controller, node, event, additional)

        r.ex.binder._queue = spy
        try:
            action(r)
            r.ex.fire_triggers()
        except Exception as exc:  # noqa: BLE001 — any raise inside a legal action is the finding
            v.error = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            r.ex.decisions.provider = None
            r.ex.binder._queue = real_queue
        name = self.names(r)
        v.triggers = queued  # type: ignore[attr-defined]
        v.events = queued + [t for e in r.ex.journal.events[start:] if (t := self.render_event(r, e))]
        after = self.snapshot(r)
        v.changes = self.diff(before, after)
        if end_turn and v.error is None:
            # what lasts: end the turn and diff again ("until end of turn" must wear off, a
            # permanent change must not; damage wears off in cleanup)
            r.ex.decisions.provider = provider
            try:
                r._dispatch({"op": "end_turn"})
                v.changes += [f"after the turn ends: {c}" for c in self.diff(after, self.snapshot(r))] or [
                    "after the turn ends: (nothing changes)"]
            except Exception as exc:  # noqa: BLE001
                v.error = f"at end of turn: {type(exc).__name__}: {exc}"[:300]
            finally:
                r.ex.decisions.provider = None
        v.asks = [(w, tuple(name(x) for x in voc), name(word)) for w, voc, word in raw_asks]
        v.raw_vocab = [voc for _, voc, _ in raw_asks]  # type: ignore[attr-defined]
        v.raw_what = [w for w, _, _ in raw_asks]  # type: ignore[attr-defined]
        return v

    def explore(self, where: str | None, label: str,
                action: Callable[[ScenarioRunner], None]) -> list[Variant]:
        """The default run, then each other word of each of the first three asks, once. Every run
        also ends the turn, to show what lasts."""
        base = self.run(where, label, action, end_turn=True)
        out = [base]
        for k, (what, vocab) in enumerate(zip(base.raw_what[:3], base.raw_vocab[:3])):  # type: ignore[attr-defined]
            if what.startswith(WINDOW):
                continue
            for alt in range(1, len(vocab)):
                if len(out) >= MAX_PER_ACTION:
                    return out
                out.append(self.run(where, f"{label} | ask {k + 1} -> {base.asks[k][1][alt]}",
                                    action, (k, alt), end_turn=True))
        return out

    # -------------------------------------------------------------- sections
    def _target_sets(self, slots: list[Any]) -> list[tuple[Handle, ...]]:
        per_slot: list[list[tuple[Handle, ...]]] = []
        for slot in slots:
            cands = sorted(slot.candidates)
            if slot.forced:
                picks = [tuple(cands[: slot.max_count])]
            else:
                picks = [(c,) for c in cands] if slot.min_count <= 1 <= slot.max_count else []
                if slot.max_count > 1 and len(cands) >= 2:
                    picks.append(tuple(cands[: min(slot.max_count, len(cands))]))
                if slot.min_count == 0:
                    picks.append(())
            per_slot.append([p for p in picks if validate_target_selection(slot, list(p)) is None])
        combos = [tuple(itertools.chain.from_iterable(c)) for c in itertools.product(*per_slot)]
        return combos[:MAX_TARGET_SETS]

    def _modes(self, node: SpellAbility) -> list[tuple[int, ...]]:
        eff = node.effect
        if isinstance(eff, Choose) and isinstance(eff.count, QConst):
            return list(itertools.combinations(range(len(eff.options)), eff.count.value))
        return [()]

    def _has_x(self) -> bool:
        cost = self.card.mana_cost
        return cost is not None and any(
            isinstance(getattr(part, "amount", None), QX) for part in cost.parts
        )

    def section_cast(self) -> tuple[list[str], list[Variant]]:
        notes: list[str] = []
        r = self.runner("hand")
        h = r.handles["card"]
        rows = [row for row in legal_casts(r.world, r.ex, r.p0) if row.handle == h]
        name = self.names(r)
        if not rows:
            notes.append("not castable or playable from hand on the standard board (all mana available)")
            return notes, []
        variants: list[Variant] = []
        for row in rows:
            if row.land:
                variants += self.explore("hand", "play land",
                                         lambda rr: play_land(rr.ex, rr.p0, rr.handles["card"]))
                continue
            slots = list(spell_target_slots(r.ex, row.node, spell_handle=h, seat=r.p0))
            for slot in slots:
                notes.append(
                    f"target slot ({'kicked ' if row.kicked else ''}cast): {slot.min_count}..{slot.max_count} of "
                    f"[{', '.join(name(c) for c in sorted(slot.candidates))}]"
                )
            xs = [0, 1, 3] if self._has_x() else [None]
            for targets, x, modes in itertools.product(self._target_sets(slots) or [()], xs, self._modes(row.node)):
                tnames = [name(t) for t in targets]
                label = "cast" + (" kicked" if row.kicked else "") + (f" X={x}" if x is not None else "")
                label += f" modes={list(modes)}" if modes else ""
                label += f" targets={tnames}" if targets else ""

                def act(rr: ScenarioRunner, t=tuple(tnames), x=x, kicked=row.kicked, modes=modes) -> None:
                    hs = tuple(rr.p0 if n == "you" else rr.p1 if n == "opp" else rr.handles[n] for n in t)
                    cast(rr.ex, rr.p0, rr.handles["card"], x=x, kicked=kicked,
                         mode_choices=modes, targets=hs)

                variants += self.explore("hand", label, act)
        return notes, variants

    def section_activate(self, where: str) -> tuple[list[str], list[Variant]]:
        notes: list[str] = []
        r = self.runner(where)
        h = r.handles["card"]
        name = self.names(r)
        legal = {o.ability_idx: o for o in legal_activations(r.world, r.ex, r.p0) if o.source == h}
        variants: list[Variant] = []
        for idx, ab in enumerate(self.card.abilities):
            if not isinstance(ab, ActivatedAbility):
                continue
            if idx not in legal:
                reason = ability_playable(r.world, r.ex, h, idx, seat=r.p0)
                notes.append(f"ability [{idx}] not activatable from {where}: {reason}")
                continue
            slots = list(activation_target_slots(r.ex, ab.effect, source=h, seat=r.p0))
            for slot in slots:
                notes.append(f"ability [{idx}] target slot: {slot.min_count}..{slot.max_count} of "
                             f"[{', '.join(name(c) for c in sorted(slot.candidates))}]")
            for targets in self._target_sets(slots) or [()]:
                tnames = [name(t) for t in targets]

                def act(rr: ScenarioRunner, t=tuple(tnames), idx=idx) -> None:
                    hs = tuple(rr.p0 if n == "you" else rr.p1 if n == "opp" else rr.handles[n] for n in t)
                    activate(rr.ex, rr.handles["card"], idx, seat=rr.p0, targets=hs)

                label = f"activate [{idx}] from {where}" + (f" targets={tnames}" if targets else "")
                variants += self.explore(where, label, act)
        return notes, variants

    def _atom(self, sentence: str) -> Any:
        return self.registry.match(sentence)[0].outcome.effect

    def stimuli(self) -> list[tuple[str, Callable[[ScenarioRunner], None]]]:
        draw, gain, lose = (self._atom(s) for s in ("Draw a card.", "You gain 3 life.", "You lose 2 life."))
        tap = self._atom("Tap target creature.")

        def ex(atom: Any, seat: int, source: str = "you_bear", target: str | None = None):
            def go(r: ScenarioRunner) -> None:
                binds = {"target": r.handles[target]} if target else {}
                r.ex.execute(atom, source=r.handles[source], controller=r.seats[seat], bindings=binds)
            return go

        def dmg(target: str, n: int, source: str = "opp_giant"):
            return lambda r: r._dispatch({"op": "deal_damage", "source": source, "target": target, "amount": n})

        def enter(key: str):
            return lambda r: r._dispatch({"op": "enter", "key": key})

        def turns(r: ScenarioRunner) -> None:
            for op in ("end_turn", "advance_turn", "end_turn", "advance_turn"):
                r._dispatch({"op": op})

        def enters_on_their_turn(r: ScenarioRunner) -> None:
            # the card is on the battlefield during the opponent's turn only: tells "each end step"
            # / "each upkeep" from "your end step" / "your upkeep"
            r._dispatch({"op": "end_turn"})
            r._dispatch({"op": "advance_turn"})
            r._dispatch({"op": "enter", "key": "card"})
            r._dispatch({"op": "end_turn"})

        def draw_two(r: ScenarioRunner) -> None:
            for _ in range(2):
                r.ex.execute(draw, source=r.handles["you_bear"], controller=r.p0, bindings={})

        def opp_attacks(r: ScenarioRunner) -> None:
            r._dispatch({"op": "end_turn"})
            r._dispatch({"op": "advance_turn"})
            r._dispatch({"op": "combat", "seat": 1, "attack": {"opp_bear": True}})

        out = [
            ("a creature enters under your control", enter("you_spare")),
            ("a creature enters under the opponent's control", enter("opp_spare")),
            ("you draw a card", ex(draw, 0)),
            ("you draw two cards, one after the other", draw_two),
            ("the opponent draws a card", ex(draw, 1, "opp_bear")),
            ("you gain 3 life", ex(gain, 0)),
            ("you lose 2 life", ex(lose, 0)),
            ("your creature (you_bear) dies", dmg("you_bear", 10)),
            ("an opponent's creature (opp_bear) dies", dmg("opp_bear", 10, "you_giant")),
            ("this card is dealt 1 damage", dmg("card", 1)),
            ("this card is dealt lethal damage", dmg("card", 99)),
            ("this card becomes tapped", ex(tap, 1, "opp_bear", "card")),
            ("turns pass: your end step, the opponent's turn, your next upkeep", turns),
            ("from your hand, the card enters during the opponent's turn, then that turn ends",
             enters_on_their_turn),
        ]
        if self.lands:
            out.insert(2, ("you play a land", lambda r: play_land(r.ex, r.p0, r.handles["you_land_drop"])))
        if "Creature" in self.card.types:
            out += [
                ("this creature attacks alone, unblocked",
                 lambda r: r._dispatch({"op": "combat", "seat": 0, "attack": {"card": True}})),
                ("this creature attacks and opp_giant blocks it",
                 lambda r: r._dispatch({"op": "combat", "seat": 0, "attack": {"card": True},
                                        "block": {"opp_giant": "card"}})),
            ]
        out.append(("another creature you control (you_bear) attacks",
                    lambda r: r._dispatch({"op": "combat", "seat": 0, "attack": {"you_bear": True}})))
        out.append(("on the opponent's turn, opp_bear attacks you (no block)", opp_attacks))
        for key, what in (("you_cast_spell", "an instant or sorcery"), ("you_cast_creature", "a creature")):
            if key in self.spells:
                out.append((f"you cast {what} ({self.spells[key]})",
                            lambda r, k=key: cast(r.ex, r.p0, r.handles[k])))
        return out

    def section_stimuli(self) -> list[Variant]:
        variants = []
        for label, action in self.stimuli():
            v = self.run("hand" if label.startswith("from your hand") else "battlefield", label, action)
            fired = ", ".join(sorted(set(v.triggers))) or "none"  # type: ignore[attr-defined]
            v.label = f"stimulus: {label} -> {fired}"
            variants.append(v)
        return variants

    def section_static(self) -> list[str]:
        """The standard board with the card on the battlefield, against the board without it."""
        without = self.snapshot(self.runner(None))
        with_card = self.snapshot(self.runner("battlefield"))
        lines = [c for c in self.diff(without, with_card) if not c.startswith("+ card ")]
        own = with_card[0].get("card")
        if own:
            _zone, _ctrl, _tapped, counters, pt, kws, _dmg = own
            lines.insert(0, f"card on the battlefield: {pt[0]}/{pt[1]}" if pt
                         else "card on the battlefield: not a creature")
            if kws:
                lines.insert(1, f"card keywords: {' '.join(kws)}")
            if counters:
                lines.insert(1, f"card counters: {dict(counters)}")
        return lines

    # ---------------------------------------------------------------- report
    def report(self) -> Report:
        rep = Report(self.card.name, self.set_code)
        is_land = "Land" in self.card.types
        notes, cast_vs = self.section_cast()
        rep.add("Cast or play from hand", notes, cast_vs)
        if any(isinstance(a, ActivatedAbility) for a in self.card.abilities):
            for where in ("battlefield", "hand", "graveyard"):
                n, vs = self.section_activate(where)
                if vs or where == "battlefield":
                    rep.add(f"Activated abilities, card in {where}", n, vs)
        if not ("Instant" in self.card.types or "Sorcery" in self.card.types):
            rep.add("Triggers: stimuli with the card on the battlefield",
                    [f"the card has {sum(isinstance(a, TriggeredAbility) for a in self.card.abilities)} triggered ability node(s)"],
                    self.section_stimuli())
            rep.add("Static: the board with the card on the battlefield vs without it",
                    self.section_static(), [])
        del is_land
        return rep


class Report:
    def __init__(self, name: str, set_code: str) -> None:
        self.name = name
        self.set_code = set_code
        self.sections: list[tuple[str, list[str], list[Variant]]] = []

    def add(self, title: str, notes: list[str], variants: list[Variant]) -> None:
        self.sections.append((title, notes, variants))

    @property
    def errors(self) -> list[str]:
        return [f"{v.label}: {v.error}" for _, _, vs in self.sections for v in vs if v.error]

    def text(self) -> str:
        out = [f"# Probe: {self.name} ({self.set_code})"]
        if self.errors:
            out.append(f"ENGINE ERRORS: {len(self.errors)}")
        for title, notes, variants in self.sections:
            out.append(f"## {title}")
            out += [f"- {n}" for n in notes]
            for v in variants:
                out += v.render(lambda x: x)
        return "\n".join(out) + "\n"

    def sha(self) -> str:
        return hashlib.sha256(self.text().encode("utf-8")).hexdigest()
