# 36 — T3 household fixes (2026-10-07, owner-approved batch from /34; no enum surgery)

Five items landed; T4 verb-ontology/atomics territory untouched. Gates after:
core **2453+2st** / packs **373/373** / tools audit+training **153**.

## ① Legality triad unified — ONE `count_semantics`, three lanes
`ability_tree.count_semantics(count, n_legal) -> (announceable, k)` is now the single
answer for the {menu/count} axis (owner §9: no atom may re-decide a shared axis):

| tag | announceable | k |
|---|---|---|
| QConst(N) | n ≥ N (CR 601.2c full-size law — clamping is WRONG) | N, never clamped |
| QAtMost(N) | n ≥ 1 (C17 designation ≥1; empty pop → 603.4 resolves doing nothing) | min(N, n) |
| QAtLeast(N) | n ≥ N | n |
| QUnbounded | always (EMPTY set legal) | n |
| unresolved (QX…) | **raise — flag, never guess** | |

Call sites, each keeping its documented LANE but not its own verdict:
- **binding.py trigger TARGET**: routes through the helper; a QConst that cannot
  complete designates NOTHING (`bindings["target"]=[]`, resolves doing nothing —
  603.4 sibling of the zero-candidate return). Old code walked the menu dry and
  would crash `take_decision(())` on an exhausted pool.
- **selectors.py ONE_OF**: resolve-time lane — helper computes k; the 608.2c
  mid-loop best-effort clamp stays documented (a QConst arriving short of
  population mid-effect resolves with what exists). The ANNOUNCE-time rejection
  is NOT this loop's job.
- **query.py**: announce-time lane. ONE_OF QConst(want>1) min=max=N past the
  population = INFEASIBLE (was `min(want,n)` clamp — the triad's third divergent
  reading); TARGET branch was already exact and now expresses it via the helper
  (values byte-identical); QX resolves to QConst then asks the helper. want==1
  ONE_OF lane untouched (frozen replay pins hold — episode md5s moved ONLY for
  the two intended pack fixes).

Tests: 21 new in `test_executor_kofn.py` — helper matrix (every tag ×
n_legal∈{0,1,k−1,k,k+1}), query slot both modes, binding designation lane via
real ETB triggers (over-1 QConst → silent nothing; over-2 exact → ask+autofill;
over-3 → 2 asks). Two stale pins re-grounded: empty-pop QConst(2) slot (0,0)→
(2,2)=infeasible; n=1 QConst(2) (1,1)→(2,2). Full core suite green = zero
fallout across 2400+ tests.

