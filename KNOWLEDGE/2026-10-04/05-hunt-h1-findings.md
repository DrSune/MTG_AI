# 05 — HUNT H1: the 12 heat≥19 DARK branches adjudicated (2026-10-04, HEAD 88b1966)

Objective: force every heat-queue (B4b) DARK branch with heat ≥19; GREEN →
`tools/scenarios/<slug>_branch<NN>.json`, divergence → suspect →
`tools/audit/suspects/`, rig-impossible → falsification record here.
Result: **9 GREEN (14 packs incl. twins) · 1 SUSPECT · 2 FALSIFIED · 1 n/a-mapping**
— engine untouched, gates green.

## Per-branch verdicts

| Branch (heat) | Verdict | Pack / evidence |
| --- | --- | --- |
| `chandra_heart_of_fire:01` OptionalEffect (37) | **GREEN** | `chandra_heart_of_fire_branch01.json` + twin |
| `chandra_heart_of_fire:02` OptionalEffect (37) | **GREEN** | `chandra_heart_of_fire_branch02.json` + twin |
| `chandra_flame_s_catalyst:01` OptionalEffect (34) | **GREEN** | `chandra_flame_s_catalyst_branch01.json` + twin |
| `chandra_flame_s_catalyst:02` OptionalEffect (34) | **GREEN** | `chandra_flame_s_catalyst_branch02.json` + twin |
| `garruk_s_harbinger:01` Selector:REST (32) | **SUSPECT** | `suspects/garruk_s_harbinger_branch01.json` (red on the library lane, intended) |
| `garruk_s_harbinger:02` OptionalEffect (32) | **GREEN** | `garruk_s_harbinger_branch02.json` (decline twin = existing `garruks_harbinger.json`) |
| `garruk_s_harbinger:03` Selector:ONE_OF (32) | **GREEN** + OBS-2 | `garruk_s_harbinger_branch03.json` |
| `radha_heart_of_keld:01` OptionalEffect (32) | **FALSIFIED** | see F-1 |
| `demonic_embrace:01` OptionalEffect (29) | **FALSIFIED** | see F-2 |
| `liliana_s_devotee:01` Conditional (24) | **GREEN** | `liliana_s_devotee_branch01.json` + twin (tokens 1 ↔ 0) |
| `see_the_truth:02` Selector:REST (19) | **GREEN** + OBS-2 | `see_the_truth_branch02.json` |
| `see_the_truth:03` Selector:ONE_OF (19) | **GREEN** + OBS-2 | `see_the_truth_branch03.json` |

## Falsifications (no engine fault — rig/rule constraints, engine faithful)

* **F-1 Radha `:01`** — the land-play CAST selector compiles with
  `position: TOP` on LIBRARY (golden `927fb139`), and the rig's auto-fillers
  (`run_scenarios` `__init__` adds 6 "Library i" **Creatures per seat AFTER
  the cards loop**) are permanently on top: no setup can put a Land at
  library top, so `optional_offer` narrows to `("skip",)` and the fire-side
  branch is unforceable. Secondary: even a top land would hit
  `cast_card`'s SpellAbility raise (basic lands compile none) — the engine's
  own documented raise, not a divergence.
* **F-2 Demonic Embrace `:01`** — graveyard activation is refused by the
  r20c gate `legality.py:968-975` (`window:not_on_battlefield`) which is
  CR 602.3-faithful: only abilities whose **own cost discards their source**
  (cycling family) open a non-battlefield window; Demonic Embrace's cost is
  "lose 3 life, discard a card" — not itself. Engine correct; the branch is
  rig-unforceable.

## The one genuine divergence — Harbinger accept-path REST

Printed rest clause is **unconditional** ("Put the rest on the bottom of
your library in random order"). Decline path moves all four (green twin
proves REST works there); the ACCEPT path moves **nothing** — library stays
`[Library 4, 3, 2, 1, 0]` top-first (suspect lane expects `[L1, L0, *, *, *]`).
Suspected site: `MOVE_ZONE` REST after a consumed `OptionalEffect` resolves
against the pre-Optional partition. Executor frozen → collected.

## OBSERVABILITY notes (matcher blind spots, behavior is green)

* **OBS-1 decision lanes are silent**: `ExecCtx.take_decision` lane 1
  (`decisions=` pool) consumes a `("fire","skip")` offer WITHOUT calling the
  provider and without a journal row — packs witness fire/skip via world
  DIFF only. The Devotee twin proves the provider ask DOES happen when the
  word must fall through.
* **OBS-2 partition designations are never journalled TARGETING**
  (STT/Harbinger ONE_OF & REST picks), so the matcher's
  `targeting_cardinality` lane can never light these 4 branches even though
  they behave correctly. TARGET-mode designations DO journal
  (Catalyst `-2` TARGETING row). Consistent with B4a's "decision channel is
  not journalled" exclusion; the 4 selector branches need a journal feed
  (601.2c-style) to ever leave DARK.

## Rig laws discovered (→ PITFALLS)

1. Auto-filler law: 6 keyed-less "Library i" Creatures per seat are added
   AFTER declared cards — they own the library TOP forever; declared library
   cards sink below; draw pops the last DECLARED card at `begin_turn` time.
2. TARGET-mode selectors never ask a provider; designations arrive only via
   the activate/cast op `targets:` lane, and must be selector candidates.
3. Handle-shift trap: declaring one extra keyed card shifts every filler
   handle by +1 — decision words like `card:5` silently retarget.
4. `verbs._v_cast` passes NO target channel to `cast_card` (docstring pins
   it): effect-cast spells must be untargeted (we used Crash Through — draws
   exactly ONE card despite a doubled CARD_DRAWN journal row, count 1 then 2).
5. Suspect packs live in `tools/audit/suspects/` — `run_scenarios.py` globs
   only `tools/scenarios/`; suspects are verified standalone (red-as-intended).

## Gates (2026-10-04, this round)

* `.venv/bin/python tools/run_scenarios.py` → **327/327** (14 new; the
  working tree also carries the parallel `basri_ket_x_*` pair-matrix packs
  and `suspects/basri_ket_x_siege_striker.json` from the B4b authoring —
  all green/red-as-intended).
* `.venv/bin/pytest MTG_bot/core -q` → **2350 passed + 3 subtests, 0 failed**
  (unchanged; engine/goldens untouched — `git status` shows tools+knowledge
  only).
