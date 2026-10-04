"""BUGCATCH B4a — branch coverage over journal evidence (design §B + §E).

For each of the 97 branches declared in ``bcs.json`` this tool decides:

* LIT          — the branch's discriminating signature (journal_kind ×
                 data_predicate) matched on an attributable row in one of
                 the card's own green-pack journals or ANY corpus replay.
* DARK         — the signature is machine-checkable against the row dumps
                 and was never seen: the §E heat queue work order.
* UNMATCHABLE  — the signature references vocabulary the row dumps do not
                 carry (honest class, with WHAT is missing per branch):
                 - ``mode-choice``   — "data carries chosen mode index": no
                   documented GameEvent data layout carries a choice/mode
                   field (events.py §"data layouts"); choices are decided
                   in the decisions channel and never journalled.
                 - ``verb-tag``      — the predicate's verb has never
                   appeared as a row's ``cause_verb`` in ANY lane; the
                   journal is a world DIFF (zones / tapped / counters /
                   life / 12a damage tuples), so verbs that move none of
                   those (library shuffle, look-at, grants, PT edits,
                   mana, coin flips, counter REMOVALS — the diff emits
                   gained>0 only) have no vocabulary to match against.

Attribution law: a row can only light a branch if it is attributable to
the card — the card's handle is the row's subject, cause, or a handle
inside the data payload (pack lane: the pack's declared real-card
handles; corpus lane: the engine's own identity names). The one documented
exclusion: an effect CAST is journalled with subject = the CAST spell and
no source field (13b layout), so for verb-CAST branches a row whose
subject IS the card (the card's own casting) never counts as the
may-cast side having fired.

Heat (§E queue = the authoring work order): DARK branches sorted by
``BCS × (1 + len(collision_flags))`` (flag multiplier: each declared
collision class doubles down on suspicion, one point per flag).

Usage:  python tools/audit/branch_coverage.py [--seeds 20] [--out ...]
Emits tools/audit/branch_coverage.json. Never mutates any pack or engine.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "tools", REPO / "tools" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import detectors as D

BCS_JSON = Path(__file__).resolve().parent / "bcs.json"
M21_JSON = REPO / "MTG_bot" / "data" / "M21.json"
ANOMALIES_JSON = Path(__file__).resolve().parent / "anomalies.json"
OUT_DEFAULT = Path(__file__).resolve().parent / "branch_coverage.json"

MODE_PHRASE = "chosen mode index"
VERB_RE = re.compile(r"verb ([A-Z][A-Z_]+)")

# --------------------------------------------------- design §C collision classes
# The six verb-family collision classes of design §C, each of which "already has
# a real bug".  ``bcs.py`` records a class membership per CARD (``collision_flags``);
# heat consumes it as a weight, and pair_coverage.py consumes the class NAMES so
# classes with no flagged card at all are still enumerable.
#
# Weights are 1.0 across the board, deliberately: §C says every class has
# produced a real bug, so none is evidence-free, but nothing measured so far
# prices one class above another.  Inventing a magnitude hierarchy with no data
# behind it would put a fiction into the queue order.  The table exists so the
# weights can be re-priced from adjudication outcomes, and §E's
# ``interaction_heat`` enters at batch B (pair level), not here.
CLASS_WEIGHTS = {
    "pt_layers": 1.0,  # counter-fold x static grant: Basri's Solidarity, Trufflesnout
    "replacement_x_replacement": 1.0,  # Containment Priest x fiery damage rewrite
    "replacement_x_trigger": 1.0,  # self-dies law (22a)
    "grant_x_consumer_missing": 1.0,  # r20a dead-keyword: 5 packs green on the bug
    "sacrifice_x_dies_token_anthem": 1.0,  # Soldier-token controller bug, Treasure gap
    "x_census_x_name": 1.0,  # sanctum NAME_EQ family (C1)
    "branch_entanglement": 1.0,  # B1 signature class: Fabled Passage precedent
}
FLAG_TO_CLASS = {
    "single_fold": "pt_layers",
    "replacement_x_ordering": "replacement_x_trigger",
    "keyword_x_consumer": "grant_x_consumer_missing",
    "branch_entanglement": "branch_entanglement",
}
UNKNOWN_CLASS_WEIGHT = 1.0


def class_weight(flags: list[str]) -> float:
    """Sum of §C class weights a card's collision flags resolve to."""
    return sum(
        CLASS_WEIGHTS.get(FLAG_TO_CLASS.get(f, f), UNKNOWN_CLASS_WEIGHT) for f in flags
    )


