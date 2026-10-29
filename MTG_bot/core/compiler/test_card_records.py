"""Card records (docs/PLAN_CARD_ONBOARDING.md): a mapped tree replaces the compiler's only when it
is current and verified, printed facts never move, and a set without records is untouched."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import fingerprint, to_dict
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_card, compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.executor import games

DATA = Path(__file__).resolve().parents[2] / "data"
REGISTRY = build_full_registry()


@pytest.fixture(scope="module")
def fdn():
    return ingest_pool(DATA / "FDN.json")


def _oid(pool, name: str) -> str:
    return next(oid for oid, raw in pool.items() if raw.identity.name == name)


def _record(raw, card, *, verified: bool) -> dict:
    rec = {
        "schema": 1,
        "set": "FDN",
        "oracle_id": raw.identity.oracle_id,
        "name": raw.identity.name,
        "text_sha": card_records.text_sha(raw),
        "ir": {
            "keywords": [to_dict(k) for k in card.keywords],
            "abilities": [to_dict(a) for a in card.abilities],
        },
    }
    if verified:
        rec["verified"] = {"tree_sha": card_records.tree_sha(card)}
    return rec


def test_m21_has_no_records_and_compiles_byte_identically() -> None:
    assert card_records.load_records("M21") == {}
    raw = ingest_pool(DATA / "M21.json")
    plain = compile_pool(raw, REGISTRY)
    with_empty = compile_pool(raw, REGISTRY, records={})
    assert {o: fingerprint(c) for o, c in plain.cards.items()} == {
        o: fingerprint(c) for o, c in with_empty.cards.items()
    }
    assert all(r.record is None for r in with_empty.results.values())


def test_a_verified_record_replaces_the_tree_and_clears_the_unparsed_register(fdn) -> None:
    oid = next(o for o, r in fdn.items() if compile_card(r, REGISTRY).unparsed)
    raw = fdn[oid]
    compiled = compile_card(raw, REGISTRY)
    # The mapped tree here is the compiler's own partial tree: the point is the plumbing.
    rec = _record(raw, compiled.card, verified=True)
    out = compile_pool({oid: raw}, REGISTRY, records={oid: rec}).results[oid]
    assert out.record == card_records.tree_sha(out.card)
    assert out.unparsed == () and out.back_face_unparsed == ()
    assert card_records.is_verified(out, rec)
    # Printed facts come from ingest, never from the record.
    for field in ("name", "mana_cost", "type_line", "power", "toughness", "colors"):
        assert getattr(out.card, field) == getattr(compiled.card, field)


def test_stale_unverified_or_changed_records_are_not_applied(fdn) -> None:
    oid = next(o for o, r in fdn.items() if compile_card(r, REGISTRY).unparsed)
    raw = fdn[oid]
    compiled = compile_card(raw, REGISTRY)

    unverified = _record(raw, compiled.card, verified=False)
    out = compile_pool({oid: raw}, REGISTRY, records={oid: unverified}).results[oid]
    assert out.record is None and out.unparsed == compiled.unparsed
    # The tooling path applies unverified trees on purpose (to probe them).
    out = compile_pool(
        {oid: raw}, REGISTRY, records={oid: unverified}, require_verified=False
    ).results[oid]
    assert out.record is not None and not card_records.is_verified(out, unverified)

    stale = dict(_record(raw, compiled.card, verified=True), text_sha="0" * 64)
    out = compile_pool({oid: raw}, REGISTRY, records={oid: stale}).results[oid]
    assert out.record is None
    assert any("stale" in g for g in out.known_gaps)

    changed = _record(raw, compiled.card, verified=True)
    changed["verified"] = {"tree_sha": "f" * 64}
    out = compile_pool({oid: raw}, REGISTRY, records={oid: changed}).results[oid]
    assert out.record is None
    assert any("verified tree changed" in g for g in out.known_gaps)


def test_a_record_cannot_change_printed_facts_or_drop_a_back_face(fdn) -> None:
    oid = next(o for o, r in fdn.items() if compile_card(r, REGISTRY).unparsed)
    raw = fdn[oid]
    rec = _record(raw, compile_card(raw, REGISTRY).card, verified=False)
    card = card_records.build_card(raw, compile_card(raw, REGISTRY).card, rec["ir"])
    assert card.mana_cost == compile_card(raw, REGISTRY).card.mana_cost
    # A single-faced card may not carry a BackFace node; ingest decides the faces.
    face = {"tag": "BackFace", "name": "X", "abilities": []}
    with pytest.raises(ValueError):
        card_records.build_card(
            raw, compile_card(raw, REGISTRY).card, {**rec["ir"], "abilities": [face]}
        )


def test_a_verified_record_rescues_a_card_the_compiler_refuses(fdn) -> None:
    oid = _oid(fdn, "Ravenous Amulet")
    raw = fdn[oid]
    with pytest.raises(StateCorruptionError):
        compile_card(raw, REGISTRY)
    with pytest.raises(StateCorruptionError):
        compile_pool({oid: raw}, REGISTRY)
    base = compile_card(replace(raw, sentences=(), back_face=None), REGISTRY).card
    rec = _record(raw, base, verified=True)
    out = compile_pool({oid: raw}, REGISTRY, records={oid: rec}).results[oid]
    assert out.record is not None
    # Unverified: the refusal stands.
    with pytest.raises(StateCorruptionError):
        compile_pool({oid: raw}, REGISTRY, records={oid: _record(raw, base, verified=False)})


def test_the_verified_supply_mode_deals_only_verified_trees(fdn, tmp_path, monkeypatch) -> None:
    oid = games.compile_supply("compiled", "FDN").deckable[0]
    raw = fdn[oid]
    folder = tmp_path / "FDN"
    folder.mkdir()
    rec = {"schema": 1, "set": "FDN", "oracle_id": oid, "name": raw.identity.name,
           "text_sha": card_records.text_sha(raw),
           "verified": {"tree_sha": card_records.tree_sha(compile_card(raw, REGISTRY).card)}}
    (folder / f"{oid}.json").write_text(json.dumps(rec))
    monkeypatch.setattr(games, "load_records", lambda code: card_records.load_records(code, tmp_path))
    supply = games.compile_supply("verified", "FDN")
    assert supply.verified_ids == {oid}
    assert supply.deckable == (oid,)
