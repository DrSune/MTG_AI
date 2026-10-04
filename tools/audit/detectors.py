#!/usr/bin/env python3
"""BUGCATCH B2 — oracle-free anomaly detectors D1..D6 over live journals.

Design: KNOWLEDGE/2026-10-02/12-bugcatch-design.md §D. Two scan modes:

* ``catalog``  — read-only pass over the pinned 10-seed journals in
  ``tools/traces/catalog.json``. The catalog stores per row only
  ``[sha16, "kind|subject|cause|verb"]`` — the ``data`` payload (amounts,
  PT assertions, zone names, counter kinds) is hashed away. Therefore the
  catalog pass is STRUCTURAL ONLY: kind inventories + a loud EXEMPT for
  every detector that needs the payload (documented coverage gap).
* ``replay``   — N in-process games replaying the exact ``--repro`` recipe
  (``deal_decks``/``_setup_game``/``_play`` from ``games.py``), consuming
  the FULL journal rows (``EventJournal.dump()``) plus the lifecycle
  registers (``layers``/``replacements``/``binder`` dumps). ``--repro``
  itself persists no rows, so the scan mirrors it in-process.

Independence rule (D5): the effective-PT recompute is derived HERE from
journal rows only (COUNTER_PLACED increments, CREATURE_DIES was-PT
assertions, and a defensively-implemented SET_PT/MODIFY_PT fold for row
kinds the journal does not yet emit). Engine ledger code is NEVER imported.

Output: ``tools/audit/anomalies.json`` — per seed per detector: hits (row
references) or clean/exempt. Run::

    .venv/bin/python tools/audit/detectors.py                 # both scans
    .venv/bin/python tools/audit/detectors.py --seeds 20      # replay scan size
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CATALOG = REPO / "tools" / "traces" / "catalog.json"
OUT_DEFAULT = REPO / "tools" / "audit" / "anomalies.json"

# Journal kinds (MTG_bot/core/executor/events.py KIND_* string values).
KIND_ZONE_CHANGE = "ZONE_CHANGE"
KIND_CREATURE_DIES = "CREATURE_DIES"
KIND_COUNTER_PLACED = "COUNTER_PLACED"
KIND_DAMAGE = "DAMAGE"
KIND_LIFE_GAINED = "LIFE_GAINED"
# B3a: the engine's life-loss feed (executor.events.KIND_LIFE_LOST). The
# D1 fold vocabulary must track the journal's: start + ΣLIFE_GAINED
# − ΣDAMAGE − ΣLIFE_LOST == final life. Losing life is NOT dealt damage
# (CR 118.5), so it is its own kind and its own fold term.
KIND_LIFE_LOST = "LIFE_LOST"
KIND_TURN_PHASE = "TURN_PHASE"
KIND_GAME_LOST = "GAME_LOST"
KIND_COMBAT_DAMAGE = "COMBAT_DAMAGE"
# Row kinds the journal does NOT emit today (mana verbs, PT layers). The
# detectors fold them defensively so that when the verbs arrive the lanes
# stop being EXEMPT for free.
KIND_MANA_ADDED = "MANA_ADDED"
KIND_MANA_SPENT = "MANA_SPENT"
KIND_SET_PT = "SET_PT"
KIND_MODIFY_PT = "MODIFY_PT"

BATTLEFIELD = "battlefield"

# Counter kinds that move power/toughness (CounterKind in ability_tree).
PT_COUNTER_DELTA: dict[str, tuple[int, int]] = {
    "PLUS_1_PLUS_1": (1, 1),
    "MINUS_1_MINUS_1": (-1, -1),
}


# --------------------------------------------------------------------------
# row model


@dataclass(frozen=True)
class Handle:
    """Mirror of the engine's identity.Handle (namespace, index) — value
    equality via str key; no engine import needed inside the detectors."""

    namespace: str
    index: int

    def __str__(self) -> str:
        return f"{self.namespace}:{self.index}"


def _handle(value: object) -> str:
    return str(value)


def _parse_handle_tag(tag: str) -> Handle | None:
    ns, _, idx = tag.partition(":")
    if not idx.isdigit():
        return None
    return Handle(ns, int(idx))


def _to_int(value: object) -> int:
    return int(str(value))


def _parse_data(data: object) -> tuple[object, ...] | None:
    """dump() rows carry data as a *repr string* possibly containing
    ``Handle(namespace=..., index=...)`` calls; eval under a tiny shim.
    Returns None when the payload is absent (catalog label rows)."""
    if data is None:
        return None
    if isinstance(data, tuple):
        return data
    if not isinstance(data, str):
        return None
    try:
        # Trusted engine-produced repr data (Handle(...) shim names only).
        value = eval(data, {"__builtins__": {}}, {"Handle": Handle})
    except (SyntaxError, ValueError, TypeError, NameError):
        try:
            value = ast.literal_eval(data)
        except (ValueError, SyntaxError):
            return None
    return value if isinstance(value, tuple) else (value,)


@dataclass
class Row:
    index: int
    clock: int
    kind: str
    subject: str
    cause: str
    verb: str
    data: tuple[object, ...] | None  # None = payload not available


@dataclass
class ReplayData:
    """Everything a detector may consume; catalog-scan instances leave the
    optional registers and every row's payload empty."""

    seed: str
    rows: list[Row]
    start_life: dict[str, int] = field(default_factory=dict)
    final_life: dict[str, int] = field(default_factory=dict)
    final_zone: dict[str, str] = field(default_factory=dict)
    identity_name: dict[str, str] = field(default_factory=dict)
    layers_rows: list[tuple[object, ...]] | None = None
    repl_rows: list[tuple[object, ...]] | None = None
    binder_dump: dict[str, list[Any]] | None = None
    crashed: str | None = None


