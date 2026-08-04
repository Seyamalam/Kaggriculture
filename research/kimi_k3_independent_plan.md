# Kimi K3 independent Kaggriculture strategy review

Date: 2026-08-04 (Asia/Dhaka)

Status: Research only. No competition join, rule acceptance, external write, or submission was performed.

## Invocation record

OpenCode version/model discovery showed these Kimi-related model IDs:

```text
kimi-for-coding/k3
kimi-for-coding/k3-256k
kimi-for-coding/kimi-for-coding
kimi-for-coding/kimi-for-coding-highspeed
modal/moonshotai/Kimi-K3
modal/seyamalam41--ep-kimi-k3-server.us-west.modal.direct
```

The exact first-party-looking Kimi K3 ID `kimi-for-coding/k3` was selected.

The initial command was:

```bash
opencode run -m kimi-for-coding/k3 --title 'Kaggriculture independent strategy review' --format default 'You are an independent Kaggle competition strategist. Analyze the Kaggriculture competition at https://www.kaggle.com/competitions/kaggriculture/overview and the current repository at /Users/seyam/work/Kaggriculture. The repository is currently empty. Public page metadata says: Create an agent to play in this farming simulation and compete with others to maximize your income. Investigate all competition pages and any publicly accessible files or metadata you can reach, but do not submit, join, accept rules, modify files, or expose credentials. Produce a rigorous solution plan. Explicitly separate VERIFIED FACTS from INFERENCES and UNKNOWN ITEMS. Cover: task mechanics and scoring; likely data/interface shape; validation and local simulation; leakage or exploit risks; state/action representation; feature engineering; baseline and advanced modeling or planning algorithms; experiment ladder with ablations and go/no-go criteria; reproducibility; leaderboard overfitting controls; final ensemble/policy selection and submission strategy; rules/compliance checks. Because this is an agent simulation rather than standard supervised prediction, correct any inappropriate assumptions about train/test CSVs. End with ten highest-value next actions and five questions that must be answered from authenticated competition materials. Include source URLs for claims. Do not perform any external write or submission.'
```

While it ran, the organizer package appeared in the shared workspace at `data/raw/competition/{README.md,AGENTS.md}`. Kimi read those files and attempted to cross-check the public engine source. Its web fetch stalled, so that process was interrupted and the same session was continued with:

```bash
opencode run -c -m kimi-for-coding/k3 --format default 'Continue and finish now. Do not call WebFetch or use credentials. Ground the answer in data/raw/competition/README.md and data/raw/competition/AGENTS.md, which are the organizer-provided package now present. Return only the requested independent strategy review: verified mechanics, uncertainty list, leakage/exploit risks, validation protocol, policy architecture and state features, baseline-to-advanced experiment ladder with ablations and thresholds, opponent modeling, reproducibility, leaderboard controls, final policy/submission strategy, compliance checks, ten next actions, and five authenticated-material questions. Be concrete and concise enough to complete in this response. Do not edit files or submit.'
```

The completed response identified itself as `build · k3`.

## Kimi's independent findings and plan

### Verified task framing and mechanics

- This is a two-player, zero-sum `kaggle_environments` farming simulation, not a train/test CSV prediction problem. The deliverable is an `agent(obs)` in `main.py` or a permitted archive.
- Default horizon is 720 turns: 24 turns/day for 30 days. Each turn permits one farmer action, one action per hired hand, and at most ten ordered market actions.
- Each player starts with $3,000, an empty farm, and a shed holding at most 100 non-seed items. Only the NW 5x5 quadrant is initially unlocked. The public engine uses the fixed extra-land order NE ($1,000), SW ($2,000), SE ($4,000).
- The winner is the player with more banked money at season end; unsold produce has no terminal value.
- Crops and livestock differ in capital cost, first-yield time, repeat interval, labor, maximum held yield, fertilizer/care response, and exposure to decay or neglect. Two missed daily care windows turn plants into weeds or make animals escape.
- Dynamic market prices depend on shared inventory around I0=10,000 and use asymmetric resource-specific curves. Town-center and randomly unlocked shop demand drain inventory. Premium resources can crash rapidly toward the $1 floor under oversupply.
- Opponent farm, money, market, and town are public; opponent shed, seeds, and carried inventory are hidden. The problem is therefore partially observable but strategically rich in opponent production inference.
- Invalid actions are silent no-ops; extra market orders are silently dropped; simultaneous PLANT actions exceeding owned seed count can invalidate all those plants. These are major correctness hazards.
- Public environment configuration specifies a one-second action timeout and 60 seconds of overage time.
- Built-in opponents are `pass`, `random`, and `starter`.

