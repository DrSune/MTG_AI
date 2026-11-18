"""The closing checks of the five entries KNOWLEDGE/2026-11-18/215 found closed or no fault (F01,
F15, F49, F64, K1), each with a control: a check that would fail if the fault were open, so the
closing check cannot pass vacuously (216 §4 E2 asked for them to be run). One line per check.

    stale_entries.py <checkout>      (run from the checkout; output: stale_entries.txt)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core.executor.games import compile_supply, get_supply  # noqa: E402
from tools.run_scenarios import run_pack  # noqa: E402

HERE = Path(__file__).resolve().parent
S = ROOT / "tools" / "scenarios"
CLOSED = ROOT / "reports" / "engine_fault_triage_2026-11-18" / "closed_checks"


def pack(role: str, path: Path, records: bool = False) -> None:
    """A pack on its set's supply: verified trees (as the suite's top-level and card packs run),
    or every record applied (``records``: as its mapped packs run)."""
    code = str(json.loads(path.read_text()).get("set", "M21"))
    sup = compile_supply("all", code, require_verified=False) if records else get_supply("all", code)
    fails = run_pack(path, sup)
    print(f"{role:8} {'PASS' if not fails else 'FAIL'}  {path.relative_to(ROOT)}" + (f"  {fails}" if fails else ""))


def test(role: str, node: str) -> None:
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
                         cwd=ROOT, capture_output=True, text=True)
    print(f"{role:8} {'PASS' if out.returncode == 0 else 'FAIL'}  {node}: {out.stdout.strip().splitlines()[-1]}")


print("== F01: a target-player slot with no legal player (CR 603.3d; spells 601.2c; abilities 602.2b)")
test("check", "MTG_bot/core/test_executor_hexproof.py::TestPlayerHexproof::"
              "test_a_trigger_targeting_an_opponent_with_hexproof_is_removed")
pack("check", S / "runed_halo_names_brash_taunter.json")
pack("control", HERE / "checks" / "f01_trigger_control_halo_names_another_card.json")
pack("check", HERE / "checks" / "f01_spell_duress_with_no_legal_opponent_is_no_row.json")
pack("control", HERE / "checks" / "f01_spell_control_duress_with_a_legal_opponent.json")
pack("check", HERE / "checks" / "f01_activated_steward_with_no_legal_opponent_is_refused.json")
pack("control", HERE / "checks" / "f01_activated_control_steward_with_a_legal_opponent.json")

print("== F15 (B-54): a spell whose required target has no legal candidate is offered")
pack("check", HERE / "checks" / "f15_swift_response_with_no_tapped_creature_is_no_row.json")
pack("control", HERE / "checks" / "f15_control_swift_response_with_a_tapped_creature.json")
readers = subprocess.run(["git", "grep", "-n", "legal_casts(", "--", "*.py"], cwd=ROOT, capture_output=True,
                         text=True).stdout.strip().splitlines()
print(f"check    {'PASS' if not readers else 'FAIL'}  query.legal_casts has no caller left: {readers or 'none'}")

print("== F49: 'doesn't untap during its controller's untap step' blocks every untap (CR 502.3)")
pack("check", CLOSED / "act_of_treason_untaps_a_creature_sleep_paralysis_holds.json")
pack("control", CLOSED / "sleep_paralysis_taps_the_bear_control.json")

print("== F64: Teferi, Master of Time's -3 duration (CR 702.26)")
data = json.loads((ROOT / "MTG_bot" / "data" / "M21.json").read_text())
cards = data["data"]["cards"] if "data" in data else data["cards"]
text = next(c["text"] for c in cards if c["name"] == "Teferi, Master of Time")
minus = next((line for line in text.splitlines() if "3]:" in line and "phase" in line.lower()), "")
ok = "until its controller's next turn" in minus
print(f"check    {'PASS' if ok else 'FAIL'}  the printed -3 reads classic phasing: {minus!r}")
pack("check", S / "teferi_master_of_time_phased_out_waits_for_its_controller.json")
pack("control", S / "teferi_master_of_time_phase_in_at_controllers_untap.json")

print("== K1: known_bugs/2026-11-05/up_to_one_none_chosen_crashes (Cavalier of Dawn, 'up to one' and none chosen)")
pack("check", HERE / "checks" / "k1_pack_none.json", records=True)
run = subprocess.run([sys.executable, "tools/cards/cardtool.py", "runpack", "M20",
                      str(HERE / "checks" / "k1_pack_none.json"), "--card", "Cavalier of Dawn",
                      "--draft", str(HERE / "checks" / "k1_draft.py")], cwd=ROOT, capture_output=True, text=True)
last = [line for line in run.stdout.splitlines() if line.strip()][-1:] or [run.stderr.strip()[-200:]]
print(f"check    {'PASS' if run.returncode == 0 else 'FAIL'}  the folder's pack against its draft (cardtool runpack): {last[0]}")
pack("covered", S / "mapped" / "M20" / "cavalier_of_dawn_no_target_makes_no_golem.json", records=True)
pack("control", S / "mapped" / "M20" / "cavalier_of_dawn_its_controller_gets_the_golem.json", records=True)
