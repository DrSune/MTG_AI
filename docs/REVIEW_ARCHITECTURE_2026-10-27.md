# Red-team: why atoms + learned encodings + a relational transformer might not beat MTG (2026-10-27)

Owner position (2026-10-27): "If there is no existing model that outperforms humans in MTG, we need
a new RL approach anyway. Trying what we're trying with the components atomized is interesting for
actually beating what the existing SOTA is … do an adversarial pass and try to find out why the
atomized subcomponents, learned encodings, a relational network, and a transformer wouldn't work."

The method is a pre-mortem. Assume the approach has failed a year from now, and list the causes.
For each cause I give the mechanism, the evidence, an early detector and a mitigation. Evidence
measured in this repo comes from `tools/audit/arch_probe.py` (report
`reports/arch_probe_2026-10-27.json`, run on branch `sets/onboarding` `5ec4646`) unless another
source is cited. My view of what *would* make the bet win, and the cheapest kill tests, are in §3
and §4.

## 0. The architecture under review
1. **Card encoder.** A static embedding per card, computed from its compiled IR: the atoms,
   their roles and parameters. It is computed once per card and cached.
2. **State encoder.** One token per visible entity: permanents, own hand, stack items, players. A
   token is the card embedding plus dynamic features: zone, controller, tapped, counters, damage,
   current P/T, continuous effects. There are also history tokens for public events.
3. **Relational core.** A transformer: self-attention over entities, which is a relational
   network. It is conditioned on the current ask.
4. **Heads.** Pointer heads over the ask's candidates (as PointerBC does now) and a value head.
5. **Training.** Self-play RL, optionally bootstrapped by imitation, possibly with search at play
   time.

## 1. Failure modes, most dangerous first

### F1. Atomized inputs make new cards representable, not understood
**Mechanism.** The bet is compositional generalization: a new card is a new combination of known
atoms, so the network should value it correctly. Neural networks, transformers included, are
known to fail exactly here.
- **SCAN** (Lake & Baroni 2018): models trained without a primitive in combinations score near
  zero on new combinations with it.
- **CFQ** (Keysers et al. 2020): accuracy falls from about 98% on random splits to under 20%
  when the test set maximizes *compound divergence*, meaning new combinations of seen atoms.
- **COGS** (Kim & Linzen 2020) shows the same pattern.

Knowing every atom does not mean knowing their combinations.

**Evidence here.**
- The training set is small and long-tailed. M21 uses 151 atom types (verbs, predicates,
  keywords, events, quantity forms, ability kinds, combinators). **57 of them (38%) occur on at
  most 2 M21 cards:** 23 predicates, 20 verbs, 5 keywords, 5 events.
- Embeddings of those atoms are trained on one or two contexts each.
- Every fully compiled M20 card is made only of M21 atoms (107/107). That is selection bias: what
  compiles is what the grammar knows. It still makes M20 the cleanest test of known primitives
  in new combinations.

**Detector.** Kill test K1 (§4) builds a compound-divergence split over atom *pairs*. If held-out
compositions score far below a random split, F1 is real.

**Mitigation.**
- Synthetic cards: generate new IR compositions with sampled parameters, execute them in the
  engine, and train on that combinatorially rich distribution. This is data augmentation (GECA,
  Andreas 2020) with an exact simulator behind it.
- Structural encoders: weights shared per atom type, tree or graph encoders over the IR.
- Atom embeddings initialized from each atom's rules meaning (§F2).

### F2. Atom meanings must be learned from a reward that is far too weak per atom
**Mechanism.**
- An IR-only encoder learns what DESTROY or KEYWORD_HAS(flying) means only through win/loss at
  the end of a game of about 84 acts. That is sparse, delayed and confounded.
- The successful unseen-card results all start from language-pretrained text encoders:
  - Xia et al. 2025 (Hearthstone), a T5 card encoder plus self-play plus a latent transition
    loss, beat tree search with up to 50% unseen cards;
  - Cardsformer;
  - DraftFM (MTG drafting), text embeddings with no card IDs.
- Our atom vocabulary starts with no semantics at all.

**Detector.** K1 compares encoders that read IR only, text only, or both, at the same budget.

**Mitigation.** This is the project's unique asset. **The engine is an exact world model**, so it
can label unlimited transitions ("apply this card's effect to state S → S′") for free.
- Pretrain the card encoder on that: predict the engine's state deltas (the rules-track lanes:
  life, zones, counters, P/T, tokens, …) from IR plus state. That is a dense, exact signal for
  atom semantics, far stronger than reward.
- Add the Oracle-text embedding from the local 27B as a second input, cached per card.

No MTG or Hearthstone learner I found has had an exact engine labelling atom semantics at this
fidelity.

