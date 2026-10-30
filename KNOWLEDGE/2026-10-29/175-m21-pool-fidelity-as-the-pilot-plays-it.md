# 175: The M21 pool as the RL pilot plays it on `main` (2026-10-29)

Measured for the owner's question "did the bugs keep RL from beating the baseline?". Scripts in the
session scratchpad (`rlq/dead_cards.py`, `rlq/bug_incidence.py`). Both read only the deals: pool
`engine`, collection seeds of window #4 (seed-base 510201, dps 1412, 1000 games), `main` at `dade4f2`.

## Dead cards (B-49)
- The pilot deals `--pool engine` (`tools/ops/rl_pilot_phases.sh:87,171`): 281 cards, of which 239
  can be cast on `main`.
- The other 42 are noncreature permanents with no way to cast them: all 10 planeswalkers, the Auras,
  Equipment, anthems, the Sanctums.
- **Every one of the 2000 dealt decks holds at least one; on average 7.9 per deck, 16.5% of its
  nonland cards.**
- On `cards/integration` the engine pool is 278 cards and all of them are castable.

## Cards that play stronger than printed
- 98.6% of the 1000 games deal at least one card that plays stronger than printed on `main`. Each such
  card is in about 30% of games.
- Fixed on `cards/integration`:
  - B-52 Kinetic Augur;
  - B-56 Twinblade Assassins;
  - B-57 Jeskai Elder, Feline Sovereign, Subira;
  - B-60b Speaker of the Heavens.
- B-61 applies to any blocked attacker whose blockers leave combat. The pool has 5 castable first or
  double strikers (counting Sure Strike).
- Found today, still open on `cards/integration`, fixes in progress (ontology round R5 and branch
  `cards/m21-fidelity`):
  - Peer into the Abyss loses no life;
  - Sporeweb Weaver and Garruk's Harbinger have full hexproof, not "hexproof from [color]";
  - Warden of the Woods draws when its controller targets it;
  - Conspicuous Snoop casts Goblins from the top of the library at instant speed, through a free
    activation;
  - Kitesail Freebooter's exile is permanent (B-60c).

## What it means for the pilot's numbers (reading, not a measurement)
- **Mirror M (policy vs its frozen anchor).** Both seats play the same bugged game, so the bugs bias
  neither side. If the updates had moved the policy far, the exploits (Peer on yourself, targeting
  your own Warden) were easy reward an RL learner usually finds first. At KL 1.3e-3 it found none.
  The flat mirror is better explained by the size of the updates (/173 §3: "movement is not
  converting") than by the environment.
- **The bugs and the dead cards still matter, two ways:**
  - What is learned is fitted to a different game. Every deck carries about 8 blanks, so luck decides
    more of each game and the gradient is noisier.
  - Against the heuristic teacher the effect is unknown. The teacher's attack-first style may gain
    more from B-57/B-61 than the net does.
- **The first probe after the merge measures it.** Anchor vs teacher on the corrected engine, with
  paired seeds where the pool allows.