The organizer README says fed-and-cared days add `+2` to an animal's pending care bank. Current public `kaggriculture.py` increments it by `+1`. This is a confirmed documentation/source discrepancy, not a settled mechanic; identify the exact server package/version and test it empirically.

### Unknowns that must remain explicit

1. Exact leaderboard rating, matchmaking, tie handling, and final/private evaluation procedure.
2. Submission limits and whether hidden evaluation changes seeds or configuration such as `marketParams`.
3. Exact server-side `kaggle-environments` version, especially the care-bonus behavior.
4. Runtime, memory, dependency, archive-size, and network limitations beyond the public per-action timeout.
5. Whether deliberate price-floor denial or other adversarial market manipulation is restricted by competition-specific rules.

### Leakage and exploit-risk audit

- There is no classic target leakage. The analogous risks are simulator/source-version mismatch, hidden seed leakage, replay overfitting, and relying on implementation bugs.
- Exact use of the published market equation is likely intended. Accessing unobserved RNG state, opponent process/files, or timing side channels would not be.
- Sales at the $1 floor reportedly do not restock market inventory, making price denial possible. Treat it as an adversarial strategy only after rules review; do not make the core agent depend on a questionable exploit.
- Never emit more than ten market orders or rely on illegal actions. Centralize precondition and seed accounting so simultaneous hands cannot trigger the PLANT all-or-nothing failure.
- Never infer performance from a single seed, one player slot, or a single opponent. Random weeds, shop sequence, and market interaction can otherwise create misleading wins.

### Validation protocol

1. Pin Python and `kaggle-environments`, record its version and hash the installed `kaggriculture.py`. Compare it with the organizer package and server behavior.
2. Build direct mechanic tests for: care-bank value, weed/escape timers, plant decay cadence, shed overflow, Fibonacci hire prices, market floor behavior, post-buy quoting, simultaneous seed accounting, market-order cap, shop timing, and end-of-day inventory drops.
3. Build a headless batch harness that accepts explicit seeds and configurations; run every pairing in both player slots.
4. For each policy pairing, use at least 500 episodes for promotion decisions. Record mean/median final money, win rate, confidence interval, tail losses, seed sensitivity, and slot effect.
5. Log diagnostics beyond reward: income by product, market price/inventory paths, water/feed deadline misses, weeds, escapes, shed overflow, dead travel time, unused cash, and end-of-season unsold goods.
6. Promote a challenger only when its confidence interval clears the prior champion on a frozen opponent pool and it does not regress against simple baselines.

### Policy architecture

Kimi recommends a hierarchical deterministic planner before deep reinforcement learning because the joint action space is large, exact mechanics are known, the observation is structured, and the per-turn time limit is strict.

The strategic day-level layer should choose:

- crop/animal portfolio and desired tile counts;
- capital allocation among seed/livestock, structures, fertilizer, hired labor, and land;
- product mix based on season remaining, observed opponent capacity, shop demand, current inventory, and marginal price impact;
- a liquidation schedule that assigns zero value to terminal inventory.

The tactical turn-level layer should turn state into deadline tasks:

1. Prevent imminent animal escape or crop loss.
2. Harvest before yield decay or storage overflow.
3. Water profitable one-time bonus windows and ongoing fertilized production days.
4. Plant early enough to finish before season end.
5. Collect and use fertilizer only when net value exceeds its labor/opportunity cost.
6. Perform shed pickup/drop/placement logistics.
7. Clear weeds when the tile has positive planned value.

Assign farmer/hands to tasks using greedy minimum-cost matching first, with Manhattan travel and task deadline/slack in the cost. Hire until marginal task value falls below the next Fibonacci hire price plus congestion/logistics cost.

The market layer should analytically simulate marginal revenue along the known price curve. Sell in tranches around town demand ticks, account for likely opponent harvest/sales, and begin forced liquidation with enough travel and order-cap slack before the final day.

