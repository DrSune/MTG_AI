# 07 — HUNT H4: suspect fixes + `ONE_OF`/`REST` partition journaling (2026-10-05)

Working tree at HEAD `10d53c6`. No commits were made. This batch touched the
engine, scenario rig, audit matcher, catalog artifacts, and knowledge docs.

## Scope A — scenario damage lane and Gadrak adjudication

The Gadrak × Malefic Scythe pair failure was a rig-semantics gap, not a rules
failure. The runner's existing `expect["damage"]` lane reads the live executor
mark ledger, which `end_turn()` clears at end-of-turn cleanup. Gadrak's end-step
Treasure trigger proves the Brute survived combat, but the live ledger has
already reset.

Added an additive historical lane in `tools/run_scenarios.py`:

```json
"damage_received": {"brute": 3}
```

It sums historical `KIND_DAMAGE` journal rows whose `subject.namespace == "card"`.
The pack now asserts both:

```json
"damage": {},
"damage_received": {"brute": 3}
```

This keeps the live-ledger law intact while letting post-cleanup packs prove
historical damage.

## Scope B — suspect adjudications

### Basri Ket × Siege Striker — rig answer leakage, not engine

The suspect answered an undeclared Grog attack ask with the generic
`"decisions": ["grog"]` lane. The pack was fixed by declaring the attack
suppression explicitly and removing the generic decision:

- `"attack": {"striker": true, "grog": false}`
- no generic `"decisions": ["grog"]`

`tools/audit/suspects/basri_ket_x_siege_striker.json` is now `status: green`.

### Garruk's Harbinger — engine `_look` window fix

The accept-path failure was caused by `_look` overwriting an open `LOOK_AT`
window when a later anaphoric `REVEAL count=1` ran inside that window. The
narrow reveal collapsed the wider look population, which left `ONE_OF` with too
few candidates and made `REST` resolve as an empty complement.

The fix treats the post-look `REVEAL` as anaphoric to the prior wider look
window and preserves that wider window for partition population.
`tools/audit/suspects/garruk_s_harbinger_branch01.json` is now `status: green`.

### Malefic Scythe × Wildwood Scourge — remains a suspect

`tools/audit/suspects/malefic_scythe_x_wildwood_scourge.json` remains
`status: suspect` and red-as-intended. It pins the H3 observed bug: EtB-placed
`+1/+1` counters are visible to the counters lane but absent from effective P/T
and combat damage. This batch did not adjudicate or fix that P/T-layer bug.

## Scope C — `ONE_OF`/`REST` partition journaling

Before H4, partition choices had no journal evidence, so the branch matcher
could not honestly light `Selector:ONE_OF` or `Selector:REST` cardinality
lanes. H4 adds narrow audit rows without redefining them as CR target
designation.

Contract:

- `EventJournal.emit_targeting(..., cause_verb="TARGET")` remains the CR
  target-designation feed.
- Real applying partition selectors emit `TARGETING` rows with
  `cause_verb="ONE_OF"` or `cause_verb="REST"`.
- Those rows are audit-only. `TargetingEvent` triggers match only
  `cause_verb == "TARGET"`.
- Query/legality/count resolution must not journal partition choices.
  `resolve_selector` therefore defaults to `journal_partition=False`; only real
  partition-applying verbs pass `journal_partition=True`.

Real applying call sites updated:

- `MOVE_ZONE` partition moves.
- discard self-resolve partition branch.
- search designation partition path.

Branch matcher updated to group partition rows by `(row.cause, row.verb)` and
filter by the requested selector mode when `ONE_OF`/`REST` rows are present.
This preserves legacy `TARGET` fake-row pins while preventing a singleton
`REST` group from faking `ONE_OF`.

## Gate ledger