@dataclass
class Hit:
    detector: str
    seed: str
    detail: str
    row_index: int | None = None
    clock: int | None = None
    subject: str | None = None
    klass: str = "hit"

    def json(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "seed": self.seed,
            "class": self.klass,
            "detail": self.detail,
            "row_index": self.row_index,
            "clock": self.clock,
            "subject": self.subject,
        }


@dataclass
class Verdict:
    detector: str
    status: str  # clean | HIT | EXEMPT
    note: str = ""
    hits: list[Hit] = field(default_factory=list)

    def json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status, "note": self.note}
        if self.hits:
            out["hits"] = [h.json() for h in self.hits]
        return out


# --------------------------------------------------------------------------
# shared timeline helpers (built once per game, consumed by D3/D4/D5/D6)


@dataclass
class Presence:
    """Per-handle battlefield presence derived from ZONE_CHANGE rows."""

    marks: dict[str, list[tuple[int, bool]]] = field(default_factory=dict)
    ever_created: dict[str, int] = field(default_factory=dict)  # clock of creation
    created_into: dict[str, str] = field(default_factory=dict)
    owner_changes: dict[str, list[tuple[int, str, str]]] = field(default_factory=dict)

    def present(self, handle: str, clock: int) -> bool:
        state = False
        for at, on in self.marks.get(handle, []):
            if at <= clock:
                state = on
            else:
                break
        return state


def build_presence(rows: list[Row]) -> Presence:
    pres = Presence()
    for row in rows:
        if row.kind != KIND_ZONE_CHANGE or row.data is None or len(row.data) < 4:
            continue
        from_state, to_state, owner_before, owner_after = row.data[:4]
        handle = row.subject
        pres.marks.setdefault(handle, []).append(
            (row.clock, str(to_state) == BATTLEFIELD)
        )
        if from_state is None:
            pres.ever_created[handle] = row.clock
            pres.created_into[handle] = str(to_state)
        if owner_before is not None and str(owner_before) != str(owner_after):
            pres.owner_changes.setdefault(handle, []).append(
                (row.clock, str(owner_before), str(owner_after))
            )
    return pres


def counter_deltas(rows: list[Row]) -> dict[str, list[tuple[int, str, int]]]:
    """handle -> [(clock, counter_kind_name, amount)] placements (COUNTER_PLACED)."""
    out: dict[str, list[tuple[int, str, int]]] = {}
    for row in rows:
        if row.kind != KIND_COUNTER_PLACED or row.data is None or len(row.data) < 2:
            continue
        kind_name, amount = row.data[0], row.data[1]
        try:
            n = _to_int(amount)
        except (TypeError, ValueError):
            continue
        out.setdefault(row.subject, []).append((row.clock, str(kind_name), n))
    return out


