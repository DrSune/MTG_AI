# 18 — Wave 1b findings (round 17b validation packs, engine FROZEN)

## batch A — wave1.json rows 1–30 minus done (28 new cards, not 25)

Scope deviation (verified): rows 1–30 hold only **2** of the 5 already-done cards
(Bloodfell Caves row 7, Jungle Hollow row 24; Radiant Fountain=34, Temple of
Epiphany=51, Wall of Runes=63). Batch A therefore = 28 new cards →
**13 pass packs** (`tools/scenarios/`, all green in 34/34 run) +
**18 suspect packs** (`tools/audit/suspects/`, kept OUT of the globbed
scenarios dir; runner has no skip mechanism; each carries `"status":"suspect"`
+ `"finding"` with the exact engine error string).

### Printed-promise passes (13 files / 12 cards)
blossoming_sands, dismal_backwater (checkland: play → +1 life, tapped),
aven_gagglemaster (life 20→24 with Baneslayer Angel = 2 flyers, Scryfall-verified),
llanowar_visionary (enter → draw 1), carrion_grub (mill 4, library/graveyard split),
massacre_wurm (opponent 3/3 → 1/1 via -2/-2; keep dying trigger out of scope),
archfiends_vessel (from hand: 1/1 + LIFELINK, no Demon — Scryfall-verified ETB
only fires from graveyard), idol_of_endurance (GY partition by mana value:
cmc-2 exiled, cmc-6 stays), lilianas_standard_bearer (kill 1/1 first → enter
draws exactly X=1), goremand (ETB forced opp sac, own creature untouched,
FLYING+TRAMPLE statics), faiths_fetters (+4 life THEN SBA 704.5q buries the
unattached aura — assert BOTH), crypt_lurker_sac + crypt_lurker_discard
(may-ask vocab `('fire','skip')`; branch-ask `choose:<handle>:<uuid>` vocab
`('0','1')` = BRANCH INDEX: 0=sac (auto-picks first sorted handle among your
creatures — define the intended victim BEFORE the Lurker or it self-sacs),
1=discard-then-draw).

### Suspects (18 packs / 17 cards; exact engine strings in each file)
- **Trigger-target designation family** — `ValueError: executor:
  TARGET selector has no designation (pass bindings={'target': ...})`:
  daybreak_charger, bone_pit_brute, basris_acolyte, basris_lieutenant,
  barrin_tolarian_archmage, gale_swooper. (`binding.py` only fills
  `bindings["target"] = event.cause` on DAMAGE firings; selectors.py raises
  for trigger TARGETs; `cast(targets=)` is dead for permanents —
  `legality.spell_castable` → `cast:not_a_spell` because records lack
  SpellAbility in the frozen compile.)
