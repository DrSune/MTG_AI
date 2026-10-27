# Atoms and the state of the art: where MTG_AI stands (2026-10-27)

Owner request (2026-10-27): "Give me your understanding of the atomic subcomponents, so I know you
are moving towards the intended target/way of generalizing this game. Then evaluate it with field
expert strategies, methods and techniques, to see if we have a SOTA approach to making a game
engine + superhuman performance."

Part 1 is my reading of the ontology, checked against `docs/DESIGN_ATOM_ONTOLOGY.md` (binding) and
the code (`MTG_bot/core/ability_tree.py`). Part 2 is the assessment. Its sources were fetched on
2026-10-27 and are listed at the end. Numbers measured in this repo cite their KNOWLEDGE note.

## 1. The atomic subcomponents, as I understand them

### 1.1 What an atom is
- **Atom.** An atom is **one game operation**: a `Verb` plus typed `role → value` pairs. There are
  50 verbs, among them DEAL_DAMAGE, DESTROY, MOVE_ZONE, CREATE_TOKEN, MODIFY_PT, GRANT_ABILITY,
  SEARCH, COUNTER_SPELL, ATTACH, GAIN_CONTROL and FIGHT. `_VERB_ROLES` fixes which roles each verb
  takes and which are required.
- **Value sorts.** A role's value comes from one of eight sorts:
  - **Quantity**, in 11 forms: QConst, QX, QCount over a selector, QProp, QBin, QThisTurn, and
    others.
  - **Selector:** a mode (6: TARGET, CHOOSE, ALL, ONE_OF, …), a count, a **Filter** and zones.
    - A Filter is an algebra over 52 predicates (TYPE_EQ, CONTROLLER_IS, KEYWORD_HAS, POWER_LE, …)
      with FAnd, FOr and FNot.
  - **Zone**, **Duration**, **PtDelta**, **TokenSpec** (a nested card record) and **LiteralName**.
- **Effects** compose atoms through seven combinators:
  - Seq keeps printed time order.
  - Choose is a menu.
  - OptionalEffect is the "may" axis.
  - Conditional, Repeat, EachPlayer and DelayedTrigger.
- **Abilities** wrap effects. There are 11 kinds: Spell, Activated (cost, timing), Triggered (one
  of 17 event classes, plus a condition), Static, Replacement, Keyword (23), EtBState,
  CostModifier, Emblem, Kicker and BackFace. The ontology's fusion unit is
  **{when-event} × {gates} × {cost} × {operations}**.
- **Canonical identity.** The same meaning must be the same bytes:
  - role pairs are sorted;
  - FAnd and FOr children are sorted and flattened, and a single child is unwrapped;
  - "deal 2 damage to target creature" and "choose target creature, deal 2 damage to it" give
    one Atom, because designation is a role, not a step (law T1).
  - TIME order (Seq) and MENU order (Choose) are kept, because they are card identity.
  - Divergences the laws cannot normalize are ledgered in `docs/ATOM_DIVERGENCES.md`.

### 1.2 How the game is meant to generalize
A new card should be a **new composition of existing atoms**. NORTH_STAR's tied rank 1 then holds
if each of three links is compositional:

| Link | Intended | Today (measured) |
|---|---|---|
| Text → IR (the compiler) | grammar maps new wordings to known atoms | **Not compositional yet.** ~450 regex sentence templates. At first touch it parsed 8% (M20) and 11% (KHM) of sentence shapes absent from M21 and ZNR. On M20 cards with new text it fully compiled 11%. After this session's two rounds the unseen-shape figure is 13% and 17% (/159, /160, /163). |
| IR → execution (the executor) | verb dispatch + selectors + layers run any composition | **Compositional by design.** Fuzzing with partly compiled cards: 40/40 games and 0 crashes on M20, KHM and ZNR. The bounce bug below shows that compiling is not the same as executing correctly, so each atom needs execution tests. |
| IR → policy (the network) | the IR serialization is the card tokenizer (ontology §0.3) | **Not built.** The live policy reads card names: an unseen card is `<unk>` (REVIEW A-1). This is the largest gap to the King goal. |

