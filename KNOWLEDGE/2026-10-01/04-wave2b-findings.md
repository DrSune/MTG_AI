# 04 — Wave 2b findings (round 18b validation packs, engine FROZEN)

Scope: wave2b_rows.json spell cards "Peer into the Abyss" → "Wildwood Scourge"
(33 cards). Outcome: **18 green packs** graduated to `tools/scenarios/`
(18/18 in `--dir /tmp/opencode/b2b`) + **15 suspects** in
`tools/audit/suspects/` (13 new + 2 carry-overs re-confirmed: capture_sphere,
wildwood_scourge). 18 + 15 = 33. No engine, harness, or pre-existing pack was
touched. Concurrent sibling sessions grew the scenarios dir 84 → 126 files and
the suspects dir with 12 foreign files; none were modified.

## Green passes (18 packs)

shock, revitalize, titanic_growth, sure_strike, unleash_fury, rangers_guile,
unsubstantiate, rise_again, swift_response, run_afoul, soul_sear,
volcanic_geyser, village_rites, rain_of_revelation, pestilent_haze,
read_the_tides, primal_might_x, traitorous_greed.

Notes worth keeping:
- **read_the_tides**: mode ask vocabulary `('0','1')`; pass `targets` AND
  `decisions:["0"]` on the cast op. Quirk (documented, NOT a suspect): the
  compiled union target slot (up to two creatures, min 1) is validated BEFORE
  mode selection, so draw-mode requires a designated extra target
  (`selection:count_below_min:0<1` otherwise). Both mode effects are faithful
  to the printed card → green with quirk note in the pack.
- **run_afoul** works with ZERO targets and ZERO decisions (auto-selects the
  flyer) — a single-TARGET spell does not need the designation channel when
  exactly one legal target exists.
- **shock / volcanic_geyser**: the `damage` lane of a dead creature vanishes;
  assert lethality through the `graveyard` zone lane instead.
- **soul_sear** doubles as Brash Taunter trigger coverage: the compiled
  "damage dealt to BT → that much to target opponent" trigger fires when BT
  IS dealt damage (incidental life assert `{"0":15}`). Synths carry no
  keywords field, so keyword promises need real cards.
- **traitorous_greed**: mana-by-chain proof — pay `{"0":{"R":4}}` exactly,
  answer the two-mana ask with ONE word `"R"`, then chain a second spell;
  generic costs are payable from any color pool.
- **primal_might_x** adds the PT closure to the existing
  primal_might_fight.json.
- pestilent_haze covers both modes via two cast ops with decisions.

## Suspects (13 new + 2 carry-overs)

peer_into_the_abyss, return_to_nature, rookie_mistake, sanguine_indulgence,
scorching_dragonfire, see_the_truth, sparkhunter_masticore,
thrill_of_possibility, track_down, transmogrify, turn_to_slag,
secure_the_scene, volcanic_salvo — plus capture_sphere and wildwood_scourge
re-confirmed (lines appended 2026-10-01): capture_sphere cast is still
`cast:not_a_spell` and `enchant` journals no MOVE_ZONE so the aura ETB never
sees a host (host stays untapped); wildwood_scourge cast x=2 is still
`not_a_spell` and the ETB route dies on 'QX has no declared X'.

Root-cause highlights:
- **turn_to_slag** (two compounding defects):
  1. `executor/selectors.py:396` `role_handles` binding-precedence: the
     DESTROY atom's ALL-selector carries no top-level referent binding, so
     the spell-level TARGET designation wins — DESTROY buries the DESIGNATED
     creature. Probe proof: a 6/6 that survives the 5 damage DIES to its own
     Turn to Slag.
  2. The golden IR compiles the Equipment clause correctly
     (`DESTROY ALL battlefield SUBTYPE_EQ Equipment AND IS_ATTACHED_TO
     referent=target`, see `/tmp/opencode/ir/Turn_to_Slag.json`) but the
     executor implements only `IS_ATTACHED_TO_SOURCE`
     (`executor/quantity.py:490`); plain `IS_ATTACHED_TO` has no evaluator
     and would raise if reached.
- **secure_the_scene**: the CREATE_TOKEN atom compiles with only the `tokens`
  role (no controller role, `/tmp/opencode/ir/Secure_the_Scene.json`) and
  `verbs.py:655` `_v_create_token` hardcodes `ctx.controller` — the Soldier
  token goes to the CASTER even when an opponent's permanent is exiled.
  Probe: Secure the Scene on an opponent creature mints a Soldier under p0.
- Harness-bound suspects (targeting infra, not card logic):
  peer_into_the_abyss (TARGET_PLAYER designation impossible via
  `cast(targets=packkeys)` → `count_below_min`), spells with >1 TARGET
  selector (`NotImplementedError: … more than one TARGET selector needs
  per-slot designation (arc 3)`), and cost-gated cards uncastable in the
  frozen harness (sanguine_indulgence `cost:mana_generic:0<3`,
  volcanic_salvo `cost:mana_generic:8<10`).

## Harness facts learned this wave
- `battlefield_pt` / `battlefield_keywords` lanes key by card NAME, not pack
  key; `tokens` lane has NO controller dimension (token-controller promises
  are untestable → root-caused in code instead).
- `begin_turn` draws NO card on turn 1; hand lanes are exact counts.
- `enter` accepts `"tapped": true`. There is no `mana` expect lane; prove
  mana addition by chained cast with an exact-cost pool.
- Real Equipment needs `type_line "Artifact — Equipment"` + the `enchant` op
  to attach; synth cards lack the type_line nuance the Slag filter wants.

Verification: `tools/run_scenarios.py --dir /tmp/opencode/b2b` → 18/18;
full-dir run + `pytest MTG_bot/core -q` results recorded in the session
return (core suite unchanged: engine frozen).
