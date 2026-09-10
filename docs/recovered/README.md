# Recovered documents

Design content that existed only in git history and would have been lost to anyone reading the
working tree. Restored to disk so it is findable without knowing which commit to look in.

| file | recovered from | what happened |
|---|---|---|
| `RL_ARCHITECTURE_pre_db5e024.md` | `git show db5e024^:MTG_bot/docs/RL_ARCHITECTURE.md` | A doc rewrite replaced **237 lines with 48**. The current `MTG_bot/docs/RL_ARCHITECTURE.md` retains almost none of the design reasoning. |

## Why this one matters

It is the owner's own architecture writing, and several ideas raised freshly in 2026-09 turn out to
have been written down here already, in more detail:

- **The Query Vector plus vector search over the card pool.** §5.1: *"For each slot, the model
  generates a Query Vector based on the current deck's synergy and the opponent's strategy. It
  performs a Vector Search against the card embedding pool to find the optimal card to add."* This
  is the drafter mechanism, written months before it was proposed again.
- **Per-decision proxies as the teacher's signal.** §5.1 lists the teacher's input as *"win rate,
  'confidence' gap, or reasoning depth used"*. The confidence and reasoning-depth half is the
  low-variance signal that the 2026-09-10 noise study independently concluded was the answer.
- **Frozen board cross-attention** (§4.1), which is the two-tier board cache in
  [`../COST_MODEL.md`](../COST_MODEL.md).
- **The rethink compute penalty** (§4.3), so the model learns its own optimal stopping point rather
  than being given a fixed pass count. This is [`../DECISIONS.md`](../DECISIONS.md) D11.
- **Belief vectors over hidden information**, with three named encodings for multi-opponent
  scenarios and the rule *"do not embed into every entity token"* (§6, §7).
- **Anti-meta-cycle machinery** for the teacher: matchup history and a diversity bonus to avoid
  A beats B beats C beats A loops (§5.2).

**One place the current design deliberately departs from it.** §5.3 proposes penalising the Teacher
for proposing illegal decks. [`../DESIGN_TEACHER.md`](../DESIGN_TEACHER.md) §8 rejects that: legality
is a rule of Magic, not a strategy, so it belongs in a hard mask that is free and exact rather than
in a penalty that wastes samples and creates a surface to game. That is a considered overrule, not
an oversight.

## The rule that follows

**Never replace a design document. Append to it, or move the old one here.** A rewrite that shortens
a doc destroys the reasoning while leaving the conclusions, and reasoning is the part a future
session actually needs.
