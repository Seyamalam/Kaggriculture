from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

from kaggle_environments.envs.kaggriculture import kaggriculture as engine


ROOT = Path(__file__).resolve().parents[1]


def _load_main():
    spec = importlib.util.spec_from_file_location("v18_recovery_test", ROOT / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observation(*, step=289, shed=None, farmer=None, action_tile=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    if action_tile is not None:
        tiles[4][4] = action_tile
    return {
        "step": step,
        "player": 0,
        "farms": [
            {
                "farmer": farmer,
                "hands": [],
                "tiles": tiles,
            }
        ],
        "private": {
            "shed": shed or {},
            "inventories": [{}],
        },
        "market": {
            "inventory": {
                "MILK": 10_000,
                "STRAWBERRY": 10_000,
                "WOOL": 10_000,
                "MELON": 10_000,
            },
            "prices": {
                "MILK": 160,
                "STRAWBERRY": 120,
                "WOOL": 200,
                "MELON": 250,
            },
        },
        "town": {"unlocked_shops": ["PIZZA_SHOP", "YARN_STORE"]},
    }


def test_embedded_prices_match_default_and_overridden_engine():
    module = _load_main()
    for item in module._V18S_DEFAULT_PARAMS:
        for inventory in (9_900, 10_000, 10_050, 10_100, 10_200):
            assert module._v18s_market_price(item, inventory, {}) == engine.market_price(
                item, inventory
            )

    custom = engine._resolve_market_params(  # noqa: SLF001 - pinned-engine parity test.
        {"MILK": {"base": 200, "above_target": 0.8}}
    )
    market = {"params": custom}
    for inventory in (9_900, 10_000, 10_050, 10_100):
        assert module._v18s_market_price("MILK", inventory, market) == engine.market_price(
            "MILK", inventory, custom
        )


def test_matched_rival_cap_stops_before_the_floor():
    module = _load_main()
    for item in module._V18S_PREMIUM:
        quantity = module._v18s_safe_addition(
            item,
            stock=500,
            covered=0,
            inventory=10_000,
            market={},
        )
        assert quantity > 0
        assert module._v18s_market_price(item, 10_000 + 2 * (quantity - 1), {}) > 1
        assert module._v18s_market_price(item, 10_000 + 2 * quantity, {}) == 1


def test_projected_shed_accounts_for_same_turn_pickup():
    module = _load_main()
    obs = _observation(shed={"MILK": 5}, farmer=[4, 4])
    action = {"farmer": ["PICKUP", "MILK", 3], "hands": [], "market": []}

    projected = module._v18s_project_shed(obs, action)

    assert projected["MILK"] == 2


def test_recovery_sweep_prepends_sales_and_preserves_original_action_as_suffix():
    module = _load_main()
    obs = _observation(shed={"MILK": 10, "STRAWBERRY": 5})
    original = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", "WHEAT", 3]],
    }
    before = deepcopy(original)

    overlaid = module._v18s_recovery_sweep(obs, original)

    assert original == before
    assert overlaid["farmer"] == original["farmer"]
    assert overlaid["hands"] == original["hands"]
    assert overlaid["market"] == [
        ["SELL", "MILK", 10],
        ["SELL", "STRAWBERRY", 5],
        ["SELL", "WHEAT", 3],
    ]


def test_recovery_sweep_abstains_before_day_12_off_phase_and_on_full_queue():
    module = _load_main()
    original = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
    assert module._v18s_recovery_sweep(
        _observation(step=241, shed={"MILK": 10}), original
    ) == original
    assert module._v18s_recovery_sweep(
        _observation(step=290, shed={"MILK": 10}), original
    ) == original

    full = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", "WHEAT", 1] for _ in range(module.MAX_ORDERS)],
    }
    assert module._v18s_recovery_sweep(
        _observation(shed={"MILK": 10}), full
    ) == full

