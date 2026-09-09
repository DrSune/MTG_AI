# Attic — dead code, kept only for reference

Nothing in here is on the project's path. Do not import it, do not extend it, do not
read it looking for how the current system works. It is preserved because it records
what was tried.

| File | What it was | Why it is here |
|---|---|---|
| `mtg_rule_engine.py` | An **earlier, separate** rules engine | Highest-priority archive. It is not the engine. The live engine is `MTG_bot/rule_engine/`. Someone will otherwise open this first and lose an afternoon. |
| `legacy_game_state.py` | Original state scaffold, was `rule_engine/game_state.py` | Named like the state model, imported by nothing, superseded by `game_graph.py` on day one. A pure decoy. |
| `legacy_rulebook.py` | Was `rule_engine/rulebook.py` | Never instantiated anywhere, and `Rulebook()` raises `NameError` on construction. |
| `card_recognition_nn.py`, `card_extraction.py`, `basic_card_extraction.py` | Computer-vision card recognition from photos/video | The original project scoped card recognition alongside play. That is off the King Goal. **A live Weights & Biases API key was hardcoded in this file and committed to git history; it has been removed from the working tree but must still be revoked.** |
| `yt_frame_extractor.py`, `yt_scraping/` | YouTube scraping to harvest card images | Same dead branch as above. |
| `qwen.py`, `qwen_client.py`, `requirements_agent.txt` | An LM Studio / local-LLM agent harness | An abandoned attempt to drive development with a local model. |

If any of this becomes relevant again, it should be rewritten, not revived.
