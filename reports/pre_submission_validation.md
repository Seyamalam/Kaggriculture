# Pre-submission validation report

Date: 2026-08-04  
Agent: `main.py`  
SHA-256: `04870c4342d289992cea2a5e3085588708852686eb720a090249ae2a705a3e24`  
Environment: `kaggle-environments==1.32.3`  
Engine SHA-256: `2f5f94e3da0f007f6d7628e30889bd19c83716183eeaa05b4922430db5021737`

## Results

| Opponent | Starting seed | Games | Slot policy | Wins | Ties | Mean ours | Mean theirs |
|---|---:|---:|---|---:|---:|---:|---:|
| starter | 20260804 | 25 | alternate | 25 | 0 | 40,499.20 | 3,497.08 |
| random | 20260901 | 25 | alternate | 25 | 0 | 40,118.68 | 0.00 |
| mirror | 20261101 | 10 | alternate | 6 | 0 | 51,347.30 | 49,597.00 |

Across both 25-game baseline gates: zero preventable plant-to-weed transitions, zero zero-cash day boundaries, zero terminal unsold items, and no invalid episode status. The shed-pressure estimate registered 2 items in each 25-game suite; terminal liquidation still completed.

## Runtime

Measured by replaying the policy over 719 recorded observations from one full episode:

- mean: 0.092 ms/action
- p95: 0.320 ms/action
- maximum: 0.420 ms/action

The competition specification allows one second per action, leaving a wide safety margin.

## Interpretation

This is a plumbing promotion gate only. `starter` and `random` are weak and cannot estimate ladder strength. The evidence supports submitting to validate server compatibility, not treating this agent as a final competitive solution.
