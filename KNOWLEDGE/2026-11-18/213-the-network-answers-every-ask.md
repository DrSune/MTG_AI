# 213. The network answers every ask (2026-11-18)

The owner, on r29's fallback count (about 0.1 a game against r28's 0.02): "We cannot accept the
model can't choose between all its options ... Shouldn't the target be 0.00 for fallback? I don't
want any weaknesses for long-horizon RL self-play."

Agreed: the target is zero, and it is now zero by construction. The network's seat has no fallback
agent left to hand an ask to.

## 1. What the fallback was

`actor.NetAgent.decide` handed two kinds of ask to the heuristic (`HeuristicAgent`):
- an ask with more than `features.MAX_OPTIONS` = 64 options;
- every `name` ask ("choose a card name"), at any size.

The heuristic's choice was played, never recorded, never trained on, and counted as `overflow`
in the `iter` rows. The cap dated from the deleted PointerBC observation (registered 2026-10-24).
The self-play network never needed it:
- options are tokens of variable number;
- the trainer packs decisions by a token budget;
- the inference server buckets requests by length.

## 2. What filled it: four cards

Heuristic against heuristic, coherent decks, each set's verified pool, on main at a31c39b7 (the
code r29 runs). Scripts and outputs are in `reports/fallback_census_2026-11-18/`.

| Pool | Games | Real decisions | Fallback asks | Per seat and game | Source |
|---|---|---|---|---|---|
| M21 | 1,200 | 217,135 | 122 | 0.051 | Necromentia 69, Runed Halo 53 (name asks, 269 and 274 options) |
| M20 | 600 | 92,091 | 271 | 0.226 | Diviner's Lockbox 193 (name ask, 283 options), Icon of Ancestry 78 (creature type, 70 options) |

- **Nothing else came near.** No other ask exceeded 63 options: the widest were 42 `one_of` asks
  of 48 to 63 options in M21.
- **The engine's new asks never overflowed.** The new kinds (combat damage division, an ability
  as a target, a source's several triggers) stayed under 32 options.
- **Why r29 is above r28: the new cards.** Diviner's Lockbox was stamped 2026-11-17 (wave 4) and
  Icon of Ancestry 2026-11-13; both are in the M20 pool, which deals a quarter of r29's games.
  r28's 0.02 was Necromentia and Runed Halo.
- **Prediction against measurement.** The census predicts 0.75 × 0.051 + 0.25 × 0.226 = 0.095
  fallback asks per learner seat and game. Arm A measured 0.089, over 103 updates and one
  learner seat a game.
- **About 0.1% of the learner's decisions**, but always the same decisions:
  - a Lockbox activation's name;
  - Runed Halo's protection;
  - Necromentia's target name;
  - Icon of Ancestry's type.

  The network could never learn to play those cards' central choice, nor plan for it.

## 3. The fix (main, after r29's launch commit)

- **A name option points at the card it names.**
  - `features.O_NAMED` is a new option column: the named card's card-table row
    (`CardTable.name_row`).
  - The network reads it as a card token reads its identity (name embedding plus component
    vector), through one new layer, `model.named_ptr`.
  - The name never drops out in training. The name is the choice: Runed Halo's protection is from
    that name, not from what the card does.
- **The option list is not cut.** `MAX_OPTIONS` is gone. The fallback is removed from:
  - `NetAgent` (and its `overflow` count from the actor and the learner);
  - the searcher's simulated seats;
  - the line-value instrument;
  - the trace tool;
  - the behaviour-cloning recorder, which now records every real decision.
- **A permanent's chosen card name is observed.** `features.C_NAMED` is a card column read the
  same way through the same layer. Before, a chosen colour or creature type had a column
  (`C_CHOSEN`, 2026-11-13) but a chosen card name had none, so the network could not see what an
  opponent's Runed Halo named.
- **Older networks compute what they did.**
  - A checkpoint without `named_ptr` loads it as zero (`model.upgraded`'s pointer rule).
  - The layer is registered last, so a seeded build draws every older layer's weights as before.
  - Inputs recorded before the columns existed are widened with zeros (`model.widened`).
- **Tests:**
  - `test_the_network_answers_every_ask_however_many_options` fails on the old seat code: the
    fallback answered and the network never saw the ask.
  - `test_a_permanents_chosen_card_name_is_observed`.
  - `test_a_network_from_before_name_options_computes_what_it_did`.

## 4. The entity cap, measured and removed

The same census encoded every real decision (400 M21 and 300 M20 games, 117,481 decisions).
- **No option ever pointed at a card the network could not see**: 0 of 117,481.
- **The graveyard's keep rule cut cards.** Each graveyard kept its 16 newest cards, and each exile
  its 10 newest. This cut cards in 859 of 72,072 M21 decisions (1.2%), up to 20 cards at once,
  and in 18 M20 decisions.
- **No battlefield or hand card was ever cut.**

Showing them all costs about 0.09 extra tokens per decision (6,156 cards over 72,072 decisions).
So `MAX_CARDS`, `GRAVE_KEEP` and `EXILE_KEEP` went too: every public card is an entity. The
"observation caps" scaffold left `docs/BACKLOG.md` with this note.

## 5. What it means for r29

- **The running r29 keeps the fallback.** It is pinned at 60f0913f, at about 0.09 to 0.12 asks a
  game.
- **The fix joins when FDN does.** That is the segment after B8, with the two open engine faults'
  fixes (208 §9), and it goes in that segment's registration.
- **Expect a short adaptation.** The network meets about 280-option name asks and 70-option type
  asks for the first time. The name-option layer starts at zero on r29's checkpoint, so those
  options begin indistinguishable and the gradient separates them.
- **One decision class is still not the network's: mana payment.** The engine picks which sources
  tap (BACKLOG "Automatic payment", a registered scaffold).
  - This fix does not change it. It is a within-turn planning limit: a spell paid with the wrong
    land can strand the next spell's colour.
  - KNOWLEDGE/2026-11-18/214 takes it up with the rest of how options are presented.

## 6. Lesson

A capacity limit hid a class of decisions from training for weeks. The count existed (`overflow`,
logged every update), and nothing read it against a target. The guard is structural: no
delegation path is left in the network's seat. The remaining heuristic answers inside network
play are the searcher's playouts past `MAX_SIM_DECISIONS`, a rollout budget, not a training
decision.
