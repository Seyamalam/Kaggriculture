# Kaggle submission 55260568

## Artifact

- Kaggle description: `v18 demand recovery 30683478`
- Git commit: `69c64ae`
- `main.py` SHA-256: `3068347896710078b93f705cd2f46986033d7132fa426e68bd8cfb93756fb436`
- Submitted: 2026-08-05 06:14:28 UTC
- Submission status: `COMPLETE`

## Validation

Kaggle validation episode `90108384` completed with both seats in `DONE`
state. Final rewards were 107,531 and 107,144. Both agent log streams had
empty stdout and stderr on every turn.

The score shown immediately after validation was 600.0. At that time the
submission had no public matchmaking episodes; 600 was therefore the initial
rating, not a measured public win/loss result.

## Public matches

| Episode | Opponent | Result | Reward | Opponent reward | Margin | Rating after match |
|---:|---|---|---:|---:|---:|---:|
| 90108945 | RacoonTW | win | 183,352 | 34,264 | +149,088 | 696.0 |
| 90109603 | huanxian chen | win | 165,809 | 52,827 | +112,982 | — |
| 90110271 | typeIIIfairy | win | 103,151 | 81,025 | +22,126 | — |
| 90110946 | Manish Kumar | win | 133,704 | 67,798 | +65,906 | 1,014.9 |

The first four public episodes were wins with both agents in `DONE` state and
no non-empty stdout or stderr entries from V18. Four matches are still too few
for a stable comparison with established submissions, but the rating has moved
from its 600 start to 1,014.9.

The downloaded replay and logs are retained in the ignored `replays/` and
`logs/` directories for local analysis.

## Release disposition

The exact submitted artifact passed 68 repository tests, the immutable replay
corpus gates in `reports/v18-recovery-sweep.md`, and an independent GPT-5.6 Sol
extra-high audit. No further submission should be made solely in response to
the initial 600 rating. The next release requires fresh public-match evidence
or a frozen-corpus improvement that also preserves the V18 regression gates.