- `TARGET_PLAYER needs a bound target (12c target prompt)`:
  kitesail_freebooter, massacre_wurm_dies (dies→"that player loses 2 life"
  never designates the dying creature's controller).
- **C15 may-ask narrowing steals the choice**: alpine_houndmaster (search+move
  commits BEFORE the may-ask; vocab narrowed to `('skip',)`; 'fire'
  unanswerable; 'skip' can't undo the move; mandated shuffle never runs),
  chandras_firemaw / garruks_warsteed (named card IN graveyard yet vocab
  `('skip',)` only — printed "library and/or graveyard" graveyard branch lost).
- **"If you do" guard broken**: crypt_lurker_skip — answering 'skip' STILL
  draws a card (free draw; hand ends 2).
- **12c query-surface raises** (trigger crashes instead of evaluating):
  fierce_empath `filter pred CMC_GE not implemented`;
  chrome_replicator `filter pred NAME_PARTITION_COUNT_GE not implemented`;
  meteorite `Zone(ANY) enumeration is 12c's query surface`;
  kinetic_augur `QProp field THAT_MANY_COUNT not implemented` (both discards
  execute, rebound draw lost; static power uncompiled, effective power None).
- **Silent-false ETB-if**: garruks_uprising — with a 4/4 controlled the
  enters-if-draw evaluates FALSE (no ask, no error) while the sibling
  whenever-enters trigger DOES draw and the trample static grants fine.
- **Harness/compile gap**: capture_sphere — enchant op journals no entry
  MOVE_ZONE so the aura ETB never sees a host; unattached → SBA grave, host
  stays untapped; cast lane dead for permanents (see above).

### Harness facts re-confirmed this batch
- world.begin_turn(p0) runs BEFORE the 6 synthetic "Library n" cards are
  appended → no setup draw; library lane top-first = Library 5..0.
- Provider: a decision word not in the ask's vocab silently falls back to
  vocab[0] (this is why narrowed `('skip',)` swallows a requested 'fire').
- `enter` = MOVE_ZONE journal event (fires ETB); `play` = land drop;
  `enchant` attaches w/o journal; `deal_damage` + SBA settle kills fine.
- `battlefield_keywords` compares SORTED keyword lists; `power`/`toughness`
  lanes need JSON ints (not strings); `graveyard` lane = exact bag;
  `library` lane = exact order with `"*"` wildcard per position.

Verification: `tools/run_scenarios.py` → 34/34 (incl. 21 pre-existing);
suspects dir → 0/18, every failure the documented symptom. Baneslayer Angel
(Flying) and Archfiend's Vessel (1/1 Lifelink, ETB-from-GY-only) confirmed via
`api.scryfall.com/cards/named?exact=…` (the oracle-id endpoint 400s on wave1
IDs — use the named endpoint).

## batch B — wave1.json rows 31–66 minus done (32 new cards, not 36)

Scope deviation (verified): rows 31–66 hold 36 rows but 4 cards were already
done (Radiant Fountain 34, Temple of Epiphany 51, Wall of Runes 63, Pursued
Whale 33 → `whale_pirate_token.json`). Batch B = 32 new cards →
**21 pass packs** (`tools/scenarios/`, Flying Watcher split buff+negative) +
**12 suspect card packs + 1 deviation pack** (`tools/audit/suspects/`).

### Printed-promise passes (21 files / 20 cards)
rousing_read (enter → draw 1), setessan_training, skyscanner (own-enters IS_SOURCE),
storm_caller, trufflesnout (Scryfall oracle: choose-one, ONE +1/+1 counter —
both branches probed), valorous_steed, watcher_flying_buff + watcher_flying_negative,
solemn_simulacrum (exile-replacement on die), stormwing_entity (top-of-library scry
branch), temple_of_malady/mystery/silence/triumph (ETB life/draw/scry/tap-pay),
runed_halo (CHOOSE_NAME 'Cow' recorded in ex.name_choices), and 6 checklands
(rugged_highlands, scoured_barrens, swiftwater_cliffs, tranquil_cove,
thornwood_falls, wind_scarred_crag: play → +1 life, tapped).

### Suspects (13 packs; every FAIL line is the documented symptom)
- **B-1/B-2 crash — Zone(ANY)**: skeleton_archer, terror_of_the_peaks →
  `NotImplementedError: executor: Zone(ANY) enumeration is 12c's query surface`.
- **B-3 turret_ogre — silent-false, never fires**: with two REAL 4-power ogres
  on board the journal holds only TURN_PHASE×2 + ZONE_CHANGE×2, life 20/20.
  COND = `FAnd(TYPE_EQ Creature, POWER_GE QConst(4), CONTROLLER_IS YOU,
  FNot(IS_SOURCE))` is judged against `ctx.source` (the turret itself) →
  `FNot(IS_SOURCE)` is self-contradictory → branch unfireable in ANY world.
  Target mode is FAITHFUL: print says "each opponent" (Scryfall), EFF is
  DEAL_DAMAGE 2 ALL-mode Zone(PLAYER, OPPONENT). Pack asserts life[1]==18.
- **B-4 niambi_esteemed_speaker — both may-branches crash**: answering
  'fire' (or any word) raises `ValueError: executor: TARGET selector has no
  designation (pass bindings={'target': ...})`; even the printed no-op is
  unreachable.
- **B-5 pridemalkin, rambunctious_mutt, roaming_ghostlight, shipwreck_dowser** —
  TARGET-lane ETB raises the same `TARGET selector has no designation`; no
  prompt ever binds the target.
- **B-6 teferis_tutelage**: `ValueError: TARGET_PLAYER needs a bound target
  (12c target prompt)`.
- **B-7 thieves_guild_enforcer**: `NotImplementedError: filter pred
  ZONE_COUNT_GE not implemented (12c query surface)`.
- **B-8 wildwood_scourge**: `NotImplementedError: QX has no declared X
  (cast(x=...) binds it; 12c cost-context flag)` — and it is a creature, so
  the cast(x=) workaround route raises `illegal cast: cast:not_a_spell:card:0`.
- **B-9 teferis_wavecaster — offer gate vs result register**: named-card
  legality works (`enumerate_candidates(NAME_EQ…)` → `[card:1]`), but
  `optional_offer` (executor/query.py:508-527) gates on EVERY exact-count
  selector inside `effect.inner` against the PRE-EXECUTION world: the tail
  `MOVE_ZONE want 1 have 0` (its candidates are produced only later by the
  SEARCH result register — the 13a CARD-level divergence) collapses the ask
  to `('skip',)`, and skip leaves the named card in the library. Printed
  branch unreachable; GY-resident copy identical. Pack asserts zone[tva]==hand.
- **B-10 scry-bottom deviation family (`scry_bottom_temple.json`)**:
  `_v_scry` regroups only inside the viewed window
  (`lib[:len-n] + sorted(bottoms) + sorted(tops)`) → scry-1 "bottom" is an
  exact no-op. Pack asserts the library order changes. Covers the whole
  bottom-scry family incl. Stormwing Entity's bottom branch (its top branch
  is green in `stormwing_entity.json`).

### New harness/engine facts (batch B)
- Constructor `begin_turn(p0)` runs BEFORE the 6 synthetic "Library n" cards
  are appended; if the pack library is non-empty it draws ONE card, popping
  the LAST-listed card (cards order [Plains, Voyager] → Voyager survives).
- `optional_offer` static gate never accounts for atoms whose candidates are
  produced mid-effect → any search-then-move may-branch can never be offered.
- `enchant` op does not drain the ETB queue; follow with `end_turn` (which
  does NOT draw; `advance_turn` would draw Library 5).

Verification: `tools/run_scenarios.py --dir /tmp/green-copy` 21/21; my 13
suspects 0/13 with the exact strings above; full scenarios dir **55/55**
(21 pre-existing + 13 batch A + 21 batch B); `pytest MTG_bot/core -q`
**2081 passed**; PC-1 0.9869 (301/305), PC-2 0.9922 (634/639), PC-3 0, PC-4
0 diffs (305 files) — all baseline; PC-6/PC-8 FAILs pre-date this round.

---
## STATUS flip — round 18a (2026-10-01, doc 19): 8 packs repatriated green

First engine move since 16e. Fixed + moved to `tools/scenarios/` (now
63/63): **crypt_lurker_skip** (if-do Conditional(MAY_DONE), CR 611.1),
**alpine_houndmaster** (rebuilt — the constructor `begin_turn` draw had
eaten the pack premise; now answers the previously-STOLEN `'fire'` with an
exact post-shuffle lane pin), **chandras_firemaw**, **garruks_warsteed**,
**garruks_uprising** (template threshold/count conflation, not a silent
pred path — eval was faithful to a wrong compile), **scry_bottom_temple**
(CR 701.1 whole-library regroup), **turret_ogre** (CR 603.4 set-level
"another" via CONTROLLER_COUNT_GE count 1), **teferis_wavecaster** (B-9
offer collapse was the optional_offer pre-gating of the search-fed
referent tail, not a cast-site gap — 'fire' now resolves through the 14e
result register). Suspects remaining: **23**, all fail-only with their
documented loud strings (Zone(ANY), TARGET-designation family,
ZONE_COUNT_GE, QX…). Deviation recorded in doc 19: golden movers were 9
lines, not just turret — the if-do gate has no IR to consume without the
compiler merge; audit set-equal before regeneration.
