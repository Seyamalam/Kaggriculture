from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

from kaggle_environments import make

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.frozen_opponents import crop_specialist


SPEC = importlib.util.spec_from_file_location(
    "candidate_v3_sheep_under_test",
    ROOT / "agents" / "candidate_v3_sheep.py",
)
assert SPEC is not None and SPEC.loader is not None
candidate_v3_sheep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate_v3_sheep)


def _observation(*, day: int, farmer: tuple[int, int], carried_wheat: int = 0) -> dict[str, Any]:
    tiles: list[list[Any]] = [
        [None if x < 5 and y < 5 else "LOCKED" for x in range(10)]
        for y in range(10)
    ]
    tiles[3][3] = {
        "kind": "PASTURE",
        "animal": "SHEEP",
        "placed_day": 0,
        "yield_units": 0,
        "consecutive_unfed": 0,
        "fed_today": False,
        "cared_today": False,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }
    farm = {
        "money": 3_000,
        "tiles": tiles,
        "farmer": list(farmer),
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    opponent = {
        **farm,
        "tiles": [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)],
    }
    inventory = {"WHEAT": carried_wheat} if carried_wheat else {}
    crops = tuple(candidate_v3_sheep.CROPS)
    prices = {crop: candidate_v3_sheep.CROPS[crop]["base"] for crop in crops}
    prices.update({"EGG": 50, "MILK": 160, "WOOL": 200, "FERTILIZER": 100})
    return {
        "player": 0,
        "step": day * 24,
        "day": day,
        "hour": 0,
        "farms": [farm, opponent],
        "private": {
            "shed": {"WHEAT": 1},
            "seeds": {crop: 0 for crop in crops},
            "inventories": [inventory],
        },
        "market": {
            "inventory": {item: 10_000 for item in prices},
            "prices": prices,
        },
        "town": {"unlocked_shops": []},
    }


def test_pickup_routes_to_an_unlocked_shed_access_tile() -> None:
    obs = _observation(day=1, farmer=(4, 5))

    farmer, _hands = candidate_v3_sheep._unit_actions(obs)

    assert obs["farms"][0]["tiles"][5][4] == "LOCKED"
    assert farmer == ["NORTH"]


def test_final_day_carried_wheat_is_not_assigned_to_feed() -> None:
    obs = _observation(day=29, farmer=(3, 3), carried_wheat=1)

    farmer, _hands = candidate_v3_sheep._unit_actions(obs)

    assert farmer != ["FEED"]
    assert farmer in (["EAST"], ["SOUTH"])


def test_agent_impl_completes_paired_episodes_without_fallback() -> None:
    candidate_v3_sheep.FALLBACK_COUNT = 0
    for candidate_seat in (0, 1):
        env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 77123}, debug=True)
        agents = (
            [candidate_v3_sheep._agent_impl, crop_specialist]
            if candidate_seat == 0
            else [crop_specialist, candidate_v3_sheep._agent_impl]
        )
        env.run(agents)
        assert env.steps[-1][candidate_seat].status == "DONE"

    assert candidate_v3_sheep.FALLBACK_COUNT == 0


def test_agent_wrapper_records_no_fallbacks_over_a_complete_episode() -> None:
    candidate_v3_sheep.FALLBACK_COUNT = 0
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 77124}, debug=True)

    env.run([candidate_v3_sheep.agent, crop_specialist])

    assert env.steps[-1][0].status == "DONE"
    assert candidate_v3_sheep.FALLBACK_COUNT == 0
