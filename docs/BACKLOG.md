# Backlog

Everything parked, with the reason it is parked. Two rules for this file.

1. **When an idea does not move the ladder in [`NORTH_STAR.md`](../NORTH_STAR.md), it lands
   here rather than being built.** Say so out loud when you park something.
2. **Every hard limit, cap, or schedule added anywhere in the codebase gets an entry under
   "Scaffolds to remove", with the condition that would let it go.** Never add one silently.

Sections: scaffolds to remove; open engine faults; card onboarding and gates; training and
measurement; parked ideas, questions and doc corrections. An entry leaves this file in the commit
that closes it; git history and `KNOWLEDGE/` keep the record.

---

## Scaffolds to remove

Things currently hardcoded that the learnability principle says should not be. None of these
are neutral; each one is teaching the agent something.

| Scaffold | Where | Removal condition |
|---|---|---|
| **Drafted decks stay inside the critic's band** (2026-11-12, docs/PLAN_DRAFTER.md §5): a critic swap that would take a deck's mean spell mana value, creature count or most copies of one card outside the coherent decks' 1st-99th percentile is skipped | `tools/selfplay/decks.py` `band_of`, `drafted_decks` | It guards the critic's range, not a rule of the game: the critic is fitted on coherent decks, so outside their range its values are extrapolation. Remove it when the critic is fitted on drafted decks' games too (PLAN_DRAFTER §6's loop) and G2's calibration holds outside the band |
| **Coherent-deck recipe (B-45)**: 2 seeded colours, 24 basics, 36 cards uniform within the colour pair | `core/executor/games.py` `build_coherent_deck` / `COHERENT_LANDS` (branch `sets/onboarding` 36adf48) | It chooses colours and land count, never which spells. Remove when decks come from a learned deckbuilder (draft/sealed or constructed), or replace the land count with a learned or sampled quantity. Opt-in only; the default stays the stress pile. |
| **Trigger quarantine after `MAX_TRIGGER_FIRES = 200`** (registered 2026-10-24) | `core/executor/binding.py:31-34,147,1458` | A rules deviation: the runaway source's trigger is switched off for the rest of the game, so combos silently die. Replace with the loop shortcut and CR 104.4b handling in [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md). |
| **`TURN_CAP = 60`** (registered 2026-10-24) | `core/executor/games.py:138,1554`; `tools/selfplay/learner.py` `reward` (`--draw-reward`) | A non-rules safety rail. Scored as a draw (0 > loss = -1) it would pay a losing policy to stall (D10), so self-play scores it `--draw-reward` (default -1, a loss for both seats) and reports it as `draw-cap`. Remove once a real match clock exists. Owner, 2026-11-11: "I think the rails are good for now, we can raise them once they are only hit in genuinly close games, not just unintelligent ones." To tell, count the hits per game and read the games that hit them (not counted yet). |
| **Stall rule = draw after 3 identical rounds** (registered 2026-10-24) | `core/executor/games.py:159,1499-1511` | Same incentive problem as the cap; self-play scores it like the cap (`draw-stall`). Keep it as a progress probe until optional-loop actions exist. |
| **10 actions per player per step** (registered 2026-10-24 as "10 acts per main phase, one main phase per turn"; 10 in each main phase from 2026-11-06, B-74; per player and step since 2026-11-11, when the loop gave priority in every step, DESIGN_PRIORITY §2.6) | `core/executor/games.py` `MAX_ACTS_PER_STEP` (`_play_turns`; `Executor.acted` counts); the pack runner's `act` op | A rail, not a rule: CR 117 sets no limit on how often a player who keeps priority acts. It makes a player who never passes pass after its tenth action in a step (a free ability activated forever), recorded as any pass is. Priority did not remove it. Remove when the loop shortcut and the optional-loop action exist ([`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md), CR 104.4b) or a real match clock makes never passing lose. Owner, 2026-11-11: "I think the rails are good for now, we can raise them once they are only hit in genuinly close games, not just unintelligent ones." To tell, count the hits per game and read the games that hit them (not counted yet). |
| **Automatic payment: the pool first, then the mana sources the engine picks** (2026-10-29, B-90 option (a); the act window too since 2026-11-05; costly sources since 2026-11-11) | `core/executor/legality.py` `plan_mana_taps` / `tap_for_payment`; callers `core/executor/menu.py` (`cast_taps`, `activation_taps`: the menu every player acts from), `verbs._v_pay` with `query.optional_offer`, the `unless` lane of `verbs._v_counter_spell` | CR 601.2g / 605.3a let the payer activate mana abilities while paying. A free source is a non-creature permanent whose mana ability costs only {T} (lands, plain mana rocks). A cast, activation or payment is offered when the pool plus the untapped free sources pay it, and the engine taps an inclusion-minimal set by one rule: for each shortfall (coloured symbols first), the source whose loss leaves the most colours the other free sources make, then the one making the fewest colours, then the lowest Handle (colourless is not a colour, so a colourless source pays a generic shortfall first, and the pool pays generic costs with colourless mana first: 2026-11-06; the rule ignores a source's other abilities, so a colourless utility land such as Animal Sanctuary or Cryptic Caves spends its own {T} ability paying a {1}); a coloured choice that leads nowhere tries the next source, so a payment is found whenever one exists ({R}{W} from an R/W and a B/R dual). Since 2026-11-11 (DESIGN_PRIORITY §2.7, §11 step 4) mana abilities are no menu rows: a cast or activation from the menu is also paid, where the free sources fall short, by a creature's {T} mana ability, then by one that sacrifices its own permanent (Treasure), by the same rule within each tier (`legality._source_tier`), never sacrificing a permanent the spell or ability targets (its targets are chosen before the costs are paid, CR 601.2c, 601.2h, so the spell would lose them; tapping one is allowed; packs `treasure_*`, 2026-11-11). Never paid for the player: a mana-cost filter (Prismite, Three Tree Mascot) and a sacrifice of another permanent (Kykar's Spirit); a payment inside a resolution uses free sources only. Given up with the rows: a mana ability activated for its side effect (a Treasure sacrificed in response to its removal, CR 605.3a), and the filters entirely. The design asked the payer which costly source pays when there is more than one way; the engine picks instead, because the free sources are already its pick and a payment choice for the costly ones alone would be replaced by the learned one. The engine chooses the payment sources, a decision hidden from the player (AGENTS §10). Remove with a learned payment choice: the PAYMENT asks of DESIGN_ACTION_SPACE §1.3. |
| **Pack `mana` op** (2026-10-29, V2) | `tools/run_scenarios.py` | Mana empties as each step and phase ends (CR 500.5), so a pack that pays in a later step adds the mana at that step, standing in for the lands the player taps there. Since 2026-11-11 a cast step may instead tap real lands with `"tap": true` (the menu's automatic payment, the row above); the op stays as the short form. Remove when payment folds into the move (DESIGN_ACTION_SPACE §1.3). |
| **Observation caps: 64 options per ask, 112 card entities (graveyard and exile keep their newest 16 and 10), 128 IR tokens per card** (registered 2026-10-24 for the deleted PointerBC observation, which truncated 15,407 of 17,270 asks; these are the self-play network's) | `tools/selfplay/features.py` `MAX_OPTIONS`, `MAX_CARDS`, `GRAVE_KEEP`, `EXILE_KEEP`, `CardTable.max_ir`; `tools/selfplay/actor.py` `decide` | A larger ask, and every `name` ask, is answered by the fallback agent and never trained on (counted as `overflow` in the metrics). Capacity limits, not strategy limits. Remove or resize them with a measured context budget. |
| **Benchmark: 3 strikes per decision, then the do-nothing choice** (2026-10-24) | `MTG_bot/bench/llm.py` | Bounds a non-answering model. Remove when tool mode gives structured answers; until then forfeits are always reported. |
| **Benchmark: stateless prompts, conservative hidden-card labels** (2026-10-24; `TAP_ALL_MANA` and "X always 0" removed 2026-11-05: payment is the row above, X is one menu row per payable value; multi-slot rows hidden until 2026-11-06, now one target question per slot; one act window per main phase until 2026-11-11, now a decision at every priority point) | `MTG_bot/bench/router.py`, `protocol.py`, `llm.py` | Each is a harness simplification. Remove with tool mode (`notes` memory). An LLM seat now pays one call per priority point it can act at, so its clock is measured (DESIGN_PRIORITY §3.6). |
| **Decision-time search budget: k candidates (3-4), d sampled worlds (2), at most 6 attack or block plans, search skipped where the network's top option >= skip_p, 400 decisions per simulation, leaf = the next own turn's value** (2026-11-03/04) | `tools/selfplay/search.py` (`Searcher`, `plan_attacks`, `plan_blocks`, `MAX_SIM_DECISIONS`) | Compute budgets, not strategy rules, but they decide which moves can ever be found (a move outside the network's top k is never searched). Replace with a budgeted tree search whose breadth follows the visit statistics (PUCT/MCTS) once the engine is fast enough; measure the plan caps by raising them. |
| **True-future label budget: a decision is labelled when the network's top option is below 0.95 (`UNSURE_P`), or for 10% of the confident ones (`CONFIDENT_SHARE`); at most 4 labels per game (`LABELS_PER_GAME`, drawn uniformly from the eligible decisions); k alternatives and d futures per label (E1: k 2 or 4, d 2); playouts to the game's end with the search's 400-decision rail** (2026-11-06, PLAN_LEARNING §13) | `tools/selfplay/search.py` (`Labeller`, the constants above it) | Compute budgets that decide which decisions are ever labelled and how finely. Set by E1's measured signal per forward pass; remove when labels are budgeted by measured value (the label's gradient contribution per forward pass, or the policy's own uncertainty with no fixed cut) and the label window decides how many a game gives. |
| **The label target's step: eta = 0.5 / se (`LOGODDS_PER_SE`: a one-standard-error error moves the log-odds by at most 0.5) and the magnet weight alpha (0 by default)** (2026-11-06, PLAN_LEARNING §1.1, §13) | `tools/selfplay/search.py` `mmd_target` | A step size and a regulariser chosen by hand. The owner's 45/30/25 example converges on the shared answer only in the target's linear regime (eta of about 0.05 per outcome unit there; KNOWLEDGE/2026-11-06/186). Remove when the distillation loss sets the step from measured label noise and B*_distill, with the magnet's anneal measured (Phase 1). |
| **Self-play gate: freeze when a gate match vs the newest frozen version scores `--gate-score` with its 95% lower bound above 0.5; the teacher stage ends at `--teacher-gate` or after `--teacher-iters` updates** (2026-11-04) | `tools/selfplay/learner.py` `_eval_tick` (`--gate-score`, `--gate-deals`, `--teacher-gate`, `--teacher-iters`) | Hand-set curriculum schedule. Replace with a league whose opponent sampling follows measured win rates (prioritised fictitious self-play) so no freeze threshold is needed. |
| **PPO throttle: no new training games while a full next batch (`--steps`) is waiting** (2026-11-04) | `tools/selfplay/learner.py` `next_job` | Flow control so batches stay on-policy when workers outrun the trainer; it idles workers. Remove when the trainer keeps up (faster update) or when idle capacity is given other work (value games, evals). |
| **The heuristic's mulligan rule** (2026-11-06, with the London mulligan) | `tools/selfplay/heuristic.py` `_mulligan`, `_mulligan_bottom` | An authored keep policy, not a rule of the game, in the anchor opponent and the BC teacher: keep a hand of five cards or fewer, or a bigger one with at least two lands and at least two other cards; the card a mulligan puts on the bottom is a land while lands outnumber the rest (a copy of the land held most), else the highest mana value card. The network learns its own mulligan by PPO and imitates this one only in teacher inter-play. Remove it with the heuristic as anchor and teacher: a league of frozen versions as the fixed opponents, and runs that start from a trained network. |
| **Simulator data: each capture seat records a share 0.4 of its decisions; capture games are half network against itself, half against the heuristic; games whose seed is a multiple of 25 are held out** (2026-11-06, E0) | `tools/selfplay/learner.py` `capture` (`--capture-p`); `tools/selfplay/simulator.py` `HOLDOUT` | Collection knobs of E0's offline data. Remove when the simulator retrains on a sliding window of the league's own recent games (PLAN_LEARNING §4), held-out games drawn there. |
| **Entropy bonus in outcome PPO: 0.004 in r27, 0.0075 in r26** (2026-11-10, r26; r20-r23 ran 0.002; r27 since 2026-11-12) | `tools/selfplay/ppo.py` `ppo_train` (`--ent`); the unit text in `KNOWLEDGE/2026-11-10/189` §9 and the command in `KNOWLEDGE/2026-11-11/191` §2 | The one term in the loss that is not winning, sized by hand. Without it this learner lowers its own entropy by about 0.003 per update at lr 2e-5 (r25), and 0.002 does nothing against that (one update measured term by term, 189 §8). 0.0075 was the size whose measured push balances the fall; it overshot, and r26's entropy rose to 0.43-0.45 (189 §10-11). At r27's 0.004 an action costing 0.3 points of win probability keeps about 15% of the best action's weight (191 §2). It is one level for every kind of decision: r27's mulligan, the binary choice with the noisiest gradient, may carry what r26's bonus put there (191 §7). Remove when exploration no longer hangs on sampling noise: targets from search (PLAN_LEARNING Phase 2), or a learner whose entropy holds without it. |
| **One fixed `TEST_MASTER_SEED` for the test suite** (2026-09-11) | `MTG_bot/conftest.py:24` | It is the right default now, but a conformance suite should eventually run over k seeds and assert the result is seed-independent, which is what P13's seed band is for. Once P13 exists, replace the constant with a parametrised seed sweep. |

---

## Open engine faults
- **Possible rules faults found by the 2026-11-06 engine lean pass** (not changed; none known to be
  live in two-player verified play):
  - a target-player slot with no legal player still resolves instead of the ability being removed
    (CR 603.3d);
  - `CONTROLLER_COUNT_GT` sums all opponents at three or more seats;
  - party size can count one multi-class creature several times;
  - `templates_b6` emits `Verb.DISCARD`, which has no handler.
- **Compiler faults found by the 2026-11-06 lean pass** (none live in the M21, M20 or FDN verified
  pools: every verified card that places counters places the printed kind, and the verified
  "as long as" statics carry their condition as a while-duration):
  - the b5b put-counter template always places +1/+1 counters, whatever kind the card prints;
  - the b4 keyword-grant template raises KeyError on a keyword it does not map (loud, refuses the card);
  - rebuilding a static ability during kicker or continuation merges drops the ability's condition;
  - search scores a drawn playout as -1.0 regardless of --draw-reward (matches today's default).
- **The search's determinisation deals the opponent impossible hands** (red team of the learning
  plan, 2026-11-06): `search.py` (~72-79) re-draws the opponent's hidden cards from the whole
  five-colour pool, while training deals two-colour coherent decks. Measured on 12 deals: the
  sampled opponent holds 6-10% lands (true 37-40%) and 54-61% off-colour spells (true 0%); over 32
  positions the searching seat's playout value rises from +0.14 to +0.68 and the sign of "develop vs
  pass" flips on 6 of 14 clear positions. Every eval+search number so far was measured against
  crippled imagined opponents. Fix (~30 lines): sample hidden cards the way the deck generator builds
  decks (prototype matches the true-cards control, +0.15 vs +0.14). Prerequisite of DECISIONS D20.

Each reproduction is a scenario pack in `tools/scenarios/known_bugs/`. It holds the outcome the
printed text demands, so it FAILS today and passes once the bug is fixed; then it moves to
`tools/scenarios/`, or is deleted when a regression test already covers it. Run them with
`tools/run_scenarios.py --dir tools/scenarios/known_bugs`; they are outside the default sweep. The
M20 mappers' repros, run against their draft trees, are in `tools/scenarios/known_bugs/2026-11-05/`
(its README lists them and says how to run each).

### Combat

- **B-102 [fixer A, found 2026-10-30; B-84 until the integration merge] Attack triggers can see a creature put onto the battlefield
  attacking** (latent: no M21 card misfires today).
  - `Executor.join_attack` (`executor/__init__.py` ~1915) journals the same DECLARE_ATTACKERS
    row, in the same declare group, as a declared attacker, and `binding._match_node` (~919)
    matches every such row. CR 508.3a and 508.4: a creature put onto the battlefield attacking
    never "attacked", so no "whenever ... attacks" trigger may see it. Falconer Adept's Bird
    (80a895f) and Basri Ket's -2 Soldiers take this path.
  - Hidden today by two accidents. The joined row is journalled before the token's own
    ZONE_CHANGE row, so at match time the token's keywords are not yet in the layer map (a
    flying filter misses the Bird). And the per-declaration dedup (`binding._queue` ~728, one
    instance per ability per declare group) has already queued any trigger the declared
    creature matched. Probes 2026-10-30 (Tide Skimmer + Falconer Adept, and a per-creature
    flying filter with only the Adept declared): no extra trigger. A filter on type, subtype,
    token-ness or controller that the token matches and no declared creature does would fire.
  - Coupling: that dedup is itself wrong for per-creature triggers (B-103). Whoever fixes B-103
    must exclude joined rows in the same change, or the Bird and the Soldiers start
    triggering. `_group_size` (battalion) and the `declare_attackers` register
    (THAT_MANY_COUNT) count joined rows as well.
  - Fix: mark the joined row (its own payload, or an `entered_attacking` set folded into the
    replay hash) and skip it in the DeclareAttackersEvent match, the group size and the
    register. Engine lane.
  - **History inherits B-102**: `EVENT_THIS_TURN` over `DeclareAttackersEvent` reads the journal
    through `binding._match_node`, so a creature put onto the battlefield attacking (joined row,
    CR 508.4) counts as an attack. "You attacked this turn" is unaffected (such a creature only
    enters during a declared attack); "attacked with N or more creatures" would be. The B-102 fix in
    `_match_node` fixes both lanes.
- **B-103 [fixer A, found 2026-10-30; B-85 until the integration merge] "Whenever a creature ... attacks" fires once per
  declaration, not once per attacker** (live in M21, weaker than printed).
  - `binding._queue` (~728) queues one instance per ability per declare group for every
    DeclareAttackersEvent. That is right for "one or more" and "attack with two or more"
    (Basri Ket's -2, Tide Skimmer, Mangara) and wrong for a per-creature trigger, which
    CR 603.2c fires once per matching attacker. Repro, failing today:
    `tools/scenarios/known_bugs/hooded_blightfang_each_deathtouch_attacker.json` (two
    Blightfangs attack: four triggers are due, two fire, so the life totals end 22/16, not
    24/14).
  - Live in M21: Basri, Devoted Paladin's -1 puts its counter on one attacker per declaration,
    and Hooded Blightfang drains once however many deathtouch creatures attack. Across the 19
    sets these two, Basri Ket, Tide Skimmer and Mangara are the only compiled attack triggers
    not keyed on IS_SOURCE (snapshot 2026-10-30).
  - Design decision, an IR change: `DeclareAttackersEvent` cannot tell "a creature attacks"
    from "one or more creatures attack" (Basri Ket's -2 and the Paladin's -1 differ only in
    their filters). (a) A `batch: bool = False` field, omitted when False so per-creature trees
    stay byte-identical, set by the compiler on "one or more", "attack with N or more" and
    "you attack"; the dedup then applies to batch triggers only. Three goldens re-bake (Basri
    Ket, Tide Skimmer, Mangara). Recommended. (b) Infer batching in the engine from a
    CONTROLLER_COUNT_GE condition: no schema change, but it cannot separate Basri Ket's -2
    from the Paladin's -1, so it is not enough. Either way it lands with B-102's exclusion.
  - **Also filed as B-106** (vfix2, V14, 2026-10-29; numbered B-81 in a6c7740; gated as R5-14),
    which records the rule and the gate's options:
    - `DeclareAttackersEvent` is (filter, attacked). The same bytes carry "Whenever you attack" / "one
      or more creatures you control attack" (CR 508.3d: once per declaration; MAPPER_GUIDE prescribes
      it, `binding._queue` dedups by (source, node, declare_group)) and "Whenever a creature you control
      [with deathtouch] attacks" (CR 508.3a with 603.2c: once for EACH such attacker, the event subject
      being that attacker). M21 Hooded Blightfang drains once; Basri, Devoted Paladin's −1 grant
      ("Whenever a creature attacks this turn, put a +1/+1 counter on it") counters only the first
      attacker.
    - Options sent to the gate: (1) an optional field (absent = once per event, so existing trees stay
      byte-identical) that the per-object templates set, the binder skipping the dedup for it and
      binding the subject per row; (2) flip the default to per object and mark "one or more"; (3)
      encode "one or more" as a QAtLeast condition. The coordinator recommends a GENERAL form of (1):
      once-per-event vs once-per-object is one trigger axis (dies, enters, damage too), so an
      attack-only field would become a second encoding of it (AGENTS §9).
    - Damage today (2026-11-06, `binding._queue`): a `DamageDealtEvent` with no `source` filter ("is
      dealt damage") fires once per recipient per combat damage step (CR 510.2); one with a `source`
      filter fires per DAMAGE row (per dealer and recipient). That is right for "a source you control
      deals ... to an opponent" and "deals combat damage to a player", wrong for "one or more ...
      deal" (Feline Sovereign, not verified) and for a dealer trigger with no recipient ("whenever
      this creature deals damage") split by trample or several blockers (none compiled). The general
      field would replace that reading.
  - **Leeching Sliver plays weaker than printed until B-103** ("whenever a Sliver you control attacks"
    fires once per declaration, not once per attacking Sliver, CR 603.2c). Its tree is right; repro
    `tools/scenarios/known_bugs/leeching_sliver_each_attacking_sliver.json` (fails today, as Hooded
    Blightfang's does). B-102 applies too: a Sliver put onto the battlefield attacking would trigger it.

### Casting, the stack and targets

- **The CAST atom has no target channel.** `verbs._v_cast` (verbs.py:1872) calls `stack.cast_card`
  without targets, because the CAST role table has only `source` and `cost`. `cast_card` then
  validates the empty designation (stack.py:1546) and raises `ValueError: executor: cast: illegal
  target selection: selection:count_below_min:0<1` for any spell with a required target, whose
  caster should choose it as the spell is cast (CR 601.2c).
  - Reached through Chandra, Flame's Catalyst's -2 ("You may cast target red instant or sorcery
    card from your graveyard"). Latent in training: Chandra herself is engine-unsupported, so no
    verified, compiled or castable M21 pool deals her (B-99). Ten verified red spells it can target
    raise when cast this way: Destructive Tampering, Scorching Dragonfire, Shock, Soul Sear, Sure
    Strike, Traitorous Greed, Turn to Slag, Unleash Fury, Volcanic Geyser, Volcanic Salvo. The
    may-offer
    still offers "fire" (`query.cast_designee_ok`, query.py:844, checks the card and its payment,
    not its targets), so a game that gets there is voided (`tools/selfplay/rig.py:161`). Conspicuous
    Snoop (Goblin spells) and the Mystic Forge draft (artifact and colorless spells) reach no
    targeted spell in the M21 or M20 verified pools; a Goblin kindred instant or a colorless removal
    spell would raise the same way.
  - Repro: `tools/scenarios/known_bugs/chandra_catalyst_recasts_a_targeted_spell.json`.
  - Not small, and owned by the ontology round: it is the "target and X channel on effect casts"
    that gate round 3 requires of R5-2 (DESIGN_ATOM_ONTOLOGY §9). The fix needs: an ask of the
    caster for each target as the spell is cast (a `target:` ask like the trigger lane's,
    `binding._designate`), with several slots threaded as `cast` threads them
    (`slot_designations`); "fire" and the activation target offered only for a card whose targets
    can be chosen (`query.cast_designee_ok`); a target's cost increase priced (`cast_card` builds
    its plan before any target exists, stack.py:1556, where `cast` re-prices, stack.py:1220, V29);
    and the targets checked again on resolution (CR 608.2b; both lanes do since 2026-11-10,
    `stack.resolve_top`). Each changes what the network is asked.
  - The X half: `_v_cast` passes X = 0 unless the ability announced an X, so Chandra's -2, which
    pays the spell's mana cost, recasts Volcanic Geyser with X = 0 (the caster chooses X, CR
    601.2b; 107.3b makes X = 0 only when no mana cost is paid, as for Idol of Endurance).
- **B-99 [fixer 3, 2026-10-29; renumbered from B-75 (phasing took it) and then B-97 (R5-1 took it) at the integration merges] Chandra, Flame's Catalyst's "If that spell would be put into your
  graveyard, exile it instead" is not applied.** Her -2 casts a red instant or sorcery from your
  graveyard through `stack.cast_card`; the rider's replacement (`B5b-repl-graveyard-exile`) is never
  registered for that cast, so the spell resolves into the graveyard and can be recast. Stronger than
  printed, but Chandra, Flame's Catalyst is not castable yet, so nothing exploits it today. Repro:
  `tools/scenarios/chandra_catalyst_recast_draw_journalled_once.json` (its note says where the card
  should land: exile; it lands in the graveyard). Owner of the fix: the ontology round, which is
  redesigning replacements created at resolution (DESIGN_ATOM_ONTOLOGY §10).
- **The bench labels a multi-mode `choose` token "choice N"** (`bench/protocol.py` maps tokens to
  bullets only when every option set is one mode); it is representable but not described.
- **Target recheck gap (not reachable in current games)**: Enthralling Hold's "as you cast it"
  restriction is re-read at resolution, so it fizzles if its target untaps.
- **An ability whose source left and came back still acts on the source** (CR 400.7, found
  2026-11-11). Targets are rechecked against zone changes since they were chosen
  (`stack.recheck_targets`, `returns.moved_since`), but an ability's own source is not: "this
  creature gets +1/+1" activated, then the creature exiled and returned in response, pumps the new
  creature. The new object should be untouched, while information about the source (its power for
  "deals damage equal to its power") comes from its last known information (CR 608.2h), which
  `departed_lki` drops on re-entry (`__init__.py`). Not reachable without a flicker effect in the
  dealt pools.
- **B-54 [2026-10-29, first mapping batch] `legal_casts` offers a spell whose required target has
  no legal candidate** (CR 601.2c), and casting it raises. The bench router hides such rows; the
  probe now skips them.
- **Two "target" words with the same text share one target slot** (found 2026-11-06): the slot
  query keys a slot by its selector (`query.spell_target_slots` dedupes by repr, which is how the
  compiled anaphora of "target creature ... its power" stays one target), so "Target creature gets
  +1/+1. Target creature gets -1/-1" would be one slot and could not take two creatures (CR 601.2c,
  115.3). Latent: no card in the M21, M20 or FDN verified pools has two such words. Needs the
  compiler to tell a second target word from a reference back (a slot id on the selector).
- **The folded `activate` takes its targets before it asks X** (2026-10-29, the activation X
  lane), so X is announced after the designation (CR 601.2b orders X before 601.2c targets). No
  carrier has both: Ugin's [−X] has no target.

### Triggers, events and the journal

- **Yarok, the Desecrated and Sanctum of All make their extra trigger with a trigger of their own
  (2026-11-11).** CR 603.2d: the ability triggers that many times at once, so the copies go on
  the stack with everything else that triggered (CR 603.3b). The engine instead queues a trigger
  of the carrier (`compiler/templates_b5b.py:2482-2501`, fed by `binding._fan_ability_triggers`),
  which goes on the stack as an object of its own; the extra copy is queued only when that
  resolves (`Verb.TRIGGER_ADDITIONAL`). Since priority, players get priority between the
  original and the extra copy, and the trigger-order ask offers the carrier's trigger as an
  option (`test_executor_t5d.py`). Life totals agree in the packs. Fix: count the copies when
  the ability triggers and queue them with the original, with no carrier trigger.

- **B-92 [vfix V8, 2026-10-29; updated at the d955f67 merge, 2026-10-30] A fight's two DAMAGE
  journal rows both name the fight's source as the cause** (CR 701.12b: each creature deals damage
  equal to its power to the other). Since V44 `verbs._v_fight` applies each blow with the fighting
  creature as `ctx.source`, so protection, deathtouch, lifelink and source-keyed replacements read
  the creature; the journal does not.
  - Still open: the journal's one-cause-per-atom diff (`Journal.record_atom`, called by the
    executor's Atom lane with the atom's cause) names the fight's source as the dealer of both
    rows, so a damage trigger with a dealer filter (`binding._match_damage` reads `event.cause`
    for `DamageDealtEvent.source`) sees the wrong dealer.
  - Latent in M21 (census 2026-10-30): the four dealer-filtered damage nodes are Hooded
    Blightfang, Chandra's Incinerator, Chandra's Pyreling and Fiery Emancipation. The first three
    read damage to players or planeswalkers, which a fight never deals. Fiery Emancipation is a
    replacement and reads the per-blow source since V44.
  - Correction: this entry used to say that Brash Taunter's echo hits its own controller after a
    fight. It does not. The echo's opponent is chosen in the trigger controller's coordinates and
    its filter reads the recipient (`brash_taunter_fight_redirects_to_opponent` passes, with and
    without the decision).
  - Fix: a per-row cause. The V3 dealer lane (`verbs.damage_source`, the Atom lane's DEAL_DAMAGE
    cause) is the one-dealer model; FIGHT needs two.
- **CounteredEvent has no trigger or history reader**: the countered spell has left the stack
  when its COUNTER row is matched, so a "spell" filter cannot be judged afterwards
  (binding._UNSUPPORTED_EVENTS refuses a trigger on it; the history atoms reject it). Needs the
  spell's last known information on the row before "whenever a spell is countered" or "if a spell
  was countered this turn" can be written.
- **The journal records a player's net life change per atom** (events.py `record_atom`): a
  lifelink source dealing damage to its own controller (10E Orcish Artillery with Loxodon
  Warhammer) leaves no DAMAGE, LIFE_LOST or LIFE_GAINED row, though that player lost 3 and gained 3
  (CR 120.3a, 702.15b). Every history and trigger reader inherits it (EVENT_THIS_TURN, bloodthirst,
  LIFE_GAINED_THIS_TURN_GE, "whenever you gain life"). Fix: journal player damage and lifelink gains
  from the verbs' own tuples, not the life diff.
- **A created token's ability record is keyed by its name alone** (2026-11-06): `_v_create_token`
  (verbs.py ~1340) registers the binder record under `token_oracle_id(spec.name)` once per game, so
  two different token specs sharing a name (two different "Spirit" tokens) would both get the first
  one's triggered/static abilities. Not live: in the M21 and M20 verified pools only Pirate, Treasure
  and Ajani's Pridemate tokens carry abilities, one definition each. Fix before a pool has a clash:
  hash the spec's abilities into the id.

### Effects, zones and replacements

- **B-30 `identity_of` drops oracle text and stamps `set_code="M21"` on every card**
  (`core/executor/games.py:402` `identity_of`).
- **B-64 [verifier, FDN round 2] A may-offer, and a Choose inside it, still offer an action that
  cannot be done** (Crypt Lurker's discard with no creature card), a phantom option (AGENTS §10).
  Weaker side only since V12: "if you do" reads whether the optional action changed anything
  (CR 118.12). **Fix.** Offer the may only when the action can be done (CR 609.3).
- **B-65 [verifiers, FDN rounds 1-2] Nothing removes an Aura whose host its enchant filter no
  longer allows** (CR 704.5m). `Executor._unattached_auras` buries an Aura that is unattached or
  whose host has protection from it (V44), not one whose host stops matching (an "Enchant
  creature" Aura on a permanent that stops being a creature). The cast-time host filter is fixed
  (ENCHANT carries the filter).
- **B-72 [fixer A] DESTROY and other direct graveyard moves never check the dies replacements**
  (`verbs._to_graveyard` → `_move_to`). A creature hit by Scorching Dragonfire, then destroyed later
  the same turn, goes to the graveyard instead of exile. Weaker than printed.
- **B-97 [2026-10-29, branch `engine/r5a-until-leaves`; renumbered from B-76 at the integration merge] Ontology R5-1: zone moves "until" an event
  (CR 610.3) are built; what is left.**
  - **"For as long as ~ remains on the battlefield" (CR 611.2b)** ends when the object phases out
    (702.26f). It must not reuse `DurationUntilLeaves`; it needs its own node or a field.
  - **Calix, Destiny's Hand [−3]** ("until target enchantment you control leaves the
    battlefield"): the anchor is a second target, and `DurationUntilLeaves(source="target")` can
    only name the spell's single target binding. Gap ledger; needs a per-slot referent.
  - **Still unparsed** (each needs a clause the compiler lacks, not a new atom): Prayer of Binding
    ("up to one target", ready for a mapper now), Seal Away ("tapped creature"), Glass Casket
    ("with mana value 3 or less"), Sigrid, Colossal Whale, Glorious Protector, Grasping Giant,
    Hixus, Constricting Sliver, Valki.
  - **A return to a zone other than the battlefield consults no replacement effect.** The move
    path asks `replacement_for_zone_change` only for battlefield entries (`verbs._v_move_zone`), so
    Leyline of the Void would not exile Idol of Endurance's returning cards (B-72 family; general,
    not specific to returns).
  - **Simultaneity is per destination zone.** One MOVE_ZONE per zone, in the fixed order
    battlefield, hand, graveyard, exile; within a zone every object moves at once. V32 chooses
    each entering Aura's host inside the move loop, so an Aura returning in the same batch as a
    creature can pick that creature (strictly, 303.4f sees only objects already on the
    battlefield).
  - Kitesail Freebooter's "You choose ... from it" is still asked when Freebooter left before its
    trigger resolved. CR-correct (the choice is made, nothing is exiled), but the ask has no
    consequence.
- **A permanent's static records keep the controller they were attached with** (fresh-eyes
  review, 2026-11-06): `layers._new_static` registers a static PREVENT_EFFECT with the controller
  of the moment, and GAIN_CONTROL does not re-register it, so "you" in a stolen permanent's static
  still means the old controller in `prevents_activation`, the attack/block consults
  (`_rec_ctx`), and possibly the layer statics. `prevents_countering` reads the source's current
  controller (test `test_you_follows_the_permanents_controller`); the other consults need the same
  (CR 109.5), with packs for a stolen "can't block" or anthem static.
- **A Conditional after a step that made two or more tokens judges nothing**
  (`executor._conditional_subject` takes the result register only when it holds one object): no
  tree has such a step today; "if they ..." over several tokens would need its own reading.
- **B-112 [fixer 3, 2026-10-30, review wave 4 residue] CR 111.8 (a token that has left the
  battlefield can't change zones) is not enforced.** W4-4 runs state-based actions before
  triggers, and keeps a token that a queued firing names in the world as its last-known
  information until that firing resolves, so a trigger that moves "it" could still move such a
  token, as before W4-4.
- **Order choices are never asked** (M20 verification round, 2026-11-05; 21/21 planted faults
  caught):
  - Scry keeps the cards it leaves on top in handle order (verbs._v_scry): the player's "any order"
    choice is removed. Weaker only, but live on verified M21 scry cards (B-81: alters options).
  - "Any order" is never asked (Anticipate, Cavalier of Gales, Goblin Ringleader: WRONG); "random
    order" is fixed (Drawn from Dreams, Brightwood Tracker: OK under B-81, information only).
- **Abilities that work from the graveyard are refused** (CR 113.6k; M20 Sanitarium Skeleton), and
  the same row on the battlefield is a paid no-op (the Demonic Embrace shape; extend
  query.inert_row to "moves its own source from a zone it is not in"). Repro:
  `known_bugs/2026-11-05/graveyard_abilities_never_activatable`.
- **Starlight Snare's "doesn't untap during its controller's untap step" blocks every untap of
  the creature** (FDN round 1, 2026-11-06; CR 502.3: only the untap step). Check the verified
  "next untap step" cards too (Frost Breath M21, Frost Lynx M20); it matters only when an untap
  effect is in play.
- **Damage to a permanent that left the battlefield during resolution** is still marked on the
  card (round-3 verification, 2026-11-06: Sorin, Imperious Bloodlord's sacrificed Vampire took 3
  in the graveyard; CR 608.2b).
- **The reveal record of "reveals their hand" lists the library, not the hand** (verbs.py ~1485;
  round-3 verification, 2026-11-06); nothing reads it today.

### Mana and payment

- **B-90 [vfix V2, 2026-10-29] No compiled card retains mana** ("you don't lose this mana as steps
  and phases end": Upwelling, Savage Ventmaw, Leyline Tyrant, Grand Warlord Radha, Birgi, Neheb
  all compile partly); the first one that compiles needs a retention lane in
  `Executor.empty_mana_pools`. The rest of B-90 (no mana outside the active player's main phase)
  is the automatic-payment scaffold: option (a) built, (b) the `PAYMENT:PTR` asks of
  `DESIGN_ACTION_SPACE.md` §1.3 the design target.
- **The payment rule's "most colours stay makeable" is greedy**: 102 of 32,717 random boards
  (0.31%; 0 of 7,204 real-game casts) had a payment leaving a strict superset of colours
  (Conclave Mentor with Blossoming Sands, Temple of Silence, Thornwood Falls, Swiftwater Cliffs).
  Part of the automatic-payment scaffold; a learned payment choice retires it.
- **Hybrid costs (latent; no verified card has one)**: the engine's `build_payment_plan` assigns
  hybrid symbols greedily by printed colour (CR 118.13a lets the payer choose) and ignores
  Chromatic Orrery for hybrid; the planner's Orrery shortcut misses 56 of 2,646 synthetic hybrid
  payments the engine accepts.

### Multiplayer

- **B-108 [vfix2, V42, 2026-10-30] Opponent refs with three or more seats: one acting player is
  loud when it would stand for several.**
  - Measured on a three-seat world (`MTG_bot/core/test_executor_multiplayer_opponents.py`, real
    M21 cards). These play as printed: turn rotation; "each opponent discards" (Bad Deal, through
    V10's per-player discard lane; before V10 only the first opponent discarded); damage to each
    opponent (Storm Caller); each opponent mills (Thieves' Guild Enforcer); Massacre Wurm's -2/-2
    and its per-controller life loss; "as long as an opponent has eight or more cards in their
    graveyard", read from the second opponent; "target opponent" offering every opponent and
    "target player" offering every player (V21); and Teferi's Ageless Insight's draw-step
    exception across the other players' turns.
  - The one wrong answer was `selectors.role_player`. It took the FIRST player a ControllerRef
    denotes as the one acting player of DRAW, SCRY, LOOK_AT/REVEAL, ADD_MANA and MOVE
    `pop_order=TOP`. It now raises when the ref denotes several. This is a hard stop where a silent
    pick used to be, not a cap. No M21 tree reaches it: a scan of every castable and refused M21
    tree finds no singular verb that carries OPPONENT, ALL_OPPONENTS or ANY. Two seats never
    denote several opponents. The suite and a 60-game castable soak stay green.
  - **What would remove the raise:**
    - ALL_OPPONENTS ("each opponent") in those verbs should iterate in APNAP order (CR 101.4), as
      `role_players` does.
    - A non-targeted singular OPPONENT ("an opponent") with several candidates needs a chooser
      ask. Who chooses, and under which tag kind, is a design decision. It is not taken here.
  - Two-seat consumers: `games.py:1175` deals `GameWorld(num_players=2)`.
- **Multiplayer combat**: `selectors.defending_players` reads the engine's one defending player.
  With several (CR 506.2a) it must be resolved per attacking creature (CR 508.5a) from
  `Executor.attacked`, and kept for a creature removed from combat (CR 508.5, second sentence;
  `_remove_from_combat` drops the entry).

### Rules not modelled

- **No copy effects and no layer dependencies** (the 2026-09-10 audit's list for the pre-rebuild
  engine, still true of this one): `Verb.COPY` has no handler in `verbs.HANDLERS`, so no copy
  effect runs (Sublime Epiphany's COPY mode is never offered), and the layer system applies
  effects in timestamp order with no dependency pass (CR 613.8; `layers.py`).
- **Not modelled, because no card in the pools needs it** (B-74 residue; the postcombat main phase
  landed 2026-11-06, 46c7288): a trigger at the beginning of a second
  main phase (the frozen `Phase` has no member for it; the three Sanctums' "first main phase"
  fires once, in the first main phase, CR 505.1a), additional main phases (Relentless Assault,
  10E), and CR 505.4's Saga lore counters (precombat main phase only).

### To triage

- **B-73 [2026-10-29 soaks] The anomaly detectors flag about 2% of M21 games on `main`.**
  - Measured: 18 flags in 800 castable games (400 stress + 400 coherent), all pre-existing. On
    `cards/integration`: 10.
  - The classes:
    - d1: life moved without a journal row;
    - d3: a +1/+1 counter placed on a card already off the battlefield (CR 400.7);
    - d5: P/T recompute mismatch (Goblin Wizard, Thieves' Guild Enforcer, Quirion Dryad, Palladium
      Myr);
    - d6: an end-of-turn grant or lose layer still bound to a card that left (related to B-50 and
      CR 400.7); two replacement records for one event (B-69); a delayed trigger never drained.
  - BUGCATCH's "scan = 0" was 10 catalog seeds, so the larger sample now finds these. Triage each
    class: detector gap or engine bug.
  - Since then B-50 (CR 400.7, f908287) and B-69 (two replacements on one event, a528b03) are
    fixed, and the M20 verified-pool soak found 0 detector hits in 300 games (/184 §12):
    re-measure on the castable pool before triaging.

---

## Card onboarding and gates

### Compiler and ontology

- **B-41 The grammar does not generalize to unseen text**: at first touch PC-2 on sentence shapes
  absent from M21/ZNR is 0.080 (M20) and 0.111 (KHM), against 0.89 on seen shapes. On cards with
  new text, PC-1 is 0.11 (M20) and 0.03 (KHM) (KNOWLEDGE /159). Tied rank 1 needs compositional
  mechanisms over sentence shapes. The cheapest first are keyword lines carrying reminder text, and
  keyword lists (ZND-4a). Measure every grammar round on a sealed split
  (`tools/audit/new_set.py`).
- **B-42 MOVE_ZONE has two spellings for one meaning**: the moved object is `cards` in 67 uses and
  `target` in 20 (the exile family), and "its owner's hand" is `Zone(HAND, OWNER)` on three M21
  cards and `Zone(HAND, ANY)` on three others (KNOWLEDGE /163). That violates the identity law
  (DESIGN_ATOM_ONTOLOGY §6). Settle it in a gated ontology round, re-baking goldens.
- **B-44 One-card predicates**: `LIFE_LEAD_OVER_START_GE`, `NAME_PARTITION_COUNT_GE`,
  `ATTACK_AGAINST_COUNT_GE`, `NOT_FIRST_DRAW_THIS_STEP`, `INSTANT_OR_SORCERY_CAST_THIS_TURN` read as
  single cards. Decompose them into general atoms (e.g. a QThisTurn count of CastSpell events with
  an FOr filter) in a gated ontology round ("as few subcomponents as possible", owner 2026-10-19).
  - **Measured 2026-10-28 over 19 sets (4,486 compiled cards).** There are 193 component types. 48
    of them cover 90% of uses, and 50 (26%) are used by two cards or fewer.
  - The tail folds into a few general shapes:
    - eight "this turn" predicates are one counted-event atom with a filter and N: `CARDS_DRAWN_`,
      `CAST_THIS_TURN_FROM`, `ENTERED_THIS_TURN_FROM`, `MOVED_TO_ZONE_THIS_TURN`,
      `WAS_CAST_THIS_TURN`, `INSTANT_OR_SORCERY_CAST_`, `NOT_FIRST_DRAW_THIS_STEP` and
      `ATTACK_AGAINST_COUNT_GE`;
    - five comparators are one property comparison: `CMC_GE`, `COLOR_COUNT_GE`,
      `CONTROLLER_COUNT_GT`, `LIFE_LEAD_OVER_START_GE` and `NAME_PARTITION_COUNT_GE`;
    - `FIGHT` is two damage atoms.
  - Owner, 2026-10-27: components that "capture a lot of [the cards'] functionality, such that our
    model needs to learn less atomised components", so the network shares structure. Track it with
    the reuse numbers above.
  - **Collapse the legacy turn-history atoms onto `EVENT_THIS_TURN`** (AGENTS §9: one meaning, one
    encoding). DIED_THIS_TURN, LIFE_GAINED_THIS_TURN_GE, CARDS_DRAWN_THIS_TURN_GE,
    INSTANT_OR_SORCERY_CAST_THIS_TURN and MOVED_TO_ZONE_THIS_TURN are each `EVENT_THIS_TURN` /
    `SUBJECT_OF_EVENT_THIS_TURN` over an existing EventSpec. They stay because M21 trees must stay
    byte-identical; the condition grammar emits them for their old wordings so there is one encoding
    per meaning today. Two behaviours change in the move and need a decision: the general atom
    counts a threshold per individual (LIFE_GAINED/CARDS_DRAWN with `who=OPPONENT` sum over all
    opponents, wrong in multiplayer), and DIED_THIS_TURN's existential fallback for a non-creature
    judged handle becomes an explicit choice of atom. Do it at an era boundary, with the goldens and
    verified trees re-pinned. WAS_CAST_THIS_TURN stays: a permanent's cast row comes before its
    entry, and only it follows the spell onto the battlefield (CR 400.7c; the fresh-eyes review
    showed that folding it would make Containment Priest exile every cast creature), so
    `SUBJECT_OF_EVENT_THIS_TURN` refuses a CastSpellEvent.
- **B-48 [2026-10-28] Discard has two encodings.**
  - 27 compiled discard effects are `MOVE_ZONE` from hand to graveyard: Jeskai Elder, Liliana's
    Steward, Duress, Bad Deal and others. One card (Coralhelm Chronicler) uses `Verb.DISCARD`.
  - Same meaning, different bytes: this breaks the identity law and splits the network's training
    signal for one concept.
  - Discard is a keyword action (CR 701.8), and "whenever a player discards" triggers and madness
    key off it. So pick one encoding in the ontology round, probably `DISCARD`, and re-bake
    the affected goldens at an era boundary.
- **B-47 [/167, S-3b differential] Nothing keeps a token's `type_line` and its `types`/`subtypes`
  in step.** The executor mints a token's identity from `type_line` alone
  (`verbs._v_create_token`); Speaker of the Heavens' Angel (`type_line="Angel"`, fixed 2026-10-30,
  a5c6dfb) was the only TokenSpec in the 19 sets missing a card type, and it could not attack or
  block. Either `TokenSpec.__post_init__` checks that the line equals the composed fields, or the
  executor mints from the fields.
- **B-75 [2026-10-29, branch `engine/phasing`] Phasing (CR 702.26) is implemented as a status; one
  printed clause still has no ontology.**
  - **Open, weaker than printed: Teferi, Timeless Voyager's "Until the end of your next turn, they
    can't phase in."** Accepted as divergence D16 by ontology R5-9 (gate round 3 GO,
    2026-10-30; `docs/ATOM_DIVERGENCES.md`). The compiler's built-in `_phase_in_prevention_effect` (`compiler.py` ~206)
    emits `PREVENT_EFFECT(event=ZoneChangeEvent(COMMAND/OPPONENT -> BATTLEFIELD/OPPONENT),
    condition=CONTROLLER_IS OPPONENT, duration=DurationUntilNextTurn)`. Phasing is not a zone
    change, so the record is inert and the creatures phase back in at their controller's next
    untap step. Repro: `tools/scenarios/known_bugs/teferi_timeless_voyager_cant_phase_in.json`.
    What the clause needs, for the next gated ontology round:
    - an event: a phasing event shaped like `TapStateEvent`, e.g. `PhasingEvent(phased_in: bool,
      filter: Filter)`, that the phasing step offers to the prevention registry before each
      phase-in (the consumer: `Executor._phasing_step`);
    - "they": the creatures the preceding PHASE_OUT phased out. PHASE_OUT writes the `result`
      register, so either a filter referent for it or the `_v_prevent` convention of materialising
      the affected set at registration (today it reads the `target` binding, here the targeted
      player). `CONTROLLER_IS OPPONENT` is broader than "they" (it would also hold a creature
      phased out earlier by another effect, stronger than printed);
    - the duration: `DurationUntilNextTurn` ends as your next turn begins, the printed text at
      its end. Phase-ins happen only in their controller's untap step, so no reachable game tells
      them apart today; a PHASE_IN effect during that turn would.
  - No carrier: the phasing keyword (702.26a's phase-out half), PHASE_IN (702.26c by an effect),
    a directly phased-out Aura (702.26i), "for as long as" durations tracking a phased-out
    permanent (702.26f; `DurationUntilLeaves` must not end on phasing, R5-1).
- **B-77 [fixer A, m21-fidelity item 4] A spell's "would die this turn, exile it instead" has no
  duration in the tree** (play is right; the encoding is implicit).
  - Scorching Dragonfire (M21, ELD, FDN), Obliterating Bolt (FDN) and Blitz of the Thunder-Raptor
    (IKO) compile a card-level `ReplacementAbility` with no duration (the IR node has no such
    field). The executor registers a resolving instant's or sorcery's ReplacementAbility until end
    of turn, scoped to the cast's designation (`stack.py`, `replacements.register_ephemeral_
    replacements`), which is the printed "this turn" for all five. Packs
    `scorching_dragonfire_late_damage_creature` and `scorching_dragonfire_expires_next_turn` pin it.
  - So the model's static view of these cards does not show "this turn", and a future spell whose
    replacement has another duration would be played wrong without a compile error.
  - Options: (a) an optional `duration` on `ReplacementAbility` (ontology change, the R5-1 sibling
    for replacements; the Dragonfire family re-bakes with `DurationEot`); (b) keep the executor rule
    and write it into the ontology doc as the meaning of a ReplacementAbility on an instant or
    sorcery (no IR change; the gap stays implicit).
  - The spell-side death replacement is still skipped by DESTROY and other direct graveyard moves
    (B-72).
- **B-80 [fixer A, m21-fidelity] "Can attack as though it didn't have defender" has no
  component** (Drowsing Tyrannodon, live in M21; slightly weaker than printed).
  - It compiles to LOSE_ABILITY(DEFENDER) while you control a creature with power 4 or more, so
    the Tyrannodon stops having defender (Portcullis Vine cannot sacrifice it as "a creature with
    defender"). Review pack `tyrannodon_still_has_defender_for_portcullis_vine` (batch B) fails.
  - The attack legality reads DEFENDER directly (`legality.py`, "no 'can attack as though it
    didn't' carrier in the corpus"). Options for the gated ontology round: (a) an attack
    permission atom (a "may attack despite defender" policy, the MANA_POLICY/GRANT_ACTIVATION
    family) the attack check consults; (b) a parameter on KeywordAbility(DEFENDER) carrying the
    "as long as" condition. (a) keeps DEFENDER a plain keyword and is reusable for "can block as
    though" cards; recommended.
  - Re-checked on 18afa85 (2026-10-30): tree unchanged; the Portcullis Vine pack still fails, the
    two attack packs pass.
- **B-81 [fixer A, m21-fidelity item 5] Lossy rows judged (2026-10-29).** Significance per
  AGENTS §11 (alters legal options or state outcomes).
  - Significant, not fixed: See the Truth's "If this spell was cast from anywhere other than your
    hand, put each of those cards into your hand instead" runs as an extra step that returns one
    card, not all three. It is unreachable until something lets you cast it from elsewhere
    (Chandra, Flame's Catalyst's -2, R5). Fix: the conditional "instead" arm (as Life Goes On),
    replacing the one-and-rest split, once a pack can cast it from the graveyard. Re-checked on
    18afa85 (2026-10-30): tree unchanged, still unreachable.
  - Not significant, kept: Garruk's Harbinger "in a random order" (the bottom order is
    information, no option changes); Cultivate's REVEAL count (REVEAL is a recorded no-op);
    Fiery Emancipation's universal recipient (damage only ever goes to permanents or players);
    Malefic Scythe's kind-blind counter count (nothing in M21 puts another counter kind on an
    Equipment); Barrin's unconstrained "a permanent" (anything moving from the battlefield is
    one); Chandra's Incinerator (the engine sums noncombat damage dealt TO opponent seats, as
    printed; only the docstring's reading is off).
- **B-96 [fixer 4, 2026-10-29] "You have no maximum hand size" compiles nowhere.** Since V36 the
  cleanup step discards down to seven (CR 514.1, 402.2: `executor.MAX_HAND_SIZE`, read only by
  `Executor._discard_to_hand_size`). The sentence is UNPARSED on Reliquary Tower (M13), Spellbook
  (10E), Niv-Mizzet, Visionary and Finale of Revelation (FDN), Folio of Fancies and The Magic Mirror
  (ELD) and Sea Gate Restoration (ZNR), so these partly compiled cards are now weaker than printed
  in the pool modes that deal partly compiled cards. No M21 card and no FDN record is affected.
  Needs a component for a player's maximum hand size (a static over the player, and "for the rest of
  the game" on a resolving effect): an ontology decision for a gated round.
- **B-98 [2026-10-29, branch `engine/r5a-until-leaves`; renumbered from B-77 at the integration merge] Ontology R5-6: `TargetingEvent.actor`
  ("becomes the target of a spell or ability an opponent controls") is built; the rest of the
  census needs other pieces.**
  - Not compiled, each for a reason outside R5-6 (11 cards, 8 sets, by the oracle census):
    - Frost Titan (M11, M12), Diffusion Sliver (M15), Reidane (KHM): "counter that spell or ability
      unless its controller pays": abilities never sit on the stack, so an ability cannot be
      countered (R5 gate round 2).
    - Ward (Cackling Prowler, Tolarian Terror, Zul Ashur; FDN): the IR has no WARD keyword, and
      ward (CR 702.21a) also counters abilities, which cannot be countered here.
    - Battle Mammoth (KHM): its clause "you may draw a card" does not parse on its own.
    - Shield Mare (M19): "When this creature enters or becomes the target ...", a trigger on either
      of two events, which no template composes.
    - Leyline of Combustion (M20): "you and/or at least one permanent you control" triggers once per
      spell, not per targeted object, and "that player" needs a referent for the event's actor.
- **B-100 [fixer 3, 2026-10-30; renumbered from B-76 (the defender entry took it) and then B-98 (R5-6 took it) at the integration merges] Two permission rows do nothing until the R5 permission lane.**
  Weaker than printed; never a crash and never a phantom option.
  - Radha, Heart of Keld's "you may play lands from the top of your library" compiles to a free
    row whose CAST is filtered to lands. A land is never cast (CR 305.1: playing it is a special
    action), so the row can do nothing: the CAST head refuses with a cast-gap ledger row, the
    may-offer narrows to skip, and `query.legal_activations` no longer offers the row
    (`query.inert_row`). R5-3's `play_lands` makes it playable.
  - Demonic Embrace's "You may cast this card from your graveyard ..." is refused
    (`compiler.casts_itself_from_another_zone`, a KNOWN-GAP row), so the card is engine-unsupported
    until R5-2's permission lane (PERMIT_CAST) brings it back.
- **B-101 [fixer A, 2026-10-30] Protection residues after V44** (one oracle,
  `legality.protected_from`):
  - 702.16n/p ("this effect doesn't remove Auras") has no IR; no compiled card needs it (M15
    Spectra Ward does not compile).
  - The compiler has no general "Protection from <quality>" line: only the printed M21 forms
    compile, and an unseen "Protection from black" stays unparsed (`compiler._is_keyword_line`);
    702.16k (from a player) has no compiled shape.
- **B-109 [2026-10-30, branch `engine/r5b-go-items`] Ontology R5-7: `AbilityActivatedEvent` and
  one CR 605.1a classifier.**
  - Gap ledger: "whenever you activate a boast ability" (KHM Frenzied Raider) has no kind (boast
    has no IR component). Expressible but not compiled: the trigger users Runic Armasaur and
    Kurkesh (NON_MANA), Sarkhan's Whelp (ANY), Chandra's Regulator (LOYALTY); the locks Bound in
    Gold, Pithing Needle, Sorcerous Spyglass (NON_MANA) and the twelve "can't be activated" cards
    (ANY; `reports/r5_census_2026-10-29.json`). Pithing Needle, Spyglass and Phyrexian Revoker
    also need their named source (`CHOOSE_NAME` + `NAME_CHOSEN`).
  - "[0]:" abilities are expressible now but no template parses them (`frames.py` B13-loyalty and
    the `templates_b5c.py` loyalty patterns take only `+N`/`−N`): 12 cards in 11 sets, none in
    M21.
- **B-107 [vfix2, V15 residue, 2026-10-29] Untargeted "up to N" still compiles as an exact count**
  for M21 Rewind ("Untap up to four lands") and Cultivate ("Search your library for up to two
  basic land cards"): the player must take the full count when it is available (weaker than
  printed; rarely matters). `resolve_selector`'s CHOOSE has a QAtMost lane with a NONE stop since
  f80c7d4 (Ugin's −10, Alpine Houndmaster), so the fix is QAtMost in those two templates.
  - A library search can never fail to find (CR 701.19b): only Alpine Houndmaster's named finds
    can (QAtMost, CR 701.23b); every other tutor still finds when it can.
- **IS_SOURCE means both "this spell costs" and "this ability costs"** (red team, 2026-11-06): since
  de9fbd6 the cost fold reads a dealt spell's own modifiers, so Sanctum of Tranquil Light's
  activation discount ("{1} less for each Shrine") also folds into its own cast from hand. Harmless
  today (it costs {W}, nothing generic to cut) and no other card is affected; give the activation
  discount its own predicate before a card with a generic cast cost has one.
- **Landwalk is a keyword the defending-player census shows** (2026-11-06; CR 702.14c: "can't be blocked as long as
  the defending player controls" a land of the type). About 20 cards in 10E and M10-M15 print or
  grant it (Bog Wraith, Plague Beetle, Rock Badger, Rootwater Commando, Rushwood Dryad, Emerald
  Oryx, Bog Raiders, Lurking Crocodile, Harbor Serpent, Merfolk Spy, Stormtide Leviathan, Colossal
  Whale, Mirri; Elvish Champion, Goblin King, Dryad's Favor, Volcanic Strength, Master of the Pearl
  Trident; the Coral Barrier and Chasm Skulker tokens), about 10 of them fully compiled by it alone.
  Others read it as a keyword ("Creatures without flying or islandwalk can't attack"), so it must be
  `Keyword` with a land-type parameter, read by the block legality through DEFENDING_PLAYER, never
  a static compiled from its reminder text.
- **"The player or planeswalker it's attacking"** (Scorch Spitter) is the attacked object, not the
  defending player: it needs a referent over `Executor.attacked` that survives removal from combat.
- **"Defending player controls an Island / no Walls"** (Sea Monster, Serpent of the Endless Sea,
  Siege Dragon): CONTROLLER_COUNT_GE counts only "you"; it needs a `who` slot. The search plans
  attacks before combat opens (`search.plan_attacks` at `pre_combat`), when there is no defending
  player yet, so a "can't attack unless defending player ..." restriction would drop out of its
  plans; decide it at the declaration.
- **"Whenever equipped creature becomes blocked"** (Tormentor's Helm) has no event: it triggers once
  per combat however many creatures block (CR 509.3c), BecomesBlockedEvent is anchored to the
  source, and DeclareBlockersEvent(blocked=...) fires once per blocker.
- **Ancient Hellkite** now compiles "{R}: This creature deals 1 damage to target creature defending
  player controls." but not "Activate only if this creature is attacking."; and until players act
  at every priority point (DESIGN_PRIORITY §11 5b-2) no ability can be activated while attacking.
- **"You may pay <mana>." composes with any trigger frame**, so the payment half of a pair whose
  second half has no template now parses on partly compiled cards (Llanowar Sentinel, Tenacious
  Dead, Frenzied Goblin in M15 and FDN, Skyrider Patrol, Sparktongue Dragon, Eternal Taskmaster,
  Embereth Skyblazer): their "When you do" / "If you do" halves need templates.
- **Measured and not built in component wave 2** (cards each would fully compile; NUMBERS.md
  2026-11-06):
  a delayed trigger that remembers the objects it is about (CR 603.7b/c: one-shot, "at the
  beginning of the next end step" or "at end of combat", does nothing to an object that changed
  zones), 4 (Fog Elemental, Crumbling Colossus, Phytotitan, Tiana), the largest engine change, and
  it reads the created-token `result` that wave added; the cost parts "Remove N <kind> counters
  from this <permanent>" and "Exile this <permanent>", 4 (Hanged Executioner, Brittle Effigy,
  Inquisitive Puppet, Steelbane Hydra; 2 more, Soul of Zendikar and Soul of Ravnica, also need
  activation from a graveyard, CR 113.6m); a discard trigger event, 3 (Megrim in 10E and M10,
  Liliana's Caress); a life-total threshold, 3 (Twinblade Paladin in M20 and FDN, Serra Ascendant).
- **What the history atoms do not read** (refused or documented, 2026-11-06): untap-step rows
  precede `journal.turn_window()` (no turn-start marker), so "became untapped this turn" is refused;
  a damage threshold counts per recipient, never per dealer ("a source you controlled dealt 5 or
  more damage" needs a dealer grouping); `binding._match_damage` ignores `DamageDealtEvent.amount`,
  so the history atoms require QUnbounded there and read "how much" from their count.
- **Still needs an atom** (from the 92 needs-atom records the turn-history work read): "Activate only once each turn"
  (Frilled Sandwalla) needs the ability's identity on `AbilityActivatedEvent` (the row has the
  index; no filter names "this ability"); "you've cast another spell this turn" (Illusory Angel) is
  a cast restriction; conditional uncounterability (Banefire's "If X is 5 or more", Exquisite
  Firecraft's spell mastery), "can't be countered by blue or black spells" (Autumn's Veil) and the
  compound "cost {1} less to cast and can't be countered" (Thryx, Cunning Nightbonder) have no
  template; "Each opponent who cast a spell this turn" (Angelic Arbiter) needs a per-player judged
  history; Vengeful Warchief and Vilis can now use LifeLostEvent as a trigger.
- **Lure has no atom** (round-3 verification, 2026-11-06): Prized Unicorn (M20, needs-atom) "All
  creatures able to block this creature do so" puts a requirement on each creature able to block
  it, obeyed only by that creature blocking it. A lure atom must also extend the count of
  requirements a block declaration obeys (`most_obeyed` in `_declare_blockers`) to those
  per-creature requirements; the matroid greedy over attackers no longer gives the most then (a
  maximum-weight matching does, menace aside).
- **Reflexive triggers have no node** ("when you do", CR 603.12; round-3 verification,
  2026-11-06): Sorin, Imperious Bloodlord was
  mapped as "if you do" with the target chosen on activation; the review refused it (the target
  exists even when nothing is sacrificed, and the Vampire about to be sacrificed is offered).
- **A planeswalker whose emblem record is empty should not reach a supply** (M20 verification
  round, 2026-11-05): Mu Yanling, Sky Dancer's -8 emblem is unmapped, so the -8 does nothing.
- **B-46 [/166; first touch done + round S-3a, /167] Fourteen older sets are dealt mostly partly blank.** The castable pools of M19,
  10E, M10–M13, M15, ORI, DOM, WAR, FDN, ELD, THB and IKO deal 2,482 cards. Only 683 of them
  (27.5%) are fully compiled; the engine plays the rest with their unparsed sentences blank.
  - Their IR matches what the engine does, so K1b could train IR encoders on them. But clean
    volume (fully compiled only) is 556 training cards against 1,829 dealt.
  - Every grammar round on these sets adds clean training cards, and the K1b curve was still
    rising at 16 sets.
  - M14 cannot be dealt at all: 9 mana-capable castable cards, and `build_deck` needs
    `MIN_MANA_SOURCES` = 10.
  - Sealed first touch is done for all 15 (with M14), with baselines and an S-3a round-end read
    (/167). Their dev registers may now be read by grammar rounds; the test groups stay
    sealed, read once per round.
  - Synthetic cards (atoms composed with sampled parameters) come after real-set volume, as the
    clean test of genuinely new compositions (owner, 2026-10-27).
- **B-40 PC-2 counts a shape-gap card's front sentences as matched**: `measure_pool` puts them in
  `sentence_total` but never in the unparsed queue (`core/compiler/coverage.py:368-531`), while PC-1
  counts the same card against coverage. One card in ZNR, two in M20, three in KHM.

### Records to map or re-verify

- **M20 Tale's End can go back to G1 and G2** (2026-11-11): its record is mapped but not verified,
  and its notes call it weaker than printed because no ability on the stack could be targeted.
  Since B-110 closed (abilities on the stack are targets, `stack.stack_abilities`), its whole
  text plays; M21 Sublime Epiphany's packs `sublime_epiphany_1/2` show the same target.
- **M20 Mystic Forge (needs-atom): re-map it.** Its permission cast can be countered (851d652; its
  pack `pack_forge_cast_can_be_countered.json` passed against its draft with the old counter window,
  so re-run it with a response cast while the spell waits on the stack); the target half is "The
  CAST atom has no target channel" under the engine faults.
- **FDN Joraga Invocation can go back to G2**: it was refused because a must-be-blocked
  requirement forced the first able blocker; the defender chooses since 62a1ae2 (2026-11-06).
- **FDN round 1 record findings** (2026-11-06; neither card is verified):
  - Incinerating Blast's mapped discard is ONE_OF where the compiler writes CHOOSE; the pick is
    journalled as a targeting event on the discarded card.
  - Good-Fortune Unicorn's trigger placed no counter in a verifier's pack (not investigated).

### Gates, probe, soak and the pack runner

- **G3 counts equivalent mutants as survivors** (2026-11-05, 2026-11-06): a mutant whose changed
  part the engine never reads survives every pack, so G3 refuses a card no pack can clear.
  - M20: Gods Willing (its colour is chosen at resolution, so the five TARGET selectors bind one
    slot and an ALL selector in that role resolves to the designation; gates.py `_twin_targets`
    skips abilities with a Choose) and Blightbeetle (a static prevention never reads its atom's
    own `condition`).
  - FDN: Battlesong Berserker (`target->all` on a trigger whose two steps share one designation:
    identical selectors merge, binding.py ~1950, and `role_handles` returns the bound target
    whatever the mode, selectors.py ~1315) and Searslicer Goblin (`your turn -> each turn` when
    the condition already requires TURN_OF YOU: the actor check, binding.py ~1104, and the
    condition test the same thing). No game can tell either mutant from the card. Both verdict
    copies are ready to re-run (scratchpad g3kill_fdn/verdicts).
  - Fix: an equivalent-mutant rule (a dead-role check) in `gates.mutants`. `gates._twin_targets`
    (gates.py:339) treats only spells as sharing one target; extend it to triggers, and treat a
    trigger-scope mutant as dead when the condition already fixes the turn.
  - Separately, `cardtool.py mutate --out` writes nothing (`cmd_mutate` never reads `args.out`).
- **Probe (G1) blind spots** (verifiers: M20 2026-11-05, FDN round 1 and round 3 2026-11-06).
  - Clauses left NOT_EXERCISED: granted abilities are never activated, loyalty never reaches an
    ultimate, the land drop is always a Plains, the library holds 6 cards, no planeswalker is on
    the board, and the "Aura" probe card is a 2/2 creature.
  - A 0/0 X creature dies at setup (Wildwood Scourge); stimuli never end the turn, so "until end
    of turn" on a triggered effect goes unexercised; the opponent's attack stimulus never asks
    for blocks; an Equipment's attachment is invisible without a static; combat stimuli answer
    trigger target asks and unprimed "may" choices internally; pools emptying at end of turn
    hide payments.
  - An animated land shows only +HASTE (no P/T or type) in G1 (Wakeroot Elemental).
- **Pack runner (`tools/run_scenarios.py`)** (pack-repair agent and verifiers, 2026-11-05 and
  2026-11-06):
  - **Decision words no ask uses pass silently** (the third silent-pass hole, after unread expect
    lanes and unoffered words, both closed 2026-11-05). Measured over 1,182 packs: 224 have
    leftover words, but 189 are cast/activate steps whose words the runner hands out twice (the
    spell's primed `decisions` and the provider's queue copy), so the provider's copy stays
    unconsumed although the words were used. The other 35 are genuine leftovers (enter 12,
    end_turn 10, combat 7, advance_turn 5, deal_damage 1; e.g. faiths_fetters "skip",
    spirit_of_malevolence_dies_trigger "foe"). Fix: hand each word out once, fail a step that
    leaves words unused, then repair the flagged packs with red evidence.
  - **The `cast` op still gives its words to two lanes.** It passes the step's words to the cast
    as its decision pool (where `stack.cast_modes` takes a mode word) and to the provider. The
    provider's queue does not drop a word the pool took, so a cast step that names a mode by word
    and then answers an ask its resolution makes would hand that ask the mode word. No pack does
    that today. The `activate` op stopped passing a pool on 2026-11-06 (7a40f78), for the same fault
    with a permission row's "fire" (all 729 packs ran identically either way).
  - In cast steps decision words reach the engine raw (pack keys are not translated) and a
    skipped word restarts the queue.
  - In a combat step, a creature missing from the `attack` map takes its attack answer from the
    step's `decisions`, which shifts the words meant for a trigger.
  - The deal_damage op cannot target a player.
  - The docstring omits the `life` op and lanes the runner reads (kickback_asks, battlefield_pt,
    battlefield_keywords).
- **Packs bind every placed card's record; games bind none until a card is cast, played or
  enters** (2026-11-06): the pack runner calls `attach_pool` after placing the cards, which binds
  `handle_record` for every zone, while `_setup_game` attaches the pool before the decks are dealt.
  So no pack could see the fetched-land bug fixed with this entry (a pack fetching a land passed on
  the broken engine; only a test through `_setup_game` was red). Make the runner bind like a game
  (battlefield, stack and graveyard at setup; hand and library unbound). The
  `handle_record.get(...)` readers are audited (2026-11-06, branch `fix/live-play-bugs`): only the
  CR 601.2f cost fold read a card in hand that way, so a dealt card's own "this spell costs" modifier
  never applied (Volcanic Salvo was never offered); it reads `spell_record` now. The other readers
  read battlefield permanents, which are bound on entry.
- **The soak's repeated-activation screen counts per turn** (2026-11-06): its "6 or more in a turn"
  threshold was set for one 10-act window per turn; since 2026-11-11 a player may act at every
  priority point of every step (the act cap is 10 per player per step), so legal activations spread
  over a turn flag (Seasoned Hallowblade, discarding a real card each time). Count per step, the
  act cap's unit.

---

## Training and measurement
- **Distillation from playout labels (parked by the owner, 2026-11-09; DECISIONS D21).** E3 failed:
  one round changes ~3% of choices and cuts regret 2-4% (100k and 300k labels), winning nothing
  measurable; the epoch rule (held-out KL, epoch 0 included) kept the untrained network because 92%
  of the targets tie (KNOWLEDGE 2026-11-06/186 §5). To look at: stop or choose epochs by regret on
  held-out positions, not by held-out fit; the step (eta 1.59 is near hard labels; 186 §3: the owner's
  45/30/25 example converges only below ~0.1); more futures per label (fewer ties, less noise);
  several rounds (expert iteration) rather than one; lr and epochs. On disk: 449k greedy k 2 d 2
  labels from runs/selfplay/r23_mulligan/gen.pt (runs/labels: e1_A*, e3_A*, e3b_A*, bank_A*, bank2_A*),
  19k sampled (e1_B), 10.5k k 4 (e1_C*), the 2,099 regret positions (e3_regret); 2.9 GB. Scripts:
  `git show df8c4de:tools/selfplay/experiments/<name>`.
- **How far to take the opponent simulator** (owner, 2026-11-06; after E0 and Phase 2's play-time
  search): test how much each extension helps against what it costs in compute time.
  - How many cards to predict: hand only; hand plus the next 3-5 library cards; the whole remaining
    library. Measure belief quality (NLL, calibration), the error of playout labels on belief futures
    against true-card futures, and play strength with search (paired, unseen deals), against the
    training and inference time per decision.
  - The consequence part (the owner wants likelihood AND consequence): a head, trained on the
    playouts of play-time search, that predicts how much a candidate hidden card changes each move's
    result; it drives the importance-sampling proposal (likelihood x consequence). Measure the gain
    in search strength per added millisecond.
  - How many candidates per decision (d sampled hands) and per slot before the gain flattens.
- **From the owner's learning vision** (docs/OWNER_VISION_LEARNING.md, 2026-11-06):
  - Knowledge tracking: what each player legally knows about cards in hidden zones (a card an effect
    put on top or on the bottom, a revealed card returned to hand), erased by a shuffle; give it to
    the networks (section 4). Decide whether the opponent's per-card hand age is public (section 4).
  - History or memory input: explicit history features first, then an encoder over the game's events
    (section 3).
  - The opponent simulator: beliefs over the opponent's hidden cards, trained by supervision from
    finished games, used by the search's determinisation and possibly as policy input (section 5).
  - Matchup blocks: many games on the same decks with fresh shuffles, both seats, as a learning test
    and a curriculum; measure on unseen matchups against memorisation (section 7).
- **Teacher that drafts decks and matchups** (owner idea, 2026-11-06; long horizon): a trained teacher
  builds decks and picks matchups (student vs a chosen frozen version) that teach the student what it
  is weak at, balancing niche and meta play and unfair matchups against the two players' strength, so
  that each game maximises learning; it also learns deck-building. Established form: environment
  design / automatic curriculum (PAIRED, ACCEL, teacher-student curricula). Needs a student that
  learns reliably first (/184 §25).
- **Signal plan** (2026-11-06, after the PPO audit; measuring now): duplicate deals in training (each
  deal from both seats, the pair's result learned), lambda toward 1 (the full result reaches every
  decision), and at least B* decisions per optimizer step (gradient accumulation). Measured (/184 §26):
  B* ~2.2M decisions; pairing and lambda = 1 do not lower it. The privileged critic (training-only
  value network seeing hidden cards) is dropped (owner 2026-11-06; estimated gain only 1.3-1.8x).
  Candidate core instead: per-decision targets from playouts that compare alternatives on the same
  sampled futures (luck cancels), sampled from the player's beliefs, never the true hidden state.
- **Explore/exploit league** (owner idea, 2026-11-06; after the PPO audit): alternate exploration and
  exploitation to climb in "level ups": exploiter agents trained only against the frozen main policy
  find new strategies; a behavioural-diversity measure (how differently a candidate decides on a fixed
  probe set of states) keeps the explored strategies distinct; the main policy then trains against the
  promising ones (prioritised by how hard they are to beat), freezes, and the cycle repeats at the new
  level. Established forms: AlphaStar's league with exploiters, PSRO, population-based training.
  Blocked on the audit: an exploiter is "learn to beat a fixed opponent", which the learner does not do
  today (/184 §22-23).
- **More name masking** (2026-11-06, the r19 game review): the network reads whether a targeted effect
  helps or hurts from card names, not components (`name_dropout` 0.1); raise it so it must read the
  rules text, and measure masked play.

### Self-play stack

- **Spawned workers import torch (~530 MB each, ~9.5 GB for 18 workers).** Spawn re-imports the
  parent's main module (tools.selfplay.learner, which imports torch) in every child; the workers
  themselves only send inference requests. Fix: launch through a torch-free entry module, or make
  learner.py's torch imports lazy. Memory, not correctness.
- **Optimizer state is not saved for resume.** A resumed run restarts AdamW's moments, so its
  first updates differ from an uninterrupted run. Save the trainer's optimizer state with
  state.pkl (the trainer process owns it).
- **An eval running at a resume is lost** (queued ones survive). Re-queue in-flight evals.
- **The value loss moves the policy through the shared trunk** (2026-11-10, `KNOWLEDGE/2026-11-10/189`
  §8). A value-only update at v0 moves the policy by KL 0.0021 and changes its top choice in 0.9% of
  decisions, as much as the full update (0.0026, 1.0%): drift with no evidence behind it. Candidates
  for the run after r26: value coefficient 0.05 (Adam learns the value as fast and leaves more of the
  step to the policy term), a value head that sends no gradient into the trunk, or a separate value
  phase with a KL constraint on the policy (phasic policy gradient).
- **Off-policy lag**: 42-135% of each r17 batch was played on the previous weights (collection
  overlaps the update). The importance ratio corrects it and the bf16/fp32 ratio is unbiased
  (mean 0.9996), but the data is further off-policy than CleanRL assumes; watch the clip fraction.

### What the network sees

- **The network sees neither which planeswalker an attacker attacks, nor block pairings, stack
  targets, emblems, or live (not printed) types and colours** (interface audit, /184). Needs input
  columns, zero-initialised on load like new ask kinds (`model.load` pads card, player and global
  columns with zeros since 2026-11-06).
- **A target ask does not show the X its row announced** (2026-11-06): X comes first, in the act
  row (`cast:<card>:x<N>`, CR 601.2b), but the target asks that follow show the spell only as the
  ask's source card, so Volcanic Geyser's and Primal Might's targets are chosen blind to X. Add the
  declared X to the target ask (a global column).
- **A phased-out permanent is an ordinary battlefield card in the observation** (B-75;
  `tools/selfplay/features.py` `encode`, AGENTS §10). The menus never offer it; the bench seat view
  marks it. Add a `phased_out` row word (like `tapped`) at the next observation-schema change.
- **The observation cannot see the return rows** (B-97, `tools/selfplay/features.py`): a policy
  trained on it does not know that killing Banishing Light returns its card (AGENTS §10). Add the
  row (anchor, card, return zone) at the next observation-schema change.
- **Duress / Kitesail Freebooter's choose ask lists each card twice** (index tokens plus handle
  aliases, verbs._v_choose, r19c), so an agent sees two options per choice and splits its
  probability. One token per choice (the handle) was tried on 2026-11-05 and reverted: r19c made
  the aliases additive on purpose ("the digest and the index lane stay byte-unchanged", for
  replays), and two unit tests and three packs pin the index lane. Decide the replay contract
  first, then switch to handles and re-pin.

### Tickets 2026-10-19 (OWNER DIRECTIVE — generalization & training program; model lane, parked until the atom-ontology lane closes its R-rounds)

- T-G1 FAIR generalization measurement: the random-choice baseline is too weak to be
  trusted (owner). Protocol to design: solid-volume self-play training PER SET
  (~100k-game scale or whatever is demonstrably converged — volume unknown until T-G3),
  then cross-play: M21-dedicated vs ZNR-dedicated models on the ZNR-only pool (and
  reverse). Reuses the /123 era-parity control machinery (frozen bsh_S3a_s3 2×2 grid).
- T-G2 multi-set fairness design: with 3+ sets, per-set dedicated models AND a combined
  main model at BALANCED per-set training volume; acceptance law = the more sets the
  main model trained on, the higher its ELO vs a one-set dedicated model.
- T-G3 set-mastery cost curve: measure compute-per-set-to-mastery (vs good opponents,
  full complexity) once a couple of sets ARE mastered; only then can time-saved from
  atomization be quantified.
- T-G4 keep per-set SPECIALIZED models as first-class artifacts (may be optimal for
  set-restricted games).
- T-G5 ELO/puzzle-system audit for set-transfer fairness (opponent control, pool
  separation, no era confounders) — decide before running the T-G1 matrix.
- T-G6 owner question, needs an answered audit: do our implementations use the 128 GB
  unified memory + compute throughput optimally? Is there any current size class where
  NVFP4 GEMM implementations pay off for speedup?
- T-G7 parallel training on the 128 GB box (multiple runs at once) — feasibility +
  throughput measurement; likely speedup for the T-G1 matrix.
- T-G8 capability-ceiling probes: CONTINUALLY train longer runs to find where ELO
  plateaus; when more complex play styles/techniques stop being learnable, that is the
  parameter-scaling signal (recurring law, not a one-off).
- T-G9 drafting + niche-deck play: still untouched by design (basics first) — stays queued.
- OWNER'S END-GAME CRITERION (context for the atom program): when a NEW set needs only
  atomized-subcomponent implementation + one-or-a-few keyword/mechanic adds + a little
  RL to master, the model is GENUINELY general — that is what the ontology R-rounds are
  building toward (§8 tokenizer law).

---

## Parked: ideas, questions and doc corrections

### Your own recorded ideas that were never built

These are worth keeping because you wrote them down and the reasoning was good. Sorted by how
much they serve the King Goal.

**The complete index of your ideas, with the ones that were lost or distorted, is
[`OWNER_IDEAS.md`](OWNER_IDEAS.md).** This section holds only the ones that belong on the path.
Entries tagged `L1`..`L9` below were recovered in the 2026-09-10 notes audit and had reached no
live document at all.

#### Directly serves rank 1

- **Self-play league / opponent pool.** Removed from the task list in commit `d29a1d6` without
  ever being built. What exists now (2026-11-06, `tools/selfplay/learner.py`) is a pool, not a
  league: PPO against the newest frozen version, older versions (`--p-past`) and the heuristic
  (`--p-heuristic`) at fixed rates, rated by Elo against fixed anchors; no opponent sampling
  follows measured win rates (the "Self-play gate" scaffold row).
  The charter now names adaptive opposition as a default yes. **This is the single
  highest-value item on this list.**
- **Belief vector over hidden information.** From the 272 lines of `RL_ARCHITECTURE.md` that a
  doc rewrite destroyed in `db5e024`; recover with
  `git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md`. It contained a recurrent belief net over
  history tokens, three named encodings for multi-opponent scenarios with a pros-and-cons table,
  deterministic bookkeeping of exact opponent card counts, optional particle sampling of
  plausible opponent states, and supervised pre-training of the belief net from self-play logs
  before end-to-end fine-tuning. It also contained the rule *"do not embed the belief vector
  into every entity token"*, which is right and which
  [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) reuses for pool tokens.
  - **`L4`: when that head is finally trained, weight its loss by the impact of the state.**
    `ideas.md:66` and `:76-95`, never recorded anywhere until now. Your words: *"It should be more
    important to predict a lower-probability high-impact scenario, than the opposite. So how do we
    teach it this if we dont impact that head with the result of the games?"*, answered with
    `L_weighted = W(s) * L_aux` where `W(s)` is proportional to `abs(V(s))`. This matters because an
    unweighted cross-entropy over a sparse label learns the base rate, which is exactly the null
    `METRICS.md` `CLS-3` is built to expose. **Free diagnostic: report `CLS-3` split by `abs(V(s))`
    quantile.** Uniform accuracy across quantiles means the head learned the prior; accuracy
    concentrated in the high-swing tail means it learned inference.
  - **`L6`: opponent strategy as a continuous latent, never a discrete archetype class.**
    `notes.txt:20-22` proposed archetype detection then hand inference conditioned on it;
    `ideas.md:25` sharpened it to *"dont predict discrete strategies, use RGB approach maybe"*. The
    sharpened version is the right one and an authored archetype taxonomy is refused by
    `NORTH_STAR.md` §3 anyway. **Name the tension when this is designed:** `METRICS.md` `VAR-10` is
    an alarm against encoding *who* the opponent is; this encodes *what they are doing*, and a
    design that does not distinguish them will trip an alarm meant for something else.
  - **`L7`: the second encoding.** `project_specific_gemini_context.md:15-18`: encode the visible
    state, run the opponent-hidden predictor, then **encode again including the prediction**. The
    Tier A / Tier B split is not this: there, belief is an auxiliary head that never re-enters the
    encoder. The cheap version already exists in D11's rethink loop, where a later pass can see the
    earlier pass's output at no structural cost, so `b_t` could be visible there for free.

- **`L1`: the composite / super-token encoding, and the hierarchical action space.** The whole of
  `MTG_bot/mtg_token_encoding.md`, 124 lines, cited by no document in this repository. It proposes
  one composite entity per token type per player carrying aggregate stats, an internal per-token
  record for exact simulation, **max/min/median or attention pooling over the individual token
  vectors** so the aggregate is sensitive to extremes rather than to a mean, and a two-level action
  space where the policy says "attack with 3 tokens" and a deterministic layer picks which three.
  **This is a written answer to the open question at
  [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) §10.3**, which asks whether canonical ordering
  of `ATTACK_SET` and `BLOCK_ASSIGN` survives at 8 blockers against 5 attackers and warns the
  failure would present as *"the bot blocks adequately but never finds the good multi-block"*.
  Commander token floods are the case that breaks the token budget, so this is rank 1.
  **Recommended split when it is resolved: refuse the deterministic Level-2 mapper** (choosing
  *which* tokens is a strategy decision and hiding it in the engine hides it from learning, which
  `NORTH_STAR.md` §3 defaults to no) **and adopt the pooling**, which is a representation choice
  costing one op. Whichever way it goes, write it down.

- **`L3`: relational bias in the board encoder's attention.** `notes.txt:63`: *"The game state is a
  graph (a counter is on a creature; an aura is attached to a creature). We will encode these
  relationships by adding a **Relational Bias** to the Transformer's attention mechanism."*
  [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) rejects a tree GNN, but that is about the **card
  ability tree**; the **board** encoder in [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) is flat
  self-attention with **no edge encoding at all**, while `ARCHITECTURE.md:33` (deleted 2026-11-05;
  `git show dd4bce5^:docs/ARCHITECTURE.md`) measures 214 entities
  and **412 relationships** at a Commander start. The proposal is an additive `b_ij` over a small
  typed edge vocabulary (attached-to, controlled-by, counter-on, blocking, targeting, in-zone).
  **The measurement that decides it:** an `N x N` bias tensor per layer is memory traffic, and the
  GB10 is bandwidth-bound, so price it against the same latency harness that sizes the model before
  adopting or refusing.

- **`L8`: the retrieval index does not exist.** `ideas.md:162-164` asks to *"investigate
  **TurboQuant** methods to accelerate similarity searches and retrievals from the card embedding
  vector database"*, and it is recorded nowhere. Meanwhile `DESIGN_CARD_POOL.md:184` specifies
  `retrieve_topk(query(board, belief), legal_pool)` with `k = 64..256` **per decision** and names no
  ANN method, no quantisation scheme, no recall bound and no rebuild cadence. Rank 1 because the
  clock is rank 1 (`NORTH_STAR.md` §1a). Four constraints the index must satisfy, from
  [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §2.2: **filtered** ANN, because legality is a rule of Magic and
  cannot become approximate; a **recall number** against the exact scorer plus the TV distance
  between exact and retrieved policies, because dropped candidates are the ones nearest the
  decision boundary; **quantisation validated against the residual-norm diagnostic**, not only
  against recall, because the same vectors carry the generalisation claim; and a **rebuild cadence**,
  because `v_card` moves every update.
- **Frozen board cross-attention** — encode the board once per phase and have every reasoning
  pass cross-attend to it without re-encoding. Also from the destroyed doc. On the DGX this is
  not an optimisation, it is a requirement; it is the Tier A / Tier B split in
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md).
- **Rethink compute penalty**, so the model learns the optimal stopping point rather than being
  given a fixed pass count. Exactly the right instinct — the reward pays for thinking, and the
  model learns when deeper thought is worth it.
- **Puzzle-ladder levels 3 and 4** from `progression_playbook.md`: stack interaction (responding,
  end-of-turn timing, combat tricks) and second-order thinking (playing around sweepers, bluff
  attacks, baiting counterspells). Only levels 1 and 2 exist. Levels 3 and 4 are unreachable
  until the engine has real priority.
  - **`H12`: concept-tag every puzzle so its cards can be hot-swapped across sets.**
    `progression_playbook.md:62-69`, not carried into `METRICS.md` §10's PZL rebuild. A puzzle
    tagged with the *concept* it tests rather than the cards it uses is the tied-rank-1 goal
    expressed as a test corpus: it is how you check that a never-seen card built from practised
    primitives is played competently. Cheap, and it has to happen before the corpus is authored,
    not after.
- **Deck-space evolution to find niche decks** (`ideas.md`). **Promoted 2026-09-10 by D14: this is
  now on the path, not parked.** Niche-deck strength is part of rank 1, so the mechanism for
  finding niche decks is too. Original note follows: an elite pool of niche decks,
  periodic re-evaluation, mutation, under-confidence sampling, a novelty reward, robustness
  testing by perturbing one card, and `R_final = R(D) + λ·Robustness(D)` with **λ annealed from
  high to low** so that early training punishes sharp minima and late training goes looking for
  them. This is the mechanism for the stated goal of being good at weird decks.
  **Correction, 2026-09-10: D14 promoted deck-space evolution, not every mechanism in that
  sentence.** Three of them were subsequently refused with reasons in
  [`DESIGN_DRAFTER.md`](DESIGN_DRAFTER.md) §9, and this entry used to contradict that file.
  The refusals stand: the **annealed λ** is a hand-authored schedule on a reward term, which
  `NORTH_STAR.md` §3 refuses, and it is replaced by the curator's learned knob distribution; the
  **sharp-minimum-seeking optimiser** confuses deck-space sharpness with weight-space sharpness and
  would select for fragility, and is replaced by `DFT-13 deck_sharpness` as a measured coordinate;
  a **novelty term in any reward** is what uniform random maximises, and is replaced by
  conditioning on a measured statistic. What is genuinely on the path from that sentence: the elite
  pool (the capped archive), the single-card-swap mutation, and the leave-one-out robustness sweep
  (`DESIGN_TEACHER.md:376`, which quotes you). **Still parked and not yet answered:** the archive
  refresh. Your `ideas.md:3` asks to revisit niche decks and *"re-evaluate whether they are still
  viable, better or worse than when it was first tested"*; `lambda_ret` re-evaluates the *student's
  retention*, which is a different object, so an archived deck's stored score still ages against a
  league that has moved. See [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §5.1.
- **`H13`: the Chaos Test catalogue you wrote and nobody carried forward.** `EFFECT_SYSTEM_MANDATES.md`
  names four engine stress scenarios: an illegal target discovered mid-resolution, zero and negative
  values, empty pools, and circular dependencies. None of them appears in `METRICS.md` or in
  [`TRAINING_REVIEW_PROTOCOL.md`](TRAINING_REVIEW_PROTOCOL.md). They are four concrete tests, already
  specified, that cost nothing to adopt and belong under the `EC` engine-correctness gate.

#### Serves ranks 2 and 3

- **Information-set Monte Carlo tree search** with determinization. Explicitly parked in
  `tasklist.md`. Blocked on make/unmake in the engine — see
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §5. **Two mechanisms you wrote down for it were never
  recorded until now, and both are load-bearing:**
  - **`L9a`: fix the opponent prediction for the whole simulation.** `ideas.md:52`: *"keep this
    opponent prediction fixed for the remainder of the simulation... avoid risking to have to
    re-run the opponent prediction NN"*. This is what makes ISMCTS affordable at all on this
    hardware. It is also what creates the strategy-fusion problem in the open question below, so
    the two must be answered together.
  - **`L9b`: punish the prediction head by severity, not by accuracy.** `ideas.md:55`: *"scale
    based on severity of wrongful predictions, based on the value-function analysis of how severe
    the wrongness was"*. This is `L4` again, in the search loop instead of the loss. **The same
    idea appears three times in your notes from three directions and had been recorded zero times.**
- **KV cache of board analysis across an action sequence.** Same idea as the Tier A cache.
- **Synthetic board-state dataset for pre-training the board encoder.**
- **`C23`: the four untaken options from the deleted `RL_ARCHITECTURE.md`'s efficiency ladder**
  (§8, `:189-193`): zone-local dense attention with inter-zone traffic via summary tokens, top-K
  learned-focus attention, low-rank factorised attention, and incremental belief updates along an
  MCTS path. Only the fifth, hierarchical pooling of large zones, survived into
  [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md). They are the latency ladder and the clock is rank 1,
  so they should be priced rather than forgotten.
- **`A26`: inference-time candidate re-ranking.** `notes.txt:163,165` proposed iterating the top-k
  base actions, building complete candidates, and scoring each with a **final Q-value head**.
  [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) commits to a single autoregressive decode with
  no re-ranking stage; §4.5's per-plan-step critic is a **training-time** critic, not an
  inference-time re-ranker. That is probably the right call on the clock, but no document says it
  is a call, so it reads as an oversight.

#### Product goals beyond the King Goal

- **Stockfish-style top-3 move suggestion** with a move line, so a human can set up a position
  and ask what is best. Also for drafting, both from empty and completing a partial deck.
- **Teacher by vector search** — build decks card by card via a matchup analyser emitting a query
  vector, then vector search against the card embedding pool, with matchup history and a
  diversity bonus to avoid rock-paper-scissors cycles. Every proposed matchup validated by the
  engine, illegal proposals penalised.
  **No longer parked as a mechanism: it is on the path and it is already built into three designs.**
  `score(c|s) = q(s).k(c)` at `DESIGN_TEACHER.md` §4.3:506 **is** this idea, because the argmax of
  an inner product over a set is nearest-neighbour search under that inner product. What remains
  parked is only the **index** that makes it sublinear, which is `L8` above. See
  [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §2. The illegal-proposal penalty was refused with a reason at
  `DESIGN_TEACHER.md` §8: legality is a rule of Magic, so it is a hard mask, not a reward term.
- **"Invent new cards in the gaps"** (owner, 2026-09-10). Parked as a **generative** problem: it
  needs a decoder from a query vector back into a typed ability tree, plus the compiler run in
  reverse, and it emits cards no engine has been tested against. **The measurement half is free and
  should be taken now:** `gap(s) = ||q(s) - k(c*)||` for the retrieved argmax `c*` is computable
  the day the pointer head exists, needs no decoder, and is the honest definition of "the pool has
  no card for what I want here". Logged per pick it is a coverage map of the card pool against what
  the drafter actually asks for.
- **Teacher reward by matchup win-rate delta** — reward the teacher when the student's win rate
  improves a lot over a matchup, so it prioritises scenarios where there is room to grow. Plus
  mirror-matchup mastery: fifty games from each side, and if the student only wins from one side
  the matchup is broken and worth teaching.
- **Deck analysis and suggestion for human players.**
- **"Hail Mary" logic** — in desperate positions, shift from maximising expected value to
  maximising the probability of drawing a specific out. Note this is genuinely at odds with a
  pure expected-value critic and needs a distributional value head or an explicit risk parameter
  to express at all.

#### Abandoned, do not revive

- Card recognition from photos and video, YouTube frame scraping, OCR, the image vector database,
  the local-LLM agent harness. All were in `attic/`, deleted 2026-11-05 (`git show dbd6e9d:attic/`).
  Off the King Goal.
  *Clarification 2026-10-24:* that harness was an LM-Studio coding assistant. It is unrelated to
  the LLM benchmark the owner approved on 2026-10-24 as rank-1 instrumentation
  ([`DESIGN_BENCHMARK.md`](DESIGN_BENCHMARK.md)); only its public-leaderboard half is parked, below.

### Parked, with the reason

**NeMo-RL (`nvcr.io/nvidia/nemo-rl`).** NVIDIA's RL toolkit, multi-arch on NGC. Parked rather than adopted:
it is shaped around LLM post-training (GRPO/DPO over HuggingFace models with vLLM rollouts), and this
project's rollout is a Magic rules engine with a command zone and four-player boards, not token generation.
The ladder is served by the environment and by batching inference across concurrent games, not by adopting
someone else's trainer. **Would unpark if:** the rollout ever becomes a generic vectorised env and the
bottleneck is the trainer rather than the simulator.

**Moving the project into the NGC container now.** Parked with a dated trigger rather than rejected. The
usual argument for it is false here (the pip wheel has 475 `sm_120` cubins and zero PTX, so there is no
PTX JIT to avoid; the container's own arch list stops at `sm_120` too). **Would unpark when:** the first
training number intended for publication or cross-month comparison is about to be produced, at which point
the job moves into the container pinned **by digest** and the digest is recorded beside the run. Detail in
[`HARDWARE_DGX_SPARK.md`](HARDWARE_DGX_SPARK.md).

**Generative card invention.** Already parked under D18; restated here only because the Spark session
confirmed the demand-ranked worklist half is cheap and the generative half is not.

**The public LLM leaderboard (parked 2026-10-24).** Owner decision: build the benchmark core now as
instrumentation; park the product. Release only when every gate holds: the priority and full-stack
rung has landed; the engine-error rate is below an agreed bound on a model-driven soak; engine,
pool and harness hashes are frozen per season; the W&B key in history is revoked; a private split
exists outside the public repo.

### Corrections owed to the docs

Contradictions found in the 2026-09-10 notes audit. These are not decisions; they are files that
disagree with a decision already taken.

| # | where | what is wrong | what it should say |
|---|---|---|---|
| **2** | `docs/card_embedding_architecture_sketch.png` (committed in `000e37c`) and `MTG_bot/mtg_token_encoding.md` | The only two owner artefacts cited by **no** document. The sketch specifies a 2346-d card vector with three channels beside the numeric one: an **NLP encoding of the rules text**, **17Lands meta-information**, and a **card-art autoencoder**. `DESIGN_CARD_POOL.md` builds `v_card` without any of them and never says why | one paragraph each in `DESIGN_CARD_POOL.md`, adopted or refused, in the style of that file's own Tarmogoyf overrule. Proposed refusals with real reasons, not "we killed OCR", are drafted in [`OWNER_IDEAS.md`](OWNER_IDEAS.md) §4.2 |
| **3** | [`METRICS.md`](METRICS.md) `DFT-5` | It tests land count *"against a declared heuristic"*, i.e. **conformity**. `thought_checkpoint.md:24` asked whether the model discovers the 40/60 ratio **independently**, which is the opposite epistemics. `DFT-5` is correct as a pre-flight gate and cannot answer the owner's question | keep `DFT-5` as the gate, add one cheap row that reports the land-ratio distribution against generation index **with the target curve out of the loss**. See `OWNER_IDEAS.md` §5.2 |
| **5** | [`DESIGN_ACTION_SPACE.md`](DESIGN_ACTION_SPACE.md) §4.3 | §4.3 gives **every executed plan step its own advantage**. The deleted `RL_ARCHITECTURE.md` §4.4 proposed the opposite, a reward only at the **end of the phase sequence**, *"to evaluate the Global State Change of an entire turn's worth of sequencing rather than individual taps or casts"*. The live design is better argued, but no document records that the owner's version was considered | one paragraph naming the alternative and the reason it was not taken. This is exactly the shape of reasoning `db5e024` destroyed |

### Open questions needing your decision

These are forks, not tasks. See the report that accompanied this audit.

1. **Full-game BPTT or K=256 truncated?** Memory says it is affordable either way; the question
   is whether the 10× serial cost buys anything, and that is measurable.
2. **v0.5 at 150M or straight to v1 at 392M?** Throughput scales inversely with size.
3. **`L5`: the worst-case-opponent trap.** Your question, `ideas.md:14-15`, verbatim, because it
   has never been answered anywhere: *"How do we avoid that the model predicts the opponent to have
   the worst case possible deck, and that we then play against that strategy, in scenarios where
   playing optimally against the hardest possible opponent-state combination results in exposing us
   to some of the also likely, but less consequential opponent-state combinations? Is this learned
   implicitly in win-rate and rewards, or do we need to handle that we dont expose us to scenario
   2,3,4 by playing optimally aginst scenario 1, if they are all somewhat equally likely?"*
   It is the difference between a maximin policy and a Bayes-optimal policy under the belief, and
   determinized search is known to produce exactly this pathology. **The honest answer is that it is
   learned implicitly only if the belief is calibrated and the search averages over it correctly,
   and both of those are parked.** Note also that `L4`'s impact weighting pushes the opposite way,
   toward paranoia, so `L4`, `L5` and `L9a` have to be reasoned about together and not adopted one
   at a time. Whoever writes the belief-and-search design answers this before shipping it.
