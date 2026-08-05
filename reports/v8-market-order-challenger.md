# V8 market-order challenger audit

Date: 2026-08-05

Candidate: `agents/candidate_v8_market_order.py`

Baseline: `agents/candidate_v7_public_v18.py` (C20 exact public V18 plus the
existing C17/C18 safety and entrypoint fixes)

Status: **retain as an unpromoted challenger; do not change `main.py` and do
not submit from this result alone.**

## Engine finding

Kaggriculture processes both players' market queues by order index.  At one
index it quotes both players from the same pre-commit inventory, commits both,
then refreshes prices.  Equal-product sales in the same slot therefore receive
the same quotes; a sale in an earlier slot receives the undepressed quote and
can reduce a later rival quote.

V18 selects a complete market expert once per day.  Earlier broad overlays
changed cash by only a few dollars, but that was enough to perturb a later
day's state-distance gate and select a different expert.  This is why a
locally sensible all-game sell-first transform was not safe.

## Bounded overlay

The C21 overlay has five hard boundaries:

1. It runs only on the final day (`696 <= step < 718`), after the last future
   daily expert selection, and excludes the C17 terminal liquidation.
2. It requires a congested queue: at least eight orders and at least three
   premium-product sales.
3. It only permutes existing non-WHEAT/non-FERTILIZER `SELL` orders among
   their existing slots.
4. WHEAT, FERTILIZER, every non-sale order, quantities, farmer actions, and
   hand actions are unchanged.
5. It abstains unless the proposed lead product has price above the floor and
   at least 2.0 units of visible opponent farm exposure.

Eligible orders are stably ranked by visible planned sale value
(`current_price * quantity`).  Public exposure corroborates collision risk;
it is not treated as knowledge of private inventory.

## Rejected wider variants

| Variant | Direct V7 screen | Savko trace delta | Decision |
|---|---:|---:|---|
| All-game stable sell-first | +2,366.5 mean over 4 pairs | -74 per seat | Reject: daily-gate feedback |
| All-game price/quantity SELL-slot ranker | +2,225 mean over 4 pairs | -26 per seat | Reject: trace regression |
| Final-day ungated public-pipeline ranker | 17 W / 0 T / 3 L, mean -171.15 over 20 pairs | +8 per seat | Reject: rare large mirror losses |

These screens are diagnostic ablations, not evidence for promotion.

## Exact-V7 paired mirror gate

Each seed was played twice with seats swapped.  Results below use the packaged
candidate file rather than an in-memory wrapper.

| Base seed | Pairs | Paired W/T/L | Mean paired margin |
|---:|---:|---:|---:|
| 20260820 | 30 | 13 / 17 / 0 | +7.03 |
| 20260920 | 30 | 12 / 18 / 0 | +6.33 |
| 20261020 | 30 | 15 / 15 / 0 | +12.87 |
| 20261120 | 30 | 16 / 14 / 0 | +19.43 |
| **Aggregate** | **120** | **56 / 64 / 0** | **+11.42** |

The overlay is non-negative in all 120 paired mirrors and positive in every
independent block.  This clears the narrow exact-V7 safety comparison, but
the economic effect is only about eleven dollars per two-game pair.

## Public-meta top-trace gate

Open-loop replay trace: episode 89986956, recorded Savko actions.  This is a
stress test, not a faithful adaptive reconstruction.

| Candidate seat | Policy | Candidate | Trace | Margin |
|---:|---|---:|---:|---:|
| 0 | exact V7 | 117,493 | 123,418 | -5,925 |
| 0 | C21 challenger | 117,498 | 123,415 | -5,917 |
| 1 | exact V7 | 117,130 | 123,677 | -6,547 |
| 1 | C21 challenger | 117,135 | 123,674 | -6,539 |

C21 improves the margin by eight dollars in each seat (candidate +5, trace
-3), but it still loses the trace by roughly six thousand.  Physical action
diagnostics are unchanged because C21 does not touch physical actions.

## Recommendation

Do not promote or submit C21 yet.  It is a clean, self-contained challenger
and a useful proof that bounded final-day collision ordering can add
deterministic value without mirror losses.  Its measured gain is far too small
to explain the public-score gap, and the strongest available top trace still
wins both seats decisively.  A future promotion should require a materially
larger gain against independent adaptive public opponents, not further tuning
to episode 89986956.
