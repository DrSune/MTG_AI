print("--- Executing engine.py ---")
import uuid
import random
from typing import List, Union, Optional

from .game_graph import GameGraph, Entity
from . import card_database, vocabulary as vocab
from .handlers import mana_handlers, combat_handlers, keyword_handlers, effect_handlers, triggered_ability_handlers
from .effect_manager import EffectManager
from .layer_system import LayerSystem
from .state_recorder import StateRecorder
from .actions import (
    PlayLandAction, CastSpellAction, ActivateManaAbilityAction,
    DeclareAttackerAction, DeclareBlockerAction, PassPriorityAction, PassTurnAction,
)
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

AnyAction = Union[
    PlayLandAction, CastSpellAction, ActivateManaAbilityAction,
    DeclareAttackerAction, DeclareBlockerAction, PassPriorityAction, PassTurnAction,
]

logger = setup_logger(__name__)

class StackItem:
    def __init__(self, source_id: uuid.UUID, controller_id: uuid.UUID, effect_data: dict, target_id: Optional[uuid.UUID] = None):
        self.source_id = source_id
        self.controller_id = controller_id
        self.effect_data = effect_data
        self.target_id = target_id

class Engine:
    def __init__(self, graph: GameGraph, manual_mode: bool = False):
        self.graph = graph
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        self.manual_mode = manual_mode
        self.effect_manager = EffectManager()
        self.layer_system = LayerSystem(self.effect_manager)
        self.recorder = StateRecorder()
        self.game_over = False
        self.winner_id = None
        self.stack = []
        self.move_count_this_step = 0
        self.MAX_MOVES_PER_STEP = 500 # Increased for foundation exploration
        self.stall_detected = False
        self.recorder.record(self.graph, "Game Initialized")
        logger.info("Engine initialized.")

    def _can_pay_cost(self, mana_pool: dict, cost: dict) -> bool:
        temp_pool = mana_pool.copy()
        for mana_type, amount in cost.items():
            if mana_type == self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary"): continue
            if temp_pool.get(mana_type, 0) < amount: return False
            temp_pool[mana_type] -= amount
        generic_mana_id = self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary")
        generic_cost = cost.get(generic_mana_id, 0)
        return sum(temp_pool.values()) >= generic_cost

    def get_legal_moves(self) -> List[AnyAction]:
        legal_moves: List[AnyAction] = []
        # Save original active player
        original_active_id = self.graph.active_player_id
        
        active_player_id = self.graph.active_player_id
        defending_player_id = next((pid for pid in self.graph.players if pid != active_player_id), active_player_id)
        
        is_block_step = self.graph.step == self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary")
        decision_player_id = defending_player_id if is_block_step else active_player_id
        decision_player = self.graph.entities[decision_player_id]
        
        # Temporary priority swap for environment visibility
        self.graph.active_player_id = decision_player_id

        try:
            if is_block_step:
                legal_blockers = combat_handlers.get_legal_blockers(self.graph, decision_player_id)
                attacking_creatures = [c for c in self.graph.entities.values() if c.properties.get('is_attacking')]
                for blocker in legal_blockers:
                    for attacker in attacking_creatures:
                        legal_moves.append(DeclareBlockerAction(player_id=decision_player_id, blocker_id=blocker.instance_id, attacker_id=attacker.instance_id))
            
            legal_moves.append(PassPriorityAction(player_id=decision_player_id))
            
            is_main = self.graph.phase in [self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary")]
            if is_main and decision_player_id == original_active_id:
                legal_moves.append(PassTurnAction(player_id=decision_player_id))
                if decision_player.properties.get('lands_played_this_turn', 0) < 1:
                    hand_cards = self.graph.get_entities_in_zone(decision_player_id, vocab.ID_ZONE_HAND)
                    for land in [c for c in hand_cards if c.properties.get('is_land')]:
                        legal_moves.append(PlayLandAction(player_id=decision_player_id, card_id=land.instance_id))
                        break

            mana_pool = decision_player.properties.get('mana_pool', {})
            virtual_mana = mana_pool.copy()
            for r in self.graph.get_relationships(source=decision_player, rel_type=vocab.ID_REL_CONTROLLED_BY):
                card = self.graph.entities[r.target]
                if card.properties.get('is_land') and card.properties.get('is_on_battlefield') and not card.properties.get('tapped'):
                    gen_id = self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary")
                    virtual_mana[gen_id] = virtual_mana.get(gen_id, 0) + 1

            legal_moves.extend(mana_handlers.get_tap_for_mana_moves(self.graph, decision_player))

            hand_cards = self.graph.get_entities_in_zone(decision_player_id, vocab.ID_ZONE_HAND)
            for card in hand_cards:
                if not card.properties.get('is_land'):
                    if is_main or card.properties.get('is_instant'):
                        cost = card_database.get_card_cost(card.type_id)
                        if cost and self._can_pay_cost(virtual_mana, cost):
                            targets = effect_handlers.get_spell_potential_targets(self.graph, card)
                            if targets:
                                for t in targets:
                                    legal_moves.append(CastSpellAction(player_id=decision_player_id, card_id=card.instance_id, target_id=t.instance_id))
                            else:
                                legal_moves.append(CastSpellAction(player_id=decision_player_id, card_id=card.instance_id))

            if self.graph.step == self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary") and decision_player_id == original_active_id:
                legal_attackers = combat_handlers.get_legal_attackers(self.graph, decision_player_id)
                for attacker in legal_attackers:
                    legal_moves.append(DeclareAttackerAction(player_id=decision_player_id, card_id=attacker.instance_id))

        except Exception as e:
            logger.error(f"Legal Moves Error: {e}")
        finally:
            # RESTORE ORIGINAL ACTIVE PLAYER
            self.graph.active_player_id = original_active_id
            
        return legal_moves

    def execute_move(self, move: AnyAction) -> List[str]:
        events = []
        try:
            self.move_count_this_step += 1
            if self.move_count_this_step > self.MAX_MOVES_PER_STEP:
                self.game_over = True
                return ["Error: Infinite Loop"]

            pre_permanents = {eid for eid, e in self.graph.entities.items() if e.properties.get('is_on_battlefield')}
            player = self.graph.entities.get(getattr(move, 'player_id', None))
            card = self.graph.entities.get(getattr(move, 'card_id', None))

            if isinstance(move, PlayLandAction):
                bz = self.graph.get_zone(player.instance_id, vocab.ID_ZONE_BATTLEFIELD)
                self.graph._move_card_to_zone(card, bz)
                player.properties['lands_played_this_turn'] = player.properties.get('lands_played_this_turn', 0) + 1
                events.append(f"{player.properties.get('name')} played {card.properties.get('name')}")
            elif isinstance(move, ActivateManaAbilityAction):
                mana_handlers.execute_tap_for_mana(self.graph, player, card, move.ability_id)
                events.append(f"{player.properties.get('name')} tapped {card.properties.get('name')} for mana")
            elif isinstance(move, CastSpellAction):
                cost = card_database.get_card_cost(card.type_id)
                mp = player.properties['mana_pool']
                for mt, amt in cost.items(): mp[mt] = mp.get(mt, 0) - amt
                self.stack.append(StackItem(card.instance_id, player.instance_id, {"ability_type": "spell_resolution"}, move.target_id))
                card.properties['is_on_stack'] = True
                events.append(f"{player.properties.get('name')} cast {card.properties.get('name')}")
                triggered_ability_handlers.check_triggers(self.graph, "cast_spell", card)
            elif isinstance(move, DeclareAttackerAction):
                combat_handlers.declare_attacker(self.graph, card)
                events.append(f"{player.properties.get('name')} attacked with {card.properties.get('name')}")
            elif isinstance(move, DeclareBlockerAction):
                attacker = self.graph.entities.get(move.attacker_id)
                self.graph.add_relationship(card, attacker, self.id_mapper.get_id_by_name("Blocking", "game_vocabulary"))
                events.append(f"{player.properties.get('name')} blocked {attacker.properties.get('name')} with {card.properties.get('name')}")
            elif isinstance(move, PassPriorityAction):
                if self.stack: events.append(self.resolve_stack())
                else:
                    self.progress_phase_and_step()
                    events.append(f"Phase -> {self.id_mapper.get_name(self.graph.phase, 'game_vocabulary')}")
            elif isinstance(move, PassTurnAction):
                self.end_turn(move.player_id)
                events.append("Turn Passed")

            self.layer_system.apply_all_layers(self.graph)
            self.check_state_based_actions()
            
            if hasattr(self.graph, 'queued_triggers') and self.graph.queued_triggers:
                for t in self.graph.queued_triggers:
                    self.stack.append(StackItem(t["source_id"], t["controller_id"], t["effect_data"]))
                self.graph.queued_triggers = []

            post_permanents = {eid for eid, e in self.graph.entities.items() if e.properties.get('is_on_battlefield')}
            for eid in pre_permanents - post_permanents:
                gz = self.graph.get_zone(player.instance_id, vocab.ID_ZONE_GRAVEYARD)
                triggered_ability_handlers.check_triggers(self.graph, "enters_zone", self.graph.entities[eid], gz.type_id)
            for eid in post_permanents - pre_permanents:
                bz = self.graph.get_zone(player.instance_id, vocab.ID_ZONE_BATTLEFIELD)
                triggered_ability_handlers.check_triggers(self.graph, "enters_zone", self.graph.entities[eid], bz.type_id)

            self.recorder.record(self.graph, f"Move: {type(move).__name__}")
            return [e for e in events if e]
        except Exception as e:
            logger.error(f"Exec Error: {e}"); return [f"Error: {e}"]

    def resolve_stack(self) -> str:
        if not self.stack: return ""
        item = self.stack.pop()
        source, player = self.graph.entities.get(item.source_id), self.graph.entities.get(item.controller_id)
        effect_handlers.resolve_spell_effects(self.graph, player, source, item.target_id, effect_manager=self.effect_manager)
        if source.properties.get("is_instant") or source.properties.get("is_sorcery"):
            self.graph._move_card_to_zone(source, self.graph.get_zone(player.instance_id, vocab.ID_ZONE_GRAVEYARD))
        else:
            if source.properties.get('has_as_enters_choice'):
                from .handlers import card_specific_handlers
                card_specific_handlers.handle_generalized_enters_choice(self.graph, source)
            self.graph._move_card_to_zone(source, self.graph.get_zone(player.instance_id, vocab.ID_ZONE_BATTLEFIELD))
            source.properties['is_on_battlefield'] = True
            if source.properties.get('is_creature'): source.properties['has_summoning_sickness'] = True
        source.properties['is_on_stack'] = False
        return f"Resolved {source.properties.get('name', 'Spell')}"

    def progress_phase_and_step(self, force_next_phase: bool = False):
        self.move_count_this_step = 0
        beginning_id = self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary")
        turn_phases = [beginning_id, self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary")]
        phase_steps = {
            beginning_id: [self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"), self.id_mapper.get_id_by_name("Upkeep Step", "game_vocabulary"), self.id_mapper.get_id_by_name("Draw Step", "game_vocabulary")],
            self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"): [self.id_mapper.get_id_by_name("Beginning of Combat Step", "game_vocabulary"), self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary"), self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary"), self.id_mapper.get_id_by_name("Combat Damage Step", "game_vocabulary"), self.id_mapper.get_id_by_name("End of Combat Step", "game_vocabulary")],
            self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary"): [self.id_mapper.get_id_by_name("End of Turn Step", "game_vocabulary"), self.id_mapper.get_id_by_name("Cleanup Step", "game_vocabulary")]
        }
        try:
            current_steps = phase_steps.get(self.graph.phase, [self.graph.step])
            try: 
                idx = current_steps.index(self.graph.step)
            except ValueError:
                logger.error(f"Step {self.graph.step} not found in current_steps {current_steps} for phase {self.graph.phase}")
                idx = -1
                
            if not force_next_phase and idx < len(current_steps) - 1: 
                self.graph.step = current_steps[idx+1]
            else:
                try:
                    p_idx = turn_phases.index(self.graph.phase)
                except ValueError:
                    logger.error(f"Phase {self.graph.phase} not found in turn_phases {turn_phases}")
                    raise
                    
                self.graph.phase = turn_phases[(p_idx + 1) % len(turn_phases)]
                if self.graph.phase == beginning_id:
                    self.graph.turn_number += 1
                    ops = [p for p in self.graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != self.graph.active_player_id]
                    if ops: self.graph.active_player_id = ops[0].instance_id
                self.graph.step = phase_steps.get(self.graph.phase, [self.graph.phase])[0]
        except Exception as e:
            logger.error(f"Error in progress_phase_and_step: {e}")
            raise
        
        triggered_ability_handlers.check_triggers(self.graph, "beginning_of_step", self.graph.step)

        for pid in self.graph.players: self.graph.entities[pid].properties['mana_pool'] = {}
        if self.graph.step == self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"):
            ap = self.graph.entities[self.graph.active_player_id]; ap.properties['lands_played_this_turn'] = 0
            for c in self.graph.entities.values():
                if self.graph.get_controller_id(c) == ap.instance_id:
                    c.properties['tapped'] = False
                    if c.properties.get('is_creature'): c.properties['has_summoning_sickness'] = False
        elif self.graph.step == self.id_mapper.get_id_by_name("Draw Step", "game_vocabulary"): self.graph.draw_card(self.graph.entities[self.graph.active_player_id])
        elif self.graph.step == self.id_mapper.get_id_by_name("Combat Damage Step", "game_vocabulary"): combat_handlers.assign_combat_damage(self.graph)
        elif self.graph.step == self.id_mapper.get_id_by_name("Cleanup Step", "game_vocabulary"):
            for pid in self.graph.players:
                hand = self.graph.get_entities_in_zone(pid, vocab.ID_ZONE_HAND)
                if len(hand) > 7:
                    for c in random.sample(hand, len(hand)-7): self.graph._move_card_to_zone(c, self.graph.get_zone(pid, vocab.ID_ZONE_GRAVEYARD))
            for c in self.graph.entities.values():
                if c.properties.get('is_creature'):
                    c.properties['is_attacking'] = False; c.properties['damage_taken'] = 0
                    for r in [r for r in self.graph.relationships if r.source == c.instance_id and r.type_id == self.id_mapper.get_id_by_name("Blocking", "game_vocabulary")]: self.graph.relationships.remove(r)
        self.check_state_based_actions()

    def check_state_based_actions(self):
        for pid, p in self.graph.entities.items():
            if p.type_id == vocab.ID_PLAYER:
                if p.properties.get('lost_by_deckout') or p.properties.get('life_total', 20) <= 0:
                    self.game_over = True; self.winner_id = next(op_id for op_id, op in self.graph.entities.items() if op.type_id == vocab.ID_PLAYER and op_id != pid)
                    return
        for eid, e in list(self.graph.entities.items()):
            if e.properties.get('name') == "Nine Lives" and e.properties.get('is_on_battlefield'):
                if e.properties.get('reincarnation_counters', 0) >= 9: effect_handlers.apply_destroy(self.graph, e)
            if e.properties.get('is_on_battlefield') and (e.properties.get("is_creature") or card_database.get_creature_stats(e.type_id)):
                stats = card_database.get_creature_stats(e.type_id) or {}
                t = e.properties.get('effective_toughness', stats.get('toughness', 0)); d = e.properties.get('damage_taken', 0)
                if (d >= t and t > 0) or t <= 0: effect_handlers.apply_destroy(self.graph, e)

    def end_turn(self, pid: uuid.UUID):
        start = self.graph.active_player_id
        for _ in range(20):
            if self.graph.active_player_id != start: break
            self.progress_phase_and_step(True)

    def get_reward(self, pid: uuid.UUID) -> float:
        if self.game_over: return 1.0 if pid == self.winner_id else -1.0
        return 0.0
