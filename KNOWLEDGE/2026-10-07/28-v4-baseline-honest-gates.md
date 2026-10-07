# 28 — v4 baseline sweep under honest gates (2026-10-07 09:41, cause complete 442.6)

51 eval items, 104 train gold lines, both-statistics gate (iid AND card-cluster bootstrap >3SE).

| arm | params | acc | iid | bootstrap | verdict |
|---|---|---|---|---|---|
| S0 | 0.17M | 0.686 | +5.16 | +3.85 | PASS |
| S1 | 0.63M | 0.686 | +5.16 | +3.84 | PASS |
| S2 | 1.77M | 0.667 | +4.87 | +3.51 | PASS |
| S3 | 5.30M | 0.686 | +5.16 | +3.85 | PASS |
| S4 | 35.1M | **0.726** | **+5.75** | **+4.56** | **PASS (best)** |

First time the LARGEST model leads (37/51 vs 35/51) — with corpus volume the ranking is
finally in the expected direction; owner's volume curve now reads: 75 lines -> big models
collapse; 153 -> tie; 155+protection-triage -> big leads. Crossover keeps moving right.
Ops: curve builder fixed to consume bootstrap fields (gate_pass was iid-only — bc3-style
arms could have misreported PASS there); rebuilt from reports (no retrain).
Reference: v4-archived bc3 arms remain NULL under both stats.
