"""Isolated market-policy ablations for candidate-v3 sheep.

Each arm temporarily wraps ``candidate_v3_sheep._market_actions`` and restores
the original function after its paired tournaments, including on failure.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterator

try:
    from scripts.tournament import run_paired_tournament
except ModuleNotFoundError:  # Direct ``python scripts/v3_strategy_ablation.py``.
    from tournament import run_paired_tournament


ROOT = Path(__file__).resolve().parents[1]
ARMS = ("baseline", "two-quadrant", "strawberry-hedge", "wool-hold")
DEFAULT_BLOCKS = (53001, 54001)
RELEVANT_STRAWBERRY_SHOPS = {
    "ICE_CREAM_SHOP",
    "FARMERS_MARKET",
    "BRUNCH_SPOT",
    "SMOOTHIE_SHOP",
}
Agent = Callable[[dict[str, Any]], dict[str, Any]]


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _opponent_strawberries(obs: dict[str, Any]) -> int:
    player = int(obs["player"])
    if len(obs["farms"]) < 2:
        return 0
    return sum(
        1
        for row in obs["farms"][1 - player]["tiles"]
        for tile in row
        if isinstance(tile, dict)
        and tile.get("kind") == "PLANT"
        and tile.get("crop") == "STRAWBERRY"
    )


def _conservative_remaining_money(candidate: Any, obs: dict[str, Any], orders: list[list[Any]]) -> float:
    """Ignore sale proceeds and reserve cash for every earlier purchase order."""
    player = int(obs["player"])
    farm = obs["farms"][player]
    money = float(farm["money"])
    unlocked = len(farm.get("unlocked_quadrants", ["NW"]))
    hires = int(farm.get("hires_today", 0))
    for order in orders:
        if not isinstance(order, list) or not order:
            continue
        op = order[0]
        if op == "BUY_LAND" and unlocked <= len(candidate.LAND_PRICES):
            money -= candidate.LAND_PRICES[unlocked - 1]
            unlocked += 1
        elif op == "BUY_ANIMAL" and len(order) >= 3 and order[1] == "SHEEP":
            money -= candidate.SHEEP_COST * int(order[2])
        elif op == "BUY_PRODUCT" and len(order) >= 3:
            money -= int(obs["market"]["prices"].get(order[1], 0)) * int(order[2])
        elif op == "BUY_SEED" and len(order) >= 3 and order[1] in candidate.CROPS:
            money -= int(candidate.CROPS[order[1]]["seed"]) * int(order[2])
        elif op == "HIRE":
            money -= candidate.FIB_HIRE_COSTS[hires]
            hires += 1
    return money


def _wrapper(candidate: Any, arm: str, original: Callable[..., list[list[Any]]]) -> Callable[..., list[list[Any]]]:
    if arm == "baseline":
        return original

    if arm == "two-quadrant":
        def two_quadrant(obs: dict[str, Any]) -> list[list[Any]]:
            orders = original(obs)
            unlocked = len(obs["farms"][int(obs["player"])].get("unlocked_quadrants", ["NW"]))
            if unlocked < 2:
                return orders
            return [order for order in orders if not (isinstance(order, list) and order[:1] == ["BUY_LAND"])]
        return two_quadrant

    if arm == "strawberry-hedge":
        def strawberry_hedge(obs: dict[str, Any]) -> list[list[Any]]:
            orders = original(obs)
            day = int(obs.get("day", 0))
            shops = set(obs.get("town", {}).get("unlocked_shops", []))
            triggered = bool(shops & RELEVANT_STRAWBERRY_SHOPS) or _opponent_strawberries(obs) >= 4
            if day > 9 or not triggered or len(orders) >= 10:
                return orders
            private = obs["private"]
            pending = int(private.get("seeds", {}).get("STRAWBERRY", 0)) + sum(
                int(order[2])
                for order in orders
                if isinstance(order, list) and order[:2] == ["BUY_SEED", "STRAWBERRY"] and len(order) >= 3
            )
            count = max(0, 2 - pending)
            if count <= 0:
                return orders
            remaining = _conservative_remaining_money(candidate, obs, orders)
            affordable = max(0, int((remaining - 200) // candidate.CROPS["STRAWBERRY"]["seed"]))
            count = min(count, affordable)
            if count > 0:
                orders.append(["BUY_SEED", "STRAWBERRY", count])
            return orders[:10]
        return strawberry_hedge

    if arm == "wool-hold":
        def wool_hold(obs: dict[str, Any]) -> list[list[Any]]:
            orders = original(obs)
            shed_wool = int(obs["private"].get("shed", {}).get("WOOL", 0))
            day = int(obs.get("day", 0))
            shops = set(obs.get("town", {}).get("unlocked_shops", []))
            wool_price = int(obs["market"].get("prices", {}).get("WOOL", 0))
            hold = (
                shed_wool < 24
                and day < 24
                and "YARN_STORE" not in shops
                and wool_price < 240
            )
            if not hold:
                return orders
            return [
                order
                for order in orders
                if not (isinstance(order, list) and order[:2] == ["SELL", "WOOL"])
            ]
        return wool_hold

    raise ValueError(f"unknown arm {arm!r}")


@contextmanager
def strategy_arm(candidate: Any, arm: str) -> Iterator[Agent]:
    original = candidate._market_actions
    wrapped = _wrapper(candidate, arm, original)
    candidate._market_actions = wrapped
    try:
        yield candidate.agent
    finally:
        candidate._market_actions = original


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key not in ("episodes", "pairs")}


def run_ablation(*, pairs: int, blocks: tuple[int, ...], arms: tuple[str, ...]) -> dict[str, Any]:
    if pairs <= 0:
        raise ValueError("pairs must be positive")
    if not blocks:
        raise ValueError("at least one seed block is required")
    if not arms or any(arm not in ARMS for arm in arms):
        raise ValueError(f"arms must be a non-empty subset of {ARMS}")
    candidate = _load_module(ROOT / "agents" / "candidate_v3_sheep.py", "candidate_v3_strategy_ablation")
    opponent = _load_module(ROOT / "main.py", "main_v1_strategy_ablation")
    original_market = candidate._market_actions
    results: dict[str, dict[str, Any]] = {}

    for arm in arms:
        arm_results: dict[str, Any] = {}
        for block in blocks:
            with strategy_arm(candidate, arm) as policy:
                report = run_paired_tournament(policy, opponent.agent, pairs=pairs, seed=block)
            if candidate._market_actions is not original_market:
                raise RuntimeError(f"market planner was not restored after {arm}/{block}")
            arm_results[str(block)] = _summary(report)
        results[arm] = arm_results

    aggregate: dict[str, Any] = {}
    for arm, block_results in results.items():
        reports = list(block_results.values())
        aggregate[arm] = {
            "mean_ours": mean(float(report["mean_ours"]) for report in reports),
            "mean_theirs": mean(float(report["mean_theirs"]) for report in reports),
            "mean_episode_margin": mean(float(report["mean_episode_margin"]) for report in reports),
            "mean_paired_margin": mean(float(report["mean_paired_margin"]) for report in reports),
            "paired_wins": sum(int(report["paired_wins"]) for report in reports),
            "paired_ties": sum(int(report["paired_ties"]) for report in reports),
        }

    recommendations: list[dict[str, Any]] = []
    if "baseline" in aggregate:
        baseline = aggregate["baseline"]
        for arm in arms:
            if arm == "baseline":
                continue
            deltas = {
                block: float(results[arm][str(block)]["mean_paired_margin"])
                - float(results["baseline"][str(block)]["mean_paired_margin"])
                for block in blocks
            }
            aggregate[arm]["paired_margin_delta_vs_baseline"] = mean(deltas.values())
            aggregate[arm]["block_deltas_vs_baseline"] = {str(k): v for k, v in deltas.items()}
            if aggregate[arm]["paired_margin_delta_vs_baseline"] > 0 and all(delta > 0 for delta in deltas.values()):
                recommendations.append(
                    {
                        "arm": arm,
                        "mean_paired_margin_delta": aggregate[arm]["paired_margin_delta_vs_baseline"],
                        "block_deltas": aggregate[arm]["block_deltas_vs_baseline"],
                    }
                )

    return {
        "candidate": "agents/candidate_v3_sheep.py",
        "opponent": "main.py",
        "pairs_per_block": pairs,
        "blocks": list(blocks),
        "arms": list(arms),
        "results": results,
        "aggregate": aggregate,
        "independently_positive_recommendations": recommendations,
        "recommendation_rule": "positive mean paired-margin delta and positive delta in every tested block",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--blocks", type=int, nargs="+", default=list(DEFAULT_BLOCKS))
    parser.add_argument("--arms", nargs="+", default=list(ARMS), choices=ARMS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_ablation(
        pairs=args.pairs,
        blocks=tuple(dict.fromkeys(args.blocks)),
        arms=tuple(dict.fromkeys(args.arms)),
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
