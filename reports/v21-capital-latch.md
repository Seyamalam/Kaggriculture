# V21 capital-latched late abstention

## Policy change

V21 is exact V18 until observation step 577. At that checkpoint it reads the
public bank values once and latches a single decision per seat:

```text
late_abstain = opponent_money - own_money <= -5,000
```

If true, only V18's added recovery sweep is disabled through the late window;
the original V7 market orders and all farm actions remain unchanged. If false,
the policy remains exact V18. The decision resets at step zero and is never
recomputed. The -5,000 threshold was specified before the frozen distribution
audit and was not changed to the retrospectively cleaner -6,000 split.

Candidate: `agents/candidate_v21_capital_latch.py`
SHA-256: `0cd14b653102d276c4f902fa3b8c6bd81d869b8ab64c422cb881b9d2346ec639`

## Signal audit

At step 577, `opponent_money - own_money` was measured from V18's online-safe
public observation in both seats of the frozen 17 strong and nine weak traces.

| Cohort | Seats | Median | Range |
|---|---:|---:|---:|
| Strong eight-cow | 34 | -2,030 | -5,329 to +3,032 |
| Weak four-cow | 18 | -7,644 | -10,959 to -59 |

The frozen -5,000 threshold covered 16/18 weak seats with one false activation
in 34 strong seats: 94.1% activation precision and 0.951 rank AUC.

## Outcome gates

Competition rating is based on match outcomes, so promotion gates prohibit
V18 win-to-V21 loss transitions and worsened V18 non-wins. Coin margin is a
secondary safety measure; a reduced blowout that remains a buffered win does
not outweigh a rescued loss.

| Corpus | V18 wins | V21 wins | Rescued / harmed | Mean V21-V18 delta |
|---|---:|---:|---:|---:|
| Historical public55, 110 seats | 94 | 100 | 6 / 0 | +927.8 |
| Untouched live15, 30 seats | 27 | 29 | 2 / 0 | +1,083.7 |
| Frozen top20, 40 seats | 31 | 31 | 0 / 0 | -180.2 |

Historical public55 was evaluated as three non-overlapping immutable
partitions totaling 55 unique episodes and 110 comparisons. It had zero
worsened V18 non-wins, both runtime seats positive (+885.7 and +969.9), and one
negative delta that remained a +5,009 win. On live15, Will Rice changed from
both-seat losses (-339/-595) to both-seat wins (+3,414/+3,161); the only
negative deltas remained +63k/+65k wins.

On frozen top20, 38/40 seats were exact V18. The two changed seats remained
wins at +1,616 and +6,475. Win count stayed 31/40, Ryutogrrr remained 0-2, and
mean raw margin changed from +1,155 to +975.

## Adaptive response gate

Across 100 disjoint paired seeds against exact V18, with the seat order swapped
on every seed, V21 recorded two paired wins, 97 paired ties, and one paired
loss. Mean paired margin was +6.98; every 25-pair chronological block was
nonnegative. There were zero invalid episodes, zero cash-collapse days, and
zero preventable weeds. The high tie rate is expected because both policies
are identical unless the one-time late capital gate activates.

Three focused tests cover the exact threshold boundary, one-time persistence,
per-seat reset, and untouched base-action behavior. Final promotion additionally
requires an isolated single-file smoke test, full pre-commit, exact mechanical
copy to `main.py`, and an independent release audit of the copied hash.

Both independent final audits approved one monitored submission. The isolated
smoke completed both seats in `DONE` state with candidate rewards 190,266 and
196,731 against `starter`. `main.py` was promoted by exact mechanical copy and
verified byte-identical to the audited candidate hash above.
