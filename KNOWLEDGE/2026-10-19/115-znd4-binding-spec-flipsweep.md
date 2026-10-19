# 115 — ZND-4 BINDING SPEC: flip-sweep round — clear the ONE-ROW-AWAY cards by yield rank; Batch A = verified parse gaps (exact flip list), Batch B = named-shape tail sweep (band); M21 shared-regex protocol activated

**SPEC-GATE REVISIONS (2026-10-19, gate ses_eadc5139…, SPEC-GO after patch — all landed below with
[G-FM#] marks; census re-verified at HEAD 3931bda: 353/102 unchanged; /tmp/opencode/znd4_one_away_v2.json
is now the dump of record).**
- **[G-FM1] T2 keyword-list WITHDRAWN from Batch A** → named lane defer **ZND-4a**: `KeywordOutcome`
  carries ONE enum (templates_b1.py:191), registry returns one outcome per match
  (templates.py:237–248), compiler skips outcome merging (compiler.py:1794) — "Flying, vigilance"
  needs a multi-keyword MECHANISM (schema change = Type-1, fused double-atom = §9 volume-3 violation);
  neither decided here. (Real rows: Emeria Captain "Flying, vigilance", Tuktuk Rubblefort "Defender,
  reach", Ghastly Gloomhunter "Flying, lifelink" — 3 flips parked.)
- **[G-FM2] Sneaking Guide RECLASSIFIED A→B**: carrier hardcodes FNot(IS_SOURCE) ("another"); a
  regex-only widen compiles a DIFFERENT ability (self excluded) — falsifier must pin **self-as-legal-target**.
- **[G-FM3] b9 priority PINNED = 116** (ladder 100/110/112/114; default 100 would tie b1 and the
  tid-asc tiebreak silently starves b9 rows a widened b1 also matches).
- **[G-FM4] name corrections**: shape-4 gain-life one-away = EXACTLY Blight-Priest + Scion (2 flips);
  "Arbormage" = Taunting Arbormage (conditional on MANDATE_BLOCK lane accepting the effect, else defer).
- **[G-FM5] citation fixes**: b5a:2175 is "Destroy all Equipment attached…" — NOT Ondu's all-permanents
  (honest stop pre-declared → named defer); Beyeen Veil rides the REAL anthem lane (compiled
  "get ±P/±T UET" tids), citation fixed there. Bala Ged b5b:2937 verified correct (builder
  branch-extension, tid-stable).
- **[G-FM6] Relic Robber → defer ledger**: its token text carries TWO quoted innates ("This token
  can't block" / upkeep-attack) = quoted-text family, C-lane.
- **[G-FM7] fuzz re-run gate**: Beyeen Veil is a DFC (fuzz crash class @3931bda) — post-wave run
  `--set ZNR` fuzz on the flipped pool; flipped-DFC cast paths re-probed, not assumed.
- **REVISED PREDICTIONS**: Batch A **9–10** (T1 2 + T3 2 + T4 3 + T5 Broken-Wings/Bala-Ged 2, +Ondu
  iff scope-verify passes); Batch B **8–16** (named shapes incl. Sneaking Guide, excl. Relic Robber);
  **flips 17–26 ⇒ PC-1 101–110/282 (0.3581–0.3901)**. M21: 0-diff or per-card audited re-baseline.

---


Evidence: /tmp/opencode/znd4_one_away.json (102 rows, baseline commit 14c4af2) + /114 census +
analyst reuse audit ses_eaddda70… (class table A13/B63/C17/D2/eng7; carriers file:line-verified).
Spec method /95; deferral law /113; compiled≠executing law (PITFALLS 2026-10-19); shared-index
law (PITFALLS) — stage→commit atomically, siblings are live.

## WORLD-CANONICAL + ledger constraints (binding)
- Batch A rows route to CARRIERS ALREADY EXECUTED elsewhere → carrier's existing executor falsifier
  covers FM2; implementer must NAME the carrier per row in the tid docstring.
- EXCLUDED (do not touch, do not "accidentally" widen into them): cross-sentence anaphora 5+15 rows
  (ENGINE splitter lane — compiling them single-sentence mints PHANTOM REFERENTS, /103g trap);
  C-vocabulary 17 rows (no atom has §9 volume ≥20 — biggest: SPELL-kind predicate 9, history-census
  7, blocker-legality FILTER-compound 6 — named future rounds); D-ledger ZND-3d/e/f/g rows.
- **M21 blast radius is REAL this round** (shared-regex widens in b1/b5a/b2a/b2b/b3/b4/b5b/b5c):
  pre-wave snapshot `--set M21` → /tmp/opencode/m21_pre_znd4.json; post-wave PC-4 must show 0 golden
  diffs; ANY re-baseline must be enumerated card-by-card with the sentence whose tid changed and an
  abilities-only audit; a widen that changes an M21 card's tid WITHOUT semantic change is a refactor
  — prove via tree diff, else revert to card-scoped template (house default: NEW templates live in
  bucket **b9**; widens of existing shared regexes are allowed ONLY where the audit names a carrier
  and the M21 diff stays 0).

## Batch A — parse gaps (EXACT flip list; 13 cards; every row has a carrier)
- **T1 equip-activation cost-width** (2): Scavenged Blade, Skyclave Pick-Axe — carrier
  templates_b5a.py `^Equip \{(\d+)\}` single-colorless-symbol backref → widen to mana-symbol seq.
- **T2 keyword-continuation lists** (3): Emeria Captain, Ghastly Conscription, Tuktuk "the Falls" —
  carrier b1 bare-`Flying.` KeywordOutcome; the comma/and-joined multi-keyword row is unrouted;
  implementer finds the exact row text in the dump, emits N KeywordOutcomes.
- **T3 EtB gain-N-life permanent-token width** (2): Skyclave Cleric//Basilica, Turntimber Ascetic —
  generic twin compiled for Aura (b2a:2431) and Land (b2b:2317).
- **T4 as-long-as-another-[class] statics** (3): Expedition Champion/Healer/Skulker — carriers
  b4:1491/1513 + FNot(IS_SOURCE) primitive (b2a:591).
- **T5 A-misc routing** (3+): Broken Wings (b5c:3185 artifact-or-enchant → +creature-with-flying
  filter), Bala Ged Recovery (b5b:2937 alternation width), Sneaking Guide (b3:1254 minus "another").
  Ondu Inversion destroy-all: carrier b5a:2175 is EQUIPMENT-SCOPED — verify all-permanent scope
  first; NOT compiled ⇒ honest lane-stop (named defer), do not force (audit risk-1).
- A-misc that are NOT A: Nimble Trapfinder/Seafloor Stalker compound-block lines → C lane
  (blocker-legality); excluded.

## Batch B — named-shape tail sweep (BAND 8–16 flips; new builders live in bucket b9; each ships
an EXECUTOR-observed falsifier per the compiled≠executing law — build-only tests are rejected)
1. EtB put +1/+1 counter on target creature — Dauntless Survivor (+multi-row siblings).
2. EtB target creature gains indestructible until end of turn — Angelheart Protector (grant-until-
   EOT lane b2b exists).
3. "Equipped creature has <keyword>" — Cliffhaven Kitesail (b7 equip-EtB carrier family — SAME
   bucket, cheap extend).
4. Gain-life TRIGGER "Whenever you gain life, <effect>" — Marauding Raptor/Scion siblings (event
   carrier b2b:2624 compiles the EVENT).
5. Census×damage — Kabira Takedown "damage equal to the number of creatures you control" (QCount
   :864 × DEAL_DAMAGE — resolve-pin test like b8's X-arithmetic).
6. Verb-SEQUENCE tails (Scry 2, then draw a card — Deliberate; Seq lane exists).
7. Anthem −2/−0 "Creatures your opponents control get −2/−0 UET" — Beyeen Veil (b3:1047 SET_PT/PT
   anthem lane).
8. "If you control a <class>, draw a card" — Chilling Trap (subclass-count condition + draw).
9. Negate "Counter target noncreature spell" — Negate (FNot(TYPE_EQ) into b5a:1553 COUNTER).
10. Arbormage "When it enters, if it was kicked, <mandate>"-class via WAS_KICKED (b5a carrier +
    ZND-1e WAS_KICKED lane) — ONLY if the mandate-block verb lane accepts the effect (MANDATE_BLOCK
    :237); else honest defer.
Per shape: if 3+ register rows share it → generic template; 1–2 rows → exact-text template (house
convention, phantom-law census attached).

## Predictions (binding; recompute flip list at dispatch vs committed report — /107 delta law)
- Flips: **Batch A exactly {T1 2, T2 3, T3 2, T4 3, T5 ≤3} ⇒ 10–13**; **Batch B 8–16**;
  PC-1: 84 → **102–113/282 (0.3617–0.4007)**. Flips outside the union of named cards = FINDINGS.
- Register: −(flips + shared-row count); pre-compute shared rows for the 10 B-shapes against the
  full 353 at dispatch; publish the number in the dispatch prompt.
- PC-2 follows mechanically; M21: PC-4 0-diffs OR enumerated per-card re-baseline audit.
- Determinism two-run; suite; packs +1 new falsifier pack (executor-observed effect for one B
  shape, direction-pinned); pyright 0; ruff Δ0 (truth-basis per /113 FM8); gen_buckets additive.

## Gate set (full)
Fresh-eyes on SPEC before dispatch (this file); fresh-eyes on DIFF before commit (artifact =
`git diff --cached` — live-sibling law); FM2-class falsifiers per B-shape (executor or pack, not
assertIsNotNone); tid attribution table complete (every cleared row names its template or names its
stop); deferral ledger re-verified unparsed post-wave.

## Coordination
Siblings live (HAS_KICKER fuzz lane, aura-target pack). Dispatch pre-check: mtimes + `git log -1`
+ KNOWLEDGE/<date>/ scan; commit ATOMIC path-scoped (shared-index law). Files touched: shared
carriers b1/b2a/b2b/b3/b4/b5a/b5b/b5c (widens ONLY at the named carrier), NEW templates_b9.py +
test_templates_b9.py, coverage.py, pack, reports.
