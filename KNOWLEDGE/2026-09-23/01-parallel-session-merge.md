# 2026-09-23 · 01 — Parallel-session merge (JOURNAL session work absorbed)

**Fact:** a second session (the "self-improving loop" session — see
`tools/compact_journal.py`, `tools/test_self_improvement_loop.py`,
`KNOWLEDGE/JOURNAL/`) ran in the same repo for ~24h in parallel with the
orchestrator session and landed substantial, tested work. Verified on disk
2026-09-23; all of it passes the 1004-test suite and is semantically
sane (orchestrator reviewed the compiler.py diff line by line + spot-checked
goldens).

## What the parallel session landed (now part of the working tree)
1. **Choose-opener compiler built-in** (`compiler.py`): folds "Choose one —" /
   "Choose one or more —" / "When this creature enters, choose one —" /
   "Whenever this creature attacks or blocks, choose one —" openers with their
   "• …" option bullets into `Choose` nodes; `_OPTION_CONSUMED` sentinel keeps
   the one-outcome-per-sentence alignment; 7 cards now fully parsed.
   Documented KNOWN-GAPs: "one or more" uses QUnbounded (no QAtLeast(1));
   "attacks or blocks" decomposes into two TriggeredAbilities (behaviourally
   equivalent — a creature can't do both in one turn). See
   `KNOWLEDGE/2026-09-22/04-choose-opener.md`.
2. **Search-shuffle built-in**: "If you search your library this way, shuffle."
   (6×) synthesized as `SHUFFLE(LIBRARY(YOU))` injected INSIDE the preceding
   OptionalEffect's sequence (correct: shuffles only when the optional search
   happened).
3. **Phase-in prevention built-in**: "Until the end of your next turn, they
   can't phase in." (Teferi [−8]) synthesized as
   `PREVENT_EFFECT(condition=CONTROLLER_IS(OPPONENT), event=ZoneChangeEvent
   (COMMAND(OPPONENT)→BATTLEFIELD(OPPONENT)), duration=DurationUntilNextTurn)`
   appended to the [−8] activation. Grammatically correct pattern (PREVENT
   _EFFECT takes event+condition+duration).
4. **B5c round-3**: Ugin [−X] covered (`CostLoyalty(delta=QX())` +
   `CMC_LE(QX)` + `COLOR_COUNT_GE(2)` + `EXILE` ALL) — the T7 "false UNCOVERED
   candidate" confirmed; Ugin [−10] FILTER BUG FIXED (permanent-card
   restriction now `FOr(TYPE_EQ(Creature|Enchantment|Artifact|Land|
   Planeswalker))`). b5c UNCOVERED 24→17. Teferi + Ugin now 0 unparsed.
5. **PC-4 harness bug found (not yet fixed):** `measure_grammar.py` calls
   `write_goldens` before `verify_goldens` → PC-4 can never report diffs;
   `MTG_bot/core/golden/M21/` is untracked in git → no cross-run baseline.
   Fix pending (verify-only default + `--refresh-goldens` + commit goldens).
6. UNCOVERED reason-text refreshes in templates_b5a/b2a/b2b (no count changes).

## Consequences for the orchestrator plan
- The "if you search this way" compiler rule, the phase-in shape, the choose
  family, Ugin [−X] and the Ugin [−10] fix are DONE (by the parallel session).
- My B4 conditional-costmod template task was LOST (its slot returned the
  parallel session's report); B4's "This spell costs {N} less to cast if
  you've gained N or more life this turn." is still UNCOVERED (CostModifier.
  condition + LIFE_GAINED_THIS_TURN_GE are available since grammar round 2).
- B5a additional-cost shapes (4 queue entries) still need the compiler
  `SpellAbility.additional_costs` hook (b5a agent Option-B finding), then
  templates.
- **PC-6 PHASE_IN orphan decision:** PHASE_IN (cards, controller) is the
  symmetric complement of in-use PHASE_OUT; no M21 card text uses active
  phase-in (it is automatic rule text). Decision: accept as a documented
  justified orphan (cross-set primitive, mechanic symmetry) — PC-6 pass/fail
  becomes "0 unjustified orphans; 1 documented accepted (PHASE_IN)". Owner
  ratification pending.

## Standing rule going forward
Two sessions must not edit the same repo concurrently. The JOURNAL tooling
(`tools/compact_journal.py`, `KNOWLEDGE/JOURNAL/`) is an untracked artifact of
the parallel session — keep it OUT of this session's work and commits until
the owner decides its status (feature vs. stray experiment).
