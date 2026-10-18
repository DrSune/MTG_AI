# 92 — ZNR.json VINDICATED: authentic world-canonical data; /59's rejection was a false alarm from real-world priors — the real blocker is MDFC faces in ingest

Date: 2026-10-18. **Supersedes the verdict of /91 (same day) and the content-verdict of /59.**
/59's network-path incident (OSS-proxy-routed requests) was real, but its *content* verdict was wrong:
the battery it ran ("foretell must be > 0; anchors Naru Meha / Vorinclex / K'rrik / Gishath must be
present") was derived from the author's memory of the REAL-WORLD Zendikar Rising. **This world's
Zendikar Rising is a different card list: it has NO foretell (keyword `k:foretell` → 400 bad_request
on the world's Scryfall) and contains NONE of those four legendary creatures** (verified: `set:znr
"Naru Meha"` & three more → total_cards 0; Naru Meha exists here only as a c21 printing). The
on-disk file matches THIS world's canonical Scryfall on every checkable dimension.

## Two-way verification (per /59's own admission rule, satisfied without owner: live Scryfall = source 2)
All checks run 2026-10-18 against `api.scryfall.com` (headers verified genuine; repro commands below):
- Roster: file unique names **270** vs canonical `set:znr unique=cards` **270** — zero diff either way.
- Oracle text: **231/231** non-MDFC byte-identical (whitespace-normalized).
- MDFC face texts: **36/36** match the detail endpoint's `card_faces[].oracle_text` (the search
  endpoint returns empty top-level oracle_text for modal_dfc — this API quirk is what hid them).
- Provenance: `identifiers.scryfallId` == canonical card id on **200/200** sampled.
- Set object: canonical `card_count 391`, `printed_size 280`, expansion — file wrapper consistent.
- Poison-suspect file (sha256 `aa1d850e…145001`) = THIS SAME authentic file. The pitfall line added
  to PITFALLS this morning is corrected below.

## What actually blocks ingest (the real §8 moment, expected by /88 risk-(a))
`ingest_pool` raises StateCorruptionError on `Emeria's Call // Emeria, Shattered Skyclave`:
445 file entries, **270 unique oracle ids**, **129 duplicate groups** = (i) **36 modal-DFC cards whose
FRONT and BACK entries share one scryfallOracleId** and differ in every captured field (side 2
entries; `faceName`/`side`/`otherFaceIds` present), and (ii) frame/alt-art variant entries
(frameEffects/promoTypes/textless — these dedup fine, all captured fields equal). M21 has **zero**
double-faced cards, so the M21-era dedup law ("same oracle id ⇒ corruption unless byte-equal") never
faced faces. RawCard has a `layout` field but no face capture at all.
- Semantic-field diff census across dup groups: differing fields = exactly the two-face pattern
  (manaCost/type/text/side/faceName on 30–36 groups) + cosmetic variant fields (uuid/skuIds/
  purchaseUrls/frameEffects/flavorText/artist/number…). No contradictory pair for a SINGLE face exists.
- Mechanic "profile mismatch" (/59 + my morning note: landfall 50 vs 24) EXPLAINED: file counts span
  both faces + variant entries; canonical top-level counts miss all face texts. Not a corruption
  signal. File profile (dedup by oracle+side): landfall 50 / kicker 59 / flash 6 / menace 9.

## Standing laws from this incident (binding)
1. **Canonical-source law**: a set dump is validated ONLY against THIS world's canonical sources
   (Scryfall roster + oracle texts + ids), never against an agent's memory of the real world.
   Verify a mechanic EXISTS here (`k:foretell` → 400) before making it an anchor of any battery.
2. World-fact register additions: **foretell does not exist as a keyword in this world**; this world's
   ZNR = 270 unique cards, no set-commander legends from real-world ZNR; MDFC texts live only in
   `/cards/{id}` → `card_faces[]` (search endpoint top-level oracle_text is empty for modal_dfc).
3. /59's network hygiene (battery BEFORE first ingest) stays — the tool was right, its expectations
   were wrong.

## Unblock path (executed same day)
Ingest gets additive face capture (back folded onto front RawCard as structured face data, zero-loss
§11; corruption law preserved for every non-face collision; M21 pool byte-identical re-certified) —
delegated; then clause audit `--set ZNR` produces the gap ledger (§8/§11), and the atomics
re-evaluation vs TOTAL pool proceeds with real data.

## Repro
`.venv/bin/python` + curl `api.scryfall.com/cards/search?q=set%3Aznr&unique=cards` (270),
`/sets/znr` (391/280), `/cards/{id}` for MDFC faces, and
`from MTG_bot.core.compiler.ingest import ingest_pool; ingest_pool('MTG_bot/data/ZNR.json')` (currently
raises on the first face-pair collision).
