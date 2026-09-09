# Design: card representation, auto-extension, and card-pool conditioning

Status: **proposed, not built.** This answers the second standing open problem in
[`NORTH_STAR.md`](../NORTH_STAR.md), and it is also the mechanism for the tied-rank-1 goal:
a card never seen before, built from already-practised primitives, plays correctly on day one
with zero code changes.

## The one commitment everything rests on

> **One versioned, typed intermediate representation that is simultaneously the only thing the
> engine executes and the only thing the network reads about a card.**

Adding a *node type* is a code change. Adding a *card* is not. That distinction is the whole
design.

When the executor and the encoder read different representations you get today's failure mode
exactly: the parser emits a `selector` node while the executor looks for a `target` key, so
every targeted spell in the set resolves as a no-op and nobody noticed for months. One
representation makes that class of bug structurally impossible.

## Why the current system cannot auto-extend

It is not a compositional system missing pieces. It is a regex scraper feeding a closed
if/elif chain. Verified:

- 228 of 397 cards have **zero** executable leaves. Only 85 are fully executable.
- `gain_life` is implemented; `lose_life`, its exact mirror from the sibling regex, is not.
- Filters are stored as raw English — `{"type": "Creatures you control"}` — and the target
  filter never reads that key, so an anthem pumps the opponent's creatures, itself, and lands.
- Zero of 397 cards contain the string "enters the battlefield" after MTGJSON re-templating,
  and four code paths test for it. Forty triggers are silently dead.

## Scoring the options for pool conditioning

Higher is better. "Generalisation" means a card never seen during training.

| | Strength on trained pool | Generalisation | Inference speed | Engineering cost | Commander fit | Total |
|---|---|---|---|---|---|---|
| (a) Mixture of experts, one per set | 3 | **1** | 2 | **1** | **1** | 8 |
| (b) Set/format conditioning vector | 2 | 2 | **5** | **5** | 2 | 16 |
| (c) Compositional embeddings from rules content | **4** | **5** | 4 | 2 | **5** | 20 |
| (d) Pool summary / retrieved-pool embedding | **4** | 3 | 3 | 3 | **5** | 18 |
| **(e) Hybrid: (c) for cards + (d) for pool + a thin (b) token** | **5** | **5** | 4 | 2 | **5** | **21** |

### Why one-expert-per-set is not close

You raised this and worried about dynamic model size. That worry is real but it is not the
fatal objection. The fatal ones:

- **Sets are the wrong expert boundary.** A set is a *printing* concept. The thing worth
  sharing across cards is mechanics, and mechanics cross set boundaries freely. An expert for
  one set learns "that set's flavour", which is not a real thing.
- **Commander destroys the sparsity.** A single 100-card deck spans roughly 30 sets; a
  four-player pod spans about 200. The gate would activate essentially every expert on every
  decision, so you pay full dense cost and full memory traffic for zero specialisation — on a
  machine whose binding constraint is memory traffic per decision.
- **Zero generalisation.** A new set's expert starts at random initialisation. That directly
  fails the tied-rank-1 goal.
- **Checkpoint churn.** Adding a set changes the parameter shape. The repo already carries a
  shape-tolerant loader papering over exactly this pain, which silently loads partial models.

If mixture-of-experts is ever wanted, the correct axis is **mechanical function** — a learned
router over what a card *does* — and that comes free from (c) via attention. You do not need to
declare it.

### Why (c) is not an extra cost

The decisive argument: the engine **must** have a compositional executable card representation
to satisfy rank 1 at all. Once that tree exists, the neural encoder over it is a few hundred
lines. The engineering cost of (c) is shared with a mandatory engine cost.

## Recommendation: (e)

### Step 1 — Card → typed ability tree over a closed primitive vocabulary

Roughly 60 verbs, 40 filter predicates, 10 combinators. A genuinely closed vocabulary.

```
Card     := { mana_cost, types, subtypes, supertypes, pt?, loyalty?, abilities: [Ability] }
Ability  := Static(Effect) | Triggered(Event, Condition?, Effect)
          | Activated(Cost, Effect) | Spell(Effect) | Keyword(kw, params)
          | Replacement(Event, Condition?, Action)
Effect   := Seq[Effect] | Choose(n, [Effect]) | Optional(Effect)
          | Conditional(Pred, Effect, Effect?) | Repeat(Quantity, Effect) | Atom(Verb, Args)
Verb     ∈ { DEAL_DAMAGE, DESTROY, EXILE, DRAW, MILL, GAIN_LIFE, LOSE_LIFE, ADD_MANA,
             CREATE_TOKEN, PUT_COUNTER, MODIFY_PT, SET_PT, GRANT_ABILITY, TAP, UNTAP,
             MOVE_ZONE, SEARCH, SHUFFLE, COUNTER_SPELL, COPY, SACRIFICE, DISCARD, ... }
Selector := { count: Quantity, mode: TARGET|CHOOSE|ALL|RANDOM, filter: Filter, zone, controller }
Filter   := Conj/Disj over { type, subtype, supertype, color, cmc_cmp, pt_cmp, keyword,
                             name_eq, tapped, attacking, has_counter, controller }
Quantity := Const(n) | X | Count(Selector) | Prop(of, field) | add/sub/mul/max/min
Duration := UNTIL_EOT | PERMANENT | WHILE(Condition) | UNTIL_YOUR_NEXT_TURN
```

