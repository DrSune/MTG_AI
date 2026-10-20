# 140 — R2 BINDING SPEC: F4 damage-event fold (CDE→DDE) + F1 zero-residual registration

Date: 2026-10-20. Round of docs/DESIGN_ATOM_ONTOLOGY.md §4 F4 row + §8 R2.
Evidence commit-resident (same commit): `reports/r2_evidence.md` + `reports/r2_census.json`
(`tools/audit/r2_damage_census.py`) + `reports/r2_sortdelta.json` (`tools/audit/atom_sortdelta_r2.py`,
repo-rerun reproduces: conv=True idem=True content=True exc=0). Gate protocol: spec gate →
implement (no git by implementer) → diff gate → one-commit landing.

## 1. HEADLINE (Type-1) — real fold, closed population, convergence pre-proven
Census: 13 damage-event nodes / 13 cards. CDE (combat-damage-event atom, 3 nodes:
**Jeskai Elder, Feline Sovereign [M21], Nimble Trapfinder [ZNR]**) is a wording-variant of
DDE{combat:true} (10 nodes, ZNR 0): same dealer-side "whenever this/these creatures deal
combat damage" trigger, two atoms — the §9 orthogonality violation this round merges.
Fold target = **DDE** (richer: amount/recipient/source/combat all consumed by
`_match_damage` binding.py:1088; CDE has NO recipient axis and its template self-declares
lossy "'to a player' dropped"). Measured convergence: post-fold Jeskai Elder bytes ==
Garruk's Harbinger DDE bytes VERBATIM (sortdelta script, executed). Truthful non-targets
(leave alone): passive "is dealt damage" lane, noncombat pair Pyreling/Incinerator already
byte-identical, replacement-effect shapes single-encoded.

## 2. SCOPE
(1) Compiler emission (3 template sites): emit DDE{amount:QUnbounded, combat:true,
    recipient:FAnd(()) [universal marker, binding.py:177 _is_universal — preserves TODAY's
    lossy semantics], source:<per-card filter>} — IS_SOURCE for Jeskai/Nimble;
    FAnd[CONTROLLER_IS YOU, Cat-subtype] for Feline (Subira precedent shape).
(2) D9-PRECONDITION pins (red-first, EXECUTED, per mutation-recipe law): prove by running
    the engine that DDE{recipient:FAnd(())} matches EXACTLY where CDE matched: for each of
    the 3 cards, scenario fires (a) combat damage → trigger fires; (b) non-combat damage →
    no fire; (c) Feline: non-Cat combat damage → no fire. Record red pre-change (CDE path),
    green post-fold. No FAnd(())-vs-None three-way fold is assumed — behavioral equivalence
    of the CHOSEN encoding is what ships, pinned.
(3) Dead-vocabulary deletion AFTER population-zero check (census re-run): remove CDE IR
    class + all lane references — binding.py:58/:875, replacements.py:54/:105, events.py
    feed lane, 7 IR sites, 3 emission sites, test references. Merge ledger F4 → LANDED.
(4) Goldens: re-bake EXACTLY {Jeskai Elder, Feline Sovereign} (M21 2); Nimble Trapfinder
    ZNR has no golden store (guards + fuzz cover).
(5) F1 direction: NO-OP-WITH-EVIDENCE — zero residual (M21 43/43, ZNR 16/16 event actors
    compile CONTROLLER_IS; StepEvent.controller population 0 + executor-declared
    UNSUPPORTED binding.py:159; census evidence committed). Register verdict in §4 F1 row.
(6) atom_field_table: any CDE rows removed; rerun exit 0. NUMBERS rows + landing note.

## 3. Pre-registered predictions (MEASURED; deviation = FINDING)
- Changed records EXACT {Jeskai Elder, Feline Sovereign} M21 + {Nimble Trapfinder} ZNR
  (3 total; sortdelta JSON); 2 goldens re-bake; ALL other bytes Δ0.
- Convergence: post-fold Jeskai bytes == Harbinger bytes (test assert, executed).
- CDE population 0 both pools post-fold (census assert); removal compiles, no dangling ref.
- Fire-parity battery (2) green; PC-1/PC-2/PC-6 anchors Δ0 (M21 4/.1265, ZNR .3830/.5496/
  26/.1547); PC-4 golden_stability 0 diffs post-re-bake; suite `MTG_bot/core tools` 0 fail
  (3149±new tests); packs current-count 0-fail same-invocation; fuzz 40/40 0 sigs;
  determinism double-run byte-identical.

## 4. Registrations at landing
- BACKLOG engine-lane ticket **ZND-7** (ID verified free): (a) merged-hand discard bug —
  Bad Deal & Waker#+1 resolve first-n of MERGED all-player hands (HAND:ANY, no EachPlayer
  wrapper, verbs.py:156-200) vs "each opponent discards two" [found during R3 census];
  (b) "to a player" recipient-fidelity rules change — gated on settling D9 empty-FAnd
  three-way fold first; fold here preserves today's semantics.
- Ledger: F4 → LANDED (merge ledger); D9 note (FAnd(()) behavior-pinned, fold still open).

## 5. NOT in scope
ZND-7 (above), D9 three-way fold itself, R3 ask-lift (separate spec /141), recipient
fidelity, any executor matching-semantics change (fold must be fire-parity-preserving).
