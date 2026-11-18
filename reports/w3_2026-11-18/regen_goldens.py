"""Re-baseline the M21 golden trees (MTG_bot/core/golden/M21) after gate round W3's template
changes: the state triggers (Nine Lives, Mazemind Tome), the extra-trigger static (Sanctum of
All) and the reveals that name their cards (DESIGN_ATOM_ONTOLOGY §20). A golden refresh is a full
regenerate (golden.write_goldens); the diff it leaves is the round's M21 tree change.

    regen_goldens.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.golden import write_goldens  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

print(write_goldens(ingest_pool(ROOT / "MTG_bot" / "data" / "M21.json"), build_full_registry(), "M21"))
