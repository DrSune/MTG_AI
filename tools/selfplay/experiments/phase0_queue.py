"""Phase 0's unattended queue (KNOWLEDGE/2026-11-06/187): the pre-registered E0, E1 and E3 steps in
order, E1's stop rules applied as written (e1_looks.decide), then label scaling so the machine does
not idle. Two lanes, each a user service (mtg-phase0@sim, mtg-phase0@labels):
- sim: E0's measurements on the two trained simulators (the cost bench first, on a quiet GPU);
- labels: E1 A, B and C in looks (the extension if gray); E3 on the configuration that passed (A
  if it did, else the passing one with the lowest B*; if none did, A, as a measurement: 186 §5);
  then more of its labels, distilled and measured at 300k, 600k and 1M.
A step leaves runs/phase0/<lane>/<step>.done and a restart resumes at the first undone step; a
failed step is logged and left undone. A label job that stops short resumes in a new directory on
the next unused seeds (the instrument and the distiller read all of a job's directories).

    PY tools/selfplay/experiments/phase0_queue.py sim|labels    (cwd: the pinned run worktree)
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from e1_looks import decide

ROOT = Path("/home/sune/Desktop/MTG_AI")
RUNS, PY = ROOT / "runs", str(ROOT / ".venv/bin/python")
Q = RUNS / "phase0"
LAB, SIM = Path("/home/sune/Desktop/MTG_AI-labels-run"), Path("/home/sune/Desktop/MTG_AI-sim-run")
X, SX = Path(__file__).resolve().parent, SIM / "tools/selfplay/experiments"
GEN = RUNS / "selfplay/r23_mulligan/gen.pt"
CAP = RUNS / "simulator/e0_capture/capture"
LOOK = 2.65e6
E1 = {"A": (2, 2, 1, 30_000_000), "B": (2, 2, 0, 31_000_000), "C": (4, 2, 1, 32_000_000)}
FINAL = ("pass", "fail", "pass (point estimate)", "fail (point estimate)")
LANE = sys.argv[1] if len(sys.argv) > 1 else ""


def log(msg: str) -> None:
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)
    with (Q / f"{LANE}.log").open("a") as fh:
        fh.write(line + "\n")


def run(args: list, out: Path, cwd: Path = LAB) -> None:
    """One command to its end, stdout to out, stderr to out.err; raises on a non-zero exit."""
    with out.open("w") as fo, Path(f"{out}.err").open("a") as fe:
        rc = subprocess.run([str(a) for a in args], cwd=cwd, stdout=fo, stderr=fe, check=False,
                            env={**os.environ, "PYTHONPATH": str(cwd)}).returncode
    if rc:
        raise RuntimeError(f"{Path(str(args[1])).name} exited {rc}, see {out}.err")


def step(name: str, fn, needs: tuple = ()) -> None:
    d = Q / LANE
    if (d / f"{name}.done").exists():
        return
    missing = [n for n in needs if not (d / f"{n}.done").exists()]
    if missing:
        log(f"{name}: skipped, needs {', '.join(missing)}")
        return
    log(f"{name}: start")
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - logged and left undone; the lane goes on without it
        log(f"{name}: FAILED {e!r}")
        (d / f"{name}.failed").write_text(f"{e!r}\n")
        return
    (d / f"{name}.done").write_text(time.strftime("%F %T\n"))
    log(f"{name}: done")


def dirs_of(base: str) -> list[Path]:
    out = []
    while (p := RUNS / "labels" / (base if not out else f"{base}.{len(out) + 1}")).exists():
        out.append(p)
    return out


def totals(dirs: list[Path]) -> dict:
    t = {"forward_passes": 0, "labels": 0, "games": 0}
    for p in dirs:
        if (s := p / "summary.json").exists():
            j = json.loads(s.read_text())
            t = {k: v + j[k] for k, v in t.items()}
    return t


def next_seed(dirs: list[Path], seed0: int) -> int:
    s = seed0
    for p in dirs:
        if (f := p / "summary.json").exists():
            j = json.loads(f.read_text())
            s = max(s, j["config"]["seed0"] + j["issued"])
        else:  # died before its first summary: skip a margin
            s += 100_000
    return s


def avail_gib() -> float:
    with open("/proc/meminfo") as fh:
        return next(int(x.split()[1]) for x in fh if x.startswith("MemAvailable:")) / 2**20


def run_labels(base: str, k: int, d: int, greedy: int, seed0: int, *, fp=None, labels=None,
               games=None, poll=None, single=False):
    """Label jobs of the generator in runs/labels/<base>[.n] until their totals reach fp forward
    passes, labels or games. poll(dirs) runs E1's due look, returning its verdict or None; a final
    verdict ends the job. single: one directory, started over on the same seeds if cut short."""
    for _ in range(12):
        ds = dirs_of(base)
        t = totals(ds)
        if (fp and t["forward_passes"] >= fp) or (labels and t["labels"] >= labels) or (
                games and t["games"] >= games):
            return None
        if single and ds:
            shutil.rmtree(ds[0])
            ds, t = [], totals([])
        while avail_gib() < 40:
            time.sleep(300)
        r = RUNS / "labels" / (base if not ds else f"{base}.{len(ds) + 1}")
        args = [PY, X / "label_run.py", "--run", r, "--init", GEN, "--refresh-table", "--extend-sets",
                "M20", "--mix-sets", "M20", "--mix-share", "0.25", "--pool", "verified", "--infer-bf16",
                "--workers", 10, "--slots", 32, "--groups", 2, "--bucket-ratio", 100, "--serve-wait", 5,
                "--mem-floor-gib", 15, "--progress-every", 120, "--label-k", k, "--label-d", d,
                "--label-greedy", greedy, "--seed0", next_seed(ds, seed0),
                "--label-fp", fp - t["forward_passes"] if fp else 1e12]
        if labels:
            args += ["--max-games", math.ceil((labels - t["labels"]) / 3.9) + 50]
        if games:
            args += ["--max-games", games - t["games"]]
        log(f"label job {r.name} (k {k}, d {d}, greedy {greedy}) from seed {next_seed(ds, seed0) + 1}")
        with open(f"{r}.out", "a") as fo:
            p = subprocess.Popen([str(a) for a in args], cwd=LAB, stdout=fo,
                                 stderr=subprocess.STDOUT, env={**os.environ, "PYTHONPATH": str(LAB)})
        while True:
            ended = p.poll() is not None
            v = poll(dirs_of(base)) if poll else None
            if v in FINAL:
                if not ended:
                    p.terminate()
                    p.wait()
                return v
            if ended and v is None:
                break
            if not ended:
                time.sleep(30)
        log(f"label job {r.name} ended ({p.returncode}): {totals([r])}")
        time.sleep(60)
    raise RuntimeError(f"{base}: 12 jobs without reaching the target")


def e1(cfg: str) -> None:
    """One E1 configuration in looks of 2.65M forward passes (186 §2), to a final verdict."""
    k, d, greedy, seed0 = E1[cfg]
    f = Q / f"e1_{cfg}.looks"

    def rows() -> list[dict]:
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []

    def max_looks(rs: list[dict]) -> int:
        return 8 if any(r["verdict"] == "gray: extension" for r in rs) else 4

    def poll(ds: list[Path]):
        rs = rows()
        look, m = len(rs) + 1, max_looks(rs)
        if look > m or totals(ds)["forward_passes"] < look * LOOK:
            return None
        out = Q / f"e1_{cfg}_look{look}.json"
        run([PY, X / "e1_instrument.py", GEN, *ds, "--K", 16, "--out", out], Q / f"e1_{cfg}_look{look}.log")
        res = json.loads(out.read_text())
        v = decide(res, look, m)
        res["look"], res["verdict"] = look, v
        out.write_text(json.dumps(res, indent=1) + "\n")
        row = {"look": look, "verdict": v, "labels": res["labels"], "forward_passes": res["forward_passes"],
               "B_star_fp": res["label"].get("B_star_fp"), "bounds_fp": res["bounds_fp"],
               "signal_z": res["label"]["signal_z"], "placebo_z": res["placebo"]["signal_z"]}
        with f.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        log(f"E1 {cfg} look {look}: {json.dumps(row)}")
        return v

    for _ in range(4):
        rs = rows()
        if rs and rs[-1]["verdict"] in FINAL:
            return
        run_labels(f"e1_{cfg}", k, d, greedy, seed0, fp=max_looks(rs) * LOOK, poll=poll)
    raise RuntimeError(f"E1 {cfg}: no verdict")


def last_look(cfg: str) -> dict:
    rows = (Q / f"e1_{cfg}.looks").read_text().splitlines()
    return json.loads((Q / f"e1_{cfg}_look{len(rows)}.json").read_text())


def e3_cfg() -> str:
    """E3's configuration (186 §5), fixed at its first use."""
    f = Q / "e3_config.json"
    if not f.exists():
        final = {c: last_look(c) for c in E1 if (Q / f"e1_{c}.looks").exists()}
        passed = sorted((r["label"]["B_star_fp"], c) for c, r in final.items() if r["verdict"].startswith("pass"))
        cfg = "A" if "A" in [c for _, c in passed] else passed[0][1] if passed else "A"
        f.write_text(json.dumps({"config": cfg, "passed": [c for _, c in passed],
                                 "verdicts": {c: r["verdict"] for c, r in final.items()}}) + "\n")
        log(f"E3 configuration: {f.read_text().strip()}")
    return json.loads(f.read_text())["config"]


