# Design: real priority (the priority rung)

Status: **proposed 2026-11-10, not built.** The owner, 2026-11-10: "make sure the game works as
Magic. It is important to get it up to speed in terms of the basics. Having the skeleton set up so
we train the network for realistic games from the beginning, seems important. Not having the
instant mini-rounds or what it is, is bad."

This replaces BACKLOG B-110 ("abilities never sit on the stack") and the "priority rung" the
scaffolds point to. Code facts come from two surveys of 2026-11-10 (the engine, and the self-play
and agent code); the ones the design rests on were re-read (`stack.py:1227-1239`,
`legality.py:1955`, `__init__.py:1686-1709`, `games.py:132-134,1426-1546`). Line numbers are as
of 64f0aee.

## 0. Why

A player acts only in their own two main phases (`_play_turns`, `games.py:1504,1540`). Besides
that there are two one-round windows: counterspells against a spell (`_response_window`,
`stack.py`, opened inside `cast`) and one-target damage or pump instants after blockers
(`open_combat_window`). Activated abilities resolve inside `activate` (`legality.py:1955`) and
triggers inside `_settle`, so no ability is ever on the stack. Note 190 §4.1 counts the cost:
about 30% of M21's nonland cards play weaker than printed (Eliminate, Heroic Intervention, Opt,
Frost Breath, Unsubstantiate among them), and a network trained here learns that instants are
sorceries. Commander, the far goal, is a game of instant-speed interaction.

Two smaller defects go with the windows: the combat window asks seats in fixed `player_order`, so
on seat 1's turn seat 0 is asked first (`stack.py:1015`, against CR 117.3a and its own docstring),
and the counter window never gives the caster priority back (CR 117.3c). The heuristic answers
both windows without judgement (190 §1.13).

## 1. The rules to implement (two players)

- **Priority** (CR 117). The active player receives priority at the start of each step and phase
  that has it, after turn-based actions and after the triggers of its start are on the stack
  (117.3a), and after any spell or ability resolves (117.3b). A player who casts, activates or
  plays a land keeps priority (117.3c). Passing gives it to the other player (117.3d). When both
  pass in succession the top object resolves, or with an empty stack the step ends (117.4).
  Each time a player would receive priority, state-based actions are checked and waiting
  triggers go on the stack first (117.5).
- **Steps** (CR 500-514): untap (no priority), upkeep, draw, first main, beginning of combat,
  declare attackers, declare blockers, combat damage (a first-strike damage step before it when a
  creature has first or double strike), end of combat, second main, end step, cleanup (no
  priority unless something happens in it, 514.3a). Mana empties as each step and phase ends
  (CR 500).
- **Timing.** Sorcery speed: own turn, a main phase, empty stack (sorceries, creatures and other
  permanents, "activate only as a sorcery", loyalty abilities, playing a land). Instant speed:
  whenever the player has priority (instants, flash, other activated abilities).
- **Casting and activating** (CR 601.2, 602.2): announce, choose modes, X and targets, pay, and
  the object is on the stack. It resolves later, when both players pass. Mana abilities do not
  use the stack (605.3b).
- **Triggers** (CR 603.3): put on the stack the next time a player would receive priority, the
  active player's first (APNAP), each player ordering their own; modes and targets are chosen
  then, and a trigger with no legal target is removed (603.3d).
- **Resolution** (CR 608): targets are checked again and the effect runs; LIFO (CR 405).

## 2. What changes in the engine

### 2.1 Principles

1. **Priority points are clean boundaries owned by the turn loop**, not callbacks inside an
   engine call. A fork (`tools/search/fork.py`) is a deepcopy between engine calls, so only then
   can the search branch on a response, and only then can a game be stopped and resumed at any
   priority point. Choices made while casting or resolving (targets, modes, X, payment, discard)
   stay provider asks inside the call, as today.
2. **A forced pass is not a decision.** A player with no legal action but passing is not asked.
   That is the rules, not a shortcut. The engine never filters legal actions by usefulness.
3. **Delete, do not keep alongside.** `_response_window`, `open_combat_window` and their vocabs
   (about 380 lines of `stack.py`) and the hook in `combat_blocks` go. Counterspells and combat
   tricks are cast from the general menu.
4. **Seeded games stay reproducible; trajectories change once.** Engine randomness is keyed on
   `_op_seq` (`__init__.py:548-553`), so every new op shifts seeded games. The fixed-trajectory
   pins (`test_executor_games.py:2332-2335,2454`; `test_executor_player_loss.py:295,314-316`)
   are re-pinned deliberately, once.