Three type constructors carry the compositional weight.

**Quantity on every numeric field, without exception.** This is what kills the "X spells and
dynamic power/toughness are special cases" problem. There is no `*`; there is a real expression.

**One Selector type used by targets, statics, counts, triggers, and search.** Structured, never
English. Because the affected set is re-evaluated against current state, the
"anthem pumps everybody" class of bug becomes unrepresentable.

**Structured EventSpec**, so Oracle re-templating can never silently disable a trigger again.
Enters-the-battlefield is a zone change from anywhere to the battlefield, not a substring.

Replacement effects share EventSpec with triggers deliberately: they are the same predicate
over the same typed event bus, differing only in whether they fire before or after. Commander
needs this for the command-zone replacement and commander tax, and today it does not exist at
all — replacement dispatches on two literal card-name strings.

Token creation takes a **nested card record**, not a string. Tokens become first-class, which is
also what lets the engine store identical tokens as a multiset with a count instead of one
entity each — the thing that would otherwise run out of memory on a token combo.

### Step 2 — Tree → card vector

Serialise the tree depth-first with explicit structural tokens (open, close, node type,
argument role), add a learned depth embedding and a parent-role embedding, and run a small
4-layer transformer. Pool with a learned card token.

**Take the linearised tree over a tree GNN.** The GNN is prettier and matches the
"is-ability-of edge" idea in `MTG_bot/notes.txt`, but the linearised form solves the binding
problem just as well via open/close plus depth and role embeddings, uses stock attention kernels
(which matters on a bandwidth-limited GB10), and is trivially cacheable. Embed numerals as
log-bucketed tokens so "deal 7" and "deal 8" are neighbours and "deal 4000" does not explode.

### Step 3 — Additive atomic residual, zero-initialised

```python
v_card = v_composed(tree) + gate * E_atomic[oracle_id]
# E_atomic weights INITIALISED TO ZERO, weight_decay toward zero,
# an unseen oracle_id is not in the table so the residual is exactly zero.
```

**This settles the Tarmogoyf-versus-Maro objection from `notes.txt`, and I think that objection
was wrong.** The argument was that a pure component model sees `Power = *` for both and cannot
learn that one depends on graveyards and the other on hand size, so a unique per-card id is
required. But `*` is not a primitive — it is a lossy parse. In a proper tree, Tarmogoyf is
"set power to count of card types across all graveyards" and Maro is "set power to count of
cards in your hand". Those are structurally different trees and a compositional encoder
separates them perfectly. **The fix belongs in the primitive vocabulary, not in an escape
hatch.**

Keep the residual anyway, for the reason chess engines keep piece-square tables: it captures
what composition genuinely misses — printed rate versus format, real-world play patterns, the
gap between what a card says and how good it is. But it must be additive, gated,
zero-defaulted, and droppable, so that:

> **The composition *is* the card. The atomic embedding is a learned correction that defaults
> to zero.**

Train with **atomic-id dropout at about 15%**, replacing the row with an out-of-vocabulary row.
This forces the policy to be able to play from composition alone. It is a regulariser, not a
hardcoded heuristic, and it costs nothing.

**Ship one diagnostic to the dashboard: the mean ratio of the residual's norm to the composed
vector's norm.** That number is the project's generalisation health gauge. If it climbs, your
primitive vocabulary is too weak and the model is memorising. It is the single number that
tells you whether the tied-rank-1 goal is being met.

### Step 4 — Fix identity first

Key everything on MTGJSON `identifiers.scryfallOracleId`, never on `cards.card_id`. Blockers
verified in the current code:

- `card_id` is an autoincrement rowid and the ingest drops the table, so re-ingest renumbers
  every card and silently invalidates every learned embedding row.
- 397 rows for 285 distinct names, so one card occupies three unrelated embedding slots.
- `card_id` and `game_vocabulary.id` share one integer axis and already collide.

Separate the namespaces before anything else.

## Pool conditioning, concretely

The purpose is not taxonomy. It is **"what should I be playing around?"** Build it as
retrieval, not as a summary:

