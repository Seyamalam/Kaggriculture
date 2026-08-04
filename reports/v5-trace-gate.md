# V5 replay-trace stress gate

Candidate: `agents/candidate_v5_eight_sheep.py`

V5 expands V4 from four to eight sheep and tightens the seed pipeline. It
passed its bounded local screen but failed one of two strong replay traces and
was not submitted.

## Bounded local screen

Four same-seed pairs per opponent:

| Opponent | Episode wins | Mean candidate | Mean opponent | Mean margin |
|---|---:|---:|---:|---:|
| V4 | 8/8 | 52,156.50 | 47,516.13 | +4,640.38 |
| submitted v1 | 6/8 | 52,743.75 | 40,266.38 | +12,477.38 |
| animal specialist | 8/8 | 46,471.00 | 31,816.13 | +14,654.88 |

All diagnostics were zero, including terminal seeds and fallback count.

## Strong replay traces

The trace opponent replays recorded actions by observation step and does not
adapt after the new episode diverges. It is an adversarial stress case rather
than a reconstructed opponent or ladder estimate.

| Source episode | Trace profile | Candidate seat | Candidate | Trace | Result |
|---:|---|---:|---:|---:|---|
| `89975956` | sheep/wool-heavy | 0 | 24,723 | 34,702 | loss |
| `89975956` | sheep/wool-heavy | 1 | 24,383 | 33,081 | loss |
| `89976616` | mixed cow/sheep | 0 | 62,830 | 15,412 | win |
| `89976616` | mixed cow/sheep | 1 | 62,641 | 15,279 | win |

Every episode completed with zero detected unit no-ops, fallbacks, or terminal
waste. The failure is strategic: eight sheep plus a sheep-heavy opponent flood
the shared wool market. V6 must diversify the second four pasture slots when
public opponent state signals wool crowding, and it must pass both traces in
both seats before broader evaluation.
