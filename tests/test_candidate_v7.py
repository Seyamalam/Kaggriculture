from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

from kaggle_environments import make


ROOT = Path(__file__).resolve().parents[1]
V7_PATH = ROOT / "agents" / "candidate_v7_public_v18.py"
V7_SHA256 = "603175d39f2857cbd618dc8f5ac9411e9fd234e3142777ec203342172f05a50e"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_v7_import_contract_and_public_source_hash() -> None:
    module = _load(V7_PATH, "candidate_v7_contract_test")

    assert callable(module.agent)
    assert callable(module._kaggle_submission_entrypoint)
    assert V7_PATH.read_text(encoding="utf-8").startswith("# SPDX-License-Identifier: Apache-2.0\n")
    assert hashlib.sha256(V7_PATH.read_bytes()).hexdigest() == V7_SHA256


def test_candidate_v7_beats_v6_above_100k_in_both_seats_with_valid_hand_lists() -> None:
    v7 = _load(V7_PATH, "candidate_v7_full_episode_test").agent
    v6 = _load(
        ROOT / "agents" / "candidate_v6_adaptive_livestock.py",
        "candidate_v6_v7_opponent_test",
    ).agent

    for candidate_seat in (0, 1):
        env = make(
            "kaggriculture",
            configuration={"episodeSteps": 720, "seed": 2014872257},
            debug=True,
        )
        env.run([v7, v6] if candidate_seat == 0 else [v6, v7])
        final = env.steps[-1]
        assert [state.status for state in final] == ["DONE", "DONE"]
        assert float(final[candidate_seat].reward) >= 100_000
        assert float(final[candidate_seat].reward) > float(final[1 - candidate_seat].reward)

        for index in range(1, len(env.steps)):
            previous = env.steps[index - 1][candidate_seat].observation
            action = env.steps[index][candidate_seat].action
            assert isinstance(action, dict)
            assert set(action) == {"farmer", "hands", "market"}
            assert isinstance(action["farmer"], list) and action["farmer"]
            assert isinstance(action["hands"], list)
            assert len(action["hands"]) == len(previous.farms[candidate_seat].hands)
            assert all(isinstance(hand_action, list) and hand_action for hand_action in action["hands"])
            assert isinstance(action["market"], list)
            assert len(action["market"]) <= 10
