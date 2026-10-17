# 91 — ZNR.json on disk (Oct-9 refetch) FAILS the /59 sanity battery again — same poisoning signature

Date: 2026-10-18. Ran the /59 battery (mechanic-phrase counts + anchor cards) read-only against
`MTG_bot/data/ZNR.json` (untracked, mtime Oct-9 17:33, 4.6 MB).

- Fingerprint: **sha256 `aa1d850e8755fe5888dcbb1b1d1348270b850cb587388e39e4cd30836e145001`**
- Wrapper: valid v5.3 (`meta.version 5.3.0+20261008`, meta.date 2026-10-08), `data.code=ZNR`,
  `data.name="Zendikar Rising"`, baseSetSize 280, cards list len 445, setCode=ZNR on cards.
- Battery results: `foretell` occurrences **0** (home-set mechanic of ZNR — must be >0);
  flash **6** (home mechanic, far too few); all four set commanders absent (Naru Meha, Vorinclex
  Monstrous Raider, K'rrik Son of Yargle, Gishath Sun's Avatar); mechanic profile landfall **50** /
  kicker **59** — a Zendikar-BLOCK-era profile wearing a ZNR label.
- Verdict: the Oct-9 file is NOT an authenticated ZNR dump (identical failure class to /59; the refetch
  did not clean it). **Ingest stays BLOCKED** (owner rule: two-way verification — owner drop-in OR
  checksum + second source). Playbook /88 remains armed, trigger not met.
- Owner ask (unchanged from /59): verified ZNR source, or the checksum of the authentic dump to
  compare against; meanwhile this exact artifact sha256 is registered so future sessions recognize and
  reject it instantly.
- Repro (read-only): parse json; count `foretell` in card texts; membership-test the four anchors.
