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
| 90111614 | Jiarui (Jerry) Cao | win | 117,813 | 114,768 | +3,045 | 1,079.3 |
| 90112297 | Enrico Ambrosio | win | 129,474 | 106,888 | +22,586 | 1,198.4 |
| 90112969 | Furina | win | 142,055 | 131,921 | +10,134 | 1,282.3 |
| 90113641 | Ayodeji | win | 153,147 | 140,240 | +12,907 | 1,393.2 |
| 90114321 | Sheep | win | 135,201 | 131,373 | +3,828 | — |
| 90115006 | Milkomeda | win | 138,644 | 124,790 | +13,854 | — |
| 90115677 | Will Rice | loss | 138,524 | 139,119 | -595 | 1,544.3 |
| 90116362 | Bocen Li | win | 181,866 | 54,228 | +127,638 | — |
| 90116405 | Amy Yuan | win | 133,583 | 129,654 | +3,929 | — |
| 90117048 | takai380 | win | 126,046 | 113,693 | +12,353 | — |
| 90117722 | Mobzya | win | 161,038 | 160,931 | +107 | 1,804.1 |
| 90118413 | 木下陽平 | win | 130,380 | 128,339 | +2,041 | — |
| 90119117 | cmxu | win | 120,643 | 110,893 | +9,750 | — |
| 90119795 | GzmCR632 | win | 116,522 | 115,588 | +934 | — |
| 90120485 | KevlarZanderChi | win | 138,368 | 137,285 | +1,083 | — |
| 90121168 | Roshan Singh | win | 141,217 | 139,272 | +1,945 | — |
| 90121857 | CROW | win | 148,645 | 147,619 | +1,026 | — |
| 90122540 | fmind | win | 144,393 | 141,446 | +2,947 | — |
| 90123236 | sash | loss | 112,562 | 124,362 | -11,800 | — |
| 90123284 | Nkosi Ndwandwe | win | 133,469 | 131,365 | +2,104 | — |
| 90123938 | yjhv buddies | loss | 131,814 | 136,652 | -4,838 | — |
| 90124623 | Sai Teja Bandaru | win | 136,232 | 135,049 | +1,183 | — |
| 90125302 | wacata | win | 138,997 | 136,775 | +2,222 | 2,053.6 |

The first 27 public episodes finished 24-3 with every episode in `DONE/DONE`
state. V18 rose from its 600 start to 2,053.6. Its losses were Will Rice by 595,
sash by 11,800, and yjhv buddies by 4,838. See
`reports/v18-public-loss-analysis.md` for the checkpoint, production, and
executed-market attribution.

The downloaded replay and logs are retained in the ignored `replays/` and
`logs/` directories for local analysis.

## Release disposition

The exact submitted artifact passed 68 repository tests, the immutable replay
corpus gates in `reports/v18-recovery-sweep.md`, and an independent GPT-5.6 Sol
extra-high audit. No further submission should be made solely in response to
the initial 600 rating. The next release requires fresh public-match evidence
or a frozen-corpus improvement that also preserves the V18 regression gates.
