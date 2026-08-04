from __future__ import annotations

import importlib.util
from pathlib import Path

from kaggle_environments import make


ROOT = Path(__file__).resolve().parents[1]


def load_candidate_v4():
    spec = importlib.util.spec_from_file_location(
        "candidate_v4_landcap_test",
        ROOT / "agents" / "candidate_v4_landcap.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_v4_is_valid_and_never_requests_third_land():
    policy = load_candidate_v4().agent
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 64001},
        debug=True,
    )
    env.run([policy, "starter"])
    assert [state.status for state in env.steps[-1]] == ["DONE", "DONE"]

    buy_land_requests = 0
    for index in range(1, len(env.steps)):
        action = env.steps[index][0].action
        if not isinstance(action, dict):
            continue
        market = action.get("market", [])
        if not any(isinstance(order, list) and order[:1] == ["BUY_LAND"] for order in market):
            continue
        buy_land_requests += 1
        previous_farm = env.steps[index - 1][0].observation.farms[0]
        assert len(previous_farm.unlocked_quadrants) < 2

    assert buy_land_requests == 1
    assert len(env.steps[-1][0].observation.farms[0].unlocked_quadrants) == 2


def test_candidate_v4_fallback_preserves_observable_hand_shape():
    policy = load_candidate_v4().agent
    malformed = {
        "player": 0,
        "farms": [{"hands": [[0, 0], [1, 1]]}],
    }
    assert policy(malformed) == {
        "farmer": ["PASS"],
        "hands": [["PASS"], ["PASS"]],
        "market": [],
    }
