# 136 — R1b BINDING SPEC: Cost-parts canonical construction-sort + planner determinization

Date: 2026-10-20. Round of docs/DESIGN_ATOM_ONTOLOGY.md §3 SET-R1b rows, §8 R1b.
Evidence commit-resident: `reports/r1b_sortdelta.json` + `reports/r1b_sortdelta_summary.md`
(script `tools/audit/atom_sortdelta_r1b.py`) + the planner order audit (full text in
this spec's PARTS below, extracted from the evidence round). Gate protocol: spec gate →
implement (no commits by implementer) → diff gate → one-commit landing (golden-wave law).

## 1. HEADLINE DECISION (Type-1) — byte-wave with neutrality BY CONSTRUCTION
Earlier framing "planner-first corpus-Δ0, then sort" is DEAD by measurement: multi-part
Costs are everywhere (printed mana costs ARE multi-part Costs: M21 221 cards, ZNR 213).
Measured byte-delta of the sort: **M21 226/305 + ZNR 216/281** records change,
**226 M21 goldens** re-baseline. Neutrality is NOT hoped-for, it is PROVEN at one site:
`build_payment_plan` (:717ff) already recomputes everything from the parts LIST order;
sorting parts at CONSTRUCTION (`Cost.__post_init__`, the :2541 precedent; folded costs
pass through the same constructor via spell_cost :1113/1123, so kicker folds inherit)
makes the plan a function of the parts MULTISET. The audit's per-channel verdicts:
- (a) FAILURE-STRINGS: precedence = first-failing part in order; production consumers
  are `is None` tests ONLY (query.py:942-966/:255/:281; stack.py:753 embeds into error
  text). Strings drift on multi-failing costs; test exact-match pins re-pin (audited
  sample: single-part or order-free paths — surface small; full truth = suite rerun).
- (b) DISCOUNT MIN-CLAMP (:721-727): per-color draw is a Σ-min-clamp — payability
  ORDER-INVARIANT (proven); only intermediate trace + which string surfaces drift.
  Orrery global-pool shortfall (:738-747) order-free. Generic clamp post-loop aggregate.
- (d) WITNESS DIGEST (:1433 sha1 repr): vocab handle-sorted stable; parts order enters
  via sacrifice_options ask sequence (:799→pay_costs :1423) — multi-sacrifice-part
  population **0**, pinned red-first anyway.
- (e) KICKER FOLD (:1272) LIVE today (34/40 ZNR kicker + M21 Goremand/Thrill): runtime
  fold order today = printed++additional; after the wave the folded Cost self-sorts —
  replay/determinism surfaces (fingerprint pins test_executor_binding:812, rung1:355,
  stack:1291) must stay byte-stable: the digest vocab is multiset-keyed; ask-sequence
  drift only possible on multi-sac (0 population) — battery proves.
- (f) extra_deltas (:698-715): pure += accumulators ⇒ commutative — CLASSIFY
  OPERATOR-AUDIT → **SET** (sorted at construction same wave; atom_field_table updated).

## 2. SCOPE (one wave, landable)
(1) `ability_tree.py`: `Cost.__post_init__` sorts parts by canonical_json (SET law);
`CostManaHybrid.colors` sorted (corpus Δ0 — 0 hybrids both pools; witness preference
printed→alpha pinned by constructed-IR test only — dormant vocabulary battery);
CostModifier.extra_deltas sorted (SET reclass). atom_field_table CLASSIFY: Cost.parts
SET-R1b→SET-ENFORCED, additional_costs same, CostManaHybrid.colors same,
extra_deltas OPERATOR-AUDIT→SET-ENFORCED — module rerun exit 0.
(2) CONSTRUCTED-IR red-first battery (tests-first, before sorts ship — each MUST fail
pre-change, pass post): (i) two-failing-part precedence string stable under parts
permutation; (ii) {W/B}+{W/U} hybrid with pool W:1 B:1 payable-FLIP probe — pins the
CURRENT greedy first-printed-color channel DETERMINISTIC under sorted order (NOT fixed
semantics — see D10 below); (iii) {U}{X} cost + {U} discount carrier (Stormwing Entity
lane, CostDeltaReduceMana) trace invariant, string stable; (iv) constructed two-
sacrifice-part cost ask-sequence determinism (replay byte-stability of
`sacrifice:...:digest` keys).
(3) Goldens re-bake EXACTLY the 226 names (r1b_sortdelta.json); 79 no-cost-M21 byte-
match (305−226); leaf-multiset audit per card.
(4) Test re-pins for drifted diagnostic strings (identity-keyed where possible; per-
assertion audit comment; NO relaxation) — full suite is the truth surface.
(5) NUMBERS row + this round's landing note.

## 3. Pre-registered predictions (MEASURED; deviation = FINDING)
- Record bytes: M21 **226** + ZNR **216** exact sets (JSON); 226 goldens re-bake.
- PC-1/PC-2/PC-8 Δ0; PC-6 gate metric Δ0 (anchors M21 4/.1265 MOVE_ZONE, ZNR
  26/.1547 MODIFY_PT); PC-4 verify 0 post-re-bake; PC-5 report p99 (sort cost ≪ R0).
- packs current-truth count pre/post same-invocation; fuzz 40/40 0 sigs; corpus drift 0.
- Ask-sequence determinism: replay double-run byte-identical (fingerprint pins).
- ZNR 216 changed records have NO golden store (guards via verify-N/A + fuzz).

## 4. Ledger (DIVERGENCES additions at landing)
D10: hybrid-payment greedy payer-choice unsoundness ({W/B}+{W/U}, pool W:1 B:1 pays iff
favorable processing order; population 0) — RULED out-of-scope for R1b (canonicalizing
processing order ≠ fixing the greedy; a CR-faithful fix is a bipartite/matching problem,
same family as the blocker-completion Kuhn law /117 — named engine-lane item when a set
ships such costs). D11: failing-string precedence diagnostic (canonical order pinned by
battery (i) — drift accepted, diagnostic-only consumers proven).

## 5. NOT in scope
R2 (F4 damage fold, F1 residual re-audit), R3 (CHOOSE blindness audit; V4′ freeze armed),
greedy-hybrid fix (engine lane, D10), gameplay_eval/model files (sibling lane).
