# 13 — Wave-3 fix batch C (r20c): cast/cost/attach lanes — batch close

HEAD 004aa83, engine editing **authorized**. Scope: the last 6 wave-3 suspects — hobblefiend,
malefic_scythe, waker_of_waves_activation, speaker_of_the_heavens (executor-fixable) plus
ornery_dilophosaur and creature_spell_nodes_systematic (compiler-side). Outcome: **4 fixed &
promoted (runner 204/204; suite 2213), 2 STOPs with written root causes; every gate green —
and for the first time in the campaign, the trace catalog needed NO repin (0/10 diverge)**.

## Per-item verdicts

| Suspect | Diagnosis | Fix site |
|---|---|---|
| hobblefiend | Effect's self-designation ("put a +1/+1 counter on **it**") is a CHOOSE-selector filtered on IS_SOURCE, but `role_handles` was binding-FIRST under the shared role name `target` — and the COST lane (Sacrifice) journalled its TARGET pick into the same binding, so the counter hijacked onto the sacrificed creature | `selectors.py` `_filter_is_self_referential` (IS_SOURCE anaphora walker, same shape as `_filter_has_referent`) + `self_ref` exemption in `role_handles`; TARGET mode stays the designation lane, exemption inert for every non-self filter |
| malefic_scythe | The leave-detach sweep prunes `executor.attachments` while handling the ZONE_CHANGE row, which lands BEFORE the CREATURE_DIES row of the same diff — so the dies trigger's "exiled with it" IS_ATTACHED_TO_SOURCE filter read a table that had already forgotten the aura | `binding.detach(leaving=True)` snapshots the departing host's aura set into `executor.detach_lki[host]` **before** pruning; `quantity.IS_ATTACHED_TO_SOURCE` falls back to that LKI snapshot (CR 400.7) only once the judged host has LEFT the battlefield — live table governs while it stands |
| waker_of_waves_activation | Two independent blocks: (a) the CR 602.3 window gate refused ALL non-battlefield activations — but "Discard this card:" activations (cycling CR 702.29a family) are printed-legal from the hand; (b) `build_payment_plan`'s r19b CR 601.2h self-exclusion made the printed self-discard cost unsatisfiable, and `ability_playable`/`activate` couldn't even fetch the record of an un-attached hand card | `legality.py`: `_ability_discards_its_source` (IR-driven: CostDiscard + HAND zone + IS_SOURCE filter — never card-name); window exemption gated exactly on that shape; CostDiscard branch carves the exclusion back iff `_filter_is_self_referential(part.target.filter)` (the IR proof this is the printed self-cost, not Thrill-shape "discard a card" — 601.2h is a CAST-cost rule); `spell_record` = handle_record else oracle-`binder.records` fallback (a hand card is never ATTACHED), both lanes |
| speaker_of_the_heavens | LIFE_LEAD_OVER_START_GE unimplemented (12e flag). The finding's "corrupt printed_text / flip-enchant win-condition" addendum was a **card misidentification**: the local M21 row (#38 + #347 promo) matches Scryfall oracle text exactly ("…at least 7 life more than your starting life total…"); no data re-ingest needed | `quantity.py` branch: ledger read `world.players[p].life − executor.starting_life[p] ≥ N`, never a LIFE_GAINED journal sum (a non-damage CR 118.12 loss leaves NO row — events.py emits gains + damage-losses only, so a gains-sum OVERSTATES the lead); `Executor.starting_life` snapshot at construction (the frozen world takes `start_life` but never stores it); replay rebuilds the world at the same value (games.py:1017) → snapshot is replay-identical, kept OUT of the fingerprint, PC-4 stayed exact |
| ornery_dilophosaur | **STOP (compiler, B-family)**: compiled condition demands 4 creatures with P≥4; printed text says "**a** creature with power 4 or greater" — the "4" misread as the count. Golden amendment needs the 305-card set-equality audit + PC-4 re-pin → compiler-campaign scope | no engine change; pack stays in `tools/audit/suspects/` |
| creature_spell_nodes_systematic | **STOP (compiler)**: `compiler.py:1517-1524` grants a SpellAbility to creature cards only when `effect_outcomes` is non-empty — 2/149 creatures carry one; spy run: 0 creature casts in 10 games. Executor work can never move this | no engine change; note stays in `tools/audit/suspects/` |

## Promotions & pack edits

- 4 packs promoted: scenarios dir **200 → 204**. Convention as observed in-repo (23/23 promoted
  packs): `status`/`finding` are **retained as discovery-time history** — the runner ignores them;
  the 12-note's "stripped" wording described an earlier batch, the files are the authority.
- waker pack: ONE_OF cost-lane choice pinned with `"decisions": ["card:6"]` (decision words are
  literal engine handles, consumed in tree order — the loud raise names the vocabulary).
- speaker pack: `{"op":"life","seat":0,"set":27}` (new runner op — harness ledger write, the
  loyalty-op precedent) + expect `tokens.Angel:1` and `battlefield_keywords.Angel:[FLYING]`
  (the power/toughness lane keys by handle, not token name — that lane dropped).
- Probe rotation: `test_executor_legality.py::test_unsupported_condition_pred_raises` now probes
  `CONTROLLER_COUNT_GT` (R8-9 dual-filter, still unimplemented) with both filter slots — the
  previous probe pred became implemented this batch. `test_executor_r20b`'s player-subject probe
  unaffected (`_player_subject_verdict` has its own closed vocabulary, raises before `_eval_atom`).

## Engine unit tests (new)

`MTG_bot/core/test_executor_r20c.py` — **17 tests, all green**: hand-window 4 (self-discard legal,
activate pays+resolves, ordinary hand activation still refused, unregistered card loud), payment
self-lane 3 (self-ref pays source; generic discard still excludes cast spell + fails loudly alone),
role-lane 2 (binding can't hijack IS_SOURCE; plain CHOOSE stays binding-first), LKI 3 (snapshot
after leave, live table governs on battlefield, unrelated host false), life-lead 5 (snapshot, open,
one short, paid-down closes — the ledger-vs-journal pin, opponent-isolation).
Rig laws learned: `PUT_COUNTER`'s count role is spelled `count`; synthetic oracle ids must match
the scryfall-hex regex (`identity.py:35`); `activate(executor, …)` — no world arg; hand-card IR
arrives via `ex.binder.records[oid]` (never `attach_card`).

## Gate evidence (2026-10-01)

1. runner **204/204** (`tools/run_scenarios.py --dir tools/scenarios`)
2. suite **2213 passed + 3 subtests** (2196 + 17 new), 0 failures (`pytest MTG_bot/core -q`)
3. `measure_grammar --with-engine-flags` **exact**: PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0
4. `traces/catalog.py compare` **0/10 diverge — no repin** (the four fixes never fire on the 10
   trace seeds; detach_lki/starting_life are fingerprint-excluded derived state). `games --seeds
   100 --pool all` **0 crash classes** (endings: 83 caps, 17 game-overs)
5. `pyright` 6 errors == HEAD baseline 6 (pre-existing `Counter` annotations in run_scenarios.py
   423-546; new files clean); `ruff` **Δ0 vs HEAD worktree** (one self-introduced SIM102 fixed by
   the De Morgan single-if form)

## Standing traps added (→ PITFALLS.md)

- IS_ATTACHED_TO_SOURCE direction: the filter SUBJECT is the host, `ctx.source` is the aura.
- `atom.args.get(role)` pairs use printed role names (`count`, not `amount`, on PUT_COUNTER).
