# 02. Phase-3 COMPILER CAMPAIGN roadmap (2026-10-02, analyst, read-only)

Baseline re-measured this session: PC-1 301/305 · PC-2 634/639 · PC-3 **0** · PC-4 0 ·
engine 297/305 · PC-8 **0.3213 (98/305) FAIL** (target ≥0.40 — compiler-side, moves only
with audited IR; may legitimately RISE as casts/targets are emitted) · PC-6 orphan FAIL
pre-existing. Suspects: 13 files, all fail on documented lines (0/13 pass law holds).
Precedent: **C1** (/01) — template fix + set-equal inventory audit + `--refresh-goldens`
re-pin; sanctum ×4 promoted. Every batch below repeats that protocol.

## Ground truth verified for this roadmap (analyst probes)

- **Creature-spell-node question ANSWERED — no different lane exists.** legality.cast
  requires a SpellAbility (`cast:not_a_spell`, legality.py:1148-1150); games harness has
  exactly two put-into-play lanes: `play_cast` (asserts `isinstance(node, SpellAbility)`,
  games.py:497) and `play_land` (lands only). `CardMeta.playable = is_land or
  has_spell_node` (games.py:168-172). The brief's "the games harness DOES cast them" is
  true for only the 2 of 165 creatures carrying SpellAbility (Goremand, Sparkhunter
  Masticore — they hit the existing "Creature: EffectOutcome → SpellAbility(CREATURE)"
  path, compiler.py:1517-1524). Plain creatures sit dead in hand (pool `all`) or are
  staged via `enter` (scenarios). **Systemic fix = emission gap in compiler assembly,
  not a lane, not grammar.**
- Grammar governance: FAtomPred/Verb grew through OWNER-ruled **grammar rounds** (R3–R10,
  each a dated decision doc, additive+byte-stable law, INDEX `2026-09-24/02`). "FROZEN"
  = no IR/golden moves without an audited set-evidence batch (C1 form) and no new vocab
  without a new round. Round-3 queue explicitly registered **anaphora** for later rounds.
- Vocabulary facts that decide OWNER-blockers:
  - `CONTROLLER_COUNT_GE` / `POWER_GE` / `ZONE_COUNT_GE` **exist** → adherent, ornery,
    waker expressible template-only.
  - `QBinOp.DIV` docstring: "round-up-half is expressed as (n+1)//2" → peer expressible.
  - `Verb.PREVENT_EFFECT` docstring cites "can't attack or block" → tampering expressible.
  - SEARCH slot carries `tapped_on_enter` (opt:bool, honored by `_v_search`) → fabled.
  - `Verb.CREATE_TOKEN: {"tokens":T,"count":F}` — **NO controller slot** → secure_the_scene
    needs `_ATOM_RULES` addition = OWNER.
  - DamageDealtEvent row vocabulary = subject/cause/amount; no destination/subject-kind
    discriminator for "to an opponent" (player-subject test unexpressible) → pyreling
    needs new predicate or event slot = OWNER.
  - `SpellKind.CREATURE`, `SpellAbility(effect=None)` precedent (additional-costs cards,
    compiler.py:1548-1554), `EtBState` (initial_counters+tapped, ability_tree:2693),
    Keyword.FLASH exist → creature-node + wildwood need NO grammar change.

## Batches

