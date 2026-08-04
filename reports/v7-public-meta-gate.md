# V7 public-meta reset

Status: **unpromoted challenger**. V7 replaces incremental V6 tuning with an
exact, attributed copy of the public Apache-2.0 V18/C20 policy. `main.py` still
contains the submitted V6 policy until the independent release gate completes.

## Why the reset was necessary

The first V6 public episode ended at 54,684 coins and raised its initial rating
from 600.0 to 704.2. In eight sampled top-vs-top public replays, 16 outcomes
ranged from 93,434 to 160,756 coins, with mean 120,833 and median 121,865.

Those leaders execute near-identical V18-style routes:

- three quadrants and 13 total field units including the farmer;
- 14 pastures holding eight cows and six sheep by day 11;
- a melon/wheat opening followed by large recurring strawberry production;
- fertilizer collection plus selective crop fertilization;
- a deliberate wheat buy/feed/sell cash-flow cycle;
- route-level and market-level expert schedules selected from public state.

V6 instead ended with two quadrants, six daily hands, eight sheep, only eight
crop tiles, no fertilizer application, and 42 unlocked empty tiles. This is a
structural throughput gap, not a livestock-count tuning problem.

## Frozen candidate

- File: `agents/candidate_v7_public_v18.py`
- SHA-256: `603175d39f2857cbd618dc8f5ac9411e9fd234e3142777ec203342172f05a50e`
- Source: public C20 Exact Replication Control notebook
- License: Apache-2.0, retained per-file
- Full test suite: 31 passed

The copied candidate is byte-for-byte identical to the downloaded public
source. See `THIRD_PARTY_NOTICES.md` for attribution.

## Local challenger screen

Five fresh seed pairs were evaluated from both seats against each opponent.

| Opponent | Record | Mean V7 | Mean opponent | Mean margin |
|---|---:|---:|---:|---:|
| submitted V6 | 10–0 | 172,852 | 54,511 | +118,341 |
| animal specialist | 10–0 | 179,208 | 32,106 | +147,101 |
| crop specialist | 10–0 | 181,305 | 9,252 | +172,054 |
| diversified baseline | 10–0 | 186,146 | 9,654 | +176,492 |

Across all 40 episodes, both seats completed normally with zero preventable
weeds and zero zero-cash days. The policy intentionally leaves small amounts of
standing crop value at the season boundary; this is already dominated by its
cash advantage but remains a possible isolated follow-up ablation.

## Mirror-meta sanity check

V7 self-play over ten fresh seed pairs produced 20 banks from 96,579 to
157,829, mean 130,031 and median 129,673. Seat means were 129,682 and 130,381,
with a 4–6 win split. Mirror collision therefore does not collapse the route,
but an exact public-meta copy should be expected to win roughly half its games
against identical copies. Large wins against weak local policies do not imply a
2,900 rating by themselves.

## Remaining release gate

Before promotion or upload:

1. Independently audit exact-source integrity, licensing, runtime, state reset,
   action legality, and both-seat robustness.
2. Run a larger unseen paired-seat gate against V6 and the frozen opponent pool.
3. Replay all downloaded server-loss traces and representative top-meta traces.
4. Compare exact V7 against an independent copy of the same public V18/C20
   artifact; require mirror-scale cash and no systematic seat collapse.
5. Promote the exact audited hash only; do not hybridize the route before the
   first live measurement.