### F3. The game being learned is not Magic
This is the most underrated risk, and it has two parts.
- **Rules.** This is "batch Magic" (REVIEW A-3): no priority, counter-only responses, mana that
  never empties, one act window per turn. It also has live rules bugs: B-43 sends a bounced
  creature to seat 0's hand whoever owns it. RL is very good at exploiting simulator quirks
  (specification gaming, Krakovna et al. 2020), so "superhuman in this engine" need not transfer.
- **Decks** (measured, `core/executor/games.py:360-401`). Every deck is a five-colour pile:
  - a guaranteed 10 mana sources (one basic of each colour, then other mana-capable cards);
  - then 50 cards sampled uniformly from the whole pool.

  The docstring calls these "stress decks, not tournament decks". Over 400 dealt M21 decks:
  - **lands average 13.4 of 60** (range 7–23), and mana sources including dorks and rocks 16.6;
  - about 22% lands spread over five colours, against about 40% in two colours in real decks
    (17/40 Limited, 24/60 constructed);
  - an opening hand holds about 1.6 lands.

  Games take **34.7 turns and 83.5 acts on average** (40 RandomPolicy games). Every BC, RL and
  benchmark number so far was measured on this distribution.

  K3-lite (§4) **did not confirm** that mana screw decides games. Under random play a 1–5 land gap
  is close to a coin flip, and only gaps of 6 or more (9% of games) are decisive. The deck
  distribution is still not Magic's: five colours, 22% lands, no curve. So a policy learns the
  value of fixing, curve and colour discipline in a world where those differ from real decks.

**Detector.**
- Rules: per-CR-area fidelity packs.
- Decks: K3-lite, plus K3 proper with a trained policy, where mana and colour may matter more
  than under random play.
- Later, cross-engine play against Forge or XMage AI through a bridge.

**Mitigation.**
- Priority and the full stack (A-3). B-43 and mana emptying.
- Deal only `compiled` cards (round S-1).
- **A coherent-deck mode** (B-45): 2 colours, about 40% lands, a mana curve, still seeded and
  learnable. Opt-in, so existing measurements stay comparable.

### F4. Hidden information without belief or search is exploitable
**Mechanism.** A per-seat transformer must infer the opponent's hand and deck from the history.
Without memory and some opponent modelling, it learns to play the *average* opponent. ByteRL beat
a top-10 Hearthstone player yet is "highly exploitable" in Legends of Code and Magic.
Every superhuman imperfect-information result except DeepNash uses search at decision time:
Libratus, Pluribus, ReBeL, Student of Games. DeepNash replaced search with a game-theoretic training
rule (R-NaD) and massive self-play.

**Detector.** Train exploiters: best responses against the frozen policy, as AlphaStar does. The
exploiter's win rate is the gap.

**Mitigation.**
- Event-log tokens for history.
- Regularized or equilibrium training (R-NaD, piKL).
- League self-play with exploiters.
- Determinized ISMCTS at play time with the learned value at the leaves. XMage and Forge
  already ship determinized Monte Carlo search.
