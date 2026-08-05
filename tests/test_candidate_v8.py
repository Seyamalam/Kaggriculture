from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V8_PATH = ROOT / "agents" / "candidate_v8_market_order.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, V8_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observation(*, step: int = 713, exposed: bool = True) -> dict:
    opponent_tile = {
        "kind": "PLANT",
        "crop": "STRAWBERRY",
        "yield_units": 2 if exposed else 0,
    }
    return {
        "step": step,
        "player": 0,
        "market": {
            "prices": {
                "WHEAT": 50,
                "FERTILIZER": 15,
                "MELON": 100,
                "STRAWBERRY": 120,
                "MILK": 200,
            }
        },
        "farms": [
            {"tiles": [[None]], "money": 10_000, "hands": []},
            {
                "tiles": [[opponent_tile if exposed else None]],
                "money": 10_000,
                "hands": [],
            },
        ],
        "private": {"shed": {}, "inventories": []},
    }


def _action() -> dict:
    return {
        "farmer": ["PASS"],
        "hands": [["PASS"]],
        "market": [
            ["SELL", "WHEAT", 40],
            ["SELL", "MELON", 5],
            ["SELL", "FERTILIZER", 2],
            ["SELL", "STRAWBERRY", 6],
            ["SELL", "MILK", 3],
            ["HIRE"],
            ["BUY_SEED", "MELON", 1],
            ["BUY_PRODUCT", "WHEAT", 1],
        ],
    }


def test_candidate_v8_import_and_final_entrypoint_contract() -> None:
    module = _load("candidate_v8_contract_test")

    assert callable(module.agent)
    assert callable(module._candidate_v8_submission_entrypoint)
    assert V8_PATH.read_text(encoding="utf-8").startswith(
        "# SPDX-License-Identifier: Apache-2.0\n"
    )
    assert module._C20_EXACT_AGENT is not module.agent


def test_overlay_only_reorders_existing_unprotected_sell_slots() -> None:
    module = _load("candidate_v8_overlay_test")
    original = _action()
    overlaid = module._c21_market_order_overlay(_observation(), original)

    assert overlaid is not original
    assert overlaid["farmer"] == original["farmer"]
    assert overlaid["hands"] == original["hands"]
    assert overlaid["market"][0] == ["SELL", "WHEAT", 40]
    assert overlaid["market"][2] == ["SELL", "FERTILIZER", 2]
    assert overlaid["market"][5:] == original["market"][5:]
    assert [overlaid["market"][index][1] for index in (1, 3, 4)] == [
        "STRAWBERRY",
        "MILK",
        "MELON",
    ]
    assert Counter(map(tuple, overlaid["market"])) == Counter(map(tuple, original["market"]))
    assert original == _action()


def test_overlay_abstains_outside_its_final_day_collision_gate() -> None:
    module = _load("candidate_v8_abstention_test")
    original = _action()

    assert module._c21_market_order_overlay(
        _observation(step=695), original
    ) == original
    assert module._c21_market_order_overlay(
        _observation(step=718), original
    ) == original
    assert module._c21_market_order_overlay(
        _observation(exposed=False), original
    ) == original
    sparse = _action()
    sparse["market"] = sparse["market"][:7]
    assert module._c21_market_order_overlay(_observation(), sparse) == sparse
