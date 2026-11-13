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
| **Package decks** (2026-11-12, docs/PLAN_CEILING.md §14.3): a deck holds 8 copies of its package's consumers (4 when its pair holds one) and 8 copies of other producers, the rest filled as a coherent deck; a package is kept only when a colour pair holds a consumer and 8 producer copies (a consumer that produces, and a basic at 12, count); the pair is the one holding the most consumers, then the most producer copies; consumers and producers are drawn uniformly | `tools/selfplay/packages.py` `CONSUMER_COPIES`, `PRODUCER_COPIES`, `derive`, `build` | Chosen so that a player sees a consumer in 93% of games (16 cards of 60 by their ninth turn, an 18-turn game), not measured to be best; they set how much of a deck is the package and which packages exist at all. Remove when decks come from the drafter fitted on a pilot that plays synergies (§14.4 "Later"), or when the Teacher sets a package's density from measured skill headroom (§9.1, §14.1) |
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
| **r28's guard: stop the run at 1.80 mulligan declarations per game (a 10-update mean), or at a 50-update heuristic win rate 0.05 under the first 50 updates'** (2026-11-12, KNOWLEDGE 199 §3) | `tools/selfplay/guard.py`, unit `mtg-r28-guard` | A safety rail on r27's runaway, not a learning signal: the network never sees it. Ends with r28; drop it once the mulligan's learning holds without it (R1 met to the read at 400). |
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

- **What closing B-102 and B-103 (B-106, gate R5-14) left open** (2026-11-12, closed in 6f020b8).
  The trigger axis `TriggeredAbility.once_per_event` (and `DelayedTrigger`'s; CR 603.2c) closed
  them: absent, a trigger fires once per occurrence its event matches; True, once per event. A
  creature put onto the battlefield attacking gets no DECLARE_ATTACKERS row (CR 508.4).
  - The binder groups an event's occurrences only for a declaration (its DECLARE_ATTACKERS rows
    share a group) and a combat damage step (its DAMAGE rows to one recipient, gathering the
    dealers `source` names). A once-per-event trigger on any other event kind refuses to bind
    (`binding._check_trigger`; a granted one, never bound, is refused when it triggers). None
    compiles today; the first would be M20 Woodland Champion ("one or more tokens you control
    enter"), KHM Elvish Warmaster and M19 Desecrated Tomb.
  - Within those two kinds the grouping is fixed, and the IR cannot yet say otherwise: "attacks a
    planeswalker you control with one or more creatures" (WAR Oath of Kaya) and "you attack a
    player with one or more" (ZNR Akiri) need one trigger per attacked object, and "one or more
    creatures you control are dealt damage" needs the recipients gathered. A flagged trigger of
    that shape would bind and fire per declaration or per recipient, so a mapper must not flag it
    (MAPPER_GUIDE: needs-atom). None compiles.
  - The IR refuses the flag where it changes nothing (`ability_tree.gathers_occurrences`, gate
    round 4): a self or attached subject, damage that is not only combat damage, no dealer named.
    For `combat=None` ("one or more ... deal damage", combat or not) that is a scope limit, not a
    no-op: the flag would gather the combat rows. Such a card is needs-atom (none compiles).
  - A dealer trigger with no recipient ("whenever this creature deals damage") split by trample
    or several blockers still fires per DAMAGE row, not once per step (none compiled).
- **A pack cannot respond to a combat trigger** (2026-11-12): the combat op's `respond` steps run
  when the step has priority with an empty stack, after the attack triggers resolved. So "an
  attacker leaves while Tide Skimmer's / Makeshift Battalion's / Mangara's trigger waits" is
  pinned by `MTG_bot/core/test_executor_trigger_timing.py` (binder.hold), not by a pack, and
  Mangara's G3 mutant that only S5 tells apart (below, Gates) has no pack to kill it. A
  `"hold": true` on the combat op's declare step would give packs that window.

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
- **A triggered ability's per-slot designation: what is left** (2026-11-13; the designation itself
  is `binding.TriggerBinder._designate_slots`, as spells and activations designate).
  - A target whose legal set reads the player designated beside it ("exile target creature target
    opponent controls") raises: the slots are made independently, so its population would be
    empty. Needs the player designated first and the dependent slot made with it bound. No card
    of the 19 sets prints it; the spell lane has the same limit silently (the spell is uncastable).
  - The engine's `target:` ask of a multi-slot trigger does not say which slot it fills or what
    was picked so far: the rig sets `AskContext.slot`, `picked` and `targeted` only for the
    router's own `pick:` asks of spells and activations (AGENTS §10). A features change, with the
    network's owner.
  - The class not yet mapped: M10 Capricious Efreet (also a random pick among the designated),
    KHM Halvar, God of Battle, M20 Loaming Shaman (also "any number of target cards").
- **A player's keywords are not in the observation** (2026-11-13). Hexproof and protection on a
  player (Leyline of Sanctity, Veil of Summer, Runed Halo) change the opponent's target menus,
  which the engine computes, but `tools/selfplay/features.py` encodes keywords per card only, so
  the network sees the Leyline on the battlefield, not "you have hexproof" (a resolved Veil leaves
  no permanent behind). A features change, with the network's owner.

### Triggers, events and the journal

- **An event-filter qualifier is read without the layers brought up to date** (2026-11-12, gate
  round 6 m4). `TriggerBinder._queue` runs `layers.recompute()` before it reads an intervening
  "if" (CR 603.10: the effects that exist right after the event), but `_match_node` reads the
  event's filters as they stand. Since R6-2 the event qualifiers are in those filters (Tide
  Skimmer's "two or more creatures with flying", Makeshift Battalion's "at least two other
  creatures attack"), so a continuous effect that changed with the event (a flyer granted or lost
  in the same op) can be misread. Recompute before matching an event whose node holds a qualifier
  that reads characteristics, or once per drained batch.
- **A reflexive trigger cannot read the target of the ability that created it** (2026-11-12, gate
  round 6 m1). `fire_reflexive` carries its resolution's bindings without `target`, so the
  reflexive trigger's own targets are its own (CR 603.12); IKO Back for More's "Return target
  creature card ... When you do, it fights up to one target creature you don't control" needs
  "it", the creator's target, in a register of its own (a distinct binding name), not in
  `target`. Unparsed; build it with the card.
