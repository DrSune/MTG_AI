# 17 — Round-17a: validation audit chain lands (real APIs), wave1 = ETB family

Date: 2026-09-30 · state: uncommitted (branch tip `e1795d6` + round-17a working tree)

## 0. Integrity correction (binding for future sessions)

ORCHESTRATOR REPAIR (same day, verified): the phantom "vision pipeline"
was NEVER referenced by the round-16 close-out or anywhere in this tree
(grep KNOWLEDGE/ docs/ = card names only: Llanowar Visionary, Double
Vision). Its source is a contaminated SUBAGENT SESSION MEMORY (a prior
agent session reported reading/writing `vision_audit.py`, `gold.py`,
`tich.py`, `engine_api.py` — none ever landed on disk: confabulated tool
output; treat any claim citing those paths as fiction). Lesson recorded
in PITFALLS: subagent briefings may carry phantom inheritance; rebuild
on verified APIs, and never attribute phantom content to knowledge docs.
The real infra is: `tools/make_replay.py` (real CLI: `--seed --pool
{all,engine,castable} --turns --out-dir --img-base`), `tools/fetch_card_images.py`
(Scryfall art → `MTG_bot/assets/card_images/<oracle_id>.jpg`, 321 files),
`tools/run_scenarios.py`, `tools/traces/catalog.py`, `games.compile_supply`.
The "card showed up in vision" selection filter is therefore replaced by the
honest one: **golden card + engine-supported + art asset on disk**.

## 1. What shipped (all new files, engine untouched this pass)

- `tools/audit/wave_builder.py` — derives `tools/audit/wave1.json` **from the
  golden-compiled IR** (`ingest_pool` + `build_full_registry` +
  `compile_pool`, the exact `compile_supply` chain; ETB =
  `TriggeredAbility` whose event is a `ZoneChangeEvent` with
  `to_zone == BATTLEFIELD`). Each row: oracle_id, mechanics (Atom verb names
  in the trigger effects), trigger count, subject-narrowed flag, gated
  `engine_supported`, art path + presence, printed text. `--lint`
  re-derives and byte-diffs vs the frozen file → golden drift turns lint red.
- `tools/audit/verify_wave.py` — three mandatory stages:
  1. **IR vs goldens**: recompiles and checks every wave row (trigger still
     present, engine support, oracle_id) → `IR_MISMATCH` fails exit 2.
  2. **Replay**: every pack in `tools/scenarios/` runs through the real
     `ScenarioRunner` (`run_pack`) — the pack `expect` block is the full
     assertion set; wave coverage + gap lists reported.
  3. **Game replay** (`--with-replay`): one seeded game through
     `games.play_game` (the harness `make_replay` drives), trace kept under
     `reports/audit/`, wave cards that actually reached the battlefield.
  `--emit-json` writes the machine-readable board (HTML renderer deferred).
- 5 new wave packs in `tools/scenarios/`, every assert from `M21.json`
  `originalText` fetched the same session:
  | pack | printed promise | asserted | verdict |
  |---|---|---|---|
  | radiant_fountain | "When this land enters, you gain 2 life." (no tap clause) | life 20→22, battlefield, **untapped** | PASS |
  | bloodfell_caves | "enters tapped" + gain 1 via **real land-drop** (`play` op) | life 21, tapped | PASS |
  | jungle_hollow | same text via `enter` op | life 21, tapped | PASS |
  | temple_epiphany | enters tapped + "scry 1", decision word `top` | tapped, library order preserved top-first, life 20 | PASS |
  | wall_of_runes | Defender + "When this creature enters, scry 1" | DEFENDER keyword lane, library preserved, untapped | PASS |

## 2. Measurements (2026-09-30, commands in NUMBERS.md)

- Family census: **66 cards** carry an ETB trigger; **66/66 engine-supported**
  (gated pass) and **66/66 with art** — wave1 = all 66.
- `verify_wave --replay --with-replay --seed 7`: IR 66/66 **0 mismatches**;
  packs **21/21** (7 wave packs run, 6 cards pack-covered, **60 gap cards**);
  seed-7 engine game: **29/66** wave cards live in the trace. exit 0.
- `make_replay --seed 7 --pool engine` → `reports/replays/replay_s7.html`
  (847 entries / 129 actions). Board: `reports/audit/grammar_2026-09-30_wave1.json`.
- ruff clean on `tools/audit/`; builder `--lint` OK.
- Pack evidence for the uncommitted 17a **EtBState entry hook**: tapped
  promises hold on BOTH entry paths (`play` and `enter`), and the no-tap-clause
  land stays untapped — the assertion direction is printed-text, not engine.

## 3. Next (17b+)

1. Close the 60-card pack gap in batches (printed-text facts re-fetched per
   card at authoring time; scry-`bottom` order shape and aura-static/counters
   PT oracles still need one empirical probe each before those asserts lock).
2. HTML board renderer over the emitted JSON.
3. PC + core gates were NOT re-run this pass (audit tools are additive; the
   engine diff is the earlier uncommitted 17a one — rerun `pytest MTG_bot/core -q`
   + `measure_grammar --with-engine-flags` before any commit).
