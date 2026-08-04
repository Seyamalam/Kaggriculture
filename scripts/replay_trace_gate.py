"""Stress a candidate against one opponent action trace from a Kaggle replay.

This is deliberately *not* opponent reconstruction.  Recorded actions are
selected solely by the current observation step and never adapt after the new
episode diverges from the source replay.  A pass is useful evidence that a
candidate tolerates one historically strong production/market schedule; a
failure is actionable, but a pass does not estimate ladder win rate.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from kaggle_environments import make

try:  # Supports module and direct-script execution.
    from scripts.tournament import episode_diagnostics, resolve_agent
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI
    from tournament import episode_diagnostics, resolve_agent


ROOT = Path(__file__).resolve().parents[1]
PASS_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}
TERMINAL_WASTE_KEYS = (
    "terminal_unsold_items",
    "terminal_seed_cost",
    "terminal_field_yield_units",
    "terminal_non_cash_value",
)
Agent = Callable[[dict[str, Any]], dict[str, Any]]


def load_replay(path: str | Path) -> dict[str, Any]:
    """Load and minimally validate a Kaggle replay without copying it."""
    replay_path = Path(path).expanduser().resolve()
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ValueError("replay must contain at least two recorded steps")
    if not all(isinstance(states, list) and states for states in steps):
        raise ValueError("every replay step must contain at least one player state")
    return replay


def _team_names(replay: dict[str, Any]) -> list[str]:
    info = replay.get("info", {}) or {}
    names = info.get("TeamNames")
    if isinstance(names, list) and names:
        return [str(name) for name in names]
    agents = info.get("Agents")
    if isinstance(agents, list):
        return [str(agent.get("Name", "")) if isinstance(agent, dict) else "" for agent in agents]
    return []


def resolve_recorded_seat(
    replay: dict[str, Any],
    *,
    opponent_seat: int | None = None,
    opponent_team: str | None = None,
) -> int:
    """Resolve exactly one recorded player by numeric seat or team name."""
    if (opponent_seat is None) == (opponent_team is None):
        raise ValueError("provide exactly one of opponent_seat or opponent_team")
    player_count = len(replay["steps"][0])
    if opponent_seat is not None:
        if opponent_seat < 0 or opponent_seat >= player_count:
            raise ValueError(f"opponent seat must be between 0 and {player_count - 1}")
        return opponent_seat

    assert opponent_team is not None
    wanted = opponent_team.casefold()
    matches = [index for index, name in enumerate(_team_names(replay)) if name.casefold() == wanted]
    if len(matches) != 1:
        available = ", ".join(repr(name) for name in _team_names(replay)) or "<unavailable>"
        raise ValueError(f"team {opponent_team!r} matched {len(matches)} seats; available teams: {available}")
    return matches[0]


def _observation_step(state: dict[str, Any], fallback: int) -> int:
    observation = state.get("observation", {}) if isinstance(state, dict) else {}
    try:
        return int(observation.get("step", fallback))
    except (TypeError, ValueError):
        return fallback


class RecordedActionPolicy:
    """A stateless policy mapping observation step to a recorded action.

    Replay state ``i`` stores the action applied to state ``i - 1``.  Keys are
    therefore taken from the preceding observation rather than from call order.
    """

    def __init__(self, replay: dict[str, Any], recorded_seat: int):
        self.recorded_seat = recorded_seat
        self.actions_by_step: dict[int, dict[str, Any]] = {}
        for index in range(1, len(replay["steps"])):
            previous = replay["steps"][index - 1][recorded_seat]
            recorded = replay["steps"][index][recorded_seat]
            action = recorded.get("action") if isinstance(recorded, dict) else None
            if isinstance(action, dict):
                self.actions_by_step[_observation_step(previous, index - 1)] = deepcopy(action)

    def __call__(self, observation: dict[str, Any], configuration: Any = None) -> dict[str, Any]:
        del configuration
        step = int(observation.get("step", 0))
        action = self.actions_by_step.get(step)
        if action is not None:
            return deepcopy(action)
        farms = observation.get("farms", [])
        player = int(observation.get("player", 0))
        hand_count = len(farms[player].get("hands", [])) if player < len(farms) else 0
        return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hand_count)], "market": []}


def _candidate_path(specification: str) -> Path | None:
    path = Path(specification).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve() if path.is_file() and path.suffix == ".py" else None


def _load_candidate(specification: str) -> tuple[Any, Any | None]:
    """Load file candidates afresh so episode globals cannot leak across seats."""
    path = _candidate_path(specification)
    if path is None:
        return resolve_agent(specification), None
    module_spec = importlib.util.spec_from_file_location(f"replay_trace_candidate_{uuid4().hex}", path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"cannot import candidate {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    policy = getattr(module, "agent", None)
    if not callable(policy):
        raise ValueError(f"candidate {path} does not expose callable agent")
    return policy, module


def _replay_configuration(replay: dict[str, Any]) -> tuple[dict[str, Any], int]:
    configuration = dict(replay.get("configuration", {}) or {})
    info = replay.get("info", {}) or {}
    raw_seed = info.get("seed", configuration.get("seed"))
    if raw_seed is None:
        raise ValueError("replay does not expose its resolved seed")
    seed = int(raw_seed)
    configuration["seed"] = seed
    return configuration, seed


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def detected_unit_noops(env: Any, candidate_seat: int) -> dict[str, Any]:
    """Replay candidate unit actions against their exact pre-turn private state.

    This covers farmer/hand actions only.  Market orders are simultaneous and
    intentionally excluded rather than approximated inaccurately.
    """
    engine = importlib.import_module("kaggle_environments.envs.kaggriculture.kaggriculture")
    cfg = env.configuration
    board_size = int(_get(cfg, "boardSize", 10))
    turns_per_day = max(1, int(_get(cfg, "turnsPerDay", 24)))
    shed_capacity = int(_get(cfg, "shedCapacity", 100))
    requested = 0
    noops: dict[str, int] = {}
    samples: list[dict[str, Any]] = []

    for index in range(1, len(env.steps)):
        previous = env.steps[index - 1][candidate_seat].observation
        recorded = env.steps[index][candidate_seat]
        action = recorded.action if isinstance(recorded.action, dict) else {}
        farmer_action = action.get("farmer", ["PASS"])
        hands_actions = action.get("hands", []) if isinstance(action.get("hands", []), list) else []
        unit_actions = [farmer_action, *hands_actions]
        farm = deepcopy(previous.farms[candidate_seat])
        private = deepcopy(previous.private)

        plant_demand: dict[str, int] = {}
        for unit_action in unit_actions:
            if isinstance(unit_action, list) and len(unit_action) >= 2 and unit_action[0] == "PLANT":
                plant_demand[str(unit_action[1])] = plant_demand.get(str(unit_action[1]), 0) + 1
        seeds = private.get("seeds", {})
        blocked = {crop for crop, count in plant_demand.items() if count > int(seeds.get(crop, 0))}

        for unit_index, unit_action in enumerate(unit_actions):
            if not isinstance(unit_action, list) or not unit_action or unit_action[0] == "PASS":
                continue
            requested += 1
            applied = unit_action
            if len(unit_action) >= 2 and unit_action[0] == "PLANT" and str(unit_action[1]) in blocked:
                applied = ["PASS"]
            before = deepcopy((farm, private))
            engine._apply_unit_action(  # noqa: SLF001 - auditing the pinned engine is intentional.
                farm,
                private,
                unit_index,
                applied,
                board_size,
                int(previous.day),
                turns_per_day,
                shed_capacity,
            )
            if (farm, private) == before:
                operation = str(unit_action[0])
                noops[operation] = noops.get(operation, 0) + 1
                if len(samples) < 10:
                    samples.append(
                        {
                            "recorded_step_index": index,
                            "observation_step": int(_get(previous, "step", index - 1)),
                            "unit_index": unit_index,
                            "action": deepcopy(unit_action),
                        }
                    )

    return {
        "scope": "candidate farmer/hand actions only; simultaneous market orders are not classified",
        "requested_non_pass_actions": requested,
        "detected_noops": sum(noops.values()),
        "detected_noops_by_operation": noops,
        "samples": samples,
    }


def run_replay_trace_gate(
    candidate: str,
    replay_path: str | Path,
    *,
    opponent_seat: int | None = None,
    opponent_team: str | None = None,
) -> dict[str, Any]:
    """Run ``candidate`` in both seats against one recorded action schedule."""
    path = Path(replay_path).expanduser().resolve()
    replay = load_replay(path)
    recorded_seat = resolve_recorded_seat(
        replay,
        opponent_seat=opponent_seat,
        opponent_team=opponent_team,
    )
    configuration, seed = _replay_configuration(replay)
    episodes: list[dict[str, Any]] = []

    for candidate_seat in (0, 1):
        policy, module = _load_candidate(candidate)
        fallback_exposed = module is not None and hasattr(module, "FALLBACK_COUNT")
        if fallback_exposed:
            module.FALLBACK_COUNT = 0
        trace = RecordedActionPolicy(replay, recorded_seat)
        agents = [trace, trace]
        agents[candidate_seat] = policy
        env = make("kaggriculture", configuration=configuration, debug=True)
        env.run(agents)

        final = env.steps[-1]
        opponent_runtime_seat = 1 - candidate_seat
        rewards = [float(state.reward or 0.0) for state in final]
        statuses = [str(state.status) for state in final]
        diagnostics = episode_diagnostics(env, candidate_seat)
        fallback_count = int(module.FALLBACK_COUNT) if fallback_exposed else None
        terminal_waste = {key: int(diagnostics.get(key, 0)) for key in TERMINAL_WASTE_KEYS}
        episodes.append(
            {
                "candidate_seat": candidate_seat,
                "trace_runtime_seat": opponent_runtime_seat,
                "rewards": rewards,
                "statuses": statuses,
                "candidate_reward": rewards[candidate_seat],
                "trace_reward": rewards[opponent_runtime_seat],
                "margin": rewards[candidate_seat] - rewards[opponent_runtime_seat],
                "candidate_win": rewards[candidate_seat] > rewards[opponent_runtime_seat],
                "invalid_episode": len(statuses) != 2 or any(status != "DONE" for status in statuses),
                "fallback_exposed": fallback_exposed,
                "fallback_count": fallback_count,
                "terminal_waste": terminal_waste,
                "candidate_diagnostics": diagnostics,
                "unit_noop_diagnostics": detected_unit_noops(env, candidate_seat),
            }
        )

    checks = {
        "candidate_wins_both_seats": all(episode["candidate_win"] for episode in episodes),
        "zero_invalid_episodes": all(not episode["invalid_episode"] for episode in episodes),
        "zero_fallbacks_when_exposed": all(
            episode["fallback_count"] in (None, 0) for episode in episodes
        ),
        "zero_candidate_terminal_waste": all(
            all(value == 0 for value in episode["terminal_waste"].values()) for episode in episodes
        ),
        "zero_detected_candidate_unit_noops": all(
            episode["unit_noop_diagnostics"]["detected_noops"] == 0 for episode in episodes
        ),
    }
    checks["overall"] = all(checks.values())
    names = _team_names(replay)
    return {
        "candidate": candidate,
        "replay_path": str(path),
        "source_episode_id": (replay.get("info", {}) or {}).get("EpisodeId"),
        "source_seed": seed,
        "source_configuration": configuration,
        "recorded_opponent_seat": recorded_seat,
        "recorded_opponent_team": names[recorded_seat] if recorded_seat < len(names) else None,
        "method": "stateless open-loop recorded actions keyed by observation step",
        "caveat": (
            "The trace does not adapt after environment divergence. This is a one-trace stress test, "
            "not a faithful reconstruction of the opponent and not a ladder win-rate estimate."
        ),
        "episodes": episodes,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="repository-relative Python file or Kaggle agent name")
    parser.add_argument("--replay", type=Path, required=True, help="local replay JSON; never copied by this tool")
    opponent = parser.add_mutually_exclusive_group(required=True)
    opponent.add_argument("--opponent-seat", type=int)
    opponent.add_argument("--opponent-team")
    args = parser.parse_args()
    report = run_replay_trace_gate(
        args.candidate,
        args.replay,
        opponent_seat=args.opponent_seat,
        opponent_team=args.opponent_team,
    )
    print(json.dumps(report, indent=2))
    if not report["checks"]["overall"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
