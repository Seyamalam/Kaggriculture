# Iteration 2 ablation report

No candidate in this iteration passed the promotion gate. `main.py` remains the
exact v1 submission baseline and no Kaggle submission was made.

## Mixed-livestock candidate

`agents/candidate_v2.py` adds two geese, one cow, one sheep, fertilizer routing,
throughput-capped seeds, full-land thresholds, and up to twelve hands.

Four same-seed pairs (eight episodes) produced:

| Opponent | Episode wins | Paired wins | Mean candidate | Mean opponent | Mean episode margin |
|---|---:|---:|---:|---:|---:|
| starter | 8/8 | 4/4 | 51,701.625 | 3,470.875 | +48,230.750 |
| submitted v1 | 2/8 | 1/4 | 30,757.375 | 36,739.750 | -5,982.375 |

The candidate is mechanically valid but rejected because livestock service
overhead and conservative expansion lose to v1.

## Crop-first seed-cap prototype

A non-self-contained prototype tested a narrower seed queue, an eleven-hand
ceiling, and gated fourth-quadrant expansion. It was deleted after rejection.

Four same-seed pairs (eight episodes) produced:

| Opponent | Episode wins | Paired wins | Mean candidate | Mean opponent | Terminal seed cost total |
|---|---:|---:|---:|---:|---:|
| submitted v1 | 0/8 | 0/4 | 25,133.625 | 38,176.500 | 200 |
| crop specialist | 8/8 | 4/4 | 40,333.875 | 7,867.875 | 6,840 |
| diversified baseline | 8/8 | 4/4 | 40,329.000 | 10,297.625 | 6,920 |

Reducing the purchase queue underfilled the farm. A separate policy bug also
remains: when market conditions make a purchased seed's current score negative,
the planting scheduler refuses to use that sunk asset.

## Replay economics

The pinned engine accepts `SELL FERTILIZER`; fertilizer is a market product even
though organizer prose has described it as non-sellable. Every live animal
produces one collectible fertilizer after each day refresh. The two ladder
opponents that beat v1 realized substantial livestock and fertilizer revenue.

At base prices, the estimated full-season net value per occupied tile-day with
daily feeding, care, fertilizer collection, and liquidation is approximately:

| Animal | Net coins per tile-day |
|---|---:|
| Goose | 152 |
| Cow | 250 |
| Sheep | 282 |

The next bounded experiment is therefore sheep-only. It must first beat v1 in a
quick paired screen, then pass at least 200 paired episodes with zero escapes,
zero terminal inventory, at least 55% episode wins, and a positive lower 95%
confidence bound before it can be considered for promotion.
