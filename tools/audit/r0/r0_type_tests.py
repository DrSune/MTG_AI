"""Refine test-site typing: is the `.zone` receiver a Selector or an FAtom?
Look back up to 12 lines for an isinstance/assert binding of the receiver."""

import json
import os
import re
import sys
from collections import Counter

ROOT = "/home/sune/Desktop/MTG_AI"
d = json.load(open("/tmp/opencode/r0_scan.json"))
sites = [a for a in d["attrs"] if a["test"] == "test" and not a["called"]]

SEL_RE = None
cache = {}


def recv_last(recv):
    r = recv.replace(" ", "")
    if r.startswith("_pairs(") or "_pairs(" in r:
        return r.split(".")[-1]
    return r.split(".")[-1]


def classify(a):
    path = os.path.join(ROOT, a["file"])
    if path not in cache:
        cache[path] = open(path, encoding="utf-8").read().splitlines()
    lines = cache[path]
    name = recv_last(a["recv"])
    lo = max(0, a["line"] - 13)
    ctx = "\n".join(lines[lo : a["line"]])
    # nearest binding of the receiver name, searching backwards
    pats = [
        (rf"isinstance\(\s*{name}\s*,\s*Selector\)", "SELECTOR"),
        (rf"isinstance\(\s*{name}\s*,\s*FAtom\)", "FATOM"),
        (rf"isinstance\(\s*{name}\s*,\s*at\.Selector\)", "SELECTOR"),
        (rf"{name}\s*=\s*_*a?s?_?selector\(", "SELECTOR"),
        (rf"{name}\s*=\s*_as_selector\(", "SELECTOR"),
        (rf"{name}\s*=\s*.*\.args\.get\(", "SELECTOR"),
        (rf"{name}\s*=\s*_selector\(", "SELECTOR"),
        (rf"{name}\s*=\s*_pairs\(", "SELECTOR"),
        (rf"{name}\s*=\s*.*\.target\b", "SELECTOR?"),
        (rf"{name}\s*=\s*.*\.selector\b", "SELECTOR"),
        (rf"{name}\s*=\s*by_pred\[", "FATOM"),
        (rf"{name}\s*=\s*.*\.condition\b", "FATOM"),
        (rf"{name}\s*=\s*.*\.pred\.inner\b", "FATOM"),
        (rf"{name}\s*=\s*.*\.zone\b", "ZONE"),
        (rf"{name}\s*=\s*_as_fatom\(", "FATOM"),
        (rf"{name}\s*=\s*.*\.selector\b", "SELECTOR"),
        (rf"{name}\.selector\b", "SELECTOR"),
        (rf"{name}\s*=\s*.*CostDiscard", "SELECTOR"),
        (rf"{name}\s*=\s*_as_cost_discard\(", "SELECTOR"),
        (rf"_pairs\([^)]*\)\[['\"]", "SELECTOR"),
        (rf"{name}\.target\b", "SELECTOR"),
        (rf"{name}\s*=\s*.*\[FAtomPred\.", "FATOM"),
    ]
    best = None
    bestpos = -1
    for pat, kind in pats:
        for m in re.finditer(pat, ctx):
            if m.start() > bestpos:
                bestpos, best = m.start(), kind
    if best is None:
        # helper-call chains like _looked_top_library(), _cast_top_library()
        if "_selector" in a["recv"] or "library()" in a["recv"]:
            return "SELECTOR"
        return "UNKNOWN"
    return best


res = collections = Counter()
unknown = []
for a in sites:
    k = classify(a)
    a["recv_kind"] = k
    collections[k] += 1
    if k in ("UNKNOWN", "SELECTOR?", "ZONE"):
        unknown.append(a)
print(collections)
for a in unknown:
    print(
        f"  {a['file'].split('/')[-1]}:{a['line']} [{a['attr']}|{a['recv']}]"
        f" {a['recv_kind']} :: {' '.join(a['snippet'].split())[:80]}"
    )
json.dump(sites, open("/tmp/opencode/r0_test_sites_typed.json", "w"), indent=1)
