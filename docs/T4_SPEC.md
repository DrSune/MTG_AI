# T4 — Atomic-component ontology: P0 DESIGN SPEC (2026-10-07)

Owner laws binding this spec: AGENTS §8 (tokenizer law), §9 (axis orthogonality),
§10 (menu visibility — never blind, never phantom), §11 (board separation + zero loss).
Companions: `docs/T4_BLINDNESS_AUDIT.md`, `docs/T4_GAP_LEDGER.md`.
Status: **design only — no enum/code touched**. Gates: owner review (per /35) before P1.

Ground facts this spec is built on (all verified, sources cited):
`_VERB_ROLES` closed table (ability_tree.py:3305), 49 Verb / 6 SelectorMode / 17 events /
23 Keyword / 13 Quantity / 17 SITE_KINDS (bc_data.py), /30 algebra+census, /31 k-of-n precedent,
/32 event algebra, /33 catalog volumes, /34 adversarial audit, /36 T3 count_semantics.

---

## 1. Instance classes — OPERATION | EFFECT | POLICY (partition of 49 verbs)

Class = the atom's **payload role**, NOT where a decision happens: per §9 the {menu}/{count}
axes are a shared PICK wrapper, so selection never belongs to the verb. A verb therefore
partitions cleanly:

- **OPERATION (6)** — the atom IS a decision/observation operation:
  `CHOOSE, CHOOSE_NAME, SCRY, SEARCH, LOOK_AT, PAY`
- **POLICY (7)** — standing legality/timing/replacement constraints, no immediate state delta:
  `MANA_POLICY, DAMAGE_ASSIGN_POLICY, GRANT_ACTIVATION, PREVENT_EFFECT, ADD_LAND_PLAY,
  MANDATE_ATTACK, MANDATE_BLOCK`
- **EFFECT (36)** — the rest (state deltas):
  `DEAL_DAMAGE, DESTROY, EXILE, DRAW, MILL, GAIN_LIFE, LOSE_LIFE, ADD_MANA, CREATE_TOKEN,
  PUT_COUNTER, REMOVE_COUNTER, MODIFY_PT, SET_PT, GRANT_ABILITY, GRANT_TYPE, TAP, UNTAP,
  MOVE_ZONE, SHUFFLE, COUNTER_SPELL, COPY, SACRIFICE, DISCARD, REVEAL, ATTACH, GAIN_CONTROL,
  PHASE_IN, PHASE_OUT, EXTRA_TURN, END_TURN, LOSE_GAME, FLIP_COIN, CAST, FIGHT, LOSE_ABILITY,
  GET_EMBLEM`

