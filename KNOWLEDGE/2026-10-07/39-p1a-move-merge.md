# 39 — T4 P1a: verb-class partition + MOVE merge (EXECUTED, green)

Date: 2026-10-07. Scope: docs/T4_SPEC.md §1 + §9 executed. No commits (owner will commit).

## What shipped
1. **Verb CLASS partition** (`ability_tree.py`): `VerbClass` enum + `VERB_CLASS` map —
   OPERATION 6 (CHOOSE, CHOOSE_NAME, SCRY, SEARCH, LOOK_AT, PAY) / POLICY 7
   (MANA_POLICY, DAMAGE_ASSIGN_POLICY, GRANT_ACTIVATION, PREVENT_EFFECT, ADD_LAND_PLAY,
   MANDATE_ATTACK, MANDATE_BLOCK) / EFFECT 36 = 49 total. Pinned by
   `test_grammar_p1a.py::test_verb_class_partitions_the_full_enum_exactly_once`.
2. **MOVE merge**: MILL/DISCARD/EXILE retired from dispatch; one `_v_move_zone`
   handler + MOVE_ZONE slots `from` (Zone), `journal_kind` (∈ MOVE|MILL),
   `pop_order` (TOP), reusing existing `destination`/`target`/`cards`/`controller`/`amount`.
   Legacy enum members + `_VERB_ROLES` rows KEPT (golden/legacy decode; compiler no longer
   emits them). Branch order in handler: `pop_order==TOP` mill lane → `from.kind is HAND`
   discard lane → generic body; target-lane (no cards selector) = old exile.
   MOVE_ZONE atom requires ≥1 object axis (cards|target|amount) at construction.
3. **A2 pins honored** (AMENDMENT A2 i–iv):
   (i) discard lane writes `ctx.bindings["result"]` (register pin, old DISCARD contract);
   (ii) raw 12a journal rows keep literal `"MILL"` bytes via `journal_kind` slot —
   mill never writes "MOVE" rows (`test_executor_p1a_move.py` raw-row assertion, byte-identical
   pre- and post-merge);
   (iii) mill pops `lib.entries.pop()` TOP in a dedicated lane — never selector pool, never draw;
   (iv) exile designation lane = `role_handles("target")`, placement `controller_of(card)`,
   writes NO register (kept distinct from discard's result lane — pinned in
   test_executor_r20b/designation referent tests).
4. **Consumers re-pointed**: 35 compiler emit sites (b2a 9, b2b 3, b3 2, b4 1, b5a 3, b5b 7,
   b5c 9, +b5a manual `_draw_controller()` site) via scripted transform + ruff format;
   `legality.py` cost-discard `_binding_atom` (uses `**{"from": …}` — reserved word);
   `selectors.py` graveyard_sweep pin → MOVE_ZONE + destination-kind read (Tormod's Crypt;
   the one scenario FAIL caught and fixed at this step). `Keyword.MILL` grammar token
   untouched (compiler matcher, not dispatched). SUPPORTED_VERBS_V1 frozen untouched;
   V2 = frozenset(HANDLERS) shrank 46→43 automatically.

## Vocab answer (spec §9 obligation, provenance = episodes_v2 ground rows)
`build_vocab_v2` takes IR verb tokens via `cand_words_v2`: `move_zone`→{move, zone} are
ALREADY in vocab; retired tokens {mill, discard(verb sense)} drop out, and the new slot
tokens **from, journal_kind, pop, order, destination** + values **TOP/MILL** enter the
value/role token stream → vocab rebuild + retrain required (accepted: /38 precedent;
spec §9). Site-kind tokens unchanged (10); DISCARD picks emit 0 ask rows (silent selector),
so ask-row counts are unaffected by the merge itself.

## Verification (all executed 2026-10-07)
- Pre-lock proof: `test_executor_p1a_move.py` 3 tests were GREEN against the OLD handlers
  first, then atoms switched shape with **identical assertions** and stayed green = merge
  behavioral proof (mill/discard/exile triggers, life, zone order, raw rows, registers).
- `tools/run_scenarios.py` → **373/373** (after graveyard_sweep fix; 372 once = the pin).
- Golden refresh: **exactly 36/305 files** changed, 1 line each (A4 churn prediction was
  39 records / 36 files — verified); diffs hand-audited = verb+slot substitution only,
  controller refs propagate correctly (Teferi TARGET_PLAYER, Waker ANY, exile OWNER).
- `pytest MTG_bot/core -q` → **2460 passed / 0 failed** (was 2395+65); `-k "journal or replay"` 47;
  `pytest tools/audit tools/training -q` → 153; episodes rerun: items **157 / no_discrimination 0**
  (invariant), puzzle_cert + eval split unchanged (families 77, eval 32/51, new: []).
- Test migration: 19 files, +75/−31 assert lines; the ONLY non-shape removal is the
  deliberate `len(SUPPORTED_VERBS_V2)==46→43` pin; migrated IR tests now ALSO pin
  destination/from/journal_kind (strictly stronger). No skips/xfails added.

## Known drift (documented, accepted)
- `GameEvent.cause_verb` for these effects is now `"MOVE_ZONE"` (was MILL/DISCARD/EXILE)
  in journal fingerprints of affected scenarios — cause_verb string consumers audited:
  binding.py:870 `=="TARGET"`, binding.py:1010 `!="SACRIFICE"`, games.py:1050: none key on
  the retired names. Trigger MATCHING is endpoint-based and unaffected (proof: pre-lock tests).
- Incident (self-inflicted, repaired): a `ruff format $(git diff --name-only)` sweep by the
  migration agent hit golden `.json` files; repaired by deterministic `write_goldens` rerun
  (mangled copies at /tmp/opencode/golden_mangled_backup); final golden diff re-verified =
  36 files × 1 line. Lesson → PITFALLS: never feed golden JSON to ruff.

## Next (P1b candidates from /37 §9 order)
Pick-lift stays OUT (P2 gated), E1 controller-direction merge, then remaining EFFECT-verb
slot orthogonality per gap ledger; each set integration re-runs the §8 tokenizer audit.
