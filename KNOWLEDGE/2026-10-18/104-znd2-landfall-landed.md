# 104 — ZND-2 LANDFALL LANDED: template-only round clears 30 rows, PC-2 0.3416→0.3829, PC-1 0.1879→0.2411; b7 = 10th bucket; pre-commit gate cut a §10 phantom the implementer had shipped

Date: 2026-10-18. Implements /101 (binding spec, gate-rebased). Grammar/engine **frozen**: zero
edits to ability_tree.py, compiler.py, executor/* — every landing is template-layer, so M21
byte-safety held **by construction**, not by repair. Sibling ZND-1e had landed (9e78ae3) before
dispatch; coordination law honored (mtime re-check + disjoint files; T4 rebased on HEAD at dispatch).

## Headline numbers (commands: `.venv/bin/python tools/measure_grammar.py --set ZNR|M21`)
- ZNR PC-1 card_coverage **0.2411 (68/282)** — from 0.1879 (53/282, /98).
- ZNR PC-2 sentence_coverage **0.3829 (278/726)** — from 0.3416 (248/726); **+30 sentences**.
- UNPARSED register 478 → **448** (30 cleared, **0 newly unparsed**, PC-3 ambiguity **0**).
- PC-6 max verb share 0.2062 → **0.1667** (landfall's 20 rows diversify MOVE_ZONE/PUT_COUNTER;
  orphans unchanged 30), PC-8 targetable **0.0745 → 0.1028** (15 cards newly fully compiled).
- Gates: core suite **2607 passed + 36 subtests**; scenarios **403/403** (402 HEAD + new landfall
  pack); M21 PC-4 **0 diffs** (305 goldens) + deterministic fields identical to HEAD (only
  generated/git_head/PC-5 latency differ); pyright **0**; ruff **Δ0**; gen_buckets JSONs
  **byte-identical**, pins hold; ZNR report deterministic.
- **Predictions vs actual (pre-registered in /101 [G-FM3/FM5]): all three bands HIT.**
  register 448 ∈ 445±8 · PC-1 0.2411 ∈ 0.245±0.010 · PC-2 0.3829 ∈ 0.387±0.015.

## Landed inventory (tid → rows)
- **B7-landfall** (20 rows / 20 cards) — head `^Landfall — Whenever a land you control enters, …` →
  `TriggeredAbility(ZoneChangeEvent(subject=FAnd(FAtom(TYPE_EQ,"Land"), FAtom(CONTROLLER_IS,YOU))))`
  with the b6-shared tail registry (FM6 §9 one-encoding law: b7 imports b6's builders + tail lists,
  identity-pinned in test, so "+1/+1 counter on this creature." resolves to ONE encoding whether it
  rides a Landfall, Cast or ETB head). CR 603.8 "Landfall —" = **syntactic head marker only**, no
  KeywordAbility (capture-once law).
- **B7-equip-etb** (8 rows / 8 cards) — one shape, `IS_SOURCE` self-referent + `Verb.ATTACH`.
- **B4 widening** (1 row) — enters-tapped `creature|artifact|enchantment` arm DISJOINT from the land
  arm; M21 census **0** hits on the two new sentences ⇒ goldens/buckets untouched.
- **B6 tails** (1 row: Murasa Sproutling HAS_KICKER return-from-GY).
- **`tools/scenarios/znr_landfall_direction.json`** — direction falsifier: my land enters ⇒ fires
  exactly once; an opponent's land enters ⇒ silent (E1 single direction encoding, §10).
- Coverage `build_full_registry` = **ten** buckets.

## The pre-commit gate cut a phantom (§10 enforcement, the /98 T4 precedent applied)
The implementer shipped `B6-etb-kicked-trigger-named` (name-backref kicker-ETB head) + a test that
PINS ITS ZERO CONSUMERS as an "honest census". Fresh-eyes gate FM1: it matches **0 of 726** ZNR
sentences front+back and was attributed **0 of the 30** cleared rows ⇒ pure PHANTOM, and the test
would have made the suite defend the blind spot. **Withdrawn** with the reasoning written into
templates_b6.py's gap ledger: it lands *with* its consumer, because its only register row (Jace
copy-exception token) has a tail the frozen grammar cannot express (`Verb.COPY` slots are
{source}-only). The HAS_KICKER precedent cited does NOT apply — that was a spec-mandated G2
vocabulary pre-registration with named consumers; this had none. The self-anaphor's mirror law is
still pinned (a renamed head must not borrow the "if it was kicked" anaphor — PC-3), and the Jace
row stays honest residue.

## FM5 folded into the suite (CR 603.2 origin-independence)
Gate's probe promoted to a permanent test: GY→battlefield and exile→battlefield ARE enters (fire,
re-fire per event); a pure EXIT is not (silent). Now 6 executor-level landfall tests, all judging
the JOURNALS through the executor rather than the pattern.

## Also fixed on this landing (tool honesty, gate FM2)
`measure_grammar._append_numbers_md` **returned early on a same-date same-set re-run while still
printing "row appended"** ⇒ NUMBERS.md's ZNR headline sat at the superseded 0.1879/0.3416 under a
"Latest entry first" banner after this round had already improved it — the number the project
trusts most was stale, and the harness claimed to have written it. Now the re-run **replaces the
day's set section in place** and prints "section replaced"; the ZND-1e F2 invariant (one header per
set per day) is preserved. Law: a dedup guard that skips the write must not report the write.

## Residual / next (unchanged defers, all counted in /101)
party 35 (ZND-3 `{census-of-derived-set}` atom round) · BFACE 71 (face-playability Type-1) ·
class-identity ×3 · EnterStateModifier other-object enters (Type-1 atom) · ordinal-resolution-count
(Omnath) · per-player this-turn counts (Confounding Conundrum) · additional-phase (Moraug) ·
CR 603.8b live-characteristic check blocked on a missing type-REMOVAL lane (FM2 of the SPEC:
`TYPE_EQ` = printed ∪ granted; no `−` lane — gap ledger + falsifier test in place, no overclaim).
