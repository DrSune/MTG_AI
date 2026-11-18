"""The network's parameter count by part, and the AdamW state a resume would carry (§5).

    .venv/bin/python reports/network_readiness_2026-11-18/params.py runs/r29_ab/b100.pt
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.selfplay import model as M  # noqa: E402


def main() -> int:
    net, table, _ = M.load(sys.argv[1], "cpu")
    parts: dict[str, int] = {}
    for name, p in net.named_parameters():
        parts[name.split(".")[0]] = parts.get(name.split(".")[0], 0) + p.numel()
    total = sum(parts.values())
    print(f"parameters {total:,}; AdamW moments {2 * total * 4 / 2**20:.1f} MiB (fp32 exp_avg + exp_avg_sq)")
    for k, v in sorted(parts.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v:,}")
    print(f"cards {len(table.oracle_ids)}, component vocabulary {len(table.ir_vocab)}, config {net.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