Useful state features include:

- day, hour, steps remaining, money for both players;
- each tile's kind, crop/animal, age, days to yield/decay, held yield, water/feed streak, care bank, fertilizer horizon;
- private shed, seeds, and each worker's inventory;
- worker positions and distance/deadline to every pending task;
- market inventory, current price, estimated derivative and revenue from selling the next N units for each resource;
- unlocked shops, current demand rate, next town ticks, and demand-weighted future scarcity;
- opponent crop/animal counts, planting ages, inferred next harvest windows, plausible private stock, and observed money changes;
- capacity signals: unlocked land, occupied/empty tiles, expected daily labor demand, expected shed pressure, and cash runway.

### Opponent modeling

- Infer opponent future production from visible tile type and planting/placement age, then forecast likely harvest and glut windows.
- Avoid matching an opponent's premium monoculture when their expected dump will collapse its price; either sell earlier, diversify, or choose a demand-supported substitute.
- Maintain a small number of robust strategic modes, e.g. staple throughput, balanced recurring production, and adversarial market response. Switch only on strong visible evidence to prevent oscillation.
- Evaluate against a frozen portfolio: built-ins, prior champions, product-specialist scripted bots, early/late sellers, animal-heavy policies, market denial policies, and randomized policy parameters.

### Experiment ladder and gates

| Stage | Candidate | Required gate |
|---|---|---|
| 1 | Minimal wheat loop | Valid episodes; beats `pass` and `random` essentially always; no invalid actions |
| 2 | Wheat/carrot staples scheduler | At least 95% vs `starter`; zero preventable weeds/escapes; materially higher money than starter |
| 3 | Price-aware tranche seller | At least 10% mean-money gain vs stage 2 with non-overlapping confidence interval |
| 4 | Mixed portfolio planner with land, recurring crops, animals, care/fertilizer | At least 15% gain vs stage 3 and at least 90% head-to-head win rate over 500 episodes |
| 5 | Opponent-aware portfolio/sale timing | At least 60% vs frozen stage 4 mirror variants, with no regression vs simple baselines |
| 6 | Learned tuning layer, optional | At least 10% robust gain vs stage 5; otherwise retain transparent stage 5 |

Core ablations: no hands; fixed hand count; no fertilizer/care; immediate sell versus tranche sales; crops-only, animals-only, and mixed; land expansion off/on; opponent model off/on; forced-liquidation horizon; task assignment heuristic. Keep a component only when it has a positive confidence-bound contribution across the frozen pool.

For learned optimization, Kimi favors evolutionary/CMA-ES tuning of a compact set of planner weights over end-to-end deep RL initially. Deep self-play becomes reasonable only after a fast, trustworthy simulator and scripted population exist.

### Reproducibility and leaderboard control

- Pin environment/Python versions and record agent Git SHA, configuration, seed list, player slots, opponent IDs, and result JSON for every experiment.
- Keep immutable versioned agents and a champion registry connecting every Kaggle submission to one local artifact and benchmark report.
- Use deterministic decisions and no wall-clock, network, credential, or unseeded-random behavior in `main.py`.
- Tune only against a frozen local pool, not recent leaderboard opponents. Test at least 200 distinct seeds and both slots for quick checks, 500+ per pairing for promotion.
- Submit sparingly: first a plumbing baseline, then only promoted candidates. Treat leaderboard divergence as evidence of environment/config/opponent mismatch and investigate instead of directly tuning to it.
- Prefer worst-case and pool-robust win rate over peak money against passive opponents.

### Final submission strategy

The final candidate should be the highest ladder stage that passes all local gates, not necessarily the most complex. It should:

- adapt to observed/config-derived horizon and state rather than blindly hardcode 720 turns;
- run comfortably under the time limit, targeting under 50 ms per turn;
- precompute static market/task tables safely;
- have a conservative fallback policy for unexpected observation shapes;
- start forced liquidation early enough that all shed and carried inventory can be sold;
- use a single `main.py` unless measured value from bundled assets justifies archive complexity;
- be benchmarked from both player slots across the frozen opponent pool immediately before submission.

### Ten highest-value next actions

