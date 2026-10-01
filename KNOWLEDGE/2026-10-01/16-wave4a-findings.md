# Wave 4a findings — activated/mana/loyalty cohort, first half (2026-10-01)

Engine frozen. Batch = first 22 names of `tools/audit/wave4.json` (Animal Sanctuary →
Mazemind Tome); sibling batch 17 took the last 21. Deliverables: **17 packs promoted** to
`tools/scenarios/` (**222 → 239, 239/239 green**), **11 suspect files** (10 cards) filed in
`tools/audit/suspects/` (**library now 21**), gates **239/239 + 2213 pytest + 3 subtests**
unchanged. Generator of record: `/tmp/opencode/gen_w4a.py`; probe rigs `p1..p16.py` +
`w4h.py`.

## Green packs (17) — each asserts only end-state-true printed facts
animal_sanctuary · azusa_lost_but_seeking · basri_devoted_paladin · basri_ket (counter clause
only) · celestial_enforcer · fabled_passage (working half) · forest · garruk_unleashed (+1) ·
igneous_cur · island · jolrael_mwonvuli_recluse · keen_glidemaster · leafkin_avenger ·
liliana_death_mage (+1/−3/−7 full arc) · lilianas_steward · liliana_waker_of_the_dead (−3) ·
mazemind_tome.

Key rig facts proven green in-packs:
- **Mana pool persists across full cycles** (seeded C:4 survived end/advance/end/advance);
  generic `{N}` payments still consume colored first (standing wave-3b rig law) — Animal
  Sanctuary needed the Mazemind Tome `{2}{T}` sink because the runner has **no `pool` lane**.
- **Basri, Devoted Paladin 3-turn arc**: +1 (counter+vigilance) → −1 (attack trigger adds 2nd
  counter) → ledger-seed 6, −6 (+2/+2 + FLYING → 6/6, life 13) → 0-loyalty PW self-sacrifices
  to graveyard. `enter` stamps identity LOYALTY=4.
- **CR 606.3 enforced**: `window:loyalty:once_per_turn` refuses a 2nd loyalty ability of the
  same permanent in one turn window; `advance_turn` between activations, +1 draw to the
  rotated seat (death-mage pack, PITFALLS entry).
- **Jolrael SET_PT = live hand count at resolution** (2 here — no setup draw when the pack's
  last lib entry is a deliberate sink… layout-dependent; assert from the observed hand lane).
- Mazemind Tome PAGE counter (charge tracking) + scry-bottom ordering verified lane-by-lane.
- Fabled Passage green pack deliberately asserts NO tapped lane: its rig controls 4+ lands
  post-search, where the printed Commander-2021 text itself wants the land untapped.

## Suspects (11 files, `tools/audit/suspects/`, 0/11 fail-only)
1. **basri_ket_minus_two** — LOUD: `THAT_MANY_COUNT has no producer register` when the −2's
   X resolves during combat; whole −2 dead.
2. **basri_ket_plus_one_indestructible** — SILENT: counter lands but INDESTRUCTIBLE never
   granted AND loyalty increment missing (`LOYALTY 4` after +1).
3. **caged_zombie_died_condition** — LOUD: `condition:false` despite a CREATURE_DIES row this
   turn — the died-this-turn condition window is not consulted (two divergences in one card).
4. **chandras_magmutt_planeswalker** — SILENT: `{T}: 1 dmg to target player or PW` — player
   unaddressable; PW binds but **loyalty never decremented** (4→4).
5. **epitaph_golem_bottom** — SILENT: "put that card on the **bottom**" ignored — Chaff
   draw-throughs back to top (library shows full junk run, Chaff missing from bottom).
   Grammar CAN express it: `ZonePosition` TOP/BOTTOM exists at `ability_tree.py:328`;
   `verbs.py:964-1000` honors it; compiled atom carries `position=None`.
6. **fabled_passage_enters_tapped** — SILENT: searched basic land enters **untapped** when
   post-search you control <4 lands (printed: "onto the battlefield tapped … if four or more
   lands, untap"). Compiled SEARCH atom has `tapped_on_enter=None` while Cultivate's
   MOVE_ZONE siblings emit `True` — delivery template drops the flag. The ≥4-land branch is
   indistinguishable (Y2 probe: untapped, matching the conditional-untap clause), so the
   conditional is unfalsifiable — land is already untapped in every branch.
7. **furious_rise_activation** — LOUD: printed card has NO activated ability (pure end-step
   trigger; trigger half works), yet idx1 passes legality and crashes
   `selector referent 'result' has no register`. idx0's refusal
   (`ability:not_activated:TriggeredAbility`) is the correct negative.
8. **garruk_minus_two** — LOUD: `filter pred CONTROLLER_COUNT_GT not implemented (12c query
   surface)` at activation; whole −2 (incl. Beast tokens) dead.
9. **ghostly_pilferer_unblockable** — SILENT: discard cost resolves but `blocked[pilf]` still
   names the wall — the "can't be blocked" grant from its only activated ability never lands.
10. **leafkin_avenger_bolt** — SILENT: `{7}{R}` bolt binds a PW but loyalty not decremented
    (same damage-to-PW loyalty hole as Magmutt; player seat unaddressable).
11. **liliana_waker_plus_one** — SILENT: +1's "each opponent who can't discard loses 3 life"
    clause never fires (`life[1]: 20`); −3 is green in its own pack.

Suspect-only cards (divergence makes any printed-true assertion impossible): Caged Zombie,
Chandra's Magmutt, Epitaph Golem, Furious Rise, Ghostly Pilferer. Garruk −7 needs no suspect:
activation legal and 0-loyalty self-sacrifice to GY verified (G7b probe); the emblem trigger
is out of wave-4 scope.

## Rig-construction confounds killed this batch (worth re-reading before wave 5)
- The constructor's setup `begin_turn` draws the **last-listed library card** (standing
  r18a pitfall) — it silently ate the search target in the original Fabled FPb probe and the
  Epitaph Chaff target; ALWAYS list a decoy after the subject and pin lanes knowing the pop.
- `deal_damage` op does not settle death/SBAs — kill via `combat` (Caged Zombie, Magmutt).
- Basri Ket / Basri PD / Waker identity loyalty = 4 (stamped); pool has no `{1}`/`{C}`
  activation cards, so payment sinks are Scavenging Ooze `{G}` / Tome `{2}{T}` only.
