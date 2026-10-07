# 26 — Audit response (owner 07:52): methodology holes found, one CONFIRMED engine bug, tokenizer census

## Falsification test EXECUTED (card-cluster bootstrap, 4000 draws, seed 7, on bc5_*_report eval_rows)
arm  acc   iid_m  cluster_m   verdict: margins SHRINK ~30% (i.i.d. assumption inflated them,
S0 0.680 4.19->3.03, S1 0.700 4.48->3.44, S2 4.19->3.04, S3 4.19->3.43, S4 4.48->3.46).
ALL arms still >3 SE with P(acc>floor)>=0.999 -> last night's verdict SURVIVES but the gate
must be cluster-bootstrap (binomial SE is the wrong model: 50 items = 32 cards, intra-card
correlation). Floor held fixed in bootstrap (per-item floors not in rows) — conservative.

## CONFIRMED engine bug (the hole's worst case realized)
tools/scenarios/feat_of_resistance.json eval_reclassification.reason says "no prevention lane".
Verified: golden/M21/2038f505...(Feat of Resistance).json tree contains NO PREVENT atom, while
Verb.PREVENT_EFFECT exists (ability_tree.py, phase-in boilerplate compiler.py:190, executor
replacements) -> the card EXECUTES WRONG vs printed text, and 14 packs carry this same
author-self-declared eval_reclassification flag (grep count) — every one is a SUSPECT: an
engine-vs-text disagreement cured by deletion instead of a fix.
FIX: reclassification becomes FAIL-REGISTERED (stays in ledger + E budget, excluded from
pass-rate only, needs file:line evidence why-no-decision); all 14 packs triaged into
engine-bug / true-no-decision / schema-gap.

## Elo inadmissibility (adversarial, verified in elo_s3_sanity.json): CIs vs pass-floor AND
vs random STRADDLE 0.5 winrate yet ladder reports positive ratings. Rule: Elo line
inadmissible unless that pair's bootstrap CI excludes 0.5.

## Tokenizer census (analyst + my recount, commands in /25->/26 thread)
Pool: 397 cards data, 305 enabled, 305 goldens, PC-1 0.9934 (2 unparsed: Snoop, Sanctum of
All), 92 never pooled. ASK OBSERVABILITY: golden CHOOSE selector-mode appears 172x vs ONE_OF
(the only asking selector) 4x -> the silent-choice class IS the fail-core cause.
Classified: modal "Choose two" = compiler-opener gap (pure vocab); cultivate/search picks
resolve via deterministic stand-in selectors.py:285-287 (observability plumbing); cw-window
shocks = NO priority atom (engine semantics, owner ruling); single-candidate auto-fill
selectors.py:438 = by-design (eval items there are MIS-SPECIFIED, re-register honestly).

## Ops incident (mine): sqlite3.connect("MTG_bot/mtg_bot.db") on a NONEXISTENT path silently
CREATED an empty shadow DB that masked the real one (config says data/mtg_bot.db). Removed
file + stale root twin; real DB verified intact (397 cards, read-only uri mode thereafter).
Pitfall recorded.
