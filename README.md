# Kaggriculture Agent

A reproducible, self-contained agent for Kaggle's [Kaggriculture competition](https://www.kaggle.com/competitions/kaggriculture/overview). Kaggriculture is a two-player farming simulation, not a supervised train/test prediction task. The deliverable is a `main.py` policy that earns more banked coins than its opponent after 720 turns.

The current V21 policy retains the exact, attributed Apache-2.0 public V18/C20
closed-loop farm route and the locally developed V18 market-recovery overlay,
then adds a one-time late capital latch. It combines:

- deterministic task assignment for planting, watering, harvesting, weeds, and shed logistics;
- opponent- and inventory-aware crop scoring using the published market curves;
- cash-runway-aware daily hiring and staged land expansion;
- seed accounting that avoids the simulator's all-or-nothing simultaneous-plant failure;
- automatic liquidation and a defensive no-error fallback.
- a three-quadrant, 12-hand production route with eight cows and six sheep;
- public-state expert selection for route repair and market-order timing.
- demand-matched premium sales on the first turn after town consumption;
- a matched-rival price-floor cap that keeps denial sales economically useful.
- late abstention from added sweeps only when the public rival is already at
  least 5,000 coins behind at step 577.

## Current result

Submitted V18 opened 14-1 in public play and rose from its 600 initial rating
to 1,804.1. V21 then improved the frozen historical corpus from V18's 94/110
wins to 100/110 and an untouched live-15 corpus from 27/30 to 29/30, with zero
V18 win-to-V21 loss flips or worsened V18 non-wins. It preserved the sealed
top-20 result at 31/40 wins. Across 100 adaptive paired seeds against exact
V18, V21 was 2-1 with 97 ties, +6.98 mean paired margin, all four chronological
blocks nonnegative, and zero invalid/cash/weed regressions. See
`reports/v18-recovery-sweep.md`, `reports/submission-55260568.md`, and
`reports/v21-capital-latch.md` for the causal controls, live results, audits,
and exact release evidence.

## Repository map

| Path | Purpose |
|---|---|
| `main.py` | Single-file Kaggle submission |
| `agents/` | Immutable submitted baselines and development candidates |
| `THIRD_PARTY_NOTICES.md` | Attribution and per-file licenses for imported public policies |
| `scripts/tournament.py` | Seeded, slot-swapped local evaluation harness |
| `scripts/leaderboard_benchmark.py` | Live top-ladder public replay-trace benchmark |
| `scripts/comparative_replay_corpus.py` | Candidate-versus-baseline gate over a local replay corpus |
| `tests/` | Full-episode validity and self-play tests |
| `docs/competition.md` | Competition mechanics, evaluation, timeline, and submission contract |
| `docs/rules.md` | Implementation-focused rules summary |
| `docs/findings.md` | Engine audit, discrepancies, and strategy findings |
| `docs/plan.md` | Experiment ladder and Codex/Kimi K3 debate synthesis |
| `metadata/competition.json` | Machine-readable competition metadata |
| `research/` | Recorded independent Kimi K3 reviews |

The authenticated competition download, server logs, and replays are intentionally ignored by Git because the rules restrict redistribution. Re-download them locally when needed. Repository code is MIT-licensed and publicly mirrored through the competition's Kaggle surfaces as required by the public-code-sharing rule.

## Setup

Python 3.12 and `uv` are used because the host's Python 3.14 is ahead of some simulation dependencies.

```bash
uv sync --dev
uvx kaggle competitions download kaggriculture -p data/raw
unzip data/raw/kaggriculture.zip -d data/raw/competition
```

Kaggle credentials must be configured separately; never commit tokens or browser state.

## Verify

```bash
uv run pre-commit install
uv run pre-commit run --all-files
uv run pytest -q
uv run python scripts/tournament.py --opponent starter --games 10
uv run python scripts/tournament.py --opponent random --games 10
uv run python scripts/tournament.py --opponent main.py --games 10
```

The repository deliberately uses a local pre-commit test hook instead of GitHub
Actions or another hosted CI/CD workflow. Install it once after cloning; every
commit will then run the full test suite. Every tournament comparison swaps
player slots. Increase the game count and use a frozen scripted-opponent pool
before promoting a strategic change.

## Benchmark the current leaders

With Kaggle credentials configured, one command resolves the current top five
teams, selects each team's best active submission and newest completed public
episode, downloads the public replay into the ignored `artifacts/` cache, and
tests `main.py` against each recorded policy from both seats:

```bash
uv run python scripts/leaderboard_benchmark.py \
  --candidate main.py \
  --top 5 \
  --episodes-per-team 1
```

The command writes `artifacts/leaderboard-benchmark.json` and `.md`. Its
immutable corpus manifest records the UTC capture cutoff, installed engine,
distinct leaderboard and submission ratings, and a composite identity for every
`(submission, episode, recorded seat)` trace. Replay bytes, configuration, and
the selected action stream are SHA-256 digested. Increase `--top` or
`--episodes-per-team` for a broader, slower screen. To compare a new candidate
against the exact same teams and episode seeds without refreshing the API,
reuse the saved snapshot and choose different output paths:

```bash
uv run python scripts/leaderboard_benchmark.py \
  --candidate agents/candidate_v8_market_order.py \
  --snapshot artifacts/leaderboard-benchmark.json \
  --output artifacts/v8-leaderboard-benchmark.json \
  --markdown artifacts/v8-leaderboard-benchmark.md
```

