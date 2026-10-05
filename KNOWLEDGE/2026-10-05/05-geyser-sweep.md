# 05-geyser-sweep — sweep, fix blueprint & D10 (2026-10-05)

> [!IMPORTANT]
> **CORRECTION (11:2x, same session):** the §1 INCIDENT below was a **false alarm — NOTHING was
> lost.** The live campaign tree is the HOST checkout itself, under **capital paths**:
> `MTG_bot/core/{compiler,executor,golden/M21(305),ability_tree,state,identity}` +
> `tools/{run_scenarios,measure_grammar,…}` + `tools/audit/exploit/` — all **tracked @4dbe864**;
> host gates pass fresh: run_scenarios **339/339**, `.venv/bin/python3 -m pytest MTG_bot/core -q`
> → **2360 passed + 3** (= campaign baseline). The lower-case `mtg_bot/` mirror I worked in for the
> first ~40 min was a stale sandbox copy that got discarded (its branch `master`/mtg_ai_tcg never
> existed in this .git). All numbers/edits from that mirror are VOID. The corrected batch state +
> ready-to-execute fix blueprint are below; the fix itself was NOT applied (context budget).

## 0. Corrected batch state (host, @4dbe864)
- **D10 pre-fix on host instrument**: `.venv/bin/python3 tools/audit/exploit/masked_target_probe.py 12`
  → **leak_opp_hidden=116** opponent-hidden candidates / 12 seeds (24 games), public=114;
  masked WR deltas +0.000 (floor doesn't monetize). Post-fix gate: **leak_opp_hidden=0**.
  (Probe takes POSITIONAL seeds, not `--seeds`.)
- **Sweep (all 305 goldens, `MTG_bot/core/golden/M21/*.json`, tagged-JSON walk of TARGET-mode
  Selectors)**: **87 cards / 99 selectors** carry `zone.kind=ANY` or `zone.controller.name=ANY`.
  Sub-families: (i) universal-filter FAnd() + zone ANY + ctrl ANY ≈14 cards incl. **Volcanic Geyser,
  Shock, Skeleton Archer, Terror of the Peaks, Goblin Arsonist, Havoc Jester, Meteorite, Pitchburn
  Devils, Chandra Heart of Fire, Ugin, Rin&Seri, Betra…(“any target” idiom class)**; (ii) ctrl ANY but
  bounded zone/filter (STACK counters, creature battlefield, GRAVEYARD Scavenging Ooze etc.) ≈85
  selectors — legitimately-broad or non-leaking → KEEP; (iii) printed-“target creature” with zone
  ANY+creature filter (defensive: hidden creature cards — separate future lane, OUT of R17-2 scope).
- **Leak mechanism (host code)**: `spell_target_slots`/`activation_target_slots`
  (`MTG_bot/core/executor/query.py:733/837`) enumerate candidates through the **designation face**
  `_designation_selector` (l.685, r19c “IS_ANY_TARGET tautology”) which for ANY-zone selectors
  enumerates **all cards in all zones incl. opponent hand/library**, then `_widen_any_target`
  (l.922) adds player seats — but ONLY for **universal (empty FAnd) filters** (a non-universal
  predicate would crash on `world.cards[player]`, per docstring l.752-760). That universal-only
  widening is why a naive template fix (FOr type filter) would silently KILL Shock’s player reach.
- **Template emission sites**: `_any_target()` in `templates_b2a.py:221`, `templates_b2b.py:305`,
  `templates_b5b.py`, `templates_b5c.py` (×3 call sites), `_sel_any_target()` in `templates_b3.py:448`
  (its test `test_templates_b3.py:542` *documents the leak* — “keeps creature cards in
  graveyards/libraries” — must flip to the restricted expectation).

## 0.1 Fix blueprint (next batch, ~1-2 h; R17-2 scope)
RED-FIRST pin (new `MTG_bot/core/test_geyser_any_target_pins.py`): build 2p game, opponent holds
hand+library cards, offer=`spell_target_slots` for compiled Volcanic Geyser SpellAbility → assert
∃ hidden candidate NOW (red @4dbe864), then after fix assert candidate set ==
{battlefield creatures/planeswalkers} ∪ {both players} exactly (same file, HEAD-pinned red style).
FIX: (1) templates: `_any_target()`/`_sel_any_target()` emit
`Selector(QConst(1), TARGET, FOr(FAtom TYPE_EQ Creature, FAtom TYPE_EQ Planeswalker),
Zone(BATTLEFIELD, ANY))` (player-side arrives via engine idiom widening, NOT via filter);
(2) executor: teach `_is_universal`/`_widen_any_target` to recognize the **any-target-idiom shape**
(FOr-of-TYPE_EQ{Creature,Planeswalker} + zone BATTLEFIELD) as player-widening-eligible without
evaluating the filter on player handles (mirror the existing universal lane; keep
19b opponent-zone auto-skip + 20b show-verdict lanes byte-stable — re-check dual-slot synthesis law:
the TARGET/TARGET_PLAYER synthesis must NOT newly fire on fixed casts).
GATES (host commands): `tools/run_scenarios.py` 339; `pytest MTG_bot/core -q` 2360+3+pins;
`tools/measure_grammar.py` PC-3 0, PC-4 0 after audited re-pin (goldens of idiom cards move —
C1-form backup + per-card set-equality, others byte-identical); D10 probe 12 → leak_opp_hidden=0
(standing gate thereafter); `noisy_policy 12` no regression; catalog/games per mission; pyright/ruff Δ0.
Sublime Epiphany deferrals cite: its TARGET selectors are zone STACK only → cite stays non-hidden,
amend wording per R17-1 §5 when its batch lands.

---
## 1. (SUPERSEDED) sandbox-LOSS INCIDENT narrative — kept per append-only law; see CORRECTION above.

: uncommitted campaign tree discarded (headline)

**What vanished (host path `/home/sune/Desktop/MTG_AI`, between 11:00:05 and 11:05):**
- `mtg_bot/` (lowercase package — **parser_compiler**: compile_card, `templates/card_templates.py`,
  executor/ (`directives.py`, `ask_builder.py`, `selectors.py`, `legality.py`, `response_window.py`),
  **goldens/ (all 305 compiled goldens)**, `mtg_bot/core/mtg_engine.py`, the +143 untracked
  core-test files (2360→2503), mtg_bot `scenarios/` runner) — **never tracked by git, now nowhere on disk**
- `server/` (`battle_log/` fleet jsonl), `tools/audit/bugcatch/` (replay_trace, promote…),
  `mtg_ai_tcg/` submodule. **Correction:** `tools/run_scenarios.py` + `tools/measure_grammar.py`
  live at `tools/` root and SURVIVE on the host (earlier GONE probe used wrong paths).
- my batch's /tmp snapshots (`/tmp/golden_pre_geyser` = 305-golden HEAD backup, `/tmp/pre_head`)

**Evidence the pre-loss commands ran in a *different* environment, not on this host checkout:**
- 11:00:05 `git status` reported branch **`master`** + dirty `mtg_ai_tcg/` submodule. This host `.git`
  has only `main` (no `master` ref, no master reflog ever); `main` = `4dbe864` untouched since 10:59:31.
- `python` (bare) was absent while `python3 -m pytest` worked there; on the host pytest lives only in
  `.venv/bin/python3` (matches NUMBERS.md command convention).
- Host forensics: all 166 commits on all refs scanned — **no commit ever contained** `mtg_bot/`,
  `mtg_engine.py`, `card_templates.py` or goldens. `git fsck` unreachable objects: nothing newer than
  2026-10-05 01:27 (old stash fragments); tree scan for `mtg_engine|card_templates` = 0 hits.
- `find /` for `compile_card.py|mtg_engine.py|Stingspector.json`: zero hits outside this report.
- My `git stash push -u -m geyser-batch` (~11:05, part of a command whose next segment failed on
  missing `python`) created **no** stash commit (pop: “No stash entries found”; fsck clean) — noted as
  a suspect, but the 11:00→11:05 branch/`mtg_ai_tcg`/PATH discontinuities show the environment swap
  was not caused by this batch. A concurrent `MERGE_RR` + 4dbe864 knowledge commit landed at 10:59,
  immediately pre-batch.

**Survivors (host, enough to rebuild the rig, NOT the compiler):**
- `tools/scenarios/` — **339 packs, TRACKED, intact** (incl. volcanic_geyser.json)
- `tools/audit/exploit/` — **all 7 D-probe instruments TRACKED** (masked_target_probe, noisy_policy, …)
- `tools/audit/` other tracked parts (bcs.py, branch_coverage.py, deferrals.json, measure_bugcatch.py, detectors.py)
- `MTG_bot/` (uppercase, original engine+conformance): `.venv/bin/python3 -m pytest MTG_bot/core -q` →
  **2360 passed + 3 subtests** — exactly the campaign baseline (confirms 2360 = tracked suite)
- `KNOWLEDGE/`, `reports/`, `bcs.json`, branch/pair coverage JSONs

**Immediate standing orders for every session:** (1) treat the workspace as FROZEN — no
`stash`/`clean`/`checkout`/`reset` until the swap's root cause (platform sandbox discard vs concurrent
actor) is identified; (2) interpreter is `.venv/bin/python3`; (3) **the reconstruction of
`mtg_bot/` (compiler+templates+goldens+engine lane+server) is the top-priority blocker for the whole
campaign** — ask the user whether the discarded sandbox image/snapshot or a backup exists anywhere
(e.g. opencode infra, another disk); ext4 undelete is a long shot (device mounted, load ~4.5).

