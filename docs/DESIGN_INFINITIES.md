# Design: infinities, loops, and combo play

Status: **proposed, not built.** This is the recommended answer to one of the two standing open
problems in [`NORTH_STAR.md`](../NORTH_STAR.md). It needs a decision before the engine is
rewritten, because two of its prerequisites are state-model decisions.

## The reframing that makes this tractable

**Magic has no infinite quantities.** It has arbitrarily large quantities *chosen by a player*.
The comprehensive rules never require representing infinity; rules 719 and 720 let a player
propose a shortcut and name a number of iterations, and rule 104.4b makes a loop with no
choices in it a draw. So the problem is not "how do we store ∞". It is four separate problems,
and conflating them is what has stalled it:

1. **Detection** — has the game returned to a state it has been in before?
2. **Classification** — mandatory (a draw) or optional (a player's choice)?
3. **Compression** — how do we execute a billion iterations without a billion engine steps?
4. **Learning** — how does the agent ever *find* the loop?

Number four is the hard one and the other three exist to serve it.

## 1. Detection: two fingerprints, not one

One hash cannot serve both consumers, because they need incompatible granularity.

`H_exact` includes everything: hand and library identity and order, exact counters, exact
damage, exact life, exact mana. It excludes instance ids, the global clock, and the absolute
turn number. It is what rule 104.4b needs, since a mandatory draw legally requires *exact*
repetition. It also gives you a transposition table for search and replay verification.

`H_struct` is deliberately lossy. Hidden and bulk zones collapse to counts per functional
class. Counters, damage, and multiplicity become presence-only. Life, mana, and library size
are excluded entirely and carried separately. That lossiness is the whole point: it fires on a
combo where the board is structurally identical but you have two more mana and one more token.

Losing exactness is safe because **every extrapolation built on `H_struct` is verified by
re-execution**, never trusted.

### The accumulator vector

Everything excluded from `H_struct` goes into a fixed integer vector `A` that is carried
exactly alongside it: per seat, life, poison, energy, commander damage, mana pool by colour,
zone sizes, lands played, cards drawn, storm count; and per object class, multiplicity,
counters by kind, and marked damage. An object class is a canonical content key — oracle id,
controller, zone, tapped, face-down, attachments, chosen modes, and which *kinds* of counter
are present but not how many.

Hashes are Zobrist-style and maintained **incrementally on mutation**, so fingerprinting is
amortised constant rather than proportional to state size.

### Six things that silently break this

Every one is a live footgun in the current code.

- The global clock and per-entity timestamps must be **excluded**. They increment on every
  entity creation, so including them means no fingerprint ever repeats.
- UUIDs must be excluded. Object references have to be canonicalised to content-derived
  ordinals.
- Continuous effects hash **by origin, never by materialised value**, or you double-count with
  the base characteristics already hashed.
- Turn number must be excluded, or infinite-extra-turn loops never repeat.
- Consecutive passes must be **included**, or two priority points with identical boards but
  different pass state look identical and you declare a false loop.
- **A real priority system is a hard prerequisite, not an optimisation.** A loop is defined at
  priority points, and "could the opponent have responded" is exactly what separates mandatory
  from optional. Today only one player ever holds priority.

## 2. Classification

A repeated `H_struct` is **never** automatically a draw. It raises a loop candidate, and
classification is mechanical:

- Accumulator delta is zero **and** `H_exact` also repeated, **and** no player faced a real
  choice anywhere in the cycle → **mandatory draw**, per 104.4b. No agent involvement.
- Accumulator delta is zero but someone had a choice → **optional null loop**. Offer the
  shortcut action with zero gain, and if every player with agency declines to leave the cycle
  for a full pass round, declare the draw. This is the judge asking "will you stop?".
- Accumulator delta is nonzero → **productive loop**. This is a combo. See below.

"A player had a choice" operationally means that player had more than one legal move at some
point in the cycle. That over-reports agency in rare cases where all the choices are
irrelevant, which is the safe direction: you offer a shortcut instead of an instant draw, the
agent declines, and you draw one cycle later.

## 3. Representing "infinity": a shortcut action, not an extended-number type

**Position: do not build an `ℕ ∪ {∞}` type.** Build `ShortcutLoop(cycle_id, n)` as a
first-class legal action, with symbolic fast-forward and stacked objects.

Four reasons the ∞ type is wrong:

- It has no rules basis. Magic produces a *player-named* quantity, not an infinite one.
- It poisons every arithmetic path in the engine. Every damage assignment, power/toughness
  calculation, counter add, cost payment, and comparison becomes infinity-aware. That is an
  enormous correctness surface bought for zero rules fidelity.
- Its semantics are genuinely undefined where it matters: ∞ minus 5, ∞ against ∞ in combat,
  infinite mill versus infinite draw (both empty a library, only one loses you the game).
- Most importantly, **it deletes the decision.** How many times to loop *is* the strategic
  content. Leave two mana up, or go all the way? Kill one opponent or three? Stop at twenty
  tokens because the fourth player has a board wipe? An ∞ type removes that from the action
  space. A shortcut action makes it a learned parameter.

### Three mechanisms make shortcuts exact

**Stacked objects.** Identical objects collapse into one entity carrying a multiplicity count.
Today `create_token` allocates one entity plus two relationships per token into a flat list
scanned linearly — that design runs out of memory on a token combo. With stacking, a billion
Squirrels is one row. Objects split out of the stack lazily, only when something individuates
one: targeting it, putting a counter on it, blocking with it. This is required for the multiset
hash anyway, and it is what the encoder wants too.

**Guarded linear extrapolation.** If the cycle body's behaviour does not depend on the
accumulator values over the extrapolated range, then `A' = A + n·ΔA` is exact. The bound `n_max`
comes from derived guards: floor-bounded coordinates like life and library size stop *at* the
boundary, and numeric thresholds are harvested from the ability trees of every object in a
public zone. That harvesting is automatic precisely because of the compositional card
representation in [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) — **this is where the two open
problems fuse.** Without a typed ability tree, the guards would be a growing table of
per-card special cases.

**Verification by re-execution.** Never trust the extrapolation. Run the cycle body concretely
twice and confirm the structural hash returns and the accumulator delta is identical both
times. Apply the delta for `n − 2` iterations. Then run the body **once more concretely** and
confirm the state is where the extrapolation predicted. If it is not, roll back through the
mutation journal and play it out by hand.

That requires a **mutation journal with rollback** in place of `copy.deepcopy`, which is
currently 6 ms per clone and therefore fatal to search as well. Neither prerequisite is
loop-specific work; both are needed anyway.

### How the agent picks `n`

A base action head selects the shortcut; a parameter head conditioned on that base action emits
a categorical over **log buckets** — 1, 2, 4, 8, … up to `n_max`, with `n_max` always present
as an explicit "go off" bucket. Log buckets because the difference between ten and eleven
iterations is nothing and between ten and a million is everything. The bucketing is a
representation choice; the policy over buckets is entirely learned.

The agent must be able to see what the loop is worth, so the observation gains a small token
per available cycle carrying the cycle length, `log1p(n_max)`, and the signed log of each
accumulator delta. **That is the only place a symbolic large-number notion belongs — as a
feature, never as engine state.**

## 4. Learning: how the bot actually becomes good at combo

This is the real question.

### The core rule

> **The engine never auto-shortcuts a productive loop. Discovery is unassisted; exploitation is
> free.**

The shortcut action only becomes legal *after* the agent has, by its own choices, executed the
cycle body once and produced a structural repeat. The agent must find the sequence. Once it
has, one action does the rest. This is exactly how a human plays a combo.

That resolves the dilemma cleanly: rollouts cannot hang, because one action closes an unbounded
loop, and the agent is not deprived of learning the loop, because it had to build it.

### But discovery is exponentially unlikely, and that is the actual problem

A six-action combo, in a Commander legal-move set of 50 to 200, found by epsilon-greedy
exploration, has odds around 200⁻⁶. It will never happen. Three mechanisms, in increasing order
of importance:

**Offline combo mining — the main engine of discovery.** After every self-play game, scan the
recorded trajectory for pairs of priority points with matching structural hash and nonzero
accumulator delta. Extract each as a macro: a precondition signature, the action sequence, the
per-iteration gain, and its provenance. Store them in a per-card-pool combo library. Thereafter,
whenever the state satisfies a macro's precondition, the engine offers "execute this macro" as
a *single* legal action alongside the atomic ones.

This is option discovery, with the termination condition supplied for free by the structural
hash, and it is **learned rather than authored** — nobody writes down which two cards combo. To
bootstrap an empty library, run offline combo search on frozen positions from real self-play:
depth-limited search restricted to loop-relevant *action classes* (mana abilities, sacrifice
outlets, untappers — a class filter, never a card list), looking for structural repeats with
positive gain. That is pure CPU, embarrassingly parallel, and it runs on the Grace cores while
the GPU trains. It is the ideal use of a machine whose rollouts are Python-bound rather than
FLOP-bound.

The agent still has to learn *when* the combo is good. All the mining does is make the sequence
reachable.

**Do not add a hand-tuned combo bonus.** With a discount of 0.99 and a six-step cycle, credit
reaches the setup actions fine; exploration is the problem, not credit assignment. A combo bonus
is exactly the reward shaping the charter forbids, and this repo already has thirteen such terms
that between them taught the agent to optimise shaping instead of winning. If a bootstrap is
genuinely needed, let the critic grade itself — a small clipped bonus proportional to the value
increase from taking the shortcut, annealed to zero on a **written removal condition**, and
logged as a scaffold.

**Remove the three reward-side blockers first.** Today the agent is actively trained away from
combos. The move cap pays −10 to whoever found the loop. The training loop blocks any action
repeated five times in a step, which is exactly what a combo body looks like. And it strips
mana actions after 100 "unproductive" steps, dismantling a combo's mana engine mid-assembly.
All three must go; the structural fingerprint subsumes all of them and does so exactly.

**Train against combo too.** Once the library is populated, seed the self-play league with decks
containing known macros. Learning to *interact* with combo — hold up the counterspell, kill the
piece — is half of Commander strength, and the league is the only thing that will teach it.

## 5. What must be capped, honestly

Be straight about this: **you cannot make non-termination purely incentive-based.** An incentive
is felt at episode end, and a non-terminating episode has no end. There must be a rail. The
design goal is that every rail be *sound* — never changes what a rational agent would do — and
*gradient-neutral* — never teaches the agent anything.

After this design, exactly three rails remain, and none of them is a policy cap.

| Rail | Value | Why it is sound and neutral |
|---|---|---|
| Wall-clock budget per episode | hardware-derived | On expiry, **truncate and bootstrap**: the return becomes reward plus discounted value estimate. This is the textbook-correct treatment of time-limit truncation and injects no preference for or against loops. Never assign a win, loss, or draw. Log every truncation; a rising rate is a bug alarm. |
| Distinct object-slot limit | e.g. 4096 *individuated* objects | With stacked objects this is unreachable in legal play. Hitting it is an engine bug: raise, discard the episode, alert. Never silently draw. |
| `n_max` on a shortcut | derived per cycle | Not a chosen number. It is the point at which extrapolation stops being sound. |

That trades four hand-tuned caps for one hardware-derived, gradient-neutral truncation.

**And the incentive part that already exists:** the mandatory-draw rule *is* an incentive. A
draw is worth roughly nothing. An agent that walks into a mandatory loop from a winning position
is punished by the rules of Magic rather than by a rail; an agent that walks into one from a
losing position is rewarded, correctly, because that is a real Magic play. That is the right
amount of reward design here: zero.

## Prerequisites, in order

1. Deterministic canonical state — integer handles instead of UUIDs, deterministic trigger
   ordering.
2. Real APNAP priority rounds.
3. Mutation journal with rollback, replacing `deepcopy`.
4. Stacked objects with multiplicity.
5. Incremental Zobrist `H_struct` and `H_exact`.
6. Loop candidate → classify → shortcut action with the parameter head.
7. Offline combo miner and per-pool macro library.
8. Delete the four caps; switch to truncate-and-bootstrap.
