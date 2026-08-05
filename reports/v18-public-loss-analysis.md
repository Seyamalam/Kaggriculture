# V18 public-loss analysis

## Scope

Submitted V18 (`55260568`, SHA `30683478`) opened 24-3 across its first 27
public matches and reached rating 2,053.6. Every match completed `DONE/DONE`.
The three V18 log streams for the losses had empty stdout/stderr on every turn;
maximum recorded call duration was below 0.49 seconds. These are strategic
losses, not crashes, timeouts, or illegal actions.

| Episode | Opponent | V18 seat | V18 reward | Opponent | Margin |
|---:|---|---:|---:|---:|---:|
| 90115677 | Will Rice | 1 | 138,524 | 139,119 | -595 |
| 90123236 | sash | 0 | 112,562 | 124,362 | -11,800 |
| 90123938 | yjhv buddies | 0 | 131,814 | 136,652 | -4,838 |

The replay attribution re-runs the recorded opponent actions open-loop against
the pinned engine. It is exact for the recorded schedule but cannot model how
an opponent would adapt after a counterfactual policy changes shared state.

## Checkpoint diagnosis

| Opponent | Step 289 | Step 433 | Step 577 | Step 625 | Final | Main cause |
|---|---:|---:|---:|---:|---:|---|
| Will Rice | -12 | +2,227 | +6,100 | -1,118 | -595 | Late sale timing |
| sash | -4,416 | -7,254 | -3,308 | -11,374 | -11,800 | Production scale |
| yjhv buddies | -1,730 | -1,557 | -753 | -3,077 | -4,838 | Extra sheep/WOOL supply |

### Will Rice

Both farms exposed the same eight cows, six sheep, and hand count through step
577. V18 built a 6,100-coin lead, then lost 7,218 coins of relative bank by
step 625. In the late 577:719 window it realized 50,998 from 294 premium units
while the recorded opponent realized 57,668 from 327 units. Across the complete
game their total premium revenue was essentially equal (V18 +28), leaving a
595-coin terminal loss driven by timing and smaller residual items rather than
production capacity.

V21's frozen late latch activates here because the opponent is 6,100 coins
behind at step 577. On the same recorded schedule it changes V18's margins from
-339/-595 to +3,414/+3,161 in the two runtime seats, a both-seat rescue.

### sash

sash was already 4,416 coins ahead when V18's overlay first became active. It
had seven hands versus V18's three at step 289, one additional cow, and more
melon capacity; the hand advantage grew to nine or ten through most of the
middle game. Premium sales explain about 10,618 of the 11,800 terminal gap:

| Product | V18 units / revenue | sash units / revenue | Revenue gap |
|---|---:|---:|---:|
| MILK | 200 / 33,879 | 230 / 37,262 | -3,383 |
| WOOL | 168 / 12,610 | 168 / 15,166 | -2,556 |
| STRAWBERRY | 261 / 53,726 | 268 / 54,990 | -1,264 |
| MELON | 114 / 23,722 | 126 / 27,137 | -3,415 |

V21 does not activate in V18's actual losing seat because sash remains ahead at
step 577. It leaves the -11,800 result unchanged. This is correctly outside the
late-abstention mechanism: the deficit is larger production throughput.

### yjhv buddies

The farms were close in public bank through step 577, but yjhv carried one more
sheep throughout the measured checkpoints. It ultimately sold 30 more WOOL and
eight more STRAWBERRY units. Its premium-revenue advantage was 4,821, almost
exactly the 4,838 final margin:

| Product | V18 units / revenue | yjhv units / revenue | Revenue gap |
|---|---:|---:|---:|
| MILK | 230 / 45,184 | 230 / 44,320 | +864 |
| WOOL | 138 / 18,483 | 168 / 22,998 | -4,515 |
| STRAWBERRY | 266 / 54,279 | 274 / 55,458 | -1,179 |
| MELON | 120 / 25,448 | 120 / 25,439 | +9 |

V21 does not activate because yjhv is 753 coins ahead at step 577, and both
runtime seats remain exact V18. The loss is a narrow livestock-mix disadvantage,
not late over-liquidation.

## Shared timing pattern

All three losses deteriorate in the final 577:719 window. V18 concentrates
premium sales immediately after town demand (`step % 4 == 1`); the opponents
sell more of their volume in later phases after prices recover. That timing is
harmful only when V18 has already built a large lead and future price is worth
more than further denial—the Will Rice case addressed by V21. Against sash and
yjhv, the opponent's additional production volume is the dominant cause, so
blind late abstention would not recover the losing seat.

## Disposition

No new policy work or submission is authorized from this analysis. V18 and V21
should accumulate public matches. Future research, if resumed, should treat
the two unresolved classes separately: midgame workforce/animal scale against
sash-like farms and one-sheep WOOL throughput against yjhv-like farms.
