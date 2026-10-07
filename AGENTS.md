# MTG_AI Multi-Agent Architecture & Context Guidelines

## 1. Core Operating Philosophy
- **DGX Spark Unified Architecture**: The orchestrator and subagents share the NVIDIA GB10's 128 GB unified LPDDR5X memory. To maximize inference throughput and prevent KV-cache congestion, **work MUST be distributed to specialized subagents**.
- **Orchestrator Role**: The main agent (`build` / `plan`) is an **Architect and Coordinator**. It does not write repetitive boilerplate or read massive logs directly. It delegates bounded tasks to subagents and synthesizes their results.

---

## 2. Specialized Subagent Roster & Full Matrix

### Standard Production Roster (Default Recommendation)
Stick to this standard roster for 95% of daily tasks. Each subagent has a tuned balance of context capacity, reasoning depth, and speed:

| Agent Name | Model Tier | Context | Output Ceiling | Mode / Permissions | Primary Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`ultra`** | `262k-xhigh` | 262,144 | 32,768 | `subagent` (Read, edit, bash) | Complex cross-module features, monumental refactors, deep proofs. |
| **`coder`** | `128k-medium` | 131,072 | 32,768 | `subagent` (Read, edit, bash) | Full module implementation, refactoring, unit testing & verification. |
| **`analyst`** | `128k-xhigh` | 131,072 | 32,768 | `subagent` (Read-only, no edit) | Deep architectural alignment against MTG engine mandates. |
| **`reader`** | `64k-instant` | 65,536 | 8,192 | `subagent` (Read-only, no bash) | Fast multi-file inspection, symbol extraction, doc summarization. |
| **`tester`** | `64k-instant` | 65,536 | 8,192 | `subagent` (Bash, no edit) | Runs `pytest` and test suites, reports compact pass/fail breakdowns. |
| **`adversarial`**| `64k-xhigh` | 65,536 | 16,384 | `subagent` (Read-only, no edit) | Hunts edge cases, infinite loops, rules loopholes, and invariants. |

### Complete 16-Combination Matrix (Available for Custom Scenarios)
The gateway and OpenCode support the full matrix of **4 Context Tiers $\times$ 4 Reasoning Efforts**:
`vllm/nvidia/Qwen3.8-27B-NVFP4-{context}-{effort}`

| Context | `instant` (no thinking) | `low` (light thinking) | `medium` (balanced) | `xhigh` (deep reasoning) |
| :---: | :--- | :--- | :--- | :--- |
| **`32k`** | Fast worker / summaries | Quick lint/tool checks | Short-context refactors | Micro-proofs / regex / bitwise |
| **`64k`** | **`reader`**, **`tester`** | Fast test diagnostics | Medium bugfixes | **`adversarial`** review |
| **`128k`**| Fast bulk file inspect | Doc migration passes | **`coder`** implementation | **`analyst`** deep review |
| **`262k`**| Whole-repo AST extraction | Fast whole-repo search | Balanced orchestrator | **`ultra`** / Primary orchestrator |

### When to Use Non-Standard / Niche Combinations:
Stick to the standard roster unless you have a specific, high-leverage reason. Examples where "odd" combinations shine:
* **`32k-xhigh` (Deep reasoning, micro footprint)**: Use when solving a mathematical, bitwise, or formal MTG rule proof (e.g. layers interaction, state-based action loop prevention) that requires massive deductive reasoning but only needs a tiny snippet of code in context. Runs with minimal KV cache overhead.
* **`262k-instant` (Max context, zero thinking latency)**: Use when performing whole-repository symbol extraction, formatting massive log dumps, or running AST scans across 400 cards where thinking tokens would waste time and you only need high-speed direct text processing.
* **`128k-low` / `64k-low` (High context, light verification)**: Use for straightforward repetitive tasks across medium-sized files (e.g., updating docstrings, migrating type annotations) where pure instant might hallucinate, but full `medium`/`xhigh` thinking adds unnecessary latency.
* **`262k-medium` (Full orchestrator context, faster turn times)**: A great alternative for the main orchestrator when coordinating routine execution phases that do not require maximum `xhigh` contemplation.

---