# --------------------------------------------------------------------------
# D1 life conservation


def d1_life(g: ReplayData) -> Verdict:
    v = Verdict("D1_life", "clean")
    life_kinds = (KIND_DAMAGE, KIND_LIFE_GAINED, KIND_LIFE_LOST)
    if not any(r.kind in life_kinds for r in g.rows):
        v.note = "no life-moving rows; nothing to conserve"
        return v
    if not g.final_life:
        v.status = "EXEMPT"
        v.note = "final life unavailable (catalog rows carry no payload/state)"
        return v
    gains: dict[str, int] = {}
    losses: dict[str, int] = {}
    for row in g.rows:
        if row.data is None:
            v.status = "HIT"
            v.hits.append(
                Hit("D1_life", g.seed, "payload-less row in a replay scan", row.index)
            )
            continue
        if row.kind == KIND_LIFE_GAINED and row.subject.startswith("player:"):
            gains[row.subject] = gains.get(row.subject, 0) + _to_int(row.data[0])
        elif row.kind in (KIND_DAMAGE, KIND_LIFE_LOST) and row.subject.startswith(
            "player:"
        ):
            losses[row.subject] = losses.get(row.subject, 0) + _to_int(row.data[0])
    for player, final in g.final_life.items():
        start = g.start_life.get(player, 20)
        expected = start + gains.get(player, 0) - losses.get(player, 0)
        if expected != final:
            v.status = "HIT"
            v.hits.append(
                Hit(
                    "D1_life",
                    g.seed,
                    f"{player}: journal fold {start}+{gains.get(player, 0)}-"
                    f"{losses.get(player, 0)}={expected} but final life {final} "
                    f"(delta {final - expected}: life moved by an unjournalled "
                    f"verb, or a DAMAGE/LIFE row missed/ghosted)",
                )
            )
    return v


# --------------------------------------------------------------------------
# D2 mana conservation


def d2_mana(g: ReplayData) -> Verdict:
    v = Verdict("D2_mana", "clean")
    mana_rows = [r for r in g.rows if r.kind in (KIND_MANA_ADDED, KIND_MANA_SPENT)]
    if not mana_rows:
        v.status = "EXEMPT"
        v.note = (
            "the journal has no mana verb (no ADD_MANA/MANA_SPENT kinds in the "
            "KIND_* vocabulary) — conservation unverifiable; lane stays exempt "
            "until mana is journalled (Treasure {T} gap precedent)"
        )
        return v
    pool: dict[str, int] = {}
    for row in mana_rows + [r for r in g.rows if r.kind == KIND_TURN_PHASE]:
        if row.data is None:
            continue
        if row.kind == KIND_MANA_ADDED:
            pool[row.subject] = pool.get(row.subject, 0) + _to_int(row.data[0])
        elif row.kind == KIND_MANA_SPENT:
            pool[row.subject] = pool.get(row.subject, 0) - _to_int(row.data[0])
            if pool[row.subject] < 0:
                v.status = "HIT"
                v.hits.append(
                    Hit(
                        "D2_mana",
                        g.seed,
                        f"{row.subject} spent more than added (pool "
                        f"{pool[row.subject]})",
                        row.index,
                        row.clock,
                        row.subject,
                        klass="leak",
                    )
                )
        elif row.kind == KIND_TURN_PHASE:
            phase_name = str(row.data[0])
            if phase_name in ("ending", "end", "cleanup"):
                # CR 106.4: mana empties at end of step; nonzero here is a leak
                # UNLESS a mana-pool-retention/drain verb was journalled.
                for player, amount in pool.items():
                    if amount != 0:
                        v.status = "HIT"
                        v.hits.append(
                            Hit(
                                "D2_mana",
                                g.seed,
                                f"pool {amount} for {player} survives phase "
                                f"'{phase_name}' with no drain verb journalled",
                                row.index,
                                row.clock,
                                player,
                                klass="leak",
                            )
                        )
                pool = {}
    return v


