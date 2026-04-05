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

## 5. Import Integrity (Crucial)
When extending core logic (especially in `train.py`, `engine.py`, or `environment.py`), you MUST ensure all referenced classes and actions are imported.
*   **Action Types:** If you use `ActivateManaAbilityAction`, `CastSpellAction`, etc., verify they are in the `from ...actions import ...` block.
*   **Vocabulary:** Ensure `vocab` is imported if accessing `ID_MANA_GREEN` or similar constants.
*   **Avoid NameErrors:** Most crashes in the training loop are due to missing imports after a logic update.

## 6. Pre-Execution Checklist
Before starting a long training run:
1.  **Syntax Check:** Run `python -m py_compile path/to/modified_file.py` to catch basic errors.
2.  **Import Audit:** Scan your changes for new class names and ensure they have corresponding import statements.
3.  **Smoke Test:** Run a small reproduction script or the `Scenario Runner` to ensure the core loop still starts.
