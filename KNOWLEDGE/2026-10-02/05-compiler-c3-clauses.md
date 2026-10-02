# 2026-10-02 · Compiler campaign C3 — dropped clause emissions (Waker +1 tail, Transmogrify reveal-until; Peer STOP)

HEAD at batch start: 9e26ba2 (C2). Batch: restore three dropped clause emissions; two
promoted, one falsified as UNCOMPILABLE-IN-THIS-IR. Goldens moved only through the
C1-form set-evidence audit (303 byte-identical, abilities-only keys).

## Per-card verdicts

### Liliana's Waker +1 — PROMOTED (bucket B5a, tid `B5a-each-opp-cant-lose-life`)
- Restored clause: each opponent who can't lose life… tail of the loyalty +1 ability.
  Tail merges via the R11-1 loyalty-trailing path into the loyalty-+1 `ActivatedAbility`
  as `Seq(DISCARD, EachPlayer(...))`.
- Encoding: `EachPlayer(ALL_OPPONENTS, Conditional(FNot(FAtom(ZONE_COUNT_GE,
  who=YOU, zone=Zone(HAND,YOU), count=QConst(1))), LOSE_LIFE(controller=YOU, amount=3)))` —
  the gate "can't lose life" is read as the engine's loss-shape proxy: no cards in hand
  (the corpus' only mechanical can't-lose-life substrate; PITFALLS-adjacent).
- **Documented deviation**: the tail is emitted AFTER the discard head (post-discard
  hand check). r21b precedent, roadmap-sanctioned; pre-discard reading would need a
  state snapshot the IR cannot hold.
- **Misregister correction**: the roadmap attributed this sentence to b2b/b4; the bucket
  partition truth is B5a (bucket B5a.json:530 is the only occurrence, corpus-wide single).

### Transmogrify — PROMOTED (bucket B5b, tids `B5b-transmogrify-reveal-creature`,
`B5b-transmogrify-shuffle-rest`; spell folds to `Seq(EXILE, SEARCH, SHUFFLE)`)
- Restored tail: SEARCH(1× CHOOSE `TYPE_EQ Creature` @ `Zone(LIBRARY, TARGET_PLAYER,
  TOP)`, destination `Zone(BATTLEFIELD, TARGET_PLAYER)`, controller TARGET_PLAYER) +
  SHUFFLE(`Zone(LIBRARY, TARGET_PLAYER)`).
- **Documented divergences** (accepted): (1) "reveals … until a creature" is encoded as
  TOP-enumerate = `entries[-1:]` only — a non-creature top misses (no deeper scan; the
  whole-library CHOOSE was rejected: it would pick any library card, `Library 0`);
  (2) "then shuffles the rest" carried as SHUFFLE of the whole library (rest ≡ remainder
  after the chosen card moved — same verb, superset zone, engine-correct outcome);
  (3) the REVEAL verb is SEARCH-verb garnish — SEARCH already names the card.
- TARGET_PLAYER at runtime = `controller_of(bound target)` (selectors.py:87-95) =
  "that creature's controller". Correct semantics, no second printed target.

### Peer into the Abyss half-life clause — **STOP (permanent verdict, roadmap correction)**
- "loses half their life total" has NO quantity lane: `QPropField` has no `LIFE`
  property and `_v_lose_life` reads `amount()` only. The golden stays byte-identical
  (audit asserts it), the pack stays in `tools/audit/suspects/`, and the scenario stays
  red-as-intended (`expected 10, got 20`). Any future fix must come with an engine
  quantity lane (`QPropField.LIFE`), not a template hack. Roadmap must list Peer under
  "needs engine support", not "compiler emit-fix".

## The dual-slot cast contract (new pitfall, see PITFALLS 2026-10-02 C3 row)
A spell with BOTH a TARGET-mode Selector AND any `TARGET_PLAYER` read gets a
**synthesized second positional slot** (query.py:778-798, 14b B-8 fix) even when the
player is derived, not printed. Cast must supply both designations positionally; scenario
packs use the r22b `decisions: ["player:N"]` token. `binding_one("target")` returns the
FIRST designation (the creature), so TARGET_PLAYER still resolves as
controller-of-target. The frozen engine is right; the pack was wrong.

## Numbers (full table in NUMBERS.md 2026-10-02 C3 section)
- Audit: 2 moved (abilities-only), 303/305 byte-identical, lane multisets proven
  (`/tmp/opencode/c3_inventory_audit.py` vs `/tmp/golden_pre_c3`).
- PC-1 303/305 · PC-2 637/639 · PC-3 0 · PC-4 0 · PC-8 98/305 Δ0 · UNPARSED queue 5→3.
- Suites: bucket 185 · `test_compiler_c3.py` 7 · core 2284+3 subtests · scenarios
  292/292 (2 promoted) + 9 suspects 0/9 red-as-intended · games 100 seeds 0 crash
  classes · catalog 2/10 diverged (both seeds located to a changed card) → repin 0/10.
