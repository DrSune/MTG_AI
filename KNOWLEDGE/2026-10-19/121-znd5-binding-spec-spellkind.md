# 121 — ZND-5 BINDING SPEC: spell-kind round — CastSpellEvent + TYPE_EQ/SUBTYPE_EQ ALREADY express the conjunctive families (verified); ~13 rows template-lane, 2 named lane-defers (mana-restriction, targeted-by event); no new atom expected

**SPEC-GATE REVISIONS (2026-10-19, gate ses_eacd7917…, SPEC-GO after 4 blocking fixes — all landed
here):**
- **[G-A4] COPY HAS NO EXECUTOR DISPATCH AT ALL** — `Verb.COPY` never dispatched
  (executor/__init__.py:228–237) and the stack vocab-gate EXCLUDES COPY-bearing cards from
  executable resolution (stack.py:510–538, seed-96 crash). The spec's earlier "copy lane b5c:3380"
  was compile-emitted-only. **Lithoform Engine → immediate ZND-5a defer**; future copy-spell work
  is an ENGINE lane (stack-write + copy-object + retarget decision), never a template job. PITFALLS
  carries the trap.
- **[G-A5] Anticognition evidence was TRUNCATED in the dump** — real oracle adds "If an opponent has
  eight or more cards in their graveyard, INSTEAD counter that spell, then scry 2." ⇒ two register
  sentences: **s1 (counter-or-pay + FOr TYPE_EQ) compiles via existing lanes** (payer-seat safe,
  flat {2}, verbs.py:1926), **s2 (instead/threshold/scry replacement-window) → ZND-5e named defer**.
  Card is 2-row residue ⇒ s1 feeds PC-2, not a flip.
- **[G-A3] Master of Winds RECODED**: oracle = "base power and toughness become 4/1 or 1/4" =
  may + TWO-WAY PT-PAIR CHOICE FORK — not a tail reuse → **ZND-5f named defer**.
- **[G-A1] OR-precedent recited**: the real disjunction precedent is `FOr(TYPE_EQ Instant,
  TYPE_EQ Sorcery)` at templates_b5a.py:396–410 (tids :2071/:2082; FOr evaluated at
  executor/binding.py:221) — NOT the Quirion-Dryad COLOR_IN atom earlier cited. 3-branch
  type∪subtype FOr is novel but structurally trivial; **filter referent gate-verified**:
  `_match_cast` (binding.py:957–990) reads the SPELL card for TYPE_EQ/SUBTYPE_EQ/COLOR_IN —
  "Wizard spell" = SUBTYPE_EQ (TYPE_EQ("Wizard") would silently NEVER-fire — that trap is now
  a required falsifier axis: matching-kind positive AND negative).
- **[G-A7] priority direction verified**: templates.py:227 sorts (−priority, tid) ⇒ b10=118 runs
  BEFORE b9/b1; regex-disjointness from Cat/Dog/noncreature heads is a MUST (probe pinned).
- **REVISED PREDICTIONS**: Batch A **5 flips** (Umara Wizard, Windrider Wizard, Relic Amulet,
  Rockslide Sorcerer, Umara Mystic), Batch B **0–1 flips** (Anticognition s1 = rows-only), ⇒
  **PC-1 109–110/282 (0.3865–0.3901)**, register −7..−10 (publish per-tid attribution).

---


