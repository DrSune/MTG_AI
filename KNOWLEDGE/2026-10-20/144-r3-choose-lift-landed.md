# 144 — R3 silent-CHOOSE ask-lift LANDED (executes /141 binding spec)

Date: 2026-10-20. Status: landed, uncommitted (owner commits). Supersedes nothing;
completes /141 phases 2–6 (phase 1 recorded in /143).

## What landed

**LIFT-NOW = 14 cards / 14 nodes** (ground truth `/tmp/opencode/r3_lift.json`,
from the committed ledger /143). All lifts are RUNTIME ask-surface only —
compiled IR bytes Δ0 both pools (plain-rehash shas M21 `52ae7619…`,
ZNR `e8965a74…`, gaps 0/1; snapshot `/tmp/opencode/r3_compiled_pre.json`).

Three wiring sites (all opt-in via `ask_choose=True`, default-off everywhere else):
1. `selectors.resolve_selector` — opt-in kwarg consumed only from effect-role
   lanes (`role_handles` non-cast branch, `verbs._search_designation`,
   MOVE_ZONE effect-pool call). QOneOf(QConst>1) folds that were silent become
   asks; k==1 sites carry no `{i}of{k}` segment (symmetric with frozen one_of
   single tag). Site: `choose:{source_ref}[:{i}of{k}]:{digest12}`.
2. `legality.build_payment_plan` — CostTap/CostDiscard record
   `tap_options`/`discard_options` at PLAN time, gated per cost, all-or-nothing.
3. `legality.pay_costs` — ask loops mirror the r22a sacrifice precedent.
   Sites `tap:{controller}:{source}:{digest}` / `discard:{controller}:{source}:{digest}`.

Gate `_choose_lift_allowed` (selectors.py, shared): referent / self-ref /
non-QConst / position-set zones / hidden-zone-not-owner / multi-zone ANY-wide /
player-handle (unit-world) source / chooser ≠ card controller / oracle-deferred
(`R3_CHOOSE_DEFERRED_ORACLES`) → silent. QUnbounded DEFERRED (ONE_OF lane
raises on them); opponent choosers + Run Afoul → ZND-9; Bad Deal + Waker +1 →
ZND-7(a). No +STOP promise for QConst (spec §6).

**Battery**: `MTG_bot/core/test_ontology_r3.py` — 17 tests, RED-first 6F/11P
pre-change (`/tmp/opencode/r3_red_prechange.log`), 17/17 green post.

**V4′ upgrade** (`ontology_conformance.py`): count-only census → per-node
shape-hash `sha256-16{node tag, holder field, container index-path, canonical
selector}`. Baseline v2 = 146 cards / 193 nodes, population-identical to the
frozen count law (old vs new census verified card-by-card). Deletions, tag/
filter swaps and duplicate-selector deletions all error, even at constant counts.
Probes 20/20 (`test_ontology_conformance.py`), incl. idx-path sensitivity.

## LOUD findings during verification

1. **V4′ first draft had a coverage hole (caught, fixed).** Single-level
   tuple/list field scan missed container-nested CHOOSE leaves (e.g.
   `AbilityEffect.args.pairs[i][1]`) → census saw 31/193 nodes = the freeze
   would have silently ignored 162 nodes. Caught by the ledger re-run
   (baseline format mismatch exposed it), fixed with recursive
   `_container_leaves` + index-path in the signature, baseline regenerated,
   population proven identical to the pre-upgrade census. Lesson: the
   checker PASSing against a self-regenerated baseline proves nothing —
   the ledger's independent 193-node walk is what caught it.
2. **Ledger generator needed a baseline-v2 compat fix** (`_bcnt`): rerun is
   byte-identical again (sha `4059273d…` preserved).
3. **Pack supply audit**: 13 packs / 17 asks of shape
   `choose:card:{i}:c2012070b279` = R3 fold of pack-encoded
   QOneOf(QConst(handle-list)) target prompts (real choices, §10 BLINDNESS
   intent). run_scenarios provider answers FIFO vocab-clamped → 428/428
   double-run byte-identical, zero pack rewrites needed. 0 tap:/discard:
   pack asks (no pack exercises a QConst tap-option cost; unit-covered only).
4. **Deviation vs spec count**: 14 lifts, not 15/17 — spec arithmetic
   double-counts Bad Deal + Waker +1 which its own exclusion removes; Run
   Afoul additionally deferred (opponent chooser, direction unencoded → ZND-9).
5. **Corpus re-anchor**: `test_executor_games` game re-anchored 50→30 turns
   (same loser; double-run verified; precedent 2026-10-08 re-anchor). Other
   drift fixes: dangling-referent + r19a lone-search got decision providers;
   test_executor_library stayed green via the player-handle-source gate.

## Gate scoreboard (all re-run after final edits)

| Gate | Result |
| --- | --- |
| `pytest MTG_bot/core tools -q --timeout=600` | 3120 + 66 games + 53 subtests, **0 fail** |
| R3 battery | 17/17 |
| Compiled-bytes Δ0 (both pools) | PROVEN (variant `plain` rehash) |
| Ledger rerun vs committed | BYTE-IDENTICAL |
| `ontology_conformance.py` | PASS errors=0 warns=7 rc=0 |
| Audit probes | 20/20 |
| `atom_field_table.py` | rc=0 |
| Packs `run_scenarios` | 428/428, double run byte-identical |
| Fuzz ZNR `--games 40` | 40/40, crashed=0, signatures=0, double-run outcome-identical |

