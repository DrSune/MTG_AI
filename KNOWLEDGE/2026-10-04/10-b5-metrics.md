# B5 — PC-11..PC-14 wired into the campaign gate (tools-only, HEAD 68f9c85)

## What shipped

- `tools/audit/measure_bugcatch.py` — the single B5 acceptance instrument. House
  format (name/value/target/pass per PC, mirrors `tools/measure_grammar.py`):
  writes `reports/bugcatch_<date>.json` + auto-appends a dated NUMBERS.md
  section. Every number is RE-COMPUTED at run time (live disk membership via
  `membership.py`, branch/pair JSON totals, in-process D1–D6 scan) — nothing
  hardcoded.
- `tools/audit/deferrals.json` — the ruled PC-11 exception list. One entry:
  `Sublime Epiphany` (BCS 29), cited to the R16-1 response-window deferral
  (2026-09-30/11 + 16 closeout; wave-2 exclusion + wave-5 re-admit note
  2026-10-01/26). Future ruled deferrals are added here; the gate honors them.

## Measured baseline (2026-10-05 run, `.venv/bin/python tools/audit/measure_bugcatch.py`)

| PC | value | state |
|----|-------|-------|
| PC-11 residue @ BCS≥20 | **1 total / 0 ungated** (66 at/above T, 65 pack/suspect-covered; the 1 = Sublime Epiphany, deferred by R16-1) | PASS — GATED |
| PC-12 branch litness | **0.3814** = 37 LIT / 97 declared (13 DARK, 47 UNMATCHABLE); target ≥ 0.90 | FAIL — report-only |
| PC-13 pair coverage | **0.2820** = 2419/8577 tested; 7 classes, 0 zero-tested (best branch_entanglement 31.4%, worst pt_layers/grant 23.1%) | FAIL — report-only |
| PC-14 anomalies (D1–D6 × 10 catalog seeds) | **0** hits, 0 crashes | PASS — GATED |

`--deep` adds the N=20 replay lane (13 s total, full journal payloads; D1/D3–D6
run with data, D2 stays EXEMPT as in B2): **also 0 hits / 0 crashes**.

DARK-on-highBCS (BCS≥20, report-only until H-hunts drain): 6 branches —
Chandra Heart of Fire 01/02 OptionalEffect (BCS 37), Chandra Flame's Catalyst
01/02 (34), Radha Heart of Keld 01 (32), Demonic Embrace 01 (29).

## Exit-code policy (B5 ruling)

- **exit 0 iff** PC-11 ungated residue == 0 **and** PC-14 anomalies == 0.
- PC-12/PC-13 print PASS/FAIL against their targets but are tagged
  `(report-only)` and NEVER move the exit code — the design's §F targets
  (≥0.9 litness, full BCS≥T pair coverage) are B3/B4 queue-drain work, not
  current-state facts; failing on them would freeze the campaign.
- Negative-path honesty verified: with `deferrals.json` emptied, the same
  residue exits 1; restored, exits 0.

## Gates this batch

`measure_bugcatch.py` exit 0 (catalog lane) + exit 0 (`--deep`); core suite
**2354 passed + 3 subtests, 0 failed** (unchanged); pyright **0** on the new
file; ruff **Δ0** (`ruff check` + `format --check` clean). No MTG_bot/**, no
wave_builder.py, no H5/malefic-wildwood files touched.
