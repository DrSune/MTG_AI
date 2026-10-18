# 96 — BLINDSPOT (a) CLOSED: back-face sentences enter the sentence census; ZNR PC-2 honest at 0.2534 (184/726)

Date: 2026-10-18. Closes blindspot (a) of /93 (measurement-only wave — the compiler
still does NOT compile faces; that stays gated behind /95's engine wave order).
Files touched: `coverage.py` (back-face sweep in `measure_pool` + OMIT-IF-EMPTY
`backface` report key + total-order `_unparsed_key` tiebreakers),
`test_coverage.py` (+4 `TestBackFaceCensus` tests), `tools/measure_grammar.py`
(2-line OMIT-IF-EMPTY `backface` passthrough in report assembly, mirrors `shape_gaps`).

## Semantics implemented (per /93 fix-order (a))
- PC-2 denominator = FRONT + BACK sentences. Every back-face sentence is an
  unparsed row BY CONSTRUCTION (compiler never reads `back_face`): register row
  `{oracle_id, name: "<card> [face B]", sentence, bucket_hint: "BFACE"}`, merged
  into `unparsed_queue` in total (oracle_id, sentence, name, bucket_hint) order.
- PC-1 formula untouched (front-face compile results only). `pool_stats` stays
  verbatim front-face (pinned 305/639/510 law intact). M21 (0 faces): report
  content byte-identical (verified vs `/tmp/opencode/grammar_m21_prechange.json`,
  timestamp + PC-5 latency exempt) and gains NO `backface` key.

## Numbers (commands: `.venv/bin/python tools/measure_grammar.py --set ZNR|M21`;
report copies `/tmp/opencode/grammar_ZNR_2026-10-18_bface.json`,
`grammar_m21_postchange.json`)
- ZNR sentence denominator **655 → 726** (+71 back-face sentences, 36 cards with faces).
- UNPARSED register **471 → 542** rows (71 BFACE). **PC-2 0.2809 → 0.253444**
  (184/726, now honest). PC-1 unchanged 0.1418 (40/282).
- BFACE shape histogram (71 rows / 8 distinct — face text is LOW-entropy, one
  `ADD_MANA`-style clause family + 2 land-entry shapes): "This land enters
  tapped." ×25 · "{T}: Add {C}." ×33 (W8 B8 G7 R6 U5) · "As this land enters,
  you may pay 3 life." ×5 + "If you don't, it enters tapped." ×5 (Cyclonic one
  shape-pair). ⇒ grammar round (b) for faces is ~8 shapes, cheap.
- M21 re-run exit 1 = the SAME pre-existing PC-6/PC-8 FAILs as before the change.

## Gates run (2026-10-18)
compiler suite **841 passed** (= 837 + 4 new; NOTE: suite was transiently red from
wiped `/tmp/opencode/phase1_buckets/` fixtures — regenerated via `tools/gen_buckets.py`,
no source touched) · M21 byte-ident ✅ · pyright 0 ✅ · ruff clean ✅.
