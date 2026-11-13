# 206 — The engine wave on triggers and events: one event at a time

**Context.** Building ontology round 10 (gathered zone-change events, 204 §5) turned up five
faults in how the trigger binder sees events. They were logged in BACKLOG ("Triggers, events and
the journal") and fixed here, with no IR change (merged 6bd77ef4, 2026-11-13 10:28).

## 1. The faults and the fixes

| Fault | Cause | Fix | CR |
|---|---|---|---|
| Permanents moving in one atom saw each other's moves only in journal row order. Two "whenever another creature you control dies, gain 1 life" creatures killed by one wrath gained 1 where the rules give 2, and a holder leaving with three creatures saw none | `TriggerBinder.on_events` matched one row at a time and attached or detached each mover at its own row | Each event (a batch) is matched in three steps: look-back triggers against what was there before; then the moves; then the rest, newcomers included. Departed objects read their granted abilities, keywords and types from last-known information | 603.6a, 603.10a |
| Three dies triggers were filed as graveyard-only (Immortal Phoenix, Cavalier of Gales, Cavalier of Thorns), and "another" counted the card itself | `functions_from_graveyard` | Read correctly; those three now bind on the battlefield | 113.6m |
| A per-object trigger's "it" followed an object that had changed zones (Marauding Raptor's damage hit a flickered creature) | The row's handle was bound as "it", and handles survive zone moves | One CR 400.7 check (`_gone`) for both the per-object and the gathered lanes; departed objects are read by last-known information (Terror of the Peaks' "that creature's power") | 400.7, 608.2h |
| One EachPlayer instruction ("each player sacrifices a creature") was one event per player | Each player's sub-execution was its own atom boundary | The boundaries at one depth share one batch. "Until" returns ended inside it run after it (610.3) | 101.4 |
| Event filters read layers as the last recompute left them (a creature made a flyer by the same event could be missed) | Only `_queue`'s intervening "if" recomputed | A lazy recompute before the first read that needs it, in the step for triggers that do not look back | 603.10 |
| A replaced death was its own event (Scorching Dragonfire's exile in a state-based check) | Each replacement action ran as its own boundary | Both drains run inside one event | 614.6, 704.3 |

## 2. Evidence

- **Tests:** 36 in `MTG_bot/core/test_executor_one_event.py`, failing on the base except the
  labelled controls. 27 of 27 engine mutants are killed.
- **Trees:** 0 changed over the 19 sets, and 0 verified cards in or out.
- **Seeded games:** 600 heuristic games on the verified pools.
  - 597 have identical replay digests, and 0 crashed on either side.
  - The 3 that differ are rules corrections, each with the same winner:
    - FDN Spinner of Souls now looks back at both creatures dying beside it;
    - a bounced Concordia Pegasus no longer keeps the trigger Light of Promise granted it;
    - M21 Watcher of the Spheres now sees a token enter in the same event as its keyword map's
      update.
- **Engine time:** −1 to −3% against the base. The first build cost +15-23%, which a lazy
  recompute removed.
- **Review:** one fresh-eyes reviewer found no FATAL or MAJOR. Its 2 MINOR and 5 NIT findings are
  fixed or recorded.
- **Files:** `reports/one_event_2026-11-13/`.

## 3. What changes for training

- Verified play changes only where the rules say it should. 3 of 600 games differ, and none
  changes the winner.
- r28 (pinned 44a62d9) is unaffected.
- A run started from main after this deals games with these corrections.
