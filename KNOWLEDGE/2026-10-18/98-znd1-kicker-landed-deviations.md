# 98 — ZND-1 landed (+gate): kicker cluster 64/86 honest; carrier = KickerAbility node + gated EtBState; instead-fold law corrected by adversarial gate

(Numbering: this file was written as /97 in parallel with a sibling session's 97-unaskable-audit;
renumbered /98 same day. Headline coverage restated post-gate below.)

Date: 2026-10-18. Implements /95 (binding) via the b6 bucket wave. All /95 exit gates measured;
deviations from the spec's chosen carriers are documented here (§Type-1 honesty) and flagged in the
session report — the encoded *shapes* (T2/T3/T5 trees) match /95 exactly; the *carriers* for T1/T6
did not, deliberately.

## Headline numbers (commands: `.venv/bin/python tools/measure_grammar.py --set ZNR|M21`)
- ZNR PC-1 card_coverage **0.1879 (53/282)** — uplift from 0.1418 (40/282, /93).
- ZNR PC-2 sentence_coverage **0.3457 (251/726)** — uplift from 0.2809 (184/655, /93) and from
  184/726 = 0.2534 (honest back-face-inclusive denominator, /96): **+0.0923, +67 sentences**.
- Kicker evidence cluster (/tmp/opencode/znd1_evidence.json): **67 of 86 rows covered**;
  **19 rows on 19 cards residual (17 distinct shapes)**, every one inside the /95 deferral
  ledger or the
  b6 module-docstring gap ledger (choose-any-number ×3, spend-restrict, first-kicker discount,
  copy-twice/copy-token, half-life & half-library, anaphoric "+2/+1 those creatures",
  HAS_KICKER reveal-menus, X-kicker gain-control, per-each counter quantity). Rows registered,
  not deleted (honesty law).
- b6 registration: **7 templates, 21-entry shared tail table**; bucket modules now 9.
- M21: PC-4 **0 diffs** (305 goldens verified); report content **byte-identical** vs
  `/tmp/opencode/grammar_m21_prechange.json` (only timestamp/latency/git_head lines differ).
- Gates: core suite **2569 passed + 23 subtests**; pyright **0** on all touched files;
  ruff **Δ0** (modified files 55→55 findings; templates_b6.py + test_templates_b6.py 0 findings);
  ZNR report deterministic across two runs (PC-9 stable; run-vs-run diff = timing keys only).

## Deviations from /95 (binding-spec carriers → tree carriers) — deliberate, rules-grounded
1. **T1/G1 — carrier is `KickerAbility` tree node, not `AdditionalCostOutcome.kicker` flag.**
   /95 G1 proposed a bool role-flag attaching kicker to the SpellAbility additional-cost lane.
   The landed design encodes the head sentence as `AbilityOutcome(KickerAbility(cost))` — a
   member of the Ability union (ability_tree.py, serializer `_SPECS` registered). Rationale:
   a post-assembly *flag* is invisible to the model (menu-visibility law §10 — "Kicker {2}{G}"
   is printed cost-variant information the encoder must see), and §9 demands {cost} be its own
   axis, not a boolean fused onto another node. G1 as literally specified did NOT land;
   `AdditionalCostOutcome` is untouched (my earlier flag was removed as dead code).
2. **T6 — gated `EtBState.condition`, not ETB-trigger equivalence.** /95 T6 (orchestrator
   hypothesis) claimed "if kicked, enters with N counters" ≡ "When it enters, if kicked, add
   counters". Verified independently: **enters-with counters is a replacement effect**
   (CR 614.1c), not a trigger — the EtBState-with-condition encoding is the rules-correct atom.
   Omit-if-empty serialization keeps every M21 golden byte-identical (M21 has zero gated EtB
   states — test `test_ungated_etb_bytes_unchanged` pins the no-condition byte shape).
3. **Fold law extension (compiler):** an "instead" arm whose BASE sentence itself compiled to
   residue folds **standalone** (`Conditional(WAS_KICKED, arm, else=None)`; the base lives on in
   the register as honest residue — no fake else-branch). An "instead" arm with NO preceding
   content at all (orphan) still raises `StateCorruptionError`. Both paths executed in
   `test_templates_b6.py::TestInsteadFoldFailurePaths`.
4. **T4 (cast-conditional self-filter) template NOT registered this round.** Its only ZNR
   instance (Scourge of the Skyclaves) is blocked by the unencoded half-life effect anyway;
   registering a zero-consumer template would be phantom (menu-visibility law). Lands with the
   derived-quantity effects round. Registered count-wise as residue (T3 template would not match
   it — separate shape, no silent claim).