## 3. Context Estimation & Budgeting Protocol

Before delegating work or reading files, **always run the sizing tool**:
```bash
token-estimate <files...>
```

### Context Capacities & Safety Margins:
1. **64k Subagents (`reader`, `tester`, `adversarial`)**:
   - **Input Budget**: Up to **32,000 tokens**.
   - **Headroom**: 32,000 tokens reserved for reasoning, command outputs, and summaries.
2. **128k Subagents (`coder`, `analyst`)**:
   - **Input Budget**: Up to **64,000–80,000 tokens**.
   - **Headroom**: 48,000+ tokens reserved for balanced/xhigh thinking + full module generation.
3. **262k Subagents (`ultra`)**:
   - **Input Budget**: Up to **180,000 tokens**.
   - **Headroom**: 80,000+ tokens reserved for extensive `xhigh` reasoning + up to 32,768 code output tokens.
4. **Orchestrator & Compaction (`262k Native Context`)**:
   - The main orchestrator operates at Qwen 3.8 27B's full native training sequence length of **262,144 tokens**.
   - Automatic compaction triggers when context reaches **200,000 tokens** (leaving 62k headroom). Compaction runs with **`xhigh` reasoning effort** and a **32,768 token output ceiling**, preserving 120,000 tokens of recent session state with zero truncation.

> [!IMPORTANT]
> ### SUBAGENT BOUNDING & FAIL-SAFE COMPACTION
> - **Subagents are designed for short-horizon bounded tasks** (implementing 1 module, running tests, analyzing 1 spec).
> - **Avoid relying on subagent compaction**: Decompose tasks so they fit comfortably within the subagent's token budget (32k, 64k, 128k) without needing compaction.
> - **Safety Net**: If a large task (e.g. `coder`) exceeds turn limits, OpenCode's intelligent reasoning compaction (`nvidia/Qwen3.8-27B-NVFP4-compaction-thinking`) will trigger automatically, distilling the session down to a ~15k working memory checkpoint so the task completes safely rather than overflowing.

### Rules for Subagents:
* **Bounded Horizons**: Design tasks to finish within the subagent's context window. If a subagent approaches its context ceiling, the task should have been decomposed into smaller steps.
* **Default Forbid Unbounded Exploration**: Subagents are strictly forbidden from autonomous recursive reading or open-ended web browsing unless explicitly commanded in their task prompt.
* **Concise Returns**: Instruct all subagents to return structured summaries under 400 words or diffs. Never let a subagent regurgitate raw file dumps back to the orchestrator.
* **LSP & Symbol Navigation Active**: Pyright LSP is active for real-time type checking and diagnostics across all `.py` files. Use the `lsp` tool (`goToDefinition`, `hover`, `documentSymbol`, `workspaceSymbol`) to inspect functions, interfaces, and classes rather than reading entire source files into context.
* **Auto-Formatting & Verification**: Ruff is enabled as the auto-formatter on edits. Lingering compiler warnings in edit outputs do not mean an edit failed. For full repo-level checks, use `ruff check` and `pytest`.

* **Orchestrator Lifecycle & Subagent Delegation Protocol**:
  - **Orchestrator is IDLE during subagent runs**: When you invoke a subagent via `task(...)`, your session pauses completely until that subagent finishes and returns its report. You do NOT compute, plan, or execute parallel tool calls while awaiting subagent completion.
  - **Batch Blocking**: If you emit multiple `task(...)` calls in the *same* turn, you will remain blocked and idle until the *very slowest* subagent in that batch completes. Fast agents will sit finished and unread while you wait for the longest task.
  - **When to dispatch sequentially**: Whenever tasks have unequal expected durations (e.g. pairing a 1-minute `reader` or `tester` with a 30-minute `coder`), or when the findings of one subagent should inform the prompt/scope of the next. Dispatch one `task` per turn so you can immediately inspect the return.
  - **When parallel dispatch is acceptable**: Only when tasks are strictly independent, non-overlapping in file scope, and have similar expected completion times (e.g. 2-3 parallel test suites or parallel file readers).

---

## 4. How to Prompt Subagents via the `task` Tool