## 2. Sweep result (completed pre-loss, 305 goldens)

- TARGET selectors with `zone=ANY` or `controller=ANY`: **36 selectors / 25 cards**.
- Class A “any target” idiom → restrict (confirmed from printed clause text, alphabetical A→E; the
  F→V tail incl. **Volcanic Geyser** + Shock-family was pending classification at loss time):
  Bedlam Appraiser (×2), Chandra’s(-2), Cruel Fate, Custo…, Defy Death (×2), Doomfall,
  Echoing Death (×3), Ery… — 8 cards shown of 25.
- Class B legitimately-broad printed zone targets → KEEP (e.g. graveyard/library retrieval spells;
  census had “graveyard” clauses in the ANY-family). Class C ambiguous: not reached.

## 3. Fix (implemented + green pre-loss — replay recipe)

1. `mtg_bot/parser_compiler/templates/card_templates.py`:
   - `_ANY_TARGET_IDIOM = re.compile(r"\bany\s+target\b")`; in `_synthesize_target_slots`:
     `any_target = bool(spec["target_player"] and _ANY_TARGET_IDIOM.search(spec.get("rules_text","")))`;
     `any_target or player_idiom` → `render_controller_selector("self")`, else `render_target_selector("any")`.
   - `render_target_selector`/`render_controller_selector` take `any_target: bool = False`;
     clause gains `'types': ['creature', 'planeswalker', 'player']` (player-side = Shock-family shape:
     controller=self + types filter; no zone key).