def e3_dirs() -> list[Path]:
    return dirs_of(f"e1_{e3_cfg()}") + dirs_of(f"e3_{e3_cfg()}")


def distill(out: str, sizes: str, dirs: list[Path]) -> None:
    """V: the per-future variance of result differences at the configuration's last look."""
    v = last_look(e3_cfg())["per_future"]["var_diff"]
    run([PY, X / "e3_distill.py", GEN, RUNS / "labels" / out, sizes, v, *dirs], Q / f"{out}.log")


def regret(apps: list[Path], name: str) -> None:
    run([PY, X / "e3_regret.py", RUNS / "labels/e3_regret", GEN, *apps, "--out", Q / f"{name}.json"],
        Q / f"{name}.log")


def gain(app: Path, name: str) -> None:
    """app against the generator, greedy, on the 450 standard evaluation deals, seats swapped."""
    r = RUNS / "selfplay" / name
    shutil.rmtree(r, ignore_errors=True)
    run([PY, "-m", "tools.selfplay.learner", "--run", r, "--init", app, "--opp-ckpt", GEN, "--eval-only",
         "--eval-opponents", "snap:opp", "--eval-deals", 450, "--pool", "verified", "--infer-bf16",
         "--workers", 10, "--mem-floor-gib", 15], Q / f"{name}.log")