Rulings embedded in this partition:
- `MANDATE_ATTACK/BLOCK` are POLICY (they constrain combat-declaration legality — "creatures
  can't attack" is the restricting card's component per §11; the restriction never touches the
  restricted creatures' encodings).
- `CAST`, `FLIP_COIN`, `FIGHT`, `TAP/UNTAP/SACRIFICE/DISCARD` are EFFECTs; their menus live in
  the shared PICK/designate wrapper (FIGHT stays a candidate to decompose into DAMAGE+PICK, /33 §3).
- Keywords (23) are a **fourth POLICY family** (modifier layer), not verbs — but MILL/SCRY/FIGHT
  exist as BOTH Verb and Keyword (double encoding, /33; merge row L-20 in the ledger).
- Selector modes: decision-owning = `TARGET, CHOOSE, ONE_OF`; no-decision resolvers =
  `ALL, REST, RANDOM` (a node resolved by a resolver MUST be encoded no-decision — §10 phantom law).

## 2. Canonical slots per atom

Source of truth = `_VERB_ROLES` (req | opt), extracted 2026-10-07:

| verb | req | opt | verb | req | opt |
|---|---|---|---|---|---|
| DEAL_DAMAGE | target,amount | dealer,recipient | PUT_COUNTER | target,counter_kind,count | — |
| DESTROY | target | — | REMOVE_COUNTER | target,counter_kind,count | — |
| EXILE | target | — | MODIFY_PT | target | power,toughness,duration |
| DRAW | controller,amount | — | SET_PT | target | power,toughness,duration |
| MILL | controller,amount | — | GRANT_ABILITY | target,ability | duration |
| GAIN_LIFE | controller,amount | — | GRANT_TYPE | target,types | duration |
| LOSE_LIFE | controller,amount | — | TAP | target | duration |
| ADD_MANA | controller,amount | color | UNTAP | target | duration |
| CREATE_TOKEN | tokens | count,controller | MOVE_ZONE | cards,destination | tapped_on_enter |
| CHOOSE | target | count,duration | SEARCH | cards,destination | controller,tapped_on_enter |
| SCRY | controller,count | — | SHUFFLE | zone | — |
| REVEAL | controller,count | duration | COUNTER_SPELL | target | unless |
| LOOK_AT | controller,count | — | COPY | source | — |
| SACRIFICE | target | — | DISCARD | controller,cards | — |
| ATTACH | equipment,target | — | GAIN_CONTROL | target,controller | duration |
| PREVENT_EFFECT | condition,event | controller,duration,step | PHASE_IN | cards,controller | — |
| PHASE_OUT | target | — | EXTRA_TURN | count | — |
| END_TURN | — | — | MANDATE_ATTACK | cards | controller,duration |
| MANDATE_BLOCK | cards | controller,duration | LOSE_GAME | — | — |
| FLIP_COIN | — | — | CHOOSE_NAME | — | name_filter |
| FIGHT | target | — | LOSE_ABILITY | target,ability | duration |
| GET_EMBLEM | — | — | ADD_LAND_PLAY | — | count,duration |
| MANA_POLICY | scope | filter | GRANT_ACTIVATION | filter | window |
| DAMAGE_ASSIGN_POLICY | scope | filter | | | |

Menu-visibility (§10) slot verdicts — slots the model must SEE that are missing/misplaced:
1. **SCRY** — no per-group order axis; executor pins Handle-ascending (verbs.py:1008-1018). BLIND.
2. **ADD_MANA** — `color` optional scalar; the mana ask fuses colour+amount, amount never
   askable (/30). Needs NUMBER menu `{range 0..n}` askable. BLIND.
3. **MANDATE_ATTACK / attack surface** — encoded as N binar attack asks, not a visible k-over
   attacker-set menu (/30). BLIND (set declaration invisible).
4. **CHOOSE_NAME** — names are UNBOUNDED vocabulary (any card name in the world). Tokenizer
   law §8: needs a name-encoding decision (spelling tokens vs id space); currently only 2
   consumers. OPEN (flag, no P0 decision).
5. **EXTRA_TURN** count present (Teferi −10 = `count=2`, verified byte-correct). CLEAN.
6. Up-to-{n} family: `QAtMost(n)` + NONE-stop is the right shape (Basri +1 clean, verified
   golden); the failures are MIS-ENCODES (`QConst(k)` for "up to", `QUnbounded` losing min —
   ledger rows), not slot-shape failures.

## 3. Menu-source taxonomy (§9: menu axis is orthogonal to operation)

`menu ::= FULL-LIST | ZONE+FILTER | DERIVED | NUMBER` — every one clamped by ACTUAL
availability at present time via the single `count_semantics` helper (/36; INFEASIBLE lane).

| source | definition | today's consumers |
|---|---|---|
| FULL-LIST | static enumerable options | node-Choose effect branches (27 g), may (42 g), cw/counter pass-branches |
| ZONE+FILTER | zone + filter descriptor, live legal set | TARGET designate (115 g/34 asks), ONE_OF search picks, DISCARD-from-hand, REST subtraction |
| DERIVED | menu computed from live state | scry top-N window, revealed hand (Duress), THAT_MANY_COUNT (Basri −2), Snoop's top-Goblin castable set, attacker set |
| NUMBER | bounded range, clamped | mana amount (FUSED today — violation), QAtMost search counts |

Violations to fix in P1: mana NUMBER fused into colour list; attacker set as binars;
scry window shown without its order axis.

## 4. Duration axis + per-choice-effect bundling

- Duration exists as first-class slots on 12 verbs (§2 table `duration` opt) with
  `DurationPermanent` / `DurationEot` values observed in goldens. T4 keeps the closed
  duration enum; new durations arrive via set integrations (§8), each with a census.
- Per-choice effects: node-Choose options each bundle a full Seq (Sublime 5 branches ✓,
  Gargaroth ✓). MISSING axis: PICK-with-entity-menu + per-item effect ("for each card
  discarded this way, draw a card") has no `fx_per_choice` slot anywhere — P1 adds it to the
  PICK wrapper, not to any verb.

## 5. Board-separation rule (§11 operationalized)

A card's record = ONLY its own components. Interaction-acquired restrictions never touch the
restricted card's encoding (defender check verified present on Gargaroth-style keyword
grants: restrictions are granted by the restricting source or by legality code, restricted
records untouched). `GRANT_ABILITY/LOSE_ABILITY` target = restricted objects but the effect
node lives in the granting card — compliant. Engine computes live legality; observation
menu presents true options at decision time. No change.

## 6. Zone-verb unification → MOVE{from,to}

Proposal: `MILL`, `EXILE`, `DISCARD` compile to one `MOVE` atom:
`MOVE {cards|count, from:Zone, to:Zone, chooser?, visibility}` + generic PICK wrapper.

| verb (vol /33) | migration | golden churn |
|---|---|---|
| MILL (3) | MOVE{from=LIBRARY/ctrl, to=GRAVEYARD/ctrl, count} | 3 |
| EXILE (19) | MOVE{from=src-zone, to=EXILE/owner} | 19 |
| DISCARD (17) | MOVE{from=HAND/ctrl, to=GRAVEYARD, visibility=hidden-source} + PICK menu (menu shape unchanged) | 17 |
| DESTROY (13) | **KEEP** — destroy ≠ move (replacement/regenerate interaction semantics differ) | 0 |
| PHASE_OUT/IN | **KEEP separate** — phase ≠ zone (treat-as-nonexistent state, CR 701; not a MOVE) | 0 |

Exact churn = **39 / 305 goldens** re-encoded static records. Ask bytes: DISCARD's ask is the
generic PICK over {HAND/ctrl}; if the rendered `zone:hand` menu tokens stay identical the
replay pins (want==1 frozen path, /31) are untouched. Executor: 3 handler families → 1 MOVE
handler + visibility flag.

## 7. One-grammar rule: static tree-render ≡ dynamic ask tokens

Shared alphabet, `{op, qty+live-bound, menu, fx}`; dynamic progress tags ride the /31 frozen
precedent (`one_of:<src>:i of k` — no new SITE_KINDS ever, bc_data.py:97-106 frozen-prefix law):

| atom shape | static render | ≡ dynamic ask |
|---|---|---|
| may | `whether{fx:…}` | `may:…` |
| pick k over menu | `pick{qty:2of?,menu:lib|SUPERTYPE=Basic&TYPE=Land,fx:move→BF tapped}` | `one_of:s:i of k` + menu tokens |
| modal branches | `choose_effect{k=1..5,opts:[op1..op5]}` | `choose:` + branch tokens |
| designate | `target{qty:n,menu:zone|filter}` | `target:…` |
| scry | `scry{qty:n,menu:top(n),order:ASK}` | `scry:` (+ new order sub-ask, P1) |
| mana | `amount{range:0..n}` | `mana:` amount lane (P1) |
| attack | `pick{qty:0..|A|,menu:attackers,fx:declare}` | `attack:` set form (P1) |

Blindness test (auditable per card): tokens(ask presented) ⊆ derivable-from(static render ∪
live clamp values); a node the engine resolves with a singleton/no-op menu must render as
no-decision (never phantom).

## 8. PT layer — explicit note

`SET_PT / MODIFY_PT / PUT_COUNTER` **stay** (volumes 4/50/28; PUT_COUNTER is the counter
substrate Malefic-Scythe-style derived PT already reads via `QBin`+`QProp COUNTER_COUNT`).
Verified defect (/36 addendum, pinned `test_current_pt_timestamp_behavior`): fold is
order-dependent — [+1/+1, SET_PT 3/3] = 3/3 but [SET_PT 3/3, +1/+1] = 4/4; CR 613 fixed-layer
oracle says 4/4 both. **OPEN DESIGN QUESTION — P0 does NOT decide.** Two candidate semantics:
(a) timestamps + CR 613 dependency-ordered continuous-effect layers (adds `timestamp`/`layer`
slots to PT verbs); (b) derived-value PT (effects stored as live expressions over base +
mutable sources — counters/attachment state — no timestamps, dependency edges only between
derivations reading mutable state). Malefic Scythe's `1×COUNTER_COUNT(source)` QBin shape
already leans (b) and works; (a) is the rules-lawyer-exact route. Owner/T4-layer-model gate.

## 9. P1/P2 blast radius (one-sentence verdicts)

- **P1 (grammar-visible)**: verb partition = card-encoder token churn of −3 verbs +1 MOVE
  (ask-channel vocab FROZEN, only intra-kind tags); golden regen = 39 static records (zone
  merge) + ask-shape change ≈ 12 scry + 13 attack-set + ~2 multi-pick-search cards (some
  overlap; ~60/305 worst case); replay pins safe on want==1 frozen bytes; packs: re-solve the
  subset of 373 containing affected cards (exact count = first T1 task); full retrain follows.
- **P2 (deferred, gated)**: E1 direction unification (7 event controller-fields vs
  CONTROLLER_IS filters), LifeGainedEvent amount slot, PlayLandEvent (0 M21 consumers —
  future-set exposure), Gargaroth event-union, PT timestamp decision (§8), saga/adventure/
  delve/proliferate atoms — each arrives through its own §8 set-integration re-evaluation.

## AMENDMENTS (adversarial review 2026-10-07; binding gates before any P1 code)
A1. SITE_KINDS blind-lane FIXED same day (/38): one_of+sacrifice added (16 asks had been
    site:?); precedent = /29 re-encode rule. Vocab now 19 kinds.
A2. MOVE merge PINNED prerequisites (must be spec-verified before implementing):
    (i) DISCARD result register feeding THAT_MANY_COUNT pairing (verbs.py:229,275-281);
    (ii) MILL journals literal "MILL" vs others "MOVE" (verbs.py:295 vs 98-103) — keep
    journal-kind param on merged MOVE; (iii) MILL top-of-library pop order differs from
    selector order — pin explicitly; (iv) EXILE binds role `target` not `cards`
    (verbs.py:219). Field-based event/replacement matching survives (events.py:479,
    binding.py:969) — with these four pinned, silent semantics drift is closed.
A3. Replay-safety claim REPLACED: DISCARD picks today emit 0 ask rows (silent) — PICK lift
    CHANGES their episode streams; P1 gate = enumerate per affected golden which ask rows
    exist pre/post; ONE_OF byte lane stays frozen; re-solve (never pin-claim) the rest.
A4. Churn wording: MOVE merge touches 39 VERB RECORDS in 36 unique golden files (5 overlap).
A5. Verb enum docstring "39 members" is stale (=49) — comment-only refresh (/38).
