# V6 release gate

Decision: **GO for one monitored progress submission**. V6 is a materially
stronger candidate than submitted v1, but this gate does not claim that it is a
leaderboard champion or final strategy.

## Frozen artifact

- Candidate: `agents/candidate_v6_adaptive_livestock.py`
- Source commit: `374b348`
- SHA-256: `1464c72bba660d5c86d9c3295c7a5c17551241c0a2cb75f53fcf1159266aadcb`
- Test suite: 29 passed
- Dependencies: Python standard library only

V6 keeps the deterministic crop and logistics planner, expands to eight safe
pasture tiles, and observes the opponent's placed livestock. It normally scales
to eight sheep. Seeing at least two opponent sheep during the early expansion
window latches a diversified four-sheep/four-cow response.

## Strict paired-seat gate

The frozen V6 artifact was compared with the stronger eight-sheep V5 candidate
over 25 seeds, swapping player seats for every seed.

| Metric | Result |
|---|---:|
| Episode record | 50 wins, 0 ties, 0 losses |
| Seat 0 / seat 1 wins | 25 / 25 |
| Mean V6 bank | 61,035.04 |
| Mean V5 bank | 51,155.38 |
| Mean episode margin | +9,879.66 |
| 95% Wilson lower bound | 0.9287 |
| First-half paired margin | +16,043.83 |
| Second-half paired margin | +23,189.00 |

All invalid-episode, preventable-weed, cash-collapse, capacity-pressure, and
terminal-waste diagnostics were zero.

## Server-loss trace stress tests

The two public losses from submission `55245711` were replayed as open-loop
opponent action traces from both seats. This checks the policy against observed
strong behavior, but it is not a substitute for live adaptive ladder play.

| Episode | Opponent archetype | Seat | V6 | Trace | Margin |
|---|---|---:|---:|---:|---:|
| `89975956` | sheep/wool-heavy | 0 | 53,154 | 39,235 | +13,919 |
| `89975956` | sheep/wool-heavy | 1 | 53,660 | 36,887 | +16,773 |
| `89976616` | cow-heavy/mixed | 0 | 57,801 | 15,181 | +42,620 |
| `89976616` | cow-heavy/mixed | 1 | 57,587 | 14,941 | +42,646 |

All four runs reached `DONE` with zero wrapper fallbacks, detected unit no-ops,
and terminal waste.

## Independent release audit

An independent GPT-5.6 Sol extra-high reviewer reproduced the gate and trace
results, checked trigger spoofing and self-containment, and measured mean agent
runtime of 0.047 ms, p99 0.070 ms, and maximum 0.088 ms against the one-second
action limit. Its verdict was GO for exactly one monitored progress submission,
with the explicit caveat that the evidence does not establish champion status.

