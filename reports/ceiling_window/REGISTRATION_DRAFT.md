# The ceiling-read window: registration draft (before any of its games)

**For the coordinator:** review, then copy into a KNOWLEDGE note (suggested
`KNOWLEDGE/2026-11-13/204-ceiling-window.md`) at a commit before the window runs. Results are
appended to that note and never edit §1-§5.

**Context.** `docs/PLAN_CEILING.md` §14.1 and §14.5 as amended 2026-11-13 02:25:
- r28's gates have sat at about 0.54 against its init since update 100 (199 §7), and R3 is
  falsified (199 §5);
- the four package ordering lines carry no signal (202 §2), and 202 registered the ceiling read
  as the next test of "richer decks, more skill";
- so the window measures the skill spread per deck distribution, and plays the games that fix
  the held-out pool L's ratings (§7.2, §14.4), as a pause in r28.

The owner (2026-11-12): *"Realistic decks probably have a higher skill cieling than random decks
... We need to make sure it has some signal in the directions we move, or the gradient never goes
there."*

## 1. What runs

`reports/ceiling_window/queue.sh`, from a worktree pinned at the note's commit
(`/home/sune/Desktop/MTG_AI-cw`), as the unit `mtg-ceiling`, one GPU job at a time, after
`systemctl --user stop mtg-r28`. Every job is `learner.py --eval-only` with `--refresh-table
--extend-sets M20 --pool verified --infer-bf16 --eval-set M21 --workers 18 --slots 16 --groups 4`:
greedy, M21, each deal played twice with the seats swapped.

**The network NET:** r28's `last.pt` at the pause, copied to `runs/ceiling_window/r28_latest.pt`
(its update and sha256 go to `queue.log`).

**The deal shapes:**
- *coherent*: the default;
- *package*: `--package-share 1.0` (`tools/selfplay/packages.py`: both decks built around a
  synergy package; 19 packages kept in M21's verified pool at this commit, 18 when package mode
  was built);
- *drafted*: `--eval-decks drafted:8 --draft-critic runs/window2/critic_r27.json` (193's v0
  critic, content sha256 6b8014ae…): each seed's coherent decks after 8 critic swaps, as 193's
  G4. The mode is named `drafted:8:6b8014ae`.

