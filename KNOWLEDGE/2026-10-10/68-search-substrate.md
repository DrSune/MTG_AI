# 68 — Search substrate: fork 6 ms / rollout 0.54 s — AlphaZero loop is affordable

Date: 2026-10-10. Producer: tools/search/{fork.py,rollout.py,test_fork.py} + additive `_play(resumed, stop_after)` in games.py (default path byte-identical).
- Fork = interning deepcopy (IR interned per-root, rng/provider/trace hygiene); 33x faster than replay-prefix (5.95 vs 196.2 ms), isolation + determinism pinned by fingerprint tests.
- rollout(): production _play loop, pluggable seat policies (random/greedy/any .decide), outcome incl. life-diff at cap; 536.8 ms midgame cap60; 1.86/s/core -> ~37/s across 20 cores. expand(): single-step legal options + boundary semantics (mid_act/pre_combat/post_combat), continuations exposed, desync tripwire.
- Pinned ask coverage positions: seed 20261010 t8 (choose, act via mid_act branch, attack), seed 14 t11 (block). Gotchas: silent combat = no asks; fork cost grows with journal; rollout consumes input game (fork first); mana-choose masks act menus at turn_top.
- Gates mine-run: pytest tools/search MTG_bot/core = 2532+2st; scenarios 398/398.
