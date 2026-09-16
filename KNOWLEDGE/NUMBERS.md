# NUMBERS — dated measurement log

Latest entry first. Every row: date, number, producing command, notes. A number must have all three
to be admissible (METRICS.md rail: the instrument must be reproducible).

---

## 2026-09-16 (session 6 — template bucket wave; session STOP at owner's request)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state at stop | **510 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | +144 vs session 5 (366): b1 (31), b3 (26), b4 (34), b5a (53) suites |
| bucket coverage at stop | B1 15/15 · B2a 45/45 decl.-covered (17 UNCOVERED) · B3 41/48 · B4 18/47 (29 UNCOVERED) · B5a 38 covered + 23 pre-consumed (29 UNCOVERED, in test docstring) | per-bucket parametrized tests + /tmp probe | 5 of 8 bucket modules landed; **B2b, B5b, B5c missing**; B2a test file missing |
| UNCOVERED shapes so far | **~62** (B2a 17 + B3 7 + B4 29 + B5a 29, dedup not yet applied across buckets) | `/tmp/opencode/phase1_buckets/UNCOVERED_ALL.md` | ranked families for the grammar-addition decision: see 2026-09-16/01-handoff-continuation.md §2 T3 |
| templates shipped | **135** (15 + 45 + 23 + 18 + 34) | grep `Template(` per module | PC-6 vocabulary health (orphan verbs) measurable once harness lands (T5) |

## 2026-09-15 (session 5 — ability_tree grammar review fixes: player referents, Quantity count, duration role)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state | **366 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | +8 vs session 4 (358): 7 new round-trip catalog entries (Selector-target-player, FAtom-CONTROLLER_IS-target-player, FAtom-CMC_LE-dynamic-count, Atom-TAP/UNTAP/MANDATE_ATTACK-duration, auto Zone-PLAYER) + 1 validation case (CONTROLLER_IS with ALL_OPPONENTS rejected) |
| pyright ability tree | **0 errors, 0 warnings** | `/home/sune/.local/bin/pyright MTG_bot/core/ability_tree.py MTG_bot/core/test_ability_tree.py` | IDE-LSP "Import pytest could not be resolved" is environmental (no venv context); CLI pyright resolves it — see 2026-09-15/03-grammar-review-fixes.md |

## 2026-09-15 (session 4 — compiler steps 2/3: template registry + card/pool compile)

| Number | Value | Command | Notes |
|---|---|---|---|
| core test state | **358 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | +70 vs session 3 (288): `templates.py`/`compiler.py` suites (template registry, mana-cost/P-T parsing, continuations, meta-filters, assembly, emblem attachment, engine-support, M21 smoke) |
| pyright compiler package | **0 errors, 0 warnings** | `/home/sune/.local/bin/pyright MTG_bot/core/compiler/compiler.py MTG_bot/core/compiler/templates.py MTG_bot/core/compiler/test_compiler.py MTG_bot/core/compiler/test_templates.py` | union narrowing via explicit `isinstance` helpers (see PITFALLS) |
| M21 emblem attachment | **3 emblems, 0 orphans, 3 attached** | `pytest MTG_bot/core -q` (`TestM21Smoke.test_emblems_attached`) | requires two-pass `compile_pool` (see PITFALLS) |
| M21 star P/T | Weird + Kinetic Augur → `star P/T` known gap, P/T stay `None`, no exception | same (`test_star_pt_cards_report_gap_not_exception`) | gap, not corruption |
| M21 summary consistency | total = **302** (305 − 3 emblems), fully+partially = total, unparsed > 0, known_gap ≥ 2 | same (`test_summary_consistency`) | compiled with empty registry, so unparsed = all text; this is the instrument's null-test baseline |

## 2026-09-15 (session 3 — ingest review fixes: split, validation, dedup)

### Re-measured M21 sentence baselines
| Number | Value | Command | Notes |
|---|---|---|---|
| file-level sentences | **927 total, 503 unique** | `python -m pytest MTG_bot/core -q` (`TestSmokeRealM21Pool.test_file_level_baselines`) | 397 card records, 391 with text; paren-depth-aware `split_sentences`; **supersedes** 952/509 |
| pool-level sentences | **639 total, 510 unique** | same (`TestSmokeRealM21Pool.test_pool_entries_and_keying`) | 305 oracle-keyed entries, 291 with text; **supersedes** 655/516 |
| delta from old flat split | **25 sentence boundaries** inside parentheses no longer split | inline probe comparing `re.compile(r'(?<=[.?!])\s+\|\n')` with `split_sentences` | 23 card records changed; 0 token records changed |
| affected card records | **23 of 397** | same | 5 Temple cards ×2 printings (5→4 each); Speaker of the Heavens ×2 (4→3); Discontinuity ×2 (5→3 each); Mazemind Tome ×2 (6→5); Opt, Riddleform, Spined Megalodon, Wall of Runes, Alchemist's Gift, Malefic Scythe, Short Sword ×1 each (−1 sentence) |
| emblems | **3** with owners | same | `56c1893f…fcdb`: Liliana, Waker of the Dead; `8a908da7…5d36`: Garruk, Unleashed; `ab67e4ec…5c1`: Basri Ket + Soldier |
| pool layouts | normal 285 / token 17 / emblem 3 | same | no record is both token and emblem |
| pool keywords / mana value | 24 distinct, **119 total** / 0:44, 1:30, 2:63, 3:68, 4:43, 5+:57 | same | unchanged by split/dedup fixes |
| core test state | **288 passed / 0 failed** (`MTG_bot/core`) | `python -m pytest MTG_bot/core -q` | includes new split, validation, dedup, emblem, and real-pool tests |

