# 2026-10-04/01 — BUGCATCH B1: BCS instrument + branch inventory shipped

**Scope**: tools-only batch per `KNOWLEDGE/2026-10-02/12-bugcatch-design.md` §A+§B.
Built `tools/audit/bcs.py` → artifact `tools/audit/bcs.json` (regenerate: `python3 tools/audit/bcs.py`).
No MTG_bot/** edits, no commits. Gates: suite **2345 passed + 3 subtests unchanged** (`.venv/bin/python -m pytest MTG_bot/core -q`), pyright **0 errors** on bcs.py, ruff **Δ0** (new file, 0 findings; shebang → chmod +x; `date.today()` → `datetime.now(UTC).date()` per tools/audit convention).

## The instrument
Per-card counts of 9 IR primitives over the **305-card golden corpus** (`MTG_bot/core/golden/M21/*.json`
+ `tools/audit/coverage.json`; the duplicate "Cat" name is keyed `Cat (2)`/handle `cat_2` — 304→305 fix):

| # | Primitive | Weight | What counts |
|---|---|---|---|
| 1 | atomic ops | 1 | verb leaves (Draw/SetPT/Damage… leaves) |
| 2 | branch slots | 3 | Conditional/Choose/OptionalEffect/EachPlayer/Repeat nodes + Selector mode ∈ {ONE_OF, REST} |
| 3 | role slots | 2 | CostTap/Sacrifice/Discard/Life/Loyalty/PutCounter |
| 4 | quantifiers | 6 | QX/QBin/QProp/QCount/QAtLeast/QAtMost/QThisTurn/QDistinctColorCount |
| 5 | token minting | 3 | CREATE_TOKEN leaves |
| 6 | replacement | 5 | ReplacementEffect nodes |
| 7 | layer verbs | 2 | SET_PT/MODIFY_PT/PUT/REMOVE_COUNTER/GRANT_ABILITY/GRANT_TYPE + **exotic-keyword payloads** |
| 8 | triggers | 4 | TriggeredAbility/DelayedTrigger |
| 9 | anaphora | 3 | IS_ANY_TARGET/TARGETS_SOURCE-class preds, THAT_MANY/THIS_WAY counts, referent ∈ {event,result} |

Weights = count of documented **silent-semantic** ledger bugs per class (fix docs 2026-10-01/11,12,13,18,19,23,24,25 + 2026-10-02/04–09); derivation table ships in `meta.weight_derivation`. BCS = Σ wᵢ·count.

## Corpus facts discovered (binding for B2–B5)
- `Repeat` is a real IR class (`ability_tree.py:2395`, serialiser row :3735) with **0 occurrences** in all 305 goldens.
- `IS_TARGET` does not exist; real preds: `IS_ANY_TARGET`, `TARGETS_SOURCE`, `IS_SOURCE`, `IS_ATTACHED_TO*`, `IS_EXILED_WITH_SOURCE`, `DIED_THIS_TURN`, `MOVED_TO_ZONE_THIS_TURN`. `TARGET_PLAYER` never appears in golden IR (runtime-synthesized, 24a) — proxied by TARGET selectors.
- **Exotic-keyword bug payloads (r20a) live in CardRecord top-level `keywords[]` as KeywordAbility nodes, NOT in `abilities[]`** — LIFELINK/PROWESS/BATTALION notations count into p7 via `KEYWORD_CONSUMER_BUGS`.
- Branch serialiser fields: Conditional = pred/then_effect/else_effect; Choose = count/options; OptionalEffect = inner; Repeat = count/inner; EachPlayer = ref/**effect** (not inner — an early signature bug). Anaphora `referent` fields can be dicts (ControllerRef) — isinstance-str guard required.
- Journal vocabulary for signatures: `MTG_bot/core/executor/events.py` KIND_* (CARD_DRAWN, CAST, COMBAT_DAMAGE, COUNTER_PLACED, CREATURE_DIES, DAMAGE, DECLARE_ATTACKERS, DECLARE_BLOCKERS, GAME_LOST, LIFE_GAINED, LOYALTY_ACTIVATED, TAP_STATE, TARGETING, TO_STATE, TURN_PHASE, ZONE_CHANGE). LOSE_LIFE maps to LIFE_GAINED (negative row — B3 to falsify).

## Calibration gate result (falsification, not curve-fit)
- **silent-semantic** class (27 cards): gate "≥2 non-zero among p4–p9" → **19/27 pass**.
  8 exceptions, each risk-prims=1, all classified as per-card-score **blind spots** (matches design §C prediction — score is blind to cross-card/cross-branch collision classes; weights NOT adjusted):
  - branch_entanglement: Destructive Tampering (15), Fabled Passage (16) — bug is in branch machinery + §C union.
  - keyword×consumer: Makeshift Battalion (2), Mistral Singer (2) — single notation, consumer missing in engine.
  - replacement×ordering: Teferi's Ageless Insight (6), Caged Zombie (6) — needs second card / journal-order law.
  - single-fold: Basri's Solidarity (3), Secure the Scene (13) — one missing fold rule (engine layers/binder).
- **machinery-rooted** excluded by class (3): Tormod's Crypt, Epitaph Golem, Chandra's Magmutt (generic role_handles/_v_move_zone bugs, not card-shape-shaped).
- **crash-class-only** excluded (10; `meta.calibration.crash_only`).
- **vanilla-identity** (14 cards): all-zero residual **14/14** pass. Ledger corrections: the "Teferi's draw" bug is Teferi's **Ageless Insight** (22b), not Master of Time; Wishcoin Crab is not a ledger card; Goblin Wizard is keyword-class (PROWESS notation), not vanilla.

## Outputs
- **BCS**: mean 14.1, max **70** (Basri Ket); buckets 0:24, 1–9:89, 10–29:161, 30+:31.
  Top-10: Basri Ket 70, Garruk Unleashed 54, Siege Striker 53, Malefic Scythe 49, Liliana Waker of the Dead 48, Conclave Mentor 46, Gadrak the Crown-Scourge 46, Basri Devoted Paladin 45, Wildwood Scourge 44, Alpine Houndmaster 41.
- **Branch inventory**: **97 declared branches** on 74 cards (Conditional 16, Choose 27, OptionalEffect 41, EachPlayer 5, Selector ONE_OF/REST 8), each with ID + falsifiable discriminating signature (journal_kind × data_predicate). `lit_so_far` **deferred to B3** (pack-journal match over tools/scenarios + 100-seed catalog).
- Heat table + exception table + `blind_spot_classes` all in `tools/audit/bcs.json` meta.