# --------------------------------------------------------------------------
# D3 counter conservation


def d3_counters(g: ReplayData) -> Verdict:
    v = Verdict("D3_counter", "clean")
    placements = counter_deltas(g.rows)
    if not placements:
        v.note = "no COUNTER_PLACED rows"
        return v
    if not any(r.kind == KIND_ZONE_CHANGE and r.data is not None for r in g.rows):
        v.status = "EXEMPT"
        v.note = "zone payload unavailable (catalog rows) — presence unverifiable"
        return v
    pres = build_presence(g.rows)
    deaths = {r.subject: r for r in g.rows if r.kind == KIND_CREATURE_DIES}
    for handle, events in sorted(placements.items()):
        for clock, kind_name, amount in events:
            died = deaths.get(handle)
            after_death = died is not None and clock > died.clock
            if after_death or not pres.present(handle, clock):
                v.status = "HIT"
                v.hits.append(
                    Hit(
                        "D3_counter",
                        g.seed,
                        f"phantom placement: {kind_name} x{amount} on {handle} at "
                        f"clock {clock} while not on the battlefield "
                        f"(counters that cost resources must move before resolving)",
                        None,
                        clock,
                        handle,
                    )
                )
    v.note = (
        "counter REMOVALS emit no row (grammar has no removal feed), so the "
        "removal side of conservation is exempt by construction"
    )
    return v


# --------------------------------------------------------------------------
# D4 token ledger


def d4_tokens(g: ReplayData) -> Verdict:
    v = Verdict("D4_token", "clean")
    tokens = [
        r
        for r in g.rows
        if r.kind == KIND_ZONE_CHANGE
        and r.data is not None
        and len(r.data) >= 4
        and r.data[0] is None
    ]
    if not tokens:
        v.note = "no created (token) objects in this game"
        return v
    if not g.final_zone:
        v.status = "EXEMPT"
        v.note = "final battlefield state unavailable (catalog rows)"
        return v
    for row in tokens:
        data = row.data
        assert data is not None and len(data) >= 4
        to_state = str(data[1])
        if to_state != BATTLEFIELD:
            v.status = "HIT"
            v.hits.append(
                Hit(
                    "D4_token",
                    g.seed,
                    f"token {row.subject} created into '{to_state}' — creation "
                    "enters the battlefield directly",
                    row.index,
                    row.clock,
                    row.subject,
                )
            )
        owner_before, owner_after = data[2], data[3]
        if owner_before is not None and str(owner_before) != str(owner_after):
            v.status = "HIT"
            v.hits.append(
                Hit(
                    "D4_token",
                    g.seed,
                    f"token {row.subject} created with owner change "
                    f"{owner_before}->{owner_after}",
                    row.index,
                    row.clock,
                    row.subject,
                )
            )
    token_handles = {r.subject for r in tokens}
    pres = build_presence(g.rows)
    for handle in sorted(token_handles):
        journal_on_bf = pres.present(handle, max((r.clock for r in g.rows), default=0))
        world_on_bf = g.final_zone.get(handle) == BATTLEFIELD
        if journal_on_bf != world_on_bf:
            v.status = "HIT"
            v.hits.append(
                Hit(
                    "D4_token",
                    g.seed,
                    f"token {handle}: journal says on-battlefield={journal_on_bf}, "
                    f"world says '{g.final_zone.get(handle)}' — ledger/world split",
                    None,
                    None,
                    handle,
                )
            )
    v.note = (
        "token copies/commander-copy tokens have no register class of their "
        "own yet (design §D FP story); copies share the created-object lane"
    )
    return v


# --------------------------------------------------------------------------
# D5 independent layer recompute


@dataclass
class _Death:
    handle: str
    row: Row
    was_pt: tuple[int, int]
    pt_delta: tuple[int, int]


