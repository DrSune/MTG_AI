# PITFALLS — standing traps (each dated; newest first)

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
