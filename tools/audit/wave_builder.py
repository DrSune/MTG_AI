#!/usr/bin/env python3
"""Wave target maps: golden-compiled IR cohorts (wave 1 = ETB, 17a; wave 2 = SPELL-resolution).

There is no vision model in this repo (the round-16 close-out note's
"vision pipeline" never landed — verified 2026-09-30). The audited
universe is therefore exactly what the goldens are: the 305 M21 cards,
every one of which has real Scryfall art on disk
(``MTG_bot/assets/card_images/<oracle_id>.jpg``) — the old "cards that
showed up in vision" filter is here the honest filter "card with art
asset + engine-supported + has an ETB trigger".

The IR is NOT hand-written: every row is read out of the compiled
golden pool (:func:`ingest_pool` + :func:`build_full_registry` +
:func:`compile_pool` — the same chain ``games.compile_supply`` runs),
so ``wave1.json`` is a measurement, and ``--lint`` re-measures and
diffs against the frozen file: a golden edit that changes the ETB
family, the verb set, or engine support flips lint to red.

Wave 2 (loop step 1, 2026-10-01) is the SPELL-resolution cohort: every
non-token card whose compiled IR carries a :class:`SpellAbility` node
(cast/resolve path). Same derive-from-IR rule as wave 1 — no hand-list —
and the same engine-supported gate: a spell card whose flag is False
because of unsupported atoms *inside* its effect is EXCLUDED until those
atoms are fixed (recorded in ``meta.excluded_by_flag`` with the verb
reasons). The two wave-1 cast-lane suspects (Capture Sphere, Wildwood
Scourge) carry NO SpellAbility node at all — that absence is the suspect
itself — so they are appended as explicit ``carry_over`` rows.

Wave 3 (loop step 1, 2026-10-01) is the STATIC/KEYWORD cohort: every
non-token card carrying a TOP-LEVEL :class:`StaticAbility` node in
``record.abilities`` or a :class:`KeywordAbility` node in
``record.keywords`` (the continuous-effect / keyword layer — never a
spell, trigger, or activation effect; statics *granted* by those lanes
are nested and already counted by waves 1-2). Same derive-from-IR rule
and gate; a static card whose flag is False is excluded with the
unsupported verbs its static nodes hit (``meta.excluded_by_flag``).
Because this wave targets cards NOT yet exercised, every card whose name
appears as a ``real`` entry in ``tools/scenarios/*.json`` (the 148 green
packs) or ``tools/audit/suspects/*.json`` is EXCLUDED by name; the count
lands in ``meta.excluded_count``. No carry-over semantics apply.

Wave 4 (loop step 1, 2026-10-01) is the MANA/ACTIVATED cohort: every
non-token card whose compiled IR carries an :class:`ActivatedAbility`
node anywhere (the "cost: effect" lane — tap abilities, mana abilities,
loyalty abilities, equip; verified 2026-10-01 the M21 goldens carry ZERO
cycling text, so the cycling lane has no corpus members). Same
derive-from-IR rule and gate as waves 2-3; exactly one card (Gadrak, the
Crown-Scourge) carries the node only INSIDE its TokenSpec (the token's
own ability) and is pack-covered by name anyway, so the row set is
identical under a top-level-only reading. Cards already exercised by a
pack or suspect are EXCLUDED by name (``meta.excluded_count``); gate
flags record the unsupported verbs inside the activated nodes.

Usage::

    .venv/bin/python tools/audit/wave_builder.py              # write wave1.json
    .venv/bin/python tools/audit/wave_builder.py --lint       # re-derive, diff
    .venv/bin/python tools/audit/wave_builder.py --wave2      # write wave2.json
    .venv/bin/python tools/audit/wave_builder.py --wave2 --lint
    .venv/bin/python tools/audit/wave_builder.py --wave3      # write wave3.json
    .venv/bin/python tools/audit/wave_builder.py --wave3 --lint
    .venv/bin/python tools/audit/wave_builder.py --wave4      # write wave4.json
    .venv/bin/python tools/audit/wave_builder.py --wave4 --lint
    .venv/bin/python tools/audit/wave_builder.py --coverage

Coverage census (2026-10-01): the corpus-level adjudication question —
does EVERY one of the 305 golden cards have a pack, a suspect, or at
least a documented family-less profile? Unlike the wave cohorts the
census excludes nothing (token and emblem records count as normal
cards), classifies each card pack / suspect / uncovered by name against
``tools/scenarios/*.json`` and ``tools/audit/suspects/*.json``, and
profiles every uncovered card with its full IR node-type signature so
the wave-5 question can be answered from ``coverage.json`` alone.

Closed waves: a frozen cohort whose every card has since been promoted
into ``tools/scenarios/*.json`` or ``tools/audit/suspects/*.json`` carries
``meta.status = "closed"``. Its ``--lint`` then PASSes iff every frozen row
is covered by name (the fresh derivation legitimately excludes consumed
cards by name, so byte-drift is expected, not failure); open waves keep
exact byte-identical lint.

Exit code 0 = wave file current (lint) / written (build).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    CostPart,
    KeywordAbility,
    SpellAbility,
    StaticAbility,
    TriggeredAbility,
    ZoneChangeEvent,
    walk,
)
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor import SUPPORTED_VERBS_V2

DATA = REPO / "MTG_bot" / "data" / "M21.json"
ASSETS = REPO / "MTG_bot" / "assets" / "card_images"
DEFAULT_OUT = Path(__file__).resolve().parent / "wave1.json"
DEFAULT_OUT2 = Path(__file__).resolve().parent / "wave2.json"
DEFAULT_OUT3 = Path(__file__).resolve().parent / "wave3.json"
DEFAULT_OUT4 = Path(__file__).resolve().parent / "wave4.json"
DEFAULT_COVERAGE = Path(__file__).resolve().parent / "coverage.json"

#: Wave-3 name-exclusion sources: every green scenario pack (148) and every
#: suspect file; a card counts as covered if its name appears as a ``real``
#: entry in any of them (subject or support role alike — it was exercised).
COVERED_GLOBS = ("tools/scenarios/*.json", "tools/audit/suspects/*.json")

#: Wave-1 cast-lane suspects: verified 2026-10-01 to carry NO SpellAbility
#: node in the compiled IR (their cast path is the machinery gap under
#: audit), so they never enter the natural cohort — appended as marked rows.
CARRY_OVER = ("Capture Sphere", "Wildwood Scourge")


def is_battlefield(zone) -> bool:
    """Zone-vs-BATTLEFIELD test that survives Zone-enum vs constant forms."""
    kind = getattr(zone, "kind", zone)
    name = getattr(kind, "name", kind)
    return str(name).endswith("BATTLEFIELD")


def etb_triggers(record) -> list[TriggeredAbility]:
    """The family map: TriggeredAbility whose EVENT is a zone change INTO
    the battlefield (the T8-audit-corrected structured event, never a
    substring)."""
    return [
        t
        for t in walk(record)
        if isinstance(t, TriggeredAbility)
        and isinstance(t.event, ZoneChangeEvent)
        and is_battlefield(t.event.to_zone)
    ]


def printed_texts() -> dict[str, str]:
    """oracle_id -> rules text (the raw Scryfall set file keeps the human
    text; make_replay.card_text_map is the same derivation)."""
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for card in raw["data"]["cards"]:
        oid = (card.get("identifiers") or {}).get("scryfallOracleId")
        if not oid:
            continue
        out.setdefault(oid, card.get("text") or card.get("originalText") or "")
    return out


def _compile_state() -> tuple:
    """The real compile chain, shared by every wave: ``ingest_pool`` +
    ``build_full_registry`` + ``compile_pool`` (untargeted and gated),
    exactly what ``games.compile_supply`` runs."""
    raw = ingest_pool(DATA)
    registry = build_full_registry()
    pool = compile_pool(raw, registry)
    gated = compile_pool(raw, registry, supported_verbs=set(SUPPORTED_VERBS_V2))
    return pool, gated, printed_texts()


def spell_abilities(record) -> list[SpellAbility]:
    """The wave-2 family map: the card's own cast/resolve effect nodes
    (SpellAbility), read out of the compiled record — never a substring."""
    return [n for n in walk(record) if isinstance(n, SpellAbility)]


def unsupported_verbs(record) -> list[str]:
    """Atom verb names on the whole card that the engine cannot execute —
    the honest reason a card fails the ``engine_supported`` gate."""
    return sorted(
        {
            node.verb.name
            for node in walk(record)
            if isinstance(node, Atom) and node.verb not in SUPPORTED_VERBS_V2
        }
    )


def _row(
    _record,
    oid: str,
    gated,
    texts: dict[str, str],
    *,
    verbs: list[str],
    n_spells: int,
    carry_over: bool,
) -> dict:
    """One frozen row — same core schema as wave 1 (oracle_id / mechanics
    verbs / gated engine support / art path / printed text), wave-2 fields
    named for what they count."""
    return {
        "oracle_id": oid,
        "mechanics": verbs,
        "n_spell_abilities": n_spells,
        "carry_over": carry_over,
        "engine_supported": bool(gated.results[oid].legality.engine_supported),
        "image": str(ASSETS / f"{oid}.jpg"),
        "has_image": (ASSETS / f"{oid}.jpg").exists(),
        "printed_text": texts.get(oid, ""),
    }


def derive_wave() -> dict:
    pool, gated, texts = _compile_state()
    cards: dict[str, dict] = {}
    for oid, res in pool.results.items():
        record = res.card
        if record.is_token or oid in pool.emblems:
            continue
        ets = etb_triggers(record)
        if not ets:
            continue
        verbs = sorted(
            {v.verb.name for t in ets for v in walk(t.effect) if isinstance(v, Atom)}
        )
        cards[record.name] = {
            "oracle_id": oid,
            "mechanics": verbs,
            "n_etb_triggers": len(ets),
            "subject_narrowed": any(
                getattr(t.event, "subject", None) is not None for t in ets
            ),
            "engine_supported": bool(gated.results[oid].legality.engine_supported),
            "image": str(ASSETS / f"{oid}.jpg"),
            "has_image": (ASSETS / f"{oid}.jpg").exists(),
            "printed_text": texts.get(oid, ""),
        }
    return {
        "meta": {
            "wave": "wave1",
            "family": "ETB (ZoneChangeEvent to BATTLEFIELD)",
            "source": "golden pool: ingest_pool + build_full_registry + compile_pool",
            "built_by": "tools/audit/wave_builder.py",
            "n_cards": len(cards),
        },
        "cards": dict(sorted(cards.items())),
    }


def derive_wave2() -> dict:
    """Wave 2 = engine-supported ∩ SpellAbility, plus the two cast-lane
    carry-over suspects. Spell cards excluded by the gate are recorded in
    ``meta.excluded_by_flag`` (name -> unsupported verb names) so the
    frozen file itself carries the honest exclusion evidence."""
    pool, gated, texts = _compile_state()
    cards: dict[str, dict] = {}
    excluded: dict[str, list[str]] = {}
    by_name: dict[str, str] = {}
    for oid, res in pool.results.items():
        record = res.card
        if record.is_token or oid in pool.emblems:
            continue
        by_name.setdefault(record.name, oid)
        spells = spell_abilities(record)
        if not spells:
            continue
        if not gated.results[oid].legality.engine_supported:
            excluded[record.name] = unsupported_verbs(record)
            continue
        verbs = sorted(
            {
                v.verb.name
                for s in spells
                if s.effect is not None
                for v in walk(s.effect)
                if isinstance(v, Atom)
            }
        )
        cards[record.name] = _row(
            record,
            oid,
            gated,
            texts,
            verbs=verbs,
            n_spells=len(spells),
            carry_over=False,
        )
    carry = 0
    for name in CARRY_OVER:
        if name in cards:  # honest: only append if the cohort missed it
            continue
        oid = by_name[name]
        cards[name] = _row(
            pool.results[oid].card,
            oid,
            gated,
            texts,
            verbs=[],
            n_spells=0,
            carry_over=True,
        )
        carry += 1
    return {
        "meta": {
            "wave": "wave2",
            "family": (
                "SPELL-resolution (SpellAbility nodes), "
                "engine-supported gate, cast-lane carry-overs appended"
            ),
            "source": "golden pool: ingest_pool + build_full_registry + compile_pool",
            "built_by": "tools/audit/wave_builder.py",
            "n_cards": len(cards),
            "n_gate_excluded": len(excluded),
            "n_carry_over": carry,
            "excluded_by_flag": dict(sorted(excluded.items())),
        },
        "cards": dict(sorted(cards.items())),
    }


def static_nodes(record) -> list:
    """The wave-3 family map: TOP-LEVEL static-layer nodes — StaticAbility
    (continuous effects) in ``abilities`` plus KeywordAbility (keywords) in
    ``keywords``. Nested statics (granted from spell/trigger lanes) are not
    counted here; they belong to the waves 1-2 cohort."""
    return [
        *[a for a in record.abilities if isinstance(a, StaticAbility)],
        *[k for k in record.keywords if isinstance(k, KeywordAbility)],
    ]


def static_unsupported_verbs(record) -> list[str]:
    """Atom verb names INSIDE the card's static nodes that the engine
    cannot execute — the honest flag reason for a wave-3 exclusion."""
    return sorted(
        {
            node.verb.name
            for a in static_nodes(record)
            for node in walk(a)
            if isinstance(node, Atom) and node.verb not in SUPPORTED_VERBS_V2
        }
    )


def static_mechanics(record) -> list[str]:
    """Wave-3 mechanics: atom verbs inside StaticAbility payloads UNION the
    keyword names of KeywordAbility nodes — the static layer's verb
    families, read out of the IR."""
    verbs = {
        node.verb.name
        for a in record.abilities
        if isinstance(a, StaticAbility)
        for node in walk(a.effect)
        if isinstance(node, Atom)
    }
    verbs |= {k.keyword.name for k in record.keywords if isinstance(k, KeywordAbility)}
    return sorted(verbs)


def _real_names_from(pattern: str) -> set[str]:
    """Names appearing as a ``real`` entry in every JSON file matching
    `pattern` (subject or support role alike — the card was exercised)."""
    names: set[str] = set()
    for path in sorted(REPO.glob(pattern)):
        board = json.loads(path.read_text(encoding="utf-8"))
        names |= {
            c["real"]
            for c in board.get("cards", [])
            if isinstance(c, dict) and "real" in c
        }
    return names


def pack_names() -> set[str]:
    """Names exercised as ``real`` entries in the green scenario packs."""
    return _real_names_from(COVERED_GLOBS[0])


def suspect_names() -> set[str]:
    """Names carried as ``real`` entries in the open suspect files."""
    return _real_names_from(COVERED_GLOBS[1])


def covered_names() -> set[str]:
    """Names exercised by existing material: every ``real`` card entry in
    every green scenario pack and every suspect file."""
    names: set[str] = set()
    for pattern in COVERED_GLOBS:
        names |= _real_names_from(pattern)
    return names


def derive_wave3() -> dict:
    """Wave 3 = static/keyword layer, engine-supported gate, minus every
    card already exercised by a green pack or suspect (excluded by NAME —
    ``meta.excluded_count``). Coverage arithmetic: n_static_cards =
    n_covered_excluded + n_gate_excluded + n_cards. No carry-over rows."""
    pool, gated, texts = _compile_state()
    covered = covered_names()
    cards: dict[str, dict] = {}
    excluded: dict[str, list[str]] = {}
    n_static_cards = 0
    n_covered = 0
    for oid, res in pool.results.items():
        record = res.card
        if record.is_token or oid in pool.emblems:
            continue
        statics = static_nodes(record)
        if not statics:
            continue
        n_static_cards += 1
        if not gated.results[oid].legality.engine_supported:
            reasons = static_unsupported_verbs(record)
            excluded[record.name] = reasons or unsupported_verbs(record)
            continue
        if record.name in covered:
            n_covered += 1
            continue
        cards[record.name] = {
            "oracle_id": oid,
            "mechanics": static_mechanics(record),
            "n_static_abilities": len(statics),
            "engine_supported": bool(gated.results[oid].legality.engine_supported),
            "image": str(ASSETS / f"{oid}.jpg"),
            "has_image": (ASSETS / f"{oid}.jpg").exists(),
            "printed_text": texts.get(oid, ""),
        }
    return {
        "meta": {
            "wave": "wave3",
            "family": (
                "STATIC/keyword layer (top-level StaticAbility + "
                "KeywordAbility nodes), engine-supported gate, "
                "pack/suspect-covered names excluded"
            ),
            "source": "golden pool: ingest_pool + build_full_registry + compile_pool",
            "built_by": "tools/audit/wave_builder.py",
            "n_static_cards": n_static_cards,
            "excluded_count": n_covered,
            "n_gate_excluded": len(excluded),
            "excluded_by_flag": dict(sorted(excluded.items())),
            "coverage": (
                f"{n_static_cards} static-family cards = {n_covered} already "
                f"covered (name) + {len(excluded)} gate-flagged + "
                f"{len(cards)} wave-3 cohort"
            ),
            "n_cards": len(cards),
        },
        "cards": dict(sorted(cards.items())),
    }


def activated_abilities(record) -> list[ActivatedAbility]:
    """The wave-4 family map: ActivatedAbility nodes ("cost: effect" —
    tap/mana/loyalty/equip lanes) read out of the compiled record via
    ``walk``, never a substring. Verified 2026-10-01: 93 of the 94 family
    cards carry theirs top-level; the sole nested one (Gadrak's TokenSpec)
    is pack-covered by name, so top-level-only would freeze the same rows."""
    return [n for n in walk(record) if isinstance(n, ActivatedAbility)]


def activated_unsupported_verbs(record) -> list[str]:
    """Atom verb names INSIDE the card's activated nodes that the engine
    cannot execute — the honest flag reason for a wave-4 exclusion."""
    return sorted(
        {
            node.verb.name
            for a in activated_abilities(record)
            for node in walk(a)
            if isinstance(node, Atom) and node.verb not in SUPPORTED_VERBS_V2
        }
    )


def activated_mechanics(record) -> list[str]:
    """Wave-4 mechanics: atom verbs inside the activated abilities' effect
    payloads — the cost:effect lane's verb families, read out of the IR."""
    return sorted(
        {
            node.verb.name
            for a in activated_abilities(record)
            for node in walk(a.effect)
            if isinstance(node, Atom)
        }
    )


def derive_wave4() -> dict:
    """Wave 4 = mana/activated lane, engine-supported gate, minus every
    card already exercised by a green pack or suspect (excluded by NAME —
    ``meta.excluded_count``). Coverage arithmetic: n_activated_cards =
    n_covered_excluded + n_gate_excluded + n_cards. No carry-over rows."""
    pool, gated, texts = _compile_state()
    covered = covered_names()
    cards: dict[str, dict] = {}
    excluded: dict[str, list[str]] = {}
    n_activated_cards = 0
    n_covered = 0
    for oid, res in pool.results.items():
        record = res.card
        if record.is_token or oid in pool.emblems:
            continue
        acts = activated_abilities(record)
        if not acts:
            continue
        n_activated_cards += 1
        if not gated.results[oid].legality.engine_supported:
            reasons = activated_unsupported_verbs(record)
            excluded[record.name] = reasons or unsupported_verbs(record)
            continue
        if record.name in covered:
            n_covered += 1
            continue
        cards[record.name] = {
            "oracle_id": oid,
            "mechanics": activated_mechanics(record),
            "n_activated_abilities": len(acts),
            "engine_supported": bool(gated.results[oid].legality.engine_supported),
            "image": str(ASSETS / f"{oid}.jpg"),
            "has_image": (ASSETS / f"{oid}.jpg").exists(),
            "printed_text": texts.get(oid, ""),
        }
    return {
        "meta": {
            "wave": "wave4",
            "family": (
                "MANA/ACTIVATED (cost:effect — ActivatedAbility nodes: "
                "tap/mana/loyalty/equip lanes; M21 goldens carry zero "
                "cycling text), engine-supported gate, "
                "pack/suspect-covered names excluded"
            ),
            "source": "golden pool: ingest_pool + build_full_registry + compile_pool",
            "built_by": "tools/audit/wave_builder.py",
            "n_activated_cards": n_activated_cards,
            "excluded_count": n_covered,
            "n_gate_excluded": len(excluded),
            "excluded_by_flag": dict(sorted(excluded.items())),
            "coverage": (
                f"{n_activated_cards} activated-family cards = {n_covered} "
                f"already covered (name) + {len(excluded)} gate-flagged + "
                f"{len(cards)} wave-4 cohort"
            ),
            "n_cards": len(cards),
        },
        "cards": dict(sorted(cards.items())),
    }


def families_of(record) -> list[str]:
    """Which of the four audited families the card belongs to, decided by
    the waves' own node-detection helpers (never a substring): etb =
    :func:`etb_triggers`, spell = :func:`spell_abilities`, static =
    :func:`static_nodes`, activated = :func:`activated_abilities`."""
    fams: list[str] = []
    if etb_triggers(record):
        fams.append("etb")
    if spell_abilities(record):
        fams.append("spell")
    if static_nodes(record):
        fams.append("static")
    if activated_abilities(record):
        fams.append("activated")
    return fams


def cost_node_classes(record) -> list[str]:
    """Cost-part class names (CostTap, CostManaColor, CostLoyalty, …)
    inside the card's own ability/keyword nodes — the activation-cost
    profile; the printed casting cost is profiled separately."""
    return sorted(
        {
            type(n).__name__
            for a in (*record.abilities, *record.keywords)
            for n in walk(a)
            if isinstance(n, CostPart)
        }
    )


def mana_cost_node_classes(record) -> list[str]:
    """Cost-part class names of the card's printed casting cost."""
    if record.mana_cost is None:
        return []
    return sorted(
        {type(n).__name__ for n in walk(record.mana_cost) if isinstance(n, CostPart)}
    )


def derive_coverage() -> dict:
    """Corpus adjudication census: does EVERY one of the 305 golden cards
    have a pack, a suspect, or at least a documented family-less profile?
    Unlike the wave cohorts this EXCLUDES NOTHING — token and emblem
    records count as normal cards (a name shared by a card and its token,
    e.g. "Cat", is censused per oracle_id). Status precedence pack >
    suspect; membership in both is recorded per card and counted in
    ``meta.n_pack_and_suspect``. Every UNCOVERED card carries its full IR
    node-type profile (top-level ability node classes, keyword names,
    activation cost nodes, casting-cost nodes) and its gated
    ``engine_supported`` flag — the evidence for whether a wave 5 family
    actually remains."""
    pool, gated, _texts = _compile_state()
    packs = pack_names()
    suspects = suspect_names()
    cards: dict[str, dict] = {}
    for oid, res in pool.results.items():
        record = res.card
        in_pack = record.name in packs
        in_suspect = record.name in suspects
        status = "pack" if in_pack else "suspect" if in_suspect else "uncovered"
        entry: dict = {
            "name": record.name,
            "families": families_of(record),
            "status": status,
            "in_pack": in_pack,
            "in_suspect": in_suspect,
            "engine_supported": bool(gated.results[oid].legality.engine_supported),
        }
        if status == "uncovered":
            entry["profile"] = {
                "ability_node_classes": sorted(
                    {type(a).__name__ for a in record.abilities}
                ),
                "keywords": sorted(
                    {
                        k.keyword.name
                        for k in record.keywords
                        if isinstance(k, KeywordAbility)
                    }
                ),
                "cost_nodes": cost_node_classes(record),
                "mana_cost_nodes": mana_cost_node_classes(record),
            }
        cards[oid] = entry

    uncovered = [c for c in cards.values() if c["status"] == "uncovered"]
    grouped: dict[str, list[str]] = {}
    for c in sorted(uncovered, key=lambda c: c["name"]):
        sig = " + ".join(c["profile"]["ability_node_classes"]) or "(no ability nodes)"
        grouped.setdefault(sig, []).append(c["name"])
    n_pack = sum(c["status"] == "pack" for c in cards.values())
    n_suspect = sum(c["status"] == "suspect" for c in cards.values())
    return {
        "meta": {
            "question": (
                "does every M21 card have a pack, a suspect, or a "
                "documented family-less status?"
            ),
            "source": "golden pool: ingest_pool + build_full_registry + compile_pool",
            "built_by": "tools/audit/wave_builder.py --coverage",
            "family_predicates": {
                "etb": "etb_triggers: TriggeredAbility w/ ZoneChangeEvent to BATTLEFIELD",
                "spell": "spell_abilities: SpellAbility nodes",
                "static": "static_nodes: top-level StaticAbility + KeywordAbility",
                "activated": "activated_abilities: ActivatedAbility nodes",
            },
            "status_precedence": "pack > suspect (both memberships kept per card)",
            "n_cards": len(cards),
            "n_pack": n_pack,
            "n_suspect": n_suspect,
            "n_uncovered": len(uncovered),
            "n_pack_and_suspect": sum(
                c["in_pack"] and c["in_suspect"] for c in cards.values()
            ),
            "n_uncovered_engine_supported": sum(
                c["engine_supported"] for c in uncovered
            ),
            "uncovered_grouped_by_top_level_nodes": {
                k: v for k, v in sorted(grouped.items())
            },
        },
        "cards": dict(sorted(cards.items())),
    }


def print_coverage(cov: dict) -> None:
    """Human summary of the census: counts, then every uncovered card
    grouped by its top-level node-class signature."""
    meta = cov["meta"]
    print(
        f"coverage: {meta['n_cards']} cards = {meta['n_pack']} pack + "
        f"{meta['n_suspect']} suspect + {meta['n_uncovered']} uncovered "
        f"({meta['n_pack_and_suspect']} names in pack AND suspect; "
        f"{meta['n_uncovered_engine_supported']} uncovered engine-supported)"
    )
    for sig, names in meta["uncovered_grouped_by_top_level_nodes"].items():
        print(f"  [{sig}] x{len(names)}: {', '.join(names)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--wave2", action="store_true", help="SPELL cohort instead of wave 1"
    )
    ap.add_argument(
        "--wave3", action="store_true", help="STATIC/keyword cohort instead of wave 1"
    )
    ap.add_argument(
        "--wave4", action="store_true", help="MANA/ACTIVATED cohort instead of wave 1"
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--lint", action="store_true", help="re-derive and diff vs disk")
    ap.add_argument(
        "--coverage",
        action="store_true",
        help=(
            "corpus adjudication census instead of a wave file: every golden "
            "card's pack/suspect/uncovered status, profiles for the uncovered"
        ),
    )
    args = ap.parse_args(argv)

    if args.coverage:
        out = Path(args.out) if args.out else DEFAULT_COVERAGE
        cov = derive_coverage()
        out.write_text(
            json.dumps(cov, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print_coverage(cov)
        print(f"wrote {out}")
        return 0

    if args.wave4:
        derive, default_out = derive_wave4, DEFAULT_OUT4
    elif args.wave3:
        derive, default_out = derive_wave3, DEFAULT_OUT3
    elif args.wave2:
        derive, default_out = derive_wave2, DEFAULT_OUT2
    else:
        derive, default_out = derive_wave, DEFAULT_OUT
    out = Path(args.out) if args.out else default_out
    wave = derive()
    text = json.dumps(wave, indent=2, sort_keys=True) + "\n"

    if args.lint:
        disk = out.read_text(encoding="utf-8")
        frozen = json.loads(disk)
        if frozen.get("meta", {}).get("status") == "closed":
            # Closed cohort: every frozen card was promoted into a pack or
            # suspect, so the fresh derivation legitimately excludes them by
            # name — byte-drift is expected. PASS iff every frozen row is now
            # covered by name in scenarios/ or suspects/.
            names = sorted(frozen["cards"])
            uncovered = [n for n in names if n not in covered_names()]
            if not uncovered:
                print(f"closed: {len(names)}/{len(names)} covered, consumed")
                return 0
            print(f"lint DRIFT (closed wave): uncovered={uncovered}")
            return 1
        if disk == text:
            print(f"lint OK: {wave['meta']['n_cards']} cards, IR current")
            return 0
        old = json.loads(disk)
        gone = set(old["cards"]) - set(wave["cards"])
        new = set(wave["cards"]) - set(old["cards"])
        changed = [
            n
            for n in set(old["cards"]) & set(wave["cards"])
            if old["cards"][n] != wave["cards"][n]
        ]
        print(
            f"lint DRIFT: dropped={sorted(gone)} added={sorted(new)} "
            f"changed={sorted(changed)}"
        )
        return 1

    out.write_text(text, encoding="utf-8")
    print(
        f"wrote {out}: {wave['meta']['n_cards']} {wave['meta']['wave']} cards "
        f"({sum(c['engine_supported'] for c in wave['cards'].values())} "
        f"engine-supported, {sum(c['has_image'] for c in wave['cards'].values())} "
        f"with art)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
