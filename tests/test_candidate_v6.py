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


def _signal_observation(day: int, *, opponent_sheep: int = 0, own_cows: int = 0):
    def board():
        return [[None for _x in range(10)] for _y in range(10)]

    ours, theirs = board(), board()
    ours[3][3] = {"kind": "PASTURE", "animal": "SHEEP"}
    ours[3][4] = {"kind": "PASTURE", "animal": "SHEEP"}
    if own_cows:
        ours[3][5] = {"kind": "PASTURE", "animal": "COW"}
    for index in range(opponent_sheep):
        theirs[2][index] = {"kind": "PASTURE", "animal": "SHEEP"}
    # Cow-heavy pasture pressure must not masquerade as wool competition.
    for index in range(4):
        theirs[3][index] = {"kind": "PASTURE", "animal": "COW"}
    farm = lambda tiles: {"tiles": tiles, "farmer": [0, 0], "hands": []}
    return {
        "player": 0,
        "day": day,
        "farms": [farm(ours), farm(theirs)],
        "private": {"shed": {}, "inventories": [], "seeds": {}},
        "market": {"prices": {"WOOL": 1}},
    }


def _animal_tiles(farm, animal: str) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y, row in enumerate(farm.tiles)
        for x, tile in enumerate(row)
        if isinstance(tile, dict) and tile.get("animal") == animal
    }


def test_candidate_v6_trigger_is_bounded_and_latched() -> None:
    candidate = _load(
        ROOT / "agents" / "candidate_v6_adaptive_livestock.py",
        "candidate_v6_trigger_test",
    )
    assert not candidate._mixed_livestock_response(_signal_observation(7))
    assert candidate._target_portfolio(_signal_observation(7)) == {"SHEEP": 4, "COW": 0}
    assert candidate._mixed_livestock_response(_signal_observation(7, opponent_sheep=2))
    assert candidate._target_portfolio(_signal_observation(7, opponent_sheep=2)) == {
        "SHEEP": 4,
        "COW": 4,
    }
    assert not candidate._mixed_livestock_response(_signal_observation(4, opponent_sheep=2))
    assert not candidate._mixed_livestock_response(_signal_observation(11, opponent_sheep=2))
    assert candidate._mixed_livestock_response(_signal_observation(11, own_cows=1))
    assert candidate._target_portfolio(_signal_observation(13)) == {"SHEEP": 4, "COW": 0}
    assert candidate._target_portfolio(_signal_observation(14)) == {"SHEEP": 8, "COW": 0}


def test_candidate_v6_exact_portfolios_and_clean_lifecycle_in_both_seats() -> None:
    candidate = _load(
        ROOT / "agents" / "candidate_v6_adaptive_livestock.py",
        "candidate_v6_lifecycle_test",
    )
    v1 = _load(ROOT / "agents" / "submission_v1.py", "candidate_v1_v6_test")
    v5 = _load(ROOT / "agents" / "candidate_v5_eight_sheep.py", "candidate_v5_v6_test")
    regimes = ((v1.agent, (8, 0)), (v5.agent, (4, 4)))
    candidate.FALLBACK_COUNT = 0
    for opponent, expected_counts in regimes:
        for seat in (0, 1):
            env = make(
                "kaggriculture",
                configuration={"episodeSteps": 720, "seed": 65001},
                debug=True,
            )
            env.run([candidate.agent, opponent] if seat == 0 else [opponent, candidate.agent])
            assert env.steps[-1][seat].status == "DONE"
            totals = []
            for states in env.steps:
                farm = states[seat].observation.farms[seat]
                totals.append(len(_animal_tiles(farm, "SHEEP")) + len(_animal_tiles(farm, "COW")))
            assert totals == sorted(totals)

            terminal = env.steps[-1][seat].observation
            sheep = _animal_tiles(terminal.farms[seat], "SHEEP")
            cows = _animal_tiles(terminal.farms[seat], "COW")
            assert (len(sheep), len(cows)) == expected_counts
            assert sheep == set(candidate.CORE_SHEEP_TILES) | (
                set(candidate.FLEX_TILES) if expected_counts == (8, 0) else set()
            )
            assert cows == (set(candidate.FLEX_TILES) if expected_counts == (4, 4) else set())
            assert all(int(value) == 0 for value in terminal.private.seeds.values())
            assert all(int(value) == 0 for value in terminal.private.shed.values())

            for index in range(1, len(env.steps)):
                action = env.steps[index][seat].action
                if not isinstance(action, dict):
                    continue
                previous_farm = env.steps[index - 1][seat].observation.farms[seat]
                actions = [action.get("farmer"), *action.get("hands", [])]
                positions = [previous_farm.farmer, *previous_farm.hands]
                for unit_action, position in zip(actions, positions):
                    if isinstance(unit_action, list) and unit_action[:1] == ["PICKUP"]:
                        x, y = map(int, position)
                        assert previous_farm.tiles[y][x] != "LOCKED"
                        assert (x, y) in {(4, 4), (5, 4), (4, 5), (5, 5)}

    assert candidate.FALLBACK_COUNT == 0
