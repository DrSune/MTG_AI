import json
import os
import uuid
from datetime import datetime

class StateRecorder:
    """Records GameGraph states to JSON for visualization."""
    def __init__(self, output_dir="logs/history"):
        self.output_dir = output_dir
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.step_count = 0
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Clear old history for this session if it exists
        self.current_session_path = os.path.join(self.output_dir, self.session_id)
        os.makedirs(self.current_session_path, exist_ok=True)

    def record(self, graph, action_name="initial_state"):
        """Saves a snapshot of the current game graph."""
        state = {
            "step": self.step_count,
            "timestamp": datetime.now().isoformat(),
            "action": str(action_name),
            "turn": graph.turn_number,
            "phase": graph.id_mapper.get_name(graph.phase, "game_vocabulary"),
            "step_id": graph.id_mapper.get_name(graph.step, "game_vocabulary"),
            "active_player": str(graph.active_player_id),
            "entities": {},
            "relationships": []
        }

        for uid, entity in graph.entities.items():
            # Convert UUID properties to strings for JSON
            processed_props = {}
            for k, v in entity.properties.items():
                if isinstance(v, uuid.UUID):
                    processed_props[k] = str(v)
                elif isinstance(v, dict):
                    # Handle nested dicts like mana_pool (which uses int keys, also needs conversion)
                    processed_props[k] = {str(nk): nv for nk, nv in v.items()}
                else:
                    processed_props[k] = v

            state["entities"][str(uid)] = {
                "type_id": entity.type_id,
                "properties": processed_props,
                "display_name": graph._get_entity_display_name(entity)
            }

        for rel in graph.relationships:
            state["relationships"].append({
                "source": str(rel.source),
                "target": str(rel.target),
                "type_id": rel.type_id
            })

        file_path = os.path.join(self.current_session_path, f"state_{self.step_count:04d}.json")
        with open(file_path, "w") as f:
            json.dump(state, f, indent=2)
        
        # Also update a 'latest.json' for live view
        latest_path = os.path.join(self.output_dir, "latest.json")
        with open(latest_path, "w") as f:
            json.dump(state, f)

        self.step_count += 1
        return file_path
