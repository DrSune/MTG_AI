
import random
import time
from MTG_bot.strategic_brain.environment import MTGEnv
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.strategic_brain.deck_generator import Archetypes
from MTG_bot import config

def run_self_play():
    print("--- Starting Self-Play Integration Test ---")
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    env = MTGEnv(loader)
    
    # 1. Reset
    print("Resetting environment (Life Gain vs Ramp)...")
    obs = env.reset(format="limited", archetypes=(Archetypes.LIFE_GAIN, Archetypes.RAMP))
    
    done = False
    step_count = 0
    max_steps = 200 # Safety limit
    
    while not done and step_count < max_steps:
        # 2. Get Legal Actions
        legal_actions = env.get_legal_actions_as_tokens()
        
        # 3. Pick a random move
        action = random.choice(legal_actions)
        
        # 4. Step
        obs, reward, done, info = env.step(action)
        
        if step_count % 10 == 0:
            ap_life = obs["observation"][3]
            opp_life = obs["observation"][5]
            phase = obs["observation"][0]
            print(f"Step {step_count}: Active Player Life: {ap_life}, Opponent Life: {opp_life}, Phase: {phase}")
            print(f"  Action Taken: {info.get('action_taken')}")
            
        step_count += 1
        
    print(f"--- Game Over in {step_count} steps! ---")
    if done:
        winner = "Player 1" if obs["observation"][3] > 0 else "Player 2"
        print(f"Winner: {winner}")

if __name__ == "__main__":
    run_self_play()
