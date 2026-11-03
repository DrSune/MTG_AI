"""Self-play training for a per-seat entity-transformer policy (see README.md here).

Modules: ``features`` (what one seat may see, as arrays), ``heuristic`` (the rule-based anchor
and BC teacher), ``model`` (the network), ``actor`` (game worker processes), ``learner`` (BC,
PPO, evaluation, inference server).
"""
