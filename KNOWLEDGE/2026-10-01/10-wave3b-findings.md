# 10 — Wave 3b findings (static/keyword cohort, batch B: Malefic Scythe → Wildwood Patrol)

27 cards, one scenario pack each, printed-text-as-truth law, engine FROZEN. Outcome:
**22 green** (`tools/scenarios/`), **5 card-level + 4 systemic suspects** (9 new files in
`tools/audit/suspects/`, `status`+`finding` schema). Gates after landing: runner
**186/186** (164 baseline + 22), suite **2168 + 4 subtests** unchanged (`pytest MTG_bot/core -q`).

## Rig laws learned (binding for future pack authors)
1. **Damage lane is global** (`run_scenarios.py` check, always asserted): the declared ledger
   defaults to `{}`; ANY surviving marked creature must be declared — mangara_the_diplomat
   ships only after adding `"damage": {"biter": 4}`. Marks on creatures that DIE are dropped —
   never declare them (snarespinner expects `{"s": 1}`, not the dead Imp).
2. **A pack's real card must survive the final check**: the `battlefield_keywords` /
   `battlefield_pt` lanes resolve BY NAME and FAIL with "expected 1 on battlefield, got 0"
   if the star died in its own combat scene (wildwood_patrol 4/2 trading into a 2/2 — resized
   the wall to 1/3 instead of touching the lane).
3. **Payment spends colored mana first**: Revitalize {1}{W} drained C:2·W:2 down to {C:2} in
   one cast (legal but surprising — give the pool slack; no promise is weakened by extra mana).
4. **block_asks lane wants `"<key>,NONE"` angle-bracket form** — the vocab string is
   comma-JOINED handles after `<key>` substitution; bare handle strings don't map.
5. **`enter` + `"decisions": ["<key>"]` fires ETB TARGET triggers** (sigiled_contender rides
   Pridemalkin's ETB to plant the +1/+1 counter that flips the conditional lifelink static).

## Suspect root causes (grep-verified, engine frozen)
| Gap | Loud/Silent | Evidence | Suspects |
|---|---|---|---|
| **Trigger TARGET designation = 12c** — binder `_check_event` raises TargetingEvent triggers | LOUD | `Warden of the Woods trigger event TargetingEvent is 12c` | warden_of_the_woods |
| **`LIFE_LEAD_OVER_START_GE` pred unimplemented** (12c query surface) + local printed_text row CORRUPT | LOUD | activation probe raise | speaker_of_the_heavens |
| **StaticAbility `GAIN_LIFE` not layer-parseable (12e)** — card unREGISTRABLE; crashes `attach_pool`, aborts whole directory | LOUD | `StaticAbility payload verb GAIN_LIFE is not layer-parseable (12e)` | rin_and_seri_inseparable (never lands in tools/scenarios — even as a probe) |
| **Activation legality hard-requires battlefield source** — printed hand-activation (discard-cost) windows don't exist | LOUD | `window:not_on_battlefield` on `{1}{U}, Discard this card:` | waker_of_waves_activation (−1/−0 static ships green) |
| **163/165 creature goldens have NO SpellAbility node** → `cast:not_a_spell` (legality.py:1036-1043); only Goremand + Sparkhunter Masticore castable | SILENT (systematic) | every creature pack stages via `enter`; FLASH timing untestable | creature_spell_nodes_systematic (masked_blackguard pump ships green) |
| **PREVENT_EFFECT vs CombatDamageEvent has NO damage-application consumer** (only untap/block/attack-declaration consumers, replacements.py:423/512/528) | SILENT | protected Pack Leader takes 2 and dies | pack_leader_prevention (anthem + unblocked lanes ship green; Nine Lives green via separate ReplacementAbility path) |
| **Attachment table detached on the ZONE_CHANGE row BEFORE the CREATURE_DIES row** — `IS_ATTACHED_TO_SOURCE` reads the live `ex.attachments` (quantity.py:574-586, no was-snapshot) → dies-triggers of equipment/auras never fire | SILENT | table `{}` at the dies row, filter False, counter stuck at 1 | malefic_scythe (only golden with this shape, grep-verified) |
| **PROWESS dead keyword** (wave3a family, 3rd instance) | SILENT | Singer stays 2/2 after Opt cast | mistral_singer_prowess (flying + Opt lanes ship green) |
| **CONTROLLER_COUNT_GE count=4 vs printed threshold "power 4"** — compile-side count/power conflation, gate silently fails with one 5/5 ally | SILENT | 2/2 deals 2 (expected 4/4 deals 4) | ornery_dilophosaur |

## Positive confirmations (lanes proven live)
- Conditional statics flipping on COUNTERS (Sigiled Contender LIFELINK appearing exactly with
  the Pridemalkin counter; Pridemalkin's trample-granting static stacks correctly).
- **Vryn Wingmare CostModifier IS enforced** (CR 601.2f fold, legality.py:542-583): base-cost
  mana is REJECTED `cost:mana_generic:0<1` for noncreature spells (ad-hoc probe; the shipped
  pack pays the surcharge).
- Tome Anima "drawn two or more" → blocker never asked (`not_asked_to_block` lane).
- Shacklegeist block-vocab narrowing to `"<i>,NONE"` (flying-only) + `{T}` Spirit-tap cost.
- Vodalian mana restriction path: tap-activation + instant cast resolve in-sequence.
- Mangara both draw triggers; Pack Leader anthem on real AND synthetic `Creature — Dog`
  (em-dash subtype parse works; PL itself is a Dog and protected); Wildwood Patrol trample
  ask fires only for keyword holders (engine gate at `__init__.py:1669`).
- Setup law re-probed: `begin_turn(p0)` in `__init__` does NOT draw (empty library) — Opt
  packs expect `Library 4..0` + hand 1 (singer/vodalian/vryn).

## Notes on adjudication discipline
- probe_hand_base / probe_warden_enter / probe_speaker_gate stayed in `/tmp/opencode/b3b/`
  as evidence vehicles (they FAIL by design — never shipped).
- rin_and_seri's pack ABORTS the whole runner directory (init raise) → evidence lives only
  in the suspect file; same rule as wave2's wildwood_scourge.
