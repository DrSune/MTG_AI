# Procedural Scenario Generation Framework

To reliably track gradual improvements in the MTG AI, we use **Procedural Scenario Generation**. This system generates thousands of unique puzzles categorized by difficulty, challenge type, and cardset.

## 📂 Directory Structure

Scenarios are stored using a set-first hierarchy to ensure tests are isolated by card pool:

`MTG_bot/scenarios/{SET_CODE}/level_{N}/{CATEGORY}/`

*   **SET_CODE**: e.g., `M21`, `ELD`, `ZEN`.
*   **LEVEL**: `level_1` (Tactical), `level_2` (Sequencing), `level_3` (Strategic).
*   **CATEGORY**:
    *   `lethal`: Find a way to reduce opponent life to 0 this turn.
    *   `board_clear`: Remove all or key opponent threats using spells/abilities.
    *   `setup`: Maximize future mana, card advantage, or board presence for next turn.
    *   **`combat`**: Find the optimal blocks or attacks in a single combat phase.

---

## 🧩 Challenge Types & Templates

### Level 1: Immediate Tactical
*   **lethal**: Opponent at low life, player has burn or a pump spell.
*   **board_clear**: Opponent has multiple X/1 creatures; player has a "deal 1 damage to all" spell (e.g., *Cinderclasm*).
*   **combat**: Opponent attacks with a 2/2; player has a 3/3 and a 1/1. (Correct choice: block with 3/3).

### Level 2: Sequencing & Resource Management
*   **setup**: Player has 5 mana and two 3-cost creatures. (Correct choice: play the one that provides a continuous effect first).
*   **board_clear**: Use a spell to weaken creatures, then finish them off with a combat block.
*   **lethal**: Sequence a land drop to afford a haste creature for the win.

### Level 3: Probabilistic & Strategic
*   **setup**: Holding a board clear spell while the opponent has a small board. (Correct choice: wait for them to over-extend before casting).
*   **lethal**: Playing around a likely counterspell or combat trick based on opponent open mana.

---

## 🛠️ Cardset Connection

The `ScenarioGenerator` script is initialized with a `set_code` parameter.
1.  It loads only cards from the specified set (`MTG_bot/data/{SET_CODE}.json`).
2.  It queries the `mtg_bot.db` for card attributes (power, toughness, keywords) to fill the templates.
3.  All generated JSON files include a `set_code` field to ensure the `ScenarioRunner` uses the correct rule engine configuration.
