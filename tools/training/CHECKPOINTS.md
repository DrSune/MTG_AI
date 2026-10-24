# Checkpoints: evidence by hash, not by blob

Checkpoints (`*.pt`) are **never committed**. GitHub rejects any file over 100 MB, the repository
is public, and a checkpoint is a derived artifact. The evidence that a result came from a given
checkpoint is its SHA-256 in [`CHECKPOINTS.sha256`](CHECKPOINTS.sha256), which covers every
`tools/training/*.pt` on the DGX Spark as of 2026-10-24 (254 files, 11 GB).

Verify from the repository root:

```bash
sha256sum -c --quiet tools/training/CHECKPOINTS.sha256
```

A missing file prints `No such file or directory`, a changed one prints `FAILED`. Tests that
need a checkpoint skip with that path as the reason when it is absent (`tools/_testutil.py`).

## What happened on 2026-10-24

Six checkpoints had been force-added on 2026-10-06, despite `*.pt` in `.gitignore`. Four of
them are about 134 MB, so `main` could no longer be pushed. Nothing had been pushed since
2026-09-14. At the owner's instruction they were removed from the unpushed history with
`git filter-branch`. They stay on disk, untracked, and are listed in the manifest. Commit SHAs
after `f7dec8d` changed; [`docs/COMMIT_MAP_2026-10-24.tsv`](../../docs/COMMIT_MAP_2026-10-24.tsv)
maps the old SHAs (still cited in KNOWLEDGE) to the new ones.

| file | bytes | introduced in (pre-rewrite SHA) | evidence it backs |
|---|---|---|---|
| `bc_s2.pt` | 140,541,669 | `f7dec8d` | batch-2 v2-schema BC retrain, NULL result |
| `bc_s1.pt` | 140,388,453 | `f75ef1a` | tracked "for parity with bc_s2.pt", Elo-harness evidence |
| `bc3_A.pt`, `bc3_A_best.pt` | 140,537,279 / 140,543,102 | `f907bb0` | batch-3 arm A, eval 0.6136 (+2.60 SE) |
| `bc3_B_best.pt` | 700,725 | `7629864` | batch-3 arm B, 169K params, passes the 3-SE gate (0.6591) |
| `bc3_dagger_best.pt` | 702,092 | `7629864` | batch-3 DAgger arm, NULL |

Copies of these six, the full pre-rewrite history (`git bundle`, 440 MB) and the `/tmp/opencode`
evidence tree (6.5 GB) are in `~/mtg_ai_evidence/` on the Spark. That is the same disk, so it
protects against git operations and `/tmp` cleanup, not against disk loss. Copy the bundle
elsewhere.
