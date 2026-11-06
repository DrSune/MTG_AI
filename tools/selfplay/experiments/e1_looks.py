"""E1's looks (186 §2): whenever a label job's served forward passes cross the next multiple of
2.65M, run the instrument on its labels so far and apply the pre-registered stop rules; on a stop,
end the job. After the fourth look the job ends by its own budget (10.6M) and the point estimate
decides (printed by the last look).

    PYTHONPATH=<checkout> PY e1_looks.py CKPT RUN_DIR [MAX_LOOKS]
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

BOUND = 2.65e6
HERE = Path(__file__).resolve().parent


def decide(res: dict, look: int, max_looks: int) -> str:
    lab, pl = res["label"], res["placebo"]
    S, se, noise, fpl = lab["signal"], lab["signal_se"], lab["noise_per_label"], res["fp_per_label"]
    data = res["forward_passes"]
    b = lab.get("B_star_fp")
    b_low = noise / (S + 2 * se) * fpl if S + 2 * se > 0 else float("inf")
    b_high = noise / (S - 2 * se) * fpl if S - 2 * se > 0 else float("inf")
    placebo_ok = (pl["signal_z"] or 0) < 2
    res["bounds_fp"] = [b_low, b_high]
    if b is not None and data >= 4 * b and b_high <= BOUND and placebo_ok:
        return "pass"
    if b_low > BOUND:
        return "fail"
    if look >= max_looks:
        if b_low <= BOUND <= b_high and max_looks == 4:
            return "gray: extension"
        return "pass (point estimate)" if b is not None and b <= BOUND and placebo_ok else "fail (point estimate)"
    return "continue"


def main() -> None:
    ckpt, run = sys.argv[1], Path(sys.argv[2])
    max_looks = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    look = 1
    while look <= max_looks:
        s = run / "summary.json"
        fp = json.loads(s.read_text())["forward_passes"] if s.exists() else 0
        done = not any(str(run) in " ".join(p) for p in _cmdlines())
        if fp < look * BOUND and not done:
            time.sleep(30)
            continue
        out = run / f"look{look}.json"
        subprocess.run([sys.executable, str(HERE / "e1_instrument.py"), ckpt, str(run), "--K", "16",
                        "--out", str(out)], check=True, stdout=subprocess.DEVNULL)
        res = json.loads(out.read_text())
        verdict = decide(res, look, max_looks)
        res["look"], res["verdict"] = look, verdict
        out.write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps({"look": look, "verdict": verdict, "labels": res["labels"],
                          "forward_passes": res["forward_passes"],
                          "B_star_fp": res["label"].get("B_star_fp"),
                          "bounds_fp": res["bounds_fp"], "signal_z": res["label"]["signal_z"],
                          "placebo_z": res["placebo"]["signal_z"]}), flush=True)
        if verdict != "continue":
            for pid, cmd in _procs():
                if str(run) in cmd and "label_run.py" in cmd:
                    os.kill(pid, signal.SIGTERM)
            return
        look += 1


def _procs():
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                cmd = open(f"/proc/{d}/cmdline").read().replace("\0", " ")
            except OSError:
                continue
            yield int(d), cmd


def _cmdlines():
    return [[cmd] for _, cmd in _procs() if "label_run.py" in cmd]


if __name__ == "__main__":
    main()
