# Project Goals

This document outlines the goals, ideas, and scope of the Projekt Projector project.

## Core Objective

The primary goal of this project is to develop a sophisticated AI that can play Magic: The Gathering. This involves several key components:

*   **Game Engine:** A robust rule engine that can accurately simulate the game of Magic: The Gathering.
*   **Card Recognition:** The ability to recognize Magic: The Gathering cards from images.
*   **Strategic Brain:** A deep learning model that can make strategic decisions and play the game at a high level.

## Key Ideas and Approaches

### Card Recognition

*   **Data Acquisition:**
    *   Extract card images from various sources, including YouTube videos (card openings, gameplay), and online forums.
    *   Use a bounding box algorithm to extract individual cards from images.
    *   Utilize OCR to extract text from card names, types, and abilities.
    *   Match extracted card names with a comprehensive card database (e.g., Scryfall).
*   **Vector Database:**
    *   Create a vector database of card images for efficient similarity search.
    *   Store a few diverse, real examples per card (5-20).
    *   Ensure that the images in the vector database have no background, only the pure card.
    *   Training samples, however, should include various backgrounds.
*   **Hard Negative Mining:**
    *   Actively seek out and include examples where the model fails or confuses cards to improve its accuracy.

### Strategic Brain (AI Player)

*   **MCTS and Imperfect Information:**
    *   Use Information Set Monte Carlo Tree Search (ISMCTS) to handle the imperfect information nature of card games.
    *   Employ determinization by sampling opponent hands and decks to run simulations.
*   **Opponent Modeling:**
    *   Develop a separate neural network to predict the opponent's hand, deck, and strategy.
    *   This prediction will be used to inform the MCTS simulations.
*   **Reward and Learning:**
    *   Backpropagate rewards based on game outcomes (win/loss).
    *   Use a discount factor to weigh the importance of actions taken at different stages of the game.
    *   Implement a cost-sensitive auxiliary loss to prioritize learning from high-impact scenarios.
*   **Deck Discovery and Evolution:**
    *   Explore methods for discovering "niche" decks and avoiding forgetting them.
    *   Use techniques like mutation (evolutionary strategies), under-confidence sampling, and novelty rewards.
    *   Maintain an "elite pool" or experience buffer of niche decks.
    *   Employ adversarial training to test deck robustness.

## Image Naming Convention

*   **Single-Card Images:** `{card_name}_{set_code}_{collector_number}.png`
*   **Multi-Card Images:** `{source/video_id}_{timestamp/frame_number}.png`

## Card Tracking Database

*   Create a database (e.g., an Excel spreadsheet or a simple database) to track the number of examples for each card.
*   This database should store information on a per-unique-card/set basis.