def d5_pt_recompute(g: ReplayData) -> Verdict:
    """Independently re-derive effective PT and diff vs the engine's own
    CREATURE_DIES was-PT assertions. The fold is re-implemented HERE:
    counters stack on the base, SET_PT overwrites the base at its point,
    MODIFY_PT adds — none of it imported from the engine's ledger."""
    v = Verdict("D5_pt_recompute", "clean")
    deaths = [
        r
        for r in g.rows
        if r.kind == KIND_CREATURE_DIES and r.data is not None and len(r.data) >= 5
    ]
    if not deaths:
        v.note = "no was-PT assertions (no deaths) in this game"
        return v
    placements = counter_deltas(g.rows)
    pt_rows: dict[str, list[Row]] = {}
    for row in g.rows:
        if row.kind in (KIND_SET_PT, KIND_MODIFY_PT):
            pt_rows.setdefault(row.subject, []).append(row)

    def fold(handle: str, died_at: int) -> tuple[int, int]:
        dp = dt = 0
        for clock, kind_name, amount in placements.get(handle, []):
            if clock <= died_at:
                step = PT_COUNTER_DELTA.get(kind_name, (0, 0))
                dp += step[0] * amount
                dt += step[1] * amount
        for row in pt_rows.get(handle, []):
            if (
                row.kind == KIND_MODIFY_PT
                and row.clock <= died_at
                and row.data is not None
            ):
                dp += _to_int(row.data[0])
                dt += _to_int(row.data[1]) if len(row.data) > 1 else 0
                # SET_PT rewrites the base — it is folded into the anchor
                # derivation (derived base), not the delta, by design.
        return dp, dt

    parsed: list[_Death] = []
    for row in deaths:
        data = row.data
        assert data is not None
        try:
            was_pt = (_to_int(data[3]), _to_int(data[4]))
        except (TypeError, ValueError):
            continue
        dp, dt = fold(row.subject, row.clock)
        parsed.append(_Death(row.subject, row, was_pt, (dp, dt)))

    groups: dict[str, list[_Death]] = {}
    for death in parsed:
        key = g.identity_name.get(death.handle) or "?"
        if key == "?":
            # Without the printed identity the grouping must not merge
            # strangers; per-handle checks below still run.
            key = death.handle
        groups.setdefault(key, []).append(death)

    for key, deaths_g in sorted(groups.items()):
        # Rule A — counter-invariant assertions: same asserted PT with
        # different counter deltas means the fold ignored the counters
        # (the trufflesnout killer). Base-unknown, SET_PT-proof.
        by_assert: dict[tuple[int, int], list[_Death]] = {}
        for death in deaths_g:
            by_assert.setdefault(death.was_pt, []).append(death)
        for asserted, bucket in by_assert.items():
            deltas = {d.pt_delta for d in bucket}
            if len(deltas) > 1 and any(d != (0, 0) for d in deltas):
                v.status = "HIT"
                for death in bucket:
                    v.hits.append(
                        Hit(
                            "D5_pt_recompute",
                            g.seed,
                            f"counter-invariant assert: {death.handle} died "
                            f"asserted {asserted[0]}/{asserted[1]} with pt-delta "
                            f"{death.pt_delta} while a same-identity copy "
                            f"({key}) asserts the SAME PT with a different "
                            "counter fold — recompute says they must differ",
                            death.row.index,
                            death.row.clock,
                            death.handle,
                            klass="counter-blind",
                        )
                    )
        # Rule B — anchor fold check: a zero-delta death pins the base;
        # other copies must assert base+delta exactly.
        anchors = [d for d in deaths_g if d.pt_delta == (0, 0)]
        if not anchors:
            continue
        base = anchors[0].was_pt
        for death in deaths_g:
            if death.pt_delta == (0, 0):
                continue
            expected = (base[0] + death.pt_delta[0], base[1] + death.pt_delta[1])
            if death.was_pt == expected:
                continue
            blind = death.was_pt == base
            v.status = "HIT"
            v.hits.append(
                Hit(
                    "D5_pt_recompute",
                    g.seed,
                    f"recompute mismatch on {death.handle} ({key}): assert "
                    f"{death.was_pt[0]}/{death.was_pt[1]} vs fold "
                    f"{expected[0]}/{expected[1]} (anchor base {base[0]}/{base[1]} "
                    f"+ counters {death.pt_delta})"
                    + (
                        " — COUNTER-BLIND: assertion equals the uncountered base"
                        if blind
                        else "; NOTE: a SET_PT/MODIFY_PT layer is a possible "
                        "benign reading (those verbs are not journalled)"
                    ),
                    death.row.index,
                    death.row.clock,
                    death.handle,
                    klass="counter-blind" if blind else "unexplained-diff",
                )
            )
    return v


