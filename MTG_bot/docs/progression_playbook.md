# MTG AI Progression Playbook: First-Principles Validation

This document outlines a scalable, first-principles framework for validating MTG AI performance. It is designed to graduate the bot from immediate state resolution (Level 1) to sophisticated second-order thinking (Level 4).

> [!IMPORTANT]
> **Evaluation Philosophy**: A bot's success must be measured by its ability to navigate heuristics, not its ability to brute-force a game tree. Search depth and node evaluation limits must be tightly controlled during these tests to ensure the bot has *learned* the concepts rather than simply calculated them.

---

## Level 1: First Principles (Immediate State Resolution)
**Learning Goal**: Rules engine mastery and terminal state identification.
**Solution Space**: Depth 1.

| ID | Concept | Description |
|:---|:---|:---|
| **1.1** | **Combat Lethal** | Recognizing when unblocked power exceeds opponent life. Attack with all. |
| **1.2** | **Spell Lethal** | Utilizing "reach" (e.g., burn spells) to close a game. |
| **1.3** | **Survival Block** | Prioritizing life survival over creature value when facing lethal. |
| **1.4** | **Survival Sweeper** | Identifying when a board reset (Wrath of God effect) is required to survive the next turn. |

---

## Level 2: Leverage and Sequencing (Resource Efficiency)
**Learning Goal**: Generating disproportionate value from minimal inputs.
**Key Heuristic**: Proper phasing and sequencing.

| ID | Concept | Description |
|:---|:---|:---|
| **2.1** | **Information Sequencing** | Drawing cards first to maximize information before making land/combat decisions. |
| **2.2** | **Mana Maximization** | Spending mana efficiently across phases (e.g., prioritizing 3-drops over 2-drops). |
| **2.3** | **The Favorable Trade** | Trading low-value assets for high-value opponent assets. |
| **2.4** | **Post-Combat Main Phase** | Withholding board information until after combat to complicate opponent decisions. |

---

## Level 3: Interactivity (The Stack and Timing)
**Learning Goal**: Understanding that responding is often higher leverage than acting.
**Key Heuristic**: Timing as a resource.

| ID | Concept | Description |
|:---|:---|:---|
| **3.1** | **"In Response" Blowout** | Invalidating opponent resources (Auras/Equip) by casting removal on the stack. |
| **3.2** | **EOT (End of Turn) Mastery** | Holding up interaction mana and using it proactively only at the end of the opponent's turn. |
| **3.3** | **The Combat Trick** | Using hidden information (pump spells) after blockers are declared. |

---

## Level 4: Second-Order Thinking (Anticipation)
**Learning Goal**: Incomplete information management and future turn optimization.
**Key Heuristic**: Risk management and baiting.

| ID | Concept | Description |
|:---|:---|:---|
| **4.1** | **Playing Around Sweepers** | Choosing not to over-extend into a likely board wipe. |
| **4.2** | **The Bluff Attack** | Forcing sub-optimal behavior by representing cards that are not in hand. |
| **4.3** | **Baiting the Counter** | Sacrificing a secondary threat to resolve a primary win condition. |

---

## Implementation Constraints for Agents

### 1. Reward Function Delta (Incremental Success)
Puzzles should not be binary Win/Loss. They must score based on **incremental advantages**. 
- *Example*: In "Playing Around Sweepers", the success criteria is: `HandSize > 0 AND LifeTotal > 0 on Turn T+1`.

### 2. Concept Tagging
Every puzzle in the database must be tagged with its core conceptual heuristic.
- *Format*: `{"concept": "Stack_Interaction", "set": "M21", "level": 3}`
- *Purpose*: Allows hot-swapping specific cards while maintaining the underlying logic when scaling to other sets.

---

> [!TIP]
> **Mastery Threshold**: A level is considered mastered when accuracy is >98% over 3 consecutive evaluations (Generations). At this point, the evaluation focus should shift to the next level of the framework.
