# 18 — Wave-4 fix-a (r21a): planeswalker damage, prevention-condition sides, zero-loyalty SBA

Batch: fix-batch **21a** of the wave-4 suspect backlog (engine editing
authorized). HEAD at start: `4545d58`. Five suspects in scope; batch 21b's
`basri_ket_minus_two.json` untouched. Card truth from the local M21 dump
(+ live Scryfall for wording), never memory.

## Verdicts (5 suspects)

| Suspect | Verdict | Root cause / disposition |
|---|---|---|
| Ghostly Pilferer (can't be blocked) | **FIXED → promoted** | `_pair_vetoed` judged `rec.condition` on the BLOCKER (block consult passes subject=blocker); GP's IS_SOURCE names the BLOCKED side → condition never matched → veto dead. Block consult now judges the condition over BOTH pair sides; attack consult stays attacker-side. |
| Chandra's Magmutt {T} → player-or-PW | **FIXED → promoted** | two gaps: (a) `role_handles`' blanket PLAYER-zone self-resolve exemption silently re-pointed the designated walker's handle at the player (damage hit player:1); exemption narrowed to PURE player selectors (`not value.zones`). (b) no planeswalker damage lane existed at all. |
| Leafkin Avenger {7}{R} bolt | **FIXED → promoted, expectation corrected** | same (a)+(b); plus the author's `{LOYALTY: 3}` was a printed-math misprint: Leafkin is 4 power, Basri, Devoted Paladin is printed loyalty 4 → walker DIES (CR 704.5h). Pack now asserts `zone{pw: graveyard} + counters{pw: {}}`. |
| Basri Ket +1 (indestructible) | **FIXED → promoted, expectation corrected** | nothing was compiled away: the harness `battlefield_keywords` vocab simply omitted `Keyword.INDESTRUCTIBLE` (report-only list) — engine `layers.keyword_of` said True all along. And `{LOYALTY: 5}` was a misprint (Basri Ket printed loyalty **3**, dump-confirmed → +1 = 4). |
| Liliana, Waker +1 (can't-discard life loss) | **STOP (compiler gap, IR/goldens FROZEN)** | golden `e0df8e2a…json` ability[0] (+1) compiles to a SINGLE DISCARD atom (CHOOSE 1, any HAND) — the "Each opponent who can't loses 3 life" sentence has NO step anywhere in the IR. Engine never receives the clause. Root cause written into the suspect file. Precedent: peer_into_the_abyss (17-wave4b findings / 07). |

## Engine changes (5 files, uncommitted)

1. `replacements.py::_pair_vetoed` — condition evaluation moved INSIDE the
   event branches: DeclareBlockers consult = `cond(blocker) OR cond(blocked)`;
   DeclareAttackers consult = `cond(attacker)`. Corpus-inventory justification
   in the docstring: all 12 PREVENT atoms carry either a subject-independent
   static state gate (Tome Anima `CARDS_DRAWN_THIS_TURN_GE`; static
   materialization registers `static.condition`, and Faith's Fetters /
   Shacklegeist register None — their restriction lives in the event slots),
   designation-bound (`IS_ANY_TARGET`, Subira), or GP's `IS_SOURCE` naming the
   blocked side. No corpus carrier has a blocker-side condition → both-sides
   is zero-risk today and correct for a future "can't block" activation.
2. `verbs.py::_deal_damage_to_card` — CR 120.4d planeswalker lane:
   `identity.loyalty is not None` → decrement LOYALTY counter (missing key
   falls back to PRINTED loyalty — missing is not zero), journal DAMAGE row,
   lifelink rides the dealt amount, return BEFORE mark_damage/deathtouch.
3. `executor/__init__.py` — new `_zero_loyalty_walkers()` in `_state_checks`
   (CR 704.5h): battlefield walkers with `_loyalty_of <= 0` are buried and the
   **LOYALTY counter KEY is popped** — binding.py:431 re-seeds via `setdefault`
   on battlefield re-entry, so a stale 0 would otherwise ride re-entry into an
   instant second death; `_loyalty_of`'s printed fallback makes the popped key
   re-enter at the printed value. STATE_CHECK journal row `ZERO_LOYALTY`.
4. `selectors.py::role_handles` — `player_side` exemption now requires
   `and not value.zones`. Corpus scan: ONLY Magmutt + Leafkin carry a
   PLAYER-zone selector with `zones=`; pure TARGET_PLAYER selectors stay
   byte-identical.
5. `legality.py::_loyalty_death_check` — stale docstring corrected (the check
   now exists in two places; legality's stays for the activation-cost path).

Harness (`tools/run_scenarios.py`): `battlefield_keywords` vocab +=
`Keyword.INDESTRUCTIBLE` (report-only; no green pack regressed).

## Tests

New `MTG_bot/core/test_executor_r21a.py` — 9 tests: blocked-side condition
(GP shape) vetoes / blocker-side condition vetoes (both-sides, with the
blocker-side slot filter carrying directionality), attack consult stays
attacker-side; PW damage decrements not marks, printed fallback, zero-loyalty
burial + key-drop, re-entry re-arms from printed; bound walker survives the
player-or-PW selector, pure player selector still self-resolves.

## Gates (all green, 2026-10-01)

| Gate | Result |
|---|---|
| scenarios | **243/243** (239 + 4 promotions; MOVE+STRIP law) |
| pytest `MTG_bot/core -q` | **2222 passed + 3 subtests, 0 failed** (2213 + 9) |
| measure_grammar `--with-engine-flags` | PC-1 **301/305**, PC-2 **634/639**, PC-3 **0**, PC-4 **0** — unchanged |
| traces catalog | seeds 3+7 legitimately diverged (new STATE_CHECK walker-death rows; outcome class unchanged) → **repin**; compare **0/10 diverging** |
| games smoke | `catalog.py build --seeds 100 --pool all` → **100 games, 0 crash classes** |
| pyright / ruff | 0 errors on all touched engine files + new test file; ruff Δ0 vs HEAD (test-file I001/F401 fixed) |

Note: a full `--dir tools/audit/suspects` run crashes on the pre-existing
GAIN_LIFE static issue in the rin_and_seri pool (verified pre-existing at
HEAD via stash); evaluate suspects per-pack/isolated-dir. Suspects now
**17 files** (21 − 4 promoted; liliana stays with root cause).