# --------------------------------------------------------------------------
# D6 lifecycle audit


def d6_lifecycle(g: ReplayData) -> Verdict:
    v = Verdict("D6_lifecycle", "clean")

    def hit(detail: str, klass: str, subject: str | None = None) -> None:
        v.status = "HIT"
        v.hits.append(Hit("D6_lifecycle", g.seed, detail, None, None, subject, klass))

    if g.binder_dump is None and g.repl_rows is None and g.layers_rows is None:
        v.status = "EXEMPT"
        v.note = "registers not captured (catalog rows) — lifecycle unverifiable"
        return v
    notes: list[str] = []

    if g.binder_dump is not None:
        # (i) registered-never-drained: a delayed trigger still pending at
        # game end never fired AND never expired — the clock-bounded window
        # is the whole game (delayed durations are clock-bound by their
        # duration node, so survival to game end means the window bound was
        # met without a drain).
        for entry in g.binder_dump.get("delayed", []):
            hit(
                f"delayed trigger still pending at game end (never drained, "
                f"never expired): {entry!r:.160s}",
                "registered-never-drained",
            )
        # (ii) dead-handle bound refs: a still-attached trigger on a handle
        # that ended off the battlefield (IS_SOURCE bleed). FP story:
        # graveyard-lifetime triggers are legal — reported as suspects.
        for entry in g.binder_dump.get("attached", []):
            handle = str(entry[0])
            if (
                handle.startswith("card:")
                and g.final_zone
                and g.final_zone.get(handle) not in (None, BATTLEFIELD)
            ):
                hit(
                    f"trigger attached to {handle} which ended in zone "
                    f"'{g.final_zone.get(handle)}' (detached only if dead)",
                    "dead-handle-bound-ref",
                    handle,
                )

    if g.repl_rows is not None:
        # (iii) replacement fired >1x per event: two replacement records
        # competing for the same event identity (containment case). FP
        # story: legal sequential replacement choice per CR 614.
        # B3a narrowing: only LIVE records can apply to an event. An
        # ``expired`` row is a lifecycle audit trail entry — a re-entering
        # card's previous registration, self-detached by
        # replacements.attach_source (replacements.py) the instant the new
        # one registers, so the two NEVER co-exist. CR 614.3 co-registration
        # requires records applied to the same event simultaneously; a ghost
        # can't. B2 seed 16/17 Containment Priest double-list: falsified.
        by_event: dict[str, list[tuple[object, ...]]] = {}
        for row in g.repl_rows:
            if row and row[0] == "repl" and row[5] == "live":
                by_event.setdefault(str(row[6]), []).append(row)
        for event, rows in sorted(by_event.items()):
            if len(rows) > 1:
                hit(
                    f"{len(rows)} replacement records for one event "
                    f"{event[:120]!r} (statuses "
                    f"{[str(r[5]) for r in rows]})",
                    "multi-replacement-per-event",
                    str(rows[0][2]),
                )

    if g.layers_rows is not None:
        # (iv) dead-handle bound refs in the layer registry: live layers
        # whose source/targets ended off the battlefield.
        # B3a narrowing (source side only): a duration-tagged ``grant`` /
        # ``lose`` layer is created at its spell/ability RESOLUTION, and
        # CR 611.2a — "an effect once created exists independently of its
        # source" — so an instant that granted an EOT effect correctly
        # lives in the graveyard while the grant stays live (B2 seed 16:
        # Crash Through's +3/+3 grant, falsified). Static/continuous
        # layers DO depend on their source (CR 611.3a: loses the ability
        # when the source leaves), so a dead source there stays a hit.
        # The TARGET side is flagged for every kind regardless.
        for row in g.layers_rows:
            seq, kind_, source, _controller, tag, status = row[:6]
            raw_targets = row[6] if isinstance(row[6], tuple) else ()
            targets = tuple(str(t) for t in raw_targets)
            if status != "live" or not g.final_zone:
                continue
            source_exempt = kind_ in ("grant", "lose") and bool(str(tag).strip())
            for raw in (source, *targets):
                handle = str(raw)
                if source_exempt and handle == str(source):
                    continue
                if handle.startswith("card:") and g.final_zone.get(handle) not in (
                    None,
                    BATTLEFIELD,
                ):
                    hit(
                        f"live layer #{seq} kind={kind_} tag={tag} bound to "
                        f"{handle} ended in '{g.final_zone.get(handle)}'",
                        "dead-handle-bound-ref",
                        handle,
                    )
    notes.append(
        "delayed triggers legitimately expire mid-game (clock-bounded); only "
        "game-end survivors are flagged; attached-on-graveyard is suspect "
        "(graveyard triggers are legal), adjudication decides; repl lane "
        "counts only live records (expired = self-detached lifecycle ghost, "
        "CR 614.3 needs co-existence); grant/lose source-side dead handles "
        "are CR 611.2a-legal (effect outlives its source)"
    )
    if notes:
        v.note = "; ".join(notes)
    return v