- **A state trigger triggers again while it waits** (2026-11-12, found reading Nine Lives'
  rulings). CR 603.8: "When there are four or more page counters on this artifact" (Mazemind
  Tome), "nine or more incarnation counters" (Nine Lives) trigger once and not again until the
  ability has left the stack ("Once the first triggered ability is on the stack, it won't trigger
  again, even if more ... counters are put onto it"). They compile as CounterPlacedEvent
  triggers, so every further counter placed while the first waits queues another one (it does
  nothing: the permanent is already exiled). Fix with a state-trigger encoding, or a guard keyed
  on the waiting instance.

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
- **The trigger lane reads CR 113.6m its own way** (2026-11-12, found with the activation-zone
  fix): `binding.functions_from_graveyard` files a trigger whose effect moves its own card out of
  a graveyard as graveyard-only, while the activation lane reads the same rule in
  `legality.activation_zone`. It skips 113.6m's "unless its trigger condition ... specifies that
  the object is put into that zone", so three dies triggers that do it are bound in the graveyard
  instead of looking back from the battlefield (CR 603.10a): M20 Cavalier of Gales, Cavalier of
  Thorns, Immortal Phoenix. Its IS_SOURCE test also counts "another" (FNot). No game difference
  is known (the dies row is matched by the graveyard binding, with the controller from last-known
  information); fold the two readings into one classifier when the trigger lane is free.
- **A created token's ability record is keyed by its name alone** (2026-11-06): `_v_create_token`
  (verbs.py ~1340) registers the binder record under `token_oracle_id(spec.name)` once per game, so
  two different token specs sharing a name (two different "Spirit" tokens) would both get the first
  one's triggered/static abilities. Not live: in the M21 and M20 verified pools only Pirate, Treasure
  and Ajani's Pridemate tokens carry abilities, one definition each. Fix before a pool has a clash:
  hash the spec's abilities into the id.

### Effects, zones and replacements

- **"As this enters" runs only CHOOSE_NAME** (2026-11-12, gate round 4, e6f9358): an EtBState
  `effect` is run inside the zone-change bookkeeping (`Executor.run_as_enters`, CR 614.1c), and any
  verb but Runed Halo's CHOOSE_NAME raises NotImplementedError there. It goes when a card that needs
  another (Sutured Ghoul, Devouring Hellion, Rescuer Sphinx) is mapped with its own tests.
- **A move from a hand asks its cards as a discard** (2026-11-12): MOVE_ZONE `from` HAND takes the
  discard lane (`verbs._v_move_zone`, `_discard_picks`), whose ask is `discard:<seat>:...`, so
  Cavalier of Gales's "put two cards from your hand on top of your library" reaches a bench seat
  as "choose what to discard" (protocol.py's prompt for the kind). The cards and their order are
  right; the label is not. Name the ask by its destination, or give the move its own kind.
- **Cards a controller picks from a look at another player's library or hand raise as they go
  into that library** (2026-11-12, ontology gate round 5, m4; `verbs._library_order`,
  `_looked_at`): a tripwire. CR 401.4 has the owner arrange cards put into their library together,
  but a card's own "in any order" can tell its controller to: 10E Agonizing Memories (unparsed),
  "Look at target player's hand and choose two cards from it. Put them on top of that player's
  library in any order." No compiled card in the 19 sets does it, so the engine raises rather
  than guess who orders. When one compiles: ask its controller, with its tests.
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
- **The top-n lane of MOVE_ZONE reads the destination's player's library** (2026-11-12, found
  with the SHUFFLE fix; latent: no compiled tree in the 19 sets takes the lane):
  `verbs._v_move_zone`'s "top n of a library into a hand" lane takes the cards from
  `zone_owner(ctx, dest_ir, owner=ctx.controller)`'s library, so an OWNER or ANY destination reads
  the ability controller's library, and a selector over another player's library is ignored.
  The library is the selector zone's player, and its cards go to their owner's hand (CR 108.3,
  400.3). Left for the agent changing MOVE_ZONE (the `arrange` role), with a test that fails first.
- **A Conditional after a step that made two or more tokens judges nothing**
  (`executor._conditional_subject` takes the result register only when it holds one object): no
  tree has such a step today; "if they ..." over several tokens would need its own reading.
- **B-112 [fixer 3, 2026-10-30, review wave 4 residue] CR 111.8 (a token that has left the
  battlefield can't change zones) is not enforced.** W4-4 runs state-based actions before
  triggers, and keeps a token that a queued firing names in the world as its last-known
  information until that firing resolves, so a trigger that moves "it" could still move such a
  token, as before W4-4.
- **Starlight Snare's "doesn't untap during its controller's untap step" blocks every untap of
  the creature** (FDN round 1, 2026-11-06; CR 502.3: only the untap step). Check the verified
  "next untap step" cards too (Frost Breath M21, Frost Lynx M20); it matters only when an untap
  effect is in play.
- **Damage to a permanent that left the battlefield during resolution** is still marked on the
  card (round-3 verification, 2026-11-06: Sorin, Imperious Bloodlord's sacrificed Vampire took 3
  in the graveyard, CR 608.2b; that mapping is gone, the reflexive target is now chosen after the
  sacrifice, but the marking is not fixed).
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
    "target player" offering every player (V21); Teferi's Ageless Insight's draw-step
    exception across the other players' turns; and, since 2026-11-12, Brash Taunter's trigger
    asking which opponent it targets (before, the dealer pre-bind of `binding._put` stood as the
    target: the damage source's controller, unasked).
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
- **A printed "target opponent" read without a TARGET selector still takes a trigger's
  pre-bind** (2026-11-12): `binding._put` binds the dealer of a DAMAGE firing, or the dead
  creature of a DIES firing, for an effect that reads a designated player and prints no TARGET
  slot. That serves the "that player" anaphora (TARGET_PLAYER, D18, Massacre Wurm), but a
  TARGET_OPPONENT read is always a printed target: with several opponents its controller must be
  asked (CR 603.3d). No compiled tree in the 19 sets has one; lift the pre-bind for
  TARGET_OPPONENT when one appears.
- **Multiplayer combat**: `selectors.defending_players` reads the engine's one defending player.
  With several (CR 506.2a) it must be resolved per attacking creature (CR 508.5a) from
  `Executor.attacked`, and kept for a creature removed from combat (CR 508.5, second sentence;
  `_remove_from_combat` drops the entry).

### Rules not modelled

- **No copy effects and no layer dependencies** (the 2026-09-10 audit's list for the pre-rebuild
  engine, still true of this one): `Verb.COPY` has no handler in `verbs.HANDLERS`, so no copy
  effect runs (Sublime Epiphany's COPY mode is never offered), and the layer system applies
  effects in timestamp order with no dependency pass (CR 613.8; `layers.py`). Layer 2 has one:
  an Aura's "You control enchanted creature" applies after what changes the Aura's control
  (`Executor._recompute_control`, 2026-11-12). Timestamps are approximate too: a static's P/T
  entry for an object it newly covers (a creature entering, or one a stolen anthem now reaches)
  is stamped when it is covered, not with the static's timestamp (CR 613.7a). Only a "set P/T"
  static over other objects could tell; the three that compile (Kinetic Augur, Ironroot Warlord,
  Enigma Drake) set their own power.
- **Not modelled, because no card in the pools needs it** (B-74 residue; the postcombat main phase
  landed 2026-11-06, 46c7288): a trigger at the beginning of a second
  main phase (the frozen `Phase` has no member for it; the three Sanctums' "first main phase"
  fires once, in the first main phase, CR 505.1a), additional main phases (Relentless Assault,
  10E), and CR 505.4's Saga lore counters (precombat main phase only).

### To triage

- **The heuristic activates only a planeswalker's first ability row** (2026-11-12, KNOWLEDGE 201 §5).
  `heuristic.py` `_act` never uses Garruk, Savage Herald's -2, and if it did it would judge both
  target slots of an activation by the whole card. A weaker training and evaluation baseline, not
  a rules fault.
- **The G1 probe raises `GameOver: player:0` on M21 Sanctum of Calm Waters** (2026-11-12, KNOWLEDGE
  201 §5), identically before and after wave 1. The card is verified; its next re-verification
  needs the probe fixed.
- **The journal is not a record of what players know** (2026-11-12, KNOWLEDGE/2026-11-12/197).
  SCRY journals how many cards were scried, not which went where (`verbs.py` `_v_scry`); REVEAL
  has no zone role and `_look` reads only the library, so "target opponent reveals their hand"
  (Duress, Kitesail Freebooter, Thought Distortion) journals the target's whole LIBRARY as revealed
  and opens a look window on it; a graveyard-only search's REVEAL(1) journals the library's top
  card. No gameplay effect found (Duress's choice reads the hand through its own selector), and no
  network input reads these rows (features show only offered and scried cards). Anything that
  rebuilds knowledge from the journal is wrong: `search.reshuffle_unknown` did, and was replaced by
  a whole-library shuffle. Fix: a zone role on REVEAL, and SCRY rows that name the cards.
- **Teferi, Master of Time's -3 duration (suspected, check the ruling)** (2026-11-12, 197): "phases
  out until your next turn" compiles as plain PHASE_OUT, and the pack
  `teferi_master_of_time_phased_out_waits_for_its_controller.json` pins classic phasing (it phases
  in at its controller's next untap step). With his loyalty abilities usable on any player's turn,
  the two readings can differ; check the Comprehensive Rules and the card's rulings.

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

- **"N damage to that creature's controller": two answers, one of them stale** (2026-11-13,
  analysis only; a decision for the next gate round).
  - MAPPER_GUIDE ("has no encoding yet ... Mark such a card needs-atom (M20 Chandra's Outrage)")
    and Chandra's Outrage's needs-atom note reject a TARGET selector over the PLAYER zone (a slot
    of its own), a referent Selector in `target` (the creature itself), ALL over Zone(PLAYER,
    TARGET_PLAYER) (a phantom player slot) and DEAL_DAMAGE `recipient` (raises). None of these is
    the verified M20 Chandra, Flame's Fury's −2: `DEAL_DAMAGE(target=Selector(ALL, QUnbounded,
    FAtom(CONTROLLER_IS, who=Selector(referent="target")), zones=(Zone(PLAYER, ANY),)))`.
  - That form opens no designation (AGENTS §10), never names TARGET_PLAYER (D18), and reuses the
    canonical "its controller" referent Selector as CONTROLLER_IS's `who`, as filters already read
    "that creature's controller" (M21 Feline Sovereign, `who=Selector(referent="event")`). By the
    identity law it is the one encoding for the wording: the guide's line is stale.
  - One engine fault first: `selectors.controller_matches` reads a referent's current controller
    (`controller_of`), not the one it last had (CR 608.2h), which `role_players` reads
    (`last_known_controller`). Probed 2026-11-13: "destroy target artifact; 3 damage to that
    artifact's controller" on a stolen artifact hits its owner. Exact today for damage dealt while
    the object is still there (Chandra's two, Searing Barrage, Ravaging Blaze, Synchronized
    Spellcraft) or on the stack (ELD Bonecrusher Giant's "that spell's controller"); wrong for
    10E Cryoclasm, ORI Smash to Smithereens and THB Impending Doom.
  - Then: the guide's line, and the cards: Chandra's Outrage (M20, M11, M12, M14), Bonecrusher
    Giant (referent "event"), Searing Barrage, Ravaging Blaze, Cryoclasm, Smash to Smithereens,
    Impending Doom, Synchronized Spellcraft (X).
- **"Whenever you discard a card" has two encodings in waiting** (2026-11-13, analysis only).
  - M20 Bag of Holding (verified) triggers on `ZoneChangeEvent(HAND YOU -> GRAVEYARD YOU)`; M20
    Glint-Horn Buccaneer's needs-atom note asks for a discard event (B-48).
  - CR 701.8a defines the action as the move, but the two are not the same set. A discard need
    not end in the graveyard: a replacement redirects it (Leyline of the Void M20/M11 and Dryad
    Militant FDN exile it; Darksteel Colossus M10/FDN, Progenitus FDN, Nexus of Fate M19 and Legacy
    Weapon 10E shuffle themselves in; madness, none in the 19 sets, exiles it), and a card's text
    may put a card from a hand into a graveyard without discarding it (none in the 19 sets).
  - So Glint-Horn's note is right: one wording, one encoding (identity law), the keyword action's
    own event as SacrificeEvent is CR 701.21's: a `DiscardEvent(actor, filter)` with B-48's one
    discard encoding. Type-1: the next ontology round.
  - Per card: Glint-Horn stays needs-atom (with Leyline of the Void compiled it would deal no
    damage for a redirected discard: weaker than printed). Bag of Holding keeps its stamp: none of
    the redirecting cards compiles in the pools, and its effect ("exile that card from your
    graveyard") cannot see a redirected card anyway; it refolds when the event lands. Fell Specter,
    Liliana's Caress, Megrim, Rielle, Tinybones and Waste Not wait for the same event.
- **DOM Shalai, Voice of Plenty: "You, planeswalkers you control, and other creatures you control
  have hexproof."** (2026-11-13). The player and a filtered set of permanents in one static:
  `layers._new_static` refuses two populations in one record, and no filter joins "you" with type
  tests (TYPE_EQ is False on a player). Templates_b16 covers "You have hexproof." and "You and
  permanents you control ..."; this one needs a decision on its shape.
- **D19: a MOVE_ZONE into a library with no position means two things** (2026-11-12, ontology
  gate round 5, m5; ATOM_DIVERGENCES D19): "put it on the bottom of your library" (M21 Epitaph
  Golem) and "shuffle it into its owner's library" (M20 Cavalier of Gales: the move, then a
  SHUFFLE) both write `Zone(LIBRARY, ...)` with no `position`, and `verbs._bottom_put` takes it as
  the bottom. Both play right today (one card each). A several-card shuffle-into move would ask
  its owner an order (`verbs._arrange`) the shuffle then discards; `orders_a_library` refuses
  `arrange` with no position. None exists in the 19 sets. Fold: "on the bottom" writes BOTTOM,
  and the executor arranges only an explicit end.
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
- **B-75 [2026-10-29, branch `engine/phasing`] Phasing (CR 702.26) is implemented as a status.**
  - **Fixed 2026-11-12 (1cac720): Teferi, Timeless Voyager's "Until the end of your next
    turn, they can't phase in."** (divergence D16, closed). The compiler's built-in
    `_phase_in_prevention_effect` emits `PREVENT_EFFECT(condition=IS_RESULT,
    event=PhasingEvent(phased_in=True, filter=IS_RESULT), duration=DurationUntilEndOfNextTurn)`:
    - "they" are the creatures the [−8]'s PHASE_OUT phased out: `FAtomPred.IS_RESULT` reads the
      `result` register, and `verbs._v_prevent` locks that set into the record as it resolves.
      Gate round 4 fixes: IS_RESULT stands only in an Atom role that takes a Filter and cannot
      take a referent Selector (`ability_tree._is_result_role`; anywhere else, such as a
      selector's filter, `Selector(referent="result")` is the one encoding), and a read with no
      register raises;
    - `Executor._phasing_step` asks `ReplacementRegistry.prevents_phase_in` (CR 702.26a) before
      each phase-in, and an Aura attached to a creature that stays out stays out with it (702.26g);
    - the record re-tags to `Eot` as its controller's next turn begins, so that turn's cleanup ends
      it (CR 514.2); the layer registry does the same, and the P/T ledger refuses the duration (no
      carrier).
    Packs `tools/scenarios/cards/M21/teferi_timeless_voyager_*.json` (`_cant_phase_in`, moved from
    `known_bugs/`; `_only_they_cant_phase_in`; `_phases_in_after_your_next_turn`), tests
    `test_executor_phasing.py::TestCantPhaseIn`.
  - No carrier: the phasing keyword (702.26a's phase-out half), PHASE_IN (702.26c by an effect),
    a directly phased-out Aura (702.26i), "for as long as" durations tracking a phased-out
    permanent (702.26f; `DurationUntilLeaves` must not end on phasing, R5-1), and a trigger on
    phasing (the journal has no phasing row; the binder refuses a `PhasingEvent` trigger).
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
- **B-80 [fixer A, m21-fidelity] "Can attack as though it didn't have defender"** (CR 609.4,
  702.3b).
  - **Fixed 2026-11-12 (1cac720) for Drowsing Tyrannodon**, option (a): the static compiles
    to `StaticAbility(condition=<you control a creature with power 4 or greater>,
    ATTACK_POLICY(cards=self, scope=AS_NO_DEFENDER))`. `layers._new_static` registers it as an
    `"attack_policy"` record, and `legality.attack_blocked_reason` lifts defender's restriction
    only while `attack_policy_applies`; the Tyrannodon keeps defender, so Portcullis Vine may
    sacrifice it. A resolving ability's "can attack this turn as though ..." registers a resolved
    record (`verbs._v_attack_policy`; test `test_executor_combat.py::TestAttackPolicy`). Packs
    `tyrannodon_still_has_defender_for_portcullis_vine` (the review pack named here was in neither
    the repository nor its history; rebuilt from this entry, it fails on the old tree) and
    `drowsing_tyrannodon_without_a_big_creature_cannot_attack`.
  - Remaining: the five other cards with the clause leave it unparsed (Novice Knight and Arcades,
    the Strategist M19, Roving Keep ELD, Skyclave Sentinel and Skyclave Squid ZNR). The component
    covers their static and "this turn" shapes; no template emits it yet. No card in the 19 sets
    prints "can block as though".
- **B-81 [fixer A, m21-fidelity item 5] Lossy rows judged (2026-10-29).** Significance per
  AGENTS §11 (alters legal options or state outcomes).
  - Significant, not fixed: See the Truth's "If this spell was cast from anywhere other than your
    hand, put each of those cards into your hand instead" runs as an extra step that returns one
    card, not all three. It is unreachable until something lets you cast it from elsewhere
    (Chandra, Flame's Catalyst's -2, R5). Fix: the conditional "instead" arm (as Life Goes On),
    replacing the one-and-rest split, once a pack can cast it from the graveyard. Re-checked on
    18afa85 (2026-10-30): tree unchanged, still unreachable.
  - Not significant, kept: Cultivate's REVEAL count (REVEAL is a recorded no-op);
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
  - Furious Rise's "You may play that card until you exile another card with this enchantment."
    is suppressed at assembly (`compiler._is_result_anaphoric_cast_permission`, KNOWN-GAP "play
    permission"); by the 2026-10-02 decision (KNOWLEDGE/2026-10-02/08) the card stays
    engine-supported, so in castable and compiled games its end-step trigger only exiles your top
    card (weaker than printed; not in the verified pool). Checked 2026-11-12: the trigger, its
    intervening "if" and the exile are right; what is missing needs the lane:
    - a permission to play a card from exile, cast it or play it as a land (CR 305.1): no verb (R5-2
      PERMIT_CAST was never implemented), no executor state, no menu row (`executor.menu` offers
      land drops and casts from hand, and activated abilities, only);
    - its window, which ends when the next card is exiled with Furious Rise (CR 607.2a): an
      event-ended duration with no carrier. R5-8 proposed `DurationUntilEndOfNextTurn` as the
      approximation (divergence D15, never added); that duration now exists (Teferi, Timeless
      Voyager, 1cac720).
    Known-bug pack `tools/scenarios/known_bugs/furious_rise_play_the_exiled_card.json` (fails
    today: the exiled card is not offered on your next turn).
- **B-113 [2026-11-12] REVEAL `until` (ontology R5-13's redesign of FIRST_MATCH) plays
  Transmogrify (1cac720); the rest of the family does not compile.**
  - Transmogrify: `REVEAL(controller=<that creature's controller>, count=1, until=TYPE_EQ
    Creature)` reveals cards one at a time from the top until the first creature card (the
    `result`; every revealed card is the look window; `count` is the number of revealed cards
    that pass `until`, so `until=FAnd(())` and a QUnbounded `count` are refused), then
    `EachPlayer(ref=<that creature's controller>, Seq(MOVE_ZONE result -> battlefield YOU,
    SHUFFLE library YOU))`. "That creature's controller" is a referent-"target" Selector, read by
    last known information (CR 608.2h).
    Before, the tree read TARGET_PLAYER, so the menu asked a second, player target the card does
    not print (KNOWLEDGE/2026-11-05/184 "two-target spells"), and it searched only the library's
    top card: a noncreature on top put nothing onto the battlefield. Packs
    `transmogrify_reveals_until_a_creature`, `transmogrify_own_creature_reveals_from_your_library`,
    `transmogrify`.
  - 2026-11-13: "Reveal cards from the top of your library until you reveal a creature card. Put
    that card into your hand and the rest on the bottom of your library in a random order."
    compiles (templates_b16), and the REST of "the rest" reads the reveal's window and matches
    (verbs._look writes the partition anchors one_of_window / one_of_picks): M20 Vivien, Nature's
    Avenger and FDN Spinner of Souls are mapped (records, packs in `tools/scenarios/mapped/`).
    ORI Evolutionary Leap's tail compiles, its cost frame ("{G}, Sacrifice a creature:") does not.
  - Still unparsed: "onto the battlefield" tails (M15 Jalira, THB Dreamshaper Shaman, IKO Lukka's
    "creature card with greater mana value"), Consuming Aberration (the match goes to the
    graveyard with the rest), Mass Polymorph ("that many"), Abundance (replaces a draw).
- **B-114 [2026-11-12, gate round 4] Massacre Wurm's "that player" is TARGET_PLAYER (divergence
  D18): fold it to `Selector(referent="event")`, as Gloom Sower writes "that creature's
  controller".** "Whenever a creature an opponent controls dies, that player loses 2 life." compiles
  to `LOSE_LIFE(controller=TARGET_PLAYER)`; it plays right only because the trigger lane binds the
  dying creature and `selectors.players_for_ref` reads its last known controller. The rule (
  `docs/MAPPER_GUIDE.md`): "its controller" and "that player" are a referent Selector, never
  TARGET_PLAYER, which is a target (CR 115.1). Scheduled, not done: one compiler template
  (`B2b-massacre-wurm`), one golden (M21; the FDN printing compiles from the same template), then
  re-verify both cards (their verified trees change, so both leave the verified pool until then).
  The conformance test `tools/audit/test_ontology_conformance.py::
  test_a_designated_player_is_a_printed_target` lists Massacre Wurm as its one exception
  (`ontology_conformance.DESIGNATED_PLAYER_EXCEPTIONS`); the fold removes it there.
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
  Embereth Skyblazer): their "When you do" / "If you do" halves need templates. A "When you do"
  sentence that parses becomes a reflexive trigger by the compiler's merge
  (`_merge_if_do_continuation`, 2026-11-12); only Tolarian Kraken's has a template. 19 more
  reflexive sentences in the 19 sets are unparsed (census in the 2026-11-12 trigger-lane report:
  Faebloom Trick's clause parses on its own, so a "When you do, <clause>" frame would compile
  it; the rest need their antecedent, a pronoun reading or "this way").
- **"If you don't, Y" would merge as an unconditional sibling** (2026-11-12, found fixing gate
  round 6 m3). `compiler._CONTINUATION_PREFIXES` holds "If you do", so "If you don't, ..." and
  "If you don't control/put ..." are continuations, but the merge dispatch gates only
  `_DO_GATES` ("If you do,", "If you do so,", "When you do,", "When you do so,"); any other
  continuation is appended as a step of its own, Y done whether or not X was. 15 sentences of
  the 19 sets start so, all unparsed but M20 Risen Reef's, which its record maps. With the first
  template, gate "If you don't," as `Conditional(FNot(MAY_DONE), Y)` and drop "If you do" from
  the prefixes for `_DO_GATES`, as "When you do" was.
- **The trigger-timing check counts; it cannot see a qualifier joined into an intervening "if"**
  (2026-11-12, gate round 6 M2). `ontology_conformance.check_trigger_timing` compares trigger
  conditions with intervening "if"s and reflexive triggers with reflexive sentences, both ways.
  A card printing both an event qualifier and an intervening "if" could put the qualifier into
  the "if"'s condition and keep the counts equal; no sentence of the 19 sets has both
  (`reports/trigger_timing_2026-11-12/census.txt`, third section: 0). With the first such card,
  read the condition's conjuncts against the "if" clause.
- **A reflexive trigger reads a departed object's last known information only within the op it
  left in** (2026-11-12): `fire_reflexive` carries its resolution's bindings, but
  `quantity.last_known` answers for an object that left the battlefield only in that op or for
  the ability's source. Surtland Flinger's "damage equal to the sacrificed creature's power" (KHM,
  unparsed) would read the card in the graveyard, not the creature as sacrificed (CR 608.2h).
  None compiles; fix it with the first such card.
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

- **See the Truth's "cast from anywhere other than your hand" branch compiles wrong** (2026-11-13,
  verification wave 1b: the verifier left the clause unjudged, the coordinator read the tree).
  - Printed: "If this spell was cast from anywhere other than your hand, put each of those cards
    into your hand instead."
  - The tree runs the normal outcome first (one card to hand, the rest to the bottom), then a
    Conditional moving a count-1 CHOOSE over `result` to hand. So it gives one card, not three, and
    never "instead".
  - Unreachable today: no compiled card casts it from elsewhere. M20 Chandra, Acolyte of Flame's −2
    would, but it needs an atom.
  - The fix is a compiler one: an "instead" clause on a look chooses between the two outcomes,
    Conditional(not from hand, all looked-at cards to hand, else the normal pair). Test it with a
    pack once the runner can cast from a zone other than the hand (the Archfiend's Vessel item
    needs the same op).
  - See the Truth stays unverified until then; its main branch was judged OK.
- **Six M20 mapped records judged WRONG by blind G2** (2026-11-12, verification wave 1, KNOWLEDGE 201;
  verdicts `runs/verify_wave1/verdicts/B/`). They stay out of the verified pool:
  - **Battalion Foot Soldier.** "Search your library for any number of cards named Battalion Foot
    Soldier": the engine takes every copy and never asks how many.
  - **Sanitarium Skeleton.** "{2}{B}: Return Sanitarium Skeleton from your graveyard to your hand":
    the ability was offered on the battlefield, where it does nothing, and refused from the
    graveyard. Engine fixed 2026-11-12 (`legality.activation_zone`, CR 113.6m; packs
    `tools/scenarios/mapped/M20/sanitarium_skeleton_*`): the record, unchanged, goes back to
    blind G2 (its G1 trace changed; its mapping notes still describe the old engine).
  - **Sorin, Imperious Bloodlord's +1.** Re-mapped 2026-11-12 as a reflexive trigger (CR 603.12),
    its target chosen as it goes on the stack after the sacrifice; goes back to G2. Its packs,
    `tools/scenarios/mapped/M20/sorin_imperious_bloodlord_*`, run in the suite on the record.
    G3 (2026-11-13): its first +1's two "target->all" survivors are dead (the activation twin
    rule); `cardtool verify` passes with the wave-1b verdict `runs/verify_wave1b/verdicts/B/B01.json`.
  - **Goblin Ringleader.** "Put all Goblin cards revealed this way into your hand" is mapped as a
    one-of choice.
  - **Mu Yanling, Sky Dancer's -8.** The emblem is empty (`GET_EMBLEM {}`). It should give "Islands
    you control have '{T}: Draw a card.'"
  - **Cavalier of Flame.** "Discard any number of cards, then draw that many" discards the whole hand
    with no ask.
- **Re-verify the cards the trigger-timing fixes changed** (2026-11-12, trigger lane; tree shas
  changed, verified stamps left untouched, so each left the verified pool, the pool training runs
  deal, once a run pins this code. Verified deckable pools measured on the tree merged with main
  bc0d4606, `get_supply("verified", <set>)`: M21 269 -> 264, M20 255 -> 253, FDN 175 -> 173):
  - reflexive triggers (CR 603.12): M20 Cavalier of Night (record re-mapped). Its pack
    `cavalier_of_night_2` needs the record and runs on it from `tools/scenarios/mapped/M20/`,
    with the new `cavalier_of_night_sacrifices_with_no_opposing_creature`;
  - event qualifiers out of the condition (CR 603.4): M21 Tide Skimmer, Makeshift Battalion,
    Mazemind Tome, Nine Lives, Sanctum of All (compiler trees, their spec packs still pass in the
    suite), FDN Mazemind Tome, and M20 and FDN Brineborn Cutthroat (records re-mapped; they play
    as before, the turn cannot change while the trigger waits). Brineborn's `brineborn_cutthroat_1`
    packs need the record and run on it from `tools/scenarios/mapped/M20/` and `mapped/FDN/`;
  - after re-verification the `mapped/<SET>/` packs above go to `cards/<SET>/`.
- **Verification wave 1's eight G3-blocked cards** (2026-11-12, after the G3 equivalence rules;
  `reports/g3_equivalence_2026-11-12/`). Verdicts in `runs/verify_wave1/verdicts/`.
  - M20 Gods Willing: G3 clear; `cardtool verify` passes with its verdict as it stands.
  - M21 Garruk, Savage Herald: its "you may" mutant is dead; its duration mutant is killed by
    `packs/A06_garruk_grant_ends_with_the_turn.json`, which goes through a verifier first.
  - M20 Cavalier of Gales: its scry mutant is killed by
    `packs/B08_cavalier_dies_you_scry_your_library.json`. The stolen Cavalier shuffled the
    thief's library; fixed 2026-11-12 (`verbs._v_shuffle`), pack
    `tools/scenarios/mapped/M20/cavalier_of_gales_stolen_shuffles_its_owners_library.json`.
  - M20 Blightbeetle: G3 clear. Stolen, it read its old controller; fixed 2026-11-12 (the records
    of a permanent's own abilities follow its controller, `Executor._recompute_control`), pack
    `tools/scenarios/mapped/M20/blightbeetle_stolen_reads_its_new_controller.json`.
  - Both trees are unchanged and go back to verification with their packs.
  - M21 Tolarian Kraken: the reflexive trigger landed (2026-11-12, trigger lane); its two
    "target->all" survivors now differ from the card where a pack can show it, and
    `reports/g3_equivalence_2026-11-13/packs/A05_*.json` does (Gates, below).
    M21 Mangara: its Oracle "if" is an intervening "if" and is right to be read again; the
    re-read now counts a departed attacker by its last attack (its ruling). One survivor is live
    only in S5 (Gates, below). M21 Archfiend's Vessel and Teferi's Ageless Insight: G3 survivors no
    2-seat M21 pack can kill (Gates, "G3 survivors no 2-seat same-set pack can kill").
  - FDN Battlesong Berserker and Searslicer Goblin lost their documented equivalent mutants;
    neither has a current verdict.
- **M21 Runed Halo, Garruk, Savage Herald and Rookie Mistake can go to G1 and G2** (2026-11-12,
  deaba91). They were the "probe limits" cards of KNOWLEDGE/2026-10-30/177, and Runed Halo caused
  window 2's four castable-pool crashes (192 §7.6); both crashes are fixed in deaba91:
  - NAME_CHOSEN (deals 900,114, 900,195, 900,283): "As this enchantment enters, choose a card
    name" compiled as an enters trigger, so the Halo's protection was live with no name while the
    trigger waited on the stack, and pricing a player target in an act menu raised. It is now the
    entering state (`EtBState.effect`, CR 614.1c, 614.12a), and the name leaves with the object
    (CR 400.7). Only Runed Halo's tree bytes changed.
  - TARGET_PLAYER (deal 900,085): the Halo named Vito, Thorn of the Dusk Rose, whose "target
    opponent" then had no legal choice; the trigger went on the stack with an empty designation.
    CR 603.3d now removes it (`binding._designate`), and a trigger's designated player is checked
    again as it resolves (CR 608.2b, `TriggerBinder.resolve`).
  - The G1 probe tried "another target" pairs the engine refuses and probed the Halo on the
    battlefield without its choice (`tools/cards/probe.py`, fixed): all three now probe with no
    engine error. In the act window Garruk's -2 is offered with its two targets asked slot by
    slot, and it and Rookie Mistake resolve right, also with a target gone.
  - What remains: a second person's G2 review and `cardtool verify`. Spec packs: `runed_halo_*`,
    `vito_target_opponent_*`, `garruk_savage_herald_minus_two_*`, `rookie_mistake_act_window`,
    `rookie_mistake_one_target_gone`.
- **Re-verify M21 Basri Ket, M21 Tide Skimmer and FDN Ancestor Dragon** (2026-11-12, B-103's
  fix). Their once-per-declaration triggers gained `once_per_event` (Basri Ket's -2 and Tide
  Skimmer from the compiler, Ancestor Dragon in its record's `ir`), so their tree shas changed
  and all three left the verified pool (M21 262 -> 260, FDN 175 -> 174), the pool training
  runs deal, once a run pins this code. Basri Ket and Tide Skimmer play as before in the other
  pools (the compiler's tree, once per declaration), and their spec packs pass in the suite.
  Ancestor Dragon does not: its record is not applied while unverified, so in the other pools it
  plays the compiler's tree, which has no attack trigger (weaker than printed), and its spec
  pack waits in `tools/scenarios/known_bugs/ancestor_dragon_gains_once_per_declaration.json`
  (it passes with `cardtool runpack FDN <pack>`). G3 now mutates the flag, critical both ways
  (dropped: "trigger count: once per event -> each occurrence"; added where it gathers: "each
  occurrence -> once per event"); each card's existing spec pack kills its mutant (checked). M21
  Subira (verified, unchanged) gets the second mutant on its delayed trigger, which none of its
  six verified packs kills; `cards/M21/subira_draws_for_each_small_creature_that_connects.json`
  kills it, for its next verification. FDN Battlesong Berserker's record (not verified) got the
  same flag.
- **Re-verify M21 Garruk's Harbinger, M20 Drawn from Dreams and M20 Brightwood Tracker**
  (2026-11-12, MOVE_ZONE `arrange`, ontology gate round 5). Their "in a random order" move
  gained `arrange` RANDOM (Garruk's Harbinger from the compiler's B5b-rest-bottom-random, the two
  M20 cards in their records' `ir`), so their tree shas changed and they left the verified pool
  (measured against main acfb1926: M21 270 -> 269, M20 257 -> 255, FDN 175). Without the role
  the engine asks the owner the order (CR 401.4). Garruk's Harbinger plays as before in the other
  pools (its packs pass; its bottom order is random now, which none of them pins). The M20
  records are not applied while unverified, so in the other pools Brightwood Tracker plays the
  compiler's tree (a vanilla creature) and Drawn from Dreams none (no spell); their spec packs
  wait in
  `tools/scenarios/known_bugs/{brightwood_tracker,drawn_from_dreams}_rest_to_bottom_in_a_random_order.json`
  (both pass against the records' trees, asking no order). G3 mutates the role both ways,
  critical ("library order: random -> the owner's" / "the owner's -> random"), and keeps each
  card's "zone LIBRARY->GRAVEYARD"; all three G1 traces kill the first. Re-probe Anticipate,
  Stormwing Entity and Track Down too (their traces show `arrange` asks, now asked top first),
  and write the two M20 records through `cardtool try --write`.
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

- **G3 survivors no 2-seat same-set pack can kill** (2026-11-12, verification wave 1's G3 pass;
  evidence in `reports/g3_equivalence_2026-11-12/`). The equivalent classes are now dead-role
  rules in `gates.mutants`, each proven in `tools/cards/test_gates.py`: twin TARGET selectors in a
  resolution-time Choose of a spell (Gods Willing), in a trigger outside any Choose
  (Battlesong Berserker) and in an activated ability outside any Choose (Sorin, Imperious
  Bloodlord's first +1, 2026-11-13: `activate()` now refuses an empty designation for a slot that
  needs a target before any cost is paid, CR 602.2b, 601.2c, as the cast lane does; it used to
  pay and then raise "TARGET selector has no designation" at resolution, after an ALL twin had
  already acted); an end-step trigger whose condition requires TURN_OF YOU (Searslicer
  Goblin); a printed static PREVENT_EFFECT's atom `condition` (Blightbeetle); a granted
  damage-policy static's "you may" (Garruk, Savage Herald's -7). Over the 701 verified cards
  only M20 Maniacal Rage and Wolfrider's Saddle lose mutants (two non-critical "widen filter"
  each, survivors in their records); the activation rule changes none of the 709 verified on
  2026-11-13. What stays:
  - **Live only where no pack reaches.** M21 Archfiend's Vessel ("or you cast it from your
    graveyard": the effect-cast lane can, `stack.cast_card`, but no card in the 19 sets casts a
    creature card from a graveyard and the runner casts from hand only) and M21 Teferi's Ageless
    Insight (its condition's `who` matters only with a second draw replacement firing on the turn
    draw, none in the 19 sets, or with three seats, where the mutant raises). Both are proven live
    in `proof_vessel_teferi.py`, so no rule. Options: a pack op that casts through
    `stack.cast_card` from any zone (kills the Vessel's two), a 3-seat pack world, or a recorded
    decision to accept the survivor.
  - **Live, and now the card is right.** M21 Tolarian Kraken's twins sit in its reflexive
    trigger's Choose: with no legal target the {1} is paid, then the card's reflexive trigger is
    removed as it goes on the stack (CR 603.3d) and the mutant's waits there (test_gates
    `..._reflexive_trigger_choice_stays_live`). It resolves asking nothing: its "you may" narrows
    to skip, since the option left with a TARGET has no legal one (`query.optional_offer`), so no
    pack can choose the tap option. What a pack sees is the trigger itself:
    `reports/g3_equivalence_2026-11-13/packs/A05_kraken_reflexive_no_target_leaves_nothing_to_counter.json`
    (the opponent's Sublime Epiphany finds no ability of the Kraken to counter) kills both, for
    a verifier; or one more pass of priority resolves it instead of ending the main phase. M21
    Mangara's inner-filter mutant differs only when an attacked planeswalker changes control while
    the trigger waits (S5: the card draws nothing, as its intervening "if" says; the mutant draws),
    which no pack can stage (Combat, "A pack cannot respond to a combat trigger"); its event-filter
    mutant is equivalent (`proof_mangara.py`) but its shape is that one card's, so no rule.
  - A dead role is still in the tree bytes the network encodes; only G2 sees a wrong value there.
  - Separately, `cardtool.py mutate --out` writes nothing (`cmd_mutate` never reads `args.out`).
- **G3 has no operator for a qualifier re-read on resolution** (2026-11-12, gate round 6 m8). R6-2
  moved event qualifiers out of the condition; a mutant moving one back (Tide Skimmer's "two or
  more creatures with flying" re-read as the trigger resolves) differs only when the qualifier
  stops holding while the trigger waits, which no pack can stage ("A pack cannot respond to a
  combat trigger", Combat). Add the operator as non-critical, or add the combat op's response
  window first and make it critical.
- **Probe (G1) blind spots** (verifiers: M20 2026-11-05, FDN round 1 and round 3 2026-11-06).
  - Clauses left NOT_EXERCISED: granted abilities are never activated, loyalty never reaches an
    ultimate, the land drop is always a Plains, the library holds 6 cards, no planeswalker is on
    the board, and the "Aura" probe card is a 2/2 creature.
  - A 0/0 X creature dies at setup (Wildwood Scourge); stimuli never end the turn, so "until end
    of turn" on a triggered effect goes unexercised; the opponent's attack stimulus never asks
    for blocks; an Equipment's attachment is invisible without a static; pools emptying at end
    of turn hide payments.
  - An animated land shows only +HASTE (no P/T or type) in G1 (Wakeroot Elemental).
  - A scry or look at the wrong player's library is invisible (2026-11-12, M20 Cavalier of
    Gales): the snapshot keeps each library's size only (`probe.py` `snapshot`), an ask shows its
    kind without its player (`probe.py:121`), and SCRY writes no journal row. Its G3 survivor
    needed a pack answering "bottom" and pinning both libraries.
- **Regenerate the wave-1 packets whose G1 trace changed** (2026-11-12): combat stimuli now show
  the asks a combat makes (a trigger's target, a may-offer, a mode), which the pack runner's
  combat op used to answer unseen with their first word; packet A15 (Feline Sovereign) showed a
  target destroyed that nobody was shown to choose, although the engine had asked. A verdict read
  from an old trace fails `cardtool verify` ("the reviewer read a different trace"). Of wave 1's
  cards only A15 changed (16 of 1,125 M21/M20/FDN traces, draft records applied). 14 of the 688
  verified cards' traces changed too (Battle-Rattle Shaman and Solemn Simulacrum in M21 and FDN,
  Dire Fleet Warmonger, Elder Gargaroth, Garruk's Harbinger, Goblin Arsonist, Jeskai Elder,
  Pitchburn Devils, Siege Striker, Spined Megalodon, Steadfast Sentry, Tomebound Lich); their
  records' `probe_sha` only matters to a re-run of `cardtool verify`.
  - The same day the engine began asking the order of cards put into a library together
    (MOVE_ZONE `arrange`, CR 401.4, 701.22a) and stopped letting a damage trigger's dealer stand
    in for a printed target: packets A07 (See the Truth), B05 (Goblin Ringleader), B07
    (Anticipate) and B08 (Cavalier of Gales) now show `arrange` asks, and the verified M21 Brash
    Taunter (TARGETING rows), Stormwing Entity and Track Down (scry order asks) trace
    differently too.
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
- **Distillation from playout labels (parked by the owner, 2026-11-09; DECISIONS D21; taken up
  again as PLAN_CEILING's gate B under D22, pre-registered in KNOWLEDGE/2026-11-12/196 with the
  search's own targets: the epoch is chosen by play, not held-out fit, and a placebo arm is the
  control).** E3 failed:
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
  state.pkl (the trainer process owns it). Measured at r27's resume after window 2 (198 §2): no
  shock overall (`kl` 0.0037-0.0086 over updates 166-169).
- **The mulligan's forgetting** (2026-11-12, KNOWLEDGE/2026-11-12/198 §4). Learning the rest of
  the game moves the shared network so that the mulligan reads the hand less: one update without
  any mulligan row raised its logit on decent hands by +0.2 to +0.4 (lowered it on the worst).
  The stratified steps let the mulligan's own gradient answer in every step, and at r27's
  update 165 it wins (net -0.3 per update), but at v1's rates its pull is weak. r28's R1 and R1b
  (199) test whether that is enough. If not, candidates, each to be registered before use: a KL
  anchor on mulligan decisions to a reference policy, the search deciding the mulligan, or
  advantages with less variance at the first decision (the value knows little there: early-game
  explained variance 0.07).
- **The simulator and the distilled networks were trained on length-stratum steps** (198 §5).
  Window 1's `sim.pt` (192 §5) and every distillation before f83f4db took each optimizer step on
  one length stratum. Retrain the simulator on `ppo.steps` before its next registered use and
  compare its held-out NLL with window 1's.
- **The search treats copies of a card as different moves** (2026-11-12, KNOWLEDGE/2026-11-12/197).
  The engine lists one option per card object, so two Forests in hand are two candidates whose
  results differ only by noise. Gumbel halving spends simulations on copies, "moves changed" is
  inflated (65% of the changed moves in window 2's audit were swaps to a copy), and a target can
  move mass between copies (noise the network cannot fit: equal tokens give equal logits).
  `search.option_classes` keys the options the encoding cannot tell apart; the audit already
  compares distinct moves. Using it in the search's candidates (one per class, the class's
  probability summed) changes the searcher, so measure it first: a paired n = 16 point with and
  without it on the same deals, before any run's targets use it.
- **The audit's simulator worlds share the learner's torch generator with the search's**
  (2026-11-12, 197): with `--search-worlds sim`, turning `--search-audit` on changes which worlds
  the search draws (not their distribution). Matters only for a sim-world audit (195 §4's
  follow-up); then give the audit's requests a generator of their own.
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
- **A delayed or reflexive trigger on the stack encodes as ability index -1** (2026-11-12, gate
  round 6 m7; `tools/selfplay/features.py` `_ability_index`): its node is no printed ability of
  its source, so Tolarian Kraken's reflexive tap-or-untap looks like any other trigger of the
  Kraken that its record does not hold. Encode the printed ability whose effect holds the node
  at the next observation-schema change.
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
