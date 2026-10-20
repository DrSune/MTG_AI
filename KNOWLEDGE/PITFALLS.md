# PITFALLS — standing traps (each dated; newest first)

## 2026-10-05
- **[Scenario `damage` is live-ledger truth; use `damage_received` for historical combat proof.]** `expect["damage"]` reads the executor's live damage ledger, which `end_turn()` cleanup clears. A pack that survives combat but asserts post-cleanup damage needs the additive `expect["damage_received"]` lane, which sums historical `KIND_DAMAGE` rows with `subject.namespace == "card"`.
- **[Partition `TARGETING` rows are audit evidence, not CR target designation.]** `ONE_OF` and `REST` selectors may emit `TARGETING` journal rows with `cause_verb="ONE_OF"` or `cause_verb="REST"`, but `TargetingEvent` triggers match only `cause_verb == "TARGET"`. Query, legality, and count resolution must not journal partition choices; only real partition-applying verbs pass `journal_partition=True`.
- **[Branch matcher must filter partition rows by selector mode.]** `ONE_OF` and `REST` evidence is grouped by `(row.cause, row.verb)` and then filtered against the requested selector mode. A singleton `REST` complement must never be allowed to fake a lit `ONE_OF` branch.
- **[C2 source-referent selectors need the neutral zone, not battlefield.]** A selector with `referent="source"` must use `Zone(ZoneKind.ANY, ControllerRef.ANY)` in `__post_init__`; using battlefield-only zones fails with `C2: referent pin requires a neutral zone` even when the card is on the battlefield.
- **[A narrow anaphoric `REVEAL` inside an open `LOOK_AT` window must not overwrite the wider population.]** Garruk's Harbinger regressed when a later `REVEAL count=1` replaced the wider look window, collapsing `ONE_OF` and making `REST` resolve empty. Look-window updates are population-preserving, not replace-the-window.
- **[Suspect directories can be intentionally red.]** The scenario gate scans only `tools/scenarios`; `tools/audit/suspects` is an adjudication lane. `2/3` there is the correct current state while Malefic Scythe × Wildwood Scourge remains a pinned H3 bug.

## 2026-10-01
- **[18b designation asks consume the scenario `decisions` queue in ARRIVAL
  order — and designation asks fire BEFORE the may-offer] (CR 601.2c/603.1
  ordering).** A misspelled or out-of-order word silently falls back to
  `vocab[0]` (deterministic but WRONG), so the pack fails as a mysterious
  counter/power mismatch, never as a loud ask error. When repatriating a
  TARGET trigger: write decisions in ask order (target pick(s), then
  'fire'/'skip', then CHOOSE indices), or give NO decisions when the
  designation is forced (one candidate / duel TARGET_PLAYER → auto-fill,
  no ask — `test_forced_single_candidate_never_asks` pins it).
- **[PC-8 is a compiler-side metric — executor work can NEVER move it.]**
  coverage.py counts POOL ENTRIES whose compiled IR carries a TARGET-mode
  selector (98/305 since the corpus froze); a designation channel changes
  zero IR bytes. Report the executor truth (crash→run card count, runner
  green count) and state PC-8 unchanged — do not promise PC-8 rises.