### 2.2 The turn as a state machine

`Executor.phase` today has UPKEEP, FIRST_MAIN, COMBAT, SECOND_MAIN and END_TURN
(`__init__.py:380`); the steps inside them exist only as code (`begin_turn` 1831-1878,
`combat_attacks` 1982-2018, `combat_blocks` 2020-2070, `end_turn` 2725-2754). It becomes a step
clock with one value per step above. `begin_turn`, `combat_attacks`, `combat_blocks` and
`end_turn` split into per-step turn-based actions (untap, draw, declare attackers, declare
blockers, each damage wave, cleanup). Every step gets a journal marker, so "at the beginning of
the end step" and "at the beginning of combat" triggers fire on their own markers. The transient
flags (`declaring`, `_draw_step_open`, `_combat_wave_open`, `_closing_turn`) become step state.
Mana pools empty at the end of every step, including upkeep and draw, which today run together
into the first main phase.

### 2.3 Stack objects

One typed stack object for spells, activated abilities and triggered abilities, with a handle
namespace for ability objects, folded into `stack.dump()` and the fingerprint. Readers of
`stack.frames` then see abilities with no further change. `STACK_KIND_EQ` ACTIVATED/TRIGGERED
(`quantity.py:1702-1715`), stack target enumeration (`legality.py:401-412`), `_v_counter_spell`
(`verbs.py:2302-2394`) and `_exile_the_stack` (`__init__.py:1777-1798`) learn about them.
Unsubstantiate's spell half is fixed in the same step (BACKLOG under B-110). The waiting-trigger
queue is not fingerprinted today (`state.py:248-270`), safe only because every settle drains it;
it goes into the fingerprint.

### 2.4 Casting, activating and resolving

`cast` (`stack.py:1087-1382`) is one synchronous call: it pushes the spell, settles (cast
triggers resolve above it, `:1231`), opens the counter window, pops and resolves. It splits:

- `cast` does CR 601.2: designation, pricing, payment, push, the CAST row. It returns with the
  spell on the stack. Cast triggers wait in the queue.
- A new `resolve_top` does CR 608 for the top object: today's `stack.py:1238-1381` for a spell,
  the effect half of `activate` for an ability, `_fire`'s resolution half for a trigger.
- Non-mana `activate` (`legality.py:1804-1963`) pays and pushes an ability object. Mana
  abilities stay immediate.
- `cast_card` (effect casts, `stack.py:1419-1593`) pushes and returns instead of resolving inside
  the resolution that cast it.

### 2.5 Triggers

`_settle` (`__init__.py:1686-1709`) today matches events, checks state-based actions and fires
every trigger to resolution. It becomes: match events, state-based actions, then put waiting
triggers on the stack (APNAP; a new ask for a player to order their own simultaneous triggers,
which also fixes BACKLOG's "resolve oldest first, never asked"; modes and targets chosen now;
removed when a required target is missing). It never resolves anything. `_fire`
(`binding.py:1511-1628`) keeps only resolution: the intervening "if", the CR 608.2b target
re-check (missing for triggers today, BACKLOG ~205-209) and the effect. The pre-binds written
for resolution time (`binding.py:1555-1622`) move to the moment the trigger is put on the stack.
The 200-fire tripwire in `fire_all` is redefined per step.

### 2.6 The priority loop

```
step loop (state in Game: step, priority holder, passes in succession):
    turn-based actions of the step (untap, draw, declare attackers, ...)
    if the step has priority:
        holder = active player
        loop:
            settle: state-based actions, waiting triggers onto the stack      (CR 117.5)
            menu = legal actions of holder now                                 (2.7)
            action = ask holder if menu has more than PASS, else PASS
            if action is not PASS: perform it (push, or play the land); passes = 0; holder keeps priority
            elif passes + 1 == 2:                                               (CR 117.4)
                if stack empty: end the step
                resolve_top(); passes = 0; holder = active player             (CR 117.3b)
            else: passes += 1; holder = the other player
```

The loop is the only place priority moves. Its state lives in `Game`, so a game stopped at any
priority point resumes there; this replaces `stop_after`'s four boundaries and the
`skip_next_acts` / `skip_to_blocks` flags (`games.py:1442-1536`) with one resumable point. The
act cap becomes a cap on one player's actions per step (registered scaffold, `games.py:132-134`,
BACKLOG "10 acts per main phase"; its row is rewritten, not added). The stall rule stays where it
is, at the top of each turn (`games.py:1356-1400`), and so does the turn cap.

