from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.frozen_opponents import animal_specialist, crop_specialist, diversified_baseline
from scripts.tournament import _wilson_interval, run_game, run_paired_tournament


def pass_agent(obs):
    hands = [["PASS"] for _ in obs["farms"][obs["player"]].get("hands", [])]
    return {"farmer": ["PASS"], "hands": hands, "market": []}


def seeded_carrot_agent(obs):
    farm = obs["farms"][obs["player"]]
    private = obs["private"]
    x, y = farm["farmer"]
    tile = farm["tiles"][y][x]
    market = [["BUY_SEED", "CARROT", 2]] if int(obs.get("step", 0)) == 0 else []
    farmer = ["PASS"]
    if tile is None and int(private["seeds"].get("CARROT", 0)):
        farmer = ["PLANT", "CARROT"]
    elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today"):
        farmer = ["WATER"]
    return {"farmer": farmer, "hands": [], "market": market}


def stockpiled_fertilizer_agent(obs):
    market = [["BUY_PRODUCT", "FERTILIZER", 2]] if int(obs.get("step", 0)) == 0 else []
    return {"farmer": ["PASS"], "hands": [], "market": market}


def test_paired_tournament_reuses_each_seed_in_both_seats(tmp_path):
    report = run_paired_tournament(
        pass_agent,
        pass_agent,
        pairs=2,
        seed=77,
        episode_steps=24,
        replays_dir=tmp_path,
    )

    assert [episode["seed"] for episode in report["episodes"]] == [77, 77, 78, 78]
    assert [episode["candidate_seat"] for episode in report["episodes"]] == [0, 1, 0, 1]
    assert report["episodes_played"] == 4
    assert report["episode_win_rate"] == 0.0
    assert report["episode_tie_rate"] == 1.0
    assert report["episode_loss_rate"] == 0.0
    assert report["paired_win_rate"] == 0.0
    assert report["paired_tie_rate"] == 1.0
    assert report["paired_loss_rate"] == 0.0
    assert report["median_ours"] == 3000.0
    assert report["median_theirs"] == 3000.0
    assert report["median_episode_margin"] == 0.0
    assert report["episode_win_rate_wilson_95"]["low"] == 0.0
    assert 0.48 < report["episode_win_rate_wilson_95"]["high"] < 0.50
    replay_files = sorted(tmp_path.glob("*.json"))
    assert len(replay_files) == 4
    assert all(json.loads(path.read_text(encoding="utf-8"))["name"] == "kaggriculture" for path in replay_files)


def test_wilson_interval_matches_known_balanced_case():
    interval = _wilson_interval(5, 10)

    assert interval["low"] == pytest.approx(0.236593, abs=1e-6)
    assert interval["high"] == pytest.approx(0.763407, abs=1e-6)


def test_terminal_diagnostics_include_seed_cost_and_standing_yield():
    result = run_game(seeded_carrot_agent, pass_agent, 123, episode_steps=96)
    diagnostics = result["diagnostics"][0]

    assert diagnostics["terminal_seed_counts"] == {"CARROT": 1}
    assert diagnostics["terminal_seed_cost"] == 20
    assert diagnostics["terminal_field_yield_by_product"] == {"CARROT": 3}
    assert diagnostics["terminal_field_yield_units"] == 3
    assert diagnostics["terminal_field_yield_market_value"] > 0


def test_terminal_diagnostics_value_fertilizer_inventory():
    result = run_game(stockpiled_fertilizer_agent, pass_agent, 456, episode_steps=24)
    diagnostics = result["diagnostics"][0]

    assert diagnostics["terminal_unsold_by_product"] == {"FERTILIZER": 2}
    assert diagnostics["terminal_unsold_items"] == 2
    assert diagnostics["terminal_unsold_market_value"] == 200
    assert diagnostics["terminal_non_cash_value"] == 200


def test_frozen_opponents_are_observation_deterministic():
    # A real initial observation catches accidental random/global-state use and
    # guarantees that each policy emits exactly one action per existing hand.
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 24, "seed": 9}, debug=True)
    env.run([pass_agent, pass_agent])
    observation = env.steps[0][0].observation
    for policy in (crop_specialist, diversified_baseline, animal_specialist):
        first = policy(observation)
        second = policy(observation)
        assert first == second
        assert len(first["hands"]) == len(observation.farms[0].hands)


def test_animal_specialist_exercises_the_full_livestock_loop():
    from kaggle_environments import make

    unit_ops: set[str] = set()
    market_ops: set[tuple[str, str | None]] = set()

    def recording_agent(obs):
        action = animal_specialist(obs)
        unit_ops.update(
            operation[0]
            for operation in [action["farmer"], *action["hands"]]
            if operation
        )
        market_ops.update(
            (order[0], str(order[1]) if len(order) > 1 else None)
            for order in action["market"]
            if order
        )
        return action

    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 31415}, debug=True)
    env.run([recording_agent, diversified_baseline])

    assert [state.status for state in env.steps[-1]] == ["DONE", "DONE"]
    assert float(env.steps[-1][0].reward) > float(env.steps[-1][1].reward)
    assert {
        "BUILD_COOP",
        "BUILD_PASTURE",
        "PLACE",
        "FEED",
        "CARE",
        "HARVEST",
        "COLLECT_FERTILIZER",
        "FERTILIZE",
    } <= unit_ops
    assert {
        ("BUY_ANIMAL", "GOOSE"),
        ("BUY_ANIMAL", "COW"),
        ("BUY_ANIMAL", "SHEEP"),
        ("BUY_LAND", None),
        ("SELL", "FERTILIZER"),
    } <= market_ops
