# 2026-09-28 · 04 — Owner decisions: standing autonomy + atomic-decomposition reaffirmed

1. **AUTONOMY (binding for future sessions).** Owner instruction 2026-09-28: "Work independently,
   if you can take informed choices for me, prefer that over spending human time resources."
   Supersedes the per-round owner-approval pattern (2026-09-24/04 "commit approved" was a
   point-approval, not a gate). New default: orchestrator makes informed decisions (lossy accepts,
   deferrals, module assignments, commits, round sequencing), records them as dated decision notes
   with justification, and proceeds. Escalate to owner ONLY for policy forks the knowledge tree
   cannot ground: PC-target renegotiation, sentence-split/denominator changes, engine/tool
   container operations, deletion of committed knowledge, or any change to the atomization
   mandate. Commits at round boundaries are pre-approved going forward.
   Round-6 commit 0726e93 was made under point-approval; round 7+ commits land autonomously.
   Round-7 batch scope + split decision (2-phase batch, see 03 doc §dispatch note) taken under
   this new standing autonomy.

2. **ATOMIZATION MANDATE REAFFIRMED (owner check).** Owner asked (2026-09-28 13:06) whether
   compiled abilities stay atomically/sub-component decomposed for granular/generalized learning.
   Verified against committed goldens at 0726e93: Faith's Fetters = Seq of two PREVENT_EFFECT
   Atoms over DeclareAttackersEvent/DeclareBlockersEvent with IS_ATTACHED_TO_SOURCE; Tome Anima =
   StaticAbility(condition=FAtom(CARDS_DRAWN_THIS_TURN_GE, QConst(2), YOU), Atom(PREVENT_EFFECT,
   DeclareBlockersEvent(blocked=FAtom(IS_SOURCE)))). Zero English payload in IR; the only legal
   strings are card names (NAME_EQ/NAME_CONTAINS — names ARE strings in MTG). English exists only
   in template match patterns (input side) and UNCOVERED/queue registers (work lists).
   Rule restated: any proposed IR node that stores prose/text blobs instead of typed verbs/
   events/filters/quantities is REJECTED by mandate (ARCHITECTURE.md, ETB-substring lesson).
