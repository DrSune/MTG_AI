# 2026-09-29 · 10 — Round-12 close-out: the executor exists, measured, and told the truth

Phase-2 T6 landed same-day as grammar round 11 (owner "gogogo" 10:10). Commits: e638d57 (plan) ·
2a2c96f (12a verbs) · f08e490 (12b binding) · 3c443f7 (12c legality/query) · f6b0134 (12d
layers/durations/replacements) · 801cee6 (12e feed+measure). Gate doc 06 (6 rulings held: state.py
FROZEN all round — zero edits; grammar/goldens FROZEN; rule_engine FROZEN untouched).

## What exists now (MTG_bot/core/executor/, ~2.9k LOC, 152 new tests)
- Executor(GameWorld): 24-verb dispatch (flag-don't-degrade: NotImplementedError on the other 25);
  seeded RNG; Handle-sorted ops; fingerprint = world+journal+ledger+layers+binder dumps.
- Event journal (diff-inspect at Atom boundaries; C18 was-snapshots) + TriggerBinder (attach/
  lifecycle/APNAP drain via frozen order_key/200-fire tripwire; combat/cast nodes raise at bind).
- legality.py + query.py = the C15 model surface in Slate vocabulary (typed IR refs, no prose,
  Handle-sorted, pure): legal_activations/legal_targets/validate_target_selection/choose_options/
  optional_offer/rest_of, CR-cited cost rules (117.3/119.4/602.3), C17 declaration-vs-resolution
  split pinned, completeness fixtures (up-to-two=10 sets size≥1; may 2-way; choose-one).
- durations.py (full vocab + tombstones), layers.py (anthem recompute; keyword_of = printed∪
  granted−lost; granted activations become activatable), replacements.py (C24 damage interception;
  Frost-Breath PREVENT with live UNTAP consumer), begin_turn UNTAP step (freeze survives exactly
  one tick), Choose-at-runtime (12c ORDER contract).
- Proof cards run from REAL compiled goldens: Frost Breath, Nine Lives (+ Llanowar Visionary,
  Tormod's Crypt, Bloodfell Caves queries).

## First PC-7 signal (NOT the gate — that's T10 games): engine_supported 206/305 (0.6754)
Honest dispatch-readiness via AND-fold (compiler L1459-72); flip proof Catalyst (CAST+DRAW).
The 99 flagged cards cluster: spell-resolution-era verbs (CAST/COUNTER_SPELL/stack), DRAW/SEARCH
runtime (library-effect semantics exist as atoms but handlers pending), policy/permission verbs
(MANA_POLICY, DAMAGE_ASSIGN_POLICY, GRANT_ACTIVATION, GET_EMBLEM runtime), MANDATE_*, FLIP_COIN,
END_TURN/EXTRA_TURN. This is the NEXT executor arc's work list, in measured order.

## Invariants held all round (re-verify after any executor change)
PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 (goldens byte-identical, both measure modes) ·
core suite 1876 · repo-wide legacy 23 failures = HEAD parity (rule_engine/strategic_brain,
frozen boundary doc 06 ruling 2).

## Next (order per docs)
1. Executor arc 2: DRAW/SEARCH semantics → stack/casting (CAST) → policy-verb runtime → combat
   skeleton — then the 5 queue-shape machinery (introspection/action-history/trigger-dup/dig).
2. T10-era: random-policy full-M21 games → PC-7 real gate; PC-8 rises with legality.
3. Small grammar-side items still open (doc 04/09-29): Speaker lossless upgrade, HAS_COUNTER_GE.

## Session numbers
Grammar arc (prev session): PC-1 231→301, PC-2 539→634, suite 1278→1724, queue 98→5.
Executor arc (this round): suite 1724→1876, PC-7 first honest 0.6754, zero regressions to any
grammar measurement. All decisions/ledgers: docs 06-09 + NUMBERS (dated, command-backed).
