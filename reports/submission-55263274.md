# Kaggle submission 55263274

## Artifact

- Kaggle description: `v21 capital latch 0cd14b65`
- Git commit: `23d9fee`
- `main.py` SHA-256: `0cd14b653102d276c4f902fa3b8c6bd81d869b8ab64c422cb881b9d2346ec639`
- Submitted: 2026-08-05 07:50:38 UTC
- Submission status: `COMPLETE`

## Validation

Kaggle validation episode `90124697` completed with both seats in `DONE`
state. Final rewards were 107,531 and 107,144, exactly matching V18 validation
self-play because neither identical policy develops the 5,000-coin late capital
gap needed to activate V21. Both agent log streams had empty stdout and stderr
on every turn.

The score shown immediately after validation was 600.0. At that time the
submission had no public matchmaking episodes; 600 is the initial rating, not
a measured public result. V18 followed the same path and subsequently rose to
2,031.8. V21 must remain under observation until scheduled public matches
accumulate.

The downloaded replay and logs are retained in the ignored `replays/` and
`logs/` directories for local analysis.

## Release disposition

The exact submitted artifact passed 77 repository tests, isolated both-seat
smoke tests, immutable historical/live/leader gates, 100 adaptive paired seeds,
and two independent final audits. No further submission should be made from
initial-rating noise or one early match.
