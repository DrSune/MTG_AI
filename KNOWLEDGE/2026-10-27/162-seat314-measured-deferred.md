# 162 — §3.1.4 active-player fallback: MEASURED on the pilot path (10/123 block asks misrouted); fix deferred post-harvest by the night-3 invariant

Date: 2026-10-27 ~14:30 CEST. Day-queue item 2 (/154). Method: throwaway
in-process spy on `tools.eval.gameplay_eval_v2.resolve_seat` (seed block
610301-610340, M21 engine pool, anchor bsh_S3a_s1_best vs teacher, 40 games,
swap alternated, no rl sampling — routing is what is under test). The spy
compared the rig's tag-parsed seat against the engine's authoritative
`DecisionStream.asking_seat` (decisions.py:104 — set for the duration of the
provider call = `ExecCtx.controller`, live in the rig process: B-35
monkey-patch modules are NOT imported by the eval path, probe-verified).

## Finding (evidence)
- 2181 provider asks across 16 site kinds, 0 crashes. Divergences: **10, all
  `block:` sites** (10/123 block asks = 8.1%): rig_seat == active player,
  engine_seat == 1 - active (the defender) in every case.
- Every other site kind: 0 divergences (choose 912, may 143, one_of 23,
  scry 63, attack 588, mana 89, target 14, discard 43, order 9, name 2,
  sacrifice 3, cw 1, counter 5, pay 2, trample 1).
- Engine ground truth: `_declare_blockers` (executor/__init__.py, 16c) asks
  `ctx = self._ctx(source=blocker, controller=defender, ...)` per blocker —
  the ENGINE asks the defender, rule-correct (CR 509).
- MECHANISM (confirmed by deep probe on the first divergent ask, game seed
  610309, `block:card:124:22`): the blocker is a **"Bird" token**
  (`CardIdentity.is_token = true`), whose handle is ABSENT from
  `handle_words` — the rig's game-start snapshot (gameplay_eval_v2.py:531,
  built before play; tokens are minted mid-game). `resolve_seat`'s tag
  loop therefore finds NO token, skips the correct
  `controller_of(blocker)` routing, and falls through to `default_seat` =
  active player. At ask time the live world was unambiguous:
  `controller_of(card:124) = player:0 = defending_player =
  asking_seat`, yet the rig routed to seat 1 (active). The defender's
  blocking decision was answered by the ATTACKER's policy — the v1
  seat-attribution bug class, surviving in v2 in exactly this corner.
- Why only `block:` sites diverged in-sample: token ATTACK asks fall back
  to active = attacker — accidentally the right seat (588 attack asks, 0
  divergences); token BLOCK asks fall back to active = attacker — wrong
  seat. Any future ask kind whose correct decider is the non-active player
  and whose tag embeds a token carries the same latent bug; the
  `asking_seat` fix covers all kinds uniformly.

## Consequence for tonight (the binding decision)
The fix changes collect behavior on the pilot path (≈8% of block asks would
re-route ⇒ different plays ⇒ different episodes). Night-3's /158
pre-registration pins byte-identical episodes vs nights 1-2 (frozen rig,
frozen anchor, seed 510201). **Implementation is therefore deferred until
after tonight's harvest** — the window (armed 23:59, pin 07fd1a6e) runs the
UNCHANGED rig, exactly as pre-registered. Nothing in the fingerprinted tree
was touched by this measurement (spy lived in /tmp only).