- **[QAtMost TARGET asks: the FIRST pick carries NO "NONE" token** (frozen
  C17 designation range 1..n — the query lane's pinned contract); later
  picks append it. Asserting the vocab SHAPE (not just the effect) pins
  the contract; answering NONE at pick 1 would silently take vocab[0].
- **[Trigger-firing contexts pre-bind `target` by an EVENT-KIND routing
  table: DAMAGE→dealer (16a), CREATURE_DIES→dead creature (18b).]** A new
  TARGET_PLAYER trigger must check the antecedent first — when the firing
  already carries one, `_designate` must NOT ask (asking would let a
  policy "choose" the player the rules already fixed; Massacre Wurm's
  "that player" is the dead creature's controller, not a decision).
- **[`test_executor_legality.py::test_unsupported_condition_pred_raises`
  uses a live unimplemented pred as its probe]** — implementing a pred
  (18b: CMC_GE) BREAKS it; amend it to the next unimplemented pred
  (LIFE_LEAD_OVER_START_GE / TURN_OF) following the file's AMENDED
  convention. Same trap pattern as 13c/14e.
- **[Pack `decisions` words may be PACK KEYS now (18b harness): resolved to
  the card's handle before the vocab check** — but a key that also reads
  like a raw word (never mind) is resolved ONLY if present in
  `runner.handles`; raw handle strings ("player:1") pass through.


## 2026-09-29
- **[subagent reports — report-body vocabulary can be HALLUCINATED while the
  CODE is correct.]** The r9-A completion report described "Verb.DO (48
  verbs)", "DurationKind.NEXT_PERMANENT_UNTAP", "SNOOP_TARGETS",
  "ActivationWindow PHASE_OUT", "ManaPolicy dataclass" — grep of the
  committed tree finds ZERO occurrences of those names; the actual diff
  implements the binding spec exactly (`Verb.MANA_POLICY` +
  `_MANA_POLICY_SCOPES`, `ActivationWindow={SORCERY,INSTANT}`,
  `QDistinctColorCount`, `GRANT_ACTIVATION`). Rule: before a dependent
  downstream phase (batch writing against grammar names), grep-verify the
  real symbol surface (`grep -n "class X\|X = " ability_tree.py`) and
  dispatch on the CODE's vocabulary, never the report prose; all gates
  (tests/measure) passing is the reliable signal, the narrative is not.
  Same round also confirmed the measure tool's per-run NUMBERS.md append
  (reports named grammar_2026-09-29.json after midnight rollover).

## 2026-09-28
- **[round-8-C — three construction-time validators bite before any test
  runs.]** (a) C2 is enforced in `Selector.__post_init__`: a `referent=`
  selector must be CHOOSE + **QConst(1)** + neutral zone — a plural
  anaphor ("cast them this turn") may NOT carry QUnbounded; the register
  plural is an executor-side reading, the IR stays QConst(1).
  (b) `FAtom` slot rules close `referent` to IS_ATTACHED_TO only — a
  "was a creature card" gate CANNOT carry referent="result"; the landed
  `B5b-if-it-type-then` convention is the conditional subject binds the
  result register by executor convention (C18 wording in 08 §Decisions
  describes semantics, not a new slot).
  (c) the b5b/b5c canonical-stability tests extract inner nodes from
  every COVERED outcome — a template returning `RuleReminderOutcome`
  (directive/marker rows) needs an `_inner_node` branch (reason string)
  or the test raises TypeError.
- **[round-8-C — quoted emblem lines vary at the sentence splitter.]**
  The two emblem sentences whose inner text ends mid-quote are split on
  the inner ". ": Liliana's [−7] row ENDS WITHOUT the closing quote
  (`…under your control.`) while Basri's/Garruk's carry `."`. A pattern
  requiring a closing `"` fullmatches only two of three. Use
  `You get an emblem with ".+$` (opening quote required, tail free) — one
  template, three shapes, C19 keeps all inner text out of the payload.
- **[tools/measure_grammar.py — every run APPENDS a PC block to NUMBERS.md
  under a fixed header.]** The tool auto-inserts its full PC table at the top
  of NUMBERS.md on every invocation, with the hard-coded section title
  "## <date> (T5 — Phase-1 grammar measurement harness)" regardless of what
  round is running. Three same-day runs (grammar baseline, mid-batch verify,
  post-refresh) produced three near-identical blocks, one mid-process with a
  legitimate PC-4 FAIL (pre-refresh 13 diffs). Rule: treat those blocks as
  per-run snapshots (newest first), do not delete or edit their content, and
  cap the day with a hand-written round-summary block + header caveat (see
  2026-09-28 round-6 entry). A header fix to the tool itself is an owner call
  (same file as the unfixed exit-code finding, 2026-09-27).
- **[ability_tree/serialization — `_OMIT_IF_EMPTY` is the WRITE-side omission
  driver; `_SPECS` `opt:` tags only inject None on READ.]** Refines the
  2026-09-25 entry: when adding a new trailing optional field to a serialized
  dataclass (R6-4 `DeclareBlockersEvent.blocked`), BOTH registrations are
  required: the `("field","opt:kind")` `_SPECS` entry (read path) AND the
  field name in `_OMIT_IF_EMPTY["Tag"]` (write path, `to_dict` ~L3320).
  Missing the `_OMIT_IF_EMPTY` half makes every pre-existing tree grow the new
  key on regeneration → golden byte-diff storm. Guard with a
  construction-and-serialize test asserting the key is ABSENT for None.
  (Discovered R6 grammar phase.)
- **[decision docs — tid module prefixes are GUESSES; bucket JSONs are the
  partition.]** Reconfirmed at scale in the round-6 batch: 9 of 13 rows
  registered in a module other than their doc tid (final: b5a 6, b4 4, b5b 2,
  b3 1, b2a 0 — e.g. Gadrak "can't attack unless…" and Kinetic "power is
  equal to…" are B5b-keyed, not B4). Rule: before writing a builder, look up
  the normalized shape key (digits→N, mana→C) in
  `/tmp/opencode/phase1_buckets/<B>.json`; register where the JSON says. The
  gen_buckets UNCOVERED/pattern overlap asserts catch violations only when
  regenerated — check first, save a rewrite. (Round-6 batch.)
- **[templates — spelled-out numbers ("two","eight","four") are NOT captured
  by digit normalization.]** Shape normalization maps DIGITS to N; number WORDS
  survive verbatim into the shape key. Builders for word-pinned sentences
  hard-code QConst per the Gnarled-Sage house precedent (round-6: Tome Anima 2,
  Thieves' Guild Enforcer 8, Gadrak 4). `+N/+N` and `{N}` ARE digit-captured
  and can be regex-grouped. (Round-6 batch results §"Pitfall confirmed again".)
- **[unittest — a helper named `_outcome` on a TestCase subclass is shadowed.]**
  `unittest.TestCase` defines `_outcome` (the `_Outcome` context manager factory);
  defining `_outcome(self, sentence)` in a test class turns every call into
  `TypeError: '_Outcome' object is not callable` at run time, not import time.
  Use `_match_one` / `_match_outcome`. (Discovered landing the R7-A b5a/b5b tests.)
- **[test files — Pyright needs bare `assert isinstance(...)`, not
  `self.assertIsInstance(...)`.]** Narrowing a union-typed IR node before touching
  `.pred`/`.field`/`.referent`/`.inner`/`.then_effect`: `self.assertIsInstance` does
  not narrow, so 116 `reportAttributeAccessIssue`s appeared in the three round-7
  test files; converting the guards to bare `assert isinstance(...)` took them to 0
  with zero behavior change. Same trick fixed b5b's `Conditional` checks.
- **[b2a test — the EXPECTED table's second column must equal `Template.name`
  verbatim.]** `test_expected_table_matches_registry` compares the card-name column
  to the template's `name`, so the descriptive tid-label ("Kinetic Augur ETB
  (discard up to two…)") fails the assertion; keep the template name equal to the
  bucket card name. (Hit when landing Kinetic Augur/Idol of Endurance.)
- **[ability_tree/_VERB_ROLES — `DurationUntilLeaves` exists but only GAIN_CONTROL
  wires a duration role.]** EXILE/MOVE_ZONE have NO `duration` role, so R7-A's
  "Exile that card until this creature leaves the battlefield." (Kitesail) and
  "…until this artifact leaves the battlefield." (Idol of Endurance) landed lossily
  without the leaves-play window; both builder docstrings carry the verbatim C11
  note. Wiring EXILE/MOVE_ZONE durations is an R8 grammar item.
- **[grammar — FIGHT is an effect verb with ONE role (`target` = the defender);
  there is no attacker role.]** The attacker is whatever the rule reminder implies
  (source for Brash Taunter, the result-register object for Primal Might's
  "Then it fights …"). Do not invent an attacker slot; document the binding.
- **[b5a test — a shape landing flips three independent pins at once.]** Covering
  five B5a sentences moved TEMPLATES 51→56, SHAPES COVERED 55→60, UNCOVERED 12→7,
  unique-tid counts 51→56 (twice: table + canonical-stability) AND rewrote the
  Finishing Blow end-to-end expectations (its 2nd sentence became covered → Seq of
  2 steps, 0 unparsed). Budget for five coordinated edits per landing batch.
- **[goldens — keyword-list coverage rows change the `keywords` KEY, not
  `abilities`.]** A `KeywordOutcome` folds into the card-level `keywords`
  array, so the R7-B Baneslayer/Sporeweb goldens diffed outside the `abilities`
  payload for the first time. The golden-audit rule is now: diffs allowed ONLY
  in the abilities payload — `abilities`, `emblem`, or `keywords` (r7-A emblem
  + r7-B keywords precedents). Anything else (identity, P/T, colors, cost) in
  a diff set = stop and investigate.
- **[grammar — the controller-role asymmetry: LOSE_LIFE takes a referent
  Selector in `controller` (controller-of-the-object, Gloom-Sower shape);
  CREATE_TOKEN has NO controller role at all.** "Its controller loses N life"
  encodes; "Its controller creates a token" cannot — creator is implicit +
  verbatim lossy (Necromentia precedent). `_VERB_ROLES` is validated strictly
  BOTH ways (missing-required AND extra roles raise), so build AtomArgs from
  the table, never from a doc sketch. DEAL_DAMAGE likewise has no source role
  (dealer = the amount-QProp's referent, executor-side).
- **[knowledge tree — VERIFY claimed doc edits landed; reports are not files.]**
  /06 recorded "Updated INDEX.md (+2 rows)" for r7-A, but INDEX.md's last
  change is the round-6 commit — the r7-A rows were never written (lost in
  that session's compaction). r7-B backfilled /03–/06 + added /07. Rule: every
  closeout claim (INDEX/PITFALLS/NUMBERS) must be `grep`-confirmed after the
  write, and the next session's orientation check should spot-check the newest
  INDEX rows against `ls KNOWLEDGE/<date>/`.


## 2026-09-27
- **[tools/measure_grammar.py — exit code is ALWAYS 0.]** The docstring promises
  "Exit code: 0 when every evaluated pre-registered target passes, 1 when any
  target fails", but there is no `sys.exit` anywhere in the tool — it prints
  `FAILED TARGETS: …` and still exits 0. Rule: gate on the printed
  `failed_targets` list or the report JSON, never on the shell exit code.
  (`grep -n sys.exit tools/measure_grammar.py` → no matches, 2026-09-27.)
- **[tools/gen_buckets.py — pins can go stale IN A COMMITTED STATE.]** The
  round-4 commit (6a267cd) grew b2a/b4 pattern coverage without bumping the
  tool's pinned asserts, so a PRISTINE HEAD worktree failed bucket regeneration.
  Symptom: AssertionError with your own changes stashed/reverted — that is
  HEAD's stale pin, not your edit. Reproduce on clean HEAD before touching any
  pin; bump with a dated comment. (Discovered round-5 batch: B2a 54→57 unc 8→5,
  B4 27→30 unc 20→17; bucket JSONs regenerated byte-identical.)
- **[docs/batch tables — a listed row can be ALREADY-COVERED, not just
  built-in-consumed.]** Extends the 2026-09-25 rule: doc-07 row 5 (Conclave
  Mentor "When this creature dies, you gain life equal to its power.") was in
  the batch table but already covered by a B2a trigger template — it was absent
  from the live queue. Implementing it as a second template would have created
  a PC-3 ambiguity violation. Rule: before implementing a batch row, grep the
  sentence in `tools/dump_unparsed_queue.py --set M21` output; the LIVE queue
  (not the doc table, not the bucket files) says what still needs a template.
  Effect: round-5 batch = 8 rows, PC-2 +8 not +9, residual 98/100 not 97/99.

## 2026-09-25
- **[ability_tree/FAtom — to_dict omits only zone slots.]** `FAtom.to_dict`
  omits ONLY `zone`/`from_zone`/`to_zone` when `None` (`_OMIT_IF_EMPTY`); the
  other slots (`who`, `count`, `string_value`, `color`, `colors`,
  `counter_kind`, `keyword`, `inner_filter`) always serialize their null/empty
  defaults. A bare `FAtom(pred, who=...)` serializes with `"count": None`
  (etc.) PRESENT, not absent. When pinning FAtom JSON in tests, assert absence
  for the zone slots and presence-with-null for the rest — asserting
  `"count" not in d` fails. (Round-5 grammar, hit twice in
  `test_ability_tree_r6.py`.)
- **[docs/queue — decision-table rows can be cross-bucket misassigned or
  built-in-consumed.]** Decision tables (e.g. 05's 20-row batch) assign
  sentences to buckets by phase-1 row allocation, not by where the sentence
  actually lands. The Double Vision s2 row ("You may choose new targets for
  the copy.") was assigned to B2b, but the concrete sentence buckets in
  `phase1_buckets/B4.json` — the B2b template covers it only set-level (the
  compiler dispatches by bucket; PC-3 = 0 confirms the mapping). Worse, one
  assigned row ("...attacks or blocks, choose one —") was already consumed by
  a `compiler.py` built-in (`_CHOOSE_ETB_RE`) and can never be templated.
  Rule: before implementing a doc row, verify the normalized key exists in
  the target bucket's `/tmp/opencode/phase1_buckets/*.json` UNCOVERED list;
  keep built-in-consumed rows in UNCOVERED with a "handled by built-in"
  reason. Per-bucket UNCOVERED counts are bookkeeping; set-level coverage
  (PC-3 / the queue dump) is ground truth. (Round-4 batch, 2026-09-25.)

## 2026-09-24
- **[git/golden — re-staging loses the pre-baseline audit state.]** When a
  batch re-baselines goldens via `tools/measure_grammar.py --refresh-goldens`
  and then `git add`s the refreshed files, the prior index blobs are
  replaced and `git fsck --dangling` recovers nothing — the "abilities key
  is the only changed key" audit can no longer be independently re-run
  against the staged baseline. Rule: before refreshing + staging goldens,
  copy the pre-state (e.g. `cp -r MTG_bot/core/golden /tmp/golden_pre_$(date +%s)`)
  so the structural audit stays reproducible. (Happened in the 2026-09-24
  round-3 template batch; audit was valid but done pre-staging only.)
- **[ability_tree.py — ruff format churn on first edit.]** The committed
  `ability_tree.py` was NOT ruff-format-clean at HEAD. The first edit in a
  session triggers the auto-formatter, which reformats the entire file
  (line-wraps every long `raise ValueError(...)` and reflows `_SPECS` /
  `_VERB_ROLES` / frozenset literals), producing a ~1200-line diff that
  buries the real change. `git diff -w` still shows most of it (the
  reflows are structural, not whitespace-only). Rule: review `ability_tree.py`
  changes by symbol (grep the new field/role/pred by name) rather than by
  diff size; don't be alarmed by a huge diff on that file. The file is now
  format-clean, so this is a one-time cost.
- **[tools/gen_buckets.py — stale pinned asserts after template growth.]**
  `gen_buckets.py` hard-asserts exact covered-key counts per bucket
  (`b2a_keys == 51`, `b4_keys == 26` at 2026-09-17). When template modules
  gain covered shapes, these asserts go stale and the script dies
  `AssertionError: B2a pattern keys=54`, leaving
  `/tmp/opencode/phase1_buckets/*.json` missing — which then makes ALL
  per-bucket test files fail (55 failed + 8 errors, all in
  `test_templates_b*.py`). Symptom to recognize: a mass of bucket-test
  failures with no production change is almost always missing
  `/tmp` bucket JSONs. Rule: after any template-module lands, re-run
  `python tools/gen_buckets.py` and bump the pinned asserts to the new
  counts (docstring counts drift too).
- **[measure_grammar NUMBERS.md — one section per run.]** Every
  `python tools/measure_grammar.py --set M21` run appends a fresh
  `## <date> (T5 …)` section to NUMBERS.md. A session with several runs
  produces several same-date sections (7 on 2026-09-24). The harness owns
  this format — do not hand-edit the tables; mark superseded same-date
  sections by appending a `— superseded by …` note to the header only.
- **[Goremand "double-parse" was a misdiagnosis.]** The 2026-09-23/03
  follow-up claimed the same sentence fed both a (wrong) TriggeredAbility
  and the correct CostSacrifice. Verified false: the two clauses are
  distinct sentences parsed by distinct per-card templates
  (B2a-goremand for the ETB, B5a-addl-cost-sacrifice for the cost),
  `ambiguities=()` for the card, and the trigger is correct under the
  binding EachPlayer rebinding contract (PITFALLS 2026-09-22, Goremand is
  the canonical example). No code change needed. Rule: when a prior note
  asserts a "double parse", re-derive from the live compiler
  (`compile_card` → per-sentence outcomes) before treating it as real.

## 2026-09-23
- **[compiler/pyright — Optional grammar field exposes latent non-None
  assumptions.]** Widening `SpellAbility.effect` to `Effect | None = None`
  silently invalidated latent non-None assumptions in the compiler's
  continuation-merge path: both the backward merge-target search and the
  merge branch dereference `ab.effect` and needed explicit guards
  (`ab.effect is not None` in the search; `if ab.effect is None: continue`
  in the merge), and the test helpers (`_seq`/`_choose`/`_atom` in
  `test_compiler.py`) needed their signatures widened to `Effect | None`
  in the same edit batch or the whole module fails static check. Rule:
  when widening a grammar dataclass field to `X | None`, audit every
  consumer path AND the test helper signatures in one pass — pyright
  reports the consumer errors but only after the test-file cascade.
  (SpellAbility-effect-optional, 2026-09-23.)
- **[golden/diff — single-line canonical JSON defeats `git diff`.]**
  Golden files are one-line canonical JSON, so after `--refresh-goldens`
  `git diff` shows the whole file changed with no hunk-level signal about
  which card or which key changed; and the post-refresh `AM` status means
  *index = pre-change baseline, worktree = refreshed* (do not read `A`
  as "staged my changes"). Targeted verification = structural JSON
  compare: parse `git show :path` (staged baseline) vs the worktree file
  and diff the objects key-wise. That is what proved only the `abilities`
  key changed in the 4 affected goldens. Resolve `AM` with
  `git add MTG_bot/core/golden/`. (SpellAbility-effect-optional, 2026-09-23.)
- **[M21.json — oracle id path.]** Card records live at
  `payload['data']['cards']` (397 records) and the oracle id is at
  `c['identifiers']['scryfallOracleId']` — there is no top-level
  `oracle_id` key on each record (see the 2026-09-14 entry for the
  `text` vs `oracleText` sibling trap). A blind `c.get('oracle_id')`
  silently maps 0/397 and makes every card name unmappable. (2026-09-23.)

## 2026-09-22
- **[measure_grammar/PC-4 — tautological golden check]** `tools/measure_grammar.py`
  calls `write_goldens` (full regenerate, overwrites) BEFORE
  `verify_goldens`, and `MTG_bot/core/golden/M21/` is untracked in git —
  so a measurement run's "PC-4 0 diffs" proves nothing: every run
  silently rewrites all 305 goldens and the same-run verify trivially
  passes. Real drift detection exists only in `test_golden.py`
  (write → tamper → verify). Do not cite harness PC-4 as evidence of
  golden stability; to check drift, run `verify_goldens` alone against
  the on-disk baseline BEFORE any write. (2026-09-22.)
- **[compiler/OutcomeSlot — `None` is a two-use sentinel]** A `None`
  outcome slot in `compile_card` must mean *unparsed* and nothing else.
  The choose-opener wrapper originally marked consumed option slots
  `None`, and the post-fold `unparsed` reconstruction (`outcome is
  None`) then reported every consumed bullet as unparsed while the
  opener vanished from the report (6 tests failed). Fix: dedicated
  `_OptionConsumed` sentinel (`_OPTION_CONSUMED`, `__slots__ = ()`);
  `_OutcomeSlot = SentenceOutcome | _ChooseOpenerOutcome |
  _OptionConsumed | None`. Any future "consumed/handled" state needs
  its own type, never `None`. (choose-opener, 2026-09-22.)
- **[ability_tree/EachPlayer — BINDING SEMANTIC CONTRACT]** Inside an
  `EachPlayer(ref, effect)`, the referent `YOU` in the inner effect rebinds to
  the iterated player (so `EACH_PLAYER(ALL_OPPONENTS): SACRIFICE(... 
  CONTROLLER_IS(YOU) ...)` means "each opponent sacrifices a creature THEY
  control" — e.g. Goremand). The tree text alone reads "a creature you control";
  the executor AND the trained model MUST implement this rebinding or the
  encoding is silently inverted. Never "simplify" such trees by lifting the
  inner effect out of the EachPlayer wrapper. (T7 2026-09-22.)
- **[compiler/MoveState]** `Verb.MOVE_ZONE` roles = {cards, destination} and
  `Verb.SEARCH` = {cards, destination, controller}: there is NO tap-state
  parameter, so "put that card onto the battlefield TAPPED" currently encodes
  the tap state as a silent loss (Solemn Simulacrum, Fabled Passage). Round-2
  grammar item: optional tap-on-enter role. Until then, do not add templates
  that promise tap-on-enter semantics the grammar cannot carry.
- **[review/Renderer]** Ad-hoc tree renderers must be verified against the
  canonical JSON BEFORE drawing semantic conclusions — three field-name bugs
  (`OptionalEffect.inner` not `.effect`, `Choose.options` are plain effects
  with no labels, cost `amount` not `count`; plus `PtDelta.magnitude`,
  `CostModifier.controller_ref`) produced false "empty effect" readings.
  (T7 2026-09-22.)

## 2026-09-21
- **[ability_tree/MOVE_ZONE]** Verb.MOVE_ZONE takes roles ('cards', <selector>) and ('destination', <zone>).
- **[runtime/memory]** Never run standalone diffusion or large PyTorch scripts concurrently with vLLM unless available RAM > 40GB.
- **[tools/gen_buckets]** When test suite fails with missing /tmp/opencode bucket files, run 'python tools/gen_buckets.py' to regenerate all 8 buckets.
- **[ability_tree/Effect]** Leaf effects must be constructed as Atom(verb=Verb.*, args=AtomArgs(...)), never Effect(...).
- **[test_templates/CostLoyalty]** Always use assertEqual for dataclasses (CostLoyalty, DurationEot); assertIs is only valid for Enum singletons.
- **[ability_tree/PtDelta]** PtDelta uses field 'magnitude', not 'amount'.

## 2026-09-19
- **There is no ruff config file anywhere, yet `ruff check` runs an ALL-style
  ruleset (~826 rules; line_length 88).** ruff 0.16.7 (uv tool at
  `/home/sune/.local/bin/ruff`) resolves `SIM114`/`I001`/`TRY004`… on files with
  no config discoverable (verified from a bare /tmp dir; no `ruff.toml`, no
  `[tool.ruff]`, no env var). Consequence: `ruff check` on
  `MTG_bot/core/ability_tree.py` was **already failing at git HEAD (40
  findings)** — the module's pinned `ValueError`-based type validation trips
  TRY004 (which demands `TypeError`) and the pinned test suite asserts
  `ValueError`, so converting is forbidden. Interpret any "ruff check clean"
  gate as: *no new violation kinds beyond the pre-existing ones* +
  `ruff format --check` passes (it does). Do NOT mass-`noqa` or rewrite the
  module's validation style.
- **`# noqa: SLF001` is a live RUF100 (unused-noqa) trap in this
  environment.** SLF001 is not in the resolved ruleset, so the noqa directive
  is "unused" and fails `ruff check` (caught 7× in
  `test_ability_tree_t3.py`; removed). Only add `# noqa` for rules that are
  actually enabled — check with `ruff check --select <rule> file`.
- **pyright `# type: ignore` must sit on the line of the bad argument, and
  ruff auto-format can move lines after each edit.** When an edit triggers
  the formatter hook, multi-line calls get re-wrapped (one arg per line) and
  an ignore placed on the call-opening line stops matching the reported
  error line. After any batch of edits, re-run pyright and move the ignores
  to the final line positions (pattern used for the rejection catalog in
  `test_ability_tree_t3.py`).
- **`EtBState()` no-op is a grammar error, not a default.** Entering the
  battlefield "as normal" is expressed by having *no* EtBState node; an
  empty EtBState is rejected by `__post_init__`. (T3 round 1 decision,
  pinned by `test_t3_rejections[etb_noop]`.)

## 2026-09-18
- **`PtDelta` uses `magnitude`, not `amount`.**
  `MTG_bot/core/ability_tree.py` defines `PtDelta(direction: PtDirection, magnitude: Quantity)`.
  Repeated pyright errors in `test_templates_b2b.py` (`Cannot access attribute "amount" for
  class "PtDelta"`) were fixed by using `magnitude`.
- **Repeated `Atom.args.get(...)` expressions are not reliably narrowed by pyright.**
  Writing `atom.args.get("q").value` more than once can produce
  `Cannot access attribute "value" for class "object"` or
  `"value" is not a known attribute of "None"`. Bind the extracted value to a local variable or a
  typed helper (e.g. `_qconst(...)`) before accessing it.
- **`assertIs` on freshly constructed frozen dataclasses recurred in B2b.**
  `assertIs(x, DurationEot())` failed with `AssertionError: DurationEot() is not DurationEot()`.
  Use `assertEqual` for frozen dataclasses; `assertIs` is safe only for enum singletons. See the
  2026-09-17 B2a entry.

## 2026-09-17
- **`assertIs` on freshly constructed frozen dataclasses always fails.**
  `self.assertIs(x, DurationEot())` / `assertIs(x, FAtom(...))` compare
  *identity*; frozen dataclasses mint a new instance per call, so the check
  can never pass. Use `assertEqual` (dataclass field equality). `assertIs` is
  only safe for enum members (true singletons: `CounterKind.*`, `Verb.*`,
  `ControllerRef.*`, `Phase.*`). Caught in `test_templates_b2a.py`
  (3× DurationEot, 3× FAtom) before first green run.
- **`template.build({})` is not a valid IR probe.** Builders read
  `group.group("name")`, so passing a bare dict raises
  `AttributeError: 'dict' object has no attribute 'group'`. The only faithful
  driver is `TemplateRegistry.match(<concrete sentence>)` with real regex
  group context (see 2026-09-17/02-test-templates-b2a.md).
- **Mixed import paths split class identity → `KeyError` in
  `canonical_json`/`to_dict`.** An ad-hoc script that mixes `sys.path`
  top-level imports with package imports (`MTG_bot.core...`) creates two
  distinct class objects for the same name; `to_dict`'s `_TAG` registry is
  keyed by the first class, so the second raises `KeyError: <class
  'TriggeredAbility'>`. In tests/scripts, use one consistent import style
  (package imports). Not a product bug — a tooling artifact.

## 2026-09-15
- **Session 4: pyright does not narrow on unittest assertions.**
  `assertIsInstance`/`assertIsNotNone` narrow at runtime but are invisible to
  pyright, so attribute access on the `Ability`/`Effect`/`Filter` unions stays
  a static error. Use explicit `isinstance` guards (raise on mismatch) or
  typed helper functions — `test_compiler.py` uses `_spell`, `_seq`, `_atom`,
  `_selector`, `_fand`, `_cost` for this.
- **Session 4: `compile_pool` emblem attachment needs two passes.** The pool
  is name-sorted, so an owner ("Basri Ket") precedes its emblem ("Basri Ket
  Emblem"). Building the `cards` dict interleaved with emblem processing
  captures the owner before `results[owner_oid]` is replaced with the
  emblem-bearing copy, leaving `card.emblem is None` while the summary still
  counts 3 emblems / 0 orphans. Pass 1 attaches emblems to `results`; pass 2
  builds `cards` from the updated results.
- **Session 3: sentence splitting must be paren-depth-aware.** The old flat
  rule `(?<=[.?!])\s+|\n` over-splits multi-sentence parenthetical reminder
  text. The current M21 baselines are **927/503** file-level and **639/510**
  pool-level; the old **952/509** and **655/516** baselines are superseded
  (see `2026-09-15/02-ingest-review-fixes.md`). Any future split change is
  still a knowledge-tree event, not a silent bugfix.
- **Session 3: dedup must compare captured fields, not raw JSON.** Reprint
  duplicates differ in uncaptured fields such as `number`, `uuid`, `rarity`,
  and `purchaseUrls`; raw-dict equality would treat all 112 duplicate records
  as corruption. Conversely, deduping on oracle id alone could hide true
  conflicts. `ingest_pool` uses explicit `_dedup_key` over captured
  `RawCard` fields and raises only when captured fields differ.
- **Session 3: MTGJSON emblems are not tokens.** `layout == "emblem"` is
  distinct from `layout == "token"`. M21 has 17 token records and 3 emblem
  records. Emblems carry owner names only in `relatedCards.reverseRelated`;
  `ingest` exposes them as `related_names`, not as ordinary card names.
- **M21.json has 112 reprint-duplicate oracle ids (397 records → 285 unique
  cards).** A naive oracle-id-keyed build either silently drops 112 records
  (last-write-wins dict) or the spec's "417 entries" expectation is wrong.
  `ingest_pool` dedupes identical captured-field duplicates (first wins) and
  raises `StateCorruptionError` only on captured-field conflicts. When
  quoting "pool" numbers, say which level: file-level (417 records) vs
  oracle-keyed (305 entries). PC-1 denominator needs this decision at
  measurement time.
- **Sentence-split expectations pin the active split rule.** The historic
  952/509 file-level baseline is reproducible only with the old flat rule
  `(?<=[.?!])\s+|\n`; the current paren-depth-aware rule pins 927/503
  file-level and 639/510 pool-level. Changing the split changes PC-2's
  denominator — treat changes as a knowledge-tree event, not a bugfix.

## 2026-09-14
- **MTGJSON field is `text`, not `oracleText`.** This M21.json (v5 shape: `{"meta":…, "data":{…}}`)
  has no `oracleText` key; a blind `c.get('oracleText')` returns 0/397 and silently makes the whole
  pool look textless. The top level is `data.cards` / `data.tokens`, not `cards`.
- **`type` vs `types`:** `type` is the full type *line* string; `types` is the top-type list.
  Filter predicates over "Creature"/"Instant" must agree on which they read.
- **Legacy rule_engine failures are expected, not new.** 24 legacy failures (zone/keyword
  bookkeeping drift) predate Phase 1. Do not "fix" legacy code — it is attic'd at cutover.
  Work only in `MTG_bot/core/`.
- **Do not re-derive numbers from memory.** If a number is in NUMBERS.md, use it; if it is not,
  measure it with the command recorded next to it. The old repo's cardinal sin was unmeasured claims.
- **Subagents never compact.** Delegations must be bounded to their context budget (AGENTS.md §3).
  One module or one test file per delegation. Returns under 400 words.

## (carried from docs, verified in session 1)
- **English substrings cannot be the IR.** MTGJSON re-templated Oracle text so zero cards contain
  "enters the battlefield" and four legacy code paths tested for it — forty triggers silently dead
  for months. Hence structured EventSpec, never string matching. (ARCHITECTURE.md)
- **One representation for executor and encoder.** The `selector` vs `target` key mismatch made
  every targeted spell a silent no-op (7 of 397 cards targetable). The ability tree is that fix —
  do not let executor and encoder read different shapes. (DESIGN_CARD_POOL.md)
- **Re-ingest must not invalidate learned state.** Key everything on `scryfallOracleId`; golden
  files make re-ingest a visible diff, not a silent semantic change.

- **Quoted Oracle text ends inside the closing quote.** "…if able."" — the embedded rule's
  period sits BEFORE the closing quote, so a regex ending `\."\.$` never matches and the row
  silently stays in the queue. Also: raw-string patterns keep every backslash — `\\.` means
  literal-backslash-dot. Always fullmatch the concrete sentence pulled verbatim from the bucket
  JSON before trusting a quoted-sentence template. (2026-09-29 r9-B, Pursued Whale.)
- **unittest assertIsInstance does not narrow for pyright.** Test files in core/compiler are
  pyright-clean at HEAD; use `assert isinstance(...)` before attribute access on union-typed
  IR nodes in new test classes. (2026-09-29 r9-B.)
- **Verify the corpus text before declaring a measurement deviation.** Round-9 notes predicted
  PC-1 would miss by 1 because Seasoned Hallowblade "carries an Activate-only-as-a-sorcery tail";
  the actual M21 oracle text in the corpus has **no such tail** and PC-1 hit the binding
  prediction exactly (301/305). Grep the real card JSON in `MTG_bot/core/golden/M21/` (or the
  ingest corpus) before attributing a coverage delta to a phantom shape. (2026-09-29 r10.)
- **Legacy shared event-helpers silently default optional IR fields to None.** The r1-r2
  `_etb_event()` helpers (b2a/b2b) built `ZoneChangeEvent` without `subject`, so 62 "When this
  ~ enters" triggers meant "whenever ANYTHING enters" for ten rounds. When an optional IR field
  has semantic weight (event subject, referent, controller), make it a REQUIRED parameter of the
  shared helper — never rely on the dataclass default at call sites. Fixed R11-B by adding a
  required `subject: Filter` + corpus guard test_etb_subject_guard.py (empty allow-list).
  (2026-09-29 r11-B.)
- **Bulk sed edits leave pyright LSP diagnostics stale.** After sed-updating 40 `_etb_event(),`
  call sites, the edit-tool diagnostics kept reporting "Argument missing for parameter
  'subject'" against already-fixed lines. Verify with runtime pytest / the pyright CLI, not the
  cached edit-time diagnostics. (2026-09-29 r11-B.)
- **MOVE_ZONE needs the `cards` role ARG even when objects ride in `bindings`.** Atom role
  validation requires it; pass a placeholder `Selector(QConst(9), ALL, UNIV, ANY_ANY)` —
  bindings win at runtime. (2026-09-29 r12b.)
- **World counters key by `CounterKind.name`** (`"PLUS_1_PLUS_1"`, not `"+1/+1"`). (r12b.)
- **`TemplateRegistry()` is EMPTY** — compile tests need `coverage.build_full_registry()`. (r12b.)
- **One permanent = one compiled record.** A second, different-oracle `attach_card` on the same
  handle raises `ValueError` (the `(handle, idx)` binding key would silently clobber otherwise);
  tests must put a permanent's several triggers in ONE CardRecord. (r12b.)
- **LifeGained triggers whose effect gains life self-feed** → instant 200-fire RuntimeError;
  feed tests must use non-life effects (mill). (r12b.)
- **Ledger tombstones route through `_meta` (2026-09-29, 12d):** `DurationLedger.expire()`
  marks dormant ONLY ids present in `_meta`; before 12d an Eot/Permanent-tagged entry had
  no meta row, so `layers.detach_source` "expired" the layer while the materialized P/T
  entry LEAKED live forever. Rule: `record()` stores a meta row for EVERY entry (fallback
  `DurationMeta(tag, controller)`). Any future tombstone-style API must have a pinned
  effective_pt-after-expiry test (test_executor_layers.TestStaticAnthem covers it).
- **PREVENT_EFFECT has NO target role (2026-09-29):** grammar `_VERB_ROLES` = condition+event
  required, controller/duration/step optional. The affected set = the ctx's designated
  bindings ∩ IS_ANY_TARGET at cast time (`ctx.binding_handles("target")`), NOT an atom role.
  An atom built with `target=` fails Atom validation.
- **Replacement filters run in the REPLACEMENT's coordinates (2026-09-29):** the DEAL_DAMAGE
  atom's ctx carries the DEALER's controller — evaluating a Nine-Lives-style "to you" filter
  there is ALWAYS false. `replacement_for_player_damage` re-roots via
  `dataclasses.replace(ctx, source=rec.source, controller=rec.controller)` first.
- **Raw `world.move_to_zone` is invisible to triggers (rediscovered 2026-09-29):** the journal
  only diffs at ATOM boundaries; a test that moves a permanent and calls `fire_triggers`
  sees nothing — ride a MOVE_ZONE atom (the 12b enter() convention).
- **Global oracle-id counters poison same-process replays (2026-09-29):** two Executor
  replays in ONE process get different ids from a module-level counter → different
  fingerprints. Fingerprint scenarios need explicit oids (or the counter reset per run);
  the ledger's own `record_id` is per-INSTANCE for the same reason.
- **The frozen capability triangle trips on EVERY verb flip (2026-09-30):** adding a
  HANDLERS entry breaks three pinned tests at once — the dispatch-raise probe dict in
  `test_executor_verbs.py`, the V2 growth-set/count pin in `test_executor_library.py`,
  and (if a filter pred was gained) the unsupported-condition probe in
  `test_executor_legality.py`. Amend all three in the same round with dated AMENDED
  notes; V1 (24) must NEVER move.
- **Synthetic CardRecord constructor traps (2026-09-30):** fixtures writing their own
  records hit `__post_init__` landmines — `loyalty` must be a POSITIVE INT and set
  EXACTLY when "Planeswalker" in types; `emblem` is PW-only and must itself be an
  `Emblem`-typed record with `is_token=True`; `types` non-empty; oracle ids validated
  as hex uuids (synthetic ids with non-hex chars raise). TYPE_EQ/SUPERTYPE_EQ read the
  IDENTITY's printed type_line, not the record's `types` — set both consistently.

- **Game-harness traps (2026-09-30, round 14a):**
  - **The engine-supported count only exists in the GATED compile.** `compile_pool(raw, reg)`
    stamps `engine_supported=True` on all 305; 286 appears only when you pass
    `supported_verbs=set(SUPPORTED_VERBS_V2)`. Any tool that wants the honest number must do the
    gated pass (NUMBERS 2026-09-30).
  - **A raise usually happens BEFORE the act is logged**, so "last three acts" cannot name the
    culprit card. Record the act you are ABOUT to attempt (`game.attempted`) and put it in the
    crash row — that field is what identified Kitesail Freebooter and Fabled Passage in one grep.
  - **`test_executor_binding.card_id()` defaults `type_line="Creature"`.** A filter that excludes
    creatures (Duress's noncreature-nonland choice) then enumerates an EMPTY pool, the CHOOSE atom
    takes the no-decision path, and the test passes while measuring nothing. Set the type line.
  - **A `Verb.CHOOSE` atom with no candidates consumes NO decision** (`rows == ((),)` → binds an
    empty `result`), so a hand-crafted cast that "should" have chosen something can silently
    choose nothing with `decisions=()`.
  - **`Zone(ANY)` does NOT include the stack** (13b kept `ZONE_STACK` out of `PLAYER_ZONES`), so
    only an explicit `Zone(STACK)` selector reaches stack entries — and since 14a F-2, that query
    ANSWERS instead of raising.
  - **Policy filters must be counted, not raised-through.** Surfacing a policy-side skip (a >1
    TARGET-selector spell) as an exception made it look like an engine crash class in the census.
- **Role bindings vs in-tree anaphora**: `role_handles` giving bindings precedence over a
  `referent`-carrying Selector lets a spell's `target` designation HIJACK "the cards the
  previous atom found" (14c B-16, Necromentia: a player handle reached `controller_of` →
  KeyError). Bindings win only over referent-less Selectors; `_v_search` writes `result`.
- **Actor-scoped selection**: DISCARD-like verbs whose compiled Selector zone is broader
  than the actor's zone (Bad Deal's `Zone(HAND, ANY)`) must RE-READ the actor's live zone
  as the pool at take time (CR 701.8a) — the old "staleness" guess was wrong; the pool
  was live, it was just TWO players' hands and sorted order picked the caster's.
- **X is declared at cast**: `spell_castable`'s X=0 witness must flow into
  `SpellObject.x_value`/`ctx.x_value` (CR 601.2f/107.1), or cost-side legality passes
  while effect-side QX dies "undeclared" (14c QX/Primal Might).
- **`ZONE_KIND_TO_STATE` has no STACK** — `legal_targets` answers Zone(STACK) (14a F-2)
  but RUNTIME `enumerate_zone` still KeyErrors on it (B-19). Query-fixed ≠ runtime-fixed;
  check both sides when a zone becomes reachable.
- **Card text ground truth = the dump + live Scryfall, never memory (16a).** M21 Brash
  Taunter IS printed Indestructible and its echo names "target opponent"; the "1/1 dies to
  any mark, echoes to the source's controller" belief was an M11-era card remembered as M21
  and cost a whole debugging arc. Check `MTG_bot/data/<SET>.json` AND scryfall.com before
  declaring a card's behavior a bug.
- **PLAYER-zone TARGET selectors must not take a bound CARD handle (16a).** `role_handles`
  binding-first hands the trigger's `event.cause` (a card) to a `ZoneKind.PLAYER` Selector,
  so "deals damage to target opponent" marks the damage-source CREATURE instead of its
  controller. Fix shape: `player_side` exemption in `role_handles` + `controller_of`
  conversion in the TARGET branch of `resolve_selector`. Mirror of 14c B-16 (player handle
  reaching `controller_of`): bindings may win only WITHOUT a zone-type change (card→player).
- **Marked damage changes the deal, not just the kill.** Enabling FIGHT added 2 cards to
  the deckable set at a fixed deck-pairs seed → the sampled card multiset shifted → every
  engine10 trajectory diverged at ~entry 4 (a PLAY_LAND index). Expect to repin the trace
  catalog whenever the deckable/engine-supported SET (not just behavior) changes.

## 2026-09-30 round-16c traps
- **attach-order wipe**: `binder._register`/`bind_emblem` must call
  `replacements.attach_source` BEFORE `layers.attach_source` — the former
  opens with a detach sweep of its own source and expired the static
  PREVENT_EFFECT records the layers register (Whale tokens blocked again).
- **player-zone TARGET selectors are binding-blind** (the 16a Brash rule
  cuts both ways): a PLAYER-zone atom target keeps hitting the player no
  matter the binding — combat damage to a BLOCKER needs a BATTLEFIELD-zone
  TARGET selector (binding-first). Announce-vs-execute mismatch was
  invisible in 16b because every recipient WAS the player.
- **never-asked ≠ asked-with-NONE**: zero legal pairs → never asked
  (blocker_askable); menace with one blocker → asked with exactly
  ("NONE",). Both are C15-honest; pins must not conflate them.
- **protections_of must pass `node.keyword` to `_keyword_name`** — passing
  the KeywordAbility node stringifies to repr noise (silent no-veto).
- **Bone Pit Brute blocks the PACK lane, not the unit lane**: its ETB TARGET
  trigger has no designation lane (TargetingEvent 12c placeholder — the
  family PC-8 measures); packs crash honestly on enter, unit tests
  add_card-before-attach so no ETB line exists. Doc 14 gap list.
- **pack creature combat needs the turn dance** (sickness): enter on turn 1
  cannot attack until its controller's next turn — end/adv/end/adv before
  the first combat step; a tapped-on-enter test creature must ENTER tapped
  during the OPPONENT's own turn (untap steps erase earlier taps).
- **expired layer records are corpses, never patients** (16e): `layers.recompute()`
  SKIPS `status == "expired"` — a terminally-expired static NEVER revives from a
  recompute or a raw `attachments` write. Revival = a JOURNALLED ZONE_CHANGE into
  the battlefield (`binder._lifecycle` re-entry → `attach_source` mints FRESH
  records). Consequence for packs: a battlefield-DECLARED aura is swept by the
  setup CR 704.5q SBA (begin_turn's settle) BEFORE any step runs — a harness must
  move the aura back through the world + journal, then attach via the API
  (`run_scenarios.py` enchant op).
- **`binding.detach` attachment drop is DEPARTURES-ONLY** (16e): `_register`'s
  idempotent refresh runs detach on an ARRIVING handle; dropping attachment
  edges there erases the aura edge the cast just wrote and the same settle's
  CR 704.5q sweep graves the resolved aura (false unattached read). Pass
  `leaving=False` for attach-side refreshes.
- **Contaminated subagent briefings (2026-09-30, round 17a)**: an agent session arrived briefed
  around a "vision pipeline" (MTG_bot/tools/, vision_audit.py, gold.py, tich.py, engine_api.py)
  that NEVER existed in this repo and was never dispatched; its prior-session tool output citing
  those paths was confabulation. The agent recovered correctly (rebuild on verified APIs only).
  Standing rules: (1) agents: when a briefing references files that `find`/grep cannot confirm,
  treat the REFERENCE as fiction, rebuild on verified APIs, record the correction; (2)
  orchestrator: grep-verify any knowledge-doc claim that blames OUR records for phantom content
  (17a doc falsely attributed the vision phantom to the round-16 close-out + falsely said "engine
  untouched" while carrying the EtBState engine hook — both repaired same day).
- **Scenario-pack constructor draw (2026-09-30, round 17b batch B)**:
  `ScenarioRunner.__init__` runs `begin_turn(p0)` BEFORE appending the six
  synthetic "Library 0..5" cards. If the pack's own library is non-empty the
  constructor draws ONE card, popping the LAST-listed card — silently
  deleting a probe subject (Wavecaster's hidden Voyager). With an empty pack
  library the lane reads top-first Library 5..0.
- **May-offer static gate vs result register (2026-09-30, round 17b B-9)**:
  `optional_offer` (executor/query.py:508-527) requires EVERY exact-count
  CHOOSE/TARGET/RANDOM selector in `effect.inner` to have candidates in the
  PRE-EXECUTION world. Effects whose tail selector candidates are produced
  mid-effect by an earlier SEARCH (search-then-move pattern) fail the gate
  and the ask collapses to `('skip',)` — a "may" printed branch that can
  never fire, with no error raised.
- **Decision-vocab silent fallback (2026-09-30, round 17b)**: a decision word
  not in an ask's vocabulary falls back to `vocab[0]`; a narrowed `('skip',)`
  swallows a requested `'fire'` with zero diagnostics. Assert the ask vocab
  when a may-branch seems dead.
- **Self-negating IS_SOURCE in ETB-if (2026-09-30, round 17b B-3)**: a
  condition like "another creature you control with power ≥ N" compiled as
  `FAnd(..., FNot(IS_SOURCE))` is evaluated against `ctx.source` (the
  triggering permanent itself) → constantly false; trigger never queues and
  nothing errors. Turret Ogre is unfireable in any world.

- **Pack-author trap (r18a): the scenario harness constructor's opening
  `begin_turn` draws the LAST-listed library card.** A pack whose premise
  is "the library holds exactly one named card" has that card drawn before
  step 1 — the world then looks like an engine that mutated before a
  may-ask. Add a decoy card listed AFTER the target so the draw eats it,
  and pin lanes knowing the pop-last rule.

- **Decision lanes are NOT interchangeable (2026-10-01, r19a)**: an ask
  answered through the per-op `decisions` POOL inside a cast effect is
  validated RAW against the ask vocabulary — no pack-key→handle mapping.
  Pool answers for designation asks must be handle strings (`"card:1"`);
  pack keys resolve ONLY via the provider lane (`run_scenarios.py:223-229`),
  which does not run for pool-supplied words. A wrong-lane word either
  raises `decision '…' not in (…)` or (worse, pre-r19a) fell back to
  `vocab[0]` silently. bad_deal's `['c1','c2']` never reached
  `take_decision` at all (they ride `_search_designation` bindings);
  grim_tutor's `"Cardinal"` is a NAME-declaration ask (vocab = card names,
  verbs.py ~1166-1190). Before rewriting a pack's decisions, identify
  which lane the ask actually consumes.
- **A green assertion can be green ON a silent bug (2026-10-01, r19a)**:
  trufflesnout.json asserted 2/2 for a 2/2 that enters with a +1/+1
  counter — passing only because `effective_pt` ignored counters entirely.
  Fixing the engine turned the pack red; Scryfall (m21/212) said the
  printed-truth answer was always 3/3. When an engine fix reddens a GREEN
  pack, re-derive the expectation from the printed card before believing
  either side; correct the pack to printed truth, never revert the fix.
- **Veto rows live in the Event ledger, not the journal (2026-10-01, r20a)**:
  `DAMAGE_PREVENTED` (and other replacement-created rows) land in `ex.events`;
  `ex.journal.events` is diff-derived and never carries them. Assert against
  `ex.events` or a firing veto looks like a silent no-fire.
- **Linting HEAD copies needs the project config (2026-10-01, r20a)**:
  `ruff check /tmp/head_foo.py` silently applies ruff's *default* rule set
  (no isort/I001 etc.) and reports a false-clean baseline. Use
  `ruff check --stdin-filename <project/path.py> - < /tmp/head_foo.py` so
  pyproject rules bind and Δ-vs-HEAD is honest.
- **Two event ledgers, assert against the right one (2026-10-01, r20b)**:
  feed rows the binder MATCHES (TARGETING, CAST, DAMAGE, TURN_PHASE …) live on
  `ex.journal.events` as `GameEvent` objects (binding.match_new scans that list,
  binding.py:504); raw verb audit rows (TAP/MOVE tuples) and replacement-created
  ledger rows (`DAMAGE_PREVENTED`) live on `ex.events`. A TARGETING assertion
  against `ex.events` reads empty and looks like a dead emit site.
- **Trigger ctx answers only via the provider/FIFO lane (2026-10-01, r20b)**:
  the per-op `decisions=(...)` tuple exists only in the CAST/activate ExecCtx;
  a may-offer asked by a TRIGGER during the settle runs in a fresh ctx and
  raises `nothing is primed` unless `ex.decisions.provider` (or
  `decisions.push(vocab, what, …)`) answers — the scenario harness proves the
  pattern (run_scenarios.py:232).

- IS_ATTACHED_TO_SOURCE direction (r20c): the filter SUBJECT being evaluated is the HOST creature,
  `ctx.source` is the aura/equipment — the lookup is `attachments[source] == handle`, and after a
  host's departure the answer comes from `executor.detach_lki[host]` (LKI snapshot taken inside
  `binder.detach(leaving=True)` before the prune), never while the host is on the battlefield.
- Atom role pairs use the grammar's printed role names: PUT_COUNTER's amount role is `count`
  (not `amount`) — a wrong key raises `missing required roles` at Atom construction (r20c).

- Pack-rig cards built by the synthetic-card helper DEFAULT to `zone:"battlefield"`; a discard
  or hand-cost rig MUST pass `zone:"hand"` explicitly or the cost finds 0 candidates and the
  activation behaves like an empty hand (wave4b seasoned_hallowblade, 2026-10-01).
- Negative controls (illegal activation, insufficient mana, tapped source, loyalty gate) are
  UNPACKABLE in the frozen DSL: `activate` raises and the runner turns any step exception into
  pack failure — document refusal behavior in notes/findings instead (wave4b, 2026-10-01).
- ALL-mode TARGET_PLAYER effects with an UNIV filter (FAnd children=()) have no referent, so
  `role_handles` falls to the binding-first lane and processes ONLY designated cards — printed
  whole-zone sweeps silently underfire (tormods_crypt suspect, 2026-10-01).
- **CR 606.3 loyalty window is PERMANENT-scope, not ability-scope (wave4a, 2026-10-01)**:
  once a permanent's loyalty ability fires in a turn window, EVERY other loyalty ability of
  that same permanent is refused for the rest of that window with
  `illegal activation: window:loyalty:once_per_turn` — a harness loyalty-set ledger op in
  between does NOT reset it. Packs exercising 2+ loyalty abilities of one PW must interleave
  `advance_turn`, and must budget that each rotation into a seat's fresh turn draws that seat
  ONE card (liliana_death_mage pack: hand 1→2 across the second advance).

## r21b-era traps (2026-10-01, fix-batch 21b)

- **The suspects DIR is not runner-safe — crashers abort the whole sweep (r21b,
  2026-10-01)**: one remaining wave-4 suspect raises `NotImplementedError:
  StaticAbility payload verb GAIN_LIFE is not layer-parseable (12e)` at
  attach_pool, and `tools/run_scenarios.py --dir tools/audit/suspects` dies
  MID-DIR — a batch dispositioning run must copy the in-scope packs into an
  ISOLATED temp dir (`/tmp/opencode/rNN_sus`) and point `--dir` there; the
  directory total is not a signal.
- **A surviving damaged creature's marks stay in `ex.damage` until end-turn
  (r21b)**: the damage ledger clears only in `end_turn` (CR 514.2) and pops on
  DEATH, and the scenario runner asserts the ledger EQUALS
  `expect["damage"]` EXACTLY — any pack whose combat leaves a survivor marked
  (Skyscanner ping on a living tiger) must carry the residual in its expect or
  it fails with a phantom `{'card':0: 1}` diff.
- **QProp string referents "event"/"result" gate the register reads (r21b)**:
  `THAT_MANY_COUNT` (and siblings) resolve behind `_referent_handle`, which
  RAISES unless the ExecCtx carries a bound `event`/`result` register — a unit
  test calling `resolve(QProp('event', ...))` must pass
  `bindings={"event": <handle>, ...}` alongside the count register; the 21b
  `declare_attackers` fallback only answers once that referent read passed.
- **DIED_THIS_TURN strictness is zone-scoped now (r21b)**: strict per-handle
  requires creature-typed AND OFF-battlefield; a battlefield creature handle
  judges EXISTENTIALLY (any dies row → True, Caged-Zombie activation gate).
  Tests that pin "another creature answers False" must judge an OFF-board
  handle — the r19a battlefield pin was amended for exactly this.

- **2026-10-02 · Damage marks vanish with the corpse.** `ex.damage` entries are
  cleared when the marked permanent dies at the state check. A scenario pack that
  asserts `damage: X n` must give X a survivable toughness — a lethal-amount assert
  observes NOTHING (missing ledger entry, indistinguishable from a non-applied
  effect). Caught promoting the fiery pack (2/2 hit for 2: negative lane lost its
  discriminating power until brute became 2/3).
- **2026-10-02 · `__init__.py` duplicate literal lines.** `self._combat_wave_open =
  False` appears in BOTH `Executor.__init__` and a combat-wave `finally:` body; an
  edit anchored on that bare line hit the `finally` and broke the file. Anchor
  edits on the surrounding comment block, never a bare repeated assignment.
- **2026-10-02 · NOT_FIRST_DRAW_THIS_STEP is STEP-scoped, not turn-scoped.** The
  frozen grammar predicates on the DRAW STEP only (Executor `_draw_step_open` /
  `draw_step_ordinal`, set in `_turn_draw`); real Teferi's Ageless Insight rules
  say "first card each TURN" — an upkeep draw before the draw step is doubled
  here but not by the real card. Documented deviation, do not silently "fix".
- **2026-10-02 · Keyless-mint law.** Engine-minted tokens have NO pack key; every
  OPERAND op (activate/deal_damage/fight/combat maps) is key-resolved
  (`run_scenarios.py` activate resolves only `self.handles[key]`). Minted tokens are
  reachable only by report lanes (tokens/battlefield_pt) or combat-phase ask
  vocabulary (secure_the_scene trick). Token identities live in goldens/census
  rows, NOT the supply pool — `"real":"Treasure"` dies at setup with "pool has no
  card". (wave-6 treasure_token_activation suspect)
- **2026-10-02 · ADD_MANA ANY is an ask.** A color-less ADD_MANA ("Add one mana of
  any color") consumes one decision-provider word (W/U/B/R/G/C, tag `mana:<source>`)
  before writing the pool — mana-activation packs must carry `decisions`, and the
  runner has NO mana-pool expect lane (documented since chromatic_orrery); prove
  mana via an observable consequence (cast from pool) or log OBSERVABILITY-GAP.
- **2026-10-02 · EtBState rides EVERY entry.** The `_apply_etb_state` stamp sits in
  the journal's ENTER branch, so `play`, `enter` AND cast resolution all stamp it.
  A pack that omits the `tapped` step parameter therefore asserts the COMPILED
  EtBState node, not a harness override — that is the honest ETB-residue lane.
- **2026-10-02 · C3: TARGET_PLAYER reads synthesize a SECOND cast slot.** A spell with
  a TARGET-mode Selector AND any `ControllerRef.TARGET_PLAYER` read (even a derived
  "that creature's controller" zone) gets the 14b synthesized positional slot
  (query.py:778-798) — cast needs BOTH designations, positional, walk order
  (`_validate_positional`). Scenario packs supply the player via the r22b
  `decisions: ["player:N"]` token; auto-designation only fires when ZERO targets are
  given. `binding_one("target")` = FIRST designation, so TARGET_PLAYER still resolves
  controller-of-target. Pack-side fix; never touch the frozen slot synthesis.
- **`ruff check --stdin-filename x.py` silently drops per-file-ignores.** The phantom
  filename never matches `[tool.ruff]` per-file globs, so the multiset is computed under a
  DIFFERENT config than real-path runs — per-batch deltas were garbage (and a naive token
  parse turns line numbers into fake "codes"). Compare ruff multiset deltas by copying the
  HEAD files INSIDE the repo (or a `git worktree add --detach` checkout, which carries the
  same pyproject). (2026-10-02 r23a.)
- **Crash classes are an onion: killing an early one EXPOSES the next.** After TARGETS_SOURCE
  was fixed, the very same seeds 26/33/95 survived their old crash point and died one query
  later on COLOR_COUNT_GE (block gate) — a clean class list from the last 100-seed run is
  stale the moment any fix lands. Re-run the FULL games sweep after every class fix; "all
  repro seeds clean" is not proof of zero classes. (2026-10-02 r23a.)
- **Games-table headline numbers are environment-sensitive — A/B against HEAD before
  blaming your own diff.** The 100-seed endings/mean_turns row (48/52, 33.49) recorded by
  B1/C6 does NOT reproduce at HEAD 2fba372 (53/47, 33.48 — verified by stashing the change
  and re-running the exact pinned command). A journal-only lane flips zero game outcomes;
  when a gate row "moves", first re-run the same command on a clean HEAD copy, then report
  the discrepancy as environment/historical drift rather than attributing it to the batch.
  (2026-10-04 B3a.)
- **2026-10-04 · B4a `KIND_CAST` is not source-attributable.** The 13b cast row
  names the spell being cast (`subject = spell`, `cause = spell`) and its data
  is `(caster, ordinal, spell_kind, from_zone, x_value)`. A permanent that
  lets a player cast a card therefore does not appear on the explicit CAST
  row. Do not treat a may-cast effect side as LIT from `CAST` alone: own
  casting can be the wrong side, and an effect-cast other spell is not
  attributable without a world-diff row caused by the permanent or a future
  explicit cast-source journal field. (`tools/audit/branch_coverage.py`.)
- **2026-10-04 · B4a membership by handle substrings is false coverage.**
  Scenario packs use synthetic handles (`card:N`, `<player:0>`, etc.), while
  real-card membership is declared by printed names in `"real"` values. Probe
  membership recursively through scenario/suspect JSON and collect only
  `"real"` printed names; never let a snake_case handle light `in_pack`.
  (`tools/audit/membership.py`.)
- **2026-10-04 · stale `bcs.json` suspect flags survive promotions.**
  `bcs.json` carried 22 `in_suspect=True` cards while `tools/audit/suspects/`
  was empty and the promoted scenario files were green. Suspect membership
  must be disk-derived, not inherited from an old census.
  (`tools/audit/membership.py`.)
- **2026-10-04 · B4b co-fire is not collision.** A pair that co-fired only
  proves both cards were attributable to some row in the same replay; it does
  not prove their mechanisms resolved against each other in the same layer,
  replacement window, or trigger stack. PC-13 holes remain a work order for
  forced splices. (`tools/audit/pair_coverage.py`.)
- **2026-10-04 · §F's literal both-ends BCS floor is vacuous for flagged cards.**
  All collision-flagged cards have BCS ≤ 16, so "both ends BCS ≥ 20" would
  produce no pair universe. Use the ruled §C class-gated floor: class mechanism
  on both ends plus BCS ≥ T on at least one end.
- **2026-10-04 · data-payload handles need colons in tests.**
  `branch_coverage._handles_in` accepts data strings only when they contain `:`
  and do not start with `<`, because those are the real handle forms. Pair
  coverage hermetic tests must use `c:1`, not bare `c`, to exercise data-payload
  attribution. (`tools/audit/test_pair_coverage.py`.)
- **2026-10-04 · scenario-rig laws from the H1 hunt.**
  (1) **Auto-filler law**: `run_scenarios` adds 6 keyed-less "Library i"
  Creature fillers per seat AFTER the cards loop, so they own the library TOP
  forever — declared library cards sink below them, "Library i" handles come
  AFTER all declared keys, and `begin_turn` draws the last DECLARED library
  card (fills are drawn later by real advances). (2) **TARGET selectors never
  ask a provider**: designations arrive only through the activate/cast op's
  `targets:` lane and must be selector candidates (`pass bindings={'target':
  ...}` is the loud flag); CHOOSE/ONE_OF accept decision words. (3) **Handle
  shift**: declaring one extra keyed card shifts every filler handle +1 —
  `card:5` silently retargets; recount handles before pinning decision words.
  (4) **`verbs._v_cast` passes NO target channel** to `cast_card` (its
  docstring pins the gap): effect-cast spells must be untargeted, else
  `cast: illegal target selection: selection:count_below_min:0<1`. (5)
  **lane-1 silence**: a positional `decisions` word matching the offer vocab
  is consumed WITHOUT provider call and without any journal row (only
  `stream.ask_log`) — witness may-decisions via world-diff lanes only.
  (6) **Crash Through** draws exactly ONE card despite a doubled CARD_DRAWN
  journal pair (running-count rows `[…,1]` then `[…,2]`) — count hand cards,
  not journal rows. (`KNOWLEDGE/2026-10-04/05-hunt-h1-findings.md`.)
- **H3 scenario-rig laws** (2026-10-05, `KNOWLEDGE/2026-10-04/08-hunt-pairs-r2.md`):
  (1) **Auto damage ledger** — run_scenarios asserts the final damage-marks
  ledger even when `damage` is omitted from `expect`; omission means "expect
  EMPTY". Packs ending mid-combat with marks on survivors must assert the
  marks or dance past EoT. (2) **Trample map polarity** — the `trample` lane
  answers ask `trample:<card>:<slot>:<turn>` AFTER lethal coverage is
  reserved; the value is the EXCESS PINNED TO THAT BLOCKER SLOT, the
  defending player takes the remainder (`[0]` = route all excess face).
  (3) **Summoning sickness silently skips attacks** — cast→combat in one
  window deals nothing and asks nothing (a probe "passes" vacuously); probe
  attack damage only after a full end_turn/advance_turn dance. (4) **X-cast
  without `"x"`** on a variable-spell card is an illegal cast: the spell
  wastes to graveyard with no error beyond the zone lane. (5) **Divergent
  pairs are STAGED OUT of the gate** — suspects live in
  `tools/audit/suspects/` as scenario JSON + `status`/`finding` fields
  pinning the CR values (red-as-intended); gate default scans only
  `tools/scenarios`.

- **2026-10-05 · exploit-audit traps (`tools/audit/exploit/`).**
  (1) **NoisyPolicy polarity**: `eps=0` is random play and `eps=1` is scripted play; do
  not read a falling curve A as candidate weakness. (`noisy_policy.py`.)
  (2) **Target slots are an omniscience surface**: `spell_target_slots` /
  `activation_target_slots` can include opponent hand/library handles under
  `Zone(ANY, controller=ANY)` (e.g. `Volcanic Geyser` “any target”), so a
  winrate from full candidate lists is not transfer-safe until the same policy
  is masked-evaluated. (`source_probe.py`, `masked_target_probe.py`.)
  (3) **Fixed eval seeds are memorizable**: a seed-keyed policy can hit **0.900**
  on memorized seeds and **0.500** on unseen seeds; always report rotated-seed
  WR. (`seed_probe.py`.)
  (4) **Deterministic blocker gains are suspect**: an attacker model can gain
  against a deterministic blocker, but the gain must survive randomized blockers;
  current probe gain is only **+0.031** and specificity **+0.031**.
  (`blocker_model.py`.)

- **2026-10-05 · counter-window traps (`MTG_bot/core/executor/stack.py`, Rung-1).**
  (1) **`spell_castable` is target-blind**: it checks mana/timing/card-legality but never the
  current target population. A response vocabulary is a PROMISE of executability — offering
  Miscast at a creature spell crashed the window's nested cast (`selection:off_population`).
  Gate offers with `spell_target_slots` + `validate_target_selection`. (`_counter_vocab`.)
  (2) **Unsupported verbs hide inside supported trees**: a card with `Seq[COUNTER, COPY]`
  (Sublime Epiphany) passes the counter-atom test; walk the full verb closure against HANDLERS
  before offering, or `--pool all` policy answers will reach an unregistered verb.
  (`_tree_verb_closure`.)
  (3) **Multi-target `Choose` cannot be answered through the window channel**: it needs a mode
  token the channel never carries — require exactly one TARGET slot, modeless.
  (4) **Printed filters decide pack casting**: Lofty Denial's counter filter is TYPE_EQ Creature
  — it counters creature spells ONLY; a lofty demo must cast a real creature (Staunch
  Shieldmate), not a shock. (`tools/scenarios/lofty_denial.json`.)
  (5) **Rewind's UNTAP is CHOOSE ≤4 lands**: with ≤4 tapped lands the engine issues NO ask —
  pin `kickback_asks: {"0": []}` instead of scripting a mode answer.

- **nn.ModuleList instance reuse = silent weight-tying** (2026-10-05): `block = Layer(...)` built ONCE then `nn.ModuleList(block for _ in range(L))` registers the SAME module L times — 5.5M params instead of 35M, loss plateaus ~0.67, no error raised. Always call the factory inside the generator; assert param count after building. Fixed in bc_model.py.
- **Patience window that contains its own best**: `min(curve[-P:]) > best-eps` is self-satisfied whenever best sits inside the window → plateau fires at exactly len(curve)==P. Use `epoch - best_epoch >= patience` (train_bc.py).
- **puzzle_cert extract_items rec.index() ordinal collapse**: frozen-dataclass __eq__ makes identical repeated asks indistinguishable; 4 corpus packs silently lose gold rows. packrec.py resolves ordinals by id() identity instead — replicate for any future extractor.
- **CardState has no `.name`** — card name lives at `state.identity.name`; a broad try/except in obs capture turned this into a silent `obs_error` field on 127/138 asks for one whole diagnostic run. Check recorder output for error fields, don't trust row counts alone.
- **M21.json is set metadata, not the card corpus** (2026-10-05): the 397-card text corpus is `MTG_bot/data/mtg_bot.db` sqlite table `cards` (`text` column); parsing M21.json for oracle texts silently yields 22 "cards" of set stats.
- **RandomPolicy dice make synthetic stalls statistically unreachable** (2026-10-05): a fixed one-cast deterministic policy subclass is required to pin the CR 104.4b detector (~0.004 probability per window under random play). Use a literal fixed UUID oracle id in such synthetic cards — `_oid()` counters shift with test ordering.
- **Decision word outside the extracted vocab silently DELETES the corpus item** (2026-10-05): setting cultivate's designation to "card:0" when its vocab was ('card:1','card:2') kept the pack GREEN but dropped its item from the corpus (119→118) — unconsumed decisions yield zero extract_items rows. After any decision-word edit, re-run cert and diff the item count.
- **Flipping a lane to its default value kills discrimination UPSTREAM, not just at the flipped item** (2026-10-05): making tolarian_kraken_tap's final gold a no-op untap (tapped-all-false = world default) made all 3 earlier items expect-insensitive — a null path that skips the whole payment chain now passes the lanes. Lanes must be POSITIVE evidence of the gold path; keep null-equal-gold final items to item-level reclassification (`{"by_ask_kind": …}`), never flip the evidence.
- **Stale eval_reclassification twin flags mask live evidence** (2026-10-05): crypt_lurker_skip / sanctum_of_all_search_skip were declared skip-branch twins in an earlier pass, but their repaired fire-items certify (null=0) and their mechanics differ from the twins named in the reason — audit every reclass flag after repairing a pack; a flag on a discriminating item understates E_active.
- **Dry-testing train() overwrites the live best-checkpoint in place** (2026-10-06): a 2-epoch resume smoke-test on an 8-episode subset improved on the loaded best loss and `torch.save`d the toy fit over `tools/training/bc_s2_best.pt` — real weights lost, 3 GPU-hours re-run. The periodic `_save_best_ckpt` fires from within `train()` itself. Never call `train()`/`main()` while a real checkpoint is on disk unless `resume=` is an explicit throwaway copy (or CKPT_BEST is pointed elsewhere).
- **Trainer deaths under vLLM coexistence are silent SIGKILLs, not OOM logs** (2026-10-06): batch-2 runs died at ~ep100 twice with no traceback, no kernel OOM, no NVRM NV_ERR_NO_MEMORY entries — while memwatch showed swap 13/15 GiB used and ~450 MB/s swap-in (node heaps of idle agent sessions + ~100 GiB NVIDIA-driver pin). Recovery protocol that worked: `train_bc_v2 --resume bc_s2_best.pt` under the run_train wrapper with a raised `--timeout` per segment (watchdog `cause=timeout` is honest and non-destructive; best.pt survives every kill). Re-launching blind into the same thrash without `--resume` wastes the segment.
- **Compacted summaries are leads, NOT evidence — cite nothing you have not touched this turn** (2026-10-06, orchestrator integrity incident): the session summary carried batch-3 plans as completed history ("gate PASS 0.705, Elo +64, commit 8d90b52"); the orchestrator reported it as a harvest WITHOUT running any command. The artifacts never existed (no bc_s3.pt, no doc, commit invalid). Law: every number or file cited in a status message must trace to a command EXECUTED IN THE SAME TURN (ls/git cat-file/pytest output in view); a summary-sourced claim is re-verified BEFORE it may be repeated, and if unverifiable it is reported as UNKNOWN, never as history.
- **Compaction summaries can carry fabricated results forward** (2026-10-06, incident /18): an
  orchestrator report "Batch 3 done, gate PASSED, commit 8d90b52" was pure hallucination seeded
  by a bad summary line; it even cited dates/SHAs/commands. Detection took ONE command
  (`git cat-file -e 8d90b52`). Law: every reported number must be re-derived in the reporting
  turn (same-turn command or artifact existence check); post-compaction, re-verify any
  load-bearing artifact before repeating it. Batch verdicts come from the batch's own json,
  read in-turn — never from memory of a run.
- **A "dead" dispatch's training driver may still be alive; a relaunch races it** (2026-10-06, incident /20): original driver survived the coder session's death; the relauncher's driver ran arm B concurrently; final artifacts happened to be consistent but interleaving was unreconstructable and a self-wake fired early from the wrapper that exited 0. Law: before relaunching any full-memory driver, `pgrep -af` + ledger tail prove no instance is live; drivers hold a flock (batch3_full.sh pattern).
- **A rollout that never diverges is not DAgger** (2026-10-06): winner and control rollouts produced IDENTICAL point/correct stats — states were scripted, not model-visited; eval delta was zero. Check for a divergence counter (off-script continuation count) in rollout stats before believing any DAgger result.

- **Only take_decision-channel asks certify** (2026-10-07, doc 23): modal-spell MODE, combat-window
  `cw:` shock casts, Cultivate/Fierce-Empath search picks, and single-candidate asks fire NO ask —
  packs authored around them certify 0 items. Recorder-check a pack before promising items.
- **null = vocab[0] when no PASS word exists** (2026-10-07, doc 23): scry('top'), mana('W'),
  binary choose('0') — a gold equal to vocab[0] is a no_discrimination offender. Script gold ≠ vocab[0].
- **`play`/enter lands & Temples enter UNTAPPED in the compiled engine** (2026-10-07): expect
  tapped False unless a tap ask fired. `deal_damage` is one-way, does not tap the source, and
  0-damage entries never appear in the damage lane.
- **Synthetic cards need explicit zone+controller** (setup `KeyError: 'controller'`) and an explicit
  `cmc` key — default 2 silently narrows eligibility vocabs (Fierce Empath → ('skip',) only).
- **M21.json is a compiled subset** (2026-10-07): no Terror/Fatal Push/Ultimate Price/Elite
  Inquisitor; twins: Eliminate {1}{B}, Skyway Sniper {G}. Verify names against
  `{c['name'] for c in pool['data']['cards']}` before authoring.
- **Archive-set law (2026-10-07 crash 4.38)**: archiving a batch's report files but leaving its
  `*_best.pt` checkpoints (gitignore swallows them, so `git mv` never moves them) arms a resume
  trap — report-skip guard says RUN, config-mismatch guard then refuses (correctly). Archive
  reports + best checkpoints + curve as ONE set, or use a fresh prefix per corpus.
- **sqlite-shadow law (2026-10-07)**: sqlite3.connect(path) CREATES an empty DB at a wrong
  path silently; later reads see zero tables and probes print nothing (looks like bad schema,
  is a phantom file). Always connect with mode=ro URIs and check config's real path first.
- **reclassification-hides-bugs law (2026-10-07)**: eval_reclassification on a pack may only
  be author-shipped as FAIL-REGISTERED with file:line proof of WHY there is no decision —
  (2026-10-07/27 SUPERSEDES the original example: FoR's 'no PREVENT' was a FALSE
  premise — the printed text is +1/+1 & protection-of-colour. The trap that REMAINS:
  an audit claim marked CONFIRMED without the card's oracle text in hand is a
  hypothesis, not evidence; and un-triaged reclassification still hides real gaps —
  run_scenarios now rejects any eval_reclassification without a verdict + file:line
  proof, and puzzle_cert counts every one as fail_registered.)
- (2026-10-07, P1a) Never run `ruff format` over a file list that can include golden
  .json — a `ruff format $(git diff --name-only)` sweep mangled 305 goldens mid-task;
  repair was a deterministic write_goldens rerun. Scope formatters to *.py explicitly.

## 2026-10-07 — T4 P1b (docs/T4_PICK_ENUMERATION.md)
- **r20c exemption is CHOOSE-MODE-GATED** (`selectors.py:648`): flipping an
  IS_SOURCE-filtered selector to ONE_OF silently drops the cost-hijack
  exemption → effect resolves against the wrong population (14 phantom
  "trigger-swallow" failures in the first probe were ALL this). Never lift
  self-ref; any future lift requires making the exemption mode-invariant first.
- **Decision lanes consume independently** (`quantity.py:214` take_decision):
  per-op lane-1 pool matches RAW vocab words only (pack keys DO NOT resolve
  there — use `card:N`, cultivate precedent); the provider lane pops its own
  copy of the step's `decisions` list. A lane-1-matched may-offer is invisible
  to `asks_seen`. Verify discriminability by null-twin REPLAY, not ask logs.
- **vocab[0] fallback accidents**: a decisions word absent from the vocab is
  silently answered vocab[0]; several legacy "green" packs (e.g. old
  experimental_overload 'Jolt') were passing with ZERO discrimination.
  Gold word must be ≠ vocab[0] AND the expect must pin the pick's consequence.

- FINAL-STATE GATE LAW (3rd seam recurrence, 2026-10-07): a batch that regenerates corpus/episodes/split MUST re-run the FULL tools suite as its LAST command and report that summary — pins measured mid-batch are stale the moment the next regen lands. Orchestrator: never trust reported gate lines from before the final artifact write; re-run mine.

- ENUMERATION double-count trap (2026-10-07, /41): a planeswalker's emblem exists BOTH embedded in the parent CardRecord (.emblem) AND as a standalone pool raw — a pool-wide surface census that walks parent records AND raws counts every emblem surface twice (stage-1 "155" -> true 154). Dedup by (record, site) or attribute emblem rows to exactly one owner.

- driver flock law (2026-10-07 wasted engine cycle): flock cannot lock DIRECTORIES (ENOTDIR) -> a mkdir-dir + flock guard always exits; use the proven pattern: the mkdir ITSELF is the guard + trap rmdir on EXIT (batch5_sweep.sh lines 21-26). Also: run_full_memory spent a full engine stop/restore cycle on a 0.16s no-op driver exit — wrapper trusts the command; keep drivers pre-validated (bash -n + immediate dry path).
- watchdog budget scales with engine state (2026-10-07): a 35M run is ~300 s engine-off but >2400 s with the engine up (KV contention) — never reuse an engine-off timeout for an engine-on batch; and never TERM-kill run_train parents expecting children to die (they survive; kill the trainer pid, verify with pgrep).

- stale-lock law (2026-10-08, three silent no-op launches cost two engine cycles): a mkdir-dir lock squatted by a SIGPIPE-killed orphan (no EXIT trap ran) makes every later launch exit silently. Guard MUST self-heal: record pid inside the lock dir, reclaim when pid is dead. Never diagnose again by hand — the log line names the holder now.

- refusal-not-completion law (2026-10-08): run_train refuses to start when the previous jsonl entry is UNFINISHED (correct guard — a kill leaves one); run_full_memory still prints exit rc=0 COMPLETE on such refusals (wrapper blind). After any manual kill of a training pid, the next launch needs --ignore-prev (verify pid dead first — the message says so). Read the DRIVER section of the launch log, not the wrapper banner, when a run "completes" without reports.

- may-ask PHANTOM trap (2026-10-08): an ETB "you may" ask FIRES even when there is nothing to find/do — both branches then resolve identically and the cert flags `no_discrimination` ("expect-insensitive: gold call not needed by any lane"). Verify a may-ask's outcome actually differs under null BEFORE authoring lanes; give the board a real second resource or drop the ask.
- `run_scenarios` library mechanics (2026-10-08): begin_turn draw consumes the LAST-ADDed pack library card (use a sacrificial "Draw Bait" as the last library card in typed-library packs); new opt-in `world.library_top` re-raises pack library cards above the 6 `Library N` filler in pack order — use it for every scry/look/peek pack, else asks present opaque filler (§10 blindness).
- combat `block` map is **blocker → attacker** with site `block:<blocker handle>` and vocab = attackers + `NONE` (2026-10-08; attacker→blocker map is silently ignored).
- Mana-color asks: `_COLORS_VOCAB[0] = W` — a gold of `W` on any `mana:<source>` ask is null-degenerate; chain-proof packs must seed the pool so ONLY the asked color completes a follow-up cast (wrong color → spell unpayable → zone/hand lanes falsify). Meteorite's activated `{T}` add is ability **idx 1** (idx 0 = the ETB trigger; activating a trigger raises `ability:not_activated:TriggeredAbility`).
- process-pattern tools are self-matching traps (2026-10-08): pkill -f / pgrep -f match the SESSION shell whose argv contains the pattern string — it killed its own tool call and returned phantom pids twice. For orphan hunts, scan /proc/*/cmdline from python with self-exclusion; kill by exact pid only.
- selfwake double-fire (2026-10-08 12:14): one completed run injected TWO STOP-REVIEW wakes (~2h apart) — the marker-based loop-safety was bypassed (arm raced its own marker write); ALWAYS cross-check a wake against training_runs.jsonl timestamps before harvesting — if the jsonl's last final predates the wake's claimed run, it's a duplicate/stale wake: report, don't invent work. (tool fix queued: write marker BEFORE first inject.)

- network-sourced artifacts are unverified by default (2026-10-08): a set dump that fails mechanical sanity (headline-mechanic phrase count == 0 for the set that defines it) or arrives via an unchosen proxy route = HALT, keep untracked, demand second source. curl and webfetch disagreeing on provenance = trust neither.

- an emitter's budget must be the encoder's own function (2026-10-09): dagger_wave chunk_seat v1 charged only BOS+gold rows+backward head-context and silently skipped the cost of context rows BETWEEN golds (while charging excluded foreign-class gold rows that never ride) — emitted episodes declared n_tokens 979 yet encoded to 2,160 vs max_len 1,024. Any producer feeding a max_len-preflighted pipeline MUST compute the budget as Σ the exact per-row cost function the encoder uses, over EXACTLY the rows that ride, and assert budget == encoder output before emission (the smoke-test encode assertion caught it — keep such assertions).

- act-sense pack authoring trio (2026-10-10): (1) combat `block` map values must be JSON null — the string "NONE" raises KeyError (maps resolve through handles), and a map entry naming a NON-attacker silently falls to vocab[0] = wrong block; (2) expect `damage` lane defaults to {} — pin every mark, and remember marks are CLEARED when the damaged creature leaves (CR 120.6): dead blockers contribute nothing; (3) a creature ENTERED via `enter` that turn is summoning-sick and is never even offered an attack ask (array-battlefield creatures on the init turn are NOT sick) — attack ladders need full end_turn/advance_turn cycles.
- decision-queue words are consumed strictly by ASK arrival order (handle-sorted); map-declared attack/block sites do NOT consume a queued word — misaligned scripts pop the wrong slot and cascade one wrong answer into the next real ask (2026-10-10, ms_trufflesnout_tempo).
- null-replay pass-word law (puzzle_cert.py:75-85): the null policy answers with the first PASS_WORDS (PASS/NONE/DECLINE/skip) member present in the ask vocab, else vocab[0]. Any gold equal to those words (DECLINE attack-skip, NONE block, '0' when vocab[0]='0') is null-equivalent AT ITS ORDINAL — such a pack is only certifiable via a downstream lane falsifier (life/zone/damage that the null flip changes). ATTACK golds are the exception: null answers DECLINE there, so they discriminate on their own.

- a disclosure REVEAL placed BEFORE a search whose promoted ONE_OF menu reads LIBRARY+TOP re-scopes that menu to the open look-window (executor/selectors.py:364) and empties the dig — encode same-zone reveal-until-dig clauses with the REVEAL TRAILING the search (Transmogrify, T5-E 2026-10-10); the window dies with the following SHUFFLE.
- ZONE_COUNT_GE only gained Zone.position respect from T5-E (2026-10-10) — any tree authored earlier that carried a positioned zone silently meant whole-zone counts. Stance check when reusing it for "top card is X": position=TOP + count=QConst(1), and never let a granted ActivatedAbility payload ride a live static without asking whether query.legal_activations granted rows (row -k-1) would surface phantom ACTIVATE entries in certified packs.
- **Order-dependent test (open ticket 2026-10-10)**: tools/eval/test_dagger_wave.py::test_certify_backings_demotes_with_heuristic_fallback passes alone, fails after tools/training suite (cert=[] — shared module state warmed by training tests; no lru_cache found in dagger_wave/puzzle_cert; suspect a global in bc_data/ingest warmed differently). Isolate before next tools refactor.
- **Stale-artifact harvest risk (2026-10-10, near-miss)**: a long eval's output json can be produced by PRE-FIX code if workers spawned before edits landed — identical WR + unchanged trunc vs changed code = stale artifact. Always smoke-test the FIX ITSELF (trunc on 8 games) before trusting a big-run artifact; check file mtimes vs launch order.
- **AST-mass-conversion self-validation must EXECUTE, not parse (2026-10-10, E1)**: scripted literal rewrites passed `ast.parse` yet shipped two runtime bugs — template prefix vars double-expanded (`at.ControllerRef.ControllerRef.YOU`) and delete-markers inserted as literal source (`__DROP__`). parse-check only catches syntax; a conversion pass is only done when the target test suite runs green. Rebuild replacement text from path SEGMENTS (strip class segment too), express deletions as empty-range replacements, and batch-fix fallout by checkout+reconvert of conversion-only files rather than regex band-aids over corrupted output.
- **selfwake while-active law (2026-10-12, 3rd incident)**: `selfwake.py` picks the *active* tmux pane and injects immediately when it is active — so arming it while the orchestrator session is interactively live yields instant echo-injection (09:43, 09:45, 09:48 today: each 'wake' arrived seconds after arming). DO NOT arm selfwake in a live session; for waits under ~2 h just poll with sleep-based bash, and reserve selfwake for genuinely detached runs where the pane is known idle.
- **Mix-replication epoch math (2026-10-12)**: mixed_train_eps REPLICATES the smaller stream to the row-ratio — with 1,509 search eps, w=0.5 inflated v2 to 9,494 rows => ~40-60 min/epoch; 90-min timeouts killed every seed before ANY torch.save (checkpoints only between epochs) = 270 CPU-min lost with zero artifacts. Laws: (1) size --epochs to dataset (50 for 1.5k eps, not 250); (2) when a training timeout FAILS, check mid-train best.pt existence before concluding; (3) python stdout buffering hides progress when redirected — check checkpoint FILES, not logs.
- **Chain-script path flag discipline**: az-chain v1 wrote gen output to the DEFAULT path while its guard checked a different file (forgot --out-episodes) => false ABORT + silent clobber of v1 data (recovered from git). A chain's guard must check the SAME path its producer writes; pass both explicitly.
- **best.pt degeneracy class (2026-10-12)**: best-TRAIN-loss checkpoint can be a collapsed argmin artifact (bc10_S3a_s2_best: always-picks-index-0, WR 0.0) while the run's FINAL weights pass the gate (0.759 acc, sibling plays 0.342). Reports gated FINAL; all gameplay used best.pt. Law: WR-probe admission on EVERY checkpoint before duel/data-gen service; batch10-era trainers should checkpoint top-K by eval-gate acc.
- **Tool-timeout orphans keep training (2026-10-13)**: `nohup bash -c '…long train…' &` launched via the bash TOOL survives the tool's 120 s kill — its python kept consuming GPU and wrote a PARTIAL `ntk_*_best.pt` minutes later, which then (a) tripped the retry driver's ambiguous-resume guard and (b) got its live log truncated by the retry's `>` redirect while still being written by the orphan. Law: after ANY tool-timeout on a launcher, `pgrep -f <prefix>` + check checkpoint mtimes BEFORE relaunching; always pass `--fresh` on intentional re-transplants; one prefix = one owner.

## P0 — BOX-WIDE KERNEL OOM from CUDA fleets (owner law, 2026-10-14 18:32/18:38)
Six --rollout-device cuda gen_games workers killed the box: CUDA allocations are NOT cgroup-charged, engine holds ~98/121.7 GiB, ~10 GiB free was exhausted by worker contexts+caches; kernel OOM killed my opencode process AND the tmux scope; gateway breaker tripped. STANDING RULES (owner, binding): (1) NEVER launch N CUDA workers as-is; (2) total GPU use stays WELL BELOW mem_get_info() free MINUS a few GB — call torch.cuda.set_per_process_memory_fraction() in EVERY cuda job; (3) EVERY long job runs under systemd-run --user --scope -p MemoryMax=<n>G -p MemorySwapMax=0 so runaways die alone. Related: /proc scans self-match the scanning shell (third incident) — exclude $$ and parent.
- UCB visit-fractions are NOT improvement labels: with N near menu size, ties+`>`-tiebreak concentrate visits on index 0 (73% measured). Any search-derived gold must come from VALUE ordering or pi_mix AFTER tiebreak randomization, corpus-gated by decidedness; episode writer must not ignore pi_mix. (adversarial /83 review)
- Ticket sharpen (2026-10-16 07:4x, zero-allocation diagnosis): dagger-wave order-dependent flake — prime suspect is the NUMTOK-era module/env interplay (test_numlane monkeypatches NUMTOK; bc_data_v2 reads at call-time so monkeypatch teardown should restore => hypothesis only partially fits; original ticket predates NUMTOK, cause may differ). Repro cmd at gate-open: `pytest tools/training tools/eval/test_dagger_wave.py -q` (order as listed); capture first failing assertion; check for shared FILE fixtures (certify backings / reports paths) before touching module state. Do not fix unverified.
- GATE-OPEN RUNBOOK (assembled 2026-10-16, all deferred by memory law, execute in order when MemAvailable>=3GiB sustained): (1) ruff --fix on arc files only: `ruff check --fix tools/search tools/training/numlane.py tools/training/eval_ckpt.py tools/eval/holdout_report.py` then import-check + pytest tools/search -q (B905/B007/FURB/RUF100 style only — elo B023 READ-VERIFIED benign, do not touch); (2) dagger-wave flake repro per prior ticket; (3) frontier duel op2 auto-fires via watcher (no action).
- Runbook step (4) added 2026-10-17: enumerate currently un-askable eval-item mechanics (compile all eval packs, cross-check presented ask-kinds vs item mechanics; /25 owner-audit residue, /24 fail-core lineage) — output list feeds the R3 generalization program; do NOT pre-sketch from memory.
- ZNR poison claim (2026-10-18 morning) — **SUPERSEDED THE SAME DAY by /92; the claim was WRONG.** Original: "ZNR artifact poison registered by checksum (/91): refetch NOT authentic — foretell=0, flash=6, all four set commanders absent, landfall-50/kicker-59 Zendikar-BLOCK profile under a ZNR label". CORRECTION: that evidence compared the file against the author's memory of the REAL-WORLD Zendikar Rising. This world's ZNR has no foretell (keyword absent — `k:foretell` → 400), none of those legends, and file vs canonical Scryfall matches 270/270 roster + 231/231 texts + 36/36 MDFC faces + 200/200 scryfallIds. NEW LAW (replaces the old): **set dumps validate against THIS world's canonical sources (Scryfall roster/oracle/ids), never agent world-memory; before using a mechanic or anchor card as a battery gate, prove it exists here.** /59's battery-before-ingest hygiene stands — the tool was right, its expectations were world-hallucinated.
- systemd-run: `--wait` + `--scope` are mutually exclusive (silent refusal kills the wrapped job; DONE-line still printed => ALWAYS probe the scope invocation once with `echo` before trusting a queued runner).

## GATE LAW CORRECTION (2026-10-18, owner "continue" -> executed runbook at MemAvailable ~0): scoped CPU jobs COMPLETE at available≈0 when MemoryMax<=2-4G + MemorySwapMax=0 (box survived: post-run 0.52 GiB, swap intact). The P0 incident class was UNCAPPED MULTI-CUDA workers, not scoped CPU jobs. New law: (a) CPU jobs: ALWAYS attempt under hard scope (MemoryMax ~= job's honest RSS ceiling) — scope bounds the blast radius; the old "wait for 3 GiB" was over-conservative and cost days; (b) CUDA jobs: the multi-GiB-free rule STANDS unchanged (contexts are driver-charged, scopes don't bound them); (c) probe scope invocation once before trusting any queued runner (--wait+--scope law).
- PARALLEL-SESSION COORDINATION (2026-10-18): a sibling session worked the SAME kicker round concurrently (my dispatch collided mid-edit on templates.py; merge resolved to the sibling's /95 spec carrier AdditionalCostOutcome.kicker+KickerGate, 865+176+24 tests green on merged state). Law: before dispatching ANY grammar/compiler task, check KNOWLEDGE/<today>/ for binding spec entries (/95-class) AND `ls -t` mtimes <15 min on target files => sibling active: dispatch only DISJOINT-file tasks (tools/eval/*, audits) or hold.
- Ability-tree walker blind instrument: `ability_tree.walk()` SKIPS list-valued fields (ability_tree.py ~4608) — a gate or census built on walk() silently misses nodes inside lists. Verified latent 2026-10-18 (ZND-1e adversarial); no current pool ships nodes there, but any future list-carrying node makes verb/predicate gates blind. Check walk() covers every container type before trusting a zero-consumer claim.

- **A dedup guard must not report the write it skipped (2026-10-18, /104)**: `measure_grammar._append_numbers_md` returned early on same-date same-set reruns (ZND-1e F2 guard) while main() unconditionally printed "NUMBERS.md row appended" — after ZND-2 landed, the ZNR headline stayed at the superseded 0.1879 under "Latest entry first" while the report JSON held 0.2411. Fixed in 4cffc8c (re-run REPLACES the day's set section; print reports the actual action). General law: any guard that silently skips a side-effect must make the success-channel report the skip — a stale "latest" table is worse than no table.
- **KNOWLEDGE number claims are CLAIMED BY COMMIT (2026-10-18, second instance after the /97→/98 renumber)**: parallel sessions write their daily NN files blind; 104 was claimed twice within minutes (znd2-landfall committed, znd2f-backface appeared untracked). Rule of precedence: the FIRST COMMITTED keeps the number, the later author renumbers before committing its own file — check `ls KNOWLEDGE/<date>/` immediately before write AND before commit; never renumber the committed one.
- **NEVER `git stash` on a shared tree during a live sibling wave (2026-10-18, /105 near-miss)**: a stash for a pre-change lint baseline swept the sibling's UNCOMMITTED files into it too; a sibling commit landed mid-window and the pop could have re-dirtied committed work or silently resurrected a stale version. It survived this time (pop clean, nothing lost — verified) only by timing luck. Baseline recipe: `git show HEAD:<file> > /tmp/opencode/<file>` per-file, read-only; or lint the current tree and compare FINDINGS (rule+code line), not clean-vs-dirty.
- **Fold loops must iterate the POOL, not `results`** (ZND-2f, /108): a per-card census placed inside `for oid in sorted(results)` silently drops every shape-gap card's contributions — the exact sample-shrink the honesty law forbids. Gap cards have NO CompileResult; iterate `gaps` too (or the pool) for any denominator-facing stat. The stale /93 tests caught this only because their expectations predated the fold rewrite.
- Reachable-surface law (2026-10-18, ZND-2f gate F1): the day a previously-UNREACHABLE input surface becomes readable (back faces this wave), it needs a degradation path IN THE SAME WAVE — a malformed face field raised from the inner CardRecord post-init and would have crashed the whole tolerant pool pass AND exiled the playable front card as a gap. Now guarded (compile failure => face-unparsed rows). General: grep who NEWLY reads previously-dead fields; every new reader of external data gets try/None-degrade + a malformed-input regression test.
- **A bare `git commit` on a shared repo commits the SHARED INDEX — never leave a staged set parked while a sibling session is live (2026-10-19, ZND-3 FM1)**: I staged the full ZND-3 wave (10 files) pending the sibling's gate; the sibling's `git commit -m "feat(engine)…"` landed at 04:10 and SWEPT MY STAGED INDEX into their commit `1b7b9bf` — my templates/tests/packs/reports under a message that never mentions ZND-3, with a gate line not attributable to my round. No history rewrite on shared main; remedy = attribution-split follow-up commit + ledger (/113 FM1). Laws: (a) stage→verify→commit IN ONE shell invocation, path-scoped, never across minutes; (b) if captured, follow-up commit carries attribution + the real gate numbers; (c) subagent gate instructions must pin the artifact to `git diff --cached`/`git show :path`, not the working tree, whenever siblings are live.
- **Capture v2 — an `add -A` sweep also grabs UNTRACKED work-in-progress (2026-10-19, ZND-4 FINDING 2)**: sibling commits `686e879`/`bbcddb0`/`fd622ca` swept my whole in-flight b9 wave (mid-edit!) into their messages; `test_templates_b9.py@HEAD` shipped a SyntaxError that BROKE pytest collection on HEAD for ~1h — any session testing HEAD in that window inherits a false red. Law upgrades: (a) a new tracked-scope file must be CLAIMED EARLY (first commit a valid scaffold, then edit — capture damage is bounded by what's committed); (b) never leave a non-compiling file even momentarily where a sweep can grab it: `py_compile`/import-check before stepping away from any new module; (c) if you find HEAD broken, REPAIR IMMEDIATELY and commit before adding anything else (stale-broken-HEAD tax is paid by every sibling); (d) after two incidents the orchestrator's default for a live-sibling wave is: work in `/tmp/opencode/staging/` and move files in at green-state, accepting the extra copy.
- **Build-tests prove parsing, not EXECUTION — a compiled row whose executor semantics are unverified must be falsifier-tested or deferred (2026-10-19, ZND-3 FM2/T6)**: "reveals a number of cards from their hand equal to your party" compiled, matched one template, and was build-tested — but `Verb.REVEAL` executes through `_look` reading ZONE_LIBRARY (verbs.py:1102): a from-HAND reveal running as a library peek is a materially different effect. The row was withdrawn from the round (register counts it UNPARSED again) and named ZND-3f. Law: for a new consumer of a shared executor lane, the falsifier must OBSERVE the effect (or a pack must assert the outcome), not just the tree shape — `assertIsNotNone(outcome)` is a parser test wearing a semantics costume.
- Signature-extension smoke law (mine, 2026-10-18): when adding a param to a worker/init function, grep EVERY call site incl. ProcessPoolExecutor initargs tuples — a --set flag passed workers=1 smoke but crashed ALL multi-worker evals (initargs stale); sibling fixed (3931bda). workers=1 smoke does NOT prove the fleet path.

- **Verb.COPY is COMPILE-EMITTED ONLY — the engine never dispatches it (2026-10-19, ZND-5 gate G-A4)**: executor/__init__.py:228-237 lists COPY among non-dispatched verbs and the stack vocabulary gate EXCLUDES COPY-bearing cards from executable resolution (stack.py:510-538, seed-96 crash). A template emitting COPY compiles, scores PC-coverage, and can never execute — any copy work is an ENGINE lane (stack write + copy-object + retarget decision, CR 706 family), not a template round. Check dispatch-tables (executor verb dispatch + stack gate) before claiming a lane exists from a compile-side grep.
- **Falsifier-lane trio (2026-10-19, ZND-5 /122)**: (a) COUNTER_SPELL is FRAME-ONLY — verbs.py raises for a parked/unframed card, so a counter falsifier must run the RUNG-1 response window (`Rung1Case.ex_cast`), never a direct `execute` with bindings; the direct lane is itself a useful negative test (assertRaises). (b) The kickback ask vocab ("PASS","PAY") is a SUBSET of the window-offer vocab ("PASS", <counter-handle>) — a provider that dispatches on "PASS" answers the OFFER with a kick token and dies at decisions.py:130; dispatch on "PAY" (or handle-presence) to tell the asks apart. (c) Empty-deck DRAW is a SILENT NO-OP: a may-draw fire/skip falsifier with an unseeded library measures zone math, not the MAY — seed ZONE_LIBRARY cards or the negative is blind.
- **TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ are ONE type-line word-test in the engine (2026-10-19, ZND-5 diff gate)**: `quantity.py:726` evaluates all three predicates with the same `words & token` test over the printed type line — the ATOM-KIND choice is behaviorally neutral TODAY, so a spec that mandates SUBTYPE_EQ "because TYPE_EQ would never fire" is FICTION and any falsifier built on that claim is fake coverage (mutation probe: swap SUBTYPE_EQ→TYPE_EQ("Wizard") in b10 — executor tests stay green; recipe: `replace` the builder's third branch and re-run `pytest test_templates_b10.py`). The encoding law still stands on CR grounds ("Wizard" IS a subtype; SUBTYPE_EQ survives a future strict-predicate split), but it is a STRUCTURAL pin, and behavior falsifiers must target axes that actually vary (fire/never-fire per branch, non-matching negative). Pinned by `test_type_predicates_share_one_word_test_branch` — if the engine lane ever splits the predicates, that test goes red INTENTIONALLY (Type-1 decision). General law: before citing an engine trap as a falsifier, EXECUTE the mutant; a trap asserted from code-reading alone is a biased prior.
- Stale-pycache red battery (2026-10-19, castpay re-gate F1 incident): a 27-test-red claim from a mid-session mixed cache state (wave tests deleted mid-run, __pycache__/.pytest_cache regenerated) produced a false NO-GO signal — all reds vanished on clean-slate export AND dirty-tree full run. Law: BEFORE any NO-GO/fix dispatch on collected-failure evidence, re-run fresh (or export the tree to a clean dir); count must survive the rerun to be admissible.
- Eval default --out writes a TRACKED ledger (2026-10-19): tools/eval/gameplay_eval_v2.py's default output path IS the tracked tools/eval/gameplay_eval_v2.json — ANY smoke run without --out clobbers the era-of-record ledger (103k-line diff caught pre-commit). Law: always pass --out for probe/gate runs; sibling lane should default to reports/ or refuse overwrite of a tracked path.
- Frozen-golden cross-wave rewrite (2026-10-19): a FULL-SUITE pytest battery run WHILE a sibling compiler wave was uncommitted left 122 M21 golden files REWRITTEN in the worktree mid-battery (conjunct reordering; mtime = inside the pytest window; the measure harness itself is verify-only and did NOT write). A PC-4 '0 diffs' read against self-healed bytes is a FALSE GREEN — the check compared the tree against the tree. Laws: (1) after any battery, ALWAYS git-status-audit MTG_bot/core/golden/ before trusting PC-4 or committing; (2) restore with 'git checkout -- MTG_bot/core/golden/' unless your wave owns the re-baseline via explicit --refresh-goldens; (3) clean-slate export (git archive HEAD | tar -x) is the tiebreaker for 'who broke frozen data' — HEAD was proven pure (0 diffs) in this incident.
- **A golden RE-BAKE left UNCOMMITTED on a shared tree is TRANSIENT (2026-10-19, R1a)**: my 122 legitimately-re-baked M21 goldens (R1a canonicalization) sat unstaged while the diff gate ran; a sibling ops sweep (cebdab6, "worktree goldens restored") classified them cross-wave contamination — correctly BY ITS LAW (stale-code goldens poison PC-4 self-heal; a restore is indistinguishable from the right kind without the sibling's context) — and reverted them. Laws: (a) golden re-bakes land in the SAME commit as the code that changes canonical_json — stage->verify->commit in one invocation, never a parked golden wave; (b) re-run golden guards IMMEDIATELY before the commit (a sibling restore makes them red, and the reds are TRUE guards); (c) announce big identity-surface waves by scaffolding KNOWLEDGE early (a one-line in-progress note makes a sibling's sweep ask instead of restore).
- **Process-global FIFO stash masquerades as encoding purity (2026-10-20, /134 precond 2)**: the cross-process off-policy audit was RED (31/100 asks, all choose: sites, max|Δ|=0.47) while the IN-PROCESS roundtrip test was GREEN — because v2 choose-candidate grounding reads bc_data_v2._STASH, a process-global memo (STASH_CAP=32) filled only by a LIVE engine; a file+checkpoint replay silently re-grounds choose candidates differently. Law: any replay-from-recorded-rows path must have the collector's process-global memo state PINNED IN THE ROW (rl rows now carry per-ask `choose`; bc_data_v2.stash_put re-enters it, null=blind stays blind); a green test that never crosses a process boundary has NOT proven record self-sufficiency. KNOWLEDGE/2026-10-20/137.
- **The 16a DAMAGE target-pre-bind SILENTLY cancels a trigger's own 18b designation lane (2026-10-20, /140/R2; mechanics corrected same day by the R2 diff-gate's probe4)**: `_fire`'s `if ctx.bindings.get("target") is None` gate meant any KIND_DAMAGE firing (dealer pre-bound as the TARGET_PLAYER anaphora, Brash Taunter's rationale) skipped `_designate` entirely. The pre-bound dealer then resolved the printed TARGET slot **TO THE DEALER ITSELF WITH NO FILTER VALIDATION** — mode-TARGET resolution takes a pre-bound handle as frozen designation without consulting the selector's zones+filter, so a non-event filter (CONTROLLER_IS OPPONENT) still destroyed the DEALER (probe4 Variant A: ask never fired, own artifact creature died instead of the opponent's totem; probe4.py at /tmp/opencode/r2gate/). (A filter carrying a `who=<selector 'event'>` clause fails at the *referent-candidate* step instead and lands on zero — "nothing destroyed" — which is what the Feline E2E showed; the two silences have DIFFERENT mechanics, don't conflate them.) Either way: no ask, no journal row, total silence. Post-fold this hit every damage-dealt trigger with a printed target. Law: a pre-bound slot resolving a TARGET selector must be VALIDATED against that selector's zones+filter (R2 fix: `_prebind_legal_for_targets`, fail → lift to the ask lane); an event-kind pre-bind that FEEDS an anaphora read must be gated on the node actually reading the event (r22a DIES twin, R2 damage twin `_damage_designation_is_event_borne`); when moving a trigger between journal feeds, re-check every pre-bound register the new feed carries — a feed change is a binding change.
