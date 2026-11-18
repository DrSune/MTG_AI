# Plan: the cleanup and quality lift (written 2026-11-18; begins on the owner's prompt)

The owner, 2026-11-18: "write up a Cleanup plan that makes all our recent changes coherent and
anti-patchwork code. We also need to reduce bloat and clutter, make fewer, better and faster tests,
components, checks etc. A general project quality lift you could say."

**Status.** Written, not started. The owner starts it. OWNER_PREFERENCES #2 asks for a cleanup pass
at every era boundary and at least weekly. This week ended with seven merged rounds and waves, so
it is due.

**What it does not change.**
- **Behaviour.** Every wave is behaviour-preserving by construction, with the acceptance rules of §3.
- **Strength, and the MTG rules.** A change that would alter play is out of this plan. It goes to
  its own gate round.
- **r29.** r29 runs from its pinned worktree (60f0913f), so main can change under it.

## 1. State at writing (main 9ff00332, the full check green)

- **Merged today:**
  - zero fallback;
  - every public card as an entity;
  - the turn-so-far columns;
  - the rails;
  - planner v1 behind its flag;
  - the planning puzzles;
  - engine waves E3, W0 and W1;
  - gate rounds B3 (copies), B12 (the opening hand, prohibitions, the game's end) and W3 (state
    triggers, extra triggers, reveal rows);
  - verification wave 7;
  - the red team's findings folded into the plans (216).
- **Cards.** Verified: M21 268/285, M20 278/329, FDN 256/517. W3 re-baked 36 verified trees,
  mostly reveal rows with play unchanged, so they wait for re-verification.
- **Still open, outside this plan:**
  - the re-verification wave: W3's 36 cards, B12's four new M20 cards, Nine Lives, Sublime Epiphany,
    Yarok, and Chandra's Flame Wave before the next planning readout;
  - B8's re-read at r29 B's update 500 (208 §12, its rule registered);
  - engine waves W2 and W-D;
  - the M20 rounds;
  - the network builds of PLAN_LONG_RUN.

## 2. What the measurement says (the baseline; commands in the commit that adds this file)