def load_anomaly_hits(names: list[str]) -> dict[str, int]:
    """Per-card anomaly hits from anomalies.json (design §E's ``anomaly_hits``).

    A ``detectors.Hit`` is ``{detector, seed, class, detail, row_index, clock,
    subject}`` where ``subject`` is a HANDLE tag; the printed name appears in
    ``detail`` free text.  So attribution is handle-exact on ``subject`` with a
    name-in-detail fallback, never a substring scan of the whole file.
    """
    try:
        doc = json.loads(ANOMALIES_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    hits: list[dict[str, Any]] = []
    for key in ("catalog_summary", "replay_summary"):
        block = doc.get(key) or {}
        hits += [h for h in block.get("all_hits", []) if isinstance(h, dict)]
    if not hits:
        return {}

    bcs = json.loads(BCS_JSON.read_text(encoding="utf-8"))
    handle_of = {n: str(bcs["cards"][n].get("handle", "")) for n in names}
    out: dict[str, int] = {}
    for name in names:
        h = handle_of.get(name, "")
        out[name] = sum(
            1
            for hit in hits
            if (h and hit.get("subject") == h) or name in str(hit.get("detail", ""))
        )
    return {n: c for n, c in out.items() if c}


LIT = "LIT"
DARK = "DARK"
UNMATCHABLE = "UNMATCHABLE"


@dataclass
class Game:
    """One journal-bearing evidence run (same shape as b4_journal.Game)."""

    source: str
    rows: list[D.Row]
    handle_names: dict[str, str] = field(default_factory=dict)


@dataclass
class Verdict:
    status: str
    matched_by: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    missing: str = ""
    fanout_n: int = 0


# ------------------------------------------------------------------ helpers


def card_tags(game: Game, card: str) -> set[str]:
    """Handle tags in this game that carry the card's identity/name."""
    return {tag for tag, name in game.handle_names.items() if name == card}


def _handles_in(data: object) -> list[str]:
    """Stringified handles appearing anywhere (nested) in a data payload."""
    if data is None:
        return []
    if isinstance(data, (tuple, list)):
        out: list[str] = []
        for item in data:
            out.extend(_handles_in(item))
        return out
    tag = str(data)
    return [tag] if ":" in tag and not tag.startswith("<") else []


def attributed_tag(row: D.Row, tags: set[str]) -> str | None:
    """The card tag a row is attributable to (subject/cause/data spine)."""
    if row.subject in tags:
        return str(row.subject)
    if row.cause in tags:
        return str(row.cause)
    for tag in _handles_in(row.data):
        if tag in tags:
            return tag
    return None


def observed_cause_verbs(games: list[Game]) -> set[str]:
    return {row.verb for g in games for row in g.rows}


def _row_label(row: D.Row) -> str:
    return f"clock={row.clock} {row.kind} subj={row.subject} cause={row.cause} verb={row.verb}"


# ------------------------------------------------------------------ matcher


def match_branch(
    card: str, branch: dict[str, Any], games: list[Game], verbs: set[str]
) -> Verdict:
    """Apply the lit-rule to one declared branch over the evidence lanes."""
    sig = branch["signature"]
    pred = str(sig.get("data_predicate", ""))
    kinds = {k for k in str(sig.get("journal_kind", "NONE")).split("|") if k != "NONE"}
    verb_match = VERB_RE.search(pred)
    verb = verb_match.group(1) if verb_match else None

    # --- UNMATCHABLE vocabulary classes (checked BEFORE any matching).
    if MODE_PHRASE in pred:
        return Verdict(
            UNMATCHABLE,
            missing=(
                "chosen-mode index: no GameEvent data layout carries a "
                "choice/mode field (events.py documented layouts); the "
                "decision channel is not journalled"
            ),
        )
    if verb is not None and verb not in verbs:
        return Verdict(
            UNMATCHABLE,
            missing=(
                f"cause_verb tag {verb!r} appears in no row of any green "
                "pack or corpus replay — the diff-journal has no state "
                "vocabulary for this verb (no zone/tap/counter/life/"
                "damage delta it produces that is observable)"
            ),
        )

    kind = str(branch.get("kind", ""))
    matched_by: list[str] = []
    evidence: list[str] = []
    fanout = 0

    for game in games:
        tags = card_tags(game, card)
        if not tags:
            continue  # the card is not in this game — nothing to attribute

        # --- TARGETING cardinality lanes (one_of / rest selection).
        if "chosen-set cardinality" in pred:
            groups: dict[str, int] = {}
            for row in game.rows:
                if row.kind != "TARGETING" or row.cause not in tags:
                    continue
                groups[row.cause] = groups.get(row.cause, 0) + 1
            sizes = set(groups.values())
            want_one = "ONE_OF" in kind
            hit = (1 in sizes) if want_one else any(s >= 2 for s in sizes)
            if hit:
                matched_by.append(game.source)
                evidence.append(f"designation group size {sorted(sizes)} via {groups}")
            continue

        # --- CREATURE_DIES own-cause lane (the died-branch precedent).
        if "cause==own-handle" in pred:
            for row in game.rows:
                if (
                    row.kind == "CREATURE_DIES"
                    and row.cause in tags
                    and row.subject not in tags
                ):
                    matched_by.append(game.source)
                    evidence.append(_row_label(row))
                    break
            continue

        # --- generic verb-presence lane (may-accepted / condition fired).
        if verb is None:
            continue
        for row in game.rows:
            if row.verb != verb or (kinds and row.kind not in kinds):
                continue
            if attributed_tag(row, tags) is None:
                continue
            if verb == "CAST" and row.subject in tags:
                # 13b law: subject==card is the card's OWN casting; the
                # may-cast side needs a row whose subject is the cast OTHER.
                continue
            fanout += 1
            if game.source not in matched_by:
                matched_by.append(game.source)
                evidence.append(_row_label(row))
            break

    if matched_by:
        return Verdict(LIT, matched_by, evidence[:3], "", fanout)
    if (
        verb is None
        and "chosen-set cardinality" not in pred
        and "cause==own-handle" not in pred
    ):
        return Verdict(
            UNMATCHABLE, missing="no machine-readable row predicate in signature"
        )
    return Verdict(DARK)


# ------------------------------------------------------------------ rollup


def printed_text_lines(name: str) -> str:
    """First printed/rules text line from the set dump (best effort)."""
    try:
        data = json.loads(M21_JSON.read_text(encoding="utf-8"))["data"]
    except (OSError, KeyError, json.JSONDecodeError):
        return ""
    for c in data.get("cards", []) + data.get("tokens", []):
        if c.get("name") == name:
            text = str(c.get("text") or c.get("originalText") or "")
            return text.splitlines()[0] if text else ""
    return ""


def attach_heat(
    results: list[dict[str, Any]],
    bcs_of: dict[str, int],
    flags_of: dict[str, list[str]],
    hits_of: dict[str, int],
) -> list[dict[str, Any]]:
    """Design §E heat, written onto every DARK branch.  Returns the DARK rows.

    ``heat(branch) = dark x BCS x (1 + class weights) x (1 + anomaly_hits)``

    ``dark`` is the gate that makes the queue a work order rather than a
    leaderboard: a LIT branch scores 0, so the queue can never point at a
    branch already proven to fire.  The §E ``interaction_heat`` factor is a
    PAIR property and enters at batch B (``pair_coverage.py``) — a single
    branch has no interaction term to carry.
    """
    darks: list[dict[str, Any]] = []
    for r in results:
        if r["status"] != DARK:
            continue
        card = r["card"]
        flags = flags_of.get(card, [])
        bcs = bcs_of.get(card, 0)
        weight = class_weight(flags)
        hits = hits_of.get(card, 0)
        r["bcs"] = bcs
        r["collision_flags"] = flags
        r["classes"] = sorted({FLAG_TO_CLASS.get(f, f) for f in flags})
        r["class_weight"] = weight
        r["anomaly_hits"] = hits
        r["heat"] = round(1 * bcs * (1.0 + weight) * (1.0 + hits), 2)
        darks.append(r)
    return darks


def heat_queue(
    darks: list[dict[str, Any]],
    bcs_of: dict[str, int],
    limit: int = 25,
) -> list[dict[str, Any]]:
    """§E ranked work order, ordered by branch heat."""
    ranked = sorted(
        darks,
        key=lambda r: (
            -r["heat"],
            -bcs_of.get(r["card"], 0),
            r["card"],
            r["branch_id"],
        ),
    )
    top = ranked[:limit]
    for r in top:
        r["printed_text_line"] = printed_text_lines(r["card"])
    return top


def card_heat_rollup(
    darks: list[dict[str, Any]],
    per_card: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Card-level §E heat: ``dark_branch_count x mean(branch heat)``.

    Per-branch heat alone ranks a card with one DARK branch identically to a
    card with three at equal BCS; the rollup is what says "this card's whole
    rules surface is under-tested", which is the §E intent.
    """
    by_card: dict[str, list[float]] = {}
    for r in darks:
        by_card.setdefault(r["card"], []).append(float(r["heat"]))
    out: list[dict[str, Any]] = []
    for card, heats in by_card.items():
        meta = per_card.get(card, {})
        dark = int(meta.get("dark", len(heats)))
        out.append(
            {
                "card": card,
                "bcs": meta.get("bcs", 0),
                "dark": dark,
                "mean_branch_heat": round(sum(heats) / len(heats), 2),
                "heat": round(dark * (sum(heats) / len(heats)), 2),
                "collision_flags": meta.get("collision_flags", []),
            }
        )
    return sorted(out, key=lambda e: (-e["heat"], -e["bcs"], e["card"]))


def build_payload(
    games: list[Game], not_green: list[str], corpus_meta: dict[str, Any]
) -> dict[str, Any]:
    bcs = json.loads(BCS_JSON.read_text(encoding="utf-8"))
    verbs = observed_cause_verbs(games)
    hits_of = load_anomaly_hits(sorted(bcs["cards"]))

    results: list[dict[str, Any]] = []
    per_card: dict[str, Any] = {}
    bcs_of: dict[str, int] = {}
    flags_of: dict[str, list[str]] = {}

    for name, c in sorted(bcs["cards"].items()):
        branches = c.get("branches", [])
        if not branches:
            continue
        bcs_of[name] = int(c.get("bcs", 0))
        flags_of[name] = list(c.get("collision_flags", []))
        counts = {LIT: 0, DARK: 0, UNMATCHABLE: 0}
        for b in branches:
            v = match_branch(name, b, games, verbs)
            counts[v.status] += 1
            results.append(
                {
                    "branch_id": b["branch_id"],
                    "card": name,
                    "kind": b.get("kind"),
                    "journal_kind": b["signature"].get("journal_kind"),
                    "data_predicate": b["signature"].get("data_predicate"),
                    "status": v.status,
                    "matched_by": v.matched_by,
                    "evidence": v.evidence,
                    "missing": v.missing,
                    "fanout_n": v.fanout_n,
                }
            )
        declared = len(branches)
        per_card[name] = {
            "bcs": c.get("bcs", 0),
            "collision_flags": c.get("collision_flags", []),
            "in_pack": bool(c.get("in_pack")),
            "in_suspect": bool(c.get("in_suspect")),
            "declared": declared,
            "lit": counts[LIT],
            "dark": counts[DARK],
            "unmatchable": counts[UNMATCHABLE],
            "branch_coverage": round(counts[LIT] / declared, 3),
        }

    totals = {
        "branches_declared": len(results),
        LIT: sum(1 for r in results if r["status"] == LIT),
        DARK: sum(1 for r in results if r["status"] == DARK),
        UNMATCHABLE: sum(1 for r in results if r["status"] == UNMATCHABLE),
        "lit_in_pack_only": sum(
            1
            for r in results
            if r["status"] == LIT
            and all(m.startswith("pack:") for m in r["matched_by"])
        ),
        "lit_in_corpus_only": sum(
            1
            for r in results
            if r["status"] == LIT
            and all(m.startswith("corpus:") for m in r["matched_by"])
        ),
    }

    # -- §E heat: DARK gate, class weights, anomaly hits; branch + card levels.
    darks = attach_heat(results, bcs_of, flags_of, hits_of)
    queue = heat_queue(darks, bcs_of)
    rollup = card_heat_rollup(darks, per_card)
    for entry in rollup:
        per_card[entry["card"]]["heat"] = entry["heat"]

    # -- PC-11 over DISK membership, never bcs.json's historical flags.
    import membership as MEM

    pc11 = MEM.pc11(bcs, MEM.T_DEFAULT)

    # -- precedent sanity (design §B): recomputed, never asserted.
    by_id = {r["branch_id"]: r for r in results}
    fp = by_id.get("fabled_passage:01:Conditional")
    lgo_rows = any(
        r.kind == "LIFE_GAINED" and attributed_tag(r, card_tags(g, "Life Goes On"))
        for g in games
        for r in g.rows
    )
    sanity = {
        "fabled_passage_conditional": {
            "claim": "LIT since the 24a pins (design §B precedent)",
            "computed": fp["status"] if fp else "branch not declared",
            "matched_by": fp["matched_by"] if fp else [],
            "verdict": "OK" if fp and fp["status"] == LIT else "DIVERGED",
        },
        "life_goes_on_died_branch": {
            "claim": "died-branch LIT since wave 1 (design §B precedent)",
            "computed": (
                "bcs.json B1 inventory declares 0 branches for Life Goes On "
                "— precedent not recomputable at branch level; its died-side "
                "evidence (LIFE_GAINED attributed to it) is "
                + ("PRESENT in the lanes" if lgo_rows else "ABSENT")
            ),
            "verdict": "NOT-DECLARED"
            if not any(r["card"] == "Life Goes On" for r in results)
            else "CHECKED",
        },
    }

    return {
        "meta": {
            "built_by": "BUGCATCH batch B4a — tools/audit/branch_coverage.py",
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "command": "python tools/audit/branch_coverage.py",
            "design": "KNOWLEDGE/2026-10-02/12-bugcatch-design.md §B (lit-rule) + §E (heat)",
            "evidence_lanes": {
                "pack": {
                    "green_journals": sum(
                        1 for g in games if g.source.startswith("pack:")
                    ),
                    "not_green_skipped": not_green,
                    "law": "failing packs are skipped — a lane that cannot fail is not evidence",
                },
                "corpus": corpus_meta,
            },
            "observed_cause_verb_tags": sorted(verbs),
            "anomaly_hits": {
                "cards_with_hits": len(hits_of),
                "total_hits": sum(hits_of.values()),
                "note": "§E factor; inert today because anomalies.json "
                "all_hits is empty in both lanes (D1 landed in B3a). It is "
                "wired so the queue re-prices itself the moment a detector "
                "fires.",
            },
            "matcher_rules": {
                "attribution": "row lights a branch only if the card tag is the row's subject, cause, or in its data payload",
                "verb_presence": "row.verb == predicate verb AND kind in signature kinds (if any) AND attributable; verb-CAST rows exclude subject==the card itself (13b: subject==card is the card's own casting, not the may-cast side)",
                "cast_attribution_caveat": "13b's KIND_CAST row has no source-permanent field, so a branch that needs an effect to cast another card is not attributable from the explicit CAST row alone; positive may-cast control lanes must expose an attributable world-diff row or a new engine instrumentation contract before these DARK rows can become LIT",
                "targeting_cardinality": "TARGETING rows grouped by cause (designation source); ONE_OF branch lit by a group of size 1, REST branch lit by a group of size >= 2",
                "died_branch": "CREATURE_DIES row caused by the card (cause attributable, subject a different object)",
                "eachplayer": "lit by >=1 attributable fan-out row (fanout_n records the count; 2-player lanes mean each-opponent effects fan out to 1)",
                "unmatchable_classes": {
                    "mode-choice": MODE_PHRASE
                    + " predicate — choice data absent from every journalled data layout",
                    "verb-tag": "predicate verb never observed as any row's cause_verb (diff-journal cannot see that verb's effects)",
                },
            },
            "heat_formula": "§E-faithful, DARK-gated: heat(branch) = dark x BCS x "
            "(1 + sum of §C class weights) x (1 + card anomaly_hits from "
            "anomalies.json); card rollup = dark_branch_count x mean(branch "
            "heat); ties by BCS then name then branch_id. Class weights are "
            "uniform 1.0 by calibration (every §C class has produced a real "
            "bug, nothing yet prices one above another); interaction_heat is a "
            "pair factor and enters in pair_coverage.py",
            "class_weights": CLASS_WEIGHTS,
            "flag_to_class": FLAG_TO_CLASS,
        },
        "totals": totals,
        "pc11_membership": pc11,
        "sanity": sanity,
        "per_card": per_card,
        "branches": results,
        "heat_queue": queue,
        "heat_rollup": rollup,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BUGCATCH B4a branch coverage")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--pool", default="all")
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    import b4_journal  # deferred: engine-backed evidence lanes

    t0 = time.perf_counter()
    games, not_green = b4_journal.collect(
        args.seeds, args.pool, args.deck_pairs_seed, args.turns, quiet=args.quiet
    )
    payload = build_payload(
        games,
        not_green,
        {
            "pool": args.pool,
            "seeds": args.seeds,
            "deck_pairs_seed": args.deck_pairs_seed,
            "turn_cap": args.turns,
        },
    )
    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    t = payload["totals"]
    print(
        f"branches {t['branches_declared']}: LIT {t[LIT]} / DARK {t[DARK]} / "
        f"UNMATCHABLE {t[UNMATCHABLE]}  [{time.perf_counter() - t0:.0f}s]"
    )
    print(
        "sanity:", json.dumps({k: v["verdict"] for k, v in payload["sanity"].items()})
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
