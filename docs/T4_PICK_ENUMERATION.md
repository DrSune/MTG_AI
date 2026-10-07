# T4 — PICK enumeration & P1b ask-promotion pilot (2026-10-07)

Status: **stage 1 shipped** (enumeration + 8-card allowlist pilot). No mass migration.
Companion: `KNOWLEDGE/2026-10-07/40-p1b-enumeration-pilot.md`, doc 29 (ask grammar).

## 1. The census (measured, `tools`-external scripts over `golden/M21/*.json`)

155 SelectorMode-CHOOSE surfaces across 113 of the 305 M21 goldens
(note: the task brief estimated ~170; the earlier /30 pass said 157 — the
delta is `Feline Sovereign` / `Chandra's Incinerator`, which match the
string "CHOOSE" only through `Verb.CHOOSE`, not a CHOOSE-mode selector).

| class | count | verdict |
|---|---:|---|
| effect-choose, IS_SOURCE self-ref | 55 | **not blind picks** — CR 602.2c self-designations; must stay CHOOSE (see §4) |
| effect-choose non-self-ref, QConst(1), referent None | **22** | **LIFTABLE CORE** (21 pack-mentioned) — pilot allowlists 8 |
| effect-choose non-self-ref, QConst(1), referent=event/result/target | 37 | stays: anaphoric picks the 12a referent binding already serves (event 10 / result 18 / target 9) |
| effect-choose k>1 / unbounded | 31 | stays (incl. the 5 search-pick tails on the /31 lane — Cultivate-family; task law: k>1 not lifted) |
| cost-victim choose (additional/total costs) | 26 | stays: r22a already ASKS the sacrifice lane (`legality.py:1312-1351`); CostDiscard has NO lane — registered gap §5 |
| other (loyalty etc.) | 2 | n/a |

Liftable-core predicate: `mode CHOOSE ∧ count QConst(1) ∧ referent is None ∧
¬IS_SOURCE-in-filter ∧ ¬cost`.

## 2. The pilot (compiler `PICK_ASK_ALLOWLIST`, 8 rows, all (name, MOVE_ZONE))

Rain of Revelation, Rousing Read, Sanctum of Calm Waters, Jeskai Elder,
Teferi's Protege, Obsessive Stitcher, Experimental Overload, Crypt Lurker.

`_pick_ask_promotions` flips the FIRST candidate selector per (card, verb)
onto the EXISTING doc-29 ONE_OF asking channel (Handle-sorted population,
singleton auto-fill §1.4, exhaustion loud C15). Allowlist hit on a cost or
self-ref selector = loud `StateCorruptionError`, never a silent skip.

Runtime blast radius (honest — full 373-pack probe with the clean predicate):
exactly **5 packs** gain new asks (rain, rousing_read, sanctum, overload,
overload_x_garruk); the other 3 allowlist cards' surfaces are compile-pinned
but not exercised by their packs' current lanes. Zero silent behaviour
changes elsewhere. All 5 packs remediated with **falsifiable gold decisions**
(null-twin replay falsifies the pinned lane — the §10 discrimination law):
373/373 scenarios green, `no_discrimination=0` in puzzle_cert.

Eval-loop delta (HEAD worktree vs pilot, 200 rollouts/item):
items 157→**164**, punish_inaction 146→153, families 77→**80**, eval items
51→54, gold_lines 157→164, gold_rows_with_ground 79→**84**,
candidate_ground 229/474→**246/495**; fail_registered unchanged 11 (same
3 classes). New eval families: Experimental Overload, Rain of Revelation,
Rousing Read.

## 3. Deferred from the liftable core (gap ledger, NOT pilot scope)

- **Opponent-direction picks** (Goremand ETB reveal, Run Afoul, Liliana's
  Steward, Liliana Waker +1): the ask must go to the OTHER seat — the
  runner's decision channel is single-provider today.
- **Runed Halo**: card-NAME choice → no name-menu atom (§9 name axis gap).
- **Keral Keep Disciples**: "each opponent" encoded as CHOOSE(1) — encoding
  flag (should be per-object iteration, not a pick).
- **Furious Rise / Radha**: top-of-library POSITION semantics, not entity
  picks.
- **Idol of Endurance**: the pick feeds a cast-from-exile lane (no askable
  mana/routing lane yet).
- **Primal Might**: FIGHT atom resolves CHOOSE itself (`verbs.py:600`);
  needs a double-ask study before lifting.
- **Teferi's Tutelage**: surface reachable only when the pack's population
  grows past singleton — stage 2.
- **CostDiscard** (Thrill of Possibility): pays `plan.discard` with NO ask
  lane at all (vs CostSacrifice which asks) — the asymmetry is the gap.
- **Silent CHOOSE residue**: any candidate left CHOOSE resolves
  first-of-sort (the 12a stand-in) — acceptable only while un-allowlisted;
  each stage-2 widening must repeat §1's census against the new pool.

## 4. THE mode-gate pitfall (why self-ref never lifts)

`selectors.py:648` (r20c, Hobblefiend): the binding-time exemption that
keeps an activation COST's TARGET pick from hijacking a shared role name is
gated on `mode is SelectorMode.CHOOSE`. Flipping an IS_SOURCE-filtered
selector to ONE_OF **drops the exemption**, the cost-side pick hijacks the
role, and the effect silently resolves against the wrong population —
proven by control experiment (replace-only rebuild passes; flip fails).
Any future stage that wants ONE_OF self-ref must move that exemption to a
MODE-INVARIANT gate first, with its own pins.

## 5. Decision-channel mechanics discovered (runner ↔ engine)

`take_decision` lanes (`quantity.py:214`): (1) per-op raw pool — vocabulary-
validated, **pack keys NOT resolved** (needs `card:N` words); (2) DecisionStream;
(3) provider — resolves pack keys (18b). Both channels are primed from the
same step `decisions` list but consume INDEPENDENTLY: a word consumed by
lane-1 never pops from the provider queue. A may-offer matched by lane-1 is
invisible to `asks_seen` (cultivate precedent for raw-handle decision words).
Pilot packs use whichever lane the ask's op actually takes; discriminability
is verified by null-twin replay in every case, not by ask logs.
