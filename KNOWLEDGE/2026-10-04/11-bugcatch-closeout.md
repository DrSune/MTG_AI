# 11 — BUGCATCH arc closeout (2026-10-04/05, session end)

## What the arc was
Owner charge: measure suspiciousness (complexity/interactions/sequence-depth) to find the
residual bugs we expect in advanced cards. Design /12 → instruments B1–B5 → three hunt
rounds, all in one session.

## Yield (heat-predicted hunting, 4 real engine bugs + 1 falsified claim in ~33 packs)
1. Siege Striker × Basri (pair heat 3710): trigger-created EoT expiry wrong (H4, CR 611.3).
2. Garruk's Harbinger (branch heat 32): rummage REST silent no-op on accept path (H4).
3. Cast-lane EtBState dropped ENTIRELY (H5, CR 614.1c) — the Malefic×Wildwood pair probe's
   P/T claim was itself wrong (printed 0/0, Scryfall-checked) yet the FORCED probe surfaced
   the deeper bug. Lesson recorded: a wrong hunt claim can still be a great instrument.
4. (earlier same arc) LOSE_LIFE unjournalled (B2→B3a) — detector D1 found it on 4/20 seeds.
5. D6 suspects 3/3 falsified with CR citations (611.2a, re-entry ghost) — instrument noise
   handled without weakening detectors.

## Instruments now standing (all gated in tools/audit/measure_bugcatch.py)
- PC-11 complexity residue: PASS gated (1 ruled deferral: Sublime Epiphany/R16-1).
- PC-12 branch litness 0.3814 (37/97; DARK 13; high-BCS dark 6) — report-only, rises with hunts.
- PC-13 pair coverage 0.2820 (2419/8577; no zero-tested class) — report-only, rises with hunts.
- PC-14 anomalies D1–D6: PASS gated, 0 hits catalog + --deep 20-seed replay.
- Heat queues: branch_coverage.json (13 DARK left) + pair_coverage.json (~6150 untested,
  heat-ordered; rounds consume 10 at a time).
- Note: tools/audit/suspects/ directory absent while empty — recreate on first suspect.

## Standing loop (unchanged engine-author-suspect-adjudicate, now heat-fed)
Per round: H-author (10 pairs or all remaining DARK branches, engine frozen) → fix batch
(heat-predicted suspects first) → re-run measure_bugcatch (PC-12/13 up, 14 stays 0) →
catalog/gates per /02 laws. CAST-attribution deferred-instrumentation spec lives in
/04-b4a §deferred — rule on it only if a material DARK class stays unattributable.

## Session numbers (NUMBERS-backed)
Packs 304→339 · suite 2345→2360+3 · games 100-seed 0 crash classes all session ·
PC-1 303/305 PC-2 637/639 PC-3 0 PC-4 0 · ledger EMPTY (0 suspects) · 27 branch packs +
20 pair packs + B4/B5 tools + 3 docs (07/09/11) + rig laws ×12 in PITFALLS.
