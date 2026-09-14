# MTG_AI Multi-Agent Architecture & Context Guidelines

## 1. Core Operating Philosophy
- **DGX Spark Unified Architecture**: The orchestrator and subagents share the NVIDIA GB10's 128 GB unified LPDDR5X memory. To maximize inference throughput and prevent KV-cache congestion, **work MUST be distributed to specialized subagents**.
- **Orchestrator Role**: The main agent (`build` / `plan`) is an **Architect and Coordinator**. It does not write repetitive boilerplate or read massive logs directly. It delegates bounded tasks to subagents and synthesizes their results.

---

## 2. Specialized Subagent Roster

| Agent Name | Model Tier | Context | Mode / Permissions | Primary Role |
| :--- | :--- | :--- | :--- | :--- |
| **`reader`** | `64k-instant` | 65,536 | `subagent` (Read-only, no bash, no edit, no websearch) | Fast multi-file inspection, symbol extraction, doc summarization. |
| **`coder`** | `128k-medium` | 131,072 | `subagent` (Read, edit, bash allowed) | Full module implementation, refactoring, unit testing & LSP verification. |
| **`tester`** | `64k-instant` | 65,536 | `subagent` (Bash allowed, no edit, no websearch) | Runs `pytest` and test suites, reports compact pass/fail breakdowns. |
| **`analyst`** | `128k-xhigh` | 131,072 | `subagent` (Read-only, no edit) | Deep architectural alignment against MTG engine mandates, deep thinking. |
| **`adversarial`**| `64k-xhigh` | 65,536 | `subagent` (Read-only, no edit) | Hunts edge cases, infinite loops, rules loopholes, and invariants. |

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
3. **Orchestrator & Compaction (`128k`)**:
   - Compaction runs with **`xhigh` reasoning effort** and a **32,768 token output ceiling**, ensuring deep analytical synthesis and zero truncation of session state.

### Rules for Subagents:
* **No Subagent Compaction**: Subagents run bounded tasks and report back. If a subagent would require compaction, the task is **too broad**. Decompose it into multiple focused sub-tasks.
* **Default Forbid Unbounded Exploration**: Subagents are strictly forbidden from autonomous recursive reading or open-ended web browsing unless explicitly commanded in their task prompt.
* **Concise Returns**: Instruct all subagents to return structured summaries under 400 words or diffs. Never let a subagent regurgitate raw file dumps back to the orchestrator.
* **Python LSP Enabled**: Pyright LSP is active for real-time type checking and diagnostics across all `.py` files.

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
