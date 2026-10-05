"""Thin CLI alias for the metric logger — see tools/training/wandb_log.py for
the metrics.jsonl append format and the wandb no-op behaviour.

    .venv/bin/python tools/training/log_metric.py --step 10 --loss 0.53 --phase s1-bc lr=3e-4
"""

from __future__ import annotations

import sys

if __package__ in (None, ""):  # allow plain-script execution from anywhere
    import pathlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from wandb_log import main

if __name__ == "__main__":
    sys.exit(main())
