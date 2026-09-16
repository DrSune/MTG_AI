# KNOWLEDGE — dated knowledge tree (read this FIRST every session)

**Protocol (binding for all agents, see AGENTS.md §6):**

1. **Session start**: read this file, then the newest dated folder's `01-*.md` orientation note,
   then `NUMBERS.md` (latest measurement table) and `PITFALLS.md` (standing traps).
2. **Before touching a subsystem**: read the knowledge file for that subsystem if one exists
   (see map below). Delegated subagent tasks MUST name the specific knowledge files to read in
   the task prompt — a subagent that has not read the relevant knowledge file is operating blind.
3. **After any discovery, decision, or measurement**: append it to the day's folder (new numbered
   file) and, if it changes a standing number, update `NUMBERS.md` with the date; if it is a trap,
   append to `PITFALLS.md` with the date.
4. **Dating**: every file is dated in its path (folder) and its title. Never delete older entries —
   mark them `superseded by <file>` instead. Knowledge decays; the date tells you how much to trust it.

## Map

| File | What it holds |
|---|---|
| `NUMBERS.md` | The measurement log: dated tables of every number the project has, with what changed it |
| `PITFALLS.md` | Standing traps: things that cost time if rediscovered, each dated |
| `2026-09-14/01-orientation.md` | Session 1 orientation: repo state, phase status, where things live |
| `2026-09-14/02-phase1-plan.md` | Phase 1 (ability-tree grammar): plan + pre-registered measurement targets PC-1..PC-10 |
| `2026-09-15/01-ingest-dedup-decision.md` | Session 2: M21 reprint-duplicate oracle ids, dedup decision (pool = 305), ingest module shipped |
| `2026-09-15/02-ingest-review-fixes.md` | Session 3: ingest review fixes — paren-depth-aware split, emblem/related handling, validation, explicit dedup key, re-measured baselines 927/503 and 639/510 |
| `2026-09-15/03-grammar-review-fixes.md` | Session 5: ability_tree grammar review fixes — player referents (ZoneKind.PLAYER / ControllerRef.TARGET_PLAYER), FAtom.count is now Quantity, duration role for TAP/UNTAP/MANDATE_ATTACK; 366 tests, pre-golden timing |
| `2026-09-16/01-handoff-continuation.md` | **READ THIS FIRST if resuming**: session stop at 510 tests; remaining tasks T1–T9 with specs; UNCOVERED register; per-card translator+adversarial protocol (owner decision 2026-09-16); operating lessons |

## How numbers flow

`tools/measure_grammar.py` → `reports/grammar_*.json` (raw, machine) → `NUMBERS.md` (headline, human, dated).
A number not recorded in `NUMBERS.md` with a date and its producing command does not count as known.