Baseline: 432d0e9, register 333, PC-1 0.3688 (104/282). Dumps: /tmp/opencode/znd5_spellkind.json
(13 rows), /tmp/opencode/znd5_one_away_v3.json (82 cards). Method /95 + /115 (flip-yield). Laws:
compiled≠executing, phantom, shared-index v2 (work /tmp/staging → move at green; commit atomic
path-scoped — two capture incidents /113//119).

## Existing-vocabulary verification (orchestrator, this session)
`CastSpellEvent(filter, actor)` carries filter-atoms DIRECTLY (templates_b2b.py:1222 builder:
`filter=FAnd(TYPE_EQ "Creature", SUBTYPE_EQ subtype)`); an OR-LIST color filter ALREADY COMPILES
("spell that's white, blue, black, or red", b2b:2536). CR: "instant"/"sorcery" are CARD TYPES ⇒
TYPE_EQ("Instant")/TYPE_EQ("Sorcery"); "Wizard spell" = SUBTYPE_EQ("Wizard") over the cast spell
object. ⇒ conjunctive lists = composition over EXISTING atoms. **No new atom in this spec.**

## Batch A — cast-trigger conjunctive family (6 flips — same head, tail builders reused)
Head: "Whenever you cast an instant, sorcery, or Wizard spell, <tail>" → CastSpellEvent(
filter=FOr-ish composition per the b2b:2536 PRECEDENT — implementer uses the same composition the
color-list uses), tails REUSE existing effect builders: gains flying UET (Umara Wizard//Skyfalls,
carrier: keyword-grant UET lane), may-draw (Windrider Wizard, draw lane), base-power-set UET
(Master of Winds — "power becomes base 4"? READ the exact row; if base-power lane missing → defer
named), charge-counter (Relic Amulet, counters lane), 1-damage (Rockslide Sorcerer, damage lane),
+2/+0 UET (Umara Mystic, PT lane). Falsifier law: executor-observed per PITFALLS (event fires only
for matched kinds — one NON-matching cast per trigger board must NOT fire: falsifies always-fire).
Exclusions: Umara rows are MDFC — face-aware compile only, fronts carry these rows ✓.

## Batch B — spell-kind-filtered targeted/other rows (4–7 flips)
- Anticognition "Counter target creature or planeswalker spell unless its controller pays {2}" —
  COUNTER_SPELL (b5a:1553) + unless Cost + FOr(TYPE_EQ Creature, TYPE_EQ "Planeswalker"); FLAT
  amount ⇒ payer-seat SAFE (ZND-3d is the QUANTITY-scaling class only — say so in the tid docstring).
- Lithoform Engine "{3},{T}: Copy target instant or sorcery spell you control" — COPY lane
  (b5c:3380/b6 copy-exception) + stack target filter. **If copy-SPELL (vs copy-permanent/token)
  has no executor lane → NAMED DEFER ZND-5a, do not encode a copy that doesn't copy (FM2 law).**
- Sea Gate Stormcaller EtB "copy the next instant or sorcery spell with MV≤2 you cast this turn,
  if you do..." (+ its kicked twin row "copy that spell twice instead" = cross-sentence referent —
  EXCLUDED, anaphora lane) — next-spell replacement-effect lane: likely NEW MECHANICS (replacement
  duration) ⇒ pre-declared honest stop: DEFER named ZND-5b unless lane proven first.
- Kaza, Roil Chaser "{T}: The next instant or sorcery spell you cast this turn costs {X} less…" —
  next-cast cost waiver + ZND-1g X-declaration ⇒ same replacement-window question as Stormcaller ⇒
  ZND-5b family; cost-lane may make it cheaper — verify-or-defer, no forcing.

## Explicit defers (named, this round)
- **ZND-5c** Base Camp "Spend this mana only to…" — mana-restriction lane absent (census: full
  register rows matching "spend this mana only": run at dispatch; if ≥6 → propose lane as its own
  spec, else stay).
- **ZND-5d** Myriad Construct "When this creature becomes the target of a spell" — targeted-BY
  event absent (register volume 1–2) — named.
- ZND-5a/5b: per batch-B verification results (copy-spell / next-spell-replacement lanes).
- Carried: ZND-3d/e/f/g, ZND-4a/b/c/d, anaphora (engine splitter), Blood Beckoning probe row.

## Predictions (binding; recompute at dispatch vs committed report)
- Flips: Batch A **5–6** (Master-of-Winds conditional), Batch B **1–3** ⇒ PC-1 **110–113/282
  (0.3901–0.4007)**. Register: −(13 − deferred rows), publish per-tid attribution.
- M21: new bucket **b10 priority=118**; widens only where a carrier is NAMED; PC-4 0-diff or
  per-card audited re-baseline. Fuzz re-run if any MDFC flips (Umara pair are MDFCs — G-FM7 law).

## Gate set (full, /115 form)
Spec fresh-eyes BEFORE dispatch; diff fresh-eyes (`git diff --cached`-pinned) BEFORE commit;
executor-observed falsifiers all new effects (non-matching-cast non-firing falsifier is the
P0 shape — an always-firing cast-trigger = the T6 class); b10 registry laws (priority, disjointness
vs ALL buckets — the conjunctive head must not steal the Cat/Dog/noncreature rows: priority-order
probe REQUIRED); defers re-verified unparsed; suite+packs+two-run determinism; pyright 0; ruff Δ0
truth-count; gen_buckets additive.

## Coordination
Siblings were live in engine lane all night (fuzz/menace/MDFC/aura). Pre-dispatch: mtimes +
git log -1 + spec-scan; if a wave is mid-landing on compiler files, HOLD. Stage→commit atomic,
path-scoped (capture laws v2). Files: templates_b10.py NEW + test, coverage.py, batch-A carrier
tails (b2b event-builder extension via builder-call, NOT regex edits — b2b's head pattern is
_exact per card, new conjunctive head goes in b10), pack, reports, docs.
