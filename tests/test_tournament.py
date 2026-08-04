from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.frozen_opponents import crop_specialist, diversified_baseline
from scripts.tournament import run_game, run_paired_tournament


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
    replay_files = sorted(tmp_path.glob("*.json"))
    assert len(replay_files) == 4
    assert all(json.loads(path.read_text(encoding="utf-8"))["name"] == "kaggriculture" for path in replay_files)


def test_terminal_diagnostics_include_seed_cost_and_standing_yield():
    result = run_game(seeded_carrot_agent, pass_agent, 123, episode_steps=96)
    diagnostics = result["diagnostics"][0]

    assert diagnostics["terminal_seed_counts"] == {"CARROT": 1}
    assert diagnostics["terminal_seed_cost"] == 20
    assert diagnostics["terminal_field_yield_by_product"] == {"CARROT": 3}
    assert diagnostics["terminal_field_yield_units"] == 3
    assert diagnostics["terminal_field_yield_market_value"] > 0


def test_frozen_opponents_are_observation_deterministic():
    # A real initial observation catches accidental random/global-state use and
    # guarantees that each policy emits exactly one action per existing hand.
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 24, "seed": 9}, debug=True)
    env.run([pass_agent, pass_agent])
    observation = env.steps[0][0].observation
    for policy in (crop_specialist, diversified_baseline):
        first = policy(observation)
        second = policy(observation)
        assert first == second
        assert len(first["hands"]) == len(observation.farms[0].hands)