| What | Now | Why it matters |
|---|---|---|
| Core code against core tests (`MTG_bot/core`, Python lines) | 61,434 code, **82,222 tests** | Tests outweigh what they test. Many are per-card or per-round examples of one property |
| Test files named after a round or wave (`test_*_b12`, `_w3`, `_r5_*` ...) | **67 of 168** core test files | Organised by history, not meaning. A reader looking for "copies" must know the round that built them |
| Compiler template modules | **22**, named by batch (`templates_b1` ... `templates_b21`, `b2a`, `b5c`) | The same: a wording's home is the week it arrived |
| Largest files | `ability_tree.py` 295 KB, `executor/__init__.py` 187 KB, `test_selfplay.py` 160 KB, `verbs.py` and `legality.py` 136 KB, `binding.py` 126 KB | One file holds several concerns. Every round edits the same few files, and every parallel round conflicts there (tonight: B12 against W3 in ability_tree, the ontology doc, a golden, BACKLOG) |
| The full check, `tools/check.sh` at nice 19 beside a run | **6 min 31 s**: engine 155 s, tools 212 s, packs and lint the rest | The pre-merge gate is slow enough to tempt `--quick` |
| Slowest tests | the engine's top 20 take 70 of its 155 s; the tools' top 5 take 64 of 212 s (r28 v2's bitwise check 19.8 s, reprint stamps 16.1 s) | Half the time is in a few dozen tests and setups that rebuild compiled pools |
| Scenario packs | 820 runner packs; 2,077 card packs, 387 mapped, 21 known bugs | Packs are the best tests here: the printed text, played. They are also where per-card examples should live |
| `reports/` | 54 dirs, **232 Python scripts**, 444 MB. `census.py` ×18, `replay.py` ×16, `tree_dump.py` ×13, `replay_compare.py` ×11, `tree_diff.py` ×10 | One blast-radius protocol copied per round. W0 promoted it to `tools/audit/blast_radius.py`; the copies remain |
| Docs | 41 files, 24,980 lines. 21 PLAN or DESIGN docs. BACKLOG 2,414 lines, 199 entries | Several plans claim the current order (PLAN_LEARNING, PLAN_CEILING, PLAN_PLANNING, PLAN_LONG_RUN, PLAN_NETWORK_READINESS). BACKLOG held three entries twice, a merge artefact found tonight |
| Worktrees | 12 pinned (r27, r28, w2, cw, gateb, verify3-7, r29) and 2 scratch | Only r29's is in use |
| Loose top-level files | 12, seven of them pre-rebuild notes (`gemini_analysis.md`, `engine_map.md`, `ideas.md`, `notes.txt`, `project_goals.md`, `project_specific_gemini_context.md`, `thought_checkpoint.md`) | Kept as owner-idea sources (OWNER_IDEAS). They belong in one archive folder, not the root |

**Tonight's lessons, folded in below:**
- My merge check ran `check.sh --quick`, which skips `pytest tools`. Main was red for an hour
  (the latent-fault guard): §4 C6.
- The guard kept entries for faults the copy round had closed: C6.
- BACKLOG gained duplicate entries in a merge that kept both sides: C2.

## 3. The rules of the lift

1. **Behaviour preserved, measured, not assumed.** A wave is accepted only if all of these hold:
   - **(a)** 0 compiled trees change over the 19 sets (tree dump), unless the wave is a registered
     fold with its own gate round;
   - **(b)** 600 seeded heuristic replays of the verified pools are identical (`blast_radius.py`);
   - **(c)** every pack passes;
   - **(d)** the mutation kill matrix (C0) loses no mutant;
   - **(e)** engine games per CPU-second are not slower (±3%);
   - **(f)** the full check is green.
2. **One mechanism per job** (OWNER_PREFERENCES #2). Where two paths answer one question, one goes,
   and its callers move to the other.
3. **Organised by meaning.** A file, test or template lives with the component it is about, never
   with the round that built it. History stays in git and KNOWLEDGE.
4. **Every deletion has a reason in its commit:**
   - what subsumes it (a test, a pack, a mechanism);
   - or why it was dead (no caller; a closed fault; a superseded plan).

   A test that pins a named bug-hunt fault stays, or folds into a family that still pins it.
5. **Nothing is lost.** Branches are merged or tagged before a worktree is removed. A script whose
   number is cited is kept until NUMBERS.md cites the commit that held it.
6. **One wave at a time per file set**, in a worktree, with a fresh-eyes reviewer, merged with the
   FULL check.
7. **Write down why, and name assumptions** (the owner's standing rules). Each wave's report says
   what it assumed and what changes if that is wrong.

## 4. The waves

Sizes: S is under an hour of agent work, M is a few hours, L is a day.

### C0. The evidence harness (S-M; first, because every other wave is accepted on it)
- **The mutation kill matrix.** `tools/audit/kill_matrix.py` runs a mutant set against the suite
  and records which tests kill which mutants (`pytest --deselect`-style runs; per-area sampling to
  keep it to a CPU-hour). The mutant set is:
  - the G3 operators over the verified trees;
  - the engine mutants the gate reviewers wrote this week (`mutate.py` in their scratch notes:
    B12's 12, W1's, W3's);
  - a small set of operator mutants in the executor's hot rules (comparisons, off-by-one on counts,
    controller and owner swaps), the class-D audit's shapes.
- **The baseline:** the table of §2, re-measured by one script (`tools/audit/quality_report.py`),
  so every wave reports its delta in the same numbers.
- **Why first.** Removing tests by coverage loses fault detection (Rothermel et al. 2002 found
  large losses when suites were minimised by statement coverage). Removing them by mutant kills
  keeps what tests are for.
- **Transfer check.** Mutation analysis assumes the coupling effect: simple mutants stand in for
  real faults (DeMillo, Lipton and Sayward 1978).
  - Here most real faults were missing cases and object identity (215's causes A-D), not operator
    slips.
  - So the set is domain-shaped (G3, the class-D and identity shapes, the reviewers' mutants), and
    rule 4 keeps every test that pins a named fault whatever the matrix says.

### C1. Clutter (S; no code risk)
- **`reports/`:**
  - Delete the one-off scripts whose numbers are in KNOWLEDGE or NUMBERS (memory rule, 2026-11-05).
  - The 68 copies of census, replay, tree_dump, replay_compare and tree_diff go first:
    `tools/audit/blast_radius.py` is the one protocol.
  - Keep results, regression evidence and anything a KNOWLEDGE note cites by path, unless NUMBERS
    re-cites it.
  - `reports/replays/` (31 MB) is kept or pruned by its citations.
- **Worktrees:**
  - remove r27, r28, w2, cw, gateb and verify3-7, after checking each holds no unpushed commit and
    no uncopied result (verify waves 3-7 are already in main's `runs/`);
  - remove the two scratch worktrees;
  - delete merged agent branches.

  r29's worktree stays while its run lives.
- **Loose files:** the seven pre-rebuild notes move to `docs/archive/owner_notes/`, with OWNER_IDEAS
  and CLAUDE.md's layout table pointing there. `pyproject.toml` and `pyrightconfig.json` stay.
- **The old pinned checkpoints:** prune only what neither `reports/LARGE_FILES.sha256` nor a NUMBERS
  command cites (CLAUDE.md's rule after 2026-11-06's loss).

### C2. Docs, one current order (S-M)
- **One roadmap.** `docs/ROADMAP.md` holds the order of work and the GPU calendar now spread over
  PLAN_LONG_RUN, PLAN_PLANNING §6, PLAN_NETWORK_READINESS §6 and 209 §9.
  - Each plan keeps its design and its registered experiments, and points to the roadmap for
    "when".
  - PLAN_LEARNING (Phase 0 done) and PLAN_CEILING's H1/H2 sections get a status line saying what
    superseded them.
- **BACKLOG:**
  - deduplicate, finding the duplicates by script;
  - move every closed entry to a dated "Closed" appendix or delete it where git and KNOWLEDGE
    already record it;
  - keep one line per entry's status;
  - a check in `check.sh` fails on two entries with the same title.
- **CLAUDE.md:** the "current state" paragraph shrinks to pointers (the roadmap, NUMBERS, the
  running unit). The layout table follows C1's moves. The baseline paragraph moves to NUMBERS.
- **DESIGN_ATOM_ONTOLOGY (now about 3,000 lines):**
  - a one-page index of components (each atom, value and form, with its section) at the top;
  - the per-round sections stay as the gate log.

### C3. Tests: fewer, better, faster (M-L; after C0, and C3c after C4 so tests move once)
- **C3a. Speed first (S-M).**
  - The slow setups rebuild compiled pools and supplies (`test_primer` 10.5 s, the object-tables
    walk 6.7 s, the supply tests): session-scoped fixtures, one compile per pool per run.
  - The slowest 30 tests are each kept, made cheaper or moved to a nightly tier, with a reason.
  - Target, said aloud: the full check under 4 minutes beside a run (from 6.5).
- **C3b. Tiers that cannot skip what changed** (tonight's lesson).
  - `--quick` runs the engine suite, the self-play smoke, the latent-fault guard and the packs of
    the touched area. It stays under 60 s.
  - The full check is the gate for every merge and every push of code. A docs-only commit may use
    `--quick`.
  - `check.sh` prints which tier ran, so a report cannot quote a quick run as a full one.
- **C3c. Organised by component.**
  - The 67 round-named test files fold into their component's file: copies, triggers, prohibitions,
    permissions, reveals, the opening hand, layers and so on.
  - Per-card example tests whose behaviour a pack already plays become packs or are deleted (rule
    4).
  - `test_selfplay.py` (160 KB) splits by module.
- **C3d. Fewer by the kill matrix.**
  - A test that kills no mutant another test doesn't also kill, and pins no named fault, is folded
    into a parametrised family or deleted, each with its subsumer named.
  - Target, said aloud: core test lines no more than core code lines (82k to at most 61k), with the
    kill set unchanged.
- **C3e. Better: properties over the pools.**
  - Several families of example tests state one invariant:
    - a card is in one zone;
    - the state-based actions are idempotent;
    - a replay is deterministic;
    - an observation holds no hidden card (I1-I3);
    - every option a menu offers can be taken;
    - a seen row names its viewers.
  - Each becomes one property test over seeded games of the verified pools (QuickCheck-style). The
    soak detectors already are this; the property tests are their fast, always-on form.
  - Transfer check: property testing assumes the invariant is stated exactly. The CR states these,
    and where an invariant has exceptions (CR 400.7d-h), the exceptions are enumerated in the test,
    as W1 did.

### C4. Code coherence, the patchwork seams (L; one seam per wave, each reviewed)
The seams this week's rounds exposed. Each answers one question in more than one place.
1. **Object identity (CR 400.7).** Today it is spread over:
   - W1's `gone` register;
   - B3's `LastKnown`;
   - `departed_lki`;
   - the zone-change clocks;
   - permissions' `moved_since`;
   - the planner's own `Tracker` keys.

   One engine service answers "is this the same object" and "what was it last", and every reader
   calls it. DESIGN_PLANNER §7 proposed it: a clock per handle, written where ZONE_CHANGE is
   journalled.
2. **What players know.**
   - W3's seen rows carry viewers; SEARCH and MOVE rows still name hidden cards without them.
   - J3 and J4 (a library move's end; SHUFFLE as an event) are pending.
   - One knowledge-event record, the one memory v1 reads (PLAN_NETWORK_READINESS §4.4), and the old
     rows either carry viewers or leave the log.
3. **Can and can't (CR 101.2, 601.3).** Today they are:
   - PERMIT and REPLACE (round 13);
   - PREVENT_EFFECT's prohibition lanes (B12);
   - `optional_offer`'s narrowing (F43, W-D);
   - `_cant_enter`;
   - the menu's legality.

   One legality model, documented, with one entry point per question: may this be cast, may this
   enter, may this be chosen.
4. **Triggers.** State, additional, delayed, reflexive and the quarantine scaffold: one queue path
   in `binding.py`. W3 began it by removing the carrier.
5. **The game's end.** `Executor.lose` (B12) is the one loss path. Verify that every loss reaches
   it (poison, B4, will).
6. **The compiler's templates.** The 22 batch modules regroup by grammar area (triggers, costs,
   effects, statics, keywords) behind one registry. The tree dump over 19 sets must be identical.
7. **The large files.**
   - `ability_tree.py` splits into a package by concern (nodes, roles and laws, validators and
     faults, serialisation), re-exporting its names so no caller changes.
   - `executor/__init__.py` splits the state-based actions, priority and steps, and zone changes.

   Why: every parallel round conflicted in these files tonight. Smaller files by concern make
   rounds independent.
8. **tools/selfplay's dead weight.**
   - Flags that do nothing: `--name-dropout` acts only in BC (216 C4). Its encoding-level arm is
     planned; until then the flag says so.
   - Code paths left by the fallback's removal.
   - Helpers duplicated between actor, search, linevalue and trace.

### C5. Components: fewer, better (M; analysis now, folds as gate rounds)
- **The redundancy review** 209 asked for after M21 and M20 runs now, as analysis only, over:
  - every atom, value and form, this week's included (CopyOf, StateTrigger, TRIGGER_ADDITIONAL,
    OpeningHandAbility, the prohibition lanes, the reveal forms, QDistinct, PERMIT, REPLACE);
  - the question for each: does it break down into existing ones (210's method)?
- **Folds that change trees** become gate rounds scheduled with the card rounds, with
  re-verification. They are not part of the behaviour-preserving waves.
- **G3 coverage per role.**
  - B12's gate found 0 mutants for a prohibition's actor, ordinal, zone and win/lose flag.
  - W3's found none for an extra trigger's cause, which W3 then added.
  - Every IR role gets at least one critical mutant operator, so the packs are never the only gate.

### C6. Checks and gates: one check per question (S-M)
- **The overlap map.** G0's lints, the IR validators, `tools/audit`'s conformance tests, the
  latent-fault guard, the soak detectors and the dead-role rules: say which question each answers,
  and fold the overlaps.
- **The latent-fault guard's maintenance.**
  - A wave or round that closes a fault deletes its entry in the same merge (tonight's F40 and F60
    lingered).
  - The guard's docstring and 215's row status are updated together.
- **Card-tool speed.** `cardtool verify`, `survivors` and `packet` share the compiled pool cache
  (C3a's fixtures).

### C7. Faster code (M; measured, replays identical)
- **Profile the engine** over the 600 replays: games per CPU-second is 2.3-2.7 on today's pools.
  Fix the top hot paths. Known candidates:
  - `check_states` sorting at every priority check;
  - `_prohibitions`;
  - `spell_castable`, at 5.8 µs a call;
  - the menu.
- **Self-play throughput.** r29b is train-bound (PLAN_LONG_RUN's throughput budget). Profile the
  trainer's step (collate, forward, backward) before the network builds add their costs.

## 5. Order, size and budget

| Order | Wave | Size | Waits on | Runs beside |
|---|---|---|---|---|
| 0 | The re-verification wave (outside this plan, restores the pools) | M (Sonnet) | — | C0, C1, C2 |
| 1 | C0 the evidence harness | S-M | — | C1, C2 |
| 2 | C1 clutter, C2 docs | S, S-M | — | each other |
| 3 | C3a speed, C3b tiers | S-M | C0 | C6 |
| 4 | C4 seams 1-8, one at a time | L | C0; C3b (the full gate) | C5's analysis |
| 5 | C3c-e tests by component, fewer, properties | M-L | C4's moves (tests move once) | — |
| 6 | C6 checks, C7 speed | S-M, M | C0 | — |
| 7 | the scorecard: §2's table re-measured, against the baseline | S | all | — |

- **Budget.** About two days of agent work for C0-C3, and two to three for C4. The weekly limit
  resets 2026-11-23. One wave in flight at a time keeps the burn near 2% an hour. Tonight, six
  agents at once burned about 7% an hour.
- **Sequencing with the rest.** The cleanup goes before the M21+M20 training segment's code pin, so
  the segment trains on the lifted code, and before the network builds of PLAN_LONG_RUN, which
  would otherwise be built on the seams C4 removes. The card rounds pause during C4, which edits
  the same files.

## 6. Assumptions, and what changes if one is wrong

| # | Assumption | Where it binds | If wrong |
|---|---|---|---|
| A1 | The replays, the tree dump and the packs detect a behaviour change | §3's acceptance | They cover the verified pools' paths. A path no verified card reaches is covered only by unit tests, so C3d deletes no test of such a path without a mutant showing a subsumer |
| A2 | Domain-shaped mutants stand in for the real faults (the coupling effect) | C0, C3d | A test that catches a real fault no mutant models could be deleted. Rule 4 keeps every test tied to a named fault, whatever the matrix says |
| A3 | Splitting large files by concern makes rounds independent | C4.7 | If the concerns are entangled, the split moves the conflicts rather than removing them. Measure: conflicts per merge before and after |
| A4 | Organising by component makes code and tests easier to find and to keep coherent | C3c, C4.6 | The cost is one round of churn. With no branch in flight, that is the cheapest time |
| A5 | Speed targets (4 min full, 60 s quick) are reachable without dropping coverage | C3a, C3b | If not, the nightly tier holds the slow tests and the gate keeps the fast ones. The kill matrix shows what moved |
| A6 | No training run imports main's code during the lift | rule 6 | r29 runs pinned. A run started from main during C4 would train on half-moved code, so the segment's pin waits for the lift |
| A7 | The owner wants the same strength and rules, faster and cleaner, and no new features in this plan | scope | A feature or fold found along the way is logged in BACKLOG or the roadmap, not built here |

## 7. Deliverables

- One merged commit series per wave, each with its numbers against the baseline and its reasons.
- `tools/audit/kill_matrix.py` and `tools/audit/quality_report.py`, kept as tools in regular use.
- `docs/ROADMAP.md`, a deduplicated BACKLOG, and a CLAUDE.md that points instead of narrating.
- The scorecard in a KNOWLEDGE note: every number of §2, before and after.
