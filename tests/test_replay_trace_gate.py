from __future__ import annotations

import json
from pathlib import Path
import sys

from kaggle_environments import make

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.replay_trace_gate import (
    RecordedActionPolicy,
    resolve_recorded_seat,
    run_replay_trace_gate,
)


def _pass_action(obs):
    hands = [["PASS"] for _ in obs["farms"][obs["player"]].get("hands", [])]
    return {"farmer": ["PASS"], "hands": hands, "market": []}


def _burn_money_trace(obs):
    market = [["BUY_ANIMAL", "GOOSE", 1]] if int(obs.get("step", 0)) == 0 else []
    return {**_pass_action(obs), "market": market}


def _synthetic_replay(tmp_path: Path) -> Path:
    seed = 731
    env = make("kaggriculture", configuration={"episodeSteps": 24, "seed": seed}, debug=True)
    env.run([_burn_money_trace, _pass_action])
    replay = env.toJSON()
    replay["info"]["seed"] = seed
    replay["info"]["EpisodeId"] = "synthetic"
    replay["info"]["TeamNames"] = ["Burner", "Observer"]
    path = tmp_path / "synthetic-replay.json"
    path.write_text(json.dumps(replay), encoding="utf-8")
    return path


def _candidate_file(
    tmp_path: Path,
    *,
    increments_fallback: bool = False,
    farmer_action: str = "PASS",
) -> Path:
    increment = "global FALLBACK_COUNT; FALLBACK_COUNT += 1" if increments_fallback else "pass"
    source = f'''FALLBACK_COUNT = 0
def agent(obs):
    {increment}
    player = int(obs.get("player", 0))
    farms = obs.get("farms", [])
    hands = len(farms[player].get("hands", [])) if player < len(farms) else 0
    return {{"farmer": ["{farmer_action}"], "hands": [["PASS"] for _ in range(hands)], "market": []}}
'''
    kind = "fallback" if increments_fallback else farmer_action.casefold()
    path = tmp_path / f"{kind}_candidate.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_recorded_policy_is_step_keyed_stateless_and_has_shaped_fallback():
    replay = {
        "steps": [
            [{"observation": {"step": 7}}],
            [{"observation": {"step": 8}, "action": {"farmer": ["NORTH"], "hands": [], "market": []}}],
        ]
    }
    policy = RecordedActionPolicy(replay, 0)

    first = policy({"step": 7, "player": 0, "farms": [{"hands": []}]})
    first["farmer"][0] = "SOUTH"

    assert policy({"step": 7, "player": 0, "farms": [{"hands": []}]})["farmer"] == ["NORTH"]
    assert policy({"step": 99, "player": 0, "farms": [{"hands": [[0, 0], [1, 1]]}]}) == {
        "farmer": ["PASS"],
        "hands": [["PASS"], ["PASS"]],
        "market": [],
    }


def test_resolve_recorded_opponent_by_team_or_seat():
    replay = {"info": {"TeamNames": ["Alpha", "Beta"]}, "steps": [[{}, {}], [{}, {}]]}

    assert resolve_recorded_seat(replay, opponent_seat=1) == 1
    assert resolve_recorded_seat(replay, opponent_team="beta") == 1


def test_synthetic_trace_gate_passes_only_clean_two_seat_win(tmp_path):
    replay = _synthetic_replay(tmp_path)
    candidate = _candidate_file(tmp_path)

    report = run_replay_trace_gate(str(candidate), replay, opponent_team="Burner")

    assert report["checks"] == {
        "candidate_wins_both_seats": True,
        "zero_invalid_episodes": True,
        "zero_fallbacks_when_exposed": True,
        "zero_candidate_terminal_waste": True,
        "zero_detected_candidate_unit_noops": True,
        "overall": True,
    }
    assert [episode["candidate_seat"] for episode in report["episodes"]] == [0, 1]
    assert all(episode["candidate_reward"] == 3000 for episode in report["episodes"])
    assert all(episode["trace_reward"] == 2700 for episode in report["episodes"])
    assert all(episode["fallback_count"] == 0 for episode in report["episodes"])
    assert all(episode["unit_noop_diagnostics"]["detected_noops"] == 0 for episode in report["episodes"])
    assert "does not adapt" in report["caveat"]


def test_exposed_fallback_counter_fails_otherwise_winning_gate(tmp_path):
    replay = _synthetic_replay(tmp_path)
    candidate = _candidate_file(tmp_path, increments_fallback=True)

    report = run_replay_trace_gate(str(candidate), replay, opponent_seat=0)

    assert report["checks"]["candidate_wins_both_seats"] is True
    assert report["checks"]["zero_fallbacks_when_exposed"] is False
    assert report["checks"]["overall"] is False


def test_detected_unit_noop_fails_otherwise_winning_gate(tmp_path):
    replay = _synthetic_replay(tmp_path)
    # WATER on the initial empty tile is a silent engine no-op. The candidate
    # still beats the trace because the trace spends 300 coins on day zero.
    candidate = _candidate_file(tmp_path, farmer_action="WATER")

    report = run_replay_trace_gate(str(candidate), replay, opponent_seat=0)

    assert report["checks"]["candidate_wins_both_seats"] is True
    assert report["checks"]["zero_detected_candidate_unit_noops"] is False
    assert all(episode["unit_noop_diagnostics"]["detected_noops"] > 0 for episode in report["episodes"])
    assert report["checks"]["overall"] is False
