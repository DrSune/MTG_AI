# 31 — k-of-n ONE_OF lands (T2 executor batch, 2026-10-07)

Implements the /30 K-OF-N SPEC: the partition selector now ASKS `want`
times over the shrinking menu. `{choose} x {count}` is orthogonal on the
model-facing side; pick-k = k sequential pick-one asks, the same shape
`binding.py`'s TARGET designation loop (1376) already ran silently.

## What fires
- `selectors.py` ONE_OF: QConst = exact (clamped by population), QAtMost
  = NONE-stop AFTER the mandatory first pick, any other count shape
  RAISES naming itself. want==1 stays the BYTE lane (frozen tag
  `one_of:<src>:<digest>`); want>1 numbers asks AFTER the frozen kind
  prefix — `one_of:<src>:1of2:<digest>` — bc_data's site-kind law
  untouched, no new SITE_KINDS vocab, episodes re-encode only.
- `ExecCtx.one_of_pick: Handle|None` -> `one_of_picks: tuple` — REST
  subtracts EVERY pick; `query.rest_of` accepts the legacy single Handle
  (frozen callers) or a pick set.
- `query.py` legal_targets ONE_OF mirrors the loop (§8.3): QConst>1
  min=max=min(want,n); QAtMost 1..min(want,n); want==1 branch byte-frozen
  INCLUDING its n=0 "infeasible" stance — the new lanes instead report
  (0,0) FEASIBLE for n=0, matching the runtime's documented C17 clamp
  (empty population chooses NOTHING). The divergence is deliberate:
  frozen replay pins vs honest new-lane reporting; revisit when the
  frozen want==1 n=0 edge is next touched.
- Auto-fill = binding.py:1392 condition verbatim: last legal candidate
  is TAKEN without an ask (so n==want asks exactly k-1 times; n==1 asks
  zero). Constructor already refuses QUnbounded ONE_OF (ValueError);
  resolve-guard catches the rest (QAtLeast/QX: NotImplementedError).
- `Verb.CHOOSE` multi-pick raise STAYS (verbs.py:1398) — merging it with
  entity-PICK is T3; node-Choose k-subset compound tokens stay
  KEEP-SEPARATE (menu = effect branches).

## Volume census (why the grep says zero)
Pool census 2026-10-07, both sources (`MTG_bot/data/mtg_bot.db` mode=ro,
`MTG_bot/data/M21.json` via `ingest_pool`): "Choose two/three —" opener
**0 cards**; entity `choose two` **0**; mid-text `choose two` **0**;
`choose one or more` **1** (Sublime Epiphany -> node-Choose QUnbounded,
5 options, but `engine_supported=False` -> cannot be pack-cast). So
`grep '2of2|1of2' tools/training/episodes_v2.jsonl` = **0 lines**: the
atom enters at volume 0 EXACTLY as /30's transfer-test predicted. The
27 unit fixtures in `test_executor_kofn.py` are the seed the packs
cannot yet provide.

## Evidence (all executed)
- `pytest MTG_bot/core/test_executor_kofn.py` **27/27** (want2 shrink +
  tag `:1of2:`/`:2of2:`; frozen want==1 tag pinned against
  `site_digest` recomputation; QAtMost NONE after pick1, NONE at ask0
  raises; singleton auto-fill; n==want asks once; effect-per-pick via
  TAP; REST subtracts BOTH picks; query slots incl. n=0 frozen
  infeasible vs new feasible-zero; `rest_of` union).
- Gates: core **2420 passed + 2 st** (= doc-29's 2393 + 27 new); packs
  **373/373**; tools audit+training **153**.
- Re-cert chain re-run: puzzle_cert items **156** / fail_registered 11
  / mean_random 0.3489 — and **puzzle_corpus.json + episodes_v2.jsonl
  md5-IDENTICAL** to pre-change (d6228c7b… / f42aceb5…, 114 eps / 185
  asks). Byte-frozen want==1 PROVEN at episode level: zero drift.
- Review: adversarial subagent spawn unavailable (depth limit) — diff
  self-review covered the hunt list (menu-never-empty bound proof,
  NONE-at-0, auto-fill parity vs binding.py, journal payload, Handle-is-
  class union safety, leftover-attribute scan: one stale comment fixed).
  Weaker check than fresh eyes — flag for the standing review queue.

## T3 prerequisites (registered here, NOT done)
1. MERGE sel-CHOOSE-silent (157 survivors post-/29) onto this asking
   PICK-over-legal-set; entity opener ("choose two targets" English
   sense) rides THIS merge — adding the regex now, with zero pool
   population and no /30 spec line, would be speculative.
2. The 2xQConst(2) + 3xQUnbounded search-pick survivors (/29): QConst(2)
   is now EXECUTABLE — flip the `_one_of_search_picks` skip
   (compiler.py:1091-1125) and re-cert; QUnbounded still needs a
   until-quit ask shape.
3. Packs seed k-of-n when a real modal card enters the pool (first
   integration batch with "Choose two —" cards); episodes then gain
   2of2/1of2 ask rows, vocab tokens per digest as usual.
4. node-Choose QUnbounded + engine-support gap (Sublime Epiphany) if a
   branch-set k scenario is ever wanted at pack level.
