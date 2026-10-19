# 120 — overnight owner report (ZND-2→4 lane, 2026-10-18 21:00 → 2026-10-19 06:5x): PC-1 0.2411 → 0.3688, three grammar rounds landed, two VCS incidents absorbed, five engine items filed

## Headline (all gates green at 432d0e9)
| | start (pre-ZND-2) | now | command |
|---|---|---|---|
| PC-1 card_coverage | 0.2411 (68/282) | **0.3688 (104/282)** | `tools/measure_grammar.py --set ZNR` |
| PC-2 sentence_coverage | 0.4669 (339/726) | **0.5413 (393/726)** | same |
| ZNR register | 387 | **333** | same |
| suite / packs | 2855 / 403 | **3003+36st / 413** | `pytest MTG_bot/core tools -q`; `tools/run_scenarios.py` |
| M21 (PC-4) | — | **0 golden diffs throughout every wave** | `--set M21` |

## Rounds landed (each: evidence-first spec → adversarial spec-gate → implement → adversarial diff-gate → commit)
- **ZND-3 party** (`64607ad` spec → code `1b7b9bf` (captured, see incidents) → `14c4af2`): ONE grammar
  atom `QPartyCount` (live type-oracle class census; world-canonical PARTY_CLASSES per /92 law),
  full-party = FAnd-of-4 existing predicates, −34 rows, PC-1 +16 cards EXACT-predicted. The diff-gate
  WITHDREW a row it found executing wrong (from-hand reveal runs as library peek — ZND-3f) and
  corrected a false claim in the implementer's own report (ruff Δ+1 was actually Δ0).
- **ZND-4 flip-sweep** (`42af6a3` spec → `432d0e9`): yield-ranked one-row-away strategy (102 cards sat
  ONE sentence from compiling), b9 bucket + 3 shared-regex widens, −20 rows / +20 flips EXACT
  (independent tid-sweep confirmed zero out-of-union), M21 stayed 0-diff despite touching shared
  carriers, flipped-pool fuzz 40/40 clean.

## Incidents (absorbed, laws written)
Two shared-repo capture events in 3h: ZND-3's staged set swept into sibling commit `1b7b9bf` (bare
commit = shared index); ZND-4's UNTRACKED WIP swept by an add-A sweep (`686e879`) — including a
mid-edit file that broke HEAD collection for ~1h until my repair commit. No history rewrites; both
got attribution-split follow-ups (/113, /119) + PITFALLS laws (stage→commit atomic; scaffold-early;
never leave a non-compiling file where a sweep can grab it; gate artifacts via `git diff --cached`).

## Engine items FILED for the engine lane (mine were template-lane only)
- **ZND-4d** (biggest): `layers.py` static registration DROPS the duration-role ⇒ pre-existing b4
  while-statics are EVER-LIVE in the engine (gate repro: 4/4 PT with no planeswalker on board);
  M21-era, IR-only test claims hid it — needs executor falsifiers for all b4 while-carriers.
- **ZND-3d** counter-unless payer-seat party; **ZND-3e** static census re-resolution (Archpriest/Mace);
  **ZND-3f** REVEAL HAND-zone role; **ZND-3g** SPELL-kind predicate (land phantoms in CMC asks);
  **ZND-4a** multi-keyword-row mechanism (one-row-one-outcome invariant — Type-1 schema decision).
- Sibling lanes live overnight: fuzz program (/109, /116 trio fixed), menace/MDFC engine fixes,
  WAS_KICKED blink-provenance (/110), aura-target legality — check their /118 for THEIR two OPEN
  OWNER QUESTIONS (MDFC world-rule, R1 window) — not answered here.

## Next queue (this lane, in order)
1. **ZND-5 one-away re-census** (the ZND-4 flips promoted a fresh wave of one-away cards — cheap yield
   analysis like /114) then spec if a batch exists; ZND-4a mechanism spec (small, Type-1-gated).
2. **ZNR goldens certification** (PC-4 is M21-only; ZNR's now-104 compiled cards have no golden net —
   `write_goldens`/`--refresh-goldens` machinery exists; needs per-card semantic cert batches;
   DO AFTER the engine lane's next commit (recompile churn risk).
3. Playbook step-2 drift probe stays gated on PC-1 (0.37 — closer).

Numbers of record: NUMBERS.md 2026-10-19 sections; per-round ledgers /113, /119; evidence /114.
