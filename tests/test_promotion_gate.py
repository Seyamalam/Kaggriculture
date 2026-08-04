from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import promotion_gate


ZERO_DIAGNOSTICS = {
    "preventable_weeds": 0,
    "zero_cash_days": 0,
    "terminal_unsold_items": 0,
    "terminal_seed_cost": 0,
    "terminal_field_yield_units": 0,
    "terminal_non_cash_value": 0,
}


def _result(pair_episode_margins, *, diagnostics=None, bad_status_at=None):
    episodes = []
    paired_results = []
    for pair_index, (seat_0_margin, seat_1_margin) in enumerate(pair_episode_margins):
        pair_episodes = []
        for seat, margin in enumerate((seat_0_margin, seat_1_margin)):
            statuses = ["DONE", "DONE"]
            if bad_status_at == (pair_index, seat):
                statuses = ["ERROR", "DONE"]
            episode = {
                "pair_index": pair_index,
                "candidate_seat": seat,
                "margin": margin,
                "win": int(margin > 0),
                "tie": int(margin == 0),
                "statuses": statuses,
            }
            pair_episodes.append(episode)
            episodes.append(episode)
        paired_margin = seat_0_margin + seat_1_margin
        paired_results.append(
            {
                "pair_index": pair_index,
                "seed": 100 + pair_index,
                "paired_margin": paired_margin,
                "paired_win": int(paired_margin > 0),
                "paired_tie": int(paired_margin == 0),
            }
        )
    return {
        "episodes_played": len(episodes),
        "episodes": episodes,
        "pairs": paired_results,
        "diagnostic_totals": dict(diagnostics or ZERO_DIAGNOSTICS),
    }


def _evaluate(monkeypatch, reports, *, pairs=2, **thresholds):
    seeds = []
    monkeypatch.setattr(promotion_gate, "resolve_agent", lambda specification: specification)

    def fake_tournament(_candidate, opponent, **kwargs):
        seeds.append((opponent, kwargs["seed"]))
        return reports[opponent]

    monkeypatch.setattr(promotion_gate, "run_paired_tournament", fake_tournament)
    report = promotion_gate.evaluate_promotion(
        "candidate.py",
        list(reports),
        pairs=pairs,
        seed=100,
        min_win_rate=thresholds.get("min_win_rate", 0.75),
        min_wilson_lower=thresholds.get("min_wilson_lower", 0.3),
        min_mean_margin=thresholds.get("min_mean_margin", 1.0),
        min_seat_win_rate=thresholds.get("min_seat_win_rate", 0.55),
    )
    return report, seeds


def test_gate_uses_disjoint_seed_blocks_and_requires_each_opponent(monkeypatch):
    reports = {
        "alpha": _result([(10, 10), (20, 20)]),
        "beta": _result([(30, 30), (40, 40)]),
    }

    report, seeds = _evaluate(monkeypatch, reports)

    assert seeds == [("alpha", 100), ("beta", 102)]
    assert [item["base_seed"] for item in report["per_opponent"]] == [100, 102]
    assert report["aggregate"]["episodes_played"] == 8
    assert report["aggregate"]["episode_wins"] == 8
    assert report["aggregate"]["mean_episode_margin"] == pytest.approx(25.0)
    assert report["aggregate"]["median_episode_margin"] == pytest.approx(25.0)
    assert report["aggregate"]["mean_paired_margin"] == pytest.approx(50.0)
    assert "descriptive_only_correlated" in report["aggregate"]["episode_win_rate_wilson_95"]["interpretation"]
    assert all(item["checks"]["overall"] for item in report["per_opponent"])
    assert all(item["metrics"]["seat_wins"] == {"0": 2, "1": 2} for item in report["per_opponent"])
    assert all(item["metrics"]["first_half_pairs"] == 1 for item in report["per_opponent"])
    assert all(item["metrics"]["second_half_pairs"] == 1 for item in report["per_opponent"])
    assert all("episodes" not in item["summary"] for item in report["per_opponent"])
    assert report["checks"] == {
        "no_invalid_episodes": True,
        "zero_terminal_waste": True,
        "zero_preventable_weeds": True,
        "zero_cash_days": True,
        "every_opponent_independently_passes": True,
        "overall": True,
    }