## Post-harvest plan (pre-registered)
**Era-boundary bundle (decide as ONE transition, not two)**: the sibling
engine lane found **B-43** (today, /163): "Return to owner's hand" is
encoded `Zone(HAND, ANY)` → seat-0 hand on three M21 cards (Barrin,
Tolarian Archmage; Niambi, Esteemed Speaker; Roaming Ghostlight), vs the
correct `Zone(HAND, OWNER)` used by Read the Tides / Sublime Epiphany /
Unsubstantiate. Deliberately UNFIXED — "the fix changes M21 games, and the
RL pilot checks byte-identical M21 episodes. Schedule it at a pilot era
boundary: three builders → OWNER, three goldens re-baked, and a pack
bouncing an opponent's creature." B-43 and this §3.1.4 fix each change
M21 game semantics ⇒ each re-baselines the episodes ⇒ doing both at the
SAME boundary costs one re-baseline cycle instead of two:
{rig `asking_seat` fix, B-43 OWNER fix + goldens re-bake, legacy re-collect
scope decision, NEW episodes baseline (record sha + provenance), explicit
re-pin, dry-run, then the next pilot iteration}. Both fixes' data bias is
symmetric in mirror games (same rig on both sides of the probe), so
pending-tomorrow mirror verdicts remain valid as measured.
1. `provider()`: seat from `DecisionStream.asking_seat` when non-None
   (`seats.index(str(asking_seat))`), falling back to `resolve_seat` when
   None (B-35-patched processes). `resolve_seat` stays as the documented
   fallback, not the primary.
2. Re-measure with the same spy (divergence must read 0/0 on the same seed
   block) + a 2-game byte-check at the P2 seeds: rows will DIFFER from
   nights 1-2 where a block ask re-routes (expected); the NEW episodes are
   the baseline — record sha + note, re-pin explicitly with provenance.
3. Legacy re-collect program (the review's "re-collect data collected with
   it"): every BC pack + duel/elo dataset collected through this rig since
   v2 exists had ~8% of defender block asks answered by the wrong seat's
   policy. Owner decision needed on scope: (a) re-collect BC training data
   (changes future training, NOT the frozen anchor bsh_S3a_s1_b — the
   anchor stays frozen per pilot governance), (b) re-run duel/elo tables
   (numbers shift; ELO ladder gains the correct defender defense), (c)
   accept-with-disclosure for pre-pilot history. Recommend (a)+(b) as the
   next funding unit; (c) for the historical record.
4. The frozen pre-RL anchor was trained on mis-routed block data; its
   mirror verdicts are valid AS MEASURED (same rig on both sides of the
   probe — the error is symmetric in the mirror games) but the anchor's
   absolute strength carries the v1/v2 block-routing bias. Record in the
   first mirror-positive entry if it ever occurs.

## Harvest discipline update (sibling commit 0085671, 15:06)
`reports/episodes_iter1.jsonl` is **375 MB** (not the 3.4 MB of a
compressed subset I had assumed) — GitHub refuses >100 MB, so the sibling
lane rebuilt the three unpushed commits (9c67adf, 26b0852, fc12edd)
WITHOUT it and gitignored the file (backup tag
`backup/pre-episodes-drop-2026-10-27`, local only). My /161 + seed-registry
commits now read **7e0ba44 / 3c2573e** (same tree, author, dates).
STANDING RULE for future harvests: large episode jsonl files are NEVER
committed — durable evidence by SHA-256 in the entry/NUMBERS + the file
on disk under `reports/`; small artifacts (probe/audit/diag JSON) still
commit. The 23:59 window is unaffected (working-tree fingerprint
unchanged: 07fd1a6e re-verified post-rewrite).

## Day-queue state
Item 2 (this entry): MEASURED + pre-registered, implementation deferred
post-harvest (era-boundary bundle incl. B-43, above). Item 3 (ZNR `1+*`
shape gap): CLOSED as a my-lane task —
/99 shows it was already resolved 2026-10-18/19 at the supply level
(shape-gap exclusion + census-consistent ShapeGap registration;
`get_supply("engine","ZNR")` exits 0, 267 deckable, Nighthawk Scavenger
excluded-and-registered). The remaining grammar round (a card-type-census
quantity as a proper Quantity atom — /99: "encoding it is a grammar round,
so a parse kludge would lie about the atomics") belongs to the sibling
compiler wave (see /160 tickets B-28/B-36..B-39 on branch sets/onboarding).
Item 1 (T-G5 ladder): DONE (/161).
