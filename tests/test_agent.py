from __future__ import annotations

import importlib.util
from pathlib import Path

from kaggle_environments import make


ROOT = Path(__file__).resolve().parents[1]


def load_agent():
    spec = importlib.util.spec_from_file_location("submission_main", ROOT / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def test_agent_finishes_full_episode_against_starter():
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 12345},
        debug=True,
    )
    env.run([load_agent(), "starter"])
    final = env.steps[-1]
    assert [state.status for state in final] == ["DONE", "DONE"]
    assert float(final[0].reward) > float(final[1].reward)


def test_self_play_is_valid():
    policy = load_agent()
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": 54321},
        debug=True,
    )
    env.run([policy, policy])
    assert [state.status for state in env.steps[-1]] == ["DONE", "DONE"]