def test_easy_opponent_cannot_compensate_for_failed_opponent(monkeypatch):
    reports = {
        "easy": _result([(100, 100), (100, 100)]),
        "hard": _result([(-1, -1), (-1, -1)]),
    }

    report, _seeds = _evaluate(
        monkeypatch,
        reports,
        min_win_rate=0.5,
        min_wilson_lower=0.0,
        min_mean_margin=0.0,
        min_seat_win_rate=0.5,
    )

    assert report["aggregate"]["episode_win_rate"] == 0.5
    hard = next(item for item in report["per_opponent"] if item["opponent"] == "hard")
    assert not hard["checks"]["minimum_episode_win_rate"]
    assert not hard["checks"]["minimum_seat_0_win_rate"]
    assert not hard["checks"]["minimum_seat_1_win_rate"]
    assert not hard["checks"]["positive_minimum_mean_margin"]
    assert not report["checks"]["every_opponent_independently_passes"]
    assert not report["checks"]["overall"]


def test_both_seed_halves_must_have_positive_paired_margin(monkeypatch):
    # Each seat wins 75%, the overall mean is positive, and only the second
    # seed half regresses. The half check must independently block promotion.
    result = _result([(6, 4), (6, 4), (5, -10), (-10, 5)])
    report, _seeds = _evaluate(
        monkeypatch,
        {"regime-shift": result},
        pairs=4,
        min_win_rate=0.5,
        min_wilson_lower=0.0,
        min_mean_margin=0.0,
        min_seat_win_rate=0.5,
    )

    opponent = report["per_opponent"][0]
    assert opponent["metrics"]["mean_episode_margin"] > 0
    assert opponent["metrics"]["first_half_mean_paired_margin"] > 0
    assert opponent["metrics"]["second_half_mean_paired_margin"] < 0
    assert opponent["checks"]["positive_first_half_paired_margin"]
    assert not opponent["checks"]["positive_second_half_paired_margin"]
    assert not opponent["checks"]["overall"]


def test_invalid_and_diagnostic_failures_are_per_opponent_and_global(monkeypatch):
    diagnostics = {
        **ZERO_DIAGNOSTICS,
        "preventable_weeds": 2,
        "zero_cash_days": 1,
        "terminal_seed_cost": 20,
        "terminal_non_cash_value": 20,
    }
    failed = _result([(10, 10), (10, 10)], diagnostics=diagnostics, bad_status_at=(0, 0))

    report, _seeds = _evaluate(monkeypatch, {"broken": failed})

    opponent_checks = report["per_opponent"][0]["checks"]
    assert not opponent_checks["no_invalid_episodes"]
    assert not opponent_checks["zero_terminal_waste"]
    assert not opponent_checks["zero_preventable_weeds"]
    assert not opponent_checks["zero_cash_days"]
    assert report["aggregate"]["invalid_episodes"] == 1
    assert not report["checks"]["overall"]


def test_gate_requires_two_pairs_and_valid_rate_thresholds(monkeypatch):
    monkeypatch.setattr(promotion_gate, "resolve_agent", lambda specification: specification)
    with pytest.raises(ValueError, match="at least 2"):
        promotion_gate.evaluate_promotion(
            "candidate.py",
            ["opponent"],
            pairs=1,
            seed=1,
            min_win_rate=0.5,
            min_wilson_lower=0.0,
            min_mean_margin=0.0,
            min_seat_win_rate=0.55,
        )
    with pytest.raises(ValueError, match="min_seat_win_rate"):
        promotion_gate.evaluate_promotion(
            "candidate.py",
            ["opponent"],
            pairs=2,
            seed=1,
            min_win_rate=0.5,
            min_wilson_lower=0.0,
            min_mean_margin=0.0,
            min_seat_win_rate=1.1,
        )


def test_default_suite_includes_baseline_and_frozen_opponents():
    assert promotion_gate.DEFAULT_OPPONENTS == (
        "main.py",
        "crop-specialist",
        "diversified-baseline",
        "animal-specialist",
    )
