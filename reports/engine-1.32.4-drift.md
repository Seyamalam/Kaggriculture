# Kaggriculture engine 1.32.4 drift

Date: 2026-08-05

The V7 server validation replay and every downloaded public replay reported
`module_version: 1.32.4`, while the repository initially pinned 1.32.3.

## Material rule change

The 1.32.4 Kaggriculture interpreter passes configured `shedCapacity` into
market commits and rejects `BUY_PRODUCT` and `BUY_ANIMAL` units when the shed is
full. Version 1.32.3 checked affordability but allowed those purchases beyond
capacity. The change is relevant to V7's high-volume wheat feed/cash-flow lane.

No other executable interpreter differences were found in the source diff; the
remaining change clarifies a market-curve comment.

## Repository correction

- Pin: `kaggle-environments==1.32.4`
- Interpreter SHA-256: `9741c0470a8db98a70644491d5121ae6295413343d1a08ef9fcee35e0b76f2c5`
- Full suite after upgrade: 39 passed

The exact saved top-five snapshot was rerun after the upgrade. Under 1.32.3 one
trace collapsed to about 20,000 coins after divergence and created a misleading
large positive outlier for V7. Under 1.32.4 the same trace remained competitive,
and the aggregate became 1 win / 9 losses, mean margin -2,469, median -2,738,
with zero invalid episodes. V8 was identical.

All future local gates must use 1.32.4 or a later version explicitly verified
against the live replay module version.