Only a genuinely new mechanic should need code: a new verb, predicate or keyword. Foretell, boast
and crew are examples of that; "destroy target artifact" is not.

### 1.3 Where the atom set drifts from "as few as possible"
- **One-card predicates.** Several of the 52 predicates read like single cards:
  `LIFE_LEAD_OVER_START_GE`, `NAME_PARTITION_COUNT_GE`, `ATTACK_AGAINST_COUNT_GE`,
  `NOT_FIRST_DRAW_THIS_STEP`, `INSTANT_OR_SORCERY_CAST_THIS_TURN`. The last is a QThisTurn count
  of CastSpell events with an FOr filter. These are candidates for decomposition in a gated
  ontology round.
- **Divergent spellings (B-42).**
  - MOVE_ZONE names the moved object `cards` in 67 uses and `target` in 20 (the exile family).
  - "Its owner's hand" is written `Zone(HAND, OWNER)` on three M21 cards and `Zone(HAND, ANY)` on
    three others.
- **The second is a live rules bug (B-43).** `zone_owner` resolves `ANY` to seat 0. So Barrin,
  Niambi and Roaming Ghostlight put a bounced card into seat 0's hand, whoever owns it. Separately,
  `OWNER` is read as the card's *controller*: the World tracks no owner, which goes wrong after
  GAIN_CONTROL. I logged it but did not fix it, because fixing it changes M21 games while the RL
  pilot depends on byte-identical episodes.

### 1.4 Is this session's compiler work on target?
Yes, by the ontology's own tests.
- **No new atoms.** Rounds S-1 and S-2 add no atom and no per-card template. They add **general
  mechanisms** that emit the existing atoms:
  - S-1: keyword lines.
  - S-2: bucket B11, the first noun-phrase grammar in the compiler. One target-phrase grammar
    (types, "or", controller, "with keyword", "with power N or less") is shared by five verbs.
    Alongside it come general attached-creature statics, tokens, bare Equip and Enchant.
- **Identity holds.** On all 52 sentences that both B11 and an older template match, the IR is
  byte-identical, and M21's 305 goldens are unchanged.
- **The sealed test splits moved with the dev splits.** M20 test PC-1 went 0.133 → 0.162, and
  KHM's unseen-shape PC-2 went 0.114 → 0.169. That is evidence the mechanisms generalize, not that
  they fit what I read.
- **It is still incremental.** The step change is a constituent grammar; see 2.5.

## 2. Is this a state-of-the-art approach? An expert assessment

### 2.1 What the state of the art looks like in 2026
**Engines.** Production MTG engines take one of two routes.
- **Hand-written cards.**
  - Forge: a DSL script for each of 34,131 cards.
  - XMage: one Java class per card, more than 32,000 of them.
- **Compiling Oracle text.**
  - MTG Arena's GRE: a grammar-based "Game Rules Parser" that emits CLIPS rules, with no ML. About
    80% of new cards work without hand work, and the rest extend the parser. It sits on more than
    3,000 regression tests.
  - phase-rs (2026): Rust parser combinators. It reports 88% coverage of 34,300 cards, with LLM
    agents extending the parser one *class* of cards at a time behind coverage and audit gates.
    Its own backlog shows 4,535 "supported" cards that parse wrong: **coverage is not
    correctness**.
- **Research.** Semantic parsing of card text went from 4.8% exact match (card2code 2016) to
  grammar-constrained decoding. In 2025–26, LLMs write executable game models that are refined
  against recorded trajectories (Code World Models, ICLR 2026). The caveat is that
  transition-accurate code can still lose at play.

**Play.** No trading card game has a peer-reviewed superhuman agent. Public MTG RL agents are
roughly level with XMage's heuristic AI, and LLMs play weakly (mage-bench). Superhuman results in
other hidden-information games come from four families:
- **Belief-state search plus self-play RL:** ReBeL and Student of Games, for two-player zero-sum
  games.
