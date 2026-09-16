# 2026-09-14 · 01 — Orientation (session 1)

## Where the project is

- **North Star** (`NORTH_STAR.md`): strong MTG bot on the trained pool (Commander priority) +
  auto-extension to new cards built from known primitives (zero code changes) + play within a real
  match clock. Learnability principle: implement rules exactly, learn play, no hardcoded heuristics.
- **Rebuild**: D1 (environment) + D2 (ability-tree card representation), developed in
  `MTG_bot/core/`, in parallel with legacy `rule_engine`/`strategic_brain` (attic'd at cutover).
- **Phase 0 — DONE, committed** (`d03eb1f`): `core/identity.py` (Handle/HandleSpace namespaces,
  LegalityFlags, CardIdentity keyed on scryfallOracleId), `core/state.py` (GameWorld: zones,
  players, cards, seeded event clock, triggers, SHA-256 fingerprint), `core/errors.py`
  (EngineError family incl. UnsupportedAbilityError, InfiniteLoopError, StateCorruptionError).
  46/46 tests green.
- **Phase 1 — IN PROGRESS (this session): the ability-tree grammar.** Per
  `DESIGN_CARD_POOL.md` "Ordering": step 2 "Define the tree grammar; write the executor against
  it" + step 3 "Coverage instrumentation and the unparsed queue, from day one."

## Where things live

| Path | What |
|---|---|
| `NORTH_STAR.md` | outranks everything; priority ladder; overrule clause |
| `docs/DECISIONS.md` | settled decisions (D2 = ability tree is the foundation) — do not re-litigate |
| `docs/DESIGN_CARD_POOL.md` | **the Phase 1 spec**: tree grammar (Step 1), encoder (Step 2), residual (Step 3), compiler (4-step), ordering |
| `docs/METRICS.md` | measurement catalogue; Phase 1 unlocks GEN family (E4) + EC-2/EC-6/EC-7; §15 engine requirements E-*; rails 1.1-1.16 make a number admissible |
| `docs/DESIGN_ACTION_SPACE.md` | the *action token* grammar (later phase, different grammar — don't conflate) |
| `MTG_bot/core/` | the rebuild. Phase 0 done; Phase 1 modules land here |
| `MTG_bot/data/M21.json` | MTGJSON v5: `data.cards` (397), `data.tokens` (20) |
| `reports/` | measured JSON outputs (repo convention: `latency_*.json`, `decision_counts_*.json`) — grammar measurements go here too |
| `tools/` | measurement harnesses (latency/, teacher/) — `measure_grammar.py` goes here |
| `KNOWLEDGE/` | this tree; protocol in INDEX.md |
| `attic/` | dead legacy (do not read expecting live code) |

## The grammar spec (from DESIGN_CARD_POOL.md Step 1, verbatim intent)

```
Card     := { mana_cost, types, subtypes, supertypes, pt?, loyalty?, abilities: [Ability] }
Ability  := Static(Effect) | Triggered(Event, Condition?, Effect)
           | Activated(Cost, Effect) | Spell(Effect) | Keyword(kw, params)
           | Replacement(Event, Condition?, Action)
Effect   := Seq[Effect] | Choose(n, [Effect]) | Optional(Effect)
           | Conditional(Pred, Effect, Effect?) | Repeat(Quantity, Effect) | Atom(Verb, Args)
Verb     ∈ { DEAL_DAMAGE, DESTROY, EXILE, DRAW, MILL, GAIN_LIFE, LOSE_LIFE, ADD_MANA,
             CREATE_TOKEN, PUT_COUNTER, MODIFY_PT, SET_PT, GRANT_ABILITY, TAP, UNTAP,
             MOVE_ZONE, SEARCH, SHUFFLE, COUNTER_SPELL, COPY, SACRIFICE, DISCARD, ... }
Selector := { count: Quantity, mode: TARGET|CHOOSE|ALL|RANDOM, filter: Filter, zone, controller }
Filter   := Conj/Disj over { type, subtype, supertype, color, cmc_cmp, pt_cmp, keyword,
                            name_eq, tapped, attacking, has_counter, controller }
Quantity := Const(n) | X | Count(Selector) | Prop(of, field) | add/sub/mul/max/min
Duration := UNTIL_EOT | PERMANENT | WHILE(Condition) | UNTIL_YOUR_NEXT_TURN
```

Three load-bearing choices (do not weaken):
1. **Quantity on every numeric field, without exception** — no "X spells are special".
2. **One Selector type** used by targets, statics, counts, triggers, search — re-evaluated
   against current state, so the "anthem pumps everybody" bug is unrepresentable.
3. **Structured EventSpec** — ETB is a zone-change predicate, never a substring.
4. (bonus) Token creation takes a **nested card record**, not a string.

Compiler (4 steps): structured ingest → template matching (curated grammar, ~200 templates
covers most of a modern set) → explicit unparsed queue → golden file per card, committed;
oracle id primary key everywhere.

## Operating rules for this session

- Max 2 concurrent subagents; check `free -g` before a third; serialize below 5 GB available.
- Every delegation: Objective / File Scope / Constraints / Exit Criteria (AGENTS.md §4) + the
  KNOWLEDGE files to read first.
- Frequent measurement: after every module lands, run its tests + the coverage harness, and
  record headline numbers in KNOWLEDGE/NUMBERS.md with date + command.
- Commit in logical increments; put the measurement numbers in commit messages.