- The current omniscient network can serve as a privileged critic or teacher (Suphx oracle
  guiding, AlphaStar's value function), never as the actor.

### F5. Non-transitivity: self-play chases cycles
**Mechanism.** Magic is rock-paper-scissors between archetypes. Plain self-play cycles, and beating
your last self is not general strength (Balduzzi et al. 2019; Czarnecki et al. 2020, "spinning
tops"). This repo has already been fooled once by a self-referential verdict (REVIEW A-4: mirror
against its own clone).

**Detector.** Elo against a *fixed anchor panel* (UniformRandom, the heuristic, BC nets, LLM seats;
the bench's Bradley–Terry ladder), with Nash averaging. Never against the previous checkpoint
alone.

**Mitigation.** A league of historical snapshots plus exploiters, sampled with prioritized
fictitious self-play (AlphaStar). Deck diversity is part of the league.

### F6. The sample budget
**Measured.**
- Engine only, RandomPolicy on both seats, one process: **1.1–1.3 games/s, 93–106 acts/s** (two
  runs; the second shared the machine with the CED job). That is
  roughly 20 processes ≈ 22 games/s ≈ 1.9M games/day ≈ 160M acts/day, plus non-act decisions.
- Model-driven collection ran at **0.25 games/s with 6 workers** (/147), because every decision
  is a CPU forward pass.

So the engine is not the bottleneck; un-batched inference is. That corrects
ASSESSMENT_2026-10-27 §2.4.3, which blamed engine throughput.

AlphaStar and OpenAI Five consumed far more experience. DouZero reached the top of Botzone from
one 4-GPU server.

**Detector.** End-to-end self-play decisions per second with a batched inference server.

**Mitigation.**
- An actor–learner split with one GPU inference server batching all games.
- Cached card embeddings, so each decision costs only the state transformer over about 50 entity
  tokens. Card IR is small (median 17–26 nodes, at most 93), but there is no need to re-encode it
  every step.
- A small network. Engine-labelled pretraining (F2) cuts the RL samples needed.

### F7. Long horizons and credit assignment across sub-decisions
**Mechanism.** About 84 acts plus the target, block, order and mode asks per game, with one reward
at the end. Factorizing a strategic choice into many asks spreads its credit thin.

**Detector.** Value calibration curves. Learning speed on the puzzle track (track P).

**Mitigation.**
- A value head with TD(λ).
- Search-improved targets.
- Only potential-based shaping (Ng et al. 1999), which provably preserves the optimal policy.
  Any other auxiliary reward is a Goodhart risk (REVIEW A-4).
- Draws by turn cap or stall scored as losses for training.

### F8. Numbers
**Mechanism.** Atoms carry quantities: damage, P/T deltas, X costs, counters, life. Networks
extrapolate poorly outside the ranges they trained on (NALU, Trask et al. 2018). "Deal 10 damage"
when training saw at most 5 is a classic failure.

**Detector.** Metamorphic tests on synthetic cards: raising a damage amount must never lower the
card's value.

**Mitigation.** Feed numbers as several features (raw, log, buckets), plus a monotonicity
regularizer or test.

### F9. The tokenizer is not stable
**Mechanism.** "IR serialization is the card tokenizer" (ontology §0.3) ties every trained model to
the ontology. Each fusion round re-bakes IR: R1a changed 122 M21 goldens; B-42 and B-44 will
change more. Without a contract, every round silently invalidates encoders.

**Detector.** Encoder outputs must be invariant to set-field order, which the identity law
guarantees. Measure the policy delta across an ontology round.

**Mitigation.** A versioned tokenizer contract, migration maps for fused atoms, and invariance tests
at construction.

### F10. Coverage holes make the encoder blind where it matters
**Measured.**
- Among fully compiled cards, **aliasing is essentially zero.** M21, ZNR and KHM have no groups of
  different rules text with byte-identical IR. M20 has 2 groups, both legitimate synonyms ("Flying"
  with and without reminder text; "Flying, haste" against separate lines).
- So the IR is near-injective where it parses. The problem is the parse rate:
  - at first touch, 158 of M20's 249 castable cards were partly compiled;
  - 13 templates carry LOSSY or GAP notes, such as "until this creature leaves the battlefield"
    being dropped.
- An encoder over a partial IR reasons about a different card.

**Mitigation.**
- Train and play only `compiled` pools.
- Give the encoder an explicit "unparsed text" token, the sentence's text embedding, so it knows
  something is missing.
- Grammar rounds, and an audit of the 13 lossy templates.

### F11. Rare interactions, loops and combos
**Mechanism.** Magic is Turing complete (Churchill et al. 2019). Combos are multi-card, rare, and
reward only when complete. RL seldom finds them, and a fixed-depth transformer cannot simulate an
unbounded loop. The engine also distorts them: `MAX_TRIGGER_FIRES=200`, after which the card's
trigger is silently disabled for the game (REVIEW A-6).

**Detector.** A puzzle track with known lines.

**Mitigation.** Search, a puzzle curriculum, and removing the trigger cap (a registered scaffold).

### F12. Generalization claims can be Goodharted
**Mechanism.** Reprints and same-shape text inflate "unseen" scores: 79 of M20's 341 entries are
carry-over.

**Mitigation.** Policy evaluation must use the same carry-over and sealed-split discipline as the
compiler (`tools/audit/new_set.py`). Report zero-shot play only on novel cards and on sealed sets.

## 2. Verdict of the red-team
- **What could sink the bet.**
  - **F1 and F2 are load-bearing and unproven.** The literature says naive learned encoders
    generalize poorly to new combinations, and that atom semantics are hard to learn from reward
    alone.
  - **F3 is the quiet killer.** Superhuman play on five-colour, 22%-land stress piles in batch
    Magic is not superhuman Magic. The rules gap matters more than the decks: K3-lite found mana
    gaps decisive only at the extremes.
- **What is manageable with known techniques:**
  - F4, F5 and F7: league, exploiters, search, value learning;
  - F6: batched inference;
  - F8, F9, F10, F12: engineering discipline.

None of these refutes the approach. They say where it must be built differently from a plain
"transformer over atoms trained by self-play".

## 3. The strongest version of the bet: what would beat the field
1. **Engine-supervised atom semantics.** Pretrain the card and state encoders on exact engine
   transitions, then on synthetic cards composed from atoms. This turns F1 and F2 from "learn from
   sparse reward" into "learn from dense exact labels", which the Hearthstone work could only
   approximate with a learned transition loss.
2. **Hybrid card input:** IR tokens plus the Oracle-text embedding. Language priors cover rare
   atoms, and the IR covers exact parameters.
3. **An entity transformer with pointer heads over cached card embeddings,** the AlphaStar-proven
   form.
4. **A coherent-deck, `compiled`-pool, priority-correct game** (F3). Measure the share of
   variance due to mana.
5. **League self-play with exploiters, scored on a fixed anchor panel** (F4, F5).
6. **Determinized ISMCTS at play time** within the clock. The omniscient net is used only as a
   privileged critic or teacher.

## 4. Kill tests, cheapest first (each can falsify a core assumption before big RL spend)
- **K1, compositional semantics (supervised, days).**
  - *Task:* predict the engine's state delta of a card's effect (rules-track lanes) from IR plus
    state.
  - *Splits:* random; compound-divergence over atom pairs; M20 zero-shot; KHM zero-shot.
  - *Encoders:* IR-only, text-only, hybrid.
  - *Kill:* if the compound-divergence and M20 scores are far below the random split for every
    encoder, F1 is real. Then synthetic-card augmentation or structural encoders are mandatory
    before RL.
- **K1 result, 2026-10-27** (KNOWLEDGE /165, `reports/k1_2026-10-27.jsonl`; pre-registered
  `reports/k1_2026-10-27_preregistration.md`).
  - **Transfer is real where new cards resemble trained ones.** On M20's new cards the IR bag
    reaches effect-lane R² 0.506 [0.42, 0.57]. That keeps 74% of its seen-card gain and 73% of the
    identity ceiling.
  - **It is weak on effects unique in the set.** Three held-out M21 draws: 0.097, 0.003, 0.149,
    keeping 0–21%. One draw is 96% Peer into the Abyss.
  - **Atoms against text, with no pretraining:** a tie on M20 (0.506 against 0.503). IR + text is
    best on ZNR (0.298).
  - **A transformer over IR sequences does worse than the bag** at about 200 training cards.
  - **Verdict.** F1 and F2 are real, and they are bounded by effect diversity in training, not by
    the encoder. That points to synthetic atom compositions (K1b) before any big RL.
- **K2, value transfer (days).** Train a value net on M21 games with the entity encoder. Measure
  win-prediction calibration on M20's compiled pool zero-shot, against a name-token baseline,
  which sees only `<unk>` there.
- **K3, deck validity (hours, CPU).**
  - **K3-lite, run 2026-10-27:** 400 RandomPolicy games, M21 castable, current builder. 392
    decided and 343 with unequal land counts.

    | Land gap between the decks | Games | Win rate of the deck with more lands |
    |---|---|---|
    | 1–2 | 174 | 0.477 |
    | 3–5 | 138 | 0.536 |
    | ≥6 | 31 | 0.839 |
    | All unequal | 343 | 0.534 |

    Seat 0 wins 0.551. Mana is not dominant under random play.
  - Next: repeat with a trained policy and with coherent decks (B-45), and add colour-screw
    (castable share) to land count.
- **K4, self-play health (weeks).** A small league on M21 coherent decks. Report Elo against the
  anchor panel and the exploiter win rate over training.

## Sources
- Compositional generalization:
  - Lake & Baroni 2018, [SCAN](https://arxiv.org/abs/1711.00350);
  - Keysers et al. 2020, [CFQ / compound divergence](https://arxiv.org/abs/1912.09713);
  - Kim & Linzen 2020, [COGS](https://arxiv.org/abs/2010.05465);
  - Andreas 2020, [GECA](https://arxiv.org/abs/1904.09545).
- Relational inductive biases:
  - Santoro et al. 2017, [Relation Networks](https://arxiv.org/abs/1706.01427);
  - Zambaldi et al. 2019, [relational deep RL](https://arxiv.org/abs/1806.01830);
  - Battaglia et al. 2018, [graph networks](https://arxiv.org/abs/1806.01261).
- Learning dynamics:
  - Geirhos et al. 2020, [shortcut learning](https://arxiv.org/abs/2004.07780);
  - Trask et al. 2018, [NALU](https://arxiv.org/abs/1808.00508);
  - Ng et al. 1999, potential-based reward shaping (ICML);
  - Krakovna et al. 2020, [specification gaming](https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/).
- Self-play: Balduzzi et al. 2019, [open-ended learning](https://arxiv.org/abs/1901.08106); Czarnecki et al. 2020, [spinning tops](https://arxiv.org/abs/2004.09468).
- From the 2026-10-27 research brief (see `docs/ASSESSMENT_2026-10-27.md` for links): AlphaStar, DeepNash, Suphx, Pluribus, ReBeL, Student of Games, DouZero, ByteRL and its exploitability, Xia et al. 2025, Cardsformer, DraftFM, MTG Turing completeness.
