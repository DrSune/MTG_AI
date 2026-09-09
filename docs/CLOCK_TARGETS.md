# Which clock we train against, and why the draw structure changes the incentive

You asked what you are actually deciding here. This is the answer. The short version is at the
bottom: **you probably do not have to decide, because one option dominates.**

## 1. The three environments

| | Paper, head to head | Paper, Commander pod | MTG Arena | Magic Online |
|---|---|---|---|---|
| Clock | 50 min round, shared between both players | 75 min pod | ~30 min per best-of-three match, plus a per-turn "rope" and a small stock of extensions | **25 min per player**, a chess clock |
| When does it tick | wall clock, both players | wall clock, all seats | your turn | **only while you hold priority** |
| On exhaustion | finish the turn, then 5 additional turns, then **DRAW** | pod rules, no additional turns, 15-minute last-turn cap | rope burns, you lose priority and the game auto-passes for you; sustained inaction auto-concedes the game | **immediate MATCH LOSS** |
| Is a draw possible | yes | yes | effectively no | **no** |
| Worth of timing out | draw = **1 of 3** match points | same | game loss | **match loss, 0** |

Sources: [Magic Tournament Rules](https://media.wizards.com/ContentResources/WPN/MTG_MTR_2025_Nov10_EN.pdf)
Appendix B and §2.4; [MTG Arena playing a match](https://mtgazone.com/playing-a-match/);
[Magic Online events FAQ](https://help.mtgo.com/hc/en-us/articles/6046263629211-Magic-Online-Events-FAQ).
The Magic Online page returns 403 to automated fetches, so its numbers here are from consistent
secondary sources rather than read directly. **Treat the 25-minute figure as high-confidence but
not primary-verified**, and confirm it before it becomes load-bearing.

## 2. Why the draw structure changes what the agent should do

Here is the concrete case. **Your agent is losing badly. There are two minutes left.**

**Under paper rules, stalling is a correct play.** If the game runs out of time it is a draw, and a
draw is worth 1 match point against a loss worth 0. So burning the clock converts a 0 into a 1. The
agent has a real, legitimate incentive to slow down when it is behind. Human players do exactly
this, and it is policed by slow-play rules precisely because it works.

**Under the Magic Online clock, stalling is never correct.** Your clock running out is a match loss.
If you were losing, you have gained nothing. If you were *winning*, you have converted a 3 into a 0.
The clock is a pure hazard with no upside in any position.

That asymmetry propagates into three places in the design.

**It decides whether the incentive is monotone.** The design in
[`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §3.2 pays for thinking out of a clock bank and adds no
authored penalty for exhausting it, on the reasoning that the loss it causes *is* the penalty. That
is clean and it is learned rather than hardcoded. But it only works if exhausting the bank is
actually bad. Under paper rules it is sometimes good, so the agent has to learn a *contextual*
policy: spend down to a draw when behind, protect the clock when ahead. That is richer and more
realistic, and it is a considerably harder learning problem.

**It opens or closes a reward-hacking surface.** This is R6 in [`DECISIONS.md`](DECISIONS.md). If
the value head learns "low clock means low value", a draw-paying environment gives the policy a way
to cash out: prefer lines that *end* the game over lines that *win* it, because ending it stops the
bleeding and the draw pays half. Under a hard-loss clock that hack does not exist, because there is
nothing to cash out to.

**It creates or removes a cliff in the value function.** Paper's five-additional-turns rule means a
lethal line that needs six turns is worth exactly zero when five remain. The value function is
genuinely discontinuous at that boundary, and a value head that does not see the turn count will be
systematically wrong in precisely the positions that decide tournaments. Magic Online has no such
boundary.

## 3. The budgets are similar; the consequences are not

Worth stating plainly, because it is easy to assume the digital clients are tighter.

```
Paper Commander pod   75 min, 4 seats, one game    ~1,050 s per seat
Magic Online          25 min per player per match  ~1,500 s per player
```

Per-decision budget is that divided by the number of decisions the agent must make. At the design
estimate of 7,500 priority windows per seat, the paper-pod figure gives the **140 ms** target in
[`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §1.3. Magic Online is not meaningfully tighter.

So the choice is **not** about how much time there is. It is entirely about what happens when you
run out, and whether running out is ever something the agent should want.

## 4. Recommendation: train against a hard-loss clock, and you need not choose

**A policy trained under a hard-loss per-player chess clock is safe in every other environment.
The reverse is not true.**

The hard-loss clock is strictly the most demanding: no draw to fall back on, no additional turns,
and the clock ticks only while you hold priority so you cannot hide behind the opponent's thinking.
An agent that never runs out under those conditions also never runs out under paper rules, which
are more forgiving on all three axes.

Train under paper rules first and you risk the opposite: the agent learns that stalling when behind
is correct, and that behaviour loses matches outright on Magic Online and gets slow-play penalties
in paper, where a warning **adds two turns to the extension** and so actively helps the opponent.

What you give up by choosing the hard-loss clock is one genuine strategic capability: correctly
playing the paper stalling line from a losing position. That is real but narrow, and it is
*additive* later rather than foundational now. It needs a clock feature in the observation and a
draw-aware value head, both of which are small changes on top of a policy that already respects a
clock. Building it the other way round, starting from a stalling policy and trying to remove the
behaviour, is much harder.

**So: adopt the hard-loss clock as the training contract. You do not need to rule on the
deployment target now.** Revisit only if paper Commander becomes the actual deployment target, in
which case the draw structure is a fine-tune, not a rebuild.

## 5. What this changes in the existing design

| Section | Under a hard-loss clock |
|---|---|
| [`DESIGN_LATENCY.md`](DESIGN_LATENCY.md) §1.2, the budget arithmetic | Unchanged. Budgets are comparable. |
| §1.3, the contract | Unchanged; 140 ms stands as the engineering target. |
| §3.2, the clock as an environment resource | **Simplified.** Bank exhaustion is an unambiguous loss, so the incentive is monotone and no contextual draw-seeking has to be learned. |
| §3.7, the shaping audit | **Strengthened.** With a monotone consequence there is less temptation to add an authored penalty. |
| R6 in [`DECISIONS.md`](DECISIONS.md), clock-in-the-value-function hacking | **Largely dissolved.** The hack needs a draw to cash out to. Keep the ablation check anyway. |
| The five-additional-turns cliff | **Removed.** No turn-count discontinuity to model. |

## 6. What remains unverified

- The Magic Online 25-minute figure and its exact behaviour on exhaustion are from secondary
  sources; the official page blocks automated fetching. Confirm before it is load-bearing.
- Arena's exact rope duration, extension count, and auto-concede timing vary by format and have
  changed over time. Not verified here, and not needed under the recommendation above.
- Whether any digital client runs true multiplayer Commander with a per-seat clock. If Commander is
  the deployment target and no such client exists, the only real-world clock is the paper pod, and
  §2's draw structure comes back. Flagged rather than guessed.