## Up-to-N gap ledger (compile-as-QConst misses, unfixed, for R4/T4)

Cultivate / Rewind / Alpine Houndmaster / Ugin compile with QConst-exact
menus where the text implies up-to-N semantics (−10 compile surface); the
lifts shipped work at the compiled shapes. QUnbounded ONE_OF lane still
raises NotImplementedError → the deferred 7 stay silent until then.

## Files touched (this landing)

- `MTG_bot/core/executor/selectors.py`, `legality.py`, `verbs.py` (wiring)
- `MTG_bot/core/test_ontology_r3.py` (new battery)
- `tools/audit/ontology_conformance.py` (V4′), `…_v4_baseline.json` (v2 regen),
  `test_ontology_conformance.py` (probes), `r3_lane_ledger.py` (compat fix)
- Drift re-pins: `test_executor_games.py`, `test_executor_r19a.py`,
  `test_executor_dangling_referent.py` (dated R3 comments)
- Forbidden files untouched (run_scenarios.py, tools/training|eval,
  gameplay/engine_smoke reports).

---

## Diff-gate follow-up (2026-10-20, verdict FIX-THEN-GO — all fixes landed)

**FIX-1 (BREAK-R3-1, checker extinction blind spot).** `check_v4` iterated
CURRENT names only: whole-card CHOOSE extinction (rename/drop/last node
deleted ⇒ card leaves the census) passed silently and totals were never
compared. Now iterates base ∪ current (card-level `CHOOSE emission REMOVED`),
plus a per-name COUNT comparison so REMOVED is count-level, not name-level.
`sets=` param keeps CLI `--sets` partial runs from reporting un-compiled sets
as extinctions; `--write-v4-baseline` now refuses a partial census (baseline
clobber guard). RED-FIRST chain committed:
`artifacts/r3gate-v4-extinction-pre-fix.log` (5 failed / honest-passes 1)
→ `…post-fix.log` (26/26); full checker rc=0 and `--sets M21` rc=0.
New probes: card/set/count extinction + IR-level card-deleted,
last-node-deleted (mode swap CHOOSE→ALL), honest-recensus passes.

**LOUD FINDING (FIX-2 exposed a phantom).** The committed
`R3_CHOOSE_DEFERRED_ORACLES` entry `4c784905-2ed4-4f22-8387-d1c462125276`
matched NO compiled card in either pool — an inert phantom (source: R3
phase-3 authoring; matches neither the ledger nor M21.json identifiers).
Run Afoul's real oracle is `5462cb38-7cd7-46e8-a273-35d0d1af45b4`
(scryfallOracleId, ledger row + M21.json identifiers agree) — table FIXED to
it. Blast-radius audit: NO lane over-asked in practice — the run_afoul
scenario records 0 asks under BOTH UUIDs (the TARGET-bound lane short-circuits
before the ask-lift fold), packs 428/428 byte-identical, games lane green.
The hazard is now pinned in BOTH directions (`RunAfoulDeferralBehavior`:
tabled ⇒ silent ordered[:k]; table emptied ⇒ exactly 1 ask — i.e. the caster
would choose the opponent's sacrifice; the direction axis stays unencoded,
ZND-9, so the entry must not be deleted casually — a real fix encodes
direction, not a UUID removal).

**FIX-2 pins (`test_ontology_r3.py`, battery 17 → 22):**
`DeferredDeferralTable` — table == {Run Afoul real uuid}; uuid == compiled
M21 Run Afoul's pool key; every non-lifted L-B ledger row classifies into
exactly one defer reason: ZND-7(a) merged menu {Bad Deal, Liliana, Waker of
the Dead}, QUnbounded {Chandra Flame's Catalyst, Chandra Heart of Fire,
Necromentia, Siege Striker}, opponent-chooser/ZND-9 {Goremand, Liliana's
Steward, Mind Rot, Run Afoul}; only Run Afoul's oracle appears in the table
(the others defer on GATE rules, so table edits cannot silently reclassify).
`RunAfoulDeferralBehavior` — both behavior paths constructed (see above).

**FIX-3 records.** Δ0 repro command appended to NUMBERS.md (re-executed:
52ae7619…/e8965a74… re-printed exactly); evidence copied to
`KNOWLEDGE/2026-10-20/artifacts/` (red log, fuzz double-run, Δ0 snapshot,
FIX-1 red/green chain) with /143 pointed at them; orphan
`reports/znr_engine_smoke_2026-10-20.md` DELETED from reports/ (sibling-owned
pattern; copy kept at /tmp/opencode). NUMBERS wording on the ledger
generator line left as-is per instruction (generator lands with the commit).

Verification (this round): `pytest MTG_bot/core tools -q -k "r3 or ontology
or conform"` green (battery 22, checker probes 26); full conformance rc=0
both pools; games lane 66/66; packs 428/428 byte-identical re-run.