This is an open-loop stress benchmark: recorded public actions do not adapt
after our candidate changes the simulated state. It is useful for regression
and adversarial screening, but it does not execute competitors' private source
code and does not estimate live ladder win probability. Snapshot reuse fails
closed if the report/manifest schema, engine version, replay payload episode ID,
file digest, configuration digest, or action-trace digest changed. Older
pre-manifest reports must be recaptured with a live command. The summary reports
both raw counts and source-episode-cluster-adjusted outcomes because two sampled
teams can come from the same public match; paired-seat margin divergence makes
the remaining open-loop/seat sensitivity visible. A candidate simulation error
is retained as a trace error rather than removing that replay from the manifest,
so the frozen corpus remains candidate-independent and can be retried from the
same snapshot. Output paths are resolved before use and must not collide with
the candidate, snapshot, each other, or the replay-cache tree.

## Compare a candidate on the full local replay corpus

The comparative corpus gate runs both the candidate and frozen baseline from
both seats against every matching recorded trace, then reports the exact
candidate-minus-baseline margin deltas. For the V7 public replay cache, identify
the recorded opponent by excluding our team name:

```bash
uv run python scripts/comparative_replay_corpus.py \
  --candidate agents/candidate_v8_market_order.py \
  --baseline main.py \
  --replays-dir artifacts/v7-public-replays \
  --pattern 'episode-*-replay.json' \
  --exclude-team 'Touhidul Alam Seyam'
```

The command writes ignored JSON and Markdown reports under `artifacts/`. It
fails closed by default if a trace errors, either simulation is invalid, any
seat comparison regresses, or the mean delta is negative. Experiments that
intentionally tolerate bounded losses can set `--max-negative-comparisons` and
`--min-mean-delta` explicitly. `--recorded-team` selects the named trace seat
instead, while `--opponent-seat` is useful for corpora with missing or unstable
team labels. Reports include per-trace seat deltas and summaries grouped by
recorded team and final public farm footprint. A corpus manifest pins the
installed engine, source seed, resolved recorded seat, replay byte digest and
size, configuration digest, and selected action-trace digest. The command
rejects duplicate `(episode, recorded seat)` identities, duplicate replay
content, non-finite thresholds, and any resolved/symlinked collision among the
candidate, baseline, replay inputs, JSON output, and Markdown output. Replay
bytes are revalidated between the baseline and candidate runs so a file changed
during a long gate fails closed instead of producing a mixed comparison.

As with the leader benchmark, this is comparative open-loop evidence. The
recorded trace cannot adapt after either policy diverges, so the result is a
reproducible regression screen rather than a live win-rate estimate.

## Attribute replay losses

After freezing a comparative corpus report, one command can re-run its exact
candidate, baseline, engine, replay bytes, seeds, configurations, and selected
action traces with deeper market attribution:

```bash
uv run python scripts/replay_loss_attribution.py \
  --comparison artifacts/v18-standalone-v7-public55.json \
  --candidate main.py \
  --baseline agents/candidate_v7_public_v18.py \
  --replays-dir artifacts/v7-public-replays \
  --exclude-team 'Touhidul Alam Seyam' \
  --checkpoints 289,433,577,719 \
  --windows 289:433,433:577,577:719
```

The ignored JSON/Markdown report records engine-committed SELL units and
realized revenue by product, demand phase, actor, and window; checkpoint bank
and margin curves; own-bank versus opponent-denial decomposition; and rescued,
harmed-to-loss, and unresolved-loss strata. Checkpoint public state is labelled
online-safe separately for each policy; candidate-minus-baseline checkpoint
deltas are retrospective counterfactuals. Engine commit events are exact
diagnostics but are not directly observable by a live policy; window effects,
outcomes, and final footprints are labelled retrospective. Day and demand-phase
metrics derive `turnsPerDay`, `townShopSellInterval`, and
`townCenterSellInterval` from each replay configuration, falling back to the
engine defaults of 24/4/12 only when fields are absent. A digest-pinned input manifest and repeated mutation
checks prevent candidate, baseline, comparison, or replay drift during the
long-running audit. Narrow `--pattern` for a manifest-verified smoke subset.

## Submit

`main.py` exposes the required top-level `agent(obs)` function and uses only the standard library.

```bash
uvx kaggle competitions submit kaggriculture \
  -f main.py \
  -m "v21 capital latch 0cd14b65"
```

After submission, validate the status, then inspect server episodes and logs before treating the result as usable:

```bash
uvx kaggle competitions submissions kaggriculture
uvx kaggle competitions episodes SUBMISSION_ID
uvx kaggle competitions logs EPISODE_ID AGENT_INDEX
```

## Reproducibility

- Python: 3.12
- `kaggle-environments`: 1.32.4
- Environment source SHA-256: `9741c0470a8db98a70644491d5121ae6295413343d1a08ef9fcee35e0b76f2c5`
- Current promoted agent SHA-256: `0cd14b653102d276c4f902fa3b8c6bd81d869b8ab64c422cb881b9d2346ec639`
- Default local seed sequence starts at `20260804`
- The agent is deterministic for a given observation; environmental weeds and town shops remain stochastic.

The live competition is still changing. Re-run mechanic tests and tournaments after every `kaggle-environments` upgrade.