5. **HAS_KICKER registered with ZERO template consumers** (per /95 G2; consumers = Coralhelm /
   Murasa Sproutling reveal-menus, ZND-2). Census: 0 cards use it today; vocabulary pre-registered
   so ZND-2 menus don't need an enum change. §9 census law noted for the audit.

## Landed template inventory (tid → /95 item)
- B6-kicker-head → T1 (carrier deviation 1); B6-etb-kicked-trigger → T3 (creature/enchantment
  type words; name-referent variant lands as residue with its unencoded effect);
  B6-cast-kicked-trigger → T2 (WAS_KICKED placed on `CastSpellEvent.filter` — the event's own
  subject-narrowing field, actor CONTROLLER_IS YOU — rather than `TriggeredAbility.condition`;
  same semantics, subject-local placement is the stricter reading of the :1919 convention);
  B6-kicker-additive / B6-kicker-instead-prefix /
  B6-kicker-instead-suffix → T5 additive + replacement arms, folded by `compile_card` into
  `Conditional(WAS_KICKED, arm[, else=base])` — exactly the /95 tree; B6-kicker-etb-counters →
  T6 (carrier deviation 2).

## Files
`ability_tree.py` (WAS_KICKED + HAS_KICKER members + _FATOM_RULES rows, KickerAbility,
EtBState.condition, serializer specs) · `compiler.py` (KickerEffectOutcome fold loop,
two-tier instead rule) · `templates.py` (KickerEffectOutcome + SentenceOutcome union) ·
`templates_b6.py` + `test_templates_b6.py` (new, 26 tests incl. both fold failure paths) ·
`coverage.py` (b6 registration, nine buckets).

## POST-GATE REVISIONS (adversarial fresh-eyes review, same day — COMMIT was gated on this)
- **Deviation 3 is SUPERSEDED — the gate proved the standalone fold rules-wrong, not merely ugly.**
  `Conditional(WAS_KICKED, arm, else=None)` positively asserts "un-kicked ⇒ NO effect": live on
  Roil Eruption / Cinderclasm / Blood Beckoning (un-kicked Roil encoded 0 damage vs rules 3; the
  register said "base residue" while the tree said "base = nothing" — §11 contradiction, PC-2
  inflation). CORRECTED LAW now in code: `replaces` arm + unparsed base ⇒ **no fold, arm stays in
  the register**; the fold search **breaks** at the residue slot (gate also caught a latent
  overshoot: arm could attach ACROSS a residue onto an unrelated earlier effect — synthetic repro
  pinned as `test_instead_arm_does_not_attach_across_residue` with pre-fix contrast); arm + compiled
  base still folds `Conditional(then=arm, else=base)` (positive control). Two tests that encoded
  the superseded law were rewritten.
- **Honest numbers after fix** (`--set ZNR`, deterministic): PC-1 **0.1879 (53/282)** unchanged;
  PC-2 **0.3416 (248/726)** (−3 = the inflated arms); register 475→**478**; kicker evidence join
  **64/86** (the 3 arms now honestly residual — 22 rows remain, all in /95 deferral ledger).
  Gates re-run: core **2571 passed**, M21 PC-4 0 diffs + byte-ident, pyright 0, ruff Δ0.
- Verified clean by the gate: KickerAbility serializes/round-trips (38 ZNR nodes, §10 carrier OK);
  M21 byte-identity independently reproduced; no merge debris (`KickerGate`/flag remnant grep zero);
  commit 4df4345's message claims a "KickerGate flag carrier" that exists nowhere — this file + the
  code are authoritative.
- Trap (same day): **multi-set daily-report collision** — `measure_grammar.py` names its report by
  date only, so a same-day `--set ZNR` OVERWROTE the M21 re-cert artifact
  (`reports/grammar_2026-10-18.json` now holds ZNR). Re-cert proofs survive in session records;
  one-line tool fix (set-qualified filename) = ZND-2 chore.
  **FIXED same day (ZND-1e gate F1/F2):** harness now emits `grammar_<date>_<SET>.json`, the
  NUMBERS auto-append header is set-qualified with a same-date-same-set dedup guard, and the row
  command column shows the run's real set (was hardcoded `--set M21` — evidence-law violation on
  ZNR rows). Legacy date-only file removed; today's artifacts: `grammar_2026-10-18_M21.json` +
  `grammar_2026-10-18_ZNR.json`. The 20 pre-existing duplicate T5 headers stay (append-only law).
