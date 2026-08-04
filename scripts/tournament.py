"""Run deterministic, same-seed paired-seat Kaggriculture evaluations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Callable

from kaggle_environments import make

try:  # Supports both ``python -m scripts.tournament`` and direct execution.
    from scripts.frozen_opponents import FROZEN_OPPONENTS
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI smoke test
    from frozen_opponents import FROZEN_OPPONENTS


ROOT = Path(__file__).resolve().parents[1]
SEED_COSTS = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
ANIMAL_PRODUCTS = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
PRODUCTS = (*SEED_COSTS, "EGG", "MILK", "WOOL", "FERTILIZER")
Agent = str | Callable[[dict[str, Any]], dict[str, Any]]


def _wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> dict[str, float]:
    """Return a two-sided Wilson score interval for a Bernoulli proportion."""
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("expected 0 <= successes <= trials")
    if trials == 0:
        return {"low": 0.0, "high": 0.0}
    proportion = successes / trials
    z_squared = z * z
    denominator = 1.0 + z_squared / trials
    center = (proportion + z_squared / (2.0 * trials)) / denominator
    radius = (
        z
        * (
            proportion * (1.0 - proportion) / trials
            + z_squared / (4.0 * trials * trials)
        )
        ** 0.5
        / denominator
    )
    return {"low": max(0.0, center - radius), "high": min(1.0, center + radius)}


def _inventory_counts(private: dict[str, Any]) -> dict[str, int]:
    """Return all terminal non-seed items in shed and unit inventories."""
    totals: dict[str, int] = {}
    for source in [private.get("shed", {}) or {}, *(private.get("inventories", []) or [])]:
        for item, value in source.items():
            count = int(value)
            if count:
                totals[str(item)] = totals.get(str(item), 0) + count
    return totals


def _field_yield_counts(farm: dict[str, Any]) -> dict[str, int]:
    """Count engine-reported yield units still standing in the field."""
    totals: dict[str, int] = {}
    for row in farm.get("tiles", []):
        for tile in row:
            if not isinstance(tile, dict):
                continue
            units = int(tile.get("yield_units", 0))
            if units <= 0:
                continue
            if tile.get("kind") == "PLANT":
                product = str(tile.get("crop"))
            elif tile.get("animal") in ANIMAL_PRODUCTS:
                product = ANIMAL_PRODUCTS[str(tile["animal"])]
            else:
                continue
            totals[product] = totals.get(product, 0) + units
    return totals


def _market_value(counts: dict[str, int], prices: dict[str, Any]) -> int:
    return sum(count * int(prices.get(item, 0)) for item, count in counts.items() if item in PRODUCTS)


def episode_diagnostics(env: Any, player: int) -> dict[str, Any]:
    preventable_weeds = 0
    capacity_pressure = 0
    zero_cash_days = 0
    max_hands_by_day: dict[int, int] = {}

    for index, states in enumerate(env.steps):
        state = states[player]
        obs = state.observation
        farm = obs.farms[player]
        day = int(obs.day)
        max_hands_by_day[day] = max(max_hands_by_day.get(day, 0), len(farm.hands))
        if int(obs.hour) == 0 and float(farm.money) <= 0:
            zero_cash_days += 1
        if index == 0:
            continue
        previous = env.steps[index - 1][player].observation
        previous_farm = previous.farms[player]
        if int(obs.hour) == 0:
            previous_private = previous.private
            carried = sum(int(value) for inventory in previous_private.inventories for value in inventory.values())
            shed = sum(int(value) for value in previous_private.shed.values())
            capacity_pressure += max(0, carried + shed - 100)
        for y, row in enumerate(farm.tiles):
            for x, tile in enumerate(row):
                before = previous_farm.tiles[y][x]
                if not (
                    isinstance(before, dict)
                    and before.get("kind") == "PLANT"
                    and isinstance(tile, dict)
                    and tile.get("kind") == "WEED"
                ):
                    continue
                max_life = int(before.get("max_lifespan_step", -1))
                if max_life < 0 or index < max_life:
                    preventable_weeds += 1

    final_obs = env.steps[-1][player].observation
    final_private = final_obs.private
    final_farm = final_obs.farms[player]
    prices = final_obs.market.prices
    unsold = _inventory_counts(final_private)
    seed_counts = {
        crop: int(final_private.seeds.get(crop, 0))
        for crop in SEED_COSTS
        if int(final_private.seeds.get(crop, 0))
    }
    standing_yield = _field_yield_counts(final_farm)
    unsold_items = sum(unsold.values())
    field_yield_units = sum(standing_yield.values())
    seed_cost = sum(SEED_COSTS[crop] * count for crop, count in seed_counts.items())
    unsold_value = _market_value(unsold, prices)
    field_yield_value = _market_value(standing_yield, prices)
    return {
        "preventable_weeds": preventable_weeds,
        "end_of_day_capacity_pressure": capacity_pressure,
        "zero_cash_days": zero_cash_days,
        "terminal_unsold_items": unsold_items,
        "terminal_unsold_by_product": unsold,
        "terminal_unsold_market_value": unsold_value,
        "terminal_seed_counts": seed_counts,
        "terminal_seed_cost": seed_cost,
        "terminal_field_yield_units": field_yield_units,
        "terminal_field_yield_by_product": standing_yield,
        "terminal_field_yield_market_value": field_yield_value,
        "terminal_non_cash_value": seed_cost + unsold_value + field_yield_value,
        "max_hands_by_day": max_hands_by_day,
    }


def resolve_agent(specification: str) -> Agent:
    """Resolve built-ins, frozen aliases, and repository-relative agent paths."""
    if specification in FROZEN_OPPONENTS:
        return FROZEN_OPPONENTS[specification]
    path = Path(specification)
    if not path.is_absolute() and (ROOT / path).exists():
        return str((ROOT / path).resolve())
    return specification


def run_game(
    left: Agent,
    right: Agent,
    seed: int,
    *,
    episode_steps: int = 720,
    replay_path: Path | None = None,
) -> dict[str, Any]:
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": episode_steps, "seed": seed},
        debug=True,
    )
    env.run([left, right])
    final = env.steps[-1]
    rewards = [float(state.reward or 0.0) for state in final]
    statuses = [str(state.status) for state in final]
    diagnostics = [episode_diagnostics(env, 0), episode_diagnostics(env, 1)]
    result: dict[str, Any] = {
        "seed": seed,
        "rewards": rewards,
        "statuses": statuses,
        "diagnostics": diagnostics,
    }
    if replay_path is not None:
        replay_path.parent.mkdir(parents=True, exist_ok=True)
        replay_path.write_text(json.dumps(env.toJSON(), indent=2) + "\n", encoding="utf-8")
        result["replay_file"] = str(replay_path)
    return result


def _candidate_episode(result: dict[str, Any], candidate_seat: int) -> dict[str, Any]:
    opponent_seat = 1 - candidate_seat
    ours = float(result["rewards"][candidate_seat])
    theirs = float(result["rewards"][opponent_seat])
    return {
        **result,
        "candidate_seat": candidate_seat,
        "ours": ours,
        "theirs": theirs,
        "margin": ours - theirs,
        "ours_diagnostics": result["diagnostics"][candidate_seat],
        "win": int(ours > theirs),
        "tie": int(ours == theirs),
    }


def run_paired_tournament(
    agent: Agent,
    opponent: Agent,
    *,
    pairs: int,
    seed: int,
    episode_steps: int = 720,
    replays_dir: Path | None = None,
) -> dict[str, Any]:
    """Play every seed twice, with the candidate in each seat."""
    if pairs <= 0:
        raise ValueError("pairs must be positive")
    episodes: list[dict[str, Any]] = []
    paired_results: list[dict[str, Any]] = []
    for pair_index in range(pairs):
        pair_seed = seed + pair_index
        seat_episodes: list[dict[str, Any]] = []
        for candidate_seat in (0, 1):
            left, right = (agent, opponent) if candidate_seat == 0 else (opponent, agent)
            replay_path = None
            if replays_dir is not None:
                replay_path = replays_dir / f"pair-{pair_index:04d}-seed-{pair_seed}-candidate-seat-{candidate_seat}.json"
            episode = _candidate_episode(
                run_game(left, right, pair_seed, episode_steps=episode_steps, replay_path=replay_path),
                candidate_seat,
            )
            episode["pair_index"] = pair_index
            episodes.append(episode)
            seat_episodes.append(episode)
        ours_total = sum(float(episode["ours"]) for episode in seat_episodes)
        theirs_total = sum(float(episode["theirs"]) for episode in seat_episodes)
        paired_results.append(
            {
                "pair_index": pair_index,
                "seed": pair_seed,
                "ours_total": ours_total,
                "theirs_total": theirs_total,
                "paired_margin": ours_total - theirs_total,
                "paired_win": int(ours_total > theirs_total),
                "paired_tie": int(ours_total == theirs_total),
            }
        )

    numeric_diagnostics = (
        "preventable_weeds",
        "end_of_day_capacity_pressure",
        "zero_cash_days",
        "terminal_unsold_items",
        "terminal_unsold_market_value",
        "terminal_seed_cost",
        "terminal_field_yield_units",
        "terminal_field_yield_market_value",
        "terminal_non_cash_value",
    )
    episode_count = len(episodes)
    episode_wins = sum(int(episode["win"]) for episode in episodes)
    episode_ties = sum(int(episode["tie"]) for episode in episodes)
    pair_count = len(paired_results)
    paired_wins = sum(int(pair["paired_win"]) for pair in paired_results)
    paired_ties = sum(int(pair["paired_tie"]) for pair in paired_results)
    return {
        "seed_pairs": pairs,
        "episodes_played": episode_count,
        "base_seed": seed,
        "episode_steps": episode_steps,
        "episode_wins": episode_wins,
        "episode_ties": episode_ties,
        "episode_win_rate": episode_wins / episode_count,
        "episode_tie_rate": episode_ties / episode_count,
        "episode_loss_rate": (episode_count - episode_wins - episode_ties) / episode_count,
        # Ties remain explicit non-wins; they are not silently scored as half
        # a win in either the point estimate or the Wilson interval.
        "episode_win_rate_wilson_95": _wilson_interval(episode_wins, episode_count),
        "paired_wins": paired_wins,
        "paired_ties": paired_ties,
        "paired_win_rate": paired_wins / pair_count,
        "paired_tie_rate": paired_ties / pair_count,
        "paired_loss_rate": (pair_count - paired_wins - paired_ties) / pair_count,
        "mean_ours": mean(float(episode["ours"]) for episode in episodes),
        "mean_theirs": mean(float(episode["theirs"]) for episode in episodes),
        "mean_episode_margin": mean(float(episode["margin"]) for episode in episodes),
        "mean_paired_margin": mean(float(pair["paired_margin"]) for pair in paired_results),
        "median_ours": median(float(episode["ours"]) for episode in episodes),
        "median_theirs": median(float(episode["theirs"]) for episode in episodes),
        "median_episode_margin": median(float(episode["margin"]) for episode in episodes),
        "seat_summary": {
            str(seat): {
                "wins": sum(int(episode["win"]) for episode in episodes if episode["candidate_seat"] == seat),
                "mean_margin": mean(
                    float(episode["margin"]) for episode in episodes if episode["candidate_seat"] == seat
                ),
            }
            for seat in (0, 1)
        },
        "diagnostic_totals": {
            key: sum(int(episode["ours_diagnostics"][key]) for episode in episodes)
            for key in numeric_diagnostics
        },
        "pairs": paired_results,
        "episodes": episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="main.py")
    parser.add_argument(
        "--opponent",
        default="crop-specialist",
        help="Kaggle built-in, file path, or frozen alias: " + ", ".join(sorted(FROZEN_OPPONENTS)),
    )
    parser.add_argument("--pairs", "--games", dest="pairs", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--episode-steps", type=int, default=720)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replays-dir", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    replays_dir = args.replays_dir
    if replays_dir is None and args.output is not None:
        replays_dir = args.output.parent / f"{args.output.stem}-episodes"
    report = run_paired_tournament(
        resolve_agent(args.agent),
        resolve_agent(args.opponent),
        pairs=args.pairs,
        seed=args.seed,
        episode_steps=args.episode_steps,
        replays_dir=replays_dir,
    )
    report["agent"] = args.agent
    report["opponent"] = args.opponent
    printable = dict(report)
    if args.summary_only:
        printable.pop("episodes", None)
        printable.pop("pairs", None)
    print(json.dumps(printable, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