DETECTORS = (d1_life, d2_mana, d3_counters, d4_tokens, d5_pt_recompute, d6_lifecycle)


# --------------------------------------------------------------------------
# replay generation (mirrors the games.py --repro recipe exactly)


def replay_game(
    seed: int, pool: str, deck_pairs_seed: int, turn_cap: int
) -> ReplayData:
    from MTG_bot.core.executor.games import (  # deferred: scan-only import
        RandomPolicy,
        _play,
        _setup_game,
        deal_decks,
        get_supply,
    )

    supply = get_supply(pool)
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    start_life = {str(h): int(p.life) for h, p in game.world.players.items()}
    crashed = None
    try:
        _play(game, RandomPolicy(seed), game.world.player_order, turn_cap)
    except BaseException as error:  # noqa: BLE001 - pin as-of-death, catalog precedent
        crashed = f"{type(error).__name__}: {error}"
    world = game.world
    rows = [
        Row(
            i,
            int(str(r[0])),
            str(r[1]),
            str(r[2]),
            str(r[3]),
            str(r[4]),
            _parse_data(r[5]),
        )
        for i, r in enumerate(game.executor.journal.dump())
    ]
    # Map world state by str-tag keys. We must iterate the engine's own
    # Handle objects (dataclass equality is class-scoped, so a reconstructed
    # mirror Handle never matches an engine map key).
    final_zone: dict[str, str] = {}
    identity_name: dict[str, str] = {}
    for handle, record in world.cards.items():
        tag = str(handle)
        try:
            final_zone[tag] = str(world.zone_of(handle).kind)
        except (KeyError, ValueError):
            pass  # unzoned card (removed from play) — no final zone
        identity_name[tag] = str(
            getattr(record.identity, "name", "")
            or getattr(record.identity, "type_line", "")
        )
    binder: dict[str, list[Any]] = {}
    for group in game.executor.binder.dump():
        if (
            isinstance(group, tuple)
            and len(group) == 2
            and isinstance(group[1], (list, tuple))
        ):
            binder[str(group[0])] = list(group[1])
    return ReplayData(
        seed=str(seed),
        rows=rows,
        start_life=start_life,
        final_life={str(h): int(p.life) for h, p in world.players.items()},
        final_zone=final_zone,
        identity_name=identity_name,
        layers_rows=[tuple(r) for r in game.executor.layers.dump()],
        repl_rows=[tuple(r) for r in game.executor.replacements.dump()],
        binder_dump=binder,
        crashed=crashed,
    )


