# Why a parameter's cost depends on where you put it

Written because "a parameter inside the pass loop costs forty times a parameter in the trunk" is
the single most useful thing the latency measurements produced, and it is not obvious. It should
drive the rebuild.

## 1. The machine is waiting on memory, not on arithmetic

The GB10 has two relevant speeds:

| | |
|---|---|
| memory bandwidth | ~273 GB/s |
| dense bf16 compute | ~125 TFLOPS |

To use a weight you must first read it. A weight in bf16 is 2 bytes. Using it in a matrix multiply
against one row of input does 2 floating-point operations. So at batch size 1 you get **1 FLOP per
byte read**.

The machine can do 125e12 FLOPs per second and read 273e9 bytes per second. It is balanced at

```
125e12 / 273e9 = 458 FLOPs per byte
```

At batch 1 you are supplying 1. You are **458 times short of keeping the arithmetic units busy.**
The GPU spends essentially all of its time waiting for weights to arrive from memory.

That gives the rule that governs everything else:

> **Latency at batch 1 is approximately (bytes of weight read) divided by (bandwidth).
> It is almost independent of how much arithmetic those weights then do.**

This is why the sweep found latency flat in board size and in legal-action count. Doubling the
board doubles the arithmetic, and the arithmetic was free. It was never the constraint.

## 2. Therefore cost is (size) multiplied by (how many times it is read)

A parameter is not charged once. It is charged **once per read**.

- A weight in a block that runs **once per decision** is read once. It costs 2 bytes.
- A weight in a block that runs **inside a loop** is read once per iteration.

The current model has two nested loops around its decision head:

```
for pass in range(num_passes):        # up to 8, model.py:232
    ...
    for step in range(plan_steps):    # 5, ActionSequenceDecoder
        run the 4-layer plan decoder
```

Eight passes times five plan steps is **forty reads of every plan-decoder weight, per decision.**
Each of those weights costs 80 bytes, not 2.

## 3. What that does to the current model

| block | parameters | share of model | reads per decision | share of decision's memory traffic |
|---|---|---|---|---|
| board encoder | 134.4 M | 43% | 1 | **6%** |
| **plan decoder** | **50.4 M** | **16%** | **40** | **87%** |
| everything else | 130.9 M | 41% | 1 to 8 | 7% |

The board encoder is **2.7 times larger** than the plan decoder and costs **a fourteenth as much
latency.**

So: is it bad how it is? Yes, on three counts, and the third is the one that stings.

1. **The money is in the wrong place.** 43% of the parameters sit where they are nearly free and
   16% sit where they are ruinously expensive. Capacity is not where it can be afforded.
2. **It sets the default badly.** Collection runs at eight passes, which measures 169 ms against
   19 ms at one pass. That is a nine-fold latency cost, paid on every decision of every training
   game.
3. **You are paying 87% of your latency budget for a head that receives no gradient.** Only plan
   step 0 reaches the loss today, so three of its four output heads and most of its capacity learn
   nothing. It is the most expensive component and the least trained one.

Point three is why the fix and your instruction point the same way. The head is not worthless. It
is untrained, and it is in the wrong shape.

## 4. The design rule

> **Spend parameters in inverse proportion to how many times they are read per decision.**

Concretely, three tiers, and the budget should look roughly like this:

| tier | reads per decision | what belongs here | budget guidance |
|---|---|---|---|
| **A. once per board change** | ~0.15 (one in six or more) | the board encoder, card and ability-tree encoding, everything about *what is on the table* | **as large as you like.** This is where the 128 GB gets spent. Amortised, a parameter here costs a sixth of a read. |
| **B. once per decision** | 1 | the recurrent state, the value head, the action encoder, the pointer | large. Normal cost. |
| **C. inside the pass and plan loops** | up to 40 | the reasoning step and the plan step | **small and shared.** Every parameter here is charged forty times. |

Three practical consequences for the rebuild:

**Cache the board across passes.** The board does not change between reasoning passes about the
same decision. Encoding it eight times is pure waste. Encode once, let every pass cross-attend to
the cached result. Measured: this alone is worth about 2.3 times.

**Make the reasoning step narrow and reuse it.** A pass should be a thin, shared block that
refines a small working state against the cached board, not a fresh deep stack. If the same weights
run every pass, the memory system can keep them resident and repeated passes get much cheaper than
their nominal byte count. Depth belongs in tier A, iteration belongs in tier C.

**Cut the plan loop's per-step cost, not the plan.** Five plan steps through a 4-layer decoder is
twenty layer-reads. The same plan can be emitted by a much thinner decoder, or by predicting the
plan in parallel rather than autoregressively where the steps do not depend on each other.

## 5. Why this supports adaptive reasoning passes rather than arguing against them

You said reasoning passes must be a trained head or the model will never learn to use them. That is
right, and the cost model is what makes it affordable rather than what blocks it.

The argument is not "passes are expensive, so have fewer". It is **"passes are expensive in
proportion to what is inside them, so make the inside cheap and you can afford many"**.

Do it the current way, at 50.4 M parameters per pass step, and eight passes cost 169 ms. Put the
depth in the cached board tier and make each pass a thin shared refinement, and the marginal cost
of one more pass drops by an order of magnitude. At that point the model can genuinely afford to
think for a long time on a hard turn, which is the behaviour you actually want.

There is a second, better reason to train the head. **A fixed pass count is a hardcoded schedule**,
which the charter defaults to no on. A learned halting head spends compute where it pays and skips
it where it does not, and the measurements say the easy decisions dominate: 21% of priority windows
in the current corpus have exactly one legal move. Those should cost nothing, and a trained head is
what makes them cost nothing.

## 6. How to check this holds on the real hardware

The claim is a bandwidth argument, and bandwidth arguments are checkable.
`tools/latency/bench.py` reports an **effective achieved bandwidth** column: weight bytes per
decision divided by measured latency. On the dev box it reads 20 to 50 GB/s against roughly 120
GB/s theoretical.

On the Spark, run the same script and look at that column.

- If effective bandwidth lands near the theoretical figure, the model is bandwidth bound and
  everything above holds exactly.
- If it lands far below, the model is **launch bound** instead, and the fix is CUDA graphs rather
  than architecture. The launch counts are measured, not guessed, so the two causes are
  distinguishable: `kernel_launches_measured` times roughly 8 microseconds gives the dispatch floor.

Either way the conclusion for where to put parameters is the same. Both bandwidth and launch count
scale with reads per decision, not with parameter count.