- **Model-free equilibrium RL:** DeepNash (R-NaD) in Stratego, at expert level.
- **Imitation, then league self-play:** AlphaStar, with an entity encoder, pointer heads and a
  value function that sees the opponent's information during training only.
- **Oracle guiding:** Suphx (Mahjong, above 99.99% of ranked players) trains with hidden
  information visible, then removes it.

Others worth knowing:
- Pluribus reached superhuman six-player poker on one 64-core server, searching 1–33 s per
  decision.
- DouZero ranked first of 344 Botzone bots after training on a single 4-GPU server.

For cards the agent never saw, text- or attribute-based card encoders are the proven route:
- Hearthstone, Xia et al. 2025: a T5 card encoder plus self-play beat tree search with up to 50%
  unseen cards.
- MTG drafting, DraftFM 2026: no card IDs at all, 51–60% top-1 agreement with human picks on
  held-out sets.

### 2.2 Scorecard

| Axis | State of the art | MTG_AI today | Verdict |
|---|---|---|---|
| Card representation (engine) | Compiled Oracle text → rules (Arena, phase-rs) | Compiled Oracle text → a canonical atom IR with identity laws, a divergence ledger and goldens | **Right family; the IR discipline is ahead of what phase-rs publishes** |
| Parser generality | ~80% of new cards automatic (Arena); 88% coverage (phase-rs) | Sentence-shape templates; 11% of new-text M20 cards at first touch; KHM 3% | **Far behind.** The B11 grammar is the first step on the right path |
| Correctness assurance | 3,000+ regression tests (Arena); semantic audit backlog (phase-rs) | 428 engine-verified packs; goldens; fuzz; sealed splits; 99.92% of components exercised by a pack, though "exercised" is not "verified" | **Strong for the scope; mutation testing missing** |
| Rules fidelity | Full CR with priority and stack (Arena, Forge, XMage) | "Batch Magic": no priority, counter-only responses, mana never empties, no Commander (A-3); bounce-to-seat-0 bug (B-43) | **Behind; a prerequisite for any superhuman claim** |
| Card encoder (policy) | Text/attribute encoders, no IDs (Xia 2025, DraftFM 2026); entity encoders (AlphaStar) | Name tokens; unseen = `<unk>` | **Behind; it blocks tied rank 1** |
| Hidden information | Belief search (ReBeL/SoG), R-NaD, or determinized ISMCTS (XMage, Forge 2026) | Policy and search fork read hidden zones (A-1); no belief model | **Behind as an actor.** Reusable as a privileged teacher or critic (Suphx, AlphaStar) |
| Learning signal | Self-play RL, league, search-improved targets | Imitation of a ~100-line heuristic, capped at teacher level (0.394 vs the heuristic, /133); RL pilot at instrument stage | **Behind** |
| Decision-time search | Required in every superhuman imperfect-information result except DeepNash | Not in the live policy | **Missing** |
| Self-play throughput | Millions to billions of decisions | Engine only: 1.11 games/s, 93 acts/s per process (about 1.9M games/day on 20 processes). Model-driven: 0.25 games/s with 6 workers, because each decision runs an un-batched CPU forward pass (/147; REVIEW_ARCHITECTURE F6) | **Inference, not the engine, is the binding constraint**: batch it on the GPU |
| Evaluation | Duplicate format, CIs, Elo against anchored bots, human calibration, exploitability | Duplicate deals, Wilson/bootstrap/SPRT/Bradley–Terry, anchored floors, sealed splits, Goodhart controls, LLM seats | **At or above field practice; missing external opponents (Forge/XMage AI) and humans** |

### 2.3 What is genuinely ahead of the field
- **A canonical, ledgered IR.** Arena and phase-rs compile to rules, but neither publishes an
  identity law. Here, "same meaning ⇒ same bytes" is tested.
  - It is what makes differential testing possible. B11 was checked against 52 overlapping
    sentences.
  - It makes the IR usable as a tokenizer.
