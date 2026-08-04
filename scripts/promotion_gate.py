"""Evaluate one candidate against a fixed multi-opponent promotion suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

try:  # Supports module and direct-script execution.
    from scripts.tournament import _wilson_interval, resolve_agent, run_paired_tournament
except ModuleNotFoundError:  # pragma: no cover - exercised by direct CLI use
    from tournament import _wilson_interval, resolve_agent, run_paired_tournament


DEFAULT_OPPONENTS = (
    "main.py",
    "crop-specialist",
    "diversified-baseline",
    "animal-specialist",
)


def _add_totals(target: dict[str, int], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            target[key] = target.get(key, 0) + int(value)


def evaluate_promotion(
    candidate: str,
    opponents: list[str],
    *,
    pairs: int,
    seed: int,
    min_win_rate: float,
    min_wilson_lower: float,
    min_mean_margin: float,
) -> dict[str, Any]:
    """Run the suite and return a JSON-serializable promotion decision."""
    if not opponents:
        raise ValueError("at least one opponent is required")
    if pairs <= 0:
        raise ValueError("pairs must be positive")
    for name, value in (
        ("min_win_rate", min_win_rate),
        ("min_wilson_lower", min_wilson_lower),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")

    resolved_candidate = resolve_agent(candidate)
    opponent_summaries: list[dict[str, Any]] = []
    all_episodes: list[dict[str, Any]] = []
    all_pairs: list[dict[str, Any]] = []
    diagnostic_totals: dict[str, int] = {}

    for opponent_index, opponent in enumerate(opponents):
        result = run_paired_tournament(
            resolved_candidate,
            resolve_agent(opponent),
            pairs=pairs,
            seed=seed,
        )
        episodes = list(result.get("episodes", []))
        paired_results = list(result.get("pairs", []))
        all_episodes.extend({**episode, "opponent": opponent} for episode in episodes)
        all_pairs.extend({**pair, "opponent": opponent} for pair in paired_results)
        _add_totals(diagnostic_totals, result.get("diagnostic_totals", {}))

        summary = {key: value for key, value in result.items() if key != "episodes"}
        opponent_summaries.append(
            {
                "opponent_index": opponent_index,
                "opponent": opponent,
                "summary": summary,
            }
        )

    episode_count = len(all_episodes)
    episode_wins = sum(int(episode.get("win", 0)) for episode in all_episodes)
    episode_ties = sum(int(episode.get("tie", 0)) for episode in all_episodes)
    episode_losses = episode_count - episode_wins - episode_ties
    paired_count = len(all_pairs)
    paired_wins = sum(int(pair.get("paired_win", 0)) for pair in all_pairs)
    paired_ties = sum(int(pair.get("paired_tie", 0)) for pair in all_pairs)
    paired_losses = paired_count - paired_wins - paired_ties
    invalid_episodes = sum(
        1
        for episode in all_episodes
        if any(str(status) != "DONE" for status in episode.get("statuses", []))
        or len(episode.get("statuses", [])) != 2
    )
    episode_margins = [float(episode["margin"]) for episode in all_episodes]
    paired_margins = [float(pair["paired_margin"]) for pair in all_pairs]
    win_rate = episode_wins / episode_count
    paired_win_rate = paired_wins / paired_count
    wilson = _wilson_interval(episode_wins, episode_count)

    zero_terminal_waste = all(
        diagnostic_totals.get(key, 0) == 0
        for key in (
            "terminal_unsold_items",
            "terminal_seed_cost",
            "terminal_field_yield_units",
            "terminal_non_cash_value",
        )
    )
    checks = {
        "no_invalid_episodes": invalid_episodes == 0,
        "zero_terminal_waste": zero_terminal_waste,
        "zero_preventable_weeds": diagnostic_totals.get("preventable_weeds", 0) == 0,
        "zero_cash_days": diagnostic_totals.get("zero_cash_days", 0) == 0,
        "minimum_episode_win_rate": win_rate >= min_win_rate,
        "minimum_wilson_lower": wilson["low"] >= min_wilson_lower,
        "minimum_mean_margin": mean(episode_margins) >= min_mean_margin,
    }
    checks["overall"] = all(checks.values())

    return {
        "candidate": candidate,
        "opponents": list(opponents),
        "pairs_per_opponent": pairs,
        "base_seed": seed,
        "thresholds": {
            "min_win_rate": min_win_rate,
            "min_wilson_lower": min_wilson_lower,
            "min_mean_margin": min_mean_margin,
        },
        "aggregate": {
            "episodes_played": episode_count,
            "episode_wins": episode_wins,
            "episode_ties": episode_ties,
            "episode_losses": episode_losses,
            "episode_win_rate": win_rate,
            "episode_tie_rate": episode_ties / episode_count,
            "episode_loss_rate": episode_losses / episode_count,
            "episode_win_rate_wilson_95": wilson,
            "paired_results": paired_count,
            "paired_wins": paired_wins,
            "paired_ties": paired_ties,
            "paired_losses": paired_losses,
            "paired_win_rate": paired_win_rate,
            "paired_tie_rate": paired_ties / paired_count,
            "paired_loss_rate": paired_losses / paired_count,
            "mean_episode_margin": mean(episode_margins),
            "median_episode_margin": median(episode_margins),
            "mean_paired_margin": mean(paired_margins),
            "median_paired_margin": median(paired_margins),
            "invalid_episodes": invalid_episodes,
            "diagnostic_totals": diagnostic_totals,
        },
        "checks": checks,
        "per_opponent": opponent_summaries,
        "paired_results": all_pairs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--opponent", action="append", dest="opponents")
    parser.add_argument("--pairs", type=int, default=10, help="same-seed seat pairs per opponent")
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-win-rate", type=float, default=0.5)
    parser.add_argument("--min-wilson-lower", type=float, default=0.0)
    parser.add_argument("--min-mean-margin", type=float, default=0.0)
    args = parser.parse_args()

    report = evaluate_promotion(
        args.candidate,
        args.opponents or list(DEFAULT_OPPONENTS),
        pairs=args.pairs,
        seed=args.seed,
        min_win_rate=args.min_win_rate,
        min_wilson_lower=args.min_wilson_lower,
        min_mean_margin=args.min_mean_margin,
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
