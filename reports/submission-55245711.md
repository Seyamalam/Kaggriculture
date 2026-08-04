# Kaggle submission 55245711

- File: `main.py`
- SHA-256: `04870c4342d289992cea2a5e3085588708852686eb720a090249ae2a705a3e24`
- Description: `deterministic planner v1 04870c43`
- Submitted: 2026-08-04 16:55:22.440000 (Kaggle API timestamp)
- Submission status: `COMPLETE`
- Initial public score: `600.0`
- Public score after first ladder episode: `676.3`
- Public score after three ladder episodes: `511.8`
- Daily submission slots remaining immediately after upload: 4

## Validation episode

- Episode ID: `89974785`
- Type: `EPISODE_TYPE_VALIDATION`
- State: `COMPLETED`
- Runtime configuration: 720 steps, 10×10 board, $3,000 starting money, 100-item shed, 10 market orders/turn, 1-second action timeout
- Self-play final rewards: 27,202 and 28,227
- Both agents: `DONE`
- Agent 0 log entries: 719
- Nonempty stdout/stderr entries: 0 / 0
- Server mean action duration: 0.000635 seconds
- Server maximum action duration including initial import: 0.028855 seconds

## First public ladder episode

- Episode ID: `89975326`
- Opponent: `yankang_XZK`
- Seed: `58766750`
- Agent reward: 28,848
- Opponent reward: 21,140
- Result: win
- Updated public score: 676.3

## Subsequent public ladder episodes

| Episode | Opponent | Agent coins | Opponent coins | Result |
|---:|---|---:|---:|---|
| `89975956` | Aromal vK | 24,965 | 62,006 | loss |
| `89976616` | Vignesh Murugan | 32,762 | 52,983 | loss |

Both losses completed normally. Replay inspection found no illegal actions, but v1 used no livestock or fertilizer and ended with economically material unused seeds. Its authenticated live score was `511.8` at 2026-08-04T23:18:09+06:00. The submission remains a plumbing baseline, not a competitive champion.
