# Design: real priority (the priority rung)

Status: **approved by the owner 2026-11-10, red-teamed the same day (§10); stage 1 in progress.**
The owner on approving: "Yes all of this sounds correct, especially the proper priority sounds
like something that will teach real game mechanics, and one point more where it can learn
something real, and get good too". The owner on asking for it,
2026-11-10: "make sure the game works as Magic. It is important to get it up to speed in terms of
the basics. Having the skeleton set up so we train the network for realistic games from the
beginning, seems important. Not having the instant mini-rounds or what it is, is bad."

This replaces BACKLOG B-110 ("abilities never sit on the stack") and the "priority rung" the
scaffolds point to. Code facts come from two surveys of 2026-11-10 (the engine, and the self-play
and agent code) and a red-team of the first draft; the ones the design rests on were re-read
(`stack.py:140-150,1227-1239`, `legality.py:1606-1628,1955`, `__init__.py:1686-1709`,
`games.py:132-134,1426-1546`, `query.py:294-303`, `router.py:409-426`, `verbs.py:2384-2394`).
Line numbers are as of c861b37.

## 0. Why

A player acts only in their own two main phases (`_play_turns`, `games.py:1504,1540`). Besides
that there are two one-round windows: counterspells against a spell (`_response_window`, opened
inside `cast`) and one-target damage or pump instants after blockers (`open_combat_window`).
Activated abilities resolve inside `activate` (`legality.py:1955`) and triggers inside `_settle`,
so no ability is ever on the stack. Note 190 §4.1 counts the cost: about 30% of M21's nonland
cards play weaker than printed (Eliminate, Heroic Intervention, Opt, Frost Breath, Unsubstantiate
among them), and a network trained here learns that instants are sorceries. Commander, the far
goal, is a game of instant-speed interaction.

Defects that go with it: the combat window asks seats in fixed `player_order`, so on seat 1's
turn seat 0 is asked first (`stack.py:1015`, against CR 117.3a and its own docstring); the counter
window never gives the caster priority back (CR 117.3c); the heuristic answers both windows
without judgement (190 §1.13); and activated abilities are offered only from the battlefield
(`query.py:301`, `router.py:415`), so an ability used from a hand or a graveyard (M21's Waker of
Waves discards itself for its effect) is never offered at all.

## 1. The rules to implement (two players)

- **Priority** (CR 117). The active player receives priority at the start of each step and phase
  that has it, after turn-based actions and after the triggers of its start are on the stack
  (117.3a), and after any spell or ability resolves (117.3b). A player who casts, activates or
  plays a land keeps priority (117.3c). Passing gives it to the other player (117.3d). When both
  pass in succession the top object resolves, or with an empty stack the step ends (117.4).
  Each time a player would receive priority, state-based actions are checked and waiting
  triggers go on the stack, repeated until neither happens (117.5); putting a trigger on the
  stack can itself trigger.
- **Steps** (CR 500-514): untap (no priority), upkeep, draw, first main, beginning of combat,
  declare attackers, declare blockers, combat damage, end of combat, second main, end step,
  cleanup. With no attackers, declare blockers and combat damage are skipped (508.8). When a
  creature has first or double strike there are two damage steps; the second takes creatures that
  dealt no damage in the first plus those with double strike now (510.4). Cleanup has no priority
  unless state-based actions or triggers happen in it, and then it repeats (514.3a). Mana empties
  as each step and phase ends (CR 500).
- **Timing.** Sorcery speed: own turn, a main phase, empty stack (sorceries, creatures and other
  permanents, "activate only as a sorcery", loyalty abilities, playing a land). Instant speed:
  whenever the player has priority (instants, flash, other activated abilities, from whatever zone
  the ability works in).