**The search:** window 1's anchor setting (192 §9: n = 4): `--search-root gumbel --search-m 16
--search-n 4`, act decisions and attack plans, horizon 1, uniform worlds, greedy continuation,
skip at 0.97.

**Part 1, the ceiling read** (deals 1,100,000+, the same seeds in every shape):

| Job | Measures | Deals | Estimated time |
|---|---|---|---|
| `b_coherent` | (b) NET raw against the heuristic, and the setup's sanity check (§4) | 2,000 | 4 min |
| `a_coherent` | (a) NET searched at n = 4 against NET raw (`--search-record`) | 1,500 | 44 min |
| `a_package` | (a) | 1,500 | 46 min |
| `b_package` | (b) | 2,000 | 4 min |
| `a_drafted` | (a) | 1,000 | 27 min |
| `b_drafted` | (b) | 2,000 | 3 min |

**Part 2, L's games** (deals 1,110,000+, every pairing on every shape). Members:

| Member | Checkpoint (under `runs/selfplay/`) | Also |
|---|---|---|
| random | — | Elo 0, the anchor |
| the heuristic | — | |
| r26 v0 | `r26_outcome_ppo/v0.pt` | r23's network (`r23_mulligan/gen.pt`): the same weights and table; r25's v0 byte for byte |
| r26 v1 | `r26_outcome_ppo/v1.pt` (update 202) | |
| r26 v2 | `r26_outcome_ppo/v2.pt` (update 378) | |
| u1000 | `r26_outcome_ppo/u1000.pt` | r27's v0: the same network once loaded (r27's file holds u1000's weights, the zero columns `model.load` adds, a refreshed table) |
| u1000 + search | u1000 at n = 4 | §7.2's "r27's v0 plus search at the anchor's n" |
| r27 v1 | `r27_priority_ppo/v1.pt` (update 75's weights) | r28's v0: the same weights and table |

Checked by loading every candidate on the CPU (`model.load`, every tensor compared): duplicates are
one player, so r23's network, r27's v0 and r28's v0 are not separate members. Every member's file
and the critic are pinned in `reports/LARGE_FILES.sha256`; the queue refuses to play if one
differs.

The pairings (one job per line and shape; the first member is the job's init):

| Job | Pairings | Deals per shape | Time, 3 shapes |
|---|---|---|---|
| `L_r26v0` | r26 v0 – heuristic, – random | 300 | 4 min |
| `L_r26v1` | r26 v1 – r26 v0, – heuristic, – random | 300 | 6 min |
| `L_r26v2` | r26 v2 – r26 v1, – heuristic | 300 | 4 min |
| `L_r26v2-r26v0` | r26 v2 – r26 v0 | 300 | 2 min |
| `L_u1000` | u1000 – r26 v2, – heuristic, – random | 300 | 6 min |
| `L_r27v1` | r27 v1 – u1000, – heuristic | 300 | 4 min |
| `L_r27v1-r26v2` | r27 v1 – r26 v2 | 300 | 2 min |
| `L_heuristic` | the heuristic – random | 300 | 2 min |
| `L_u1000s4-u1000` | u1000 + search – u1000 | 300 | 27 min |
| `L_u1000s4-r27v1` | u1000 + search – r27 v1 | 200 | 18 min |

17 pairings over 8 members: a chain by expected strength with skip links (r26 v0–v2, r26 v2–r27
v1), the heuristic met by five networks, random by three networks and the heuristic, and the
searched member in a cycle (u1000 + search – u1000 – r27 v1). Connected, with cycles. Neighbouring
networks are expected to score 0.5-0.6 against each other (their gates froze them at 0.55), where
a game carries the most information; random's games, at 0.92-0.99, mostly anchor the scale.

**Part 3** (deals 1,120,000+): NET against r27 v1 and against u1000, 300 deals per shape (5 min),
so `rate.py rate` gives NET an L rating with its (b) games.

**Precision.** A paired searched-against-raw score has an SE of about 0.012 per 300 deals at
n = 4 (192 §4). So (a) has SE 0.0054 at 1,500 deals (95% ±0.011) and 0.0066 at 1,000 (±0.013);
(b) about 0.0061 at 2,000 deals (±0.012; r28's v0 had ±0.024 at 500). The differences between
shapes are read paired by seed (`score.py` prints the unpaired estimate beside them). The pairing
buys little: package decks come from their own draw of the seed, and 8 critic swaps take a deal's
games apart (window 2's G4: drafted and coherent deal scores correlate +0.01 over 1,000 seeds).
So package minus coherent in (a) has SE about 0.0076 (±0.015), drafted minus coherent about 0.0093
over its 1,000 shared seeds (±0.018).

**Time.** From window 1's measured rates (192 §4, §7.5; NUMBERS 2026-11-11/12: 1.76 s per deal
searched at n = 4, 0.114 s raw against the heuristic, 0.12 s raw network against network, about
14 s to start a job) and window 2's drafted games (0.77 of the time of coherent ones raw; 17.7
turns against 19.4): part 1 about 129 min, part 2 about 75 min, part 3 about 5 min, the score
about 2 min. **Total about 3.5 hours**, plus stopping and resuming r28. Package searched games are
budgeted 5% slower (the heuristic's package games run 15.8 turns against 16.4). Every job has a
cap of about twice its estimate. Nothing is dropped.

**The score:** `env PYTHONPATH=. .venv/bin/python reports/ceiling_window/score.py
runs/ceiling_window` (the queue writes `runs/ceiling_window/score.txt`). L's ratings are frozen
with `rate.py fit runs/ceiling_window/pool_L.json runs/ceiling_window/L_*` once the coordinator has
read the games (voids, the fit).

## 2. Predictions

The skill spread of a deal shape is the stronger player's score over deals there. S1 decides
r29 (§3); S2-S4 are scored hit or miss as registered and decide nothing on their own. Every
interval is a 95% one: normal over deals for a shape, a bootstrap over the shared seeds for a
difference between shapes (`score.py`).

| # | Metric | Prediction | Falsifier |
|---|---|---|---|
| S1 | (a) package minus coherent | The owner's hypothesis, above all in the search's headroom: +0.02 or more, the lower bound above 0 | The upper bound below +0.02: package decks hold no material extra one-turn headroom |
| S2 | (a) drafted minus coherent | −0.025 to +0.005. Drafted decks are tempo decks, not richer ones (§14.1's red team: games 1.71 turns shorter, the deal decided by the deck on the play more often, 193 G4's pilot-decided deals −0.045) | The lower bound above 0: critic-drafted decks hold more headroom |
| S3 | (b) package minus coherent | +0.01 or more (the owner's hypothesis; the heuristic's blind spots in package decks push the same way, §5) | The upper bound below 0 |
| S4 | (b) drafted minus coherent | −0.04 to +0.005 | The lower bound above +0.01 |

**The agent's own expectation** (so the reviewer is scored too): S1 near 0 (−0.01 to +0.015).
The four ordering lines read no value (202 §2), and horizon 1 cannot see a package's payoff beyond
the next turn (§5).

## 3. What each outcome means for r29

| S1 (a: package minus coherent) | Reading | r29 |
|---|---|---|
| Lower bound above 0, estimate +0.02 or more | Package decks hold more of the skill the search finds in one turn: more for the network to learn there | §14.1's A/B: r29 trains with a package share (its value registered with r29), beside r28 continued at matched updates; both rated on L, which holds every shape |
| Lower bound above 0, estimate below +0.02 | A real but small gain | The same A/B, registered with its expected gain at most the measured one |
| The interval holds 0 and its upper bound is below +0.02 | No material extra headroom at the search's horizon | r29 is not the package A/B. The levers of §14.4 for a stall come first: training both seats of learner-against-learner games (about twice the on-policy decisions per game), and the own-decklist columns asked again on package decks (200 §1). Package decks stay out of training; a specialist still needs a line class with measured value (202 §3's sacrifice line) |
| The upper bound below 0 | Package decks hold less | As the row above |
| The interval holds 0 and reaches +0.02 | Unresolved | 1,500 more deals of `a_coherent` and `a_package` (deals 1,101,500+, about 95 minutes) in r28's next pause, then this table again; no r29 decision from this window |

S2 falsified (drafted decks hold more headroom) reopens §14.1's withdrawn step B, drafted decks in
training, as an r29 candidate beside package decks. S2 met confirms §14.1: the drafter waits for a
pilot that plays synergies (§14.4).

## 4. Sanity and stop rules

- **The setup:** `b_coherent` runs first. NET below 0.65 against the heuristic there stops the
  window before any searched game (the queue exits and r28 resumes): r28's v0 scored 0.753 there
  on 500 deals (199 §5). Predicted: 0.72-0.82.
- **The search helps at all:** if (a)'s coherent lower bound is not above 0.50, S1 and S2 are not
  read: the instrument does not resolve headroom on this network. Predicted (a) coherent:
  0.52-0.58 (u1000 0.556 ± 0.012 at n = 4 on window 1's deals).
- **Voids:** at most 0.5% of deals per job (r27 and r28 played the verified pool with 0 voids; the
  castable pool's crashes were fixed in 201).
- **L before it is frozen:** `score.py` prints each pairing's pooled score beside the all-shape
  fit's expectation. A pairing more than 3 SE from it marks the pool non-transitive there
  (TRAINING_REVIEW_PROTOCOL R4.2); the ratings are then frozen with that pairing named, never
  adjusted by hand.

## 5. Confounds, measured or named

1. **The code is not r28's.** The window runs at its own commit, 104+ commits after r28's pin
   44a62d9 (package mode exists only there). Measured on the CPU:
   - the verified M21 pool grew from 262 to 275 cards; 13 are new to r28 (Archfiend's Vessel;
     Basri, Devoted Paladin; Drowsing Tyrannodon; Feline Sovereign; Garruk, Savage Herald; Hooded
     Blightfang; Rookie Mistake; Runed Halo; Teferi's Ageless Insight; Teferi, Timeless Voyager;
     Tolarian Kraken; Transmogrify; Unsubstantiate);
   - they make 4.9% of the spells in coherent and drafted decks and 5.3% in package decks
     (deals 1,100,000-1,100,399; 96-97% of deals hold one), so they are not a difference between
     shapes. Package decks concentrate them in two payoffs (Feline Sovereign, Hooded Blightfang);
   - `--refresh-table` rebuilds 12 of the table's 613 rows and adds 10 component tokens at zero
     (`@once_per_event`, `role:arrange`, `PhasingEvent`, `Verb.ATTACK_POLICY`, ...);
   - the arrange ask (CR 401.4) is new: the network reads its column through zero weights.
   Every job and shape shares these, and the numbers here are not compared with r28's own gates.
2. **The search sees one turn, in uniform worlds.** A package's payoff beyond the next turn is
   invisible to (a) (§14.2), and uniform worlds misdraw a package opponent's hand more than a
   coherent one's. Both push S1 toward 0: a null S1 says "no more one-turn headroom", not "no
   more skill".
3. **NET never trained on package or drafted decks** (r28 deals coherent decks, M20 in 25%). (a)
   on package decks includes what the network has not learned about them. That is the gain r29
   would buy, so it counts for the decision, but it is not by itself a higher ceiling.
4. **The heuristic's blind spots** (it never activates a sacrifice outlet and aims burn at
   creatures first; package mode, NUMBERS 2026-11-12) widen (b) on package decks for a reason
   that is not the decks'. That is why (b) does not decide.
5. **Drafted decks** use a critic fitted on r27's games at update 29 (193); it knows none of the
   13 new cards, so swaps neither add nor remove them.

## 6. Exploratory (reported, never decisive alone)

- u1000's own search headroom per shape (`L_u1000s4-u1000`): a second network's S1, at SE about
  0.012 per shape.
- L's fit per shape and the networks' Elo range per shape (`score.py` part 2): the owner's
  hypothesis predicts a wider ladder on package decks.
- The deal falls per shape (the stronger player won both games, lost both, one each), turns,
  searched decisions and clear corrections per game.
- NET's L rating (`rate.py rate`).
- L's ladder, expected: r26 v0 < r26 v1 < r26 v2 ≤ u1000 < r27 v1, u1000 + search within 30 Elo
  of r27 v1, the heuristic within 100 of r26 v0.

## 7. Not set up

- **The niche shape.** §7.2 and §14.4 deal L's members niche decks too. No niche-deck generator
  exists (D14's niche set and the drafter's nicheness knob are unbuilt), so L is dealt coherent,
  package and drafted decks only. A niche shape joins L when it exists, by rating its games
  against the frozen ratings, not by refitting them.
- **F1's checkpoints, specialists and exploiters** (§7.2) do not exist yet (gate B has not run).
- **§14.1's 2x2 per deal** (decks swapped apart from the pilots) is not built: a deal's two games
  swap the pilots with their seats and decks together. Each pilot plays each deck and each seat
  once, which cancels deck and seat asymmetry in expectation, not its variance.
- **The CPU smoke cannot test** bf16 inference or the GPU's timing: the CPU runs fp32.