- **Measurement honesty.**
  - Sealed first-touch splits with logged reads. No MTG engine I found reports a held-out
    first-touch number.
  - Floors in every table, and duplicate statistics.
  - These are the controls the Leaderboard Illusion and Goodhart literature call for.
- **An LLM benchmark built on the same instrument as the bot.** Same action space, a per-seat view
  with a metamorphic hidden-information test, name masking, and a primer generated from the
  compiled pools. Against mage-bench this is a stronger design: duplicate deals, floors, and no
  composite score.

### 2.4 What blocks superhuman play, in order
1. **Rules fidelity.** Instant-speed interaction is core MTG skill. Without priority and a full
   stack the agent masters a different game (A-3). Fix B-43 and mana emptying with it.
2. **Card representation.** A name-token policy cannot meet tied rank 1. The IR-as-tokenizer
   encoder is the planned answer and matches the SOTA pattern (structured or text encoders, no
   IDs).
3. **Throughput.** Model-driven self-play runs at about 0.25 games/s because every decision is an
   un-batched CPU forward pass. The engine alone runs at 1.11 games/s per process, about 1.9M
   games/day on 20 processes. An actor–learner setup with a batched GPU inference server and cached
   card embeddings is the fix. Correction, 2026-10-27: this section first blamed the engine; see
   REVIEW_ARCHITECTURE F6.
4. **Learning signal.** Imitating the heuristic is capped at the heuristic's level, and that cap
   was measured. Self-play RL with search-improved targets is the standard way past it.
5. **Hidden information at play time.**
   - First step: determinized ISMCTS. It is cheap, proven in MTG, and is what XMage and Forge do.
   - Belief-aware search (ReBeL/SoG-style) is the research frontier.