- **Casting and activating** (CR 601.2, 602.2) is one action: announce, choose modes, X and
  targets, pay, and the object is on the stack. Triggers that fire while it is being cast or
  activated (a sacrificed creature's dies trigger, a "becomes the target" trigger) wait and go on
  the stack above it. Mana abilities do not use the stack (605.3b) and may be activated whenever
  the player has priority or is paying (605.3a).
- **Triggers** (CR 603.3): put on the stack the next time a player would receive priority, the
  active player's first (APNAP), each player ordering their own; modes and targets are chosen
  then, and a trigger with no legal target is removed (603.3d).
- **Resolution** (CR 608): targets are checked again and the effect runs; LIFO (CR 405). A card
  that changed zones is a new object (CR 400.7): a spell or ability whose target left and came
  back no longer has that target. A countered object leaves the stack (701.6a).

## 2. What changes in the engine

### 2.1 Principles

1. **Priority points are clean boundaries owned by the turn loop**, not callbacks inside an
   engine call. A fork (`tools/search/fork.py`) is a deepcopy between engine calls, so only then
   can the search branch on a response and a game stop and resume at any priority point. Choices
   made while casting or resolving (targets, modes, X, payment, discard) stay provider asks inside
   the call, as today.
2. **The engine settles only where a player would receive priority** (CR 117.5), and at the
   cleanup check (514.3a). Today every top-level op settles at its end, and costs are paid op by
   op: "a sacrificed creature's dies trigger resolves mid-payment" (`legality.py:1623-1625`). If
   those settles put triggers on the stack, a cost's triggers would land under the spell. Casting
   and activating, the payment's taps, sacrifices and discards included, become one atomic op.
3. **A forced pass is not a decision.** A player with no legal action but passing is not asked.
   That is the rules, not a shortcut. The engine never filters legal actions by usefulness.
4. **Hidden information stays hidden.** A forced pass and a chosen pass are recorded identically
   everywhere: journal, events, features. No menu enters the journal. Today the windows' WINDOW
   rows journal the asked seat's castable vocabulary and exist only for a seat that holds an
   answer (BACKLOG, the WINDOW rows' item); they go.
5. **Delete, do not keep alongside.** `_response_window`, `open_combat_window` and their vocabs
   (about 380 lines of `stack.py`) and the hook in `combat_blocks` go.
6. **Seeded games stay reproducible; trajectories change once.** Engine randomness is keyed on
   `_op_seq` (`__init__.py:548-553`). The fixed-trajectory pins
   (`test_executor_games.py:2332-2335,2454`; `test_executor_player_loss.py:295,314-316`) are
   re-pinned deliberately, once, when the engine lands.

### 2.2 The turn as a state machine, owned by the Executor

`Executor.phase` today has UPKEEP, FIRST_MAIN, COMBAT, SECOND_MAIN and END_TURN
(`__init__.py:380`); the steps inside them exist only as code (`begin_turn` 1831-1878,
`combat_attacks` 1982-2018, `combat_blocks` 2020-2070, `end_turn` 2725-2754). It becomes a step
clock with one value per step of §1. `begin_turn`, `combat_attacks`, `combat_blocks` and
`end_turn` split into per-step turn-based actions. Every step gets a journal marker, so "at the
beginning of the end step" and "at the beginning of combat" triggers fire on their own markers.
The transient flags (`declaring`, `_draw_step_open`, `_combat_wave_open`, `_closing_turn`) become
step state, and so do the damage participants (`_combat_damage` snapshots both waves at its start,
`__init__.py:2410-2419`; with priority between the waves the second is decided when it begins,
double strike read again). Mana pools empty at the end of every step, including upkeep and draw.

The priority state sits next to the step clock in the Executor: who holds priority, passes in
succession, whether the step's turn-based actions are done, each player's actions this step. It
is folded into `state_fingerprint`, so there is one fingerprint and one resume point; `Game` only
drives.

### 2.3 Stack objects

One typed stack object for spells, activated abilities and triggered abilities, with a handle
namespace for ability objects. Today a spell's frame is popped inside the `cast` call that pushed
it, so state that must survive between pushes lives in local variables. The object carries:

- what is on the frame today, plus the `countered` flag, which `dump()` leaves out because the
  frame "is popped as soon as the counterspell's cast returns" (`stack.py:145-150`);
- the per-op decisions pool (`stack.py:1096,1279`), the slot designations, the mode-narrowed
  target node the CR 608.2b re-check uses (`:1253`) and the designation of an ephemeral
  replacement (`:1318-1320`);
- for an ability: the ability node itself, not its index (granted abilities are addressed by a
  negative index into a live layer list, `legality.py:1845-1850`, which can shift while the
  ability waits; CR 113.7a), its source and the source's zone entry, and the clock at which it was
  put on the stack (`effect_began_clock` returns None for activated abilities "because it resolves
  inline", `returns.py:108-113`);
- for every target and for the source: the clock at which it entered its zone, so a target that
  left and came back is illegal at resolution (CR 400.7; `recheck_targets` today accepts any handle
  in the current candidate set, `stack.py:450-457`, and `departed_lki` is dropped on re-entry,
  `__init__.py:1099`). The journal already answers the question (`left_zone_since`,
  `returns.py:144`).

All of it goes into `stack.dump()` and the fingerprint, and so does the waiting-trigger queue,
unfingerprinted today (`state.py:248-270`) because every settle drains it. A countered object
leaves the stack at once (CR 701.6a); the COUNTER handler (`verbs.py:2390`) moves the card and
must remove the frame. `pending_references` (`binding.py:1440-1451`), which keeps a token alive
while a waiting trigger names it, also scans the stack, or a token named by a trigger on the stack
ceases at the next state-based check (`_cease_tokens`, `__init__.py:1360-1372`).
`STACK_KIND_EQ` ACTIVATED/TRIGGERED (`quantity.py:1702-1715`), stack target enumeration
(`legality.py:401-412`), `_v_counter_spell` (`verbs.py:2302-2394`) and `_exile_the_stack`
(`__init__.py:1777-1798`) learn about abilities. Unsubstantiate's spell half is fixed here
(BACKLOG under B-110).

### 2.4 Casting, activating and resolving

- `cast` (`stack.py:1087-1382`) becomes CR 601.2 as one atomic op: designation, pricing,
  payment (the router's pre-cast taps included, `router.py:368,389`), push, the CAST row. It
  returns with the spell on the stack; everything its casting triggered waits in the queue.
- A new `resolve_top` does CR 608 for the top object: today's `stack.py:1238-1381` for a spell,
  the effect half of `activate` for an ability, `_fire`'s resolution half for a trigger.
- Non-mana `activate` (`legality.py:1804-1963`) does CR 602.2 the same way and pushes. Mana
  abilities stay immediate.
- `cast_card` (effect casts, `stack.py:1419-1593`) pushes and returns instead of resolving inside
  the resolution that cast it.

### 2.5 Triggers

`_settle` (`__init__.py:1686-1709`) today matches events, checks state-based actions and fires
every trigger to resolution, at the end of every op. It becomes the CR 117.5 step, called only by
the priority loop and the cleanup check: repeat {state-based actions; put waiting triggers on the
stack} until neither happens. Putting triggers on the stack: APNAP; a new ask for a player to order
their own simultaneous triggers (which fixes BACKLOG's "resolve oldest first, never asked"); modes
and targets chosen now; removed when a required target is missing (603.3d). `_fire`
(`binding.py:1511-1628`) keeps only resolution: the intervening "if", the CR 608.2b target
re-check (missing for triggers today, BACKLOG ~205-209) and the effect. The pre-binds written for
resolution time (`binding.py:1555-1622`) move to the moment the trigger goes on the stack. The
200-fire tripwire in `fire_all` is redefined per priority point.

### 2.6 The priority loop

```
step loop (state in the Executor: step, holder, passes, tba_done, actions this step):
    if not tba_done: turn-based actions of the step (untap, draw, declare attackers, ...); tba_done = True
    if the step has priority:
        loop:
            settle (CR 117.5): state-based actions and triggers onto the stack, until neither happens
            menu = legal actions of holder now                                       (2.7)
            action = ask holder if menu has more than PASS, else PASS (recorded the same way)
            if action is not PASS: perform it atomically; passes = 0; holder keeps priority
            elif passes + 1 == 2:                                                     (CR 117.4)
                if stack empty: end the step (cleanup: repeat while 514.3a applies)
                resolve_top(); passes = 0; holder = active player                   (CR 117.3b)
            else: passes += 1; holder = the other player
```

A game stopped at any priority point resumes there, with the turn-based actions not redone and
the holder and passes as they were. This replaces `stop_after`'s four boundaries and the
`skip_next_acts` / `skip_to_blocks` flags (`games.py:1442-1536`). The act cap becomes a cap on
one player's actions per step (registered scaffold, `games.py:132-134`, BACKLOG "10 acts per main
phase"; its row is rewritten, not added). The stall rule stays at the top of each turn
(`games.py:1356-1400`), and so does the turn cap.

### 2.7 The menu and payment

One menu for any player at any priority point, built by the router's `_act_menu`
(`router.py:235-311`) with the timing gates keyed on who holds priority. It scans activated
abilities in every zone where they work (hand and graveyard included, §0). The `stack_empty`
parameter of `ability_playable` (default True, `legality.py:1090`, never passed by
`legal_activations`, `query.py:307`, nor by the router, `router.py:368,407`) is deleted: the gate
reads `executor.stack.frames`, as `spell_window_reason` and `land_playable` already do.

**Payment folds in the costly mana sources.** The menu offers costly mana abilities (Treasure,
pay-life sources) as rows that fill the pool (`router.py:245-251`), because automatic payment taps
only free sources (registered scaffold "Automatic payment"). At every priority point such a row
would be a decision of nothing for a player holding a Treasure. Instead, `plan_mana_taps` counts
every mana source when it prices a row, and the payer is asked which source pays only when there
is more than one way. Mana rows leave the menu. What this gives up, activating a mana ability for
its side effect (sacrificing a Treasure in response to its removal, CR 605.3a), is registered as a
scaffold until payment folds into the move (DESIGN_ACTION_SPACE §1.3).

**The pre-check.** A menu build takes 1.66 ms (p99 4.4 ms), 40% of a game's time in a probe of 4
random-agent games (engine survey); today there are about 2.8 builds per turn, and with about 20
priority points a turn every build would cost about seven times more. A cheap pre-check comes
first. It must be a superset of the menu (a false negative is a silent forced pass), so it is
built from the same legality functions (floating mana, costly sources, non-mana costs, hand and
graveyard abilities, instant-speed grants like Teferi's, `legality.py:1178-1197`), and the soak
of §4 asserts it against the full menu.

## 3. What changes for the players

### 3.1 The decision interface

`take_acts` (implemented by the driver: `SeatRouter.take_acts`, `router.py:204-233`;
`RandomPolicy.take_acts`, `games.py:752-795`) gives way to one decision per priority point: the
loop asks the provider, the router builds the menu, one action or PASS comes back. Two ask kinds:

- `act`: the holder may act at sorcery speed (own main phase, empty stack). Same meaning and
  menu as today, so trained networks keep what they know.
- `priority`: instant speed only (every other priority point). New. Grown, when a checkpoint
  loads (`ASK_GROWN_FROM`, `features.py:50-63`; `model.py:309-324`), from `cw`, the trained
  decision closest to it (respond now or pass), not from `act`, where PASS means "end my main
  phase" and is rarely chosen with a spell castable. The `cw` row was cloned from a heuristic that
  always cast (190 §1.13), so the grown row's pass rate is measured in stage 2 before any
  training; if it fires at the first priority point, the new heuristic's priority decisions are
  cloned first.

`counter` and `cw` leave the router's registry (`protocol.py:74`); their embedding rows stay, so
old checkpoints load. `RandomPolicy`, the engine's random driver, gets a weight for passing, or
uniform play would cast every instant at the first priority point it sees.

### 3.2 What the network must see

Missing today (self-play survey; `features.py`):

- **The step**: only "second main" is told apart, through the ask kind (`features.py:405-409`).
  New `glob_f` columns, one per step, zero weights on load.
- **Stack order**: frames are entities top first (`:455-456`), but the model has no positional
  encoding, so the network cannot tell which frame resolves next. A depth column per stack
  entity.
- **Ability objects** as stack entities: their kind, their source card and ability index, a
  pointer to the source entity, and a handle that does not collide with the source permanent in
  `ent_index` (`:498-500`).
- **What a stack object targets**: frame targets, X and modes are not encoded. A pointer from a
  frame to its targets, like the attachment pointer (`:526-528`; `model.py:106-107`).
- **Whether the other player has just passed** (passing then resolves the top or ends the step).
  Passes are public, and forced and chosen passes look the same (§2.1.4).

### 3.3 The heuristic

It is the rating anchor and the cloning teacher. Today `_act` casts the dearest spell, instants
included, and it answers both windows without judgement (190 §1.13). The priority version passes
by default and adds: hold instants and flash cards for the opponent's turn; removal on the best
attacker after attackers are declared, or at the opponent's end step; a pump on its own creature
in a fight that it then wins or survives; a counter on a spell worth countering, or one that
targets its creature; flash creatures as blockers or at the opponent's end step; mana left at the
opponent's end step spent on draw or ping abilities; activated abilities on its own turn (it
activates none today but a planeswalker's, 190 §3.3). Its Elo moves; the anchor is re-measured
against uniform random.

### 3.4 Search, the labeller and the simulator

The search forks at `act` asks and plans attacks and blocks at the pre-combat and pre-blocks
boundaries (`actor.py:115-137`; `search.py:378-411`). With the loop of §2.6 it forks at any
priority point and resumes there. `forced` (which matches only `act` answers), the resume logic
and the value leaf (which assumes the turn's first decision is the first-main menu,
`search.py:367-375`) are rewritten, and the budget of 400 decisions per simulation
(`MAX_SIM_DECISIONS`, `search.py:67`) is re-sized. Searching `priority` asks comes after the first
training run on the new game; until then the raw network answers them. The simulator uses no
turn-loop hooks; it needs a new capture and retraining.

### 3.5 The learner

Nothing assumes one actor per turn: every decision is a trajectory step keyed by game and seat
(`learner.py:615-617`). What changes:

- **Per-kind metrics** in each `iter` row: count, PASS share, entropy, KL and advantage by ask
  kind. None exist (`rig.py:104-106` counts but `play_game` exports totals only). Without them a
  policy that always passes looks healthy, and near-certain passes dilute the mean KL and entropy
  (`ppo.py:101-121`) so that `act` and attack decisions move further per update than the mean
  shows. A KL stop, when one is used, stops on the largest per-kind KL. Checked against METRICS
  §17 before adding.
- **The batch.** At gamma = lambda = 1 the outcome noise is per game, and `--steps` counts
  decisions, so more decisions per game means fewer games per update. Every `iter` row reports
  games per update, and the batch size of note 189 is re-derived per game on the new game.
- **The entropy bonus** pushes every decision toward uniform, including priority points where
  passing is right. Values are in outcome units (2p - 1), so an action costing five points of win
  probability costs 0.10, and at 0.0075 it keeps exp(-0.10 / 0.0059), about 4e-8, of passing's
  weight: the push is self-limiting. The real risk is the other way: rare priority asks carry
  little learning signal. The per-kind entropy shows both.

### 3.6 The LLM bench

The router and protocol are shared: `ENGINE_NOTES` (`view.py:52-57`), the primer
(`primer.py:57-58`) and `duel.py:121` change, and `SeatView` gains the step and the attack and
block flags (`view.py:94-154`). An LLM seat pays one API call per ask, so its clock is measured.

## 4. Tests and scenario packs

- **An auto-pass driver for the existing tests**: both players pass until the stack is empty,
  which reproduces "cast returns resolved" for the at least 143 tests that call `cast` and the at
  least 244 that drive turns. Window answers in packs already default to PASS
  (`run_scenarios.py:412-420,448-452`). It is for old tests only: with both players passing,
  nothing happens between a push and its resolution, so it cannot find the bugs priority brings.
- **The tests that can**:
  1. An interleaving soak: at each priority point a random legal action with p of about 0.3, run
     over every pack and the card soak, asserting the pre-check against the full menu (§2.7).
  2. Generated tests that remove the source, and separately the target, in response to every
     ability and every targeted spell in the pools (CR 400.7, 608.2b).
  3. Fork-resume equivalence at random priority points: fork, resume, and compare the digest and
     fingerprint with the unforked game.
  4. Hidden information: a paired-world test (same seed, the opponent's hand differs only by a
     castable instant, the opponent passes) asserting identical asks, encodings and journal for
     the observer; and the existing encoding test (`test_selfplay.py:69`) over the new columns.
  5. One test per rule of §1: priority order; the caster keeps priority; both passing resolves
     the top and returns priority to the active player; an empty stack ends the step; mana per
     step; triggers above a spell whose cost triggered them; APNAP with targets chosen on the
     stack; 603.3d; 508.8; 510.4; 514.3a.
  6. Packs for cards that gain their printed power: Eliminate on an attacker after attackers are
     declared; Heroic Intervention in response to removal; Opt at the opponent's end step; Frost
     Breath in the opponent's beginning of combat; a flash blocker; a counterspell; Tale's End on
     a triggered ability; Unsubstantiate on an artifact spell; Waker of Waves from hand; first
     strike, then a pump in the second damage step.
- **Rewritten**: about 30 window tests (`test_executor_rung1.py` 14, `test_executor_rung2.py`),
  about 50 loop and whole-game tests, 17 `take_acts` sequencing tests, the self-play and bench
  tests that pin the boundaries (`test_selfplay.py:182,200,739`; `test_router.py:367`), and the
  54 packs with window lanes or `hold_triggers` (which stands in for responding to a trigger).
- **Pre-flight**: P9 (games end by a loss) and P12 (replay) unchanged. The card-onboarding probe
  (`tools/cards/probe.py:66,226,369,416,484`) gets stimuli at the opponent's priority points, or
  it never checks instant timing (Brineborn Cutthroat's trigger on a spell cast during an
  opponent's turn, Nightpack Ambusher's end-step check).
- The 305 compiled-IR goldens are unaffected unless the IR changes.

## 5. Throughput

Today: about 52 learner decisions per game, 13.1-14.8 games/s on 18 workers (r26); 72.8 asks with
more than one option per heuristic game (NUMBERS). Workers are CPU-bound on the engine. What
scales is the number of asks, not menu builds: a player holding an instant with untapped mana is
asked at almost every priority point of both turns. Measured in stage 2, before training, with
the heuristic and with the network grown from `cw`: decisions per game by kind, games/s. If the
cost is too high, the remedy is a shortcut the rules allow ("pass until something is put on the
stack or my next turn"), offered as an option the network learns to choose, not a filter in the
engine (DESIGN_ACTION_SPACE §1.3 has the measured case for priority shortcuts). A network will not
choose it early, so the slowdown arrives with the first training run whatever happens.

## 6. Stages

Each stage lands with the suite green and games playable. r26 runs from its pinned worktree
throughout.

1. **The engine, in one stage**: the step clock and the priority state in the Executor; stack
   objects with everything of §2.3; atomic casting and activating, `resolve_top`; triggers put on
   the stack by a settle that runs only at priority points; the loop; the windows deleted;
   abilities from every zone; payment with costly sources; the act cap's row rewritten. The draft
   had two engine stages; they cannot be split, because the counter window lives inside `cast`
   and the combat window needs `cast` to resolve on the spot (`__init__.py:2040-2045`), so an
   intermediate engine would need throwaway drains. Tests: the auto-pass driver for old tests, the
   new tests of §4, the trajectories re-pinned once.
2. **The players**: router and protocol (`priority` grown from `cw`), features (§3.2), the
   heuristic (§3.3), per-kind metrics, the hidden-information tests, the bench. Throughput and the
   grown row's pass rate measured.
3. **Search and labeller** at priority points; the simulator recaptured.
4. **Card census**: which cards now play as printed (190 §4.1's table again), the probe's new
   stimuli, BACKLOG cleared of the rows this closes.
5. **Training on the new game**: a pre-registered run (TRAINING_REVIEW_PROTOCOL).

The game changes at stage 1 and the yardstick at stage 2 (a heuristic that plays instants and
abilities), so every Elo, gate and ladder before them is history, not a baseline.

## 7. Decisions for the owner (all four taken as recommended, 2026-11-10)

1. **Faithful priority in every step** (recommended; the alternative, more windows, is the
   current scaffold grown).
2. **Shortcuts only if measured necessary**, and then learnable (§5).
3. **The first network on the new game** starts from the newest version (r26's), with `priority`
   grown from `cw`; a short cloning phase from the new heuristic only if the grown row fires
   instants at the first priority point.
4. **r26 keeps running** until stage 5 is ready to launch.

## 8. Risks

1. Atomic casting: every op that settles at its end today (payment steps, the router's taps)
   must stop doing so inside a cast or activation, or cost triggers land under the spell.
2. Flipping what `_settle` means: every step, action call, pack and many tests assume triggers
   have resolved when a call returns.
3. Stack objects carrying state that lives in local variables today (§2.3), and object identity
   across zone changes, which instant-speed bounce and flicker make reachable for the first time.
4. Trigger targets chosen when put on the stack: the pre-bind logic was written for resolution.
5. The clean-boundary requirement is structural: get it wrong and responses cannot be searched.
6. A false negative in the pre-check is a silent forced pass.
7. Throughput (§5), and behaviour at the new decision points: a policy that fires instants at once
   or always passes, unseen by totals.

## 9. After this: the other basics

From note 190, for realistic games: the network sees its own deck list and what is left in its
library (§4.3, `PLAN_LEARNING.md:351`); decks with a shape instead of uniform piles (§4.5); the
card's parts carrying what its name carries today, then names masked per game in self-play
(§5.1-5.3); an unseen-card score in every ladder (§3.4).

## 10. Red-team of the first draft (2026-11-10)

A fresh agent attacked the draft against the code and the rules. All eleven findings were taken:

| # | Finding | Change |
|---|---|---|
| 1 | Costs settle op by op mid-cast; with the new settle their triggers would land under the spell (CR 601.2i, 117.5) | §2.1.2, §2.4: settle only at priority points, atomic casting and activating |
| 2 | Stage 1 could not leave games unchanged: the counter window lives inside `cast`, the combat window needs inline resolution | §6: one engine stage |
| 3 | The stack object must carry local state; granted abilities by shifting index; `effect_began_clock` None; tokens named by a trigger on the stack would cease; countered frames would linger; loop state unfingerprinted | §2.2, §2.3 |
| 4 | Object identity across zone changes (CR 400.7) not checked at resolution | §1, §2.3, §4 |
| 5 | The mana-row rule was ill-defined and a usefulness filter in disguise | §2.7: costly sources fold into payment, mana rows go, the side-effect gap registered |
| 6 | The auto-pass driver hides the bugs priority brings | §4: interleaving soak, remove-source and remove-target tests, fork-resume equivalence, probe stimuli |
| 7 | Forced and chosen passes, and the journal's WINDOW rows, could reveal a castable instant | §2.1.4, §4 |
| 8 | Per-kind KL and entropy; games per update; the entropy arithmetic was off by two (0.05 for 0.10); growing `priority` from `act` is the worst prior; ability entities need source and index | §3.1, §3.2, §3.5 |
| 9 | CR 508.8, 510.4, 514.3a and the 117.5 repetition were missing | §1, §2.2, §2.6 |
| 10 | Abilities from hand and graveyard are in no menu; `stack_empty` is never passed; the pre-check needs to be a superset | §0, §2.7 |
| 11 | What scales is asks, not menu builds; measure with the network too | §5 |

## 11. Build order of stage 1 (2026-11-10)

Baseline before the first change: `pytest MTG_bot` 5091 passed, 39 deselected, 71 subtests (54 s).
Tests call the engine outside any game loop about 1,200 times (`execute` 341, `begin_turn` 274,
`cast` 180, `apply_effect` 142, `combat_*` 98, `end_turn` 95, `advance_turn` 73, `activate`
62), and expect a call to return resolved. So the engine gets two drivers of priority, one rule:

- **Driven** (a game loop holds the executor): after every action and resolution the loop asks
  the holder; the engine never passes for a player who has a choice.
- **Undriven** (a unit test, a pack set-up, a tool): an op ends with both players passing until
  the stack is empty (the auto-pass driver of §4, built in), and `begin_turn`, `combat_step`,
  `end_turn` and `advance_turn` run the step machine with both players passing, up to the same
  boundaries as today. It never ends a step on its own.

Commits, each with the suite green; behaviour changes are rules fixes, and a test that pinned the
old behaviour is changed with a reason in the commit:

Steps 1-3 landed on 2026-11-10/11 (37d14e1, 43ad5a2, 271ba26) with no test moved: in random
games triggers now wait on the stack up to three deep. The trigger-order ask of §2.5 moves to step
5, with the other new ask kinds.

1. Stack objects: `SpellObject` becomes one typed object for spells and abilities, carrying the
   state of §2.3; `resolve_top` does a spell's resolution; `cast` and `cast_card` share it.
2. Abilities on the stack: `activate` puts the ability on the stack (payment atomic) and the
   trigger drain puts each trigger on the stack with its modes and targets before resolving it.
3. The settle of CR 117.5 (state-based actions and triggers onto the stack, repeated) and the
   undriven auto-pass; atomic casting.
4. The menu moves into the engine (`executor/menu.py`) for the router and `RandomPolicy`; abilities
   from every zone; costly mana sources folded into payment; the pre-check. Done for the router
   (2026-11-11); `RandomPolicy` and the pre-check move to step 5, where every priority point
   builds a menu. One change to §2.7: the engine picks which costly source pays, by the
   scaffold's own rule (BACKLOG "Automatic payment"), instead of asking.
5. The step machine and the driven loop; the windows deleted; `take_acts` becomes one decision per
   priority point in `RandomPolicy`, the router, the heuristic, the test drivers and the search
   (minimal: forks and resumes at priority points); packs with window lanes rewritten; the act
   cap per player per step.
6. The tests of §4 that can find priority bugs, and the trajectories re-pinned.

Step 5 goes in two commits:

- **5a, the step machine, undriven.** `Executor.phase` holds the step (UPKEEP, DRAW, FIRST_MAIN,
  COMBAT for the beginning of combat, DECLARE_ATTACKERS, DECLARE_BLOCKERS, FIRST_STRIKE_DAMAGE,
  COMBAT_DAMAGE, END_OF_COMBAT, SECOND_MAIN, END_TURN for the end step, CLEANUP; the name stays,
  `MAIN_PHASES` and every reader keep working). Priority state beside it, fingerprinted: holder,
  passes in succession, `tba_done`, actions per player this step, and the creatures that had
  first or double strike as the first damage step began (CR 510.4). `pass_priority` does CR
  117.3d-117.4: the next player, or with all passed the top object resolves and the active player
  gets priority (117.3b), or with an empty stack the step ends: mana empties (CR 500.4, every
  step), the next step begins, skipping blockers and damage with no attackers (508.8) and adding
  the first-strike step when 510.4 asks for it. `begin_turn`, `combat_attacks`, `combat_blocks`,
  `end_turn` and `advance_turn` become "both players pass until" the boundaries they stop at
  today (first main with an empty stack, attackers declared, second main, turn closed). The
  combat window stays inside the declare-blockers turn-based action until 5b.
- **5b-1, the windows deleted** (landed 2026-11-11). `cast` puts the spell on the stack and ends
  its op: outside a game loop both players then pass until the stack is empty;
  `Executor.holding_priority()` keeps it waiting so a test or pack can respond, and
  `Executor.all_pass()` lets the top object resolve once. Paying taps are atomic with what they
  pay for. Packs say `"hold": true`, `{"op": "resolve"}`, `{"op": "pass"}`, `"tap": true` and
  a combat step's `"respond": {STEP: [...]}`; 51 window packs and about 35 window tests were
  converted, a few window-only tests deleted. Until 5b-2 nobody responds in a game: the windows
  are gone and the loop still asks only in the main phases.
- **5b-2, the driven loop** (landed 2026-11-11). `_play_turns` gives priority in every step:
  `Executor.start_turn`, `pass_priority`, `acted` (CR 117.3c-d), `next_turn_seat`; the act cap
  counts per player and step; `stop_after` stops at "turn_top", "pre_attacks", "pre_blocks"
  and "priority", and a game resumes where its executor stands (the search's skip flags are
  gone). `take_priority(game, seat) -> bool` replaces `take_acts` in `RandomPolicy` (the
  engine menu, `PRIORITY_PASS_P` 0.9 away from its own main phases), the router (`act` and
  `priority` asks; a PASS-only menu is no ask), the bench protocol and the test drivers. The
  heuristic passes every `priority` ask until §3.3; `priority` grows from `cw` in old
  checkpoints; an ability waiting on the stack is encoded as its source card until §3.2.
  CR 103.8a now skips the whole draw step of the first turn (the new loop test caught it).
  Measured, heuristic against heuristic, 20 coherent M21 games, one core: 68.9 asks per game
  before (41e774c) and 145.2 after (75.7 of them `priority`), the same 15.3 turns, and 0.244
  s per game before against 0.356 after, once the payment planner stopped listing sources for
  a cost no mana can fix and shared one listing per menu (it was 0.618). Left in stage 1: the
  trigger-order ask, step 6's tests, the zone-entry clocks of §2.3 (CR 400.7) and the stack
  target enumeration of abilities (BACKLOG B-110).
- **The trigger-order ask landed 2026-11-11.** `TriggerBinder.put_waiting` puts every waiting
  trigger on the stack in APNAP order, and `_resolution_order` asks each player with two or
  more different ones which resolves next (`trigger:<seat>:<digest>`, kind `trigger`, grown
  from `other`); the options are the sources (`card:12`, a card's second trigger `card:12:2`),
  and copies of one ability from one source and one event share an option (CR 603.2d: their
  order cannot matter). The old drain order (newest batch, then APNAP, then trigger order) and
  its bookkeeping went: CR 603.3b puts everything that triggered since a player last received
  priority on the stack together. The heuristic answers with the order they triggered (the
  old fixed order) until §3.3; `decisions.in_trigger_order` does the same for unit tests that
  script every other decision. New packs `terror_of_the_peaks_3/4` (Terror of the Peaks and
  Bone Pit Brute: 8 damage with the Brute's trigger first, 4 the other way). Measured,
  heuristic against heuristic, 200 coherent M21 games: 0.4 `trigger` asks per game, 0 crashes;
  random games, 150 coherent and 150 stress: 0 crashes. Until §3.2 the network sees an option
  as its source card only, so two triggers of one card look alike to it.
- **Abilities on the stack are targets, 2026-11-11 (BACKLOG B-110 closed).** A selector over the
  stack adds each player's abilities to its spells (`stack.stack_abilities`, read by
  `selectors.enumerate_zone` and `legality._zone_handles`); an ability matches only
  STACK_KIND_EQ of its own kind (CR 113.7a: it has no characteristics); COUNTER_SPELL removes a
  countered ability from the stack and moves nothing (CR 701.6b). Unsubstantiate's target is now
  `FOr(STACK_KIND_EQ SPELL, TYPE_EQ Creature)`: any spell, never an ability (one golden, and the
  new branching registered in `reports/ontology_census_2026-11-11_b110_post_full.json`). The
  network points an ability option at its stack entity, the bench names it "the triggered
  ability of ...". The pack runner: a held step puts the waiting triggers on the stack (the
  player receives priority again, CR 117.5), a target `ability:<key>` names that card's ability
  on the stack, and a cast step's own mode and target words are no longer read twice. New packs
  `sublime_epiphany_1/2`, `unsubstantiate_1/2`.
- **Step 6, the printed-power packs of §4 item 6, 2026-11-11: all ten have a pack** (M21 card
  packs, with a new runner op `to_step` that passes to a step's priority): Eliminate on an
  attacker after attackers are declared (`eliminate_2`); Heroic Intervention in response to
  removal (`heroic_intervention_1`); Opt in the opponent's end step (`opt_1`); Frost Breath in
  the opponent's beginning of combat (`frost_breath_4`); a flash blocker (`containment_priest_4`);
  counterspells (`cancel`, `cancel_pass` and the Negate packs); a triggered ability countered
  (`sublime_epiphany_1`, Tale's End being unverified); Unsubstantiate on an artifact spell
  (`unsubstantiate_1`); Waker of Waves activated from the hand in the opponent's end step
  (`waker_of_waves_4`); first strike, then a pump in the first-strike damage step
  (`sure_strike_1`). Left of step 6: the interleaving soak, the generated remove-the-source and
  remove-the-target tests, and the per-rule tests of item 5 not yet covered.
- **Zone-entry clocks for targets (§2.3), 2026-11-11.** A card target that changed zones after
  its spell or ability went on the stack is a new object and no longer a target (CR 400.7):
  `recheck_targets` takes the object's `declared_clock` and reads the journal
  (`returns.moved_since`); the trigger recheck does the same. Packs
  `flicker_spell_target_is_a_new_object` (Shock does nothing to an Ox exiled and returned in
  response; it dealt 2 before), its control without the flicker, and
  `flicker_trigger_target_is_a_new_object` (Bone Pit Brute's +4/+0 misses the returned Ox; it
  made it 6 power before). The source half of §2.3 (an ability acting on its own source that
  left and came back) is open in BACKLOG.
- **5b, the driven loop, as planned.** `_play_turns` asks the holder at every priority point
  (`take_priority`); `cast`, `activate` and `play_land` in a driven game return with the object on
  the stack; the windows go; `RandomPolicy`, the router, the heuristic, the test drivers, the
  search and the packs move to priority; the act cap per player per step; the trigger-order ask;
  the `priority` ask kind grown from `cw`; the pre-check.