### 2.7 The menu

One menu for any player at any priority point, built by the router's `_act_menu`
(`router.py:235-311`) with the timing gates keyed on who holds priority. Two gaps to close:
`ability_playable` takes `stack_empty` from its caller (default True, `legality.py:1090`) and
`legal_activations` never passes it (`query.py:307`); `spell_window_reason`
(`legality.py:1414-1443`) already leaves instants ungated.

Cost: a menu build takes 1.66 ms (p99 4.4 ms), 40% of a game's time in a probe of 4 random-agent
games (engine survey). Today there are about 2.8 builds per turn; with about 20 priority points a
turn, building every time would cost about seven times more. So a cheap pre-check comes first: does
the holder have an instant or flash card in hand, or a non-mana activated ability whose timing
allows it now, and untapped mana or a free cost? Only then the full build. Measure before and
after (§5).

**Mana rows, open point.** The act menu offers costly mana abilities (Treasure, pay-life sources)
as rows that fill the pool (`router.py:245-251`), because automatic payment taps only free
sources (registered scaffold "Automatic payment"). At every priority point such a row would make a
decision of nothing for any player holding a Treasure. Proposal: offer a mana row only when some
spell or ability in the same menu becomes payable with it. That is a legality fact, not a
judgement. It goes when payment folds into the move (DESIGN_ACTION_SPACE §1.3), and is registered
as a scaffold until then.

## 3. What changes for the players

### 3.1 The decision interface

`take_acts` (implemented by the driver: `SeatRouter.take_acts`, `router.py:204-233`;
`RandomPolicy.take_acts`, `games.py:752-795`) gives way to one decision per priority point: the
loop asks the provider, the router builds the menu, one action or PASS comes back. Two ask kinds:

- `act`: the holder may act at sorcery speed (own main phase, empty stack). Same meaning and
  menu as today, so trained networks keep what they know.
- `priority`: instant speed only (any other priority point). New, grown from `act` when a
  checkpoint loads (`ASK_GROWN_FROM`, `features.py:50-63`; `model.py:309-324`).

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
- **Ability objects** as stack entities with their kind, and a handle that does not collide with
  the source permanent in `ent_index` (`:498-500`).
- **What a stack object targets**: frame targets, X and modes are not encoded. A pointer from a
  frame to its targets, like the attachment pointer (`:526-528`; `model.py:106-107`).
- **Whether the other player has just passed** (passing then resolves the top or ends the step).
  Priority passes are public.

The hidden-information test (`test_selfplay.py:69`) covers every new column as it stands.

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
boundaries (`actor.py:115-137`; `search.py:378-411`). With the loop of 2.6 it forks at any
priority point and resumes there. `forced` (which matches only `act` answers), the resume logic
and the value leaf (which assumes the turn's first decision is the first-main menu,
`search.py:367-375`) are rewritten, and the budget of 400 decisions per simulation
(`MAX_SIM_DECISIONS`, `search.py:67`) is re-sized for the extra decisions. Searching `priority` asks comes after the first training run
on the new game; until then the raw network answers them. The simulator uses no turn-loop hooks;
it needs a new capture and retraining.

### 3.5 The learner

Nothing assumes one actor per turn: every decision is a trajectory step keyed by game and seat
(`learner.py:615-617`). Three things change:
- **Per-kind metrics** (count, PASS share, entropy, advantage by kind in each `iter` row): none
  exist (`rig.py:104-106` counts but `play_game` exports totals only). Without them a policy that
  always passes looks healthy. Checked against METRICS §17 before adding.
- **The batch is counted in decisions** (`--steps`). More decisions per game means fewer games
  per update; the noise-scale reasoning of note 189 is per decision and is re-derived on the new
  game.
- **The entropy bonus** pushes every decision toward uniform, including priority points where
  passing is right. At 0.0075 an action costing five points of win probability keeps
  exp(-0.05 / 0.0059), about 0.02%, of passing's weight, so the push is self-limiting; the
  per-kind entropy shows it.

### 3.6 The LLM bench

The router and protocol are shared: `ENGINE_NOTES` (`view.py:52-57`), the primer
(`primer.py:57-58`) and `duel.py:121` change, and `SeatView` gains the step and the attack and
block flags (`view.py:94-154`).

## 4. Tests and scenario packs

