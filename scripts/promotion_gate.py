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
    min_seat_win_rate: float,
) -> dict[str, Any]:
    """Run the suite and return a JSON-serializable promotion decision."""
    if not opponents:
        raise ValueError("at least one opponent is required")
    if pairs < 2:
        raise ValueError("pairs must be at least 2 so both seed halves are non-empty")
    for name, value in (
        ("min_win_rate", min_win_rate),
        ("min_wilson_lower", min_wilson_lower),
        ("min_seat_win_rate", min_seat_win_rate),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")

    resolved_candidate = resolve_agent(candidate)
    opponent_summaries: list[dict[str, Any]] = []
    all_episodes: list[dict[str, Any]] = []
    all_pairs: list[dict[str, Any]] = []
    diagnostic_totals: dict[str, int] = {}

    for opponent_index, opponent in enumerate(opponents):
        # Each opponent owns a non-overlapping contiguous block of scenario
        # seeds. This prevents the same town/weed realization from creating
        # hidden correlation across the entire suite.
        opponent_seed = seed + opponent_index * pairs
        result = run_paired_tournament(
            resolved_candidate,
            resolve_agent(opponent),
            pairs=pairs,
            seed=opponent_seed,
        )
        episodes = list(result.get("episodes", []))
        paired_results = list(result.get("pairs", []))
        all_episodes.extend({**episode, "opponent": opponent} for episode in episodes)
        all_pairs.extend({**pair, "opponent": opponent} for pair in paired_results)
        _add_totals(diagnostic_totals, result.get("diagnostic_totals", {}))

        episode_count_for_opponent = len(episodes)
        wins_for_opponent = sum(int(episode.get("win", 0)) for episode in episodes)
        ties_for_opponent = sum(int(episode.get("tie", 0)) for episode in episodes)
        margins_for_opponent = [float(episode["margin"]) for episode in episodes]
        wilson_for_opponent = _wilson_interval(wins_for_opponent, episode_count_for_opponent)
        seat_episodes = {
            seat: [episode for episode in episodes if int(episode.get("candidate_seat", -1)) == seat]
            for seat in (0, 1)
        }
        seat_wins = {
            seat: sum(int(episode.get("win", 0)) for episode in seat_episodes[seat])
            for seat in (0, 1)
        }
        seat_win_rates = {
            seat: seat_wins[seat] / len(seat_episodes[seat]) if seat_episodes[seat] else 0.0
            for seat in (0, 1)
        }
        midpoint = len(paired_results) // 2
        first_half = paired_results[:midpoint]
        second_half = paired_results[midpoint:]
        first_half_margin = mean(float(pair["paired_margin"]) for pair in first_half)
        second_half_margin = mean(float(pair["paired_margin"]) for pair in second_half)
        opponent_invalid = sum(
            1
            for episode in episodes
            if any(str(status) != "DONE" for status in episode.get("statuses", []))
            or len(episode.get("statuses", [])) != 2
        )
        opponent_diagnostics = result.get("diagnostic_totals", {})
        opponent_zero_terminal = all(
            opponent_diagnostics.get(key, 0) == 0
            for key in (
                "terminal_unsold_items",
                "terminal_seed_cost",
                "terminal_field_yield_units",
                "terminal_non_cash_value",
            )
        )
        opponent_mean_margin = mean(margins_for_opponent)
        opponent_checks = {
            "no_invalid_episodes": opponent_invalid == 0,
            "zero_terminal_waste": opponent_zero_terminal,
            "zero_preventable_weeds": opponent_diagnostics.get("preventable_weeds", 0) == 0,
            "zero_cash_days": opponent_diagnostics.get("zero_cash_days", 0) == 0,
            "minimum_episode_win_rate": wins_for_opponent / episode_count_for_opponent >= min_win_rate,
            "minimum_wilson_lower": wilson_for_opponent["low"] >= min_wilson_lower,
            "minimum_seat_0_win_rate": seat_win_rates[0] >= min_seat_win_rate,
            "minimum_seat_1_win_rate": seat_win_rates[1] >= min_seat_win_rate,
            "positive_minimum_mean_margin": opponent_mean_margin > 0 and opponent_mean_margin >= min_mean_margin,
            "positive_first_half_paired_margin": first_half_margin > 0,
            "positive_second_half_paired_margin": second_half_margin > 0,
        }
        opponent_checks["overall"] = all(opponent_checks.values())
        summary = {key: value for key, value in result.items() if key != "episodes"}
        opponent_summaries.append(
            {
                "opponent_index": opponent_index,
                "opponent": opponent,
                "base_seed": opponent_seed,
                "metrics": {
                    "episodes_played": episode_count_for_opponent,
                    "episode_wins": wins_for_opponent,
                    "episode_ties": ties_for_opponent,
                    "episode_losses": episode_count_for_opponent - wins_for_opponent - ties_for_opponent,
                    "episode_win_rate": wins_for_opponent / episode_count_for_opponent,
                    "episode_win_rate_wilson_95": wilson_for_opponent,
                    "mean_episode_margin": opponent_mean_margin,
                    "seat_wins": {str(seat): seat_wins[seat] for seat in (0, 1)},
                    "seat_win_rates": {str(seat): seat_win_rates[seat] for seat in (0, 1)},
                    "first_half_pairs": len(first_half),
                    "first_half_mean_paired_margin": first_half_margin,
                    "second_half_pairs": len(second_half),
                    "second_half_mean_paired_margin": second_half_margin,
                },
                "checks": opponent_checks,
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
        "every_opponent_independently_passes": all(
            opponent["checks"]["overall"] for opponent in opponent_summaries
        ),
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
            "min_seat_win_rate": min_seat_win_rate,
        },
        "aggregate": {
            "episodes_played": episode_count,
            "episode_wins": episode_wins,
            "episode_ties": episode_ties,
            "episode_losses": episode_losses,
            "episode_win_rate": win_rate,
            "episode_tie_rate": episode_ties / episode_count,
            "episode_loss_rate": episode_losses / episode_count,
            "episode_win_rate_wilson_95": {
                **wilson,
                "interpretation": "descriptive_only_correlated_pooled_episodes_do_not_drive_promotion",
            },
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
    parser.add_argument("--min-seat-win-rate", type=float, default=0.55)
    args = parser.parse_args()

    report = evaluate_promotion(
        args.candidate,
        args.opponents or list(DEFAULT_OPPONENTS),
        pairs=args.pairs,
        seed=args.seed,
        min_win_rate=args.min_win_rate,
        min_wilson_lower=args.min_wilson_lower,
        min_mean_margin=args.min_mean_margin,
        min_seat_win_rate=args.min_seat_win_rate,
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
