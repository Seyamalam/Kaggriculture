from __future__ import annotations

import importlib.util
from pathlib import Path

from kaggle_environments import make


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sheep_tiles(farm) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y, row in enumerate(farm.tiles)
        for x, tile in enumerate(row)
        if isinstance(tile, dict) and tile.get("animal") == "SHEEP"
    }


def test_candidate_v5_eight_sheep_lifecycle_has_no_fallbacks_or_stranded_seeds() -> None:
    candidate = _load(
        ROOT / "agents" / "candidate_v5_eight_sheep.py",
        "candidate_v5_eight_sheep_test",
    )
    opponent = _load(ROOT / "agents" / "candidate_v4_landcap.py", "candidate_v4_v5_test")
    expected_tiles = set(candidate.SHEEP_TILES)
    assert len(expected_tiles) == 8
    assert expected_tiles.isdisjoint({(4, 4), (5, 4), (4, 5), (5, 5)})

    candidate.FALLBACK_COUNT = 0
    for seed in (65001, 65002):
        for candidate_seat in (0, 1):
            env = make(
                "kaggriculture",
                configuration={"episodeSteps": 720, "seed": seed},
                debug=True,
            )
            agents = (
                [candidate.agent, opponent.agent]
                if candidate_seat == 0
                else [opponent.agent, candidate.agent]
            )
            env.run(agents)
            assert env.steps[-1][candidate_seat].status == "DONE"

            counts = [
                len(_sheep_tiles(states[candidate_seat].observation.farms[candidate_seat]))
                for states in env.steps
            ]
            assert counts == sorted(counts)
            assert counts[-1] == 8
            assert _sheep_tiles(env.steps[-1][candidate_seat].observation.farms[candidate_seat]) == expected_tiles

            placed: set[tuple[int, int]] = set()
            for index in range(1, len(env.steps)):
                action = env.steps[index][candidate_seat].action
                if not isinstance(action, dict):
                    continue
                previous_farm = env.steps[index - 1][candidate_seat].observation.farms[candidate_seat]
                unit_actions = [action.get("farmer"), *action.get("hands", [])]
                unit_positions = [previous_farm.farmer, *previous_farm.hands]
                for unit_action, position in zip(unit_actions, unit_positions):
                    if not isinstance(unit_action, list) or not unit_action:
                        continue
                    x, y = map(int, position)
                    if unit_action[0] == "PICKUP":
                        assert previous_farm.tiles[y][x] != "LOCKED"
                        assert (x, y) in {(4, 4), (5, 4), (4, 5), (5, 5)}
                    if unit_action[:2] == ["PLACE", "SHEEP"]:
                        assert previous_farm.tiles[y][x] != "LOCKED"
                        assert (x, y) in expected_tiles
                        placed.add((x, y))

            assert placed == expected_tiles
            terminal_private = env.steps[-1][candidate_seat].observation.private
            assert all(int(count) == 0 for count in terminal_private.seeds.values())

    assert candidate.FALLBACK_COUNT == 0


def test_candidate_v5_fallback_preserves_observable_hand_shape() -> None:
    candidate = _load(
        ROOT / "agents" / "candidate_v5_eight_sheep.py",
        "candidate_v5_eight_sheep_fallback_test",
    )
    malformed = {"player": 0, "farms": [{"hands": [[0, 0], [1, 1]]}]}
    assert candidate.agent(malformed) == {
        "farmer": ["PASS"],
        "hands": [["PASS"], ["PASS"]],
        "market": [],
    }
    assert candidate.FALLBACK_COUNT == 1
