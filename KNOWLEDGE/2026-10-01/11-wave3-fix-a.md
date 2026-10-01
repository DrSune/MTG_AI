# 11 — Wave-3 fix batch A (r20a): dead keywords given runtime teeth

HEAD 79dae99, engine editing **authorized** for this batch. Scope: the 10 promoted-but-suspect
wave-3 packs covering the five dead mechanisms — LIFELINK (anointed_chorister, blood_glutton,
indulging_patrician, light_of_promise), PROWESS (heartfire_immolator, jeskai_elder,
mistral_singer_prowess), BATTALION (makeshift_battalion), granted-trigger drain
(infernal_scarring), prevention damage consumer (pack_leader_prevention).
Outcome: **all 10 packs green and promoted; runner 196/196; suite 2182; every gate green.**

## Per-item verdicts (all were compile-but-never-drain / consumer-missing = silent bugs)

| Mechanism | Diagnosis | Fix site |
|---|---|---|
| LIFELINK | keyword layered on creatures but no runtime consumer — damage never healed | `verbs.py` `_lifelink_gain()` hooked into both `_deal_damage_to_card` and the player damage branch; life gain derived from *actual* dealt damage, so a vetoed hit grants nothing |
| PROWESS | trigger nodes bound but never drained on noncreature spells | `binding.py` keyword-holder drain loop via new `layers.holders()`; EoT expiry, off-battlefield skip, creatures silent — all per printed text |
| BATTALION | cast trigger fired per-spell instead of group-gated | `binding.py` `_group_size()` gate on the entering spell's controller's entering-creature group; group-of-3 gives one counter, alone gives none |
| Granted triggers | `GRANT_ABILITY`-granted dies-draw trigger never entered the trigger drain | `binding.py` granted-trigger drain — granted abilities now drain from the receiving object's stack |
| Prevention | `PREVENT_EFFECT` replaced the event but nothing consumed the prevention of card damage | `replacements.py` `prevented_card_damage()` consumed first in `_deal_damage_to_card`; `DAMAGE_PREVENTED` row lands in `ex.events` (Event ledger, **not** the diff-derived journal) |

Supporting: `binding.py` `_ctx` carries `event_amount` for `KIND_LIFE_GAINED`.

## Expectation fixes (5 packs were green-*on-the-silent-bug*; corrected to printed truth)

- **anointed_chorister**: life 21→**24** (lifelink 4 dmg from 20 → author's miscount).
- **blood_glutton / heartfire_immolator / indulging_patrician / light_of_promise /
  mistral_singer_prowess**: green immediately once the mechanism worked — no expectation change.
- **jeskai_elder**: toughness 3→**4** — printed Jeskai Elder is **1/2**; two prowess pings → 3/4.
- **makeshift_battalion**: life 14→**13** — printed **3/2**, battalion counter → 4/3; wave
  4+1+2 = 7 damage → 13.
- **pack_leader_prevention**: damage `{fence:2}`→**`{}`** — ledger law (CR 120.6,
  `executor/__init__.py:848`): marks leave with dead cards; Fence dies, so the empty ledger is
  the *correct* outcome. Leader survives via the veto.
- **infernal_scarring**: hand 2→**1** — rig baseline hand is 0; granted dies-draw fires once.

Each fixed pack carries a `"| r20a FIX (2026-10-01): …"` notes suffix; `status`/`finding`
fields stay as historical markers per repo convention.

## Engine unit tests (new)

`MTG_bot/core/test_executor_r20a.py` — **14 tests, all green**: Lifelink 4 (card lane, player
lane, plain-source negative, vetoed-no-gain), Prowess 4 (double ping, creature silent, EoT
expiry, off-battlefield skip), Battalion 2, GrantedTrigger 1, PreventionConsumer 3.

Rig laws re-confirmed: `target` Atom roles must be `Selector(...)`, never a bare `Zone`;
casts need an attached `CardRecord` carrying `SpellAbility(kind=…)`; `GRANT_ABILITY` demands
its `target` role at construction; `begin_turn` **draws** — open the test library *after* it;
runner `_combat(seat, attackers)` DECLINEs everything not listed.

## Gate evidence (2026-10-01)

1. runner **196/196** (`tools/run_scenarios.py`)
2. suite **2182 passed + 4 subtests** (`pytest MTG_bot/core -q`) — was 2168, +14 new
3. `tools/measure_grammar.py` PC rows **exact**: PC-1 301/305 (0.9869) · PC-2 634/639 (0.9922)
   · PC-3 0 · PC-4 0 diffs. FAILED targets PC-6/PC-8 unchanged pre-existing; PC-7 deferred.
4. `tools/traces/catalog.py compare` **10/10 seeds IDENTICAL, 0 diverging — no repin needed**
   (the new drains append to trigger lists only when the keywords actually match; the sim
   corpus never fires them, so byte-determinism held).
   `games --seeds 100 --pool all` → **0 crash classes**, 85/100 survived, mean 57.4 turns.
5. `pyright` **0 errors** on all five changed files; `ruff` **Δ0** vs HEAD (binding/layers/
   verbs/replacements + test file; one self-introduced I001 fixed via `--fix`).

## Standing traps added
- `DAMAGE_PREVENTED` rows live in `ex.events`, not `ex.journal.events` — assert against the
  right list.
- Head copies of engine files lint with project config only via
  `ruff check --stdin-filename <project path> -` — bare `/tmp` copies silently get default
  rules and hide I001-class findings.