When spawning subagents, provide a structured prompt with four mandatory components:
1. **Objective**: 1–2 sentences defining the exact deliverable.
2. **File Scope**: Explicit file paths to read or edit.
3. **Constraints**: What *not* to touch and formatting limits.
4. **Exit Criteria**: Command to verify (e.g. `pytest MTG_bot/test_specific.py`).

### Example Delegations:

#### Delegating Research (`reader`):
```json
task(
  description="Inspect ability tree grammar specs",
  prompt="Read /home/sune/Desktop/MTG_AI/docs/DESIGN_CARD_POOL.md lines 1-150. Summarize the required AbilityNode and EffectNode types into a bulleted list under 200 words. Do NOT read any other files."
)
```

#### Delegating Test Execution (`tester`):
```json
task(
  description="Run Phase 1 grammar unit tests",
  prompt="Run 'pytest MTG_bot/core/test_grammar.py -q'. Report the number of passing/failing tests and copy ONLY the error message if any fail. Do not output full test logs."
)
```

#### Delegating Code Implementation (`coder`):
```json
task(
  description="Implement ZoneState container in engine",
  prompt="Implement the ZoneState class in MTG_bot/core/state.py following the spec in docs/DESIGN_CARD_POOL.md. Run 'pytest MTG_bot/tests/test_state.py' to verify. Only edit state.py."
)
```

---

## 5. Web Search & Documentation Discipline
- Brave Search is configured via MCP (`brave-search`).
- **Use Sparingly**: Only search for up-to-date library APIs, Scryfall data nuances, or obscure syntax.
- **Narrow Queries**: Always specify exact keywords (e.g. `"Scryfall oracle_id format 2026"`).
- **Never Ingest Full Web Pages**: Summarize extracted search snippets before incorporating into context.

## 6. The Knowledge Tree (binding)
- **Every session starts** by reading `KNOWLEDGE/INDEX.md`, the newest dated folder's orientation
  note, `KNOWLEDGE/NUMBERS.md` (latest measurements) and `KNOWLEDGE/PITFALLS.md` (standing traps).
- **Every delegation** names the specific `KNOWLEDGE/` files the subagent must read first, in the
  task prompt. A subagent that has not read them is operating blind.
- **Every discovery, decision, or measurement** is appended to `KNOWLEDGE/<date>/NN-*.md`
  (dated, numbered, never deleted — mark `superseded by …` instead). Headline numbers go into
  `NUMBERS.md` with date + producing command; traps go into `PITFALLS.md`.
- A number not recorded in `NUMBERS.md` with a date and command is not admissible evidence.

## 7. Code Quality Law (owner 2026-10-06 — binding for orchestrator and every subagent)
- Prefer the simplest implementation that is easy for human and agent to inspect. No
  unnecessary abstraction, indirection, cleverness or premature generalization — but never
  drop error handling or validation to save lines.
- Minimal diffs: touch only what the task requires. A drive-by rewrite of a file to change
  one line is a bug surface, not tidiness.
- VERIFIED means EXECUTED: after changing code, run the relevant tests — or write a small
  test/script exercising the change including at least one edge or failure path — and fix
  failures before reporting. Report WHAT you ran and the result. Never claim something works
  because it was re-read; same-context self-review is the weakest check and the easiest to
  fake ("review theater").
- Fresh-eyes review for substantive changes: reviewer sees only the diff + requirements,
  not the reasoning that produced them (use the adversarial/analyst subagents for this).
- Keep prompts and prompts-to-subagents short: a few explicit rules outperform a wall of
  style guidance on a local model. Verification first, style detail last.

## 8. Tokenizer Law — atomic-structure re-evaluation on every set integration (owner 2026-10-07)
- The atomic subcomponents (ability-tree vocabulary, effect/ask grammar, zones) ARE our
  tokenizer: they determine how nuanced the model can see the game and how it analogizes to
  unseen cards. A lossy or coarse tokenizer caps generalization no matter how good the data
  or model.
- Therefore EVERY set integration MUST include a fundamental re-evaluation of whether the
  atomic structure still fits the TOTAL card pool — not just parses the new set. Minimum
  evidence per integration: compile rate + top non-representable patterns, ask-kind coverage
  of the new pool vs eval needs, new effect shapes missing from the vocabulary, and any
  eval-item mechanics that remain un-askable (see KNOWLEDGE/2026-10-07/24 fail-core).
