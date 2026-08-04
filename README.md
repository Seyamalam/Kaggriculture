# Kaggriculture Agent

A reproducible, self-contained agent for Kaggle's [Kaggriculture competition](https://www.kaggle.com/competitions/kaggriculture/overview). Kaggriculture is a two-player farming simulation, not a supervised train/test prediction task. The deliverable is a `main.py` policy that earns more banked coins than its opponent after 720 turns.

The current policy combines:

- deterministic task assignment for planting, watering, harvesting, weeds, and shed logistics;
- opponent- and inventory-aware crop scoring using the published market curves;
- cash-runway-aware daily hiring and staged land expansion;
- seed accounting that avoids the simulator's all-or-nothing simultaneous-plant failure;
- automatic liquidation and a defensive no-error fallback.
- adaptive livestock expansion: eight sheep by default, or a latched
  four-sheep/four-cow response to an early sheep-heavy opponent.

## Current result

The first promoted candidate completed every local validation episode. In the 25-seed, slot-swapped pre-submission gate against the built-in `starter`, it won **25/25** with mean final bank **40,499** versus **3,497**, zero preventable crop losses, zero cash-collapse days, and zero terminal unsold items. It also won 25/25 against `random`. This is plumbing evidence, not a leaderboard-performance claim: strong evaluation requires a larger frozen opponent pool.

Kaggle submission `55245711` passed its server self-play validation (`COMPLETE`) with no stdout/stderr errors. It won its first public episode, then lost the next two; its moving rating fell as low as 511.8 and later reached 636.3 as additional matches completed. The losses exposed the intended gap between a plumbing baseline and a competitive policy: v1 uses crops and hired hands but no livestock or fertilizer, and it strands purchased seeds at the terminal boundary.

The exact submitted v1 is preserved by Git commit `dd3bbec` and tag `submission-55245711`. Development candidates are not promoted to `main.py` or submitted to Kaggle until they pass deterministic paired-seat gates against the frozen local opponent pool.

Current development status: early mixed-livestock and crop/seed-cap prototypes failed and were rejected. V6 then passed a strict 50-episode paired-seat gate against the stronger V5 policy with 50 wins, a +9,880 mean margin, and zero safety failures. It also won both seats against open-loop traces of each public v1 loss. An independent GPT-5.6 Sol extra-high audit approved one monitored progress submission. Submission `55247685` passed server self-play validation with 66,939 rewards in both seats and no logged errors; its current 600.0 is the initial rating while public pairing is pending. See `reports/v6-release-gate.md` and `reports/submission-55247685.md`.

## Repository map

| Path | Purpose |
|---|---|
| `main.py` | Single-file Kaggle submission |
| `agents/` | Immutable submitted baselines and development candidates |
| `THIRD_PARTY_NOTICES.md` | Attribution and per-file licenses for imported public policies |
| `scripts/tournament.py` | Seeded, slot-swapped local evaluation harness |
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

## Submit

`main.py` exposes the required top-level `agent(obs)` function and uses only the standard library.

```bash
uvx kaggle competitions submit kaggriculture \
  -f main.py \
  -m "deterministic planner v1"
```

After submission, validate the status, then inspect server episodes and logs before treating the result as usable:

```bash
uvx kaggle competitions submissions kaggriculture
uvx kaggle competitions episodes SUBMISSION_ID
uvx kaggle competitions logs EPISODE_ID AGENT_INDEX
```

## Reproducibility

- Python: 3.12
- `kaggle-environments`: 1.32.3
- Environment source SHA-256: `2f5f94e3da0f007f6d7628e30889bd19c83716183eeaa05b4922430db5021737`
- Current submitted agent SHA-256: `1464c72bba660d5c86d9c3295c7a5c17551241c0a2cb75f53fcf1159266aadcb`
- Default local seed sequence starts at `20260804`
- The agent is deterministic for a given observation; environmental weeds and town shops remain stochastic.

The live competition is still changing. Re-run mechanic tests and tournaments after every `kaggle-environments` upgrade.
