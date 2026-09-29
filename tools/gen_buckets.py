"""Regenerate the Phase-1 bucket JSON files from MTG_bot/data/M21.json.

Writes 8 files to /tmp/opencode/phase1_buckets/:

    B1.json    15 shape keys / 49 occurrences
    B2a.json   62 keys        B2b.json  62 keys   (B2 = trigger-shaped, 124 keys)
    B3.json    48 keys / 55 occurrences
    B4.json    47 keys / 63 occurrences
    B5a.json   90 keys        B5b.json  90 keys   B5c.json  90 keys  (B5 = 270)

Classification (reverse-engineered from the pinned template modules and
verified against every pinned constraint before this script was written):

  * shape key    = re.sub(r"\\d+", "N", sentence)
                   (braced digits {n} -> {N}, bare digits -> N; mana symbols,
                   X, {X} and card names are preserved)
  * B1           = keys whose concrete sentence fullmatches a
                   templates_b1 pattern (15)
  * B2a          = templates_b2a pattern matches (57 keys, 2026-09-26)
                     union the 5 pinned templates_b2a.UNCOVERED keys (62 total)
  * B2b          = trigger-shaped keys not in B2a (62)
                   trigger  = ^(When|Whenever|At (the )?(start|beginning))\\b
                   ("As ..." sentences are NOT triggers; they stay in B5)
  * B3           = templates_b3 pattern matches (45 keys, 2026-09-28)
                    union the 3 pinned templates_b3.UNCOVERED keys (48 total)
  * B4           = templates_b4 pattern matches (34 keys, 2026-09-28)
                     union the 13 pinned templates_b4.UNCOVERED keys (47 total)
  * B5           = every remaining key (270); B5a / B5b / B5c are the first /
                   middle / last thirds in plain alphabetical key order (90
                   each). B5a's concrete sentences must equal the 90-entry
                   SHAPES table in MTG_bot/core/compiler/test_templates_b5a.py.

Output format (one file per bucket):

    { "<shape key>": [["<card name>", "<concrete sentence>"], ...] }

Every constraint below is asserted; the script raises on any deviation.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.compiler import (
    templates_b1,
    templates_b2a,
    templates_b3,
    templates_b4,
)
from MTG_bot.core.compiler.ingest import ingest_pool, pool_stats
from MTG_bot.core.compiler.test_templates_b5a import SHAPES

POOL_PATH = REPO / "MTG_bot" / "data" / "M21.json"
OUT_DIR = Path("/tmp/opencode/phase1_buckets")

TRIGGER = re.compile(r"^(When|Whenever|At (the )?(start|beginning))\b")


def norm(sentence: str) -> str:
    """Normalize a concrete oracle sentence to its shape key."""
    return re.sub(r"\d+", "N", sentence)


def matched_keys(templates, occurrences: list[tuple[str, str]]) -> set[str]:
    """Shape keys of concrete sentences fullmatching any template pattern."""
    keys: set[str] = set()
    for _card, sentence in occurrences:
        for template in templates:
            if template.pattern.fullmatch(sentence):
                keys.add(norm(sentence))
                break
    return keys


def main() -> None:
    pool = ingest_pool(POOL_PATH)
    stats = pool_stats(pool)
    assert stats["sentence_total"] == 639, f"sentence_total={stats['sentence_total']}"
    assert stats["sentence_unique"] == 510, (
        f"sentence_unique={stats['sentence_unique']}"
    )

    # (card name, concrete sentence) occurrences, in pool order.
    occ: list[tuple[str, str]] = [
        (card.identity.name, s) for card in pool.values() for s in card.sentences
    ]
    all_keys = {norm(s) for _c, s in occ}
    assert len(all_keys) == 504, f"unique keys={len(all_keys)}"

    # Pinned template / uncovered membership.
    b1_keys = matched_keys(templates_b1.TEMPLATES, occ)
    b2a_keys = matched_keys(templates_b2a.TEMPLATES, occ)
    b3_keys = matched_keys(templates_b3.TEMPLATES, occ)
    b4_keys = matched_keys(templates_b4.TEMPLATES, occ)
    b2a_unc = {k for k, _r in templates_b2a.UNCOVERED}
    b3_unc = {k for k, _r in templates_b3.UNCOVERED}
    b4_unc = {k for k, _r in templates_b4.UNCOVERED}

    # Pinned counts are re-measured every time the template modules change
    # (these drift as templates land; see KNOWLEDGE entries for each bump).
    assert len(b1_keys) == 15, f"B1 pattern keys={len(b1_keys)}"
    assert len(b2a_keys) == 61, (
        f"B2a pattern keys={len(b2a_keys)}"
    )  # 2026-09-29 r10: Chrome Replicator same-name partition ETB landed
    # (doc 2026-09-29/02): keys 60->61, UNCOVERED prune 2->1, bucket 62.
    # 2026-09-29 r9-B: Pursued Whale per-opponent Pirate-token row landed
    # (C23, doc 2026-09-28/11): keys 59->60, UNCOVERED prune 3->2, bucket 62.
    # 2026-09-26: was 54 (2026-09-24); round-4 batch (6a267cd) added 3 b2a
    # patterns: keys 54->57 while its UNCOVERED prune 8->5 kept the bucket at 62.
    # 2026-09-28 r7-batch: Kinetic Augur "that many" draw + Idol of Endurance
    # graveyard exile landed: keys 57->59, UNCOVERED prune 5->3, bucket 62.
    assert len(b3_keys) == 48, (
        f"B3 pattern keys={len(b3_keys)}"
    )  # 2026-09-29 r9-B: Chromatic Orrery draw-per-distinct-color landed
    # (QDistinctColorCount): keys 47->48, UNCOVERED prune 1->0, bucket 48.
    # 2026-09-28 r6-batch: was 44 (2026-09-24); Subira's blocked-side
    # activation (R6-4) added 1 b3 pattern: keys 44->45 while its UNCOVERED
    # prune 4->3 kept the bucket at 48.
    # 2026-09-28 r7-batch: Brash Taunter FIGHT landed (R7-8 verb): keys
    # 45->46, UNCOVERED prune 3->2, bucket 48.
    # 2026-09-28 r8-C: Idol of Endurance IS_EXILED_WITH_SOURCE cast landed
    # (doc 2026-09-28/08): keys 46->47, UNCOVERED prune 2->1, bucket 48.
    assert len(b4_keys) == 46, (
        f"B4 pattern keys={len(b4_keys)}"
    )  # 2026-09-29 r9-B: Orrery ALL_YOURS MANA_POLICY + Teferi GRANT_ACTIVATION
    # + Enthralling targeting PREVENT landed (doc 2026-09-28/11): keys 43->46,
    # UNCOVERED prune 4->1, bucket 47.
    # 2026-09-28 r6-batch: was 30 (2026-09-26); round-6 batch added 4 b4
    # patterns: keys 30->34 while its UNCOVERED prune 17->13 kept the bucket at 47.
    # 2026-09-28 r7-batch: CHOOSE pool + protection-chosen-name + per-tapped
    # this-way + reveal-one-from-among landed: keys 34->38, UNCOVERED prune
    # 13->9, bucket 47.
    # 2026-09-28 r8-C: cast-them-this-turn + Radha pair + Furious Rise +
    # Azusa ADD_LAND_PLAY + Incinerator QThisTurn landed (doc 2026-09-28/08):
    # keys 38->43, UNCOVERED prune 9->4, bucket 47.
    assert b2a_keys & b2a_unc == set(), "B2a pattern/uncovered overlap"
    assert b3_keys & b3_unc == set(), "B3 pattern/uncovered overlap"
    assert b4_keys & b4_unc == set(), "B4 pattern/uncovered overlap"
    assert b2a_unc <= all_keys, "B2a UNCOVERED key missing from pool"
    assert b3_unc <= all_keys, "B3 UNCOVERED key missing from pool"
    assert b4_unc <= all_keys, "B4 UNCOVERED key missing from pool"

    b2a = b2a_keys | b2a_unc  # 62
    b3 = b3_keys | b3_unc  # 48
    b4 = b4_keys | b4_unc  # 47

    # Trigger-shaped keys form B2 (124); B2b is the non-pinned half (62).
    trigger_keys = {norm(s) for _c, s in occ if TRIGGER.match(s)}
    assert len(trigger_keys) == 124, f"B2 trigger keys={len(trigger_keys)}"
    b2b = trigger_keys - b2a
    assert len(b2b) == 62, f"B2b keys={len(b2b)}"
    assert b2a <= trigger_keys, "B2a contains non-trigger key"

    # Alphabetical half-split: B2a is the first 62 keys of sorted(B2).
    b2_sorted = sorted(b2a | b2b)
    assert b2_sorted[:62] == sorted(b2a), "B2a != first alphabetical half of B2"

    # B5 = everything else (270), split into alphabetical thirds of 90.
    b5 = all_keys - b1_keys - b2a - b2b - b3 - b4
    assert len(b5) == 270, f"B5 keys={len(b5)}"
    b5_sorted = sorted(b5)
    b5a_keys = set(b5_sorted[:90])
    b5b_keys = set(b5_sorted[90:180])
    b5c_keys = set(b5_sorted[180:270])

    # B5a cross-check: concrete sentences must equal the pinned SHAPES table.
    b5a_sents = {s for _c, s in occ if norm(s) in b5a_keys}
    shapes_sents = {s[0] for s in SHAPES}
    assert b5a_sents == shapes_sents, (
        f"B5a sentence mismatch: only-in-B5a={sorted(b5a_sents - shapes_sents)} "
        f"only-in-SHAPES={sorted(shapes_sents - b5a_sents)}"
    )

    # Per-bucket occurrence maps: key -> [[card, sentence], ...].
    buckets: dict[str, dict[str, list[list[str]]]] = {
        name: {} for name in ("B1", "B2a", "B2b", "B3", "B4", "B5a", "B5b", "B5c")
    }
    bucket_of_key: dict[str, str] = {}
    for k in b1_keys:
        bucket_of_key[k] = "B1"
    for k in b2a:
        bucket_of_key[k] = "B2a"
    for k in b2b:
        bucket_of_key[k] = "B2b"
    for k in b3:
        bucket_of_key[k] = "B3"
    for k in b4:
        bucket_of_key[k] = "B4"
    for k in b5a_keys:
        bucket_of_key[k] = "B5a"
    for k in b5b_keys:
        bucket_of_key[k] = "B5b"
    for k in b5c_keys:
        bucket_of_key[k] = "B5c"
    assert len(bucket_of_key) == 504, "bucket assignment is not a partition"

    for card, sentence in occ:
        key = norm(sentence)
        buckets[bucket_of_key[key]].setdefault(key, []).append([card, sentence])

    # Pinned counts (keys / occurrences).
    # 2026-09-29 r9-B batch (doc 2026-09-28/11 §9-B): 12 sentences landed via
    # b2a/b2b/b3/b4/b5a/b5b/b5c templates; bucket membership never moves
    # (pattern<->UNCOVERED pruning only), so all 8 JSONs regenerate
    # byte-identical (cmp-verified) with the three pattern pins above moved.
    # 2026-09-28 r7-B batch (docs/KNOWLEDGE 2026-09-28/07): 11 templates landed
    # in templates_b2b/_b5b/_b5c; NONE of these modules feeds this partition
    # (B2b is derived trigger-minus-B2a; B5 thirds are coverage-independent), so
    # no pin changed and all 8 JSONs regenerate byte-identical (cmp-verified).
    expected_keys = {
        "B1": 15,
        "B2a": 62,
        "B2b": 62,
        "B3": 48,
        "B4": 47,
        "B5a": 90,
        "B5b": 90,
        "B5c": 90,
    }
    expected_occ = {"B1": 49, "B3": 55, "B4": 63}
    for name, data in buckets.items():
        got_keys = len(data)
        assert got_keys == expected_keys[name], f"{name}: keys={got_keys}"
        got_occ = sum(len(v) for v in data.values())
        if name in expected_occ:
            assert got_occ == expected_occ[name], f"{name}: occ={got_occ}"

    total_occ = sum(sum(len(v) for v in d.values()) for d in buckets.values())
    assert total_occ == 639, f"total occ={total_occ}"

    # Every templates_b2a pattern fullmatches at least one B2a sentence (54/54).
    b2a_sents = {s for _c, s in occ if norm(s) in b2a}
    for template in templates_b2a.TEMPLATES:
        assert any(template.pattern.fullmatch(s) for s in b2a_sents), (
            f"uncovered B2a pattern: {template.pattern.pattern!r}"
        )

    # Deterministic output: sorted keys, sorted [card, sentence] entries.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in buckets.items():
        payload = {key: sorted(entries) for key, entries in sorted(data.items())}
        path = OUT_DIR / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        n_occ = sum(len(v) for v in payload.values())
        print(f"{name}: {len(payload)} keys / {n_occ} occurrences -> {path}")

    print("OK: all 8 bucket files regenerated; all pinned constraints hold.")


if __name__ == "__main__":
    main()