1. Pin/install the environment and snapshot hashes/version information.
2. Read authenticated Rules and Evaluation materials and fill the five unknowns.
3. Build the seeded, slot-swapped headless batch harness.
4. Add tests for the highest-risk mechanics and silent-no-op conditions.
5. Resolve the care `+1` versus `+2` discrepancy against the exact server version.
6. Implement the minimal wheat and staples baselines and record reproducible benchmark reports.
7. Implement an exact marginal-price/tranche-sale module.
8. Implement the deadline-priority task scheduler and hire-value calculation.
9. Add episode diagnostics for income, losses, labor utilization, storage, and liquidation.
10. Establish the frozen opponent pool, champion registry, and mechanical promotion gates.

### Five authenticated-material questions

1. What exact rating/matchmaking formula is used, including ties, episode count, and public/final evaluation?
2. What are daily/total submission limits, and can final evaluation alter seeds, episode length, or market parameters?
3. Which `kaggle-environments` commit/version is deployed, and what is the authoritative CARE bonus?
4. What CPU, memory, dependency, file-size, and network restrictions apply to an agent package?
5. Are deliberate market-denial/price-floor tactics permitted, and what team/code-sharing/external-resource terms apply?

## Independent cross-check after Kimi's response

The current public sources support the two most implementation-specific claims:

- `LAND_ORDER = ["NE", "SW", "SE"]` in `kaggriculture.py`.
- Public engine line 807 increments `pending_care_bonus` by `1`, while the supplied README documents `2`.
- Public `kaggriculture.json` sets `actTimeout` to 1 and `remainingOverageTime` to 60.

These should still be tested against the competition server rather than assumed to match it.

## Debate round 2: implemented-agent review

### Continuation command

The same Kimi K3 OpenCode session was continued after the first implementation and local evaluation:

```bash
opencode run -c -m kimi-for-coding/k3 --format default 'Debate round 2. Review /Users/seyam/work/Kaggriculture/main.py as currently implemented. Local results: 10/10 wins vs starter, mean 21139.7 vs 3500.8; 10/10 vs random; symmetric self-play ties at 22631. Diagnostics: the policy buys 10 hands daily for 143/day, reaches zero cash before first harvest, loses some initial melons to weeds, immediately sells all shed inventory, and uses a coarse crop score. Do not edit files, use credentials, or submit. Give a concrete ranked pre-first-submission patch recommendation focused on: (1) dynamic hand targets and cash runway, (2) deadline/slack-aware task matching, (3) seed/land budgeting, (4) market tranche timing, and (5) a proportionate seeded-game count before a plumbing submission. Cite exact functions/logic in main.py and identify risky interactions. For each proposed change give expected value, complexity/regression risk, minimum test, and acceptance gate. Distinguish MUST-FIX before plumbing submission from SHOULD-WAIT until after it. Challenge the previous plan where the evidence supports a simpler first submission. End with a prioritized patch sequence of no more than six items and a direct recommendation: submit current baseline, patch then submit, or test more first. Return only the critique.'
```

OpenCode again reported `build · k3`.

### Kimi K3 output

#### Code-verified defects

1. **Late-day planting guarantees weed conversion.** `_task_list` creates low-priority PLANT tasks at any hour. A crop planted at hour 22 or 23 cannot also be watered before end-of-day; because planting initializes one missed-watering day, the seed becomes a weed. Kimi judges this the most likely cause of the observed initial melon losses and treats it as correctness rather than tuning.
2. **Seed buying starves next-morning labor.** `_market_actions` can combine day-0 land purchase, ten hires, and a twelve-melon seed batch, then continue spending $143/day while those melons take roughly ten days to pay back. Evening seed purchases can remove the cash needed for morning workers, causing another watering shortfall.
3. **Synchronized harvest can overflow the shed.** The policy never uses `DROP`/`PICKUP`. A concentrated melon planting can produce more than the 100-item shed cap in one end-of-day auto-drop, silently destroying overflow. This is not yet measured but is mechanically plausible and should be instrumented before adding logistics complexity.
4. **Sell orders contend with hire slots.** On heavy sell mornings, `slots = 10 - len(orders)` limits how many hires can be placed in the first three hours, reducing labor when harvest/logistics pressure is highest.
5. **Greedy matching can thrash.** `_unit_actions` globally rematches every turn with no task commitment. A worker walking toward a target can be reassigned when another worker becomes marginally closer, wasting movement.