def load_catalog() -> dict[str, ReplayData]:
    """Catalog rows are [sha16, 'kind|subject|cause|verb'] — payload-free.
    Detectors see data=None and emit their EXEMPT notes; the pass still
    inventories the kind mix per seed."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    out: dict[str, ReplayData] = {}
    for seed, game in catalog["games"].items():
        rows = []
        for i, (_sha, label) in enumerate(game["entries"]):
            parts = label.split("|")
            kind = parts[0] if parts else "?"
            subject = parts[1] if len(parts) > 1 else "?"
            cause = parts[2] if len(parts) > 2 else "?"
            verb = parts[3] if len(parts) > 3 else "?"
            rows.append(Row(i, i, kind, subject, cause, verb, None))
        out[seed] = ReplayData(seed=seed, rows=rows, crashed=game.get("crash"))
    return out


# --------------------------------------------------------------------------
# scanning


def scan(games: dict[str, ReplayData], mode: str) -> dict[str, Any]:
    per_seed: dict[str, Any] = {}
    for seed, g in sorted(games.items(), key=lambda kv: (len(kv[0]), kv[0])):
        verdicts = {}
        for detector in DETECTORS:
            verdict = detector(g)
            verdicts[verdict.detector] = verdict.json()
        kinds: dict[str, int] = {}
        for row in g.rows:
            kinds[row.kind] = kinds.get(row.kind, 0) + 1
        per_seed[seed] = {
            "mode": mode,
            "n_rows": len(g.rows),
            "crash": g.crashed,
            "kinds": kinds,
            "detectors": verdicts,
        }
    return per_seed


def summarize(per_seed: dict[str, Any]) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = {}
    hits: list[dict[str, Any]] = []
    for seed_report in per_seed.values():
        for name, verdict in seed_report["detectors"].items():
            bucket = totals.setdefault(name, {"clean": 0, "HIT": 0, "EXEMPT": 0})
            bucket[verdict["status"]] = bucket.get(verdict["status"], 0) + 1
            hits.extend(verdict.get("hits", []))
    return {"per_detector": totals, "all_hits": hits}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BUGCATCH B2 anomaly detectors")
    ap.add_argument("--seeds", type=int, default=20, help="replay-scan game count")
    ap.add_argument("--pool", default="all")
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--catalog-only", action="store_true")
    ap.add_argument("--replay-only", action="store_true")
    args = ap.parse_args(argv)

    payload: dict[str, Any] = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "design": "KNOWLEDGE/2026-10-02/12-bugcatch-design.md §D (B2)",
        "coverage_note": {
            "catalog_rows_lack": (
                "catalog.json per row = [sha16, kind|subject|cause|verb]; the "
                "data payload (damage amounts, was-PT assertions, zone names, "
                "counter kinds) is hashed away and layers/replacements/binder "
                "dumps are not captured — D1..D5 structurally infeasible there"
            ),
            "journal_rows_lack": (
                "no mana verbs (D2 stays exempt), no SET_PT/MODIFY_PT/GRANT "
                "rows (D5 fold sees counters only; unexplained diffs carry a "
                "benign-layer note), no counter-removal rows (D3 removal side "
                "exempt), no per-trigger fire counts (D6 drained = still-"
                "attached-or-pending at end, window bounded by game end)"
            ),
        },
    }
    if not args.replay_only:
        t0 = time.perf_counter()
        catalog_games = load_catalog()
        payload["catalog_scan"] = scan(catalog_games, "catalog")
        payload["catalog_summary"] = summarize(payload["catalog_scan"])
        print(
            f"catalog scan: {len(catalog_games)} seeds "
            f"[{time.perf_counter() - t0:.1f}s]"
        )
    if not args.catalog_only:
        games: dict[str, ReplayData] = {}
        for seed in range(args.seeds):
            t0 = time.perf_counter()
            games[str(seed)] = replay_game(
                seed, args.pool, args.deck_pairs_seed, args.turns
            )
            print(
                f"seed {seed}: {len(games[str(seed)].rows)} rows "
                f"[{time.perf_counter() - t0:.1f}s]"
                + (
                    f" CRASH {games[str(seed)].crashed}"
                    if games[str(seed)].crashed
                    else ""
                )
            )
        payload["replay_scan"] = scan(games, "replay")
        payload["replay_summary"] = summarize(payload["replay_scan"])
        payload["replay_meta"] = {
            "pool": args.pool,
            "seeds": args.seeds,
            "deck_pairs_seed": args.deck_pairs_seed,
            "turn_cap": args.turns,
        }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    n_hits = sum(
        len(payload[key]["all_hits"])
        for key in ("catalog_summary", "replay_summary")
        if key in payload
    )
    print(f"wrote {out} ({n_hits} hits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