def sim_lane() -> None:
    def ck(a):
        return RUNS / f"simulator/e0_sim_{a}.pt"

    def ev(a):
        return RUNS / f"simulator/e0_eval_{a}.npz"

    for a in ("nowin", "win"):
        step(f"bench_{a}", lambda a=a: run([PY, SX / "e0_bench_cost.py", ck(a), CAP], Q / f"e0_bench_{a}.json", SIM))
    for a in ("nowin", "win"):
        step(f"eval_{a}", lambda a=a: run([PY, "-m", "tools.selfplay.simulator", "eval", "--data", CAP,
                                           "--ckpt", ck(a), "--out", ev(a)], Q / f"e0_eval_{a}.log", SIM))
    step("score", lambda: run([PY, SX / "e0_score_e0.py", ev("nowin"), ev("win")], Q / "e0_score.json", SIM),
         ("eval_nowin", "eval_win"))
    if not (Q / "sim/score.done").exists():
        return
    gate = json.loads((Q / "e0_score.json").read_text())["gate"]
    log(f"E0 gate: {json.dumps(gate)}")
    kept = "win" if gate["window kept (mid ratio window/none <= 0.95)"] else "nowin"
    step("consistency", lambda: run([PY, SX / "e0_consistency.py", ck(kept), 2000, 64, CAP],
                                    Q / "e0_consistency.json", SIM))
    step("next_card", lambda: run([PY, SX / "e0_next_card.py", ck(kept), CAP], Q / "e0_next_card.json", SIM))
    eps = sorted(RUNS.glob(f"simulator/e0_sim_{kept}_ep*.pt"))
    step("epoch_curve", lambda: run([PY, SX / "e0_epoch_curve.py", CAP, *eps], Q / "e0_epoch_curve.json", SIM))


def labels_lane() -> None:
    t0 = time.time()
    while not any((Q / f"sim/bench_win.{x}").exists() for x in ("done", "failed")) and time.time() - t0 < 3600:
        time.sleep(60)  # the simulator's cost bench wants a quiet GPU
    for c in E1:
        step(f"e1_{c}", lambda c=c: e1(c))

    def labels_of(base: str, seed0: int, **kw):
        k, d, greedy, _ = E1[e3_cfg()]
        return run_labels(base, k if base != "e3_regret" else 8, d if base != "e3_regret" else 4, greedy,
                          seed0, **kw)

    step("e3_labels", lambda: labels_of(f"e3_{e3_cfg()}", 33_000_000,
                                        labels=100_000 - totals(dirs_of(f"e1_{e3_cfg()}"))["labels"]))
    step("e3_regret_labels", lambda: labels_of("e3_regret", 34_000_000, games=525, single=True))
    apps = [RUNS / f"labels/e3_app/app_{n}.pt" for n in (10000, 30000, 100000)]
    step("e3_distill", lambda: distill("e3_app", "10000,30000,100000", e3_dirs()), ("e3_labels",))
    step("e3_regret", lambda: regret(apps, "e3_regret"), ("e3_distill", "e3_regret_labels"))
    step("e3_gain", lambda: gain(apps[-1], "e3_gain"), ("e3_distill",))
    for n in (300_000, 600_000, 1_000_000):  # exploratory: does distillation gain grow with labels?
        if shutil.disk_usage(RUNS).free < 200e9:
            log("under 200 GB free: the label scaling stops")
            return
        app = RUNS / f"labels/scale_{n}/app_{n}.pt"
        step(f"bank_{n}", lambda n=n: labels_of(f"bank_{e3_cfg()}", 35_000_000,
                                                labels=n - totals(e3_dirs())["labels"]), ("e3_labels",))
        step(f"distill_{n}", lambda n=n: distill(f"scale_{n}", str(n), e3_dirs() + dirs_of(f"bank_{e3_cfg()}")),
             (f"bank_{n}",))
        step(f"regret_{n}", lambda n=n, app=app: regret([app], f"regret_{n}"), (f"distill_{n}", "e3_regret_labels"))
        step(f"gain_{n}", lambda n=n, app=app: gain(app, f"scale_gain_{n}"), (f"distill_{n}",))


def main() -> None:
    (Q / LANE).mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "-C", str(X), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False)
    log(f"lane {LANE} up, code {head.stdout.strip()}")
    {"sim": sim_lane, "labels": labels_lane}[LANE]()
    log(f"lane {LANE}: queue finished")


if __name__ == "__main__":
    main()