```
pool_tokens =
    [ FORMAT_TOKEN(format_id, rules_deltas, banlist_hash_bucket) ]          # 1
  + [ v_card(commander_of_seat_i) for each seat ]                          # up to 4
  + [ POOL_SUMMARY: attention-pooled over the legal pool ]                 # 1
  + [ v_card(c) for c in retrieve_topk(query(board, belief), legal_pool) ] # k = 64..256
```

Appended to the board sequence with a pool role tag, and one hard rule: **pool tokens are keys
and values only, never queries.** They inform the board; they are not board objects. Refresh
once per turn, not per decision — the pool does not change mid-game, only the query does.

The retrieval query is a learned projection of the pooled board state and the belief vector,
trained end to end through the attention. Optionally add a cheap self-supervised auxiliary
loss: predict which pool cards the opponent actually revealed this game, harvested for free
from self-play logs. That loss is a literal implementation of "learn what to play around".

**Per-decision cost of the card encoder is zero.** A card vector depends only on the card, so
the whole pool is encoded once and cached as a tensor; during play it is an embedding gather.
Instance state — counters, tapped, damage, auras, zone — stays a separate small dynamic vector
concatenated at game time. Static card vector plus dynamic instance vector is what makes a
text-derived representation fast enough for near-real-time inference.

Memory traffic check: the whole of Magic is roughly 30,000 oracle cards at 1024 dims in bf16,
about 61 MB. Trivially resident, but reading all of it per decision costs real bandwidth, hence
two-stage retrieval — narrow to about 1,024 candidates once per game by format, colour identity
and observed commanders, then full attention over 256, refreshed per turn.

## Two independent flags, never one

```sql
format_legal     BOOLEAN   -- the banlist and set legality say yes
engine_supported BOOLEAN   -- every node in this card has an executor AND an encoder token
enabled = format_legal AND engine_supported
```

`enabled` is the "which cards are enabled" notion. It masks deck construction, draft, and any
deckbuilding suggestion. Today `cards.set_code` exists and **no query filters on it**, and the
config's card-subset setting is dead and points at a set that is not in the database.

A card that does not compile cleanly is **not in the enabled pool**. No silent degradation.
That flag is also the coverage instrumentation this project has never had.

## The three scenarios

**A new set releases.** Ingest, compile to trees. Every card whose text uses only known
primitives gets a vector immediately and plays correctly with zero code changes. Anything
containing an unparsed fragment goes to an explicit **unparsed queue** and is flagged
unsupported until a primitive is added. That queue is your own never-built idea from
`notes.txt`; there is currently no such queue and no coverage instrumentation at all, which is
why a third of rules sentences parse to zero atoms and nobody knew.

**A Commander pod where everything is legal.** Pool is roughly 25,000, format token is
Commander. The heavy lifting comes from the **per-seat commander vectors**: a commander in the
command zone is public information that constrains the entire hidden deck, colour identity plus
strategy. It is the single best predictor of what an opponent holds, it is free, and it falls
out of the same encoder with no extra machinery. This is the case where per-set experts collapse
completely and this design is at its strongest.

**Limited or sealed.** Pool is 45 to 90 cards, small enough that retrieval degenerates to full
attention. Same code path, no special case. And here the mean-pooled summary token — nearly
useless in Commander — carries real signal, because the strategic character of a sealed pool
genuinely is a low-dimensional property of the whole pool. Keeping both is not redundancy; they
are strong in complementary regimes.

## The compiler

Text to tree is an offline, versioned, **tested** compilation step, never a runtime regex.

1. Structured ingest first: types, subtypes, colours, mana value, keywords, oracle id,
   legalities, and the token list — all of which are currently discarded at ingest.
2. Template matching against a curated grammar, not free regex. Oracle text is highly
   templated; roughly 200 templates covers most of a modern set.
3. Everything unmatched goes to the unparsed queue, explicitly.
4. A golden file per card, committed. Re-ingesting against a newer MTGJSON produces a **diff**
   rather than a silent semantic change — which is precisely the failure that killed all forty
   enters-the-battlefield triggers.
5. Oracle id is the primary key everywhere, so re-ingest never invalidates learned embeddings.

## How to measure whether this worked

`NORTH_STAR.md` ranks auto-extension equal-first but nothing in the repo can measure it. Make
it a number: hold a set of cards entirely out of training decks, then evaluate play strength on
decks containing them with the atomic residual forced to zero. That is the tied-rank-1 metric.

## Ordering

1. Separate the id namespaces; re-key on oracle identity; add the two legality flags.
2. Define the tree grammar; write the executor against it.
3. Coverage instrumentation and the unparsed queue, from day one.
4. Encode the pool offline, cache it, wire composed plus zero-init residual.
5. Format token, commander tokens, pool summary. Ship. Add retrieval once the encoder is good.
6. Watch the residual-to-composed norm ratio. It is the gauge.