### 2.5 Recommended program (each step gated by a number this repo already measures)
1. **Parser: a constituent grammar.**
   - Build NP, effect, trigger, condition, cost and duration constituents (parser combinators, the
     phase-rs approach) that emit the existing IR. Keep the templates as a regression oracle: the
     B11 differential test, scaled up.
   - Let the local 27B propose grammar rules for whole classes of cards (phase-rs's "lend your
     LLM"). Accept a rule only through the gates: identity with existing IR, goldens, packs, and a
     rise on the sealed split.
   - **Gate:** first-touch PC-1 on a fresh sealed set ≥ 0.8, Arena's level.
   - Add semantic audits: IR → text regeneration diffed against the Oracle text, plus mutation
     testing.
2. **Engine: priority and a full stack (A-3).** Then mana emptying and the B-43 ownership fix,
   timed with the RL pilot's next era.
   - **Gate:** packs for priority windows; fuzz holds at 0 crashes.
3. **Encoder: IR tokens instead of names.**
   - **Gate:** zero-shot play on M20/KHM's compiled pools against the floors, where today the
     policy sees `<unk>`.
4. **Training: reuse the omniscient net as a privileged teacher or critic.** Distill it into a
   per-seat student (oracle guiding: Suphx; AlphaStar's value function), then run self-play RL
   with a small league over decks. Train with cap and stall draws scored as losses (A-4).
5. **Search: determinized ISMCTS with the learned policy and value as priors,** inside the match
   clock (Pluribus searches 1–33 s per decision).
6. **Evaluation:**
   - external opponents: Forge's AI, now with Monte Carlo search (2026), or XMage's MCTS player,
     through a bridge;
   - LLM seats, as the 27B self-play now running (/163);
   - expert humans;
   - exploitability probes. ByteRL beat a top Hearthstone player yet is highly exploitable.

### 2.6 Verdict
- **Engine:** the right architecture, the Arena and phase-rs family of compiled Oracle text, with
  a better-disciplined IR than either publishes. It is **not yet state of the art in generality or
  rules fidelity.** The parser is a shape library, and the game lacks priority and a stack.
- **Superhuman play:** the current stack is **not** a state-of-the-art approach. It is name-based,
  omniscient, imitation-capped and search-free. Every component of a SOTA recipe has a known
  design that fits this repo, and most can run on one Spark at DouZero or Pluribus scale. The
  bottlenecks are rules fidelity and un-batched model inference, not GPU (corrected: the engine
  alone is not the bottleneck, REVIEW_ARCHITECTURE F6).
- **Benchmark and measurement:** at or above field practice, and the part most ready to show
  publicly once the release gates in DESIGN_BENCHMARK hold.

What would change this verdict:
- a sealed first-touch PC-1 ≥ 0.8;
- a per-seat, IR-encoded policy beating the heuristic with a confidence interval above 0.5;
- a win rate above 0.5 against Forge or XMage AI on duplicate deals.

## Sources
- **Engines.**
  - MTG Arena GRE: [Werner 2023](https://magic.wizards.com/en/news/mtg-arena/on-whiteboards-naps-and-living-breakthrough), [Adams 2023](https://magic.wizards.com/en/news/mtg-arena/why-i-decided-not-to-do-emrakul-and-how-we-shipped-it-anyway).
  - Forge: [scripting API](https://github.com/Card-Forge/forge/wiki/Card-scripting-API), [Monte Carlo PR #12308 (2026)](https://github.com/Card-Forge/forge/pull/12308).
  - XMage: [readme](https://github.com/magefree/mage/blob/master/readme.md), [MCTS player](https://github.com/magefree/mage/blob/master/Mage.Server.Plugins/Mage.Player.AIMCTS/src/mage/player/ai/ComputerPlayerMCTS.java).
  - phase-rs (2026): [repo](https://github.com/phase-rs/phase), [misparse backlog](https://github.com/phase-rs/phase/blob/main/docs/parser-misparse-backlog.md).
- **Card text as code.** [card2code, Ling et al. 2016](https://arxiv.org/abs/1603.06744); [Abstract Syntax Networks 2017](https://arxiv.org/abs/1704.07535); [Yin & Neubig 2017](https://aclanthology.org/P17-1041.pdf); [Code World Models (ICLR 2026)](https://arxiv.org/abs/2510.04542); [rule translation vs inference (2026)](https://arxiv.org/abs/2607.14169).
- **MTG AI.** [Ensemble determinization MCTS, Cowling et al. 2012](https://eprints.whiterose.ac.uk/75050/); [ISMCTS 2012](https://eprints.whiterose.ac.uk/75048/); [MTG is Turing complete](https://arxiv.org/abs/1904.09828); [mage-bench](https://mage-bench.com/); [MTG-Causal-RL](https://arxiv.org/abs/2605.06066); [MageZero](https://github.com/WillWroble/MageZero); [DraftFM (2026)](https://arxiv.org/abs/2608.19568).
- **Superhuman play.** [Pluribus](https://ai.meta.com/blog/pluribus-first-ai-to-beat-pros-in-6-player-poker/); [DeepStack](https://arxiv.org/abs/1701.01724); [ReBeL](https://arxiv.org/abs/2007.13544); [Student of Games](https://arxiv.org/abs/2112.03178); [DeepNash](https://arxiv.org/abs/2206.15378); [AlphaStar](https://storage.googleapis.com/deepmind-media/research/alphastar/AlphaStar_unformatted.pdf); [OpenAI Five](https://arxiv.org/abs/1912.06680); [Suphx](https://arxiv.org/abs/2003.13590); [DouZero](https://arxiv.org/abs/2106.06135); [ByteRL, Hearthstone](https://arxiv.org/abs/2303.05197); [ByteRL exploitability](https://arxiv.org/abs/2404.16689).
- **Generalization to unseen cards.** [Xia et al., AAMAS 2025](https://aamas.csc.liv.ac.uk/Proceedings/aamas2025/pdfs/p2795.pdf); [generalised MTG card representations (CoG 2024)](https://arxiv.org/abs/2407.05879); [RTFM](https://arxiv.org/abs/1910.08210).
