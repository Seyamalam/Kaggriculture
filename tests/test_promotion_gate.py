from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import promotion_gate


def _episode(margin: float, *, win: int, tie: int, statuses=None):
    return {
        "margin": margin,
        "win": win,
        "tie": tie,
        "statuses": statuses or ["DONE", "DONE"],
    }


def _result(episodes, paired_margin: float, *, paired_win: int, paired_tie: int, diagnostics=None):
    diagnostics = diagnostics or {
        "preventable_weeds": 0,
        "zero_cash_days": 0,
        "terminal_unsold_items": 0,
        "terminal_seed_cost": 0,
        "terminal_field_yield_units": 0,
        "terminal_non_cash_value": 0,
    }
    return {
        "episodes_played": len(episodes),
        "episode_wins": sum(item["win"] for item in episodes),
        "episode_ties": sum(item["tie"] for item in episodes),
        "episodes": episodes,
        "pairs": [
            {
                "pair_index": 0,
                "seed": 11,
                "paired_margin": paired_margin,
                "paired_win": paired_win,
                "paired_tie": paired_tie,
            }
        ],
        "diagnostic_totals": diagnostics,
    }


def test_multi_opponent_gate_aggregates_rates_margins_and_summaries(monkeypatch):
    reports = {
        "alpha": _result(
            [_episode(10, win=1, tie=0), _episode(0, win=0, tie=1)],
            10,
            paired_win=1,
            paired_tie=0,
        ),
        "beta": _result(
            [_episode(-5, win=0, tie=0), _episode(20, win=1, tie=0)],
            15,
            paired_win=1,
            paired_tie=0,
        ),
    }
    monkeypatch.setattr(promotion_gate, "resolve_agent", lambda specification: specification)
    monkeypatch.setattr(
        promotion_gate,
        "run_paired_tournament",
        lambda _candidate, opponent, **_kwargs: reports[opponent],
    )

    report = promotion_gate.evaluate_promotion(
        "candidate.py",
        ["alpha", "beta"],
        pairs=1,
        seed=11,
        min_win_rate=0.5,
        min_wilson_lower=0.1,
        min_mean_margin=5.0,
    )

    aggregate = report["aggregate"]
    assert aggregate["episodes_played"] == 4
    assert (aggregate["episode_wins"], aggregate["episode_ties"], aggregate["episode_losses"]) == (2, 1, 1)
    assert aggregate["episode_win_rate"] == 0.5
    assert aggregate["episode_tie_rate"] == 0.25
    assert aggregate["paired_win_rate"] == 1.0
    assert aggregate["mean_episode_margin"] == pytest.approx(6.25)
    assert aggregate["median_episode_margin"] == pytest.approx(5.0)
    assert aggregate["mean_paired_margin"] == pytest.approx(12.5)
    assert aggregate["median_paired_margin"] == pytest.approx(12.5)
    assert aggregate["episode_win_rate_wilson_95"]["low"] == pytest.approx(0.150039, abs=1e-6)
    assert len(report["paired_results"]) == 2
    assert {item["opponent"] for item in report["paired_results"]} == {"alpha", "beta"}
    assert all("episodes" not in item["summary"] for item in report["per_opponent"])
    assert report["checks"] == {
        "no_invalid_episodes": True,
        "zero_terminal_waste": True,
        "zero_preventable_weeds": True,
        "zero_cash_days": True,
        "minimum_episode_win_rate": True,
        "minimum_wilson_lower": True,
        "minimum_mean_margin": True,
        "overall": True,
    }


def test_gate_reports_each_diagnostic_and_threshold_failure(monkeypatch):
    failed = _result(
        [_episode(-100, win=0, tie=0, statuses=["ERROR", "DONE"]), _episode(0, win=0, tie=1)],
        -100,
        paired_win=0,
        paired_tie=0,
        diagnostics={
            "preventable_weeds": 2,
            "zero_cash_days": 1,
            "terminal_unsold_items": 3,
            "terminal_seed_cost": 20,
            "terminal_field_yield_units": 1,
            "terminal_non_cash_value": 200,
        },
    )
    monkeypatch.setattr(promotion_gate, "resolve_agent", lambda specification: specification)
    monkeypatch.setattr(promotion_gate, "run_paired_tournament", lambda *_args, **_kwargs: failed)

    report = promotion_gate.evaluate_promotion(
        "candidate.py",
        ["alpha"],
        pairs=1,
        seed=11,
        min_win_rate=0.75,
        min_wilson_lower=0.25,
        min_mean_margin=0,
    )

    assert report["aggregate"]["invalid_episodes"] == 1
    assert report["aggregate"]["diagnostic_totals"]["terminal_seed_cost"] == 20
    assert all(not passed for passed in report["checks"].values())


def test_default_suite_includes_baseline_and_frozen_opponents():
    assert promotion_gate.DEFAULT_OPPONENTS == (
        "main.py",
        "crop-specialist",
        "diversified-baseline",
        "animal-specialist",
    )

