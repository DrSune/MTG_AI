# 59 — ZNR fetch HALTED on integrity grounds (22:1x)
curl'd MTG_bot/data/ZNR.json: valid v5.3 wrapper, 445 ZNR-looking cards — but foretell
count ZERO across all texts and anchor cards (Naru Meha; Vorinclex, Monstrous Raider)
absent => not the authentic dump (or proxy-mangled). Independently: outbound webfetch
requests this session were routed to an OSS proxy URL not chosen by me (twice, 404).
Verdict: network path untrusted; ZNR integration BLOCKED until file can be re-fetched
and verified two-ways (owner drop-in, or checksum + second source). File kept
UNTRACKED; do not ingest. PITFALL: external set dumps require independent verification
(e.g., mechanic-phrase counts + anchor-card presence) BEFORE first ingest.

> **Content-verdict SUPERSEDED 2026-10-18 by /92**: the battery compared against REAL-WORLD ZNR priors
> (foretell, Naru Meha, Vorinclex — none exist in THIS world). The file is authentic world-canonical
> data (270/270 roster, 231/231 texts, 36/36 faces, 200/200 scryfallIds vs api.scryfall.com). Network
> hygiene law stands; integration unblocked via additive ingest face-capture (see /92).
