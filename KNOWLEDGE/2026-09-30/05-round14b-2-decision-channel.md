# Round 14b-2 — the decision channel rebuilt (B-4/B-5 closed)

## The channel (owner ruling /02 + /03 B-4, implemented)

`MTG_bot/core/executor/decisions.py` — `DecisionStream`, one per Executor (`executor.decisions`),
riding EVERY ExecCtx (`_ctx`, `_cast_ctx`, `ctx_for`, binder firings, payment and replacement
contexts). A demand is `take_decision(vocab, what)` where `what` is a stable site tag. Lanes in
order:

1. **per-op pool** (`decisions=` kwarg) — byte-identical legacy behaviour, still vocab-validated
   (this is why ~30 existing unit-test call sites did not move);
2. **per-(vocab, what) FIFO** — `stream.push(vocab, what, *answers)`, served whenever the demand
   arrives, whenever the arming happens (B-4's zero-prediction lane);
3. **ask-time provider** — `stream.provider(vocab, what)`; the harness registers
   `lambda vocab, what: policy.rng.choice(vocab)`. Exhaustion raises (C15: no default).
   `ask_log` / `answered()` record the consumed history in ask order.

Producer tags (the /03 table): `may:<source>` (vocab = the query's *narrowed* `optional_offer` —
query/runtime identity), `choose:<source>:<sha1-digest of option-sets>` (Choose node),
`mana:<source>` (any-colour ADD_MANA), `scry:<player>:<n>` (per-card FIFO under one key),
`choose:<source>:<digest(rows)>` (CHOOSE verb), `name:<source>` (CHOOSE_NAME). FLIP_COIN and
RANDOM selectors stay `ctx.rng` (13a ruling: RNG is not a decision) — untouched, suite-pinned.
Site digests use `hashlib.sha1` (cross-run stable; builtin `hash()` is salted).

## Two deliberate deviations, documented per the ruling

1. **Ask-time provider instead of a pending-poll/op-completion loop.** A demand can occur
   mid-`Seq`, after earlier atoms already mutated the world; suspend-and-refire would re-execute
   them (no journal rollback; state.py frozen). The provider answers at the demand point — same
   enumeration, right where it is needed. Pending-state introspection remains available
   (`ask_log`).
2. **The runtime may-ask uses the narrowed offer vocabulary.** Pre-14b the runtime always asked
   `('fire','skip')` and `_v_pay` raised on an unpaid fire. Now `('skip',)` IS the whole
   vocabulary when firing is infeasible — an illegal decision cannot be expressed. One pinned
   raise moved upstream (`test_fire_on_unpayable_raises`, AMENDED).

## Harness fidelity (C15, strengthened not weakened)

`games.py` policy: target designation via `legal_casts`/`legal_activations`/slot queries (incl.
the NEW synthesized TARGET_PLAYER slot, `TargetSlot.synthetic`), decisions via the provider only.
Deleted: `effect_decisions`, `_atom_decisions`, `_actor`, `trigger_decisions`, `TRIGGER_TAIL`,
`SCRY_VOCAB`, `MANA_COLOR_VOCAB`, `_names_a_player`, `_cast_bindings`. Provider registration
lives in `_play` so `--repro` gets it too (the CLI path bypasses `play_game` — found by testing
`--repro 0`).

## PC-7 rerun, 10 seeds, cap 60, deck-pairs 1409 (vs 14a/14b-1)

| pool | survived 14a→14b-2 | mean turns | max | fired≥1 action |
|---|---|---|---|---|
| all (285 deckable) | 0/10 → **1/10** | 9.0 → **28.7** | 44 → 60 (cap) | 34 cards |
| engine (267) | 1/10 → **3/10** | 17.4 → **38.8** | 60 (cap) → 60 ×3 | 39 cards |
| castable (88) | 0/10 → 0/10 | 2.0 → **14.0** | 8 → 34 | 33 cards |

The 30-seed trigger (engine ≥5/10 to cap) NOT met (3/10) → 10 seeds reported. The scry/may/mana
vocabulary-rejection class is **gone from all three pools**; the wall moved to the 12c-prompt
selector pair (B-13) — see /03 STATUS UPDATE table for the full recount (B-13…B-18).

## Gates

core **1996** (1993 + QX pin + exhaustion pin + REST/ONE_OF pin; DecisionSurfaceTest rewritten as
an ask-time C15 proof, B-4 test flipped to a fix-proof with replay-fingerprint pin, B-7 pin
moved from a seed path to the predicate itself, B-8 rewritten onto the synthesized slot),
PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 **0 diffs** EXACT, engine 286 pinned, pyright **0**,
ruff **delta 0** (34 = 34; new `decisions.py` clean), replay determinism pinned (two runs, one
seed, identical fingerprint/digest/coverage). No commit (standing instruction).