## 2026-09-15 (session 2 — compiler step 1: structured ingest)

### M21 pool reality: reprint duplicates (see 2026-09-15/01-ingest-dedup-decision.md)
| Number | Value | Command | Notes |
|---|---|---|---|
| duplicate oracle ids in card records | **112 of 397** (0 conflicting) | inline probe grouping `data.cards` by `scryfallOracleId`; pinned by `pytest MTG_bot/core/compiler -q` | every duplicate structurally identical, only `number`/`uuid` differ |
| oracle-id-keyed pool entries | **305** (285 cards + 20 tokens) | `ingest_pool` post-dedup; pinned by `TestSmokeRealM21Pool` | file still has 397+20 records; "the pool" as a key space is 305 |
| pool with text | **291** | same | |
| pool sentences | **655 total, 516 unique** | same | file-level was 952/509 over the 397 records; **superseded by session 3** (639/510 pool, 927/503 file) |
| pool layouts | normal 285 / token 17 / emblem 3 | same | |
| pool keywords | 24 distinct, **119 total** | `pool_stats` | file-level total was 166 (dupes counted twice) |
| pool mana value | 0:44, 1:30, 2:63, 3:68, 4:43, 5+:57 | `pool_stats` | |
| **correction**: no-text card records | 6, all **creatures** (Staunch Shieldmate, Wishcoin Crab, Walking Corpse, Onakke Ogre, Garruk's Gorehorn ×2) | inspect `text` field | **supersedes** 2026-09-14 "6 blank = basic lands" — basic lands here have reminder text `({T}: Add {W}.)` |
| core test state | **80 passed** (`MTG_bot/core`), 34 in `MTG_bot/core/compiler` | `pytest MTG_bot/core -q` | 46 pre-existing + 34 new ingest tests |

## 2026-09-14 (session 1, evening)

### Baseline test state
| Number | Value | Command | Notes |
|---|---|---|---|
| core (Phase 0) tests | **46 passed / 0 failed** | `pytest MTG_bot/core -q` | Phase 0 (identity/state/errors) green |
| full suite | **72 passed / 24 failed / 2 xfailed** | `pytest MTG_bot -q` | all 24 failures in legacy `rule_engine` (16) + `strategic_brain` (8); expected — legacy is attic'd at cutover, not fixed |
| failure cluster | 8 of 24 in rule_engine around zone/keyword bookkeeping (StopIteration, KeyError 'effects'/'zone_id') | same | confirms ARCHITECTURE.md verdict; do not chase in legacy code |

### Card pool (M21.json — the Phase 1 compilation target)
| Number | Value | Command | Notes |
|---|---|---|---|
| cards / tokens | **397 / 20** | `python3 -c json.load('MTG_bot/data/M21.json')['data']` | all 397+20 carry `identifiers.scryfallOracleId` |
| cards with oracle text | **391/397** (6 blank = basic lands) | inspect `text` field | field is **`text`**, NOT `oracleText` (see PITFALLS) |
| oracle sentences | **952 total, 509 unique, 486 unique shapes** (numbers→N, mana→C) | sentence split on `(?<=[.?!])\s+\|\n` | **superseded by 2026-09-15 session 3** for M21 sentence counts (927/503 under paren-depth-aware split); shape count not re-measured |
| trigger-shaped sentences | **189 total, 124 unique** (`When/Whenever/At start/As ~ enters`) | regex `^(When\|Whenever\|At (the )?(start\|beginning)\|As ~\|When ~ )` | |
| keywords | **24 distinct, 166 total** (Flying 28, Scry 19, Vigilance 12, Lifelink 12, Flash 11, Enchant 11, Trample 9, Prowess 8, Reach 8, Hexproof 7, Protection 6, Mill 5, Defender 4, Haste 4, Fight 4) | counter over `keywords` | |
| mana cost strings | **79 distinct**, incl. X costs (`{X}{R}{R}`, `{X}{G}`) | counter over `manaCost` | Quantity-as-expression is mandatory (DESIGN_CARD_POOL: no `*`, real expressions) |
| loyalty cards | 29 planeswalkers | counter over `loyalty` | loyalty = ability, not P/T |
| P/T cards | 194 | counter | |
| subtypes (top) | Human 49, Cleric 16, Wizard 13, Dog 12, Aura 11, Elemental 11, Teferi 10, Rogue 9 | counter over `subtypes` | Filter vocabulary must cover these |

### Phase 1 targets (pre-registered, see 02-phase1-plan.md)
PC-1 parse coverage ≥ 90% of pool cards fully compiled (stretch 95%) · PC-2 sentence coverage ≥ 95% ·
PC-3 ambiguity 0 · PC-4 golden stability 0 diffs · PC-5 compile p99 < 50 ms · PC-6 vocabulary health
(no orphan verb; no verb > 20% of atoms) · PC-7 executor: all top-25 frequent verbs have executors,
≥ 70% of cards fully executable · PC-8 targetable_card_fraction (EC-7): true value, expect big jump
from legacy 7/397 · PC-9 determinism: identical fingerprints across runs · PC-10 instrument null test.

### Environment
Python 3.12.3 (repo .venv), torch 2.14.0+cu130 importable, 20 cores, ~10 GB RAM headroom
(121 GB total, vLLM pool resident — keep 5-10 GB buffer; max 2 concurrent subagents, serialize below 5 GB).
