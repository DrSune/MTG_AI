# MTG AI Project Index

This file serves as a map for the codebase and documentation to help agents navigate efficiently.

## 📁 Project Structure

- `MTG_bot/`: Core logic for the MTG AI.
    - `rule_engine/`: The Magic: The Gathering rule implementation.
        - `engine.py`: Main game logic controller.
        - `game_graph.py`: State representation as a graph of entities and relationships.
    - `strategic_brain/`: The AI/RL components.
        - `decision_maker.py`: Move selection logic.
        - `state_converter.py`: Graph-to-tensor conversion.
    - `scenarios/`: (NEW) Tactical puzzles for benchmarking intelligence.
    - `data/`: Card databases (M21.json, mtg_bot.db).

## 📄 Documentation Tree

1.  **RL Architecture**: [System 2 Reasoning & Action Heads](docs/RL_ARCHITECTURE.md)
2.  **Benchmarking Intelligence**: [Metrics & Learning Progress](docs/BENCHMARKS.md)
    *   [Scenario Design Philosophy](docs/SCENARIO_DESIGN_PHILOSOPHY.md)
    *   [Procedural Generation](docs/PROCEDURAL_SCENARIOS.md)
3.  **Testing Strategy**: [Validation & Manual PvE](docs/TESTING_STRATEGY.md)
4.  **Project Maintenance**:
    *   [Agent Guidelines](docs/AGENT_GUIDELINES.md): Mandatory reading for future sessions.
    *   [Central Tasklist](docs/TASKLIST.md): Pending bugs and features.
5.  **Project Goals**: [High-level vision](../project_goals.md)

## 🚀 Getting Started

- To play manually: `python -m MTG_bot.main`
- To run tests: `pytest MTG_bot/rule_engine/test_engine.py`
- To run benchmarks: `python -m MTG_bot.scenarios.scenario_runner`

## 🛠️ Internal Systems

- `rule_engine/vocabulary.py`: Canonical IDs for game concepts (Mana, Phases, Zones).
- `rule_engine/card_data_loader.py`: Handles parsing from MTGJSON to our graph representation.
