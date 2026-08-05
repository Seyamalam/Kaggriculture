from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_candidate():
    path = ROOT / "agents" / "candidate_v21_capital_latch.py"
    spec = importlib.util.spec_from_file_location("v21_capital_latch_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observation(*, step: int, own_money: int, rival_money: int) -> dict:
    farm = {"farmer": [4, 4], "hands": [], "tiles": [[None] * 10 for _ in range(10)]}
    own = dict(farm, money=own_money)
    rival = dict(farm, money=rival_money)
    return {
        "step": step,
        "player": 0,
        "farms": [own, rival],
        "private": {"shed": {"MILK": 10}, "inventories": [{}]},
        "market": {
            "inventory": {"MILK": 10_000, "STRAWBERRY": 10_000, "WOOL": 10_000, "MELON": 10_000},
            "prices": {"MILK": 160, "STRAWBERRY": 120, "WOOL": 200, "MELON": 250},
        },
        "town": {"unlocked_shops": ["PIZZA_SHOP"]},
    }


def test_latch_uses_frozen_step_577_capital_threshold_and_persists():
    module = _load_candidate()
    assert not module._v21_late_abstain(
        _observation(step=576, own_money=10_000, rival_money=0), 576
    )
    assert module._v21_late_abstain(
        _observation(step=577, own_money=10_000, rival_money=5_000), 577
    )
    assert module._v21_late_abstain(
        _observation(step=625, own_money=1_000, rival_money=20_000), 625
    )


def test_nonactivation_is_latched_and_step_zero_resets_the_seat():
    module = _load_candidate()
    assert not module._v21_late_abstain(
        _observation(step=577, own_money=10_000, rival_money=5_001), 577
    )
    assert not module._v21_late_abstain(
        _observation(step=625, own_money=20_000, rival_money=0), 625
    )
    assert not module._v21_late_abstain(
        _observation(step=0, own_money=3_000, rival_money=3_000), 0
    )
    assert module._v21_late_abstain(
        _observation(step=577, own_money=10_000, rival_money=5_000), 577
    )


def test_activated_latch_returns_the_untouched_base_action():
    module = _load_candidate()
    observation = _observation(step=577, own_money=10_000, rival_money=5_000)
    original = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 1]]}

    assert module._v18s_recovery_sweep(observation, original) == original
