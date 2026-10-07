# 32 — Event-side {when} algebra (analyst 2026-10-07; extends /30 to triggers)

17 event kinds in EventSpec decompose as {event-kind, subject filter, quantity, direction}.
CORRECTION to AGENTS §9 addendum: Filter.owner_color DOES NOT EXIST (grep 0). Real split:
ControllerRef FIELDS on 7 events (Cast/CardDrawn/LifeGained/Sacrifice/Loyalty/TurnPhase/Step)
vs CONTROLLER_IS predicate in subject filters on the other 10. "Enemy creature attacks" uses
the filter; "an opponent casts" uses the field — one concept, two encodings -> E1 MERGE.
Trigger guard = orthogonal & generic (TriggeredAbility.condition evaluated on event subject,
binding.py) — the MTG if-statement shape the owner described, CLEAN. But subject-narrowing is
triply-encoded (filter slots / condition / ad-hoc per-kind fields from_zone_not, combat,
attacked, ordinal...). StepEvent NEVER emitted (dead atom). LifeGained has NO amount slot
("whenever you gain 3+ life" unexpressible). LoyaltyActivated over-constrained (bare-any
unexpressible). Volumes: ZoneChange 70 HIGH; TurnPhase 20/Attackers 13/Dies 11/Damage 8/Cast
8/Drawn 7 MID; floor<=2: CombatDamage 2, Blockers 2, LifeGained 2, Targeting 1, BecomesBlocked
1, Sacrifice 1, Loyalty 1; Step 0. Guards fire on 24% of 152 triggers.
LEDGER: E1 direction unification MERGE (top-1 generalization); E2 promote ordinal/amount/
counterparty/source to shared axes MERGE (top-2); E3 CombatDamage->DamageDealt{combat} MERGE;
E4 BecomesBlocked->DeclareBlockers{IS_SOURCE} MERGE; E5 Dies vs ZoneChange KEEP (last-known
PT payload); E6 PlayLandEvent SPLIT/ADD (landfall = zone-move cause-verb today; high in later
sets); E7 StepEvent keep-dead; E8 **HEXPROOF: 6 goldens carry the keyword, ZERO executor
enforcement — latent engine bug, file to fix queue**. Keywords overall: 15/23 have >=2
consumer functions (owner premise holds); TREASURE also zero-consumer.