| # | Batch (shared machinery) | Cards | Files touched | Grammar? | Evidence method / pack-unlock | Risk |
|---|---|---|---|---|---|---|
| 0 | **fabled flag** (SEARCH emits `tapped_on_enter`) | fabled_passage | SEARCH build site (templates_b2a/b5c) + goldens | none (slot exists, executor honors it) | C1 form; 1 pack. Falsifiability pins already on disk (green pack asserts UNTAP-branch; suspect = FALSE branch) | lowest; prove the per-batch audit protocol |
| 1 | **Quantifier predicates** (existential census) | adherent_of_hope, ornery_dilophosaur | trigger templates (b5a/b5b/b5c) + goldens | none (CONTROLLER_COUNT_GE + inner_filter + POWER_GE/NAME_CONTAINS exist; executor census green since r21b) | per-card FAtom-multiset set-eq; 2 packs | low; ornery = count-vs-power off-by-one only |
| 2 | **Dropped-clause / anaphoric emission** (spell & loyalty tails) | peer_into_the_abyss, liliana_waker_plus_one, transmogrify | templates_b2b/b4 (spell sentences) + goldens | none — peer: LOSE_LIFE + QBin((n+1)//2); waker: Seq + FNot(ZONE_COUNT_GE HAND≥1) + LOSE_LIFE (two-player reading, r21b precedent); transmogrify: compile tail as SEARCH(creature→BF)+SHUFFLE idiom (REVEAL half is public-info garnish) — if implementer instead wants REVEAL-until slot → OWNER | per-card set-eq; 3 packs | med: transmogrify needs an adjudication note (SEARCH-idiom ruling); hidden-information fidelity recorded |
| 3 | **Phantom-node suppression / mis-split assembly** | furious_rise, rin_and_seri | compiler.py assembly (orphan-fold sites :677/:705/:760, record fold :1460-1560) + goldens | none | set-eq incl. REMOVED phantom node (diff = +folded Seq, −phantom ActivatedAbility); **furious_rise unlocks; rin_and_seri does NOT** — its pack needs the 4 clauses `unparsed=()` falsely claims parsed (Cat/Dog statics + dies triggers) = **phase-2 ingest/parse gap** | med; assembly changes are corpus-wide — byte-identical proof for 300+ goldens mandatory |
| 4 | **Creature-spell-node systemic** (assembly emission) | creature_spell_nodes_systematic, wildwood_scourge | compiler.py:1517-1524 gate widened (always SpellAbility(CREATURE), effect=None precedent :1548); wildwood: EtBState w/ QX counters + SpellAbility for X-cost permanent | none | NEW audit form (OWNER ratify, see list): additive — "diff = exactly one added SpellAbility node per creature golden; no other byte moves"; 2 packs + **corpus unlocks cast-timing testability** (wave-6 re-derivation candidate) | HIGHEST blast radius: legal_casts enumeration changes → games survivors/catalog repin (insertion precedent); flash WINDOW honoring = engine follow-up to verify (Keyword.FLASH exists; spell_window_reason reading unproven) |
| 5 | **Restriction clause + mode entanglement** | tampering (Destructive Tampering) | spell templates (Choose-one emission) + goldens; engine DeclareBlockers consumer to verify (/18 shows event-conditional consult only) | none (PREVENT_EFFECT exists) | set-eq (MODIFY_PT(0) junk → PREVENT_EFFECT atom); 1 pack | med: if executor lacks a static can't-block consumer, engine follow-up needed AFTER emission — do not fabricate IR markers (19a law) |
| 6 | **Destination/role slots** — OWNER-BLOCKED | chandras_pyreling, secure_the_scene | grammar round-11 doc, then ability_tree slots + templates + verbs/quantity | **YES — requires grammar unfreeze ruling** | after ruling: C1-form set-eq; 2 packs | pyreling: DESTINATION/subject-kind predicate vs DamageDealtEvent field (additive byte-stable, R3-style); secure: `CREATE_TOKEN += controller` slot + anaphoric "its controller" binding in `_v_create_token` (currently prints at ctx.controller unconditionally) |

Already closed (not in scope): sanctum ×4 NAME_EQ→TYPE_EQ (C1). Logged micro-gaps
(Treasure {T},Sac activation; Forgotten Sentinel EtBState) = cheap tail-of-campaign adds,
same protocol.

## Execution order (leverage↓ risk↑)

0 → 1 → 2 → 4 → 3 → 5 → (OWNER round) → 6. Rationale: 0-2 prove the audited-golden-move
protocol on small diffs; 4 next because it is the largest unlock and needs the ratified
audit form but no new vocabulary; 3's assembly fold is riskier corpus-wide and rin phase-2
can start in parallel (ingest); 6 is hard-blocked on the OWNER round and lands last.

## OWNER decisions required BEFORE code

1. **Grammar round-11** (batch 6): damage-destination predicate/field (pyreling) AND
   `CREATE_TOKEN.controller` slot (secure_the_scene). Additive+byte-stable per R3 law.
2. **Ratify the additive-golden audit form** for batch 4 (163 goldens each gain exactly
   one SpellAbility node — the frozen-golden law's "set-equal" needs an "audited additive
   emission" amendment on record).
3. **Contingency**: if transmogrify's REVEAL-until idiom is chosen over the SEARCH-idiom,
   that is also a grammar-round item (REVEAL until-slot) — recommend declining.
4. **Metric re-baselines to accept up front**: PC-8 rises toward 0.40 (expected, compiler-
   side); catalog repin after batch 4 (insertion precedent); games survivor counts shift.

## Invariants every batch must hold (gate law)

PC-3 **0 EXACT** always · PC-4 0 after audited re-pin · pytest core green + falsifiability
pins per fix (r22c style) · scenarios 286/286 + promoted packs · catalog 0-diverge-or-
repin · games 0 crash classes · pyright 0 / ruff Δ0 · goldens move ONLY via the set-
evidence audit (pre/post snapshots, byte-identical proof for untouched cards).

> [!NOTE] Ratification note (2026-10-02, orchestrator; landed with batch C2 = roadmap 0+1)
> Golden-set moves for **audited additive or output-fix emissions** under the C1-form
> evidence (pre/post snapshot, byte-identical proof for untouched cards, per-card printed-
> vs-compiled multiset set-equality) are **ratified protocol** — precedent: B-11 family,
> C1 sancta sweep, now C2 (3 goldens: Fabled flag, Adherent census, Ornery count). PC-8
> re-baseline toward ≥0.40 is **accepted up front** as expected compiler-side progress.
