# V7 public-meta reset

Status: **promoted; GO for one monitored submission**. V7 replaces incremental
V6 tuning with an exact, attributed copy of the public Apache-2.0 V18/C20
policy. `main.py` and `agents/candidate_v7_public_v18.py` are byte-identical.

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

## Extended release gate

The remaining checks were completed before promotion:

1. An independent GPT-5.6 Sol extra-high audit verified the exact source hash,
   Apache-2.0 attribution, standard-library-only runtime, state reset, action
   legality, entrypoint, and both-seat robustness. Fresh action runtime was
   0.029 ms mean, 0.033 ms p95, and 75 ms maximum under the one-second limit.
2. The extended frozen-pool gate won 200/200 episodes and 100/100 paired
   comparisons across V6 and three frozen opponent archetypes. All performance,
   seat, and half-block thresholds passed. The report's strict `overall=false`
   is solely the absolute-zero terminal-waste invariant: average terminal
   non-cash value was about 143 coins, roughly 0.08% of mean bank.
3. V7 beat both public V1 loss traces in both seats. Against Savko's current top
   open-loop trace it lost by 5,925 and 6,547 coins. This is a real warning, but
   the trace does not adapt after divergence and is not a ladder win-rate model.
4. Ten fresh mirror pairs produced 96,579--157,829 banks, mean 130,031, with no
   systematic seat collapse.
5. `main.py` was promoted wholesale at SHA-256 `603175d39f2857cbd618dc8f5ac9411e9fd234e3142777ec203342172f05a50e`.

## Newer public-anchor challenge

Two independent agents evaluated Roman Tamrazov's public Hamburger V27 notebook
before promotion. Its selected Anchor Exact policy lost 11 of 12 fresh paired
head-to-head games against V7, averaging 124,170 versus V7's 129,024. A second
four-pair run was 0--8 with a -5,721 mean margin. The anchor reduced the Savko
open-loop deficit to roughly 2,600 coins but still lost both seats. None of its
seven market/terminal overlays closed the gap; the notebook also contains an
entrypoint-selection defect for appended overlays and no explicit SPDX or
redistribution license. It was therefore rejected rather than vendored.

## Decision

Promote the exact audited V7 bytes and permit one monitored progress
submission. This is strong evidence of a major improvement over V6, not a
guarantee of a 2,900 ladder rating. Preserve the exact first live artifact so
its public matches are attributable before attempting market-order hybrids.