| Gate | Result |
|---|---|
| Scenario packs | **336/336 green** — `.venv/bin/python tools/run_scenarios.py --dir tools/scenarios` |
| Suspect packs | **2/3 green** — `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects`; Malefic Scythe × Wildwood Scourge is red-as-intended |
| Core suite | **2354 passed + 3 subtests** — `.venv/bin/python -m pytest MTG_bot/core -q --no-header -rf` |
| Audit suite | **62 passed** — `.venv/bin/python -m pytest tools/audit -q --no-header -rf` |
| Grammar | `.venv/bin/python tools/measure_grammar.py`: PC-1 `303/305`, PC-2 `637/639`, PC-3 `0`, PC-4 `0`, PC-5 `0.295 ms/card`, PC-9 stable, PC-10 pass; PC-6 and PC-8 are standing byte-identical FAILs; all measured PC values match the 2026-10-04 report except PC-5 timing noise |
| Catalog | `tools/traces/catalog.py compare` first showed 1 diverging seed (`seed 5`), then repinned and returned `0/10` diverging seeds |
| Games | **0 crash classes** over 100 decisive games, endings `47/53`, mean turns `33.52` — `.venv/bin/python -m MTG_bot.core.executor.games --seeds 100 --pool all --deck-pairs-seed 1409 --turns 60` |
| Branch coverage | **97 branches: 37 LIT / 13 DARK / 47 UNMATCHABLE** — `.venv/bin/python tools/audit/branch_coverage.py --quiet` |
| Pair coverage | **8577 candidate pairs: 2419 tested / 6158 untested**, `33` designed, no class with zero tested coverage — `.venv/bin/python tools/audit/pair_coverage.py --quiet` |
| Pyright | **0 new** on touched Python files; `run_scenarios.py` has six pre-existing `Counter` type errors present at HEAD |
| Ruff | **Δ0** on touched files; only pre-existing `tools/run_scenarios.py:723` `BLE001` remains in the touched set |

## Catalog attribution

The only trace divergence was seed 5:

- old: `ZONE_CHANGE` for a partition card move at entry 201, game journal length
  `225`
- new: inserted `TARGETING|...|ONE_OF` before that move, then `TARGETING|...|REST`
  rows for the complement, game journal length `230`
- outcome unchanged: `game over: player:0(life<=0)`

This is a pure audit-row insertion, not an outcome or decision divergence. The
catalog was repinned after that attribution, then compare returned clean.

## Branch coverage movement

Regenerating `tools/audit/branch_coverage.json` with the new scenario corpus and
partition evidence moved nine branches `DARK -> LIT`:

- `cultivate:01:Selector:REST`
- `cultivate:02:Selector:ONE_OF`
- `garruk_s_harbinger:01:Selector:REST`
- `garruk_s_harbinger:02:OptionalEffect`
- `garruk_s_harbinger:03:Selector:ONE_OF`
- `liliana_s_devotee:01:Conditional`
- `see_the_truth:02:Selector:REST`
- `see_the_truth:03:Selector:ONE_OF`
- `waker_of_waves:02:Selector:ONE_OF`

The totals moved from the stale committed instrument state **28 LIT / 22 DARK /
47 UNMATCHABLE** to **37 LIT / 13 DARK / 47 UNMATCHABLE**. The matcher still has
the same declared branch count, and the new partition evidence is mode-aware.

## Files touched

Engine:

- `MTG_bot/core/executor/events.py`
- `MTG_bot/core/executor/binding.py`
- `MTG_bot/core/executor/selectors.py`
- `MTG_bot/core/executor/verbs.py`

Rig/audit:

- `tools/run_scenarios.py`
- `tools/audit/branch_coverage.py`
- `tools/audit/test_branch_coverage.py`
- `MTG_bot/core/test_executor_h4.py`

Suspects and scenario artifacts:

- `tools/audit/suspects/basri_ket_x_siege_striker.json`
- `tools/audit/suspects/garruk_s_harbinger_branch01.json`
- `tools/traces/catalog.json`
- `tools/audit/branch_coverage.json`
- `tools/audit/pair_coverage.json`
- `reports/games_2026-10-04.json`
- `reports/grammar_2026-10-05.json`
