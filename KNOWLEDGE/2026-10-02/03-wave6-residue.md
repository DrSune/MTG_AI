# 03 — Wave-6 residue wave (2026-10-02)

Small closing wave for the two honest GAPS logged in /26 §corpus-status. Authoring-only
(engine FROZEN). Packs: 286 → 287 (+1 green); one new suspect file (13 → 14 on disk);
census re-derived with `tools/audit/wave_builder.py --coverage`: uncovered 31 → 29, both
rows flipped exactly as designed (no builder mode needed — `--coverage` re-derives from
disk; the refresh also legitimately promoted 5 stale uncovered/suspect rows whose packs
landed during the C1 sancta/shock promotions, pack>suspect precedence as coded).

## Verdicts

1. **Forgotten Sentinel — GREEN** (`tools/scenarios/forgotten_sentinel.json`).
   Golden IR (9bd4a0bd): the card's ONLY node is `EtBState{tapped:true}`; printed
   'This creature enters tapped.' Wave 1's EtB family derivation keyed on
   TriggeredAbility/ZoneChangeEvent nodes, so a pure-EtBState card was name-invisible —
   same blind spot class as the census-derived wave 2-5, now covered by the census itself.
   Method: hand → `enter` op (NO `tapped` step parameter, default false), so the
   `tapped:{fs:true}` lane can only be satisfied by the engine's journal ENTER-branch hook
   (`executor/__init__.py` `_on_zone_changes` → `_apply_etb_state`, CR 614.1c). Style twin:
   the wave-1 checkland EtBState packs (`blossoming_sands.json`), which reach the same
   stamp through `play`; non-lands have no play op, `enter` takes the role. FIRST_ATTEMPT
   green.

2. **Treasure token {T},Sac: Add-one-any — SUSPECT, HARNESS routing**
   (`tools/audit/suspects/treasure_token_activation.json`, setup witness
   `pool has no card 'Treasure'`). NOT a compiler defect — the engine side is demonstrably
   healthy: the Gadrak end-step trigger mints a real Treasure carrying its compiled
   `{T},Sac → ADD_MANA 1 ANY` ActivatedAbility (`binder.register_token`, verbs.py
   `_v_create_token`), and `_v_add_mana` even asks the decisions provider for the colour
   (vocab W/U/B/R/G/C, tag `mana:<source>`). The gap is a four-link ADDRESSING chain:
   (a) supply('all') = 285 metas, no token identities — `"real":"Treasure"` dies in
   `ScenarioRunner.__init__`; (b) synthetic Treasure = fake oracle_id, no binder record,
   nothing to activate; (c) the engine's only battlefield Treasure is the keyless
   Gadrak mint and `activate` resolves ONLY `self.handles[key]` (run_scenarios.py:352 —
   name-addressable lanes are report-only); (d) mana pool has no expect lane
   (documented since `chromatic_orrery.json` note; intended pack sidesteps via
   cast-payment consequence, the secure_the_scene method). Mint-half PROVEN: Gadrak +
   dead creature + `end_turn` → `tokens.Treasure=1` PASS (probe, /tmp/opencode/wave6/).
   Candidate rig fixes logged in the finding (name-addressable activate op, or token
   goldens in supply) — NOT built, authoring phase frozen. Gadrak's end-step Treasure
   clause, called "not asserted" in its own pack's notes, is now witnessed by the probe.

## Gate numbers (all after landing)

| Gate | Result | Command |
|---|---|---|
| runner | **287/287** (286 + sentinel) | `.venv/bin/python tools/run_scenarios.py` |
| suspects dir | **0/14** red, mine red at setup witness | `.venv/bin/python tools/run_scenarios.py --dir tools/audit/suspects` |
| suite | **2272 + 3 subtests, unchanged** (engine untouched) | `pytest MTG_bot/core -q` |
| census | 305 = 267 pack + 9 suspect + 29 uncovered; Treasure→suspect, Sentinel→pack | `.venv/bin/python tools/audit/wave_builder.py --coverage` |
| five-wave lint | all closed/consumed (66/67/55/43 + 3 waived) | `wave_builder.py --waveN --lint` |

## Rig laws learned (candidate PITFALLS rows)

- **Keyless-mint law**: engine-minted tokens have no pack key; every OPERAND op
  (activate/deal_damage/fight/combat maps) is key-resolved. Minted tokens are reachable
  only by report lanes (tokens/battlefield_pt) or by combat-phase ask vocabulary
  (secure_the_scene trick). Token identities are goldens/census rows, NOT pool metas.
- **ADD_MANA ANY is an ask**: a color-less ADD_MANA consumes one decision-provider word
  (W/U/B/R/G/C) before writing the pool — mana-activation packs must carry `decisions`.
- **EtBState rides every entry**: the `_apply_etb_state` stamp is in the journal's ENTER
  branch, so `play` AND `enter` (and cast resolution) stamp it; a pack that omits the
  `tapped` step parameter asserts the compiled node, not the harness.
