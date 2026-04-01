# Agent Guidelines: Standards & Workflows

To maintain the long-term integrity of the MTG AI project, all agents (Human or AI) MUST adhere to the following standards.

## 1. Context Preservation (Read First)
Before performing any task, you MUST read the following files to synchronize with the current project state:
*   `MTG_bot/INDEX.md`: The root map of the project.
*   `MTG_bot/docs/TASKLIST.md`: The current list of pending fixes and features.
*   Relevant logic documentation (e.g., `RL_ARCHITECTURE.md`).

## 2. Documentation Maintenance
Documentation is the "memory" of this project. 
*   **Update on Change:** If you modify a logic file (e.g., `engine.py`, `decision_maker.py`), you MUST update the corresponding `.md` file in `docs/` to reflect the new state.
*   **Semantic Tree:** Maintain the tree structure of `.md` files. Refer to other documents rather than duplicating information to save context window space.

## 3. The Tasklist Workflow
*   **Observation:** If you encounter a bug, a missing rule, or a "todo" in the code, do not just leave a comment in the code.
*   **Action:** Add it to `MTG_bot/docs/TASKLIST.md` immediately with a description and priority level.
*   **Resolution:** When a task is finished, move it to the "Completed" section.

## 4. Engineering Standards
*   **Security:** Never log or print API keys or database credentials.
*   **Testing:** Every code change should be validated via the `Scenario Runner` or existing unit tests.
*   **Idempotency:** Ensure scripts (like the data loader) can be run multiple times without corrupting the database.
