# Round 16e — GAIN_CONTROL overlay + ATTACH (equip/aura lifecycle) + 16 close-out

Date: 2026-09-30 · base HEAD 0e03a99 (16c) · scope per /11 §16e. FINAL build
phase of round 16 — the flagged-verb tail of the arc-3 wall.

## What landed
- **GAIN_CONTROL (executor-side; state.py FROZEN, R16-4)**: the control
  overlay lives in the executor, never the world. `control_entries` (append-
  only, seq-ordered) is the SOURCE OF TRUTH; `control_overlay` is a
  last-entry-wins projection rebuilt from it. `executor.controller_of` is
  the EFFECTIVE read every controller-semantic site consumes; OWNER-semantic
  reads (graveyard destination, owner-of-source, library to search) keep the
  raw `world.controller_of` — a stolen permanent still dies to its owner's
  graveyard (CR 400.7e, pinned). Sickness on takeover: `control_gained_turn`
  clock (a stolen creature is summoning-sick unless it has haste, CR 305.4).
  Tags: `Eot` rows sweep at end_turn; `Permanent`/`Anchor` rows ride until
  the anchor (or the creature) leaves the battlefield — Enthralling Hold's
  missing Duration node reads as CR 611.3 "duration ends when the aura
  leaves", handled by ONE `_expire_control(creature=…, anchor=…)` fan-out in
  `_on_zone_changes`.
- **ATTACH**: `executor.attach_aura(aura, host)` is the canonical write —
  validates both ends are world cards, forbids self-attach, sets the one
  `attachments` table, recomputes layers ("equipped creature" scopes re-read
  the table). Malefic Scythe / Short Sword equip and Enthralling Hold aura
  CAST now resolve through the real stack pipeline (enchant target picked,
  aura edge written at resolution).
- **CR 704.5q SBA**: `_state_checks` now sweeps UNATTACHED AURAS to the
  graveyard alongside lethals, per settle round. Aura marker = `"ENCHANT"`
  in the printed identity keywords — equipment carry EQUIP and are NOT
  swept (an unattached Equipment legally stays on the battlefield, CR 301.5).
  Journalled as its own STATE_CHECK atom (`… UNATTACHED` row) so replays and
  the trace-diff catalog see the sweep.
- **Enchant targeting**: the compiled Enchant keyword carries `params=[]`,
  so the enchantable POPULATION is derived from the effect tree — the
  `_strip_attached` envelope (Enthralling Hold → TYPE_EQ Creature) — and a
  TARGET slot is synthesized (QConst(1), min=max=1). Cast legality + the
  C15 ask vocab read the same derivation.
- **`binding.detach(handle, *, leaving=True)` (bug the games forced)**: a
  permanent's `_register` refresh runs `detach` before re-binding. With the
  old unconditional behaviour it ALSO dropped the attachment edge the cast
  had just written (aura-less StaticAbility carriers refresh AFTER
  attachment), feeding the new SBA a false unattached read — the resolved
  aura self-swept on the spot. The attachment drop is now DEPARTURES ONLY
  (`leaving=False` for the ARRIVING rebind path; `_lifecycle` departure
  keeps True). Pinned in `Round16eControlTest`.
- **Scenario-pack `enchant` op rebuilt (close-out)**: a pack that DECLARES an
  aura on the battlefield now meets the setup sweep honestly — begin_turn's
  settle graves the unattached aura and TERMINALLY expires its static layer,
  so the old raw-dict write attached a graveyard ghost. The op restores the
  aura through `world.move_to_zone`, JOURNALS the move (`record_atom`) so
  the binder lifecycle re-registers, then attaches via `attach_aura`.
  16/16 packs green again (`combat_mandate_furor` was the casualty).

## Layer-lifecycle law discovered at close-out (verify before re-designing)
- `layers.recompute()` SKIPS `status == "expired"` records entirely — a
  terminally-expired static NEVER revives from a recompute. Revival happens
  ONLY via `attach_source` minting FRESH records, which needs a journalled
  ZONE_CHANGE with `to_state == BATTLEFIELD` (`binder._lifecycle(attach=
  True)` inside `on_events`).
- `attach_pool` populates `handle_record` for every oracle hit REGARDLESS of
  zone, so a graveyard'd aura keeps its compiled bridge and its re-entry
  re-registration is automatic. A raw dict write can never substitute for
  the journalled path.

## Verification (final code)
| gate | result |
|---|---|
| core suite | **2079 passed + 4 subtests** (was 2076; +3 `Round16eControlTest` in test_executor_games.py) |
| validation packs | **16/16** (enchant-op rebuild above) |
| engine 30 (seeds 0-29, cap 60) | survived **26/30 (86.7%)**, crash classes **0**; the 4 non-survivors are REAL game-overs (combat life-zero / draw loss), counted apart — survival % moves with combat lethality, NOT with crashes |
| all-305 ×10 | crash classes **0**, survived **9/10 (90.0%)** — the ALL10 GAIN_CONTROL baseline crash (Enthralling Hold) is GONE |
| engine gate | **297/305** dispatch-ready (V2 = **45** verbs); flip probe: +{GAIN_CONTROL, ATTACH} gains EXACTLY {Malefic Scythe, Enthralling Hold, Traitorous Greed, Short Sword}, zero losses |
| PC | PC-1 **301/305** · PC-2 **634/639 (0.9922)** · PC-3 **0** · PC-4 **0 diffs** · PC-5 **0.242 ms** p99 · PC-9 stable · PC-10 exact — all hold; PC-6 (orphan 1 / 0.0934) & PC-8 (0.3213) unchanged pre-existing FAILs |
| catalog | repinned **6138 entries / 10 games**, post-repin compare **0 of 10 diverge** |
| determinism | replay seed 2 ×2 HTML **byte-identical** (825 entries, 120 actions) |
| showcase | `reports/replays/` seed 37: Enthralling Hold cast → takes Sparkhunter Masticore → host DIES → aura UNATTACHED SBA sweep (journal events 198/286/287) — the full 16e lifecycle visible in one replay (s7/s9 candidates discarded: carriers never drawn to cast) |
| pyright / ruff | 0 errors on the executor package + both touched test files; ruff **Δ0** vs HEAD (the 6 legacy errors in touched files — N999 + TRY004×3 + TRY004 legality + UP007 quantity — are all pre-existing; an earlier note miscounted "5") |

## Known gaps (documented, not patched)
- Control-overlay reads are EXECUTOR-side only; a replay of a PRE-16e
  catalog pin legitimately diverges (repinned this round).
- `V2 == 45` is the frozen capability pin (`test_executor_library.py:719`);
  the remaining 8 flagged-verb cards = PHASE_OUT/COPY/EXTRA_TURN family —
  arc-4 candidates by design (/11).
- The viewer never rendered raw journal ATTACH/STATE_CHECK tokens (pre-16e
  design: action snapshots carry the story) — the showcase replay proves the
  lifecycle through action rows, not raw-token rendering.
