# 09 — Hunt H5: EtB counter-fold suspect adjudication + cast-path EtBState fix

**Date:** 2026-10-05 · **HEAD at start:** 68f9c85 · **Batch:** H5 (engine editing authorized; compiler/goldens/state.py FROZEN)
**Suspect:** `tools/audit/suspects/malefic_scythe_x_wildwood_scourge.json` — claim: "counters visible in COUNTERS lane but absent from effective-P/T layer and combat."

## Verdict (double finding)

1. **Hunt premise WRONG (pack wrong, engine right).** Wildwood Scourge is printed **0/0** —
   corpus `MTG_bot/data/M21.json` (`"power":"0"`), frozen golden
   `MTG_bot/core/golden/M21/b9dec104-c636-4770-a7fc-7a3331face15.json` (`QConst(0)`), and
   Scryfall (M21 #214 / FDN #236 / CMM #332) all agree. The trigger-shaped EtB seed
   (`etb_x` ledger → ETB `PUT_COUNTER QX`) folds correctly: 0 + 1 counter = power 1.
   Observed "power 1 / deals 1" **is** the folded counter; the claimed 1/1→2/2 never existed.
   Same class as H3 row-3 (Gadrak/Houndmaster). Pack expectation corrected to `power:1,
   toughness:1` and **promoted** to `tools/scenarios/malefic_scythe_x_wildwood_scourge.json`
   (status/finding/notes stripped).
2. **REAL bug found underneath (fixed).** `_apply_etb_state` (via `_on_zone_changes` ENTER
   branch, CR 614.1c) was wired **only** to `play_land` (stack.py:848–854) and the execute
   lane — `cast()`/`cast_card()` never called `_on_zone_changes(entered)`. Casting any
   EtBState permanent stamped **none** of its entered state: Malefic Scythe's SOUL seed and
   the enters-tapped idiom both silently dropped on the cast path.

## Fix

- `MTG_bot/core/executor/stack.py`: in both `cast()` and `cast_card()`, capture
  `entered = executor.journal.record_atom(before_put, handle, "CAST", …)` and call
  `executor._on_zone_changes(entered)` before the aura effect / `_settle()` — mirrors
  `play_land`. state.py untouched (FROZEN respected).
- 6 pins in `MTG_bot/core/test_executor_stack.py::TestEtBSeedPTFold`: X-seed & EtBState-seed
  fold into `effective_pt`; tapped cast stamps; seeded+granted counters fold once (no double
  count — single `world.cards[c].counters` map confirmed, CR 613.3b/613.3d); X=0 enters &
  dies; counters layer stacks on static delta.

## Corpus impact

17 EtBState cards: 16 entered-tapped lands (play path, already hooked) + **Malefic Scythe**
(SOUL seed, cast-reachable) + **Forgotten Sentinel** (creature "enters tapped", cast path).
Catalog attribution: seed 3 diverged with ONE new `TAP_STATE` UNTAP_STEP row for
card:33=Forgotten Sentinel — previously cast untapped (the bug); now correctly tapped,
outcome unchanged, 284→285 entries. All other 9 seeds byte-identical.

## Gates (all green)

| gate | result | command |
| --- | --- | --- |
| packs | **339/339** (338 + promoted pack) | `.venv/bin/python tools/run_scenarios.py` |
| engine | **2360 passed + 3 subtests** (2354 + 6 pins) | `.venv/bin/python -m pytest MTG_bot/core -q` |
| grammar | **Δ0** vs 2026-10-04 (only PC-5 0.247→0.249 latency jitter; PC-6/8 FAILs pre-existing) | `.venv/bin/python tools/measure_grammar.py` |
| catalog | seed 3 attributed (Sentinel tapped-stamp) → **repin 3848 entries/10 games** → **0/10 diverge** | `tools/traces/catalog.py repin && … compare` |
| games | **0 crash classes**, 100 decisive 47/53, mean **33.48** t (band-identical) | `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` |
| lints | pyright **0 errors** 2 touched files; ruff **Δ0** | pyright CLI / `ruff check` |

## Side observations (out of scope, pre-existing)

- `_v_put_counter` has no n≤0 guard: X=0 writes a zero-valued `{PLUS_1_PLUS_1: 0}` key (cosmetic).
- Counters are not cleared when a card leaves the battlefield (pre-existing; X=0 Scourge dies
  and its counter map persists on the graveyard object).

No commits made (per instruction).
