# 113 — HAS_KICKER lands on the 12c query surface (last fuzz class closed)

Date: 2026-10-19. Lane: engine only (`executor/quantity.py`). Residual crash
of the /109→/112 fuzz line: `HAS_KICKER not implemented (12c query surface)`
(quantity._eval_atom), fired by Murasa Sproutling's kicked ETB ask "return
target card with a kicker ability from your graveyard" (compiled filter:
TARGET, count 1, your graveyard, `FAtom(HAS_KICKER)` — read off the compiled
tree via `compile_card`). /98 registered the pred declarative; this wave is
its first consumer.

## The encoding (printed-property reading)
- Ground truth = the card's COMPILED record: HAS_KICKER ⟺ the FRONT-FACE
  ability tuple carries a top-level `KickerAbility` — the identical scan
  `legality.kicker_of`/cast-fold use (§9 one encoding). Record resolved via
  `legality.spell_record` (handle bridge → oracle-id registry; the r20c
  hand-window pattern for off-battlefield cards).
- FACE law (/106): the scan never descends a `BackFace` subtree — a
  back-face-only kicker does NOT satisfy a front-face HAS_KICKER (pinned by
  a synthesized record; census: ZNR has 38 front-kicker cards, **0**
  back-face-only kickers). If face playability ever lands, the judged face
  becomes the coordinate at this site.
- Tokens: unregistered token record OR `is_token` record → False, never a
  raise (a token has no printed kicker).
- Bare ExecCtx (no binder) raises naming HAS_KICKER (flag-not-degrade).
- The generic 12c raise REMAINS for other unknowns (e.g. PT_GE still hits
  it; pinned by a vocab-scan test — HAS_KICKER is the only pred that moved).

## Headline numbers (producing commands)
- Fuzz rerun `python tools/eval/znr_engine_smoke.py --games 60` (defaults:
  deck-pairs seed 201019, identical to the pre-fix ledger): 60/60,
  **crashed 0 (0.0%), signatures 0** (was 1 hit, seed 10). Reports
  overwritten at identical seed → comparable.
- `pytest MTG_bot/core -q` → **2672 passed, 36 subtests** (was 2660; +7 new
  tests in `MTG_bot/core/test_executor_has_kicker.py`).
- Packs `python tools/run_scenarios.py` → **409/409** (was 408; new pack
  `tools/scenarios/znr_murasa_sproutling_kick.json`: kicked cast DESIGNATES
  the single honest candidate — the filter vetoes the plain card pre-ask,
  no phantom menu — un-kicked cast asks nothing; quiet provider falsifies a
  phantom choice; mana 10G−5G−3G=2G pins the priced kick).
- pyright: 0 errors on both touched files; ruff: Δ0 on quantity.py (the 2
  remaining findings pre-exist at HEAD), clean on the new test file.
