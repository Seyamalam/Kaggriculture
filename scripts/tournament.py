"""Run a seeded local tournament and print a compact JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from kaggle_environments import make


def _inventory_total(private: dict[str, object]) -> int:
    shed = private.get("shed", {}) or {}
    inventories = private.get("inventories", []) or []
    return sum(int(value) for value in shed.values()) + sum(
        int(value) for inventory in inventories for value in inventory.values()
    )


def episode_diagnostics(env, player: int) -> dict[str, object]:
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
            carried = sum(
                int(value)
                for inventory in previous_private.inventories
                for value in inventory.values()
            )
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

    final_private = env.steps[-1][player].observation.private
    return {
        "preventable_weeds": preventable_weeds,
        "end_of_day_capacity_pressure": capacity_pressure,
        "zero_cash_days": zero_cash_days,
        "terminal_unsold_items": _inventory_total(final_private),
        "max_hands_by_day": max_hands_by_day,
    }


def run_game(left: str, right: str, seed: int) -> dict[str, object]:
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": seed},
        debug=True,
    )
    env.run([left, right])
    final = env.steps[-1]
    rewards = [float(state.reward or 0.0) for state in final]
    statuses = [str(state.status) for state in final]
    diagnostics = [episode_diagnostics(env, 0), episode_diagnostics(env, 1)]
    return {"seed": seed, "rewards": rewards, "statuses": statuses, "diagnostics": diagnostics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default="main.py")
    parser.add_argument("--opponent", default="starter")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    games = []
    for offset in range(args.games):
        seed = args.seed + offset
        # Swap seats to detect player-order bias.
        if offset % 2 == 0:
            result = run_game(args.agent, args.opponent, seed)
            ours, theirs = result["rewards"]
            ours_diagnostics = result["diagnostics"][0]
        else:
            result = run_game(args.opponent, args.agent, seed)
            theirs, ours = result["rewards"]
            ours_diagnostics = result["diagnostics"][1]
        result["ours"] = ours
        result["theirs"] = theirs
        result["ours_diagnostics"] = ours_diagnostics
        result["win"] = int(ours > theirs)
        result["tie"] = int(ours == theirs)
        games.append(result)

    report = {
        "agent": args.agent,
        "opponent": args.opponent,
        "games": args.games,
        "wins": sum(int(game["win"]) for game in games),
        "ties": sum(int(game["tie"]) for game in games),
        "mean_ours": mean(float(game["ours"]) for game in games),
        "mean_theirs": mean(float(game["theirs"]) for game in games),
        "diagnostic_totals": {
            key: sum(int(game["ours_diagnostics"][key]) for game in games)
            for key in (
                "preventable_weeds",
                "end_of_day_capacity_pressure",
                "zero_cash_days",
                "terminal_unsold_items",
            )
        },
        "episodes": games,
    }
    printable = dict(report)
    if args.summary_only:
        printable.pop("episodes", None)
    rendered = json.dumps(printable, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
