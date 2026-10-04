# 2026-10-02 — grammar batch B6: OPPONENT_OF destination predicate + CREATE_TOKEN controller role (both ruled suspects closed)

HEAD 85f1aaf baseline. Mission: land the two owner-ruled additive slots of
`10-grammar-round-ruling.md` (/10) — (1) the damage DESTINATION predicate
`FAtomPred.OPPONENT_OF` ("to an opponent", Chandra's Pyreling + Chandra's
Incinerator), (2) the optional CREATE_TOKEN `controller` role ("Its
controller creates …", Secure the Scene + Angelic Ascension). Both landed;
both suspects promoted; suspect folder now empty. No commits (owner law).

## 1. Verdicts

**Slot 1 — OPPONENT_OF is a DESTINATION predicate, not a controller test.**
The trap: `CONTROLLER_IS` over a CARD subject reads the card's controller,
so "damage to an opponent" would ALSO fire on damage to an opponent's
creature — ruling-forbidden. `OPPONENT_OF(who)` is therefore player-total
(CR 109.5): a CARD subject is never an opponent (atom False); a PLAYER
subject is true iff not on `who`'s side. `who` validates as ControllerRef
OR referent Selector (twin convention); a non-ControllerRef value hits the
generic who-type gate ("FAtom: who must be a ControllerRef, got int")
BEFORE the R11-1 lane gate. Template effect: Pyreling/Incinerator trigger
`filter` moves from empty `FAnd(children=[])` to
`FAtom(pred=OPPONENT_OF, who=YOU)` — the trigger now refuses self-damage
(Incinerator's own landfall loop dies) and refuses opponent-creature
damage. Discriminator pins: card-subject no-fire (life stays 20/21),
player-subject fire, self-damage expects life 18 (2 dealt, no trigger).

**Slot 2 — CREATE_TOKEN `controller` role is one referent-selector, zero
new cast slots.** Idiom (consumed via `role_players`):
`Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), Zone(ZoneKind.ANY,
ControllerRef.ANY), referent="target")`. The referent-CHOOSE selector adds
no cast slot (dual-slot law, /05 §45 + PITFALLS :795) — PC-2/decision
vocabulary untouched, catalog 0/10. Failure lanes pinned: unbound referent
raises `executor: 'target' referent has no target binding` upstream; a
multi-player resolution (ControllerRef.ANY bound to 2) hits the verb's own
`need exactly 1` ValueError. No-role regression pin: tokens still mint to
the ability controller.

**C1-form golden evidence (additive law, R3).** Recompiled the pool post-edit
(`write_goldens(pool, reg, "M21", root=…)` — note the root double-nesting:
files land in `root/M21/M21`) and diffed vs the pre-edit snapshot:
**exactly 4 of 305 files differ** — 5291deb9 (Pyreling), 515cee6a
(Incinerator), 5a898412 (Angelic Ascension), d6a9746c (Secure the Scene).
For all four ONLY the top-level `abilities` key changed; Pyreling/Incinerator
= the filter swap above; STS/AA = purely additive
`("controller", referent-target Selector)` pair inserted before `tokens` in
CREATE_TOKEN roles. Zero deletions elsewhere, zero untouched-card churn.
PC-4 then measured 0 (305 refresh → 305 verify).

**FAIL-at-HEAD proof (path-scoped stash/pop of the 6 source files):**
at HEAD the promoted packs fail with exactly their owner-ruled signatures —
`chandras_pyreling_opponent_filter`: `battlefield_pt[Chandra's Pyreling]:
expected [1, 3], got [2, 3]`; `secure_the_scene`: `life[0]: expected 19,
got 20`. Post-edit both green.

**Promotion law corrected mid-batch:** strip ONLY `finding`/`status`. The
top-level `mana` key is FUNCTIONAL per-seat input (`run_scenarios.py:209`
reads `pack.get("mana")`; 133/304 green packs keep it). Stripping it broke
secure_the_scene until restored from `git show HEAD:…`. The old
"MOVE+strip" shorthand was wrong for `mana`.

## 2. Gates (all green; NUMBERS.md 2026-10-04 B6 section has the rows)

304/304 packs · suspects 2→0 (folder empty) · suite 2345+3 subtests 0 fail
(+23 pins: r12 ×12 grammar-side, r25 ×11 executor-side, + amended b2b/b5b
template assertions) · grammar PC-1 303/305 PC-2 637/639 PC-3 0 PC-4 0
engine 297/305 (45 verbs) PC-5 0.293 ms — ALL Δ0 vs 24a, PC-6/PC-8 standing
FAILs byte-identical · catalog 0/10 NO repin · games 0 crash classes, 100
decisive 47/53, mean_turns 33.48 (one outcome flipped — expected: the dead
Incinerator self-loop) · ruff Δ0 (in-repo stash baseline: identical 65-finding
multiset on the 8 tracked files; 2 new files 0 findings) · pyright 0 errors
0 warnings on all 10 touched files.

## 3. Gotchas learned

- A PLAYER-zone TARGET selector REFUSES a card binding and re-resolves to
  `player:1` — damage-to-card test wiring must bind through a
  `Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)` selector.
- Negative-type pins (`FAtom(who=5)`, bad role values) need
  `# type: ignore[arg-type]` or pyright counts them; `TokenSpec` requires
  `abilities=()`.
- Ruff/pyright config discovery: this repo has NO ruff config and no
  [tool.ruff]/pyright section — defaults everywhere, but the reliable Δ0
  baseline is still path-scoped `git stash push -- <files>` (identical
  in-repo path context), not /tmp copies.
- `measure_grammar.py --refresh-goldens` appends its own NUMBERS section per
  run; a refresh+verify pair yields two same-titled 2026-10-04 T5 sections —
  append-only law: keep both.
- Concurrent session: `12-bugcatch-design.md` in this folder was written by a
  PARALLEL session mid-batch; it is not part of B6 — do not attribute or touch.