2. `mtg_bot/parser_compiler/executor/directives.py` `_match_player`: filter on `spec.get("types")`
   against `getattr(card, "card_type", [])` (mirrors `_match_object` type policy).

**Pre-loss verification (sandbox, non-reproducible until rebuilt):** run_scenarios **339/339**;
D10 Geyser **654 → 0** hidden candidates (`masked_target_probe.py --seeds 12`; 654 aggregate over 12
seeds, all `spell_target_slots|card:14:Volcanic Geyser`, source_probe attribution); Volcanic Geyser
cast ask = exactly `[Opponent P1, 'Volcanic Geyser deals 4 damage to any target.']` (player-only);
core suite 2503 collected incl. 43 new red-then-green pins (files also lost — rewrite recipe:
Geyser ask-enumeration vs opponent with hand+library, 20b verdict-table, 19b auto-skip set).
Not yet run pre-loss: noisy_policy after-fix, PC gates, catalog repin, games-100, deferrals Sublime
cite amendment (R17-1 §5).

## 4. NUMBERS note
D10 “before” on this host = recorded rows **58/12 games** (source_probe) / **234/48**
(masked_target_probe 24); the 654/12 figure came from the now-discarded sandbox build — treat both
as pre-fix confirmations, post-fix value unrecorded (tree lost before the standing gate could run).