#### Correction to the first-round plan

- Ten wins against `starter` at roughly $21k versus $3.5k prove basic functionality but not competitiveness because starter is extremely weak.
- Deterministic symmetric self-play ties contain no useful policy-strength signal. Use money distributions across seeds and varied scripted opponents instead.
- The earlier 500-game promotion gate is disproportionate for the first plumbing submission. Kimi recommends 25 seeded games for crash/correctness coverage, with both player positions and a mix of starter/random. Large confidence-interval studies belong after infrastructure is validated.
- Opponent modeling, animals/fertilizer, exact market timing, and sophisticated portfolio optimization should be deferred until after the plumbing submission.

#### Ranked recommendations

##### P1 — Must fix: same-day planting capacity guard

Change `_task_list` so it does not emit planting late in the day and does not plant more crops than the available workers/turns can water before refresh. A minimal safe version stops new planting in the final two hours; a stronger version budgets plant tasks against remaining unit-turn capacity after urgent watering.

- Expected value: eliminates paid-seed weed losses, potentially hundreds or thousands of dollars in premium-heavy openings.
- Complexity/risk: very low; only risk is slightly slower land utilization.
- Minimum test: 25 seeded games with an own-crop weed-loss counter.
- Acceptance gate: zero preventable own-crop weeds and no mean-money regression.

##### P2 — Must fix: dynamic hands and protected cash runway

Replace the fixed ten-worker target with a workload-driven target, suggested starting rule `clamp(ceil(today_task_count / 14), 2, 10)`. Reserve enough cash for the next day's planned labor plus a small seed batch. Cap seed purchases at `money - reserve`; seed/land expansion must not consume the care budget for the existing farm. Give early-hour HIRE orders priority over new seed orders while preserving any same-turn sale that funds labor.

- Expected value: prevents zero-cash labor collapse and reduces variance more than it increases peak reward.
- Complexity/risk: low to medium; under-hiring can reintroduce missed deadlines, so retain a conservative floor.
- Minimum test: 25 seeds, logging hands/day, urgent tasks, zero-cash days, and crop losses.
- Acceptance gate: zero deadline losses, no post-day-3 labor collapse with pending work, 25/25 against starter, and no material mean-money regression.

##### P3 — Must add locally: diagnostic counters

Instrument the harness, not the submission, for crop-to-weed loss, shed overflow, terminal unsold inventory, zero-cash days, and hands hired/day.

- Expected value: determines whether logistics, market timing, or capital allocation is the actual next bottleneck.
- Complexity/risk: trivial and isolated from submission behavior.
- Acceptance gate: all counters available in the 25-game report.

##### P4 — Wait: shed overflow mitigation

Only implement if diagnostics show overflow above roughly 2% of revenue. First prefer staggered per-crop planting; add mid-day shed drops/logistics only when measured value exceeds travel cost.

##### P5 — Wait: slack-aware matching

Rank water tasks by end-of-day slack and harvest tasks by decay slack before distance. Add short task reservation/commitment to prevent rematching thrash. This is a moderate-EV, medium-regression change and should be gated on zero deadline misses plus no reward regression.

##### P6 — Wait: tranche sales and exact crop scoring

After plumbing validation, replace the coarse crop table/fudge factor with exact production timing and age-weighted visible supply. Test holding premium goods only when projected marginal price is poor and there are more than three days left; tranche around town consumption. This can improve premium returns but interacts dangerously with shed overflow and zero terminal value, so it should follow diagnostics and storage fixes.

### Kimi's final sequence and recommendation

1. Add the same-day plant/water guard.
2. Add workload-driven hands and a protected cash reserve.
3. Add local diagnostics and run a 25-seed, position-varied starter/random check.
4. Make the plumbing submission.
5. Address overflow and then task slack only if diagnostics justify them.
6. Add market tranching/exact crop scoring after the first infrastructure signal.

**Direct recommendation: patch, then submit.** The plant/water and cash-runway bugs destroy known value and are small enough to fix before an infrastructure check. Require zero preventable weeds and 25/25 starter completion/wins in the proportionate pre-submit test. Do not delay the plumbing submission for advanced market or opponent modeling.
