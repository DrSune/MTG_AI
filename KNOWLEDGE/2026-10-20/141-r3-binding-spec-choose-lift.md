# 141 — R3 BINDING SPEC: silent-CHOOSE blindness audit outcome — L-B ask-lift + census correction

Date: 2026-10-20. Round of docs/DESIGN_ATOM_ONTOLOGY.md §8 R3 / F2 freeze.
Evidence commit-resident (same commit): `reports/r3_blindness.md` + `reports/r3_blindness.json`
(full 193-node ledger, per-node executor rule cite + legal_chooser + card text). Gate
protocol: spec gate → implement (no git) → diff gate → one commit.

## 1. CENSUS CORRECTION (registers as FINDING)
§8/F2 said "174 cards". TRUE POPULATION: **193 nodes / 146 cards** (M21 145/104, ZNR 48/42;
+ Waker-emblem node via card-root walk) — "174" was CHOOSE-count inside the capped top-40
branching rows + nodes↔cards conflation. The V4′ baseline reproduces the ledger exactly
(`vs_v4_baseline_diffs: []`). Patch ontology §8 + F2 rows; NUMBERS row.

## 2. LANE ADJUDICATION (from ledger; every L-A claim carries executor cite)
L-A 161 (engine-forced: self-designation 108 selectors.py:896-910, referent-bound 48
:419-452, library-top 3 verbs.py:233-245, seat-singleton 2) — today PHANTOM decisions per
§10; **NOT fixed this round** (blast-radius separation): registered as divergence **D12**
+ scheduled round **R3b phantom-fold** (encode engine-resolved nodes as no-decision).
L-C 5 sacrifice-cost (Village Rites lane) — already ASKED via r22a 14b channel
(legality.py:1407-1440): no violation, unchanged.
L-B **27 nodes / 24 cards** — genuine choices resolved silently (BLINDNESS): first-n
effect 18 (selectors.py:575-579 `ordered[:count]`; incl. opponent-chooser subset Goremand
ab0, Liliana's Steward, Mind Rot, Necromentia, Run Afoul), discard-COST 8
(legality.py:801-830 `cands[:need]`), tap-COST 1 (legality.py:756-770, Shacklegeist).

## 3. SCOPE — the lift (verdict (ii): targeted, gold preserved)
(1) ASK WIRING at the three resolver sites ONLY, reusing existing channels (capability
    exists: r22a 14b ONE_OF k-of-n + NONE-stop; query.py:184 legal-set queries;
    `choose:<source>:<digest>` vocab site — no new ask primitive): sequential-pick
    1..k + STOP shape; menu = LIVE LEGALITY LIST, count clamped by availability
    (menu-visibility law: full axes exposed, same vocabulary statically↔dynamically).
    IR ENCODING UNCHANGED ⇒ **compiled bytes Δ0 both pools** (measured pre/post).
(2) OPPONENT-SEAT ROUTING: the 5 opponent-chooser cards MUST present the ask to the
    choosing seat, not the controller. Executor-observed battery: for all 24 L-B cards —
    ask fires, menu == legal set, STOP/NONE path preserves engine-equivalent outcome;
    per-card recorded (falsifier law: observe the executor, not the code).
(3) V4′ FREEZE LIFT POLICY (fail-closed kept): checker learns a LIFT LEDGER (per-node
    card+path+lane-rule entries produced only by set-integration tokenizer audits,
    printed every run like the whitelist); ships with ZERO entries — R2/R3 waves add no
    IR. Future L-A-SHAPED emissions remain unconditional ERROR; future CHOOSE emissions
    allowed only via ledger. Constructed probes: unlisted new CHOOSE node → FAIL;
    listed node → PASS.
(4) PACKS: ~50 scenario packs cover L-B cards (ledger has the map) — supply decisions for
    the new asks (STOP defaults where outcome-equivalent); replay/ask_log digest re-pins
    where multi-option CHOOSE asserted — identity-keyed, NO relaxation, per-assertion
    comment "R3 ask-lift". Fuzz decision-provider must handle new ask sites (surface
    loudly if it needs more than a default-STOP policy).
(5) L-A stays silent + frozen; D12 row + R3b scheduled; L-C untouched (deviation logged).
(6) Bug finding → ZND-7(a) (registered in /140 §4): merged-hand discard Bad Deal / Waker
    +1 (HAND:ANY no EachPlayer wrapper, verbs.py:156-200) — ENGINE LANE, not fixed here.

## 4. Pre-registered predictions (MEASURED; deviation = FINDING)
- Compiled IR bytes **Δ0** both pools (pre/post sortdelta-style measure); 0 golden churn.
- Ask battery: 24/24 L-B cards fire visible ask with full legal menu; 5/5 opponent-chooser
  asks land on the correct seat; NONE/STOP default == today's silent outcome where asserted.
- PC-1/PC-2/PC-6 anchors Δ0 (compile-side metrics; runtime asks cannot move them — verify);
  PC-4 goldens 0-diff (no re-bake expected); suite `MTG_bot/core tools` 0 fail;
  packs current-count 0-fail same-invocation (decision-supply wave inside); fuzz 40/40
  0 sigs; determinism double-run byte-identical; V4′ constructed probes (FAIL unlisted /
  PASS listed).
- If suite failures exceed the L-B pack surface: STOP + report (out-of-lane ask leakage).

## 5. NOT in scope
R3b phantom-fold (L-A 161 re-encode), ZND-7 bug, L-C changes, any new ask primitive,
ontology R4+ twins, sibling model/eval lanes.
