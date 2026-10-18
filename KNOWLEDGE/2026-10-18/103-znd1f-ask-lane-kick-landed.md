# 103 — ZND-1f LANDED: kick is model-visible — `card:N+kick` candidate with cost grounding in menus, spans and recordings

Date: 2026-10-18 (subagent implementation of the /102 binding spec; working tree at
2900c74 + sibling b7 wave; NO commit made — dispatch kept off git per coordination law).

## What landed (files touched — exactly the /102 claim lane, zero templates/compiler)
1. `tools/training/bc_data_v2.py` (tokenizer surface): `KICK_SUFFIX="+kick"`,
   `split_kick()` / `kick_token()` (decision 1/3; `split_kick("+kick")` bare-suffix
   edge stays literal), `kicker_cost_words(executor, handle)` — decision 2 grounding:
   `spell_record -> kicker_of -> effect_words(cost)` (static tree, same name-bag
   vocabulary as option-set rows); `card_row_lookup(world, kick_words=None)` and
   `ground_candidates(..., kick_words=None)` resolve the suffix: kick candidate =
   base referent row + `["kick"] + cost_words`; unknown handle + suffix stays
   ungroundable (no phantom).
2. `tools/training/ab_duel.py`: `_cards_rows_of` resolves suffixed snapshot tokens
   via the new INERT `obs["_kick"]` cost table (underscore keys never serialize —
   `_cards` precedent), so base spans are byte-unchanged everywhere.
3. `tools/eval/gameplay_eval_v2.py`: `_menu` presents BOTH priced rows
   (`kick_token(str(r.handle), r.kicked)`; legality already sorts base-before-kicked
   — the un-kicked dedupe regression is what used to drop the kicked row);
   `_act_obs` ships `obs["_kick"]` cost grounding. `take_acts` needed NO extra
   resolution code: the rows dict maps the suffixed token straight to the kicked
   `CastOption` and `play_cast` passes `row.kicked` (decision 4 round-trip).
4. `tools/eval/test_znd1f_kick_visibility.py` (NEW, 9 tests) — all spec gates.
5. NOT touched: `collector.py` (recording flows automatically once candidate strings
   differ — pinned by test), `MTG_bot/core/executor/games.py` — map item (d) was
   STALE: ZND-1e (9e78ae3) already casts with `kicked=row.kicked` (games.py:578);
   the seeded rigged-pool RandomPolicy episode test proves kicks already occur.

## Gate numbers (all executed 2026-10-18)
- Unit gates: `pytest tools/eval/test_znd1f_kick_visibility.py -q` → **9 passed**
  (both-rows menu + dedupe-regression dies; token→row round-trip; spans DIFFER and
  kicked span ⊇ kicker-cost words while base span = HEAD encoding; anti-phantom
  (starved pool emits no +kick); collector candidates distinguish + chosen_idx
  consistent; rig `act:main` recording contains the chosen `+kick` candidate and the
  journal CAST row carries kicked=True; seeded RandomPolicy rigged-pool episode
  journals ≥1 kicked cast; split/kick_token edges).
- M21 byte-identity: double-encode of ALL 11 corpus files
  (`tools/training/episodes*.jsonl`: 11,032 episodes, vocab 1,094) through
  `build_vocab_v2`+`encode_episode_v2`, pre-edit vs post-edit artifacts byte-compared
  (`cmp`): **diff = 0**.
- Scenarios: `.venv/bin/python tools/run_scenarios.py` → **403/403 packs passed** =
  the 402 HEAD packs unchanged + the sibling b7 wave's UNTRACKED
  `tools/scenarios/znr_landfall_direction.json` (also passes).
- Suites: `.venv/bin/python -m pytest MTG_bot/core tools -q --ignore=MTG_bot/core/compiler`
  → **1955 passed, 0 failed**; `.venv/bin/python -m pytest MTG_bot/core/compiler -q`
  (sibling wave live there, run separately for attribution) → **896 passed, 34
  subtests, 0 failed**. Total 2851 green.
- Determinism: rigged scripted rig episode run twice → identical recorded steps,
  `journal.dump()` and digest (test); collector determinism pin in-suite.
- Lint/type: `ruff check` on the 3 touched modules + new test → **0 new findings**
  (bc_data_v2 9→9, ab_duel 1→1, gameplay_eval_v2 1→0 pre-existing I001 cleared by
  the added import block, test file 0); `pyright` on all four → **0 errors**.

## Deviations / residuals (registered)
- Gate 1e "RandomPolicy episode records ≥1 +kick CANDIDATE": the collector's provider
  lane only receives ENGINE asks; the cast menu is never an engine ask, so the literal
  `+kick`-candidate recording gate is satisfied on the rig lane (`PolicyActDriver`,
  the RandomPolicy subclass that IS the act-menu presenter + recorder), and the
  data-availability half is satisfied in a true `RandomPolicy.take_acts` episode
  (journal `kicked=True`). The spec's own "recording flows automatically once
  candidate strings differ" is pinned via the provider pass-through test.
- Rig-lane base cast candidates ground through `_cards` exactly as before ZND-1f
  (`snapshot_obs` already shipped it); the kicked row keeps that referent AND adds
  `kick`+cost words (§10). No span changed for any pre-existing candidate.
- /102's adversarial-diff gate remains for the orchestrator before commit (this
  dispatch was git-free: sibling b7 wave live).
- Incident: a stray `git stash` from a shell tail-reflex touched the tree ~2s; popped
  and verified fully restored (sibling files intact). No content loss; noted for
  transparency under the no-git law.

## POST-GATE (adversarial fresh-eyes, same day): COMMIT-GO + 1 blocker — FIXED before commit
- Independently re-verified: M21 byte-identity (HEAD-copy side-by-side, 11 corpora / 11,032 eps,
  vocab+encode sha256 identical all 11); grounding §10 pool-wide probe (no presented-but-ungrounded
  +kick, X-kicker legality-gated); single menu path => chosen_idx consistency; consumer lanes
  (noisy_policy/exploit) honestly ignore or base-bias suffixed tokens; no foreign/stash-debris hunks.
- **BLOCKER (executed probe, order-independent): teacher act-menu tie-break `max(casts, key=(cmc,h))`
  picked `card:N+kick` on EVERY cmc tie — "+kick" > base lexicographically -> every future
  teacher-generated stream would bake in systematic silent OVER-KICK** (biased-priors archetype).
  Fixed: key now (cmc, UNKICKED-preferred, handle); pinned by 3 new tests (hostile-order tie, cmc
  priority unchanged, kicked-only still selectable) -> module 12/12. On kick-free pools the added key
  component is a constant => teacher M21 behavior bit-identical (strictly order-preserving).
- Hardening (gate residual): a presented +kick row with EMPTY kicker-cost grounding now RAISES
  (assert, never silently under-grounded) in _act_obs — impossible on probed pools, made loud.
- Post-fix gates re-run: tools/eval+tools/training 121 passed; scenarios 403/403 (sibling pack live).
