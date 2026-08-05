# V19 WOOL floor screen

## Hypothesis

V18's remaining Ryutogrrr loss was partly caused by selling WOOL below its
engine base price. The frozen V19 experiment changed only the recovery overlay:
new WOOL units required a modeled matched-rival marginal quote of at least
$200. Other products and the underlying farm policy remained exact V18.

Candidate: `agents/candidate_v19_wool_floor.py`

## Diagnostic traces

- Ryutogrrr, both seats: +2,384.5 mean candidate-minus-V18 margin, with both
  seats positive (+2,417 and +2,352).
- sash, both seats: -40 mean, with both seats at -40.

These results reproduce the independent audit's causal estimate but do not
justify promotion from two traces.

## Frozen cluster rejection gate

The next screen replayed V19 and V18 in both seats against 26 immutable traces:
17 from V18's core eight-cow/five-sheep target cluster and nine from the weaker
four-cow/five-sheep cluster. All 52 comparisons were valid.

| Cluster | Traces | Comparisons + / = / - | Mean delta |
|---|---:|---:|---:|
| 8 cow / 5 sheep | 17 | 6 / 20 / 8 | -417.7 |
| 4 cow / 5 sheep | 9 | 6 / 12 / 0 | +638.1 |
| Combined | 26 | 12 / 32 / 8 | -52.2 |

The worst strong-cluster regressions were -4,825 and -3,567. That violates the
predeclared requirement to preserve V18's main denial wins, so the global WOOL
floor is rejected and must not replace `main.py` or consume a Kaggle submission.

The failed experiment remains reproducible as a research artifact. The next
step is executed-sale and realized-revenue attribution before testing a more
selective policy.
