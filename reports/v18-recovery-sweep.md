# V18 demand-recovery release gate

Date: 2026-08-05  
Engine: `kaggle-environments==1.32.4`  
V7 baseline SHA-256: `603175d39f2857cbd618dc8f5ac9411e9fd234e3142777ec203342172f05a50e`  
V18 release SHA-256: `3068347896710078b93f705cd2f46986033d7132fa426e68bd8cfb93756fb436`

## Decision

Promote V18 and make one monitored Kaggle submission. V18 materially clears
the strong-meta, adaptive-mirror, fresh-holdout, legality, and standalone gates.
It is not claimed to solve every public policy: one fresh rank-18 trace remains
a repeatable counterexample and is deliberately left untouched after holdout.

## Causal diagnosis

V7's first 55 public matches showed that 16 of 19 losses came from opponents
with essentially the same physical farm. About 94% of the explained loss was
price capture on milk, wool, and strawberry. Engine-exact oracle audits then
showed that perfect same-turn SELL ordering could recover only hundreds of
coins; the missing action class was across-turn sale timing.

Town demand is applied after action steps divisible by four. Observation steps
where `step % 4 == 1` are therefore the first opportunity to use the recovered
quote. V18 starts on day 12, projects legal same-turn shed deposits and pickups,
and prepends uncovered premium sales only when that product was just consumed.
The quantity is capped as if a rival sells one matching unit in every lockstep
round, stopping before the modeled quote reaches the $1 floor. The physical
route and every original market order remain intact; original market orders are
an exact suffix, although their absolute queue indices intentionally move later.

## Iteration evidence

| Candidate | Principal change | Strong result | Decision |
|---|---|---:|---|
| V11 | Stateful within-turn cadence ranker | Top five unchanged at 1-9 | Reject |
| V12 | Unconditional post-demand inventory sweep | Top 10: 50-10, +987 mean | Continue |
| V13 | Demand-matched products | Top 10: 49-11, +1,043 | Continue |
| V15 | Own-seller non-floor cap | 24/25 paired mirrors, +2,517 | Continue |
| V16 | Append additions after original orders | Top five: 5-5, +93 | Reject |
| V17 | Day-12 onset | 24/25 paired mirrors, +2,694 | Continue |
| V18 | Matched-rival cap plus day-12 onset | Top 10: 50-10, +1,254 | Promote |

The append control is important: merely liquidating more inventory is not the
result. Early market denial is the mechanism. Phase controls confirm the engine
boundary rather than a generic periodic effect:

| Trigger phase | Top-five W-L | Mean margin |
|---:|---:|---:|
| `step % 4 == 0` | 0-10 | -3,067 |
| `step % 4 == 1` | 9-1 | +1,888 |
| `step % 4 == 2` | 4-6 | -383 |
| `step % 4 == 3` | 2-8 | -1,261 |

Day 8, 10, 12, and 14 all produced 9-1 on the same top-five corpus. Their mean
margins were +1,888, +1,888, +1,963, and +1,913, so day 12 sits inside a stable
plateau rather than being an isolated best cell.

## Final release gates

### Adaptive paired mirrors

The exact standalone artifact played 200 disjoint seeds twice, once from each
seat, against V7.

| Seed block | Episode W-L | Paired W-L | Mean paired margin |
|---:|---:|---:|---:|
| 20261301-20261350 | 83-17 | 46-4 | +2,947 |
| 20261401-20261450 | 82-18 | 45-5 | +2,848 |
| 20261501-20261550 | 76-24 | 46-4 | +2,590 |
| 20261601-20261650 | 79-21 | 40-10 | +2,566 |
| **Combined** | **320-80** | **177-23** | **+2,738** |

Every block and both runtime seats were positive. No episode was invalid and no
cash-collapse or preventable-weed diagnostic appeared.

### Leader replay traces

On the 30-trace top-10 development corpus, exact V7 was 2-58 with -3,926 mean
margin. V18 was 50-10 with +1,254 mean. All ten teams improved in aggregate.

The one-shot post-freeze live top-20 capture used corpus manifest
`ad676589fc1113758f884b0454ba8709582f50b3db7deb29a93839e709875d15`.
V18 was 31-9 with +1,155 mean margin and zero invalid/errors. Ranks 11-20,
which were not used during design, were 16-4 with +950 mean.

The known holdout failure is Ryutogrrr at rank 18: 0-2 and -7,076 mean. No
parameter was changed after observing it.

### First 55 V7 public traces

The comparative corpus gate used identical historical traces for V7 and V18,
both runtime seats, and manifest
`43f164f46b9bfb473563b6a955434883f497f958ed3112052fac0f4e328aef42`.

- Overall wins increased from 78/110 to 94/110.
- The 17-trace target farm improved from 6/34 wins at -3,319 mean margin to
  29/34 wins at +1,555.
- The nine-trace weak four-cow/five-sheep cluster remained 16/18 wins, versus
  17/18 for V7; mean margin fell from +6,815 to +2,948.
- Mean margin delta across the entire mixed corpus was -210 because V18 trades
  away weak-opponent blowout size for strong-meta wins. This is an explicit
  tradeoff, not hidden by the promotion decision.

## Integrity and limitations

- The final artifact is one standard-library-only Python file and was smoke
  tested from an isolated temporary working directory.
- Its default and overridden premium-market price functions match the pinned
  engine, including the floor boundary.
- Same-turn `DROP`, `PLACE`, and `PICKUP` projection, matched-rival capping,
  abstention, action preservation, and queue limits have focused tests.
- Pre-commit runs the full local test suite; no GitHub CI is configured.
- Replay-trace opponents are open-loop after divergence. They are adversarial
  regression evidence, not execution of private source or an estimate of live
  Bradley-Terry probability. The 200 adaptive mirrors and one-shot live holdout
  are the stronger release evidence.
- Most of the strong-trace margin gain is opponent revenue denial rather than
  higher absolute V18 bank. A live submission must therefore be monitored for
  opponents that reschedule after observing the same public market state.