- **An auto-pass driver for rigs and packs**: both players pass until the stack is empty, which
  reproduces today's "cast returns resolved" for the at least 143 tests that call `cast` and the
  at least 244 that drive turns. Window answers in packs already default to PASS
  (`run_scenarios.py:412-420,448-452`).
- **Rewritten**: about 30 window tests (`test_executor_rung1.py` 14, `test_executor_rung2.py`),
  about 50 loop and whole-game tests, 17 `take_acts` sequencing tests, the self-play and bench
  tests that pin the boundaries (`test_selfplay.py:182,200,739`; `test_router.py:367`), and the
  54 packs with window lanes or `hold_triggers` (which stands in for responding to a trigger).
- **New, one per rule**: the active player gets priority first in each step; the caster keeps
  priority; both passing resolves the top and the active player gets priority again; an empty
  stack ends the step; mana empties per step; triggers go on the stack APNAP before priority with
  targets chosen then; a trigger without a target is removed; targets re-checked on resolution.
- **New packs for cards that gain their printed power**: Eliminate on an attacker after attackers
  are declared; Heroic Intervention in response to removal; Opt at the opponent's end step;
  Frost Breath in the opponent's beginning of combat; a flash blocker; a counterspell; Tale's End
  on a triggered ability; Unsubstantiate on an artifact spell; first-strike damage then a pump in
  the regular damage step.
- **Pre-flight**: P9 (games end by a loss) and P12 (replay) unchanged; the card-onboarding probe
  (`tools/cards/probe.py:66,226,369,416,484`) answers priority asks with PASS as it answers the
  windows today.
- The 305 compiled-IR goldens are unaffected unless the IR changes.

## 5. Throughput

Today: about 52 learner decisions per game, 13.1-14.8 games/s on 18 workers (r26); 72.8 asks with
more than one option per heuristic game (NUMBERS). Workers are CPU-bound on the engine. Priority
adds asks only where the holder can act; how many is not known and is measured first: decisions
per game and games/s for heuristic games on the new engine, before the network sees it. If the
cost is too high, the remedy is a shortcut the rules allow ("pass until something is put on the
stack or my next turn"), offered as an option the network learns to choose, not a filter in the
engine (DESIGN_ACTION_SPACE §1.3 has the measured case for priority shortcuts).

## 6. Stages

Each stage lands with the suite green and games playable. r26 runs from its pinned worktree
throughout.

1. **Stack objects and the cast/activate/trigger split**, resolved by an auto-pass driver: same
   games as today except trigger targets chosen when put on the stack.
2. **The step clock and the priority loop**: priority in every step for both players, responses
   to anything, the windows deleted, the act cap redefined, mana per step; tests, packs and pins
   migrated; the new rule tests and card packs.
3. **The players**: router and protocol (`priority` kind), features (§3.2), the heuristic (§3.3),
   per-kind metrics, the bench. Measure throughput (§5).
4. **Search and labeller** at priority points; the simulator recaptured.
5. **Card census**: which cards now play as printed (190 §4.1's table again), BACKLOG cleared of
   the rows this closes.
6. **Training on the new game**: a pre-registered run (TRAINING_REVIEW_PROTOCOL).

The yardstick changes at stage 3 (a heuristic that plays instants and abilities) and the game at
stage 2, so every Elo, gate and ladder before them is history, not a baseline.

## 7. Decisions for the owner

1. **Faithful priority in every step** (recommended; the alternative, more windows, is the
   current scaffold grown).
2. **Shortcuts only if measured necessary**, and then learnable (§5).
3. **The first network on the new game** starts from the newest version (r26's), with `priority`
   grown from `act`; a short cloning phase from the new heuristic only if PPO alone flails at the
   new decisions.
4. **r26 keeps running** until stage 6 is ready to launch.

## 8. Risks

1. The clean-boundary requirement is structural: get it wrong and responses cannot be searched.
2. Flipping what `_settle` means: every step, action call, pack and many tests assume triggers
   have resolved when a call returns.
3. Trigger targets chosen when put on the stack: the pre-bind logic was written for resolution.
4. Throughput (§5).
5. Behaviour at the new decision points: an always-act fallback (the heuristic today), a policy
   that learns to always pass, unseen by totals.

## 9. After this: the other basics

From note 190, for realistic games: the network sees its own deck list and what is left in its
library (§4.3, `PLAN_LEARNING.md:351`); decks with a shape instead of uniform piles (§4.5); the
card's parts carrying what its name carries today, then names masked per game in self-play
(§5.1-5.3); an unseen-card score in every ladder (§3.4).
