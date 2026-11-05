"""Per-card records: trees mapped by agents, and play-time verification, kept as data.

docs/PLAN_CARD_ONBOARDING.md. One JSON file per card, ``MTG_bot/data/cards/<SET>/<oracle_id>.json``::

    {"schema": 1, "set": "M19", "oracle_id": "...", "name": "...",
     "text_sha": "<sha256 of the printed facts the tree was mapped from>",
     "ir": {"keywords": [...], "abilities": [...]},      # absent: the compiler's tree stands
     "verified": {"tree_sha": "<tree_sha of the card that passed>", ...}}   # absent: unverified

- ``ir`` replaces the compiler's keywords and abilities for that card, after the compiler's own
  canonicalising passes. Printed facts (name, cost, types, P/T, loyalty, colours) always come from
  ingest, so a record cannot change them.
- ``text_sha`` pins the printed text the mapping was made from. A record whose card text changed
  since is stale and is not applied; the result's ``known_gaps`` says so.
- ``verified.tree_sha`` pins the exact tree that passed the gates. A record without ``ir`` verifies
  the compiler's tree. Any later change to the card's tree drops it out of the ``verified`` supply
  mode until it is verified again.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast, get_args

from MTG_bot.core.ability_tree import (
    Ability,
    BackFace,
    CardRecord,
    KeywordAbility,
    from_dict,
    to_dict,
)
from MTG_bot.core.compiler.compiler import (
    CompileResult,
    _engine_supported,
    _flip_search_picks_in,
    _promote_liftable_picks,
    _star_pt_gaps,
)
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.identity import LegalityFlags

SCHEMA = 1
RECORDS_DIR = Path(__file__).resolve().parents[2] / "data" / "cards"


def _sha(obj: Any) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def text_sha(raw: RawCard) -> str:
    """The printed facts a mapping reads: if any of them changes, the record is stale."""
    face = raw.back_face
    return _sha(
        {
            "name": raw.identity.name,
            "mana_cost": raw.mana_cost_raw,
            "type_line": raw.type_line,
            "pt": [raw.power_raw, raw.toughness_raw, raw.loyalty_raw],
            "keywords": list(raw.keywords),
            "sentences": list(raw.sentences),
            "back_face": None
            if face is None
            else {
                "name": face.name,
                "mana_cost": face.mana_cost_raw,
                "type_line": face.type_line,
                "pt": [face.power_raw, face.toughness_raw, face.loyalty_raw],
                "sentences": list(face.sentences),
            },
        }
    )


def tree_sha(card: CardRecord) -> str:
    """The card's mapped meaning: keywords, abilities and P/T, without the emblem (an emblem is its
    own pool entry with its own record)."""
    return _sha(
        {
            "keywords": [to_dict(k) for k in card.keywords],
            "abilities": [to_dict(a) for a in card.abilities],
            "power": to_dict(card.power),
            "toughness": to_dict(card.toughness),
        }
    )


def load_records(set_code: str, root: Path = RECORDS_DIR) -> dict[str, dict[str, Any]]:
    """Every record of one set, keyed by oracle id. Absent directory: no records (M21 today)."""
    folder = root / set_code
    out: dict[str, dict[str, Any]] = {}
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema") != SCHEMA:
            raise ValueError(f"{path}: schema {record.get('schema')!r}, expected {SCHEMA}")
        if record.get("oracle_id") != path.stem:
            raise ValueError(f"{path}: oracle_id {record.get('oracle_id')!r} != file name")
        out[path.stem] = record
    return out


def decode_ir(ir: Mapping[str, Any]) -> tuple[tuple[KeywordAbility, ...], tuple[Ability, ...]]:
    """Strict decode of a record's ``ir`` block (``from_dict`` validates every node)."""
    keywords = tuple(from_dict("KeywordAbility", d) for d in ir.get("keywords", ()))
    abilities: list[Ability] = []
    for d in ir["abilities"]:
        node = from_dict(str(d.get("tag")), d)
        if not isinstance(node, get_args(Ability)):
            raise TypeError(f"ir.abilities: {d.get('tag')!r} is not an ability")
        abilities.append(cast(Ability, node))
    return keywords, tuple(abilities)


def build_card(raw: RawCard, compiled: CardRecord, ir: Mapping[str, Any]) -> CardRecord:
    """The card with the record's tree in place of the compiler's, canonicalised exactly as
    :func:`compile_card` canonicalises its own (search picks, liftable picks)."""
    keywords, abilities = decode_ir(ir)
    flipped = [_flip_search_picks_in(ab) for ab in abilities]
    promoted = _promote_liftable_picks(flipped, raw.identity.name)
    faces = [ab for ab in promoted if isinstance(ab, BackFace)]
    if (raw.back_face is None) != (not faces) or len(faces) > 1:
        raise ValueError(
            f"{raw.identity.name}: a card with a back face carries exactly one BackFace, "
            f"others none (found {len(faces)})"
        )
    return replace(compiled, keywords=keywords, abilities=tuple(promoted))


def apply_record(
    raw: RawCard,
    result: CompileResult,
    record: Mapping[str, Any],
    supported_verbs: set[Any] | None,
    *,
    require_verified: bool,
) -> CompileResult:
    """``result`` with the record's tree in place, or ``result`` unchanged (with a known-gap note
    saying why) when the record is stale, unverified while verification is required, or its
    verified tree is no longer what it builds."""
    if "ir" not in record:
        return result
    if record.get("text_sha") != text_sha(raw):
        return replace(
            result,
            known_gaps=(*result.known_gaps, "card record stale: the printed text changed"),
        )
    verified = record.get("verified")
    if require_verified and not verified:
        return result
    card = build_card(raw, result.card, record["ir"])
    if require_verified and verified.get("tree_sha") != tree_sha(card):  # type: ignore[union-attr]
        return replace(
            result,
            known_gaps=(*result.known_gaps, "card record not applied: its verified tree changed"),
        )
    return CompileResult(
        card=card,
        legality=LegalityFlags(
            format_legal=True, engine_supported=_engine_supported(card, supported_verbs)
        ),
        rule_reminders=result.rule_reminders,
        known_gaps=tuple(_star_pt_gaps(raw, card)),
        record=tree_sha(card),
    )


def is_verified(result: CompileResult, record: Mapping[str, Any] | None) -> bool:
    """The card's current tree is the one a verification passed."""
    verified = (record or {}).get("verified")
    return bool(verified) and verified.get("tree_sha") == tree_sha(result.card)
