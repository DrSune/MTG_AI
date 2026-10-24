"""Shared helpers for the tests under tools/ (added 2026-10-24).

Checkpoints are never committed (tools/training/CHECKPOINTS.md), so a fresh clone, CI, or a
scratch copy has none. A test that needs one must SKIP with the missing path as its reason. A
FileNotFoundError reads as a broken harness; a skip reads as "this machine lacks the artifact".
Measured before this helper: 29 tools tests errored or failed for exactly that reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def skip_unless_files(*paths: str | Path) -> pytest.MarkDecorator:
    """``skipif`` mark that names every missing file; usable as a decorator or ``pytestmark``."""
    missing = [str(path) for path in paths if not Path(path).exists()]
    return pytest.mark.skipif(
        bool(missing),
        reason=f"needs untracked file(s) {', '.join(missing)}; see tools/training/CHECKPOINTS.md",
    )
