# V20 late-abstention screen

## Attribution

The audited replay-loss harness analyzed the five historical traces where V18
turned at least one V7 win into a loss. Across both seats, V18 was +2,095 mean
in steps 289:433, then -2,566 in 433:577 and -4,841 in 577:719. Terminal units
were unchanged; V18 mainly shifted sales earlier and reduced its own eventual
revenue while barely changing opponent revenue.

Mean own-revenue deltas were -2,353 WOOL, -1,524 MILK, -997 STRAWBERRY, and
-354 MELON. Four seats became permanently negative at checkpoint 577 and six
only at terminal checkpoint 719.

## Frozen experiment

`agents/candidate_v20_late_abstain.py` changes one V18 constant: the added
recovery sweep stops at step 577 instead of step 718. The underlying public
farm policy and its original market orders remain unchanged.

On the five harmed traces, V20 improved all 10 seats versus V18 by +3,197 mean;
the minimum improvement was +1,344 and the maximum was +5,198.

## Cluster rejection

The same 26-trace, 52-seat gate that rejected V19 then separated the effect:

| Cluster | Traces | Comparisons + / = / - | Mean delta |
|---|---:|---:|---:|
| 8 cow / 5 sheep | 17 | 2 / 0 / 32 | -3,027.7 |
| 4 cow / 5 sheep | 9 | 18 / 0 / 0 | +2,148.8 |
| Combined | 26 | 20 / 0 / 32 | -1,235.8 |

The global late cutoff is rejected: it rescues weak-supply opponents but
removes valuable denial against strong supply. It must not replace `main.py`
or consume a Kaggle submission. The result motivates only an online-safe,
late conditional abstention experiment; final farm footprints are
retrospective diagnostics and cannot be used as a live policy gate.
