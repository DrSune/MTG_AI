# PITFALLS — standing traps (each dated; newest first)

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
