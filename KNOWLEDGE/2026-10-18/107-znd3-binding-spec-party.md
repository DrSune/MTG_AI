# 107 — ZND-3 BINDING SPEC: party round — ONE grammar item (QPartyCount), everything else existing lanes; full-party = FAnd-of-4 CONTROLLER_COUNT_GE (zero new predicate); drift-gated PT statics DEFERRED with named item

**SPEC-GATE REVISIONS (same night): adversarial gate ran on this spec — FM1 FATAL (payer-seat
party — Concerted Defense WITHDRAWN, see ZND-3d), FM2/FM3 attribution corrected by mechanical
re-count (delta −34/−35, flip set EXACT-16), FM4 clean. Gate verdict: GO after these edits; all
edits landed below with [SG-FM#] marks. The payer-seat discovery is a standing engine-class finding
independent of this round (ZND-3d).**

Date: 2026-10-18 23:5x (written while sibling waves ZND-1g + ZND-2f are LIVE in the compiler lane —
this is docs only; implementation dispatch is gated on their commits per the coordination law).
Method per /95 (evidence-first, reuse-first, additive-only). Evidence: 35 register rows / 32 cards
(`/tmp/opencode/znd2_evidence.json` key "party"; re-verified against the current working-tree report:
35 party rows still unparsed). Infrastructure audit: analyst wave ses_eaf21a64…; every file:line
below spot-verified by the orchestrator at HEAD.

## WORLD-CANONICAL SEMANTICS (/92 law — from THIS file, not world-memory)
`MTG_bot/data/ZNR.json` party reminder: **"Your party consists of up to one each of Cleric, Rogue,
Warrior, and Wizard."** ⇒ party size = number of DISTINCT classes PRESENT among creatures you
control, one-per-class cap, range **0..4**; module constant `PARTY_CLASSES = {CLERIC, ROGUE,
WARRIOR, WIZARD}`. "Full party" = all four present. **Two Clerics + one Wizard ⇒ party 2** (a
naive creature-count parse is the P0 misread — pinned falsifier below).

## Existing infrastructure verified before deciding (all re-verified at HEAD this session)
- `QDistinctColorCount` (ability_tree.py:879) + evaluator (quantity.py:323–330) — the registration
  MIRROR shape (4 touchpoints: unions :3258/:3862-style, `_FIELD_SHAPES` :3947, name list :4207).
  NOT generalizable to party: it counts PRINTED `identity.colors` (frozen data, engine carries no
  color-changing); party needs the LIVE type oracle (printed type_line ∪ layers.type_overlay —
  quantity.py:628–642 "the layer registry is the single type oracle"). Two distinct-count
  primitives with different data sources are §9-honest siblings; fusing them would ALSO break the
  frozen serialization (E-census ledger note).
- `CostDeltaReduceGeneric.amount: Quantity` (ability_tree.py:2344) + legality fold of
  delta+extra_deltas (legality.py:698–707, CR 601.2f) — per-unit discount = `QBin(MUL, QConst(1),
  QPartyCount(…))`, zero cost-grammar additions. §10: legal_casts PRICES the fold ⇒ the bound is
  visible on the query surface.
- **X-announcement: the `_shrine_count` idiom** (templates_b2a.py:199; b2b:2375) — compile-time
  SUBSTITUTION of a census Quantity where X appears. Party "where X is the number of creatures in
  your party" = same idiom with QPartyCount. **ZND-1g's cast-parameter X lane (kicker {X}) is NOT
  needed by any party row** (CR 107.4a single-X law noted; no party row has {X} in cost).
- **Full party = ZERO new predicate**: `FAtomPred.CONTROLLER_COUNT_GE` (enum :568; evaluator
  quantity.py:981–1005, HANDLE-FREE, judges `ctx.controller`, takes inner_filter) — full party =
  `FAnd(CONTROLLER_COUNT_GE(QConst(1), SUBTYPE_EQ c) × 4 over PARTY_CLASSES)`, composed template-side.
- Class grants: GRANT_TYPE carries arbitrary type words (payload :3663; static anthem layers.py:885–889,
  runtime :555–564; type_overlay read by TYPE_EQ/SUBTYPE_EQ at quantity.py:640–641) — Tajuru-Paragon
  class set ("is also a Cleric, Rogue, Warrior, and Wizard", /101 deferred-3, 3 rows) = GRANT_TYPE
  + type-word widening template. Census + grant unify on the ONE type oracle (§9 merge ledger).
- Drift hazard (GATE-RELEVANT): `_materialize_static` skips targets with existing ledger entries
  (layers.py:740–741) ⇒ static-PT values are NOT re-resolved when the underlying quantity changes.
  Kinetic Augur (SET_PT × quantity, b5b:1388) already lives with this exposure, compile-tested only.

## Grammar item (the round's ONLY addition; additive-only, omit-if-default serialization)
- **G1: `QPartyCount(selector: Selector)`** — Quantity node mirroring QCount/QDistinctColorCount
  registration exactly. Evaluator: for the selector-matched handles, union the type-oracle words
  (printed ∪ overlay — class GRANTS count, §11 board interaction is engine-side), intersect
  PARTY_CLASSES, `len()` ⇒ 0..4 by construction (the cap is the fixed 4-set, no clamp code).
  Templates pin the population axis via the selector: TYPE_EQ Creature ∧ CONTROLLER_IS YOU ∧
  battlefield (the audited `_shrine_count`/`_GE` population idiom). NOT a general distinct-atom:
  zero other consumers today ⇒ §10 phantom law ⇒ specialize now, generalize on the next census.

## Template batch (new bucket **b8**, tenth→eleventh module; tails REUSE the shared registries per /101 [G-FM6])
- **T1 cost rows (11)**: `This spell costs {1} less to cast for each creature in your party.` +
  the ability variant → CostModifier(CostDeltaReduceGeneric(QBin(MUL,1,QPartyCount))). 10-row
  single shape (largest party shape — /93 head).
- **T2 for-each scaled effects (8)** [SG-FM1/FM3 corrected from 10]: ETB/attack/counter/damage/life/token tails scale by
  QBin(MUL, unit, QPartyCount); includes Practiced Tactics "twice the number" = QBin(MUL,
  QConst(2), …) inside the DEAL_DAMAGE amount (NOT a damage-multiplier lane — zero layers work).
  **WITHDRAWN [SG-FM1, gate-FATAL]: Concerted Defense** ("Counter target noncreature spell unless its
  controller pays {1} plus an additional {1} for each creature in your party") — the engine resolves
  counter-unless-pay amounts in the **PAYER's seat** (verbs.py:1926–1928 `pctx = ctx_for(…, controller=payer)`);
  the party evaluator's CONTROLLER_IS-YOU selector would then count **the victim's party** where the
  card says the countering player's. Correct semantics = amount determined at ability resolution in
  the ability controller's seat, frozen before the payer is asked to pay. That is an ENGINE edit —
  out of a template-only round; the row stays UNPARSED (honest register) → **named item ZND-3d**.
- **T3 full-party (5)**: combat-start + cast-free-cast heads, condition = FAnd-of-4 (above);
  combat-step event templates exist (b2a:297; b2a:1655 combat trigger WITH condition already compiles).
- **T4 X-announcement (7)**: `_shrine_count` substitution idiom, X := QPartyCount.
- **T5 class grant (3, = /101 deferred-3)**: Paragon-style `is also a <class>, <class>, … and <class>`
  → static GRANT_TYPE (self). Golden (§11): Paragon's grant MOVES party counts for OTHER cards'
  abilities — the restricted card's encoding stays untouched.
- **T6 conditional (1)**: Acquisitions Expert "reveal … equal to the number in your party" —
  implementer CHECKS the REVEAL lane accepts a Quantity count; else registers as named defer (no silent drop).
- **DEFERRED with named engine item ZND-3e (2 rows, drift-gated)**: Archpriest of Iona
  `power is equal to the number of creatures in your party` + Ravager's Mace equipped-creature
  per-party static — encoding them BEFORE the layer re-resolution lane exists would mint live
  wrong-power boards (layers.py:740–741). Honesty: they stay UNPARSED (register), not encoded-and-misleading.
  ZND-3e = static-layer value re-resolution on census change (drift probe first: same board, party
  2→3, Archpriest power must follow; Kinetic Augur rides along as the pre-existing consumer).
- **DEFERRED with named engine item ZND-3d (1 row, payer-seat)** [SG-FM1]: Concerted Defense —
  counter-unless-pay amounts resolve in the **payer's** ctx (verbs.py:1926–1928), but "for each
  creature in YOUR party" names the countering player (ability controller). Fix = resolve a
  controller-scoped amount in the ability controller's ctx at resolution, freeze the total, then
  ask the payer — NOT a template change (needs a controller-frozen amount in the unless-pay lane).
  Engine-lane; row stays honest UNPARSED until ZND-3d lands.

## Predictions [SG-FM2/FM3: regenerated mechanically against the working-tree report; strict rule —
a card flips only if EVERY one of its register rows falls in a clearing tranche (the first version
of this calculation carried a "non-party rows are free" escape hatch — WRONG, dropped; that is the
same class of bug as /101's flip-set lesson)]
- Register: **−34 rows** (T1 11 + T2 8 + T3 5 + T4 7 + T5 3; +1 = −35 iff T6's REVEAL-lane check
  passes; −1 per unexpected lane-stop). PC-2: **−baseline + 34/726**.
- PC-1 flips — EXACT set (16): Allied Assault, Ardent Electromancer, Cascade Seer, Deadly Alliance,
  Drana's Silencer, Grotag Bug-Catcher, Kabira Outrider, Malakir Blood-Priest, Sea Gate Colossus,
  Shatterskull Minotaur, Shepherd of Heroes, Squad Commander, Stonework Packbeast, Synchronized
  Spellcraft, Thundering Sparkmage, Veteran Adventurer. (The gate's FM2 diff honored: −Thwart the
  Grave (surviving class-OR-list target row), −Zagras (3 surviving rows), −Concerted Defense
  (payer-seat withdrawal); +Allied Assault/+Ardent Electromancer/+Veteran Adventurer (party-only
  residue); +Stonework Packbeast (T5-only residue). The remaining 17 party cards carry OTHER
  unparsed sentences and stay residue.) Re-verify the set at dispatch against the then-committed
  report — sibling waves move the baseline. Flips outside the set = findings, not roundings.

## Gates (binding exit criteria, /101 form incl. [G-FM4] amendment)
M21: PC-4 0 diffs + deterministic fields identical vs HEAD (exempt PC-5/generated/git_head); zero
M21-facing template edits ⇒ safe by construction, but MEASURE. ZNR: deterministic two-run; register
delta EXACT vs the per-tid attribution (34, or 35 with T6). Tests pinned: **two-Clerics-one-Wizard ⇒ party 2**
(the at-most-one-each law); class GRANT moves the census (overlay consumer, §11 golden); token with
no class words ⇒ contributes 0; opponent's creatures never count (direction, E1 single encoding);
full-party FAnd false at 3 classes / true at 4; discount PRICE visible on legal_casts (§10).
Scenario pack (1 new, `znr_*_party*`, per-set "set" key): a cost-reduction cast whose priced ask
DIFFERS by party composition (falsifies both always-full-price and always-discounted encodings).
Full house set: core suite, run_scenarios, gen_buckets pins per law, pyright 0, ruff Δ0.
**Fresh-eyes adversarial on DIFF + this spec before commit.**

## Dispatch & coordination
Files: ability_tree.py (G1) + quantity.py (evaluator branch) + NEW templates_b8.py +
test_templates_b8.py + coverage.py + scenario pack + INDEX/NUMBERS backfill. **Collision surface
with the live ZND-2f backface wave = ability_tree.py + coverage.py ⇒ STRICTLY sequential**: re-run
the coordination check (`ls -t` < 15 min + KNOWLEDGE/<today>/ spec scan) IMMEDIATELY before
dispatch; after ZND-1g/ZND-2f commits, re-derive this spec's file:line inventory (the /101 [G-FM1]
law — HEAD moved twice today while specs aged).