- The first ~20 sets are expected to CHANGE the atomics materially — treat early integrations
  as tokenizer refinement opportunities, not just data pickups. Numbers go to NUMBERS.md.

## 9. Axis-orthogonality law for atomic subcomponents (owner 2026-10-07)
- Every decision/ability atom decomposes into ORTHOGONAL axes: {operation} (choose/may/
  target/order/name/policy...), {menu} (fixed list | legal-set | derived | bounded-number,
  always clamped by actual availability), {count} (1..X), {effect-of-each-choice}. No atom
  may fuse axes that other cards need independently — the operation must be reusable with
  any menu, count, or effect bundle ("choose two targets" = choose x count x target-menu).
- Conceptually-identical encodings MUST collapse into one component (the {choose} currently
  exists 3x coded differently: Choose combinator / silent selector-CHOOSE / asking ONE_OF).
  Rewriting atomics to merge duplicates is expected and normal, especially in the first ~20
  sets — but merges require: (i) similar practical effects (else the model conflates things
  it shouldn't), (ii) volume: an atom shared by too few cards cannot be learned generalized
  (owner hypothesis, testable) — every atom ships with a cards-using-it census.
- Fundamentals (choose, count, race/class-identity, attack/block, damage-lanes) are reused
  most => highest priority to get orthogonal; complex functionality decomposes into them and
  is expected to drive REWRITES of atomics as shared structure becomes visible.
- {when-event} is a FUNDAMENTAL too: event atoms (creature attacks / spell casts / you take
  {X} damage ...) decompose as {event-kind, subject filter, quantity bound, controller
  direction} — direction must have ONE encoding (today split between event.controller fields
  and FAtomPred.CONTROLLER_IS in subject filters: unify per merge ledger E1). Keywords (FLYING 40 goldens, TRAMPLE 13)
  ARE already shared atoms with multiple consumers — keep them that way.

## 10. Menu-visibility law — atomized components never leave the model blind (owner 2026-10-07)
- Every decision atom's encoding MUST expose every axis the model will face in practice, with
  the SAME vocabulary statically (card/tree encoder) and dynamically (ask/observation):
  {operation, quantity WITH live bound values, menu (full list | zone+filter descriptor),
  per-choice effects}. {heal X} without showing heal-what-menu-actually-exists = blindness;
  the model cannot choose well and a transfer gap opens between card-encoder information
  and presented options.
- Two violation classes, same sin: BLINDNESS (a real decision exists dynamically but the
  static encoding has no trace, or the ask hides axes: silent CHOOSE picks, attack-as-N-
  binars instead of visible attacker-set, scry within-order hidden, mana amount never
  askable) and PHANTOM (encoding/ask presents a choice that has no consequence or the
  engine resolves anyway: gold:false dead asks, single-candidate "decisions").
- A node the engine resolves without asking must be ENCODED as no-decision (never phantom);
  a node that asks must be traceable in the card's static encoding (never blind).
- Every atom ships with a blindness audit (static tokens <-> dynamic ask shape). New sets
  (§8) and the T4 atomization rewrite must pass it; eval items failing it are evidence.

## 11. Board-separation + zero-loss encoding law (owner 2026-10-07)
- A card's encoding contains ONLY that card's own components (the choices they create).
  Interaction-acquired restrictions are NEVER encoded into the restricted card ("card A says
  creatures can't attack" is A's component; card B's encoding stays untouched). The engine
  computes live legality; the observation menu presents the true options at decision time.
  Board interaction is the model's complexity target, not an encoding concern.
- Zero-loss goal: the components must capture ALL semantically significant information of a
  card. SIGNIFICANCE CRITERION: text is significant iff it can alter legal options or state
  outcomes. Anything significant that fits no component is a GAP REPORT — distinguishing
  (i) mis-encoded card (fix encoding) from (ii) component-coverage hole (new atom or
  rewrite). The rewrite (T4) ships a gap ledger, not just a compile rate.
