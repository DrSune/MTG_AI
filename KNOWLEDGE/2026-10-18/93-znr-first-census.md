# 93 — ZNR FIRST CENSUS: 0.142 compile / 0.281 sentence coverage; 471-sentence work register with kicker/landfall head; back-face measurement blindspot registered

Date: 2026-10-18. Follows /92 (file vindicated) + same-day unblocks: additive face capture in ingest
(48dfa0f, pool 282 = 270+12, 36 faces folded, corruption law intact, M21 byte-ident 305/0 backs,
61 ingest tests) and shape-gap-tolerant census (coverage.py tolerant loop + OMIT-IF-EMPTY
`shape_gaps`; measure_grammar PC-4 N/A for golden-less sets; `--set ZNR` runs end-to-end).

## First-touch numbers (commands: `.venv/bin/python tools/measure_grammar.py --set ZNR`; report
`reports/grammar_2026-10-18.json`, ZNR run exit 1 = FAIL policy on genuinely-failing PCs)
- PC-1 card coverage **0.1418** (40/282) · PC-2 sentence **0.2809** (184/655) · PC-3 0 PASS ·
  PC-4 N/A (no ZNR goldens — correct until trees are certified) · PC-5 0.212 ms · PC-6 orphans 33
  (max ADD_MANA 0.2597) · PC-8 0.0603 · PC-9 stable · PC-10 PASS.
- shape_gaps = **1** (Nighthawk Scavenger `power_raw='1+*'`); verified ONLY non-digit P/T in pool ⇒
  parse_pt class exhausted; no X-based P/T family lurking.
- UNPARSED register: **471 sentences / 241 cards / 311 distinct shapes**. Head concentration
  (sentences): landfall "Whenever a land" 25; kicker cluster (cost-reduction "This spell costs {N}
  less" 12 + "If this spell/creature was kicked" 23 + printed "Kicker {N}" boilerplate ~20) ≈ 57;
  "When this creature enters, if" 9; Equipment-attach EtB 8. Top-20 shapes = 151/471 (32.1%).
  ⇒ Grammar round candidates with M21-style batch economics; reminder-text "Kicker {N} (You may
  pay…" is partly BOILERPLATE-eligible (§11 significance criterion — parentheticals already stripped
  in clause audit; sentence splitter keeps them here — check before teaching them).

## BLINDSPOT ledger (§11, registered NOT fixed)
Compiler never references `back_face` ⇒ the 71 modal-DFC back-face sentences are OUTSIDE the 655-sentence
denominator entirely (measure "sees" front clauses 33 + normal 438). Two consequences: (1) PC-2 for
ZNR is optimistic by construction until faces enter measurement; (2) playability of Skyclave modal
casts (play-back-as-land / cast-back) needs engine P/T + layer support first (back faces of creature
DFCs like Akoum Warrior//Teeth carry static P/T — feasible; planeswalker-ish backs don't exist in ZNR).
Fix order proposed: (a) coverage denominator includes back sentences + shape census for faces; (b)
grammar round(s) on the head clusters; (c) engine face-playability decision (Type-1: touches layers
+ zone model) with adversarial gate.

## §8 atomics verdict data for the TOTAL-pool question (first real second-set evidence)
- New effect shapes NOT in the M21-era vocabulary census: kicker/landfall/enters-if/equipment (in the
  471 queue), modal-DFC (faces), '1+*' P/T (1 card), ADD_MANA orphan share rises (33 orphan atoms).
- "First ~20 sets change the atomics" holds on set #2 already: face capture LANDED (ingest), face
  MEASUREMENT + PLAYABILITY are the open rewrites. Zero-loss posture: nothing silently dropped —
  faces sit on RawCard, gaps sit in ledgers.
- Generalization meter (/86) stays armed — playbook /88 steps 2-3 (drift probe, holdout first-score)
  remain gated by compile rate: only 40/282 cards are currently engine-askable.

## Session gates run (2026-10-18, latest code): ingest tests 61 · compiler suite 837 · core 2539+2 ·
M21 report content-identical to pre-change baseline (timestamp+PC-5 latency only) · pyright 0 · ruff clean.
