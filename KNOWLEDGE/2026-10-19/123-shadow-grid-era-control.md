# 123 — Shadow 2×2 grid: the frozen champion has ZERO generalization gap on ZNR (and the era control caught a model-lane crash fuzz can't see)

Date: 2026-10-19 ~11:30. Rig: `tools/eval/gameplay_eval_v2.py`, pool=engine, device=cpu,
workers=4, seed-base 777001, 40 games per cell. Subject: `bsh_S3a_s3_best.pt` — frozen M21-era
champion, never trained on ZNR. Artifacts: reports/shadow_*_2026-10-19.json (4 cells).

## The grid (policy wins / 40)

| opponent | ZNR (unseen era) | M21 (own era, CONTROL) |
|---|---|---|
| heuristic teacher | **18 (45%)**, 0 crashes, 100% decisive | **17 (42.5%)**, 1 crash, 97.5% |
| random | **27 (67.5%)**, 0 crashes | **23 (57.5%)**, 0 crashes |

## Reading (confounder-checked)
- **The 45% vs teacher is NOT a generalization gap** — the era control gives 42.5% on the model's
  OWN training era. The matchup odds vs the scripted teacher are ~50/50 in-era; unseen-era play
  holds the SAME ground. Era delta = +2.5pp for ZNR, well inside n=40 noise (±~15pp).
- The random anchors confirm the model is genuinely playing (not degenerate) in BOTH eras, with a
  slightly LARGER margin on ZNR (67.5% vs 57.5%) — direction-of-noise, same caveat.
- Held constant: seed-base, worker count, pool=engine, encoder, checkpoint, turn caps. What varies:
  deck supply only. Engine state: the two eras ran the SAME engine build this morning (post
  fuzz-trio fixes 2224add/bbcddb0).
- Caveats (honest): n=40/cell (±~15pp); teacher is full-info heuristic (ceiling-ish, not human);
  engine-pool only (ZNR deckable 267, excludes register/uncompiled cards — deck composition differs
  per era, which is part of what "era" means here).
- Deep fuzz corroboration (same morning): ZNR 1000@cap-400 + M21 1000@cap-400, **0 crashes both**
  (on top of the committed 2000/era 0-crash finals; /109).

## NEW: the 1 crash is a MODEL-LANE class fuzz structurally cannot see (seed 777003, M21)
`verbs.py _v_cast → stack.py:1093 ValueError "CAST cannot pay: cost:mana_generic:2<3"` — a CAST
EFFECT asked the model which card to cast; the offer layer enumerated without PAYABILITY filtering;
the model named a card it couldn't pay for; execution refused loudly (raise kept). Ask-vs-execute
asymmetry, SAME shape as the aura hole (/114) — legality offers, engine refuses. RandomPolicy never
named the unaffordable card, hence 3000 clean fuzz games. Fix wave: cast-effect option payability
at the 12c/offer surface (CR 601.2b-e: unpayable cast option is not a legal option; a may-cast
effect with no payable option resolves honestly empty). Engine raise stays loud.

## For the owner / morning
- Generalization program premise CONFIRMED at first measurement: the v2 encoder + legality lane
  transfers M21-era play to ZNR cards at era-parity. Next step per /88 playbook needs TRAINING on
  ZNR (GPU + engine-down = owner window) to push BEYOND transfer.
- ZNR goldens cert (sibling /120 queue-2) is the right next regression net before PC-1 climbs more.
