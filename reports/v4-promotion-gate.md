# V4 promotion gate

Candidate: `agents/candidate_v4_landcap.py`

V4 combines the validated four-sheep policy with a two-quadrant cap. It is not
promoted to `main.py` and has not been submitted to Kaggle.

## Gate configuration

- Engine: `kaggle-environments==1.32.3`
- Base seed: `57001`
- 25 seeds per opponent, played once in each seat
- Five opponents: submitted v1, sheep v3, crop specialist, diversified
  baseline, and animal specialist
- Total: 125 same-seed pairs / 250 episodes

## Aggregate result

| Metric | Result |
|---|---:|
| Episode wins | 241 / 250 |
| Episode win rate | 96.4% |
| Wilson 95% interval | 93.30%–98.09% |
| Paired wins | 123 / 125 |
| Mean episode margin | +22,220.47 |
| Median episode margin | +17,632 |
| Invalid episodes | 0 |

All diagnostic totals were zero: preventable weeds, capacity pressure,
zero-cash days, unsold terminal items, terminal seed cost, standing yield, and
terminal non-cash value.

## Per-opponent result

| Opponent | Episode wins | Paired wins | Mean candidate | Mean opponent | Mean margin |
|---|---:|---:|---:|---:|---:|
| submitted v1 | 43/50 | 23/25 | 41,206.34 | 37,754.70 | +3,451.64 |
| sheep v3 | 48/50 | 25/25 | 42,888.24 | 41,068.16 | +1,820.08 |
| crop specialist | 50/50 | 25/25 | 53,901.36 | 8,584.58 | +45,316.78 |
| diversified baseline | 50/50 | 25/25 | 53,698.54 | 10,744.28 | +42,954.26 |
| animal specialist | 50/50 | 25/25 | 52,854.72 | 35,295.14 | +17,559.58 |

## Decision

The original local promotion checks pass, including a positive result against
both v1 and v3. An independent readiness audit subsequently rejected this gate:
the pool is too weak/correlated and the aggregate statistics can hide failure
against a strong opponent. V4 also lost both seats to the recorded action trace
of the 62k ladder opponent. See `reports/v4-independent-audit.md` for the
replacement per-opponent gate. No submission was made.
