# 63 — T5-E clause closure: residuals 3→0, coverage 589/589 (100.0%)

## Correction of the T5-C record (binding)
T5-C (2026-10-09) reported the three clause-audit residuals (Makeshift
Battalion attack trigger, Conspicuous Snoop conditional grant,
Transmogrify reveal-dig) as "fixed". Commit `0daa6c2` touched ONLY the
eval harness/runtime lanes — the compiler still did not emit the three
legs and the audit still carried 3 NOT-ENCODED residuals at T5-E start.
The clause audit (`tools/audit/clause_audit.py`) was and is the ground
truth for encoding closure; runtime fixes do not map clauses.

## What closed each clause (all EXECUTED, gates at bottom)
- **Battalion** — `compiler/templates_b5a.py::_build_battalion` now emits
  the full `TriggeredAbility`: `DeclareAttackersEvent(IS_SOURCE)` +
  condition `FAtom(CONTROLLER_COUNT_GE, inner=FAnd(TYPE_EQ Creature,
  IS_ATTACKING), count=QConst(3))` (CR 508.2 group-of-three, mirrors
  `binding._keyword_node("BATTALION")` incl. the PUT_COUNTER self
  selector) + `PUT_COUNTER(+1/+1, self)`. The phantom `KW:BATTALION`
  token is gone, so the binder's synthetic keyword lane is inert for the
  card (no double-fire); handcrafted keyword tests (`test_executor_r20a`)
  still pass because the binder code itself was untouched.
- **Transmogrify** — `templates_b5b.py::_build_transmog_reveal_creature`
  returns `Seq(search, REVEAL(TARGET_PLAYER, QUnbounded))`. ORDER IS
  FORCED: a leading REVEAL opens the r19b look-window and the dig's
  promoted ONE_OF+LIBRARY+TOP selector re-scopes its menu to the window
  (`executor/selectors.py:364`), which killed the dig scenario
  ("expected 1 on battlefield, got 0"). Trailing REVEAL is byte-identical
  for the dig menu and the window dies with the s3 SHUFFLE. The whole
  pool's only reveal-until-dig card; documented divergence from printed
  text order in the builder docstring.
- **Snoop** — new template `B5a-snoop-top-goblin-abilities`:
  `StaticAbility(condition=FAtom(ZONE_COUNT_GE, who=YOU,
  zone=LIBRARY/YOU/position=TOP, count=1, inner=SUBTYPE_EQ Goblin),
  effect=GRANT_ABILITY(target=self, ability=<payload>))`. Two engine
  facts made this possible without new IR enums:
  1. `executor/quantity.py` ZONE_COUNT_GE evaluator now honors the
     OPTIONAL `Zone.position` (TOP→`entries[-1:]`, mirroring the
     selector idiom). Before T5-E a positioned zone was silently a
     whole-zone count — the lie the R10 note had flagged. All corpus
     users carry unpositioned zones → byte-identical; the 19 lane tests
     pass unchanged.
  2. The T3-round-4 `StaticAbility.condition` + static GRANT_ABILITY
     lanes (Thieves'-Guild-Enforcer / Light-of-Promise shape) were
     already live.
  Payload = a registered-INERT `StaticAbility` mirror of the card's own
  s1 reveal static: valid `ability`-slot node (§8.3), invisible to
  `granted_activated` (filters to ActivatedAbility) and to the binder's
  granted-trigger drain (TriggeredAbility only) → zero observable delta,
  proven by 398/398 with byte-stable asks. A live ActivatedAbility
  payload was ruled out on two grounds: `query.legal_activations:268`
  surfaces granted rows in the ACTIVATE menu (phantom rows re-pinning
  every pack against an ability the top card may not even have), and it
  duplicates the s2 free-cast lane (§10 PHANTOM).
  **Gap ledger stays OPEN**: granting the ABILITY SET of a
  dynamically-referenced card (card→ability introspection) has no atom
  — doc /11 §DEFER's semantic content remains; the R10 UNCOVERED row was
  replaced by this gated encoding, not by full expressiveness.

## Census/re-pin trail (all re-pins are my tree changes, none hid a failure)
- `test_templates_b5a.py`: 61 templates / 65 COVERED / 2 UNCOVERED; shape
  38 → `B5a-snoop-top-goblin-abilities`; new structural test
  `test_snoop_top_goblin_grant`; battalion test re-pinned to the
  TriggeredAbility shape (superseded KeywordOutcome pin).
- `test_compiler_c3.py`: both transmogrify tests re-pinned to
  `Seq(MOVE_ZONE, Seq(SEARCH, REVEAL), SHUFFLE)`.
- `test_promotion_predicate.py` census: selfref 55→57, total 154→156 —
  attribution verified as EXACTLY two new CHOOSE+IS_SOURCE self-target
  surfaces (`('Conspicuous Snoop','GRANT_ABILITY')`,
  `('Makeshift Battalion','PUT_COUNTER')`); both stay CHOOSE in live
  (no phantom promotion; leak tests pass).
- `tools/audit/test_clause_audit.py`: the `n > 0` vacuity tripwire (an
  audit must not claim a perfect score) could not survive legitimate
  zero residuals; replaced with a structural guard — mapped_total == 589
  AND distinct evidence vocabulary > 40 (measured 73).

## Goldens
`write_goldens` + `verify_goldens` = `[]`. Working-tree golden diffs:
Battalion 8b6e2feb, Transmogrify 4c1c3a0a, Snoop f5d1bd3c (mine) +
21fa2442 Peer / 63f60dfc Sanctum (pre-existing T5-D runtime-lane
re-emissions, not touched here). Other 298 trees byte-identical.

## Gate numbers (2026-10-10, this session)
- `python tools/audit/clause_audit.py` → 589/589 mapped, 100.0%,
  0 residuals, all four classes 0.
- `python tools/run_scenarios.py` → 398/398 (post-golden regen).
- `pytest MTG_bot/core -q` → 2516 passed + 2 subtests, 0 fail.
- `pytest tools/audit tools/training -q` → 164 passed.
