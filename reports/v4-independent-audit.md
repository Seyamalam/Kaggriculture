# V4 independent readiness audit

Independent reviewer: GPT-5.6 Sol, extra-high reasoning

Verdict: **do not submit V4**. Confidence: **98%**.

## Decisive stress result

The reviewer replayed all downloaded server episodes through the pinned engine
and reproduced their rewards exactly. It then replaced v1 with V4 while driving
the 62,006-point ladder opponent from its recorded action trace:

| V4 seat | V4 coins | Trace-opponent coins | Result |
|---:|---:|---:|---|
| 0 | 54,098 | 61,813 | loss |
| 1 | 54,307 | 65,997 | loss |

The trace is open-loop and specific to one environment path, so it is a stress
test rather than a faithful adaptive policy. Nevertheless, two decisive losses
directly refute submission readiness.

## Why the 241/250 local gate was insufficient

- Three opponents responsible for 150 perfect wins averaged only approximately
  8.6k, 10.7k, and 35.3k coins.
- V3 and V4 are highly correlated policies rather than independent strategies.
- The first multi-opponent gate reused the same environmental seed block for
  every opponent.
- A pooled Wilson interval treated correlated seat pairs and repeated seed
  blocks as independent.
- Aggregate thresholds allowed easy-opponent wins to compensate for weakness
  against the strongest policy.

## Required gate before submission

- Freeze the candidate hash before selecting holdout seeds.
- Use at least three independent strong opponents averaging at least 50k on
  unseen seeds.
- Run 100 unseen seeds in both seats per opponent: at least 600 episodes.
- Require separately for every opponent:
  - at least 60% episode wins;
  - Wilson 95% lower bound above 50%;
  - at least 55% wins in each seat;
  - positive paired margin in both halves of the seed block.
- Win both seats against the 62k replay-trace stress case.
- Require zero invalid episodes, fallbacks, detected no-ops, animal escapes,
  capacity loss, or terminal value.
- Keep p99 action time below 50 ms.

V4 is mechanically strong and fast, but its opponent pool does not establish a
likely good ladder rating. No Kaggle submission was made.
