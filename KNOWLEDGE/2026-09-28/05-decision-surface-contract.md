# 2026-09-28 · 05 — Decision-surface contract (owner mandate: explore all corners of the card)

Owner instruction 2026-09-28 13:55: the atomized IR must preserve every point where an ability
requires a **controller decision** or produces a **board-dependent/stochastic outcome**, so the
Phase-2 model sees the FULL distribution of outcomes — never a pre-defaulted single path.
This doc is the binding audit + contract. Reaffirms atomization note /04 §2.

## 1. Decision classes → IR nodes (what a consumer must enumerate)

| Decision/outcome class | IR carrier | Status |
|---|---|---|
| Which ability to use (activated/loyalty/spell) | card.abilities list — each Activated/SpellAbility with Cost is a separate node; legality gating = executor | ✓ structural |
| Do optional effect or not ("may") | OptionalEffect | ✓ |
| Mode choice ("Choose one —", "Choose one or more") | Choose node with option Effects (r2 choose-opener built-in; QAtLeast(1) for "one or more") | ✓ |
| Which/how many targets | Selector(mode, count, filter, zones) — legal-set enumeration is executor-side | ✓ except collapse C-1 |
| Quantity choice (X, "up to N", pay N) | QX, QUnbounded, QAtLeast; PAY verb + "if you do" continuation | ✓ except C-1 |
| Whether/how much to choose in a search | SelectorMode.CHOOSE = "up to count, chosen by a controller" | ✓ |
| Board-conditioned outcomes ("if opponent controls more…") | Conditional (pred, effect, else_effect) — BOTH branches present in tree | ✓ (R7-3 makes Otherwise explicit) |
| Event-conditioned triggers | EventSpec + TriggeredAbility (+ blocked/subject slots) | ✓ |
| Stochastic branch (coin flip) | Verb.FLIP_COIN + FAtomPred.FLIP_WON gating (Conditional) | ✓ |
| Replacement/redirection ("instead") | ReplacementAbility (r5) | ✓ |
| Whose choice ("each opponent chooses…") | Selector.controller_ref / ControllerRef vocabulary | ✓ |
| Anaphoric picks that consume earlier choices | referent vocabulary source/controller/target/event/result + C12 | ✓ (R7-1) |

## 2. Identified collapses (found by audit 2026-09-28 — decisions currently defaulted)

- **C-1 "up to N target(s)" → TARGET + QConst(N)** (templates_b2a convention ~L33; SelectorMode
  TARGET docstring = "exactly count"). The 0/1..N-1 sub-choices are LOST. Two rule-shapes:
  targeted "up to N" = legal range 1..N; resolution-time "up to N" (e.g. "fights up to one")
  = 0..N. The CHOOSE mode already encodes 0..N. FIX: templates switch controller-chosen
  "up to" to SelectorMode.CHOOSE going forward (C15 below, immediate); faithful TARGET-max
  semantics (`QAtMost` quantity or TARGET_UP_TO mode) = grammar item R8-1 (golden-visible,
  re-baseline with audit). Affected today: b2a "up to one/two" rows + Kinetic "discard up to
  two" (R7 batch row must use CHOOSE, not TARGET).
- **C-2 TokenSpec has no color field** — token color silently dropped at creation ("4/4 white
  Angel" ≈ colorless). Mechanically relevant (hexproof-from-color, protection, tribal).
  FIX R8-2: additive `TokenSpec.color: str|None = None` (omit-if-empty ⇒ old goldens stable);
  new templates populate it.
- **C-3 "mana of any one color" → ADD_MANA(color="C")** conflates any-color with colorless.
  FIX R8-3: additive color-choice marker (e.g. `color="ANY"` vocabulary — decide with R8-1).
- **C-4 (watch) Star P/T** known gap stays gap (NUMBERS 2026-09-15), not a silent default. OK.

## 3. Binding conventions (immediate, for R7 batches and beyond)

- **C15 (decision preservation in templates)**: a template must never silently default a
  controller decision: "up to N" → SelectorMode.CHOOSE with QConst(N) (+ reveal/set
  constraints via filter); "may" → OptionalEffect; multi-outcome "if/else/otherwise" →
  Conditional with else_effect when the else sentence exists; named choices get the referent
  vocabulary. If faithful encoding needs missing grammar, the row goes lossy-with-verbatim-note
  or withdraws — it must NOT default the choice. PC-3 still binds pattern shapes.
- **C16 (decision-surface acceptance)**: every new/changed template row's report line must name
  the decisions the encoded subtree leaves open to a controller (targets × N, modes × k,
  quantity range) or state "none — fully forced". This makes the collapse class auditable
  per-batch instead of per-refactor.

## 4. Phase-2 note (encoder/executor contract)

Distribution exposure is the DESIGN_CARD_POOL single-representation mandate: the encoder reads
the same tree, so every OptionalEffect/Choose/Conditional/CHOOSE-selector/QX node is exactly one
decision or stochastic vertex the policy can branch on; the executor's job is enumerating legal
sets (filters make this mechanical). The three collapses above are the known distance between
"tree shows all corners" and current fidelity; fixing them is R8 grammar work, NOT Phase-2.
