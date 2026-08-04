"""Paired ablation of four, six, and eight sheep for candidate v4.

The v4 policy remains unchanged.  Each arm temporarily replaces its pasture
layout and appends at most one extra sheep purchase after the policy's normal
market orders.  Replays are retained only in a temporary directory long enough
to audit sheep lifecycle and pickup/placement behavior.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from statistics import mean
import tempfile
from typing import Any, Callable, Iterator

try:
    from scripts.frozen_opponents import animal_specialist
    from scripts.tournament import run_paired_tournament
except ModuleNotFoundError:  # Direct ``python scripts/v4_sheep_scale_ablation.py``.
    from frozen_opponents import animal_specialist
    from tournament import run_paired_tournament


ROOT = Path(__file__).resolve().parents[1]
BASE_LAYOUT = ((4, 3), (3, 4), (3, 3), (2, 4))
EXTRA_LAYOUT = ((5, 3), (6, 3), (6, 4), (7, 4))
LAYOUTS = {
    4: BASE_LAYOUT,
    6: BASE_LAYOUT + EXTRA_LAYOUT[:2],
    8: BASE_LAYOUT + EXTRA_LAYOUT,
}
SHED_ACCESS = {(4, 4), (5, 4), (4, 5), (5, 5)}
Agent = Callable[[dict[str, Any]], dict[str, Any]]


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _quadrant(position: tuple[int, int]) -> str:
    x, y = position
    return ("N" if y < 5 else "S") + ("W" if x < 5 else "E")


def _validate_layout(layout: tuple[tuple[int, int], ...]) -> None:
    if len(set(layout)) != len(layout):
        raise ValueError(f"duplicate pasture target in {layout}")
    forbidden = set(layout) & SHED_ACCESS
    if forbidden:
        raise ValueError(f"pasture target overlaps shed access: {sorted(forbidden)}")
    invalid_quadrants = {position: _quadrant(position) for position in layout if _quadrant(position) not in ("NW", "NE")}
    if invalid_quadrants:
        raise ValueError(f"pastures require land v4 never unlocks: {invalid_quadrants}")


def _sheep_in_system(obs: dict[str, Any]) -> int:
    player = int(obs["player"])
    farm = obs["farms"][player]
    private = obs["private"]
    placed = sum(
        1
        for row in farm["tiles"]
        for tile in row
        if isinstance(tile, dict) and tile.get("animal") == "SHEEP"
    )
    shed = int(private.get("shed", {}).get("SHEEP", 0))
    carried = sum(int(inventory.get("SHEEP", 0)) for inventory in private.get("inventories", []))
    return placed + shed + carried


def _reserved_cash(candidate: Any, obs: dict[str, Any], orders: list[list[Any]]) -> float:
    """Conservatively reserve money for every existing non-sale order."""
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
        elif op == "BUY_ANIMAL" and order[1:2] == ["SHEEP"]:
            money -= candidate.SHEEP_COST * int(order[2])
        elif op == "BUY_PRODUCT" and len(order) >= 3:
            money -= int(obs["market"]["prices"].get(order[1], 0)) * int(order[2])
        elif op == "BUY_SEED" and len(order) >= 3 and order[1] in candidate.CROPS:
            money -= int(candidate.CROPS[order[1]]["seed"]) * int(order[2])
        elif op == "HIRE":
            if hires < len(candidate.FIB_HIRE_COSTS):
                money -= candidate.FIB_HIRE_COSTS[hires]
            hires += 1
    return money


@contextmanager
def sheep_scale(candidate: Any, count: int) -> Iterator[Agent]:
    layout = LAYOUTS[count]
    _validate_layout(layout)
    original_tiles = tuple(candidate.SHEEP_TILES)
    original_market = candidate._market_actions

    def scaled_market(obs: dict[str, Any]) -> list[list[Any]]:
        orders = original_market(obs)
        day = int(obs.get("day", 0))
        owned = _sheep_in_system(obs) + sum(
            int(order[2])
            for order in orders
            if isinstance(order, list) and order[:2] == ["BUY_ANIMAL", "SHEEP"] and len(order) >= 3
        )
        if count <= 4 or day < 7 or day > 16 or owned >= count or len(orders) >= 10:
            return orders
        remaining = _reserved_cash(candidate, obs, orders)
        # Preserve two days of feed and a modest operating reserve after the
        # appended purchase. Existing feed/animal/hire orders execute first.
        reserve = 250 + (owned + 1) * 25 * 2
        if remaining >= candidate.SHEEP_COST + reserve:
            orders.append(["BUY_ANIMAL", "SHEEP", 1])
        return orders[:10]

    candidate.SHEEP_TILES = layout
    candidate._market_actions = scaled_market
    try:
        yield candidate.agent
    finally:
        candidate.SHEEP_TILES = original_tiles
        candidate._market_actions = original_market


def _unit_actions(action: Any) -> list[list[Any]]:
    if not isinstance(action, dict):
        return []
    hands = action.get("hands", []) if isinstance(action.get("hands", []), list) else []
    farmer = action.get("farmer", ["PASS"])
    return [farmer, *hands]


def _replay_evidence(path: Path, candidate_seat: int) -> dict[str, Any]:
    replay = json.loads(path.read_text(encoding="utf-8"))
    sheep_counts: list[int] = []
    purchases = 0
    placements = 0
    pickup_sheep = 0
    invalid_pickups = 0
    invalid_placements = 0
    for states in replay["steps"]:
        state = states[candidate_seat]
        observation = state["observation"]
        farm = observation["farms"][candidate_seat]
        sheep_counts.append(
            sum(
                1
                for row in farm["tiles"]
                for tile in row
                if isinstance(tile, dict) and tile.get("animal") == "SHEEP"
            )
        )
        action = state.get("action") or {}
        for order in action.get("market", []) if isinstance(action, dict) else []:
            if isinstance(order, list) and order[:2] == ["BUY_ANIMAL", "SHEEP"] and len(order) >= 3:
                purchases += int(order[2])
        positions = [tuple(farm["farmer"]), *(tuple(position) for position in farm.get("hands", []))]
        for index, unit_action in enumerate(_unit_actions(action)):
            if not isinstance(unit_action, list):
                continue
            if unit_action[:2] == ["PICKUP", "SHEEP"]:
                pickup_sheep += 1
                if index >= len(positions) or positions[index] not in SHED_ACCESS:
                    invalid_pickups += 1
            if unit_action[:2] == ["PLACE", "SHEEP"]:
                placements += 1
                if index >= len(positions):
                    invalid_placements += 1
                else:
                    x, y = positions[index]
                    tile = farm["tiles"][y][x]
                    if not (isinstance(tile, dict) and tile.get("animal") == "SHEEP"):
                        invalid_placements += 1
    escapes = sum(max(0, before - after) for before, after in zip(sheep_counts, sheep_counts[1:]))
    return {
        "purchased": purchases,
        "placement_actions": placements,
        "sheep_pickups": pickup_sheep,
        "invalid_shed_pickups": invalid_pickups,
        "invalid_placements": invalid_placements,
        "max_sheep": max(sheep_counts, default=0),
        "final_sheep": sheep_counts[-1] if sheep_counts else 0,
        "escapes": escapes,
    }


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key not in ("episodes", "pairs")}


def run_ablation(
    *,
    pairs: int,
    seed: int,
    counts: tuple[int, ...],
    opponent_names: tuple[str, ...] = ("v1", "animal-specialist"),
) -> dict[str, Any]:
    if pairs <= 0:
        raise ValueError("pairs must be positive")
    if not counts or any(count not in LAYOUTS for count in counts):
        raise ValueError(f"counts must be a non-empty subset of {tuple(LAYOUTS)}")
    for count in counts:
        _validate_layout(LAYOUTS[count])

    candidate = _load_module(ROOT / "agents" / "candidate_v4_landcap.py", "candidate_v4_scale_ablation")
    v1 = _load_module(ROOT / "main.py", "main_v1_scale_ablation")
    available_opponents: dict[str, Agent] = {"v1": v1.agent, "animal-specialist": animal_specialist}
    if not opponent_names or any(name not in available_opponents for name in opponent_names):
        raise ValueError(f"opponents must be a non-empty subset of {tuple(available_opponents)}")
    opponents = {name: available_opponents[name] for name in opponent_names}
    original_tiles = tuple(candidate.SHEEP_TILES)
    original_market = candidate._market_actions
    results: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="kaggriculture-v4-scale-") as temporary:
        temp_root = Path(temporary)
        for count in counts:
            count_results: dict[str, Any] = {}
            for opponent_name, opponent in opponents.items():
                replay_dir = temp_root / f"{count}-{opponent_name}"
                with sheep_scale(candidate, count) as policy:
                    report = run_paired_tournament(
                        policy,
                        opponent,
                        pairs=pairs,
                        seed=seed,
                    )
                # Keep lifecycle replay evidence bounded to one paired seed;
                # tournament scores and diagnostics above still use all pairs.
                with sheep_scale(candidate, count) as policy:
                    evidence_report = run_paired_tournament(
                        policy,
                        opponent,
                        pairs=1,
                        seed=seed,
                        replays_dir=replay_dir,
                    )
                if tuple(candidate.SHEEP_TILES) != original_tiles or candidate._market_actions is not original_market:
                    raise RuntimeError(f"candidate globals not restored after {count}/{opponent_name}")
                evidence = [
                    _replay_evidence(Path(episode["replay_file"]), int(episode["candidate_seat"]))
                    for episode in evidence_report["episodes"]
                ]
                count_results[opponent_name] = {
                    "tournament": _summary(report),
                    "sheep_evidence": {
                        "sampled_episodes": len(evidence),
                        "purchased_total": sum(item["purchased"] for item in evidence),
                        "placements_total": sum(item["placement_actions"] for item in evidence),
                        "pickups_total": sum(item["sheep_pickups"] for item in evidence),
                        "escapes_total": sum(item["escapes"] for item in evidence),
                        "invalid_shed_pickups": sum(item["invalid_shed_pickups"] for item in evidence),
                        "invalid_placements": sum(item["invalid_placements"] for item in evidence),
                        "mean_final_sheep": mean(item["final_sheep"] for item in evidence),
                        "min_final_sheep": min(item["final_sheep"] for item in evidence),
                        "max_observed_sheep": max(item["max_sheep"] for item in evidence),
                    },
                }
            results[str(count)] = count_results

    recommendations: list[dict[str, Any]] = []
    baseline = results.get("4")
    if baseline:
        for count in counts:
            if count == 4:
                continue
            deltas = {
                opponent: float(results[str(count)][opponent]["tournament"]["mean_paired_margin"])
                - float(baseline[opponent]["tournament"]["mean_paired_margin"])
                for opponent in opponents
            }
            clean = all(
                results[str(count)][opponent]["sheep_evidence"][key] == 0
                for opponent in opponents
                for key in ("escapes_total", "invalid_shed_pickups", "invalid_placements")
            ) and all(
                sum(results[str(count)][opponent]["tournament"]["diagnostic_totals"].values()) == 0
                for opponent in opponents
            )
            if all(delta > 0 for delta in deltas.values()) and clean:
                recommendations.append({"sheep_count": count, "paired_margin_deltas": deltas})

    return {
        "candidate": "agents/candidate_v4_landcap.py",
        "seed_pairs": pairs,
        "base_seed": seed,
        "counts": list(counts),
        "layouts": {str(count): [list(position) for position in LAYOUTS[count]] for count in counts},
        "layout_validation": {
            "shed_access": [list(position) for position in sorted(SHED_ACCESS)],
            "all_targets_outside_shed_access": True,
            "all_targets_in_v4_unlocked_quadrants": True,
        },
        "results": results,
        "independently_positive_recommendations": recommendations,
        "recommendation_rule": "positive paired-margin delta vs four sheep for both opponents, zero escapes/invalid actions/diagnostics",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--seed", type=int, default=58001)
    parser.add_argument("--counts", type=int, nargs="+", default=list(LAYOUTS))
    parser.add_argument("--opponents", nargs="+", default=["v1", "animal-specialist"], choices=["v1", "animal-specialist"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_ablation(
        pairs=args.pairs,
        seed=args.seed,
        counts=tuple(dict.fromkeys(args.counts)),
        opponent_names=tuple(dict.fromkeys(args.opponents)),
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
