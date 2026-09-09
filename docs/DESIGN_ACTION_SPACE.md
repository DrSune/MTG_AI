# Design: the action token grammar, the decoder, and trained multi-step planning

Status: **proposed, not built.** This is the design for D3 in [`DECISIONS.md`](DECISIONS.md),
the owner's three binding preservation requirements:

1. the structure where network output decomposes into actions, made into a real tokenizer;
2. multi-step planning with **every** step trained, however far down a plan it sits;
3. transferable learning of abilities, traits, stats and origins through learned encodings.

It is written against working-tree `000e37c`. Every code claim below was read, not remembered.
It composes with [`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) (§6),
[`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) (§7) and
[`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) (Tier A / Tier B, graph capture).
`docs/DESIGN_LATENCY.md` does not exist yet; §4.7 defines the seam it must honour.

---

## 0. The position, in one page

**A move is a short sequence of engine-typed fields, each filled by one masked softmax over a
single per-decision candidate table. A plan is `K` such moves emitted from one trunk forward,
executed until the engine's own verification says the next one is no longer legal.**

Two numbers judge this design, and both go on the dashboard from day one.

| Number | Definition | Why it is the right number |
|---|---|---|
| **m-bar** | mean actions executed per **trunk forward** | It multiplies the affordable model size. [`NORTH_STAR.md`](../NORTH_STAR.md) §1a defers the sizing decision until latency is measured, and D5 repeats it. At m-bar = 3 a 3x more expensive trunk fits the same per-decision clock. It also divides the 14.5 ms tokeniser cost (§5.7). |
| **mask fidelity** | complete sequences reachable through the mask decode to **exactly** the engine's legal-move set, no more and no fewer | A wrong mask makes a move permanently unreachable with no exception, no crash and no metric. It is the highest-severity silent failure this design carries. §8.1. |

m-bar is currently **fraudulent, not absent**. `train.py:228-306` really does execute five plan
steps. But every one of them is pushed into the buffer at `train.py:295-298` with step 0's
`log_prob` and step 0's `value` copied verbatim, and with `"action": best_move_idx` indexing
`current_legal` (built at `train.py:233-238`, possibly pass-filtered) while the stored
`obs["legal_action_descriptors"]` came from `_get_obs()` over the unfiltered list
(`environment.py:243-249`). The stored index and the stored candidate list address different
sets. So m-bar is 5 in wall-clock and 1 in learning. The job is to make those the same number.

### What is being replaced

Three disagreeing representations exist today and none of them is a tokenizer.

| Thing | Where | State |
|---|---|---|
| 65-float descriptor `[type, src_feats(32), tgt_feats(32)]` | built `action_mapper.py:43-92`, consumed `environment.py:244-249` | the live policy input |
| `[type, source_idx, target_idx]` integer triple | `action_mapper.py:158-199` and `:94-156`, indices into `_get_sorted_entities` (`action_mapper.py:201-210`) | **the structure the owner ordered preserved.** Reachable only via `environment.py:232-235`, called only from `test_self_play.py:24` and `test_training_flow.py:26` |
| 10-token decoder vocabulary | `model.py:88` | a *different* vocabulary. Id 8 is `TARGET` here and `MakeChoice` at `action_mapper.py:25`; id 9 `RETHINK` exists nowhere else; id 0 is `END` here and "unrecognised class" at `action_mapper.py:48` |

The descriptor carries no card identity, no entity identity, no controller and no phase.
`PlayLand(Forest#1)` and `PlayLand(Forest#2)` are byte-identical, because
`get_action_descriptor` writes only `StateConverter._extract_features`
(`state_converter.py:103-141`), which contains no identity field. Every `MakeChoiceAction` in
the five-name menu the engine offers at `engine.py:110-119` is the identical vector
`[8, 0...0]`, because `action_mapper.py:51` reads `card_id`/`blocker_id` and `MakeChoiceAction`
has neither (`actions.py:68-76`). **Preservation directive (3) has no action-side surface at
all today.**

There are also three mutually incompatible pointer index spaces: the policy pointer at
`model.py:172` points into the projected 65-dim descriptors; the plan decoder's
`source_logits` and `target_logits` at `model.py:129-130` point into
`cat([board_tokens, action_menu])` (measured `(1,220)`); `environment._format_plan`
(`environment.py:63-96`) decodes those same indices against `priority_entities + other_entities`
with the stack omitted, and it is unreachable anyway because it calls `torch.argmax`
(`environment.py:80,87,88`) while `torch` is never imported in that file
(`environment.py:1-16`). This design collapses all three into one.

### Positions taken, so they are not re-litigated

| Question | Position | Section |
|---|---|---|
| Flat action list, or grammar? | Grammar. The flat list is the grammar's fast path, not a rival. | 5.2 |
| Legality: mask, project, or pre-enumerate? | **Mask**, from an engine oracle. Projection rejected outright. | 5.2 |
| Verbs, numerals and pointers: one softmax or three heads? | **One** masked softmax over one padded candidate table. | 3.1 |
| Ratio granularity for a multi-field move | Action level, with a pre-registered fallback and a named diagnostic. Genuinely unresolved, see §10.1. | 4.3 |
| Target for a plan step that did not execute | The agent's own k-th subsequent action, or `END_PLAN`, weighted by advantage (AWR). Never plain cross-entropy. | 4.4 |
| Ratio for a plan step that did not execute | None. AWR carries no importance ratio, so PPO's trust region is untouched. | 4.4 |
| What makes ending a plan cost something | A real clock resource in the return, not an auxiliary loss term. | 4.7 |
| Set-valued slots | Canonicalise by candidate index and mask repeats. `ORDER_TRIGGERS` and `DAMAGE_ORDER` exempt, because there the order is the decision. | 5.5 |
| Batch > 1 and CUDA graphs | Pad the candidate axis, the field axis and `K` to buckets. This is what makes capture possible at all. | 3.4 |

---

## 1. The action token grammar

### 1.1 Three key sources, one candidate table

Every field is filled by a single masked softmax over one **candidate table** built once per
decision. A candidate's key comes from one of exactly three sources:

| Source | Key | Closed? |
|---|---|---|
| `VERB` | learned table `E_verb` | yes, 24 live rows plus 8 reserved |
| `NUM` | learned table `E_num` over log buckets | yes, 44 live rows plus 4 reserved |
| `PTR` | a **runtime-encoded** object / ability / option / mode / cycle vector | not a table, so no vocabulary growth |

**The vocabulary is closed precisely because pointers are not in it.** A card, ability, token,
stack object, trigger, mode or choice option never seen in training reaches the head as a
composed vector from the card encoder ([`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md) step 2),
never as an index into a table. That is the whole mechanism for preservation directive (3) and
for the tied-rank-1 entry in [`NORTH_STAR.md`](../NORTH_STAR.md) §1.

### 1.2 The closed vocabularies

```
V_struct (6)   BOS  EOA  END_SET  END_PLAN  NULL  PAD

V_verb (24 live, 8 reserved OOV rows)
  PLAY_LAND  CAST  ACTIVATE  ACTIVATE_MANA  SPECIAL_ACTION
  ATTACK_SET  BLOCK_ASSIGN  ORDER_TRIGGERS  ORDER_DAMAGE
  RESOLVE_CHOICE  MULLIGAN_TAKE  MULLIGAN_KEEP
  SHORTCUT_LOOP  PASS_PRIORITY  PASS_UNTIL  PASS_TURN  CONCEDE
  (7 further live rows held for new choice verbs, then 8 reserved)

V_role (34 live, 8 reserved)     emitted by the ENGINE, never by the network
  LAND  SPELL  ABILITY  MANA_ABILITY  SPECIAL_SLOT
  MODE  OPTION  X_VALUE  TARGET  DIVIDE_SHARE  PAYMENT  COST_TARGET
  ATTACKER  DEFENDER  BLOCKER  BLOCKED  DAMAGE_ORDER
  TRIGGER_SLOT  CHOICE_SLOT  CHOICE_OPTION  POOLCARD  ENUM_COLOR  ENUM_TYPE
  CARD_TO_BOTTOM  CYCLE  ITERATIONS  STOP_CONDITION  ROLE_OPAQUE  ...

V_num (44 live, 4 reserved)
  0..20 literal, then log buckets 24,32,48,64,96,128,192,256,384,512,
  1k,4k,16k,64k,256k,1M,2^30, plus N_MAX
```

`V_role` is a **type tag on the field**, not a token the policy emits. It selects which
projection `W_role[role]` is applied to a candidate's vector when its key is formed. Roles are
structure; they cost the policy nothing and they save one decode step per field compared with a
grammar that emits `WITH_TARGETS`-style opener tokens. On a machine where the tail is decode
steps and kernel launches, that is not a stylistic preference.

### 1.3 Verb to field schedule

The engine, not the network, supplies the schedule. `*` means a repeated field terminated by
`END_SET`. `?` means the field may be inactive (§1.5).

| Verb | Field schedule (role, kind) |
|---|---|
| `PLAY_LAND` | `LAND:PTR` |
| `CAST` | `SPELL:PTR`, `OPTION:PTR*`?, `MODE:PTR*`?, `X_VALUE:NUM`?, `TARGET:PTR` x n?, `DIVIDE_SHARE:NUM` x n?, `COST_TARGET:PTR*`?, `PAYMENT:PTR*`?, `EOA` |
| `ACTIVATE` | `ABILITY:PTR`, `OPTION:PTR*`?, `MODE:PTR*`?, `X_VALUE:NUM`?, `TARGET:PTR` x n?, `COST_TARGET:PTR*`?, `PAYMENT:PTR*`?, `EOA` |
| `ACTIVATE_MANA` | `MANA_ABILITY:PTR` |
| `ATTACK_SET` | (`ATTACKER:PTR`, `DEFENDER:PTR`)`*`, `PAYMENT:PTR*`? (attack costs), `EOA` |
| `BLOCK_ASSIGN` | (`BLOCKER:PTR`, `BLOCKED:PTR`)`*`, (`BLOCKED:PTR`, `DAMAGE_ORDER:PTR*`)`*`, `EOA` |
| `ORDER_TRIGGERS` | `TRIGGER_SLOT:PTR*` |
| `RESOLVE_CHOICE` | `CHOICE_SLOT:PTR`, (`CHOICE_OPTION:PTR` or `POOLCARD:PTR` or `ENUM_*:PTR` or `NUM`)`*`, `EOA` |
| `MULLIGAN_TAKE` | (none) |
| `MULLIGAN_KEEP` | `CARD_TO_BOTTOM:PTR*` |
| `SHORTCUT_LOOP` | `CYCLE:PTR`, `ITERATIONS:NUM` |
| `SPECIAL_ACTION` | `SPECIAL_SLOT:PTR`, `ROLE_OPAQUE:PTR*`? |
| `PASS_PRIORITY`, `PASS_TURN`, `CONCEDE` | (none) |
| `PASS_UNTIL` | `STOP_CONDITION:PTR` |

Three of these are rules corrections, not re-encodings, and each is load-bearing.

**Attacking is one move.** `engine.py:180-183` emits one `DeclareAttackerAction` per creature.
That is not Magic (CR 508.1 declares attackers simultaneously) and it destroys credit
assignment: the value of attacking with five creatures is not the sum of five independent
values.

**Blocking is a matching plus a damage order.** `engine.py:141-148` emits one action per
`(blocker, attacker)` pair, which is not a block declaration, and CR 509.2 damage ordering does
not exist anywhere in `actions.py:1-84`.

**Mana payment folds into the move that needs it (CR 601.2g).** Paying costs is part of casting;
a human does not make five decisions to tap five lands. `ActivateManaAbilityAction` survives
only as `ACTIVATE_MANA`, for deliberate floating, which is a real play. This removes the largest
distortion in the measured option distribution: over 3,000 Commander decisions, 12,263 of 16,247
offered options (75.5%) were `ActivateManaAbilityAction`. It is also
[`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §4's top throughput lever, and it is the single
largest cleanup of the plan head's training distribution available.

**`PASS_UNTIL` is a genuine rules shortcut (CR 719), not a strategy heuristic.**
`PassPriorityAction` appeared in 3,000 of 3,000 measured menus and 21.2% of decisions had
exactly one legal move. Priority shortcuts are legal Magic and one of the largest available
clock wins.

### 1.4 The Slate: one engine call per decision

```python
@dataclass(frozen=True)
class Field:
    role: int                  # V_role tag
    kind: int                  # VERB | NUM | PTR | STRUCT
    dep:  int                  # STATIC | EXCLUSIVE | ARITH | DEPENDENT   (see 3.3)
    mask: np.ndarray           # (C_pad,) bool, the prefix-independent part
    active_on: Optional[tuple] # (field_idx, candidate_set) gating this field's existence
    forced: bool               # exactly one legal filler, so no decode step

@dataclass(frozen=True)
class Slate:
    handles:   np.ndarray      # (C_pad,) int32 stable engine handles; PAD rows are -1
    kinds:     np.ndarray      # (C_pad,) key source per candidate
    roles_ok:  np.ndarray      # (C_pad, R) bool: candidate is type-valid for role r
    mana:      np.ndarray      # (C_pad, 7) float32 mana produced, for ARITH payment fields
    fields:    list[Field]     # the maximal field schedule, len <= F_pad
    valid:     np.ndarray      # (C_pad,) bool, padding mask
```

`Slate` is produced by **one** engine call per decision, `engine.decision_slate(seat)`, not one
per field. That is the load-bearing latency decision in this document.

Measured on this box over 400 real Commander decision states: `get_legal_moves()` is 0.432 ms
mean and 1.301 ms p99; `convert_graph_to_tokens()` is 14.5 ms mean and 23.7 ms max. Counted
hardware-independently: one `num_passes=1` forward issues 515 real kernel launches, and eight
forced passes issues 3,925, which on the Spark's ARM cores at 6 to 10 us dispatch is 24 to 39 ms
of pure host dispatch before a single byte of weight is read. On top of that,
`model.py:142-143` is a literal `if next_type.item() == 0 or next_type.item() == 7: pass`:
two device synchronisations per plan step, ten per reasoning pass, doing nothing.

A per-field engine round trip would put that cost structure back on every multi-field action.
One call up front, masks resident as tensors, the whole padded field schedule decoded with
**zero host synchronisation**, is the only shape that survives the measured dispatch problem.

**`forced` is the field-level generalisation of the biggest throughput lever in
[`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §4** ("auto-resolve states with exactly one legal
action, 40 to 70% fewer decisions"). At field granularity it fires far more often than at action
granularity: a spell with exactly one legal target auto-fills the target field, a unique payment
auto-fills the whole payment set. It changes nothing a rational agent would do, so it passes the
learnability test the same way the action-level version does.

### 1.5 Dynamic schedules without dynamic shapes

Sublime Epiphany's target count depends on which modes were chosen. That is a schedule whose
length depends on an earlier field, which would break fixed-shape capture. It is handled with no
control flow at all: the Slate carries the **maximal** schedule, and a field whose `active_on`
predicate is not satisfied by the realised prefix has its mask collapsed to `{NULL}` and is
therefore `forced`. The decode still runs it (constant shape, one padded step) and it contributes
no loss and no entropy. Dynamic grammar, static tensor.

---

## 2. Four M21 actions, tokenized end to end

All four use real rows from `MTG_bot/data/mtg_bot.db` (set `M21`, the only set present). Card
ids, oracle text and `effects_json` below are read from that database.

### 2.1 `PLAY_LAND` a Mountain (`card_id` 269)

Hand holds Mountain#1, Mountain#2, Fabled Passage. Pre-combat main, land drop available
(`engine.py:155-158`).

| Step | Field (role, kind) | Mask size | Emitted |
|---|---|---|---|
| 1 | verb, VERB | 6 of 32 | `PLAY_LAND` |
| 2 | `LAND`, PTR | 3 | `PTR(h_Mountain#2)` |

**2 tokens.** Today those two Mountains produce byte-identical 65-float descriptors, so the
policy cannot express a preference between them even where the instances differ (one tapped by
a previous effect, one with a counter, one that entered this turn). Here they are two distinct
pointer keys built from two distinct instance vectors. If the hand held one land, the `LAND`
field is `forced` and the move costs zero decode steps.

### 2.2 `ACTIVATE` Scavenging Ooze (`card_id` 204), `{G}: Exile target card from a graveyard`

DB `effects_json`:
`[{"ability_type": "activated_ability", "cost": "G", "effects": [{"ability_type": "gain_life", "amount": 1}, {"ability_type": "exile", "target_raw": "target card from a graveyard"}, {"ability_type": "add_counter", "counter_type": "+1/+1"}]}]`.
Board: Ooze#1 on my battlefield, Forest#3 and Forest#5 untapped, opponent's graveyard holds
Grasp of Darkness and Terror of the Peaks.

| Step | Field | Mask | Emitted |
|---|---|---|---|
| 1 | verb | `{CAST, ACTIVATE, ACTIVATE_MANA, PASS_PRIORITY, PASS_UNTIL}` | `ACTIVATE` |
| 2 | `ABILITY`, PTR | activatable ability instances, here 1 | `PTR(ab(Ooze#1, 0))` **forced** |
| 3 | `PAYMENT`, PTR, ARITH | green sources able to complete `{G}`: 2 | `PTR(Forest#3)` |
| 4 | `PAYMENT`, PTR, ARITH | cost satisfied, so `{END_SET}` only | `END_SET` **forced** |
| 5 | `TARGET`, PTR | cards in any graveyard: 2 | `PTR(TerrorOfThePeaks@gy2)` |
| 6 | `EOA` | forced | `EOA` |

**Two real decode steps** (3 and 5); the rest are forced and cost nothing.

Two things this demonstrates that today's action space cannot express at all.
`actions.py:1-84` defines exactly eight dataclasses and there is **no generic
`ActivateAbilityAction`**, so this move does not exist. And `ActivateManaAbilityAction.ability_id`
is a bare int (`actions.py:36`) encoded only indirectly through descriptor dims 20-26
(`action_mapper.py:61-76`), with a live truthiness bug at `action_mapper.py:76` (`if idx:`,
which happens to work today because White is index 20 and silently drops any future index 0).

Here the `ABILITY` candidate's key is
`W_role[ABILITY] . (h_object (+) v_node(Activated{Cost{G}, Exile(Selector{zone: GRAVEYARD})}))`.
That node vector is the *same vector* for every one-green-mana graveyard-exile outlet ever
printed. "Activate the graveyard hate" transfers to cards the model has never seen, which is
preservation directive (3) with a concrete mechanism instead of a hope.

### 2.3 `CAST` Sublime Epiphany (`card_id` 74), `{4}{U}{U}`, two modes

Oracle: "Choose one or more" over five modes. DB `effects_json` carries four `selector` nodes and
**zero** `target` keys, which is exactly why `get_spell_potential_targets`
(`handlers/effect_handlers.py:105-113`, `criteria = effect.get("target")`) returns `[]` for it
and `engine.py:177-178` emits a single untargeted `CastSpellAction`. Chosen: mode 0 (counter
target spell) and mode 2 (return target nonland permanent to owner's hand). Opponent's Volcanic
Salvo is on the stack; opponent controls Terror of the Peaks. I control Island#1-3 and
Forest#1-3, all untapped.

| Step | Field | Mask | Emitted |
|---|---|---|---|
| 1 | verb | castable now | `CAST` |
| 2 | `SPELL`, PTR | castable cards, 3 | `PTR(SublimeEpiphany@hand)` |
| 3 | `OPTION`, PTR | no optional costs on this card, so `{NULL}` | `NULL` **forced** |
| 4 | `MODE`, PTR | 5 mode slots | `PTR(mode0)` |
| 5 | `MODE`, PTR | 4 remaining (EXCLUSIVE) plus `END_SET` | `PTR(mode2)` |
| 6 | `MODE`, PTR | 3 remaining plus `END_SET` | `END_SET` |
| 7 | `X_VALUE`, NUM | inactive, `active_on` fails | `NULL` **forced** |
| 8 | `TARGET` (mode0), PTR | spells on the stack: 1 | `PTR(VolcanicSalvo@stack)` **forced** |
| 9 | `TARGET` (mode2), PTR | nonland permanents: 7 | `PTR(TerrorOfThePeaks@bf2)` |
| 10 | `PAYMENT`, PTR, ARITH | 6 sources, cost 6, `UU` forces the Islands | all six **forced** |
| 11 | `EOA` | forced | `EOA` |

**14 emitted tokens, of which 4 are real decode steps** (2, 4, 5, 9); step 6 is a two-way choice
and steps 3, 7, 8, 10, 11 are forced. The payment fold (§1.3) replaces what would be six separate
`ActivateManaAbilityAction` MDP decisions today, each with its own advantage, its own PPO ratio,
and its own contribution to the 75.5% mana skew.

This move is unrepresentable today at every level: `CastSpellAction` (`actions.py:18-29`) has
exactly one `target_id` and one `cost_target_id`, no modes, no X, no payment choice.

### 2.4 `BLOCK_ASSIGN` against Terror of the Peaks (`card_id` 164)

Attackers: Terror of the Peaks (5/4, Flying, DB text line 1) and Scavenging Ooze (2/2). Blockers
available: Barrin, Tolarian Archmage (`card_id` 45, 2/2, no flying or reach) and a 2/2 token.
The `BLOCKED` mask for Barrin **excludes Terror of the Peaks**, because CR 509.1b plus the
flying evasion check says so. That is the engine being correct, not a heuristic; today
`combat_handlers.get_legal_blockers` performs no evasion check at all, which
[`ARCHITECTURE.md`](ARCHITECTURE.md) lists in its verdict paragraph.

| Step | Field | Mask | Emitted |
|---|---|---|---|
| 1 | verb | `{BLOCK_ASSIGN, PASS_PRIORITY}` | `BLOCK_ASSIGN` |
| 2 | `BLOCKER`, PTR | 2 legal blockers plus `END_SET` | `PTR(Barrin#1)` |
| 3 | `BLOCKED`, PTR | attackers Barrin may block: 1 (Terror masked out by Flying) | `PTR(Ooze@atk)` **forced** |
| 4 | `BLOCKER`, PTR, EXCLUSIVE | 1 remaining plus `END_SET` | `PTR(Token#2)` |
| 5 | `BLOCKED`, PTR | 2 | `PTR(Ooze@atk)` |
| 6 | `BLOCKER`, PTR, EXCLUSIVE | `END_SET` only | `END_SET` **forced** |
| 7 | `BLOCKED` (order), PTR | blocked attackers with more than one blocker: 1 | `PTR(Ooze@atk)` **forced** |
| 8 | `DAMAGE_ORDER`, PTR | its 2 blockers | `PTR(Barrin#1)` |
| 9 | `DAMAGE_ORDER`, PTR, EXCLUSIVE | 1 remaining | `PTR(Token#2)` **forced** |
| 10 | `END_SET`, `EOA` | forced | `END_SET`, `EOA` |

**One MDP action for the whole assignment plus the CR 509.2 damage order**, with 4 real decode
steps. Today this is two separate `DeclareBlockerAction` MDP decisions with independent
advantages and no damage order at all. The exclusivity in steps 4, 6 and 9 is computed **on
device** from a running bitmask (§3.3), with no engine round trip.

---

## 3. The decoder and legality masking

### 3.1 One masked softmax per field

Verb rows, numeral rows, structural rows and pointer rows all live in the **same** padded
candidate table, so there are not three heads with three incommensurate logit scales. There is
one query, one key set, one softmax.

```
# built once per decision
K_ptr    = W_role[role_f] @ h_cand                 # (C_pad, d) for PTR candidates
K_tab    = E_verb / E_num / E_struct rows          # (C_pad, d) for closed-vocab candidates
K        = where(kinds == PTR, K_ptr, K_tab)       # (C_pad, d)

# per field f
q_f      = dec_step(state, role_emb[role_f], slot_idx_emb[f], k_emb[k])   # (d,)
z_f      = (K @ q_f) / sqrt(d)                                            # (C_pad,)
z_f      = z_f.masked_fill(~mask_f, -1e30)
p_f      = softmax(z_f)
```

`h_cand` is the Tier-A / Tier-B encoder output for that object, ability, mode or option, so a
pointer to a permanent is the *contextually encoded* permanent, not a re-extracted feature
vector. Pointer logits are one matvec against a tensor that already exists. This is why the
old `ActionPointerHead.action_proj` (`model.py:153`, a `Linear(65, 1024)` over hand-written
floats) disappears rather than being ported.

### 3.2 Legality: masking, and why the two alternatives lose

**Position: (i) incremental engine-supplied masking. (iii) pointer-over-pre-enumerated-list is
the degenerate case of (i) on atomic moves, not a rival. (ii) decode-then-project is rejected
outright.**

**Against (ii).** Two objections, either of which is fatal.

1. "Nearest legal move" requires a distance metric over actions, and any such metric is a
   hand-authored strategic prior: it decides that Shock at a creature is nearer to Shock at the
   face than to Grasp of Darkness at that creature. [`NORTH_STAR.md`](../NORTH_STAR.md) §3 says
   default-no to exactly that, and it would steer the policy silently.
2. It makes emit-X-execute-Y the normal operating mode. PPO's ratio is a ratio of probabilities
   of *the action that was taken*; if the projector changed it, the gradient credits a different
   action. This repo already demonstrates that pathology in miniature at `student.py:126-129`,
   which subtracts up to 10 nats from every pass logit at collection while
   `student.py:180-181` does not at training, pinning the ratio to e^(+/-10) on every pass
   action. Projection is that bug generalised to every action.

**Against (iii) as the sole mechanism.** Menu size is nearly free for the *network*: measured,
going from 1 to 256 legal actions costs about 9% of forward time. That fact is real and is why
(iii) survives as the fast path. But it measures the wrong cost. The cost of pre-enumeration is
in the *engine* and it is multiplicative: a block assignment over 8 blockers and 5 attackers is
6^8, a modal spell with X and three targets from 30 candidates is unbounded, damage division is
a composition rather than an enumeration. The measured p99 of 19 options and max of 26 are
artefacts of a crippled engine (75.5% of options are "tap a land", `MakeChoiceAction` fired 0
times in 3,000 decisions, and 0 creatures reached the battlefield in an entire 1,500-decision
game). Sizing an action space against those numbers is sizing against
`handlers/effect_handlers.py:111`.

Masked decoding turns the product into a sum: cost is O(fields x candidates) instead of
O(product of slot sizes).

**Why (i) is not hardcoding.** The mask *is* the engine's legality function, evaluated
incrementally. [`NORTH_STAR.md`](../NORTH_STAR.md) §3's corollary is explicit that the rules of
Magic are not heuristics. Under
[`DESIGN_CARD_POOL.md`](DESIGN_CARD_POOL.md)'s one-representation commitment the same
`Selector` node the executor evaluates is what produces the pointer slate, so the mask
structurally cannot drift from the executor the way `selector` drifted from `target`. Illegal
tokens get probability exactly zero and zero gradient, `log pi` is exact, the PPO ratio is
exact, and the entropy bonus is over the true support.

**(iii) falls out for free.** For `PLAY_LAND` and `ACTIVATE_MANA` the move is one verb plus one
pointer, and the pointer's mask is exactly today's legal-move list. So masked decoding
*collapses to* pointer-over-enumerated-list on the atomic decisions, which is the large majority,
and only pays sequence cost on the combinatorial ones. One mechanism, no second code path.

### 3.3 Four dependency classes, so the mask does not become a lattice

A naive incremental mask is O(F x C_prev x C) and would either explode in memory or force an
engine round trip per field. It does not, because legality dependence falls into four classes
and only the last needs the engine.

| Class | Meaning | Cost |
|---|---|---|
| `STATIC` | the mask does not depend on any earlier field | precomputed in the Slate, free |
| `EXCLUSIVE` | static mask minus already-emitted candidates | a running bitmask on device, zero engine calls. Covers attacker sets, blocker sets, target lists, mode lists, cards to bottom, damage order |
| `ARITH` | legality is a closed-form arithmetic predicate over a per-candidate vector carried in the Slate | on device. Covers payment sufficiency: `Slate.mana` (C_pad, 7) plus the remaining cost gives the mask by comparison, and `END_SET` unmasks exactly when the running total covers the cost |
| `DEPENDENT` | genuinely needs the engine | `late_validated`: decode the field unmasked, one `engine.validate(prefix)` call, resample that single field from the corrected mask on failure |

`ARITH` is what removes the single most common dependent field. `EXCLUSIVE` is what removes the
combinatorial one. What is left in `DEPENDENT` is a genuinely small residue (divided-damage
remainder constraints, some replacement-effect interactions), and **its size is not yet known**,
because the current engine cannot produce a single hard slate. That is §10.4, and §8.4 gives the
measurement that must land before this part of the design is committed.

**Completability is an obligation, not a hope.** Masked autoregressive decoding does not by
itself guarantee that every allowed prefix can be completed. `Field.mask` must admit only
tokens for which a legal completion exists: `END_SET` masked until the minimum count is met,
elements masked when choosing them would make the remainder unsatisfiable. That is constraint
propagation inside the builder and it is the thing that will silently rot. §8.1 puts it in CI.

**Termination is proved by construction, not capped.** Every reachable parser state has a
non-empty mask, because every field has either a sentinel (`END_SET`, `NULL`, `EOA`) or at
least one legal filler, or the verb that opened it would not have been legal. Maximum sequence
length is bounded by the schedule depth times the candidate count. This is a genuine
non-termination rail in the sense [`NORTH_STAR.md`](../NORTH_STAR.md) §3 allows, enforced by an
invariant test rather than by a length cap.

### 3.4 Batch > 1 and CUDA graph capture

This is the part the flat-list design cannot have and the reason the shapes are padded.

Today the batch dimension is structurally pinned to 1: `model.py:172` produces logits whose
length equals the legal-move count exactly, with no padding and no mask, so two states with
different menu lengths cannot share a tensor. `model.py:142` adds two device syncs per plan
step, `model.py:243-247` does `.any()` on a device tensor followed by a Python `break`, and
`model.py:206` passes no `src_key_padding_mask`. [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §5
lists all four as graph-capture blockers and calls CUDA graphs mandatory on this machine.

The fix is one idea applied three times: **pad every variable axis to a bucket and mask.**

| Axis | Buckets | Padding |
|---|---|---|
| candidates `C` | 32, 64, 128, 256, 512 | `valid` mask, PAD rows keyed to a learned constant |
| fields `F` | 2, 4, 8, 16 | inactive fields collapse to `{NULL}` and are forced (§1.5) |
| plan steps `K` | 1, 2, 4 | see below |

The batched inference server ([`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §4) buckets requests by
`(K, F, C)` and runs one captured graph per bucket. Inside a graph:

- the whole `K x F` decode is one captured launch sequence, so the 24 to 39 ms of ARM dispatch
  measured at eight reasoning passes collapses to a single submission;
- sampling is a captured Gumbel-argmax against a pre-supplied noise buffer, so there is no
  `Categorical(...).sample().item()` host sync of the kind at `student.py:136`;
- there is no data-dependent control flow anywhere, because `forced` fields still decode and
  inactive fields still decode.

`K` is chosen by the **previous** decision's hazard head (§4.5), so the choice of graph is made
one decision ahead and never breaks the current capture. That is the learned-allocation
mechanism [`NORTH_STAR.md`](../NORTH_STAR.md) §1a asks for, applied to the planning axis. The
bucket *ladder* is hand-chosen and is logged as a scaffold (§9, S2 and S3).

### 3.5 Sizing, and why the decoder must be narrow

The action decoder sits on top of Tier B ([`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §2), reads
`h_t` and the Tier-B outputs, and keeps a KV cache across the whole `K x F` decode. Its width is
a latency decision, not a capacity decision.

| Decoder | Params | bf16 bytes | Bytes per decode step | 32 steps at 273 GB/s |
|---|---|---|---|---|
| 2 layers, d=1024, ff=4096 | 33.6M | 67 MB | 67 MB | **7.8 ms**, unaffordable |
| 2 layers, d=256, cross-attn keys projected from 1024 | ~2.8M | 5.6 MB | 5.6 MB | **0.66 ms** |

Take d_dec = 256. The queries are narrow; the keys are the full-width encoder outputs projected
by `W_role`. Compare the thing being replaced: `ActionSequenceDecoder` is 4 `nn.TransformerDecoder`
layers at d=1024 (`model.py:93-94`, 50,401,280 params) that re-runs its entire growing prefix
every step with no KV cache (`model.py:117-122`), and measures **31.67 ms of a 64.04 ms forward,
49.5%**, more than the entire 16-layer board encoder at 28.97 ms. Ninety per cent of that cost
is plan steps 1 to 4, which receive exactly zero gradient today because `model.py:171` slices
step 0 only.

---

## 4. Training every plan step

### 4.1 Notation

At **replan** `t`, in state `s_t` with recurrent state `h_t`, **one** trunk forward produces:

- a plan `P_t = (a^0 ... a^(K-1))`, each `a^k` a padded field-token sequence `(u^k_1 ... u^k_F)`;
- a per-step hidden `h^k`, a per-step **value** `V^k`, and a per-step **hazard logit** `f^k`.

Execution: `a^0` executes. Then for `k = 1 ... K-1` the engine is asked whether `a^k` is still
legal *as a token sequence*: rebind each handle (is that object still that object, still in that
zone) and re-check each filler against the engine's legality predicate. First failure aborts.
`m_t` is the number of steps executed. `tau(t,k)` is the global index of the k-th action this
seat actually takes after the replan.

**Verification does not re-tokenise the board.** It is O(fields) handle rebinds plus per-filler
legality, one engine call per plan step, not a fresh Slate and not a
`convert_graph_to_tokens`. This is the specific reason m-bar is not hostage to the 14.5 ms
tokeniser; see §5.7 for what the dependency actually is.

### 4.2 The six terms

```
L = L_ppo  +  lambda_a * L_awr  +  c_v * L_v  +  lambda_f * L_feas
             +  lambda_m * L_mask  +  lambda_l * L_lat  -  c_H * H
```

### 4.3 (1) Executed steps: PPO, each with its own advantage

For `k < m_t` the plan step is an on-policy sample from `pi_theta(. | s_t, h_t, a^(<k))`, so the
ratio is well defined:

```
rho_(t,k) = exp( sum_f [ log pi_theta(u^k_f | s_t, h_t, a^(<k), u^(<f))
                       - log pi_theta_old(u^k_f | .) ] )

L_ppo = - E_(t, k<m_t) [ min( rho_(t,k) * A_tau(t,k),
                              clip(rho_(t,k), 1-eps, 1+eps) * A_tau(t,k) ) ]
```

Three things to be exact about.

**Conditioning is on `s_t`, not on the state at execution.** Plan step k genuinely is the object
"what I will do k actions from now given what I knew at t". Conditioning on `s_tau(t,k)` would be
a different object and a useless one, because at execution time we have deliberately not paid for
a forward pass.

**The advantage is `A_tau(t,k)`, the GAE advantage at the time the step acted**, never step 0's.
This is the single bookkeeping change that turns `train.py:295-298` from a wrong-label bug into
directive (b).

**Store the token sequence and the mask, never the log-prob.**
[`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §5 already prescribes recomputing the old log-prob to
avoid the FP8-actor / bf16-learner ratio trap; extend it to the mask so the support is
reconstructed exactly. That one change also kills, for free: the proactivity-bias offset
(`student.py:126-129`), and the collection-time dropout mismatch (`student.py:102` calls
`self.model.train()` whenever `requires_grad=True`, and 184 `aten.native_dropout` calls were
measured in one such forward).

**Store the mask bitset; do not recompute it from the engine.** Entity ids come from
`uuid.uuid4()` (`actions.py:6` and the graph), there is no `random.seed`, and zone-change
triggers are computed by set differences of UUIDs. A recomputed mask can legitimately differ
from the collected one; the renormalisation then differs; the resulting log-prob error is
indistinguishable from real policy movement. A 512-wide mask is 64 bytes. Assert equality
against a recompute on 1% of samples and alarm on mismatch.

**Ratio granularity.** The move is the MDP action, so the ratio is per action, the product over
its active fields. A field-level ratio would clip a 14-field modal X spell fourteen times as hard
as a 2-field land drop and bias the policy toward short moves. The observable symptom of that
failure is "the bot stopped casting spells and just plays lands and passes", which this repo has
already met once and answered with the proactivity bias. Diagnostic that decides the fallback:
**clip fraction stratified by move field count**. If more than 20% of long moves leave the clip
band on PPO epoch 1, switch to a per-field ratio with a shared move-level advantage. I could not
settle this analytically; see §10.1.

### 4.4 (2) Non-executed steps: advantage-weighted regression, no ratio

The chicken and egg: plans only train if they execute, and only execute if trained. Early in
training `m_t = 1` always, and PPO alone reproduces exactly the status quo the owner is
correcting.

For `k >= m_t` the target `a*_tau(t,k)` is **the agent's own k-th subsequent action**, taken from
the log. That action was sampled from `pi(. | s_tau)`, a different distribution, so there is no
valid importance ratio. Therefore use none:

```
L_awr = - E_(t, m_t <= k < K) [ w_(t,k) * log pi_theta(a*_tau(t,k) | s_t, h_t, a^(<k)) ]

w_(t,k) = min( exp(A_tau(t,k) / beta), w_max ) * surv_(t,k)
surv_(t,k) = prod_(j<k) hazard_label_j          # from the LABEL, not the prediction
```

**PPO for executed steps, AWR for non-executed steps, never mixed.** Advantage weighting is what
stops this being behavioural cloning of the agent's own mistakes: plain cross-entropy on your own
on-policy actions has its fixed point at the current policy, adds zero information, injects the
behaviour policy's sampling noise into a head that is supposed to be a plan, and actively fights
the RL objective every time the cloned action was bad. AWR is a KL-regularised policy-improvement
step, valid off-policy, and it carries no ratio, so **PPO's trust region is untouched while every
plan step still receives gradient.**

**The `END_PLAN` target is not a special case, it is data.** If the agent's k-th subsequent own
action is separated from the plan by an *opponent* action, the correct step-k target was
`END_PLAN`. Free from the log, and it is what calibrates plan length correctly.

**Discounting by realised hazard needs no schedule.** `surv` comes from the label. Steps deep in
a plan that reliably dies contribute little; steps in reliably-forced sequences contribute fully.
The weight is the data.

### 4.5 (3) A critic on every plan step, and (4) the verification bit

```
L_v    = E_(t, k<K) [ ( V^k_theta - G_tau(t,k) )^2 ]

L_feas = E_t sum_(k=0..m_t) BCE( f^k, 1[k < m_t] )
```

`L_v` is the most literal satisfaction of directive (b) available. `h^k` already exists; a value
head over it is about 1M params for all K and adds nothing measurable to the forward. It trains
**every plan step from update one, on 100% of decisions, executed or not, against a target with
no distributional controversy** (the realised return of that action).

It is also *required*, not decorative: executed steps `k >= 1` have no trunk forward, so without
`V^k` there is no value estimate at those actions and GAE cannot be computed over the executed
sequence at all. The critic and the amortisation need each other.

`L_feas` is the discrete-time hazard: `f^k = P(step k legal | steps < k legal)`. Labels exist for
`k = 0 ... m_t`; steps beyond the first failure have no label and none is fabricated. This is the
signal that solves the bootstrap problem: it is free, exact, dense, and available on every
decision before any plan is ever executable. It is also the confidence input the adaptive-compute
controller needs, unlike today's `passes_taken` (`model.py:230`, `:260`), which is an argmax over
`type_head`, a head that provably receives zero gradient because its output feeds only
`torch.argmax` (`model.py:138`, `:243`) and a `sigmoid` (`model.py:179`) that no loss reads.

**One warning inherited from the runner-up designs and adopted:** the latency controller must
never take hazard as its only input. If the plan collapses, hazard becomes a constant and the
controller degenerates to a fixed budget while still looking adaptive.

### 4.6 (5) Legality-mass calibration and latent consequence

```
L_mask = - E [ log sum_(o in legal_f) p_theta(o) ]      over fields of steps k <= m_t
L_lat  = E [ 1 - cos( g_theta(h^k), sg(z_tau(t,k)) ) ]  over executed steps
```

`L_mask` says put your mass inside the legal set. It says nothing about which legal action is
good, so it cannot encode a play pattern: it is the rules, not a heuristic.

`L_lat` is a soft anti-collapse device: if `h^1` copies `h^0` then `g(h^1)` predicts the trunk
representation of the wrong state. It is honestly weak, because it is satisfiable by encoding
"the board changed somehow" without encoding the plan. **The hard measurement of collapse is
§4.9, not this term.**

### 4.7 Ending a plan must cost something real

The temptation is to assert that the value function prices plan length correctly because a full
trunk forward costs clock. That is a hope unless the clock is actually in the return. It is not
in any of the six loss terms, and it must not be smuggled in as a seventh, because a loss term
that rewards fewer forwards is a hand-authored preference for speed over strength.

**Primary mechanism: the clock is a resource in the state and in the rules.** Each seat carries a
time bank. It is an observation feature (remaining bank, and the opponents' banks). Exceeding it
means turns are skipped, which is a real and severe Magic-legal punishment, exactly as
[`NORTH_STAR.md`](../NORTH_STAR.md) §1a describes. Nothing is added to the reward: the agent
learns the shadow price of a forward from the critic, which is what "incentives, not rules"
means here. The deliberation cost that hierarchical RL usually calls `xi` is then not a
hyperparameter, it is a learned quantity, and the option-termination boundary coincides exactly
with the Tier-A cache-invalidation boundary in
[`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §2 (2.9 ms full pass versus 0.7 ms cached). The
architecture and the algorithm agree on where the seam is.

**The bank is counted in units the agent controls, not in milliseconds.** A wall-clock budget is
non-stationary with respect to hardware and to the inference server's queue depth: the same
policy would get different punishments for reasons it cannot observe, which is noise correlated
with nothing learnable. The bank is debited in `(trunk forwards, decoder steps, engine round
trips)`, with a per-hardware exchange rate to milliseconds calibrated once and **frozen for a
training run**. That calibration table is a scaffold (§9, S5).

**Honest gap, and the scaffold that covers it.** Early in training the bank is never exhausted,
so the rules punishment carries no gradient. A small compute-cost shaping term
`-lambda_c * c_t` bridges that, annealed to zero on a written condition (§9, S4). Whether the
bank is exhausted often enough in *self-play* for the primary mechanism to take over is a real
open question, because both seats face the same incentive and neither punishes the other for
being slow; see §10.5.

### 4.8 Interaction with recurrence and BPTT

**The recurrent state advances once per replan, not once per executed action.** It consumes the
trunk output, and executed steps `k >= 1` have no trunk output. Three consequences.

- The BPTT chain shortens by m-bar. A 2,500-decision Commander game at m-bar = 3 is an ~830-step
  chain. [`DESIGN_TRAINING.md`](DESIGN_TRAINING.md) §3 concludes memory is a non-issue under
  step-level checkpointing and that **serial wall-clock is the binding constraint**, so this is a
  direct m-bar-fold cut on exactly the binding axis. Amortisation buys training throughput and
  inference latency with one mechanism.
- Step-level gradient checkpointing (§3 mitigation (c), 141 KB per decision) is unaffected. The
  plan prefix adds a few KB. The recompute must be deterministic, so the sampled plan tokens and
  the mask must both be replayed from storage rather than resampled or recomputed.
- Plan steps `k >= 1` act on an `h_t` that is stale by up to `k-1` actions. That is the price of
  the amortisation. **Hazard does not price it**, because hazard measures legality survival, not
  quality loss; a plan can be perfectly legal and badly stale. §4.9 gives the probe that does
  measure it.

The formulation of PPO's ratio against a hidden state produced by an older policy is unresolved
and is already logged as R3 in [`DECISIONS.md`](DECISIONS.md). This design makes it worse by a
factor of m-bar. See §10.2.

### 4.9 Anti-collapse: measure it, do not penalise it

Four instruments, all shipped with the plan head rather than after it.

| Instrument | What it catches |
|---|---|
| **Forced-full-replan probe.** One game in N, force `m = 1` at every decision. Compare realised return. | High m-bar with value bleeding out looks exactly like success. This is the only honest measurement of what amortisation costs in quality, and it is the missing half of §4.8's staleness admission. |
| **Plan CE at step k minus a copy-step-0 predictor, and minus a state-conditional unigram over verbs.** | With 75.5% of options being mana abilities, "tap a land, tap a land, cast" is close to the true marginal, so a fully collapsed plan achieves genuinely low CE and looks fine. Only the unigram baseline catches it. Both differences must be positive and growing. |
| **`H(pi_f) / log(support_f)` tracked against support size.** | A tight engine-supplied mask hands over a lot of strategy for free. Near-uniform sampling inside a 3-element support looks like play. If this ratio stays near 1.0 as support grows, nothing is being learned and the wins are the mask's. |
| **Gradient samples and action-class distribution per step index k.** | Catches "step 4 never executes" and the open-loop blandness pressure (step-k heads preferring actions robust to board change: attack, pass, play a land). If step 4 never gets data, delete step 4. Plan length should be an empirical finding, not the constant 5 it has been since `model.py:84`. |

**Collapse to `END_PLAN` at k=1** is not prevented by a penalty. It is prevented by §4.7 making
a fresh trunk forward cost a real resource. Absent that, re-planning every step weakly dominates
any open-loop plan, and `END_PLAN` at k=1 is the *correct* optimiser behaviour. Multi-step
planning exists because of the clock; directives (1) and (2) in the owner's instruction are not
independent.

**Collapse to repeat-of-step-0** is prevented structurally rather than by a diversity bonus: step
k's decoder input is conditioned on the realised prefix, and the `EXCLUSIVE` mask kills the
repeat (you cannot play a second land, cannot re-tap a tapped source, cannot re-declare an
attacker). Where a repeat *is* legal, it is usually also correct (combo bodies), and
`A_tau(t,k)` will say so.

**`END` is not in the vocabulary as a plan-step type.** `model.py:88` defines `0:END`,
`model.py:117` runs five iterations unconditionally regardless, and `model.py:142-143` checks for
END and does `pass`. It is already vestigial. Here "I will stop acting" is spelled
`PASS_PRIORITY` or `PASS_TURN`, which are real, supervisable, checkable moves, and `END_PLAN`
is a plan-boundary token that is masked illegal at k=0 (the agent holds priority and must take a
legal action) and mid-move (before `EOA`). Both are rules constraints.

### 4.10 Pseudocode

```python
# ---------------- COLLECTION: one trunk forward, m executed actions ----------------
slate = engine.decision_slate(seat)              # ONE engine call; masks as tensors
out   = model(obs_t, h_prev, slate, K=K_bucket)  # captured graph for (K, F, C)
# out.tokens (K, F) int32   out.V (K,)   out.f (K,)   out.h (K, d)
rec, m = [], 0
for k in range(K_bucket):
    ok, act = engine.verify_and_bind(out.tokens[k])   # handle rebind + per-filler legality
    if not ok:
        break
    r, done = engine.execute(act)
    rec.append(dict(t=t, k=k, tokens=out.tokens[k], mask=slate.mask_bits,
                    r=r, V=float(out.V[k]), done=done))
    m += 1
    if done or engine.opponent_gains_priority():
        break
hazard_labels = [(k, 1.0 if k < m else 0.0) for k in range(min(m + 1, K_bucket))]
h_next   = out.h_rnn                              # RNN advances ONCE per replan
K_next   = hazard_head.choose_bucket(out.f)       # picked ONE decision ahead, keeps capture

# ---------------- LEARNER: one replan inside a BPTT segment ----------------
def replan_loss(x, h, eps=0.2, beta=1.0, w_max=20.0):
    out  = model(x.obs, h, x.slate, K=x.K)                       # replay, learner graph
    logp = out.logp_of(x.tokens, x.masks)                        # (K,) sum over ACTIVE fields
    with torch.no_grad():
        old = model_old.logp_of(x.tokens, x.masks)               # RECOMPUTED, never stored

    ex     = torch.arange(x.K, device=h.device) < x.m            # (K,) executed mask
    ratio  = torch.exp(logp[ex] - old[ex])                       # ACTION-level ratio
    A      = x.adv                                               # (K,) GAE at the REAL times
    L_ppo  = -torch.min(ratio * A[ex],
                        ratio.clamp(1 - eps, 1 + eps) * A[ex]).mean()

    w      = (torch.exp(A[~ex] / beta).clamp(max=w_max) * x.surv[~ex]).detach()
    L_awr  = -(w * out.logp_of(x.target_tokens, x.target_masks)[~ex]).mean()   # target may be END_PLAN

    L_v    = F.mse_loss(out.V[x.has_return], x.returns[x.has_return])          # ALL k
    L_feas = F.binary_cross_entropy_with_logits(out.f[:x.m + 1], x.hz[:x.m + 1])
    L_mask = -out.legal_mass_logprob[ex].mean()
    L_lat  = (1 - F.cosine_similarity(out.g[ex], x.z_future[ex].detach(), -1)).mean()
    H      = out.masked_entropy_step0()                          # true support only

    return (L_ppo + LAM_A * L_awr + C_V * L_v + LAM_F * L_feas
            + LAM_M * L_mask + LAM_L * L_lat - C_H * H), out.h_rnn
```

`LAM_A` is **held at zero** until the shaping terms go; see §9, S1.

---

## 5. Consequences, dependencies and the cost model

### 5.1 What this deletes

| Deleted | Where | Why |
|---|---|---|
| 65-float descriptor path | `action_mapper.py:43-92`, `environment.py:244-249`, `train.py:207-211`, `train.py:243-247` | replaced by the Slate |
| `ActionPointerHead.action_proj`, `intent_proj`, `plan_query_proj` | `model.py:152-156` | one factored head replaces the three-way type/source/target split |
| `type_head`, `source_head`, `target_head` | `model.py:97-99` | 2,109,450 params with `grad is None` |
| `System2ReasoningHead.action_memory_embedder` | `model.py:56` | 51,200,000 params, `grad is None`, never referenced in any forward |
| the `.item()` pair and the `.any()`/`break` | `model.py:142-143`, `:243-247` | graph-capture blockers, replaced by fixed-shape decode |
| proactivity bias | `student.py:126-129` | already in [`BACKLOG.md`](BACKLOG.md) as a scaffold; the entropy term over the true support replaces it |
| collection in `.train()` mode | `student.py:102` | dropout while acting |

### 5.2 What this keeps, by owner instruction

`ActionSequenceDecoder` is kept and retargeted, not deleted. What changes is that it decodes
*fields of a grammar* instead of a fixed `[type, source, target]` triple that cannot express a
block assignment at all, that it has a KV cache instead of re-running its whole prefix every step
(`model.py:117-122`), that it is narrow (§3.5), and that every one of its steps reaches a loss.

### 5.3 The tokenizer directive, honoured literally

`action_to_tokens` / `tokens_to_action` (`action_mapper.py:158-199`, `:94-156`) is the structure
the owner ordered preserved: network output decomposes into integer tokens, tokens reconstruct an
`Action`. This design is that structure generalised from a fixed 3-tuple over
`_get_sorted_entities` to a variable-length typed field sequence over a per-decision Slate. The
round-trip property is kept and put in CI: `tokenize(build(toks)) == toks` (§8.2).

### 5.4 Order of work

1. Stable integer object handles and deterministic entity ordering. This is prerequisite 1 in
   [`DESIGN_INFINITIES.md`](DESIGN_INFINITIES.md) and it is a hard prerequisite here too: if
   handles are re-derived `uuid.uuid4()` values and the candidate order shifts, "the same
   referent at t and at tau(t,k)" is not the same slot and the AWR targets are scrambled. It
   presents as mild permanent underfitting, not as a bug.
2. `engine.decision_slate()` and `engine.verify_and_bind()`, written against the ability tree.
3. The differential and round-trip tests (§8), in CI before any training.
4. Decoder, `L_ppo` + `L_v` + `L_feas` + `L_mask` only. Measure m-bar and the hazard curve.
5. The clock resource (§4.7) and `L_lat`.
6. `L_awr`, only after the shaping terms are gone.

### 5.5 Canonical ordering of set-valued slots

`ATTACK_SET`, `BLOCK_ASSIGN`, `TARGET` lists, `MODE` lists and `MULLIGAN_KEEP` are sets or
matchings, not sequences. **Position: canonicalise the emission order by candidate index and mask
already-emitted candidates.** The mapping from set to canonical sequence is a bijection, so
`log pi(set)` is exact. The alternative (permutation-marginalised loss) is O(n!) or needs a
matching per sample. `ORDER_TRIGGERS` (CR 603.3b) and `DAMAGE_ORDER` (CR 509.2) are exempt,
because there the order is the decision.

This is not free of risk. Sorting by candidate index makes the model spend capacity learning the
index sort, and whether the induced autoregressive factorisation is expressible at the sizes that
matter is not settled; see §10.3.

### 5.6 The seam with `DESIGN_LATENCY.md`

That document does not exist yet. Three things it must take from here and not re-derive:

- the budget is denominated in `(trunk forwards, decoder steps, engine round trips)`, with a
  frozen per-hardware exchange rate (§4.7);
- the grammar gives an **a-priori difficulty estimate** computed on CPU in microseconds before a
  single kernel launches: the engine knows the Slate's `(F, C)` bucket and the verb mask before
  decoding, so it knows that a `BLOCK_ASSIGN` on a 12-creature board is at least 26 fields;
- the adaptive-compute controller must not take the hazard head as its only input (§4.5).

### 5.7 The dependency this design does not own, stated precisely

Plan amortisation saves a trunk forward per executed step. Whether it saves *wall-clock* depends
on what else runs per action.

`convert_graph_to_tokens` is 14.5 ms mean against 0.432 ms for `get_legal_moves` and 0.050 ms for
the whole descriptor build. It is O(entities x relationships): `_get_zone_priority`
(`state_converter.py:81-95`) and `graph.get_controller_id` linearly scan all 412 relationships for
each of 214 entities.

Two facts follow, and both matter.

1. **The tokeniser is amortised by m-bar too.** It runs per *replan*, not per action, because
   executed steps `k >= 1` deliberately have no trunk input. At m-bar = 3 the 14.5 ms is paid a
   third as often. Amortisation helps even against today's tokeniser.
2. **But only if verification stays cheap.** `verify_and_bind` must be handle rebind plus
   per-filler legality (§4.1), not a fresh Slate and never a re-tokenisation. If the engine
   cannot offer that, the design degrades to a fresh Slate per executed step, which is still
   cheaper than a full trunk forward but loses most of the win.

**Pre-registered gate.** Before committing the model size (D5), measure on the DGX Spark:
`ms per executed action` at m-bar = 1 versus measured m-bar, on the forced mana-and-cast
sequences where the no-intervention horizon is longest. If the ratio is below 1.5x, the plan head
is buying wall-clock it did not earn and the sizing decision must not lean on it.

---

## 6. Composition with the ability tree (`DESIGN_CARD_POOL.md`)

### 6.1 Both sides of every pointer are compositional

```
key(candidate)  = W_role[role_f] . ( h_instance  (+)  v_composed(subtree) )
query(field)    = dec_step( state, role_emb[role_f], slot_idx_emb[f], k_emb[k], v_node )
```

The **key** carries the composed card vector,
`v_card = v_composed(tree) + gate * E_atomic[oracle_id]` with the atomic residual
zero-initialised (`DESIGN_CARD_POOL.md` step 3). The **query** carries `v_node`, the embedding of
the ability-tree node that generated this field. So `Selector{mode: TARGET, filter: creature,
controller: opponent}` is the same query vector for every removal spell ever printed, and the
circuit that answers "which creature do I kill" is shared across cards the model has never seen.

That is the strongest available statement of preservation directive (3), and it is exactly what
the current 65-float descriptor cannot express: `_extract_features` (`state_converter.py:103-141`)
packs ten keywords into a single float as a sum of powers of two (`state_converter.py:139-140`,
range 0 to 1023), which is a hash, not a representation.

### 6.2 The field schedule is generated from the tree, not hand-written

When the Slate offers `CAST ptr(card)`, the engine walks that card's compiled tree and emits
fields in canonical tree order:

| Tree node (`DESIGN_CARD_POOL.md` step 1) | Field |
|---|---|
| `Choose(n, [Effect])` | `MODE:PTR*` with an exact-count mask |
| `Selector{mode: TARGET, filter, count}` | `TARGET:PTR` x count, mask from the filter |
| `Quantity = X` | `X_VALUE:NUM`, range bounded by payable mana |
| `Optional(Effect)` | `OPTION:PTR` over `{yes-slot, NULL}` |
| `Cost{additional, alternative}` | `OPTION:PTR*` then `COST_TARGET:PTR*` |
| `Repeat(Quantity, ...)` | `NUM` |
| mana cost | `PAYMENT:PTR*`, `ARITH` |

Adding a **card** adds candidates. Adding a **node kind** adds a `V_role` row. Only the second is
a code change. That is the same line `DESIGN_CARD_POOL.md` draws for the executor, extended to
the action space.

### 6.3 The three degradation tiers

| Tier | Example | Behaviour |
|---|---|---|
| **1. New card, known primitives** | a new three-mana "destroy target creature" | tree compiles, fields generated from known node kinds, `Selector{TARGET, creature}` query is the one it has trained on for a thousand removal spells. **Plays day one, zero code change, action space unchanged.** This is tied-rank-1. |
| **2. New keyword that is sugar over known primitives** (Bargain, Casualty, Blitz, Prototype, Backup, Kicker, Buyback, Escape, Foretell, Offspring) | "sacrifice an artifact, enchantment or token as you cast this" | the compiler expands the keyword into the tree, and the whole thing becomes `OPTION:PTR -> ptr(option_slot)` where **the option slot's vector is the encoding of that keyword's sub-tree**. A never-seen keyword becomes a never-seen slot *embedding*, not a never-seen token. The sequence shape and the vocabulary are both unchanged. This is why every cost, mode and replacement modifier collapses into one role rather than getting a `WITH_KICKER`-style verb. |
| **3. Structurally new choice shape** | a new matching, partition or ordering no role covers | first absorbed by `ROLE_OPAQUE`: any choice that is "pick 1..n from an engine-supplied option list, each option carrying an encoder vector" needs no new token, which covers naming a card, choosing a creature type or colour, day/night, dungeon rooms. What is genuinely left needs a `V_role` row, and until one exists the card is `engine_supported = false`, drops out of the enabled pool, and lands in the unparsed queue with a coverage counter. **Hard refusal, never silent misplay.** |

The canonical historical failure in this repository is forty enters-the-battlefield triggers
silently never firing. Tier 3's behaviour is the opposite of that by construction.

### 6.4 Naming a card is a pointer into the pool

`RESOLVE_CHOICE ptr(choice_slot) ptr(poolcard)` points into the retrieved pool tokens from
`DESIGN_CARD_POOL.md`'s pool-conditioning block, so "name a card" generalises to cards never seen
in training. That document's rule that **pool tokens are keys and values only, never queries** is
respected: a pointer is `q . k` with pool tokens as keys.

Compare today: `engine.py:110-119` samples five random card names and appends "Shock", and all
six produce the identical descriptor `[8, 0...0]`.

### 6.5 Vocabulary versioning

One integer version covers `{V_verb, V_role, V_num, primitive vocab, node kinds}` and is stored
in the checkpoint. A mismatch is a **loud load error**, not a silent embedding scramble. This is
the same class of failure as the `card_id` autoincrement renumbering documented in
[`ARCHITECTURE.md`](ARCHITECTURE.md), and a convention is not enough: new rows go into the
reserved OOV slots (§1.2), never appended, so a new verb never reshapes a checkpoint. A new
row is initialised to the mean of its expansion's node embeddings rather than to random.

---

## 7. Composition with the loop shortcut (`DESIGN_INFINITIES.md`)

`DESIGN_INFINITIES.md` §3 specifies "a base action head selects the shortcut; a parameter head
conditioned on that base action emits a categorical over log buckets, 1, 2, 4, 8, ... up to
`n_max`, with `n_max` always present as an explicit go-off bucket". In this grammar that is
literally one production:

```
SHORTCUT_LOOP  CYCLE:PTR  ITERATIONS:NUM
```

with no parameter head and no special case. Four points of contact.

- **The cycle is a pointer candidate**, keyed on the observation token that document already
  proposes: cycle length, `log1p(n_max)`, and the signed log of each accumulator delta. That is a
  runtime-encoded vector, so a cycle discovered in a deck the model has never seen is addressable
  the day it is mined.
- **`n_max` is the mask, not a cap.** Every `V_num` bucket above the engine-derived `n_max` is
  masked, and `N_MAX` always resolves to `n_max`. `n_max` is derived from the extrapolation
  guards, so it is not a chosen number and does not belong in the scaffolds table.
- **The shortcut appears in the Slate only after the agent executed the cycle body itself.** That
  is the discovery rule in `DESIGN_INFINITIES.md` §4 and this design changes nothing about it.
- **The mined macro library is the plan decoder's warm start.** Each mined macro is a recorded
  action sequence with a precondition signature. Pretrain the plan decoder by AWR on those
  sequences before any RL. This is a free warm start for exactly the regime where PPO exploration
  is hopeless (that document computes 200^-6 for a six-action combo), and it is the same AWR term
  from §4.4 with the macro's realised gain in place of the advantage. The termination condition
  comes for free from the structural hash, so the plan boundary and the macro boundary coincide.

The three reward-side blockers that document lists (`MAX_MOVES_PER_STEP` at `engine.py:196-199`,
the five-repeat block at `train.py:169`, the 100-step stall detector at `train.py:160,180-183`)
must go for this to work, and they are already in [`BACKLOG.md`](BACKLOG.md).

---

## 8. Correctness obligations, in CI from day one

The mask oracle is the whole design and its bugs are silent: an illegal move is simply
unreachable, with no exception, no crash and no metric. These four tests are not optional.

### 8.1 Differential test against exhaustive enumeration

On every state where `get_legal_moves()` can still enumerate, assert that the set of complete
sequences reachable through the mask decodes to **exactly** that set: no more, no fewer. Plus a
random-walk invariant over 10^6 random states x random legal prefixes: `Field.mask` is never
empty, greedy completion always yields a move `build()` accepts, and the length is bounded.

### 8.2 Round trip

`tokenize(build(toks)) == toks` for every reachable token sequence. This is the property that
keeps `action_to_tokens` honest and is the direct descendant of the structure in
`action_mapper.py:158-210`.

### 8.3 Builder / executor identity

`build()` must return **the same typed object the executor consumes**. If the builder and the
executor are separate code they will diverge, and that divergence is `selector` versus `target`
(`handlers/effect_handlers.py:111`) wearing a new name.

### 8.4 The measurement that gates the masking design

Distribution of `DEPENDENT` field frequency and `late_validated` resample rate over real states.
[`NORTH_STAR.md`](../NORTH_STAR.md) §1a says optimise the tail, and this is the tail. The
measurement is **impossible today**, because targeting is broken and no state ever produces a
hard slate. It must land before the masking design is committed. See §10.4.

---

## 9. Scaffolds, logged as [`BACKLOG.md`](BACKLOG.md) requires

Every hard limit, cap or schedule this design introduces, with the condition that removes it.
These belong in `BACKLOG.md` under "Scaffolds to remove" when the design is built.

| # | Scaffold | Where | Removal condition |
|---|---|---|---|
| S1 | **`lambda_a = 0`**: the AWR term is held at zero. Not a cap on the agent, a sequencing constraint on us. | §4.4 | The thirteen shaping terms at `environment.py:164-211` are gone. A 200-step game currently accrues about +20 of shaping against +/-10 for the actual result, so AWR would faithfully and efficiently teach the plan head to plan *shaping*. |
| S2 | **`K` bucket ladder `{1, 2, 4}`.** A cap on plan depth, chosen for graph capture. | §3.4 | The gradient-samples-per-step-index diagnostic (§4.9) shows demand at k = 4 sustained over three seeds, or shape-polymorphic capture is measured to be affordable. Note the *choice among buckets* is learned; only the ladder is authored. |
| S3 | **`(F, C)` bucket ladders `{2,4,8,16}` x `{32,64,128,256,512}`.** | §3.4 | A JIT re-capture cache keyed on observed shapes is measured on the Spark. Until then this is a hand-chosen quantisation of a continuous quantity. |
| S4 | **`-lambda_c * c_t` compute shaping, annealed to zero.** | §4.7 | The time bank is exhausted in at least X% of self-play games, so the rules punishment carries gradient by itself. If it never is, S4 cannot be removed and §10.5 is the reason. |
| S5 | **Frozen per-hardware compute-to-milliseconds exchange table.** | §4.7 | A stable captured-CUDA-graph latency profile exists per shape bucket, so the table can be regenerated rather than pinned. |
| S6 | **Hazard head frozen out of `K` selection for the first N updates**, `K` fixed at the smallest bucket. | §3.4, §4.5 | Hazard calibration error below 0.1 on held-out replans. Without this, `K` is chosen by a head that has not trained. |
| S7 | **AWR `beta` and `w_max`.** | §4.4 | Gate on critic explained variance above 0.3; below that AWR reinforces luck. |
| S8 | **`late_validated` resample retry limit.** | §3.3 | This is a genuine non-termination rail and may be permanent, but it is logged because a resample loop that cannot find a legal completion is an engine bug and must alarm rather than spin. |

Two things that look like scaffolds and are not, recorded so nobody removes them by mistake:
the legality mask (it is the rules of Magic, per `NORTH_STAR.md` §3's corollary), and `n_max` on
a shortcut (derived from the extrapolation guards, not chosen).

---

## 10. Open questions that need a stronger reasoning model

Per [`NORTH_STAR.md`](../NORTH_STAR.md) §6 these are questions I genuinely could not resolve, not
hedges. Each names the question, what was tried, and why a wrong answer is expensive. They should
be copied into [`DECISIONS.md`](DECISIONS.md) under "Needs deeper reasoning".

### 10.1 Ratio granularity for a variable-length action under PPO

**Question.** Should the importance ratio for a move be taken at the action level (one ratio,
the product over its active fields, one clip) or at the field level (one ratio per field, shared
move-level advantage)?

**Tried.** Both positions have a clean argument and they contradict. Action level is
type-correct: the move is the MDP action, and clipping it once is the textbook object. But the
ratio is a product over up to 16 fields, so its log-variance grows roughly linearly in field
count and the effective trust region is systematically tighter on complex moves; a 14-field
modal X spell leaves the band on epoch 1 while a 2-field land drop does not, which starves
exactly the actions that matter. Field level bounds each field independently, but the resulting
estimator is not the PPO estimator for the move, and I could not characterise the sign or the
magnitude of its bias. I specified a stratified clip-fraction diagnostic and a fallback (§4.3),
which decides it empirically but does not answer it.

**Why it matters.** The failure is misdiagnosable. The symptom is "the bot stopped casting
spells and just plays lands and passes", and this repository has already met that symptom once
and answered it with a 10-nat proactivity bias at `student.py:126-129` that is applied at
collection and not at training. The wrong reflex is available and it will be tempting again.

### 10.2 PPO's ratio against a deliberately stale recurrent state

**Question.** Plan steps `k >= 1` are conditioned on `h_t`, which by design is not refreshed for
up to `k-1` actions, and which at update time was produced by an older policy. What is the
correct formulation: recompute `h` under the current policy during the update (which changes the
conditioning of the plan away from what the actor actually conditioned on), store `h` and accept
the staleness, or reformulate so the problem does not arise?

**Tried.** This is R3 in [`DECISIONS.md`](DECISIONS.md), and this design makes it strictly worse
by a factor of m-bar, because staleness is now deliberate rather than incidental. I specified
storing `h_t` and replaying it (§4.8), which is internally consistent and matches what the actor
did, but I could not show that the resulting gradient is an unbiased estimator of anything in
particular. Recomputing `h` under current parameters is defensible for the executed step 0 and
clearly wrong for steps `k >= 1`, which suggests the two need different treatment, and I could
not construct that split cleanly.

**Why it matters.** It is silent. Training runs and produces curves either way, and the error
appears as a persistent quality gap that looks like insufficient capacity.

### 10.3 Whether canonical ordering of set-valued slots is safe at the sizes that matter

**Question.** For `ATTACK_SET` and `BLOCK_ASSIGN` I canonicalise the emission order by candidate
index, so `log pi(set)` is exact through a bijection. But the *gradient* flows through an
autoregressive chain whose prefix is determined by an arbitrary index sort. Does that induce a
systematic representational bias, so that sets whose canonical prefix is uninformative are harder
for a limited-capacity narrow decoder to express?

**Tried.** The alternative is a permutation-marginalised likelihood, which is O(n!) exactly or
needs a matching per sample. I rejected it on cost. What I could not verify is that the rejection
is safe at the sizes that matter: 8 blockers against 5 attackers with a d=256 decoder is not
obviously in the regime where the sort is learnable for free. An intermediate (sort by a learned
score rather than by index) reintroduces a differentiability problem I did not resolve.

**Why it matters.** Block and attack declaration are where Commander games are decided, and a
representational ceiling there would present as "the bot blocks adequately but never finds the
good multi-block", which is indistinguishable from ordinary weakness.

### 10.4 The size of the `DEPENDENT` field class

**Question.** §3.3 claims that legality dependence falls into `STATIC`, `EXCLUSIVE`, `ARITH` and
a small `DEPENDENT` residue, and the entire latency argument rests on that residue being small.
Is that true across real Magic, or does a substantial fraction of fields land in `DEPENDENT`?

**Tried.** I verified the claim for exclusivity (attackers, blockers, targets, modes) and I
argued that payment sufficiency is `ARITH` given a per-candidate mana-production vector. But
that last claim is a claim about the whole cost system: hybrid and Phyrexian mana, snow mana,
"spend this mana only on", cost reduction that depends on what has already been chosen, and
additional costs whose legality depends on the payment. I did not verify that these all remain
closed-form. I could not bound the residue empirically either, because the current engine cannot
produce a single hard slate: `handlers/effect_handlers.py:105-113` returns `[]` for effectively
every card, so no state in the repository today exercises a dependent field.

**Why it matters.** If the residue is large, the per-field engine round trip returns, which is
the exact cost structure this design was shaped to avoid, and the `late_validated` path lands on
the slowest decisions, which is the tail `NORTH_STAR.md` §1a says to optimise. It is expensive
to discover late because the whole Slate contract would have to change.

### 10.5 Whether a shared time bank produces gradient in self-play

**Question.** §4.7 makes the clock a real resource with the rules punishment (skipped turns) as
the only incentive, plus a shaping scaffold (S4) to bridge the early period. Is there a
self-play equilibrium in which both seats learn to spend the whole bank, because neither is ever
punished by an opponent who does the same, so the bank is never exhausted under pressure and the
primary mechanism never takes over from the scaffold?

**Tried.** The obvious answer is league play with fixed-budget opponents, which does create
pressure. What I could not determine is whether that pressure is *informative*: an opponent who
plays fast does not directly punish a slow agent in Magic the way a chess clock does, since the
banks are independent. That asymmetry is specific to a per-player clock and I could not construct
the argument either way.

**Why it matters.** If the answer is no, S4 is not a scaffold, it is a permanent hand-tuned
reward term, and it would be one that trades strength for speed on a fixed exchange rate the
owner never chose. That is precisely the thing `NORTH_STAR.md` §3 forbids, and it would be
better to know before the shaping is annealed. This question belongs jointly to
`docs/DESIGN_LATENCY.md` when that document is written.
