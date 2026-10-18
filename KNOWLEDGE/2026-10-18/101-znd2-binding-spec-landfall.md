# 101 — ZND-2 BINDING SPEC: landfall round — TEMPLATE-ONLY batch (zero grammar items): b7 bucket + b4 type-word widening + b6 head/tail extension; party / faces / class-identity named-item defers

**POST-GATE REVISION (same day): adversarial fresh-eyes gate RAN on this spec — FM1 fatal (T4 premise
was stale), FM2/FM3/FM4 patchable, FM5/FM6 registered, FM7 clean. All resolutions incorporated in
place below, marked [G-FM#]. The gate was RIGHT that the spec must rebase on HEAD: it moved mid-
review (sibling ZND-1e extended b6's head type-alternation).**

Date: 2026-10-18. Round scope per /93 fix-order (b) continuation after ZND-1 (kicker) landed (/98,
/100). Method per /95: evidence-first, reuse-first, additive-only, honesty ledger.
Evidence: unparsed register 475 rows (`/tmp/opencode/grammar_ZNR_finalB.json` 13:33 run, pre-/98-gate
−3 correction ⇒ 478) + family cluster dump `/tmp/opencode/znd2_evidence.json` (live-regex census,
this file: landfall 26 rows/20 shapes · equip-EtB 8 rows/1 shape · kicker-EtB residual 6 heads ·
enters-tapped 31 (25+5 BFACE pair +1 front artifact) · party 35 · class-id 3 · kw-pair 4 ·
may-play-lane 5). Infrastructure audit: analyst wave; every file:line below spot-verified at HEAD.

## Existing infrastructure verified before deciding (grep/line-verified 2026-10-18)
- `ZoneChangeEvent` (ability_tree.py:1600) + `TriggeredAbility{event, condition, effect}` (:2772);
  trigger delivery evaluates `eval_filter(node.subject, event.subject)` on the ENTERING permanent
  (binding.py:1013–1028); `KIND_ZONE_CHANGE` is journaled (executor/events.py:507).
  ⇒ "Whenever a land you control enters" = `subject = FAnd(FAtom(TYPE_EQ,"Land"),
  FAtom(CONTROLLER_IS,YOU))` — expressible TODAY.
- `EtBState(tapped)` (:2992) + templates `B4-enters-tapped-creature/-land` (templates_b4.py:1600,
  :1608, exact-match patterns `^This creature enters tapped\.$` / `^This land enters tapped\.$`);
  executor stamps tapped pre-ETB-triggers, CR 614.1c (`_apply_etb_state`, executor/__init__.py:931–1004).
- b6 shared tail table `_ETB_TAILS` (templates_b6.py:733) + `_alts`/`_alts_suffix` idiom (:624–633);
  landed head `B6-etb-kicked-trigger` covers creature/enchantment words only (:783).
- `Verb.ATTACH` (:229, slots {equipment,target} :3672); ETB `subject=IS_SOURCE` precedent
  (templates_b5a.py:958–967). All components of the equip-EtB shape exist.
- Grammar round-ZND-2 ADDS NOTHING to ability_tree.py. Zero new serialization keys ⇒ M21 goldens
  byte-identical by construction (no field can be set on an M21 shape).

## Template registrations (new bucket b7 + two surgical extensions)
- **T1 landfall (b7, new module `templates_b7.py`)**: head `^Landfall — Whenever a land you control
  enters, <tails>$` reusing b6's shared-tail table idiom + register tails observed: `+2/+2 until end
  of turn` (×5), `put a +1/+1 counter on this creature` (×3), `creatures you control get +1/+1 EOT`,
  `you gain 1 life`, `put a loyalty counter on <name>`, `put four +1/+1 counters on target Plant you
  control` (+ implementer completes the tail table from `/tmp/opencode/znd2_evidence.json`; tails
  already in `_ETB_TAILS` must be REUSED not duplicated — §9 one-encoding law). Encoded as
  `TriggeredAbility(ZoneChangeEvent(FROM ANY→BATTLEFIELD, subject=LAND∧CONTROLLER_IS_YOU), E)`.
  CR 603.8 shorthand "Landfall —" is a SYNTACTIC head marker only — do NOT also register a
  KeywordAbility for LANDFALL (capture once; the ability is the trigger).
  Census (ships with the atom, §9): **25 register rows / ~13 cards, 20 templateable** [G-FM3: 5
  stragglers fold into the defers — modal tail, graveyard-condition tail, as-though tail, Moraug
  phase tail, Omnath "first time this ability has resolved this turn" (ordinal-resolution-count,
  new axis)]. Tails REUSE the shared registry, never a b7-local copy [G-FM6].
- **T2 equip-EtB (b7)**: `When this Equipment enters, attach it to target creature you control.`
  — ONE shape, 8 rows (Cliffhaven Kitesail, Maul of the Skyclaves, Mind Carver, Ravager's Mace,
  Relic Axe, Scavenged Blade, Skyclave Pick-Axe, Utility Knife — evidence-regenerated [G-FM4]). `TriggeredAbility(ETB, subject=IS_SOURCE, Effect(ATTACH,
  {equipment: SOURCE, target: TARGET creature you control}))`. MAY-attach variants (Nahiri's Heir,
  Resolute Strike) stay deferred with their unencoded conditional arms.
- **T3 b4 widening (byte-safe edit)**: type words `creature|land` → `creature|land|artifact|
  enchantment` on the two enters-tapped patterns (ZNR front-face consumer: "This artifact enters
  tapped." — Spare Supplies). M21 patterns are EXACT-matched strings; widening is disjoint ⇒
  M21 bytes untouched (pin: M21 report byte-ident).
- **T4 b6 kicker-EtB residuals (b6 edit)** [G-FM1: the artifact widening this draft asked for is a
  NO-OP — HEAD `B6-etb-kicked-trigger` already matches `creature|enchantment|artifact|Aura|
  planeswalker|land|token` (templates_b6.py:784, verified at commit 3f0aeb8; the audit line was
  wrong)]: **name-referent head variant ONLY** (`When <NAME> enters, if <NAME> was kicked, <tail>`)
  + extend `_ETB_TAILS`
  with the register's new tails (block-ALL, create-copy-token, return-from-GY-with-kicker, gain-
  control-artifact-X). 6–8 residual rows; tails registered ONLY with real register consumers
  (phantom law §10 — no zero-consumer rows).
- **T5 TRIAGE (not a commitment)**: the graveyard-count trigger family the reader flagged (8 rows,
  "eight-or-more" phrasing not matched by the evidence regex — shape unknown) + kw-pair rows (4) +
  `is also a …` class-id rows (3): implementer DIAGNOSES (bucket hint, why unparsed) and REPORTS;
  converts to template rows only if expressible without grammar; otherwise registers as named
  defers. No silent swallowing.

## DEFERRED ledger (counted not deleted — honesty law; each names its future item)
1. **BFACE 71 rows / 8 shapes** (incl. the ×5 "As this land enters, you may pay 3 life" + "If you
   don't, it enters tapped" pair): compiler has ZERO `back_face` refs (grep 0) ⇒ /93 fix-order (c)
   FACE-PLAYABILITY round — Type-1 (layers/zone model), adversarial-gated. The pay-life pair then
   encodes `OptionalEffect(PAY, CostLife(3))` + `EtBState(tapped, condition=FNot(MAY_DONE))` —
   blockers: "If you don't" fold (compiler has only `_merge_do_continuation` :943) + MAY_DONE site
   channel inside the ETB replacement window (quantity.py:956 raises without it). HAZARD law
   (from /98 supersession): NEVER fold "if you don't" to an ungated EtBState.
2. **PARTY family — 35 register rows** (cost-reduction "costs {N} less for each creature in your
   party", "X is … for each party member", full-party combat triggers): {census-of-derived-set}
   quantity axis — NEW atom round ZND-3-PARTY with §9 census + §10 menu law (party membership is a
   live set — menu must show it). Not a template-only squeeze; do not kludge.
3. **Class identity "is also a Cleric, Rogue, Warrior, and Wizard" ×2 + related ×1**: §9 names
   class-identity a FUNDAMENTAL ⇒ ZND-3 atomics candidate (reusable identity axis, not a one-off).
4. **Other-object enters-tapped statics** (Archon of Emeria, Nahiri's Lithoforming): `EtBState` is
   SELF-only (`_apply_etb_state` reads the entering card's own record) ⇒ new
   `EnterStateModifier{subject, direction, duration}` atom + executor lane — Type-1 new atom,
   own round, adversarial-gated. (§11: restriction stays on the RESTRICTING card — board-separation.)
5. **Confounding Conundrum** (per-player this-turn enter-count predicate — ZONE_COUNT_GE is
   current-zone, MOVED_TO_ZONE_THIS_TURN is per-object), **Moraug** (additional-phase verb),
   **graveyard-recursion landfall tail** ("if this card is in your graveyard and it's your turn" —
   self-zone+turn predicate), **as-though attack tail** ×1, **modal Choose-one tails** ×3,
   **may-play lane** ("You may play that card this turn" ×2 + additional-land-X ×3): each its own
   named item; several are /95-queue inheritors.

## Predictions (pre-registered; deviation = a finding, not a rounding error)
**[G-FM3/FM5 SUPERSEDE the first-draft numbers 478→≈430±15 / ≈0.40±0.015 / 0.215±0.025 — those were
computed before the gate's flip-set correction. BINDING numbers:]** T1–T4 land: register
478 → **445±8** (templateable rows counted mechanically from `/tmp/opencode/znd2_evidence.json`:
T1 20/25, T2 8, T3 1, T4 ≤8); PC-2 **0.387±0.015** (= 281/726 center); PC-1 **0.245±0.010** (= 69/282
center; EXACT predicted flip set of 16 cards listed in [G-FM5] — Kazandu Mammoth excluded, DFC
residual). Any card flipping OUTSIDE the 16-name set, or the register landing outside the band, is a
registered finding (flip-set bug or template over-reach), not a rounding error.

## Gates (binding exit criteria, /95 form)
M21: PC-4 0 diffs AND report content byte-identical vs `/tmp/opencode/grammar_m21_prechange.json`
(timestamp/latency/git_head exempt); T3/T4 disjointness argument must be test-pinned (M21
enters-tapped bytes). Core suite green (baseline 2579+23subtests, sibling ZND-1e); pyright 0 on
touched files; ruff Δ0; bucket module count 9→10 with `build_full_registry` registration
(coverage.py:95) + gen_buckets pins per house law; ZNR deterministic two-run (PC-9); register
arithmetic honest (−covered = exactly the T1–T5 registered rows); FIRST landfall scenario pack
(`znr_*_landfall.json`, per-set supply via the ZND-1e "set" key): a land entered fires the trigger
exactly once, an opponent land does NOT (direction falsifier, E1 single encoding).
**Fresh-eyes adversarial on DIFF + this spec before commit** (Type-1 rule; /98 proved the gate
catches rules-wrong encodings, not just ugliness).

## Dispatch & coordination
Single `coder` wave: NEW `templates_b7.py` + `test_templates_b7.py`; edits ONLY
`templates_b4.py` (T3) + `templates_b6.py` (T4) + `coverage.py` (registration) + 1 scenario pack +
INDEX.md/NUMBERS.md backfill. ability_tree.py / compiler.py / executor **untouched** (grammar
frozen, engine lane = sibling). DISPATCH GATED on sibling ZND-1e commit: coordination law —
`ls -t` mtimes <15 min on compiler/test_templates_b6 (observed 18:04/18:16, sibling live 18:49);
T4 shares test_templates_b6.py with the sibling's engine tests (different regions; rebase after
their commit, re-run their KickerLaneTest + Roost 603.2 pack as part of gates).

## ADVERSARIAL GATE RESOLUTIONS (this spec was the proposal; fresh-eyes read-only gate ran 2026-10-18)
Gate verdict: FM1 fatal-if-blind, FM2/3/4 patchable, FM5/6 registerable, FM7 clean. All addressed
BEFORE implementation, per the Type-1 rule. The T4 premise in the spec draft was **stale** — the
gate caught it, I re-derived the inventory at HEAD, and it corrected FM1/FM4.

- **FM1 (fatal) — T4 "add artifact" is a no-op.** HEAD `templates_b6.py:783-785` already matches
  `creature|enchantment|artifact|Aura|planeswalker|land|token` (verified at commit 3f0aeb8 — the
  infrastructure AUDIT's "creature/enchantment only" line was simply wrong; the gate caught what
  same-context reading missed).
  **RESOLVED**: T4 drops artifact-widening entirely; T4 is now **only** the name-referent head variant
  (`When <NAME> enters, if <NAME> was kicked, <tail>`, Jace/Chandra/Nissa — 4 rows) + tail-table
  additions for genuinely-new tails. The spec's own 15-min mtime law was correct to invoke; the
  spec body simply hadn't been rebased after the sibling's commit — now it is.
- **FM2 (patchable) — T1 landfall filter `TYPE_EQ "Land"` reads printed∪grant, no type-removal lane.**
  `quantity.py:628-641` TYPE_EQ = `identity.type_line` ∪ `type_overlay` (GRANT_TYPE is add-only; no
  −lane, unlike KEYWORD_HAS's printed∪granted−lost at :576). Breakage: a land token/copy whose
  `type_line` lacks "Land" ⇒ landfall MISSES (CR 603.8b wants live-characteristic check). No
  false-positive is expressible (no removal lane), so the round is safe-but-incomplete.
  **RESOLVED**: accept printed∪grant for ZND-2 (no ZNR card triggers the gap — no lands gaining/losing
  type mid-flight in this pool), ship a **falsifier test** (a land-typeless creature animated into a
  land, or a synthetic copy-token with no "Land" in type_line, must NOT fire) + a **gap-ledger entry**
  naming the missing type-removal lane. Do NOT claim full 603.8b conformance — claim "printed-Land
  ∪ granted-Land", honest.
- **FM3 (patchable) — register arithmetic center too optimistic.** The "≈430±15" and T1 "≈22" ignored
  per-card PC-1 blockers + a tail (Omnath "gain 4 life if first time this turn") absent from both the
  tail claims and the defer list. **RESOLVED** by pre-computing the exact flip set from the evidence
  JSON (below). Recomputed centers: T1 templateable **20/25** landfall rows (not 22), total
  templateable **33 rows** ⇒ register **478 → ≈445** (matches gate's ≈441±8; the 4-row spread is the
  enter-if/kicker tails T4 may or may not reach). Omnath's "first time this turn" tail ADDED to
  §deferred-5 (ordinal-resolution-count, new axis — not templateable).
- **FM4 (patchable) — T2 card list was partly hallucinated.** Gate corrected: real 8 equip-EtB cards
  = Cliffhaven Kitesail, Maul of the Skyclaves, Mind Carver, Ravager's Mace, Relic Axe, Scavenged
  Blade, Skyclave Pick-Axe, Utility Knife (evidence-verified). **Ravager's Mace**'s PC-1 flip is
  blocked by its deferred party static ⇒ it parses the EtB-attach row but the CARD doesn't flip.
  **RESOLVED**: list regenerated mechanically from `znd2_evidence.json`; flip arithmetic excludes
  cards with any residual non-T1-4 sentence.
- **FM5 (registerable) — PC-1 flip set must be face- and residual-aware.** Pre-computed (python over
  the evidence JSON, face-suffixed names folded, only cards whose EVERY sentence is T1–T4-covered):
  **exact flip set = 16 cards** — Akoum Hellhound, Canopy Baloth, Canyon Jerboa, Dreadwurm, Kazandu
  Nectarpot, Lotus Cobra, Makindi Ox, Murasa Sproutling, Prowling Felidar, Ruin Crab, Skyclave
  Geopede, Skyclave Relic, Spitfire Lagac, Taunting Arbormage, Territorial Scythecat, Utility Knife.
  ⇒ **PC-1 predicted 69/282 = 0.2447**, PC-2 **281/726 = 0.3871** — both BELOW the spec's earlier
  optimistic 0.215/0.40 centers' upper ends but the pre-registered band. Kazandu Mammoth (a DFC)
  DROPS (back-face residual). Band: PC-1 **0.245±0.010**, PC-2 **0.387±0.015**, register **445±8**.
- **FM6 (§9 one-encoding) — cross-table tail duplication.** "+1/+1 counter on this creature." already
  lives in `_CAST_TAILS` (b6:743) and b2b; a naive b7 tail table mints a 2nd encoding ⇒ §9 violation.
  **RESOLVED**: b7 uses a **shared tail registry** (import/reuse `_ETB_TAILS`/`_CAST_TAILS`; new tails
  append to the shared list), not a per-bucket copy. Exit-gate: the `+1/+1 counter on this creature`
  sentence must resolve to ONE tid regardless of head.
- **FM7 (clean, recorded) — T3 disjointness verified clean by the gate**: no "This artifact/enchantment
  enters tapped." in either set JSON, no artifact-lands, b4 patterns are exact full-sentence, no
  competing template. Not a failure; recorded as a passed check.
- **FM8 (exit criterion added) — CR 603.4 lifecycle unverified.** `_match_zone_change` (binding.py:
  1013-1028) matches endpoint pairs generically; the gate could not confirm a graveyard-origin ETB
  won't fire landfall from a hand/library trigger. **RESOLVED**: exit-gate now REQUIRES a targeted
  test (a land put into the graveyard from hand must NOT fire a landfall trigger; only battlefield→
  battlefield / hand→battlefield of a land entering fire) as a binding exit criterion.

**Net effect of the gate**: T4 shrank (FM1), predictions moved from optimistic hand-waves
(430±15 / 0.215 / 0.40) to **evidence-derived** (445±8 / 0.245 / 0.387), two new falsifier tests +
three new gap-ledger entries (type-removal lane, ordinal-resolution-count, lifecycle CR 603.4) were
registered, and the card list was de-hallucinated. This is exactly what /98 proved the gate is for.
