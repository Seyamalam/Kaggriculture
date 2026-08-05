# V7 first 55 public matches

Date: 2026-08-05

Submission: `55248314`  
Artifact SHA-256: `603175d39f2857cbd618dc8f5ac9411e9fd234e3142777ec203342172f05a50e`

## Result

V7 reached a live rating of 1,881.1 after 55 completed public matches. Its
record was 36 wins, 19 losses, and no ties (65.5%). Seat balance was acceptable:
18-11 from seat 0 and 18-8 from seat 1.

| Metric | Value |
|---|---:|
| Mean bank | 135,897 |
| Median bank | 131,125 |
| Win bank mean / median | 140,646 / 139,342 |
| Loss bank mean / median | 126,899 / 130,060 |
| Mean loss margin | -4,093 |
| Median loss margin | -4,274 |
| Worst loss | -9,157 |
| Record when absolute margin <=20,000 | 24-19 |

The 12 large weak-opponent victories inflate the raw win percentage. Close
same-meta games are the relevant improvement target.

## Dominant failure cluster

Seventeen opponents finished with essentially the same public production
footprint as V7: 12 hands, three unlocked quadrants, 14 pastures, eight cows,
five surviving sheep, six strawberry tiles, and one wheat tile. V7 went **1-16**
against this cluster, which accounts for 16 of its 19 losses.

Physical work was effectively identical in losses:

| Requested operation | V7 mean | Opponent mean |
|---|---:|---:|
| Harvest | 338.0 | 337.7 |
| Care | 308.0 | 308.0 |
| Feed | 319.0 | 319.0 |
| Fertilize | 107.0 | 106.9 |
| Plant | 131.0 | 131.0 |

Executed production and sale quantities differed by only zero to three units
per product, and both sides ended with zero unsold inventory. Board throughput
and terminal liquidation are therefore not the live bottleneck.

## Economic attribution

The median losing game was even through day 10 and became permanently negative
around day 12. The mean deficit grew to -1,561 by day 18, -2,005 by day 22,
-4,850 by day 27, then recovered partly to -4,093 at the terminal boundary.

Reconstructing realized sale revenue from the replay states and pinned engine
explains about -4,309 per loss:

| Product | Mean V7 revenue deficit | Share of explained gap |
|---|---:|---:|
| Milk | -2,029 | 47% |
| Wool | -1,020 | 24% |
| Strawberry | -999 | 23% |
| Melon, fertilizer, wheat, other | -261 | 6% |

About 94% of the loss is price capture on milk, wool, and strawberry. A
same-step order-position audit corroborates this: losing opponents placed milk
sales ahead of V7 194 times, while V7 led on milk only 64 times.

## Architecture connection

V7 fixes both seats to the Mohit physical route; the embedded runtime has
`board_distance_strength=0`, so board forking is disabled. Its daily market
expert uses own money, hands, land, crops, private shed, and shared prices. It
does not include public opponent livestock/crop exposure. Strong Mohit priors
and the stay bonus selected Mohit on 238 of 240 observed seat-days in a separate
mirror audit.

This produces the correct farm but repeatedly loses price priority against
near-identical supply schedules.

## Live top-five benchmark snapshot

The new one-command benchmark selected the best active submission and newest
completed public trace for each of the current top five teams. On the same
1.32.4 engine used by the server, exact V7 won 1 of 10 both-seat simulations,
with mean margin -2,469 and median margin -2,738. It split 1-1 against the
3,092-rated leader trace and lost both seats to each of the other four traces.

V8 produced exactly the same top-five results and remains unpromoted.

## Rejected V9 expert switches

A follow-up agent reran complete-market and milk-first ablations on engine
1.32.4. Forcing Manual, Dmitry, or Lucien market schedules while retaining the
Mohit physical board lost 9,475--9,862 coins per fresh paired mirror. On a
representative nine-trace live panel, their mean margins were no better than
the Mohit control: Mohit -2,120; Manual -3,616; Dmitry -2,673; Lucien -2,189.
A day-12+ same-footprint milk-first rule scored -2,126 and also failed to
improve the control. V9 was rejected without creating a candidate or changing
`main.py`.

## Next gates

The physical route remains frozen. The next candidate must target market price
capture and pass all of these checks:

1. Improve the same-footprint replay cluster without changing quantities,
   board actions, hiring, purchases, or the wheat feed/cash-flow lane.
2. Preserve performance against the undercapitalized four-cow/five-sheep
   cluster, where V7 went 8-1.
3. Show a material paired improvement against exact V7 mirrors; an eleven-coin
   gain like V8 is insufficient.
4. Improve the exact saved top-five snapshot from both seats with zero invalid
   episodes and no single catastrophic regression.
5. Remain an unpromoted challenger until a broad independent audit passes.

The two bounded research directions are a clone-triggered premium collision
ranker for milk/wool/strawberry and an opponent-aware, day-locked market-expert
selector. No further submission is authorized by this audit alone.