## ② Garruk emblem dead-ask ELIMINATED (honest gold, not demotion)
Verdict: the one_of pick HAS an observable consequence (WHICH creature hits the
battlefield), so §10 says script it honestly — demoting to silent would be
BLINDNESS. `garruk_unleashed_emblem.json`: end_turn decisions `["fire","pick"]`
→ `["fire","card:3"]` ("pick" was never in the partition vocab; the provider's
vocab[0] fallback answered card:1 and puzzle_cert recorded a gold:false
dead-ask row). The rig filler named by card:3 is "Library 2", pinned by a new
`battlefield_pt` lane `{"Library 2": [1,1]}`. Probed matrix: gold passes; null
word (vocab[0]="Library 0") FAILS the lane; skip fails lane+library; any of the
other 4 fillers fails → punish_inaction, ~1/6 random. Corpus item count 156→157
(the former dead row is now a scripted item). PRECISION: episodes carry 28
gold:false rows by DESIGN (engine-lane asks like ATTACK/DECLINE that packs
don't own — normal convention, 185 asks − 157 gold); the eliminated defect is
the SCRIPTED-WORD-MISMATCH dead row: emblem one_of now records gold:true
(card:3), and corpus no_discrimination=0 is the certifying evidence.

## ③ Fierce Empath offender FIXED by lane-strengthening (not fail-registered)
Root cause (probed): `ScenarioRunner.__init__` opens the clock with
`begin_turn(p0)` — its draw took the LAST pack card (Giant Six = old library
top) into hand **before any step ran**, so both fire and skip ended in the same
state (corpus why="expect-insensitive", no_discrimination=1). Fix in
`empath_big_game_pick.json`: pack card order [fe, c6, c2] puts Small Two
(cmc 2, NOT a legal search target) on top — the draw is now decision-INDEPENDENT;
lanes pin what the may decision controls: `zone{c6:hand, c2:hand}`, `hand{0:2}`.
Probed: fire passes; skip FAILS both lanes → punish_inaction. fail_registered
stays 11 (this is a real decision, not a true-no-decision). no_discrimination
**1 → 0**.

## ④ Stale compiler gap comment restated (comments only)
compiler.py `_KEYWORDS_BARE_UNBUILDABLE` note claimed SCRY/MILL/BATTALION
"need a Quantity; PROTECTION needs a Filter" — stale: the grammar carries all
four shapes (`Keyword.SCRY/_Q_CLASSES` etc., 10 Quantity forms, full
FAnd/FOr/FNot). The REAL gap is upstream: the identity keyword pipeline ships
bare strings with no number/filter and nothing feeds `_KEYWORD_PARAMS` for
them. Comment now says so; wiring identity→params is the fix, not atomics.

## ⑤ PT timestamp order CHARACTERIZED (no engine change)
Probe (EOT-duration, 2/2 print): `+1/+1 → SET_PT 3/3` ⇒ **3/3** (later SET
overwrites the folded delta); `SET_PT 3/3 → +1/+1` ⇒ **4/4**. The fold is PURE
TIMESTAMP order; real MTG splits set(613.3b)/modify(613.3c) into FIXED layers,
so a CR oracle says 4/4 for both orders — the engine is order-DEPENDENT.
Pinned as `test_current_pt_timestamp_behavior` (test_executor_verbs.py) so any
T4 layer-model move makes this a loud diff, not a silent one. Smell flagged:
this is exactly the kind of characterized order-dependence /34 asked to catch.

## Replay-pin deltas (all intended)
- puzzle_corpus.json: items 156→**157**, no_discrimination 1→**0**,
  punish_inaction 144→146, fail_registered 11 unchanged
  {true-no-decision 7, null-degenerate-observable 3, engine-semantics-gap 1},
  mean_random 0.3489→**0.3414**.
- episodes(_v2).jsonl: 114 eps / **185** asks (unchanged — the emblem one_of
  ask was already counted; it was the GOLD flag that moved) / gold_lines
  156→**157**; v2 gold_rows_with_ground=**79**, candidate_ground=229/474.
- test_bc_v2 pins: join 156→157; handle grounding (157,189)→(163,195)
  [+6 = the garruk one_of menu], rows_with_ground 78→79.
- File diffs: episodes_v2 = **4 lines** (exactly the two fixed packs);
  episodes.jsonl (v1) +84 lines of churn = the STALE-file catch-up /34
  flagged (96 eps on disk → 114), not new drift; puzzle_corpus 68 lines.

## Self-review (mechanical; nested subagent spawn depth-blocked again)
Executed checks, not re-reads: helper matrix matches spec incl. n=0; QAtMost(0)
unconstructible (`__post_init__` guard); QX -> NotImplementedError with
"flag, never guess". Remaining min() sites audited: query.py:318 RANDOM =
FORCED engine report (no model decision, not this axis); query.py:393 CHOOSE
mode + _choice_bounds QAtMost = OPTIONAL up-to contract (EMPTY set legal by
design — min=0 is the contract, not a clamp). **One registered finding**:
`_choice_bounds` (query.py:482) QConst lane still clamps
`min(want, k_options)` — the axis's 4th surface, but `Choose.options` is a
STATIC effect tuple (fixed menus like "tap or untap"), so count>options is a
card-constant mismatch, never a live-shrinking-menu blindness. Low severity;
handed to T4 §9 merge ledger as E-candidate, NOT touched here (out of scope).

CORRECTION (fresh-eyes review): test_executor_layers.py:258 pre-exists this batch (batch claim mismatch item 10); the batch-added timestamp artifact is test_current_pt_timestamp_behavior (characterization, CR 613.3b/c-citing). Registered T4 deferrals from review: _choice_bounds QConst clamp (4th count surface, justified latent: Choose.options is a static frozen tuple), helper placement (move to executor/legality in T4), QAtMost(0) degenerate-override regression (hand-built IR only).
