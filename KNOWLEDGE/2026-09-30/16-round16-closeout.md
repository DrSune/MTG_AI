# 2026-09-30 · 16 — Round-16 close-out: COMBAT LIVE, all-pool zero crashes, 297/305

Arc 3 (owner "yes do arc 3" 09:14 + correctness/visuals mandate). Six commits: 4a8f42d (binding) ·
ad88fef (16a damage/SBA/FIGHT/catalog) · 428cf56 (16b declare) · 0e03a99 (16c blockers/CR-510) ·
e81ece1 (16e control/auras) + this. Round-15 (viewer, fa7085d) preceded. Suite 2022→**2079**,
engine gate **288→297/305 (45 verbs)**, all frozen rulings held (state.py NEVER touched;
goldens frozen all round — zero golden moves, zero coverage drift; PC-1/2/3/4 EXACT every phase).

## The headline metrics (NUMBERS-backed)
- **ALL-POOL (all 305 cards, including the ~8 still-flagged) plays 10-seed with ZERO crashes.**
  Games now END — combat deaths and losses are legitimate endings; **survival% retires as the
  engine-quality gate; "zero crash classes" is the standing bar** (engine30: 26/30, 0 classes).
- Combat shipped complete for M21's needs: declare (mandate-narrowed asks, sickness/defender/
  haste/vigilance consumers), blockers (CR 509 + flying/reach + protection + menace + restrictions),
  damage (CR 510 orders M21-era, trample asks, deathtouch, FS/DS split), as-though-blocked,
  marked damage + SBA sweeps, token-carried statics/mandates end-to-end, GAIN_CONTROL overlay,
  auras. Rules cites verified LIVE when uncertain (Baneslayer protection, CR 509.4, 702.x).
- **Owner's compounding-risk machinery works**: trace catalog (10-seed fingerprints, first-
  divergence locator) reconciled at every semantic change this round (combat boundary divergences
  each located + clean + repinned: 5504→5641→6676→6138 entries, always 0 unexplained).
- **Validation packs 16/16**, all authored from PRINTED text (Taunter echo, Primal Might X-fight,
  haste/sickness/defender/vigilance/FS-trades, block save, trample, Herald, Whale mandate,
  Traitorous flip). Two cards' printed-text ground-truth reversals caught the "trust memory" trap
  (PITFALL: card text = dump + live Scryfall, never recall).
- **12 further engine bugs found+fixed+test-pinned by this round's own packs/gates** (protection
  repr-mismatch silently disabling a veto; binding-blind player atoms; attach-order wipe;
  CONTROLLER_IS dead-on-player-handles making Mangara dead code; +8 from 16c/16e tables).

## Honest remaining wall (8 cards, all by-design deferrals, all loud)
PHASE_OUT ×2, COPY ×2 (deep semantics, deferred by ruling), COUNTER_SPELL family ×5-minus-overlap
(response window = R16-1 DEFERRED by design: our instants are own-turn-only, so uninterrupted
combat is rules-honest; later (ii)-lite response vocab is additive, catalog-provable), + PC-8-family
ETB-target designation (Bone Pit Brute; needs the 12c ask-shape lift — the next real PC-8 move),
PW-attackers + multi-blocker blocker-side ordering (doc 14 gaps).

## ROUND 17 (RECOMMENDED, unbnd): the full-corpus validation campaign
16a's pack schema scaled: scripted validation packs for ALL engine-supported cards (297), authored
from printed text (wave-batched ~25 cards/delegation, template-family-first since families share
semantics), each pack's trace inspectable in the viewer. THE owner-inspection loop: per wave,
2-3 showcase replays + the pack's assertion table → owner verdicts become ledger rows. This is
the "understand AND programmed right, card-by-card" mandate executed at corpus scale BEFORE any
further feature work; expected byproduct: packs catch semantic drifts unit tests miss (they found
12 bugs in one round at 16-pack scale).

## Owner-facing artifacts
reports/replays/replay_s7.html (pre-combat baseline) · s19/s24 (first combat deaths) · s37 (control
-steal flip) · viewer = open the HTML; action log shows every micro-decision with candidates.
