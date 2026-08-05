from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

from kaggle_environments import make


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.replay_loss_attribution as attribution


def _pass_agent(obs, configuration=None):
    farms = obs.get("farms", [])
    player = int(obs.get("player", 0))
    hands = len(farms[player].get("hands", [])) if player < len(farms) else 0
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": []}


def _replay() -> dict:
    farms = [
        {"money": 3000, "hands": [], "tiles": [[None]], "unlocked_quadrants": ["NW"]},
        {"money": 3000, "hands": [], "tiles": [[None]], "unlocked_quadrants": ["NW"]},
    ]
    return {
        "schema_version": 1,
        "module_version": importlib.metadata.version("kaggle-environments"),
        "name": "kaggriculture",
        "info": {"EpisodeId": 77, "seed": 5, "TeamNames": ["Us", "Them"]},
        "configuration": {"seed": 5},
        "steps": [
            [{"observation": {"step": 0, "farms": farms}}, {"observation": {}}],
            [
                {"observation": {"step": 1, "farms": farms}, "action": {}},
                {"observation": {}, "action": {}},
            ],
        ],
    }


def _market(products: set[str], revenue: float) -> dict:
    by_product = {
        product: {
            "executed_units": 1,
            "realized_revenue": revenue,
            "weighted_mean_price": revenue,
            "floor_units": 0,
            "post_shop_demand_units": 1,
        }
        for product in products
    }
    return {
        "executed_units": len(products),
        "realized_revenue": revenue * len(products),
        "weighted_mean_price": revenue,
        "floor_units": 0,
        "post_shop_demand_units": len(products),
        "by_product": by_product,
        "by_phase": {},
        "by_window": {},
        "feature_scope": "online_safe",
    }


def _run(*, seat: int, margin: float, products: set[str]) -> dict:
    checkpoints = {
        "0": {"margin": 0.0},
        "1": {"margin": margin},
    }
    return {
        "source_seed": 5,
        "candidate_seat": seat,
        "statuses": ["DONE", "DONE"],
        "invalid_episode": False,
        "candidate_bank": 100.0 + margin,
        "trace_bank": 100.0,
        "margin": margin,
        "checkpoints": checkpoints,
        "candidate_market": _market(products, 20.0 + margin),
        "trace_market": _market(products, 20.0),
    }


def test_parse_checkpoints_and_windows_fail_closed() -> None:
    assert attribution._parse_int_list("9,1,9") == [1, 9]
    assert attribution._parse_windows("1:5,5:9") == [(1, 5), (5, 9)]

    for value in ("5:1", "1:5,4:8"):
        try:
            attribution._parse_windows(value)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion aid
            raise AssertionError("invalid windows must fail")


def test_ledger_summary_uses_only_committed_units() -> None:
    events = [
        {"runtime_seat": 0, "product": "WOOL", "step": 5, "phase": 1, "shop_phase": 1, "price": 210.0, "revenue": 210.0},
        {"runtime_seat": 0, "product": "WOOL", "step": 6, "phase": 2, "shop_phase": 2, "price": 1.0, "revenue": 1.0},
        {"runtime_seat": 1, "product": "WOOL", "step": 5, "phase": 1, "shop_phase": 1, "price": 200.0, "revenue": 200.0},
    ]
    result = attribution._ledger_summary(
        events,
        actor_seat=0,
        products={"WOOL"},
        windows=[(1, 9)],
    )

    assert result["executed_units"] == 2
    assert result["realized_revenue"] == 211.0
    assert result["weighted_mean_price"] == 105.5
    assert result["floor_units"] == 1
    assert result["post_shop_demand_units"] == 1
    assert result["by_window"]["1:9"]["executed_units"] == 2


def test_engine_commit_instrumentation_preserves_episode_result() -> None:
    configuration = {"seed": 9, "episodeSteps": 3}
    plain = make("kaggriculture", configuration=configuration, debug=True)
    plain.run([_pass_agent, _pass_agent])
    instrumented = make("kaggriculture", configuration=configuration, debug=True)
    with attribution._capture_market_ledger() as events:
        instrumented.run([_pass_agent, _pass_agent])

    assert [state.reward for state in plain.steps[-1]] == [
        state.reward for state in instrumented.steps[-1]
    ]
    assert [state.status for state in plain.steps[-1]] == [
        state.status for state in instrumented.steps[-1]
    ]
    assert events == []


def test_comparison_reports_denial_products_checkpoints_and_strata() -> None:
    products = {"WOOL"}
    baseline = _run(seat=0, margin=-5.0, products=products)
    candidate = _run(seat=0, margin=7.0, products=products)
    candidate["trace_bank"] = 96.0
    candidate["margin"] = 11.0
    candidate["checkpoints"]["1"]["margin"] = 11.0
    row = attribution._comparison(
        baseline,
        candidate,
        checkpoints=[0, 1],
        windows=[(0, 1)],
        products=products,
    )

    assert row["stratum"] == "rescued"
    assert row["margin_delta"] == 16.0
    assert row["trace_bank_delta"] == -4.0
    assert row["denial_share"] == 0.25
    assert row["bank_decomposition_residual"] == 0.0
    assert row["checkpoint_margin_deltas"] == {"0": 0.0, "1": 16.0}
    assert row["window_incremental_margin_deltas"]["0:1"] == 16.0
    assert row["product_execution_deltas"]["WOOL"]["own_realized_revenue"] == 12.0


def test_strata_handle_equal_and_tie_transitions_explicitly() -> None:
    assert attribution._stratum(-5.0, -5.0) == "unchanged"
    assert attribution._stratum(0.0, 0.0) == "unchanged"
    assert attribution._stratum(5.0, 5.0) == "unchanged"
    assert attribution._stratum(-5.0, 0.0) == "loss_to_tie_improved"
    assert attribution._stratum(0.0, -5.0) == "tie_to_loss_regressed"
    assert attribution._stratum(0.0, 5.0) == "tie_to_win_improved"
    assert attribution._stratum(5.0, 0.0) == "win_to_tie_regressed"


def test_build_report_validates_frozen_manifest_and_labels_scope(tmp_path, monkeypatch) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    candidate.write_text("def agent(obs): return {'candidate': 1}\n", encoding="utf-8")
    baseline.write_text("def agent(obs): return {'baseline': 1}\n", encoding="utf-8")
    replay_path = tmp_path / "replay.json"
    replay = _replay()
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    content = replay_path.read_bytes()
    entry = {
        "composite_key": "77:1",
        "replay_sha256": hashlib.sha256(content).hexdigest(),
        "replay_size_bytes": len(content),
        "configuration_sha256": attribution._sha256_json(replay["configuration"]),
        "action_trace_sha256": attribution._sha256_json(
            attribution._replay_action_trace(replay, 1)
        ),
    }
    comparison = {
        "schema_version": 2,
        "engine_version": importlib.metadata.version("kaggle-environments"),
        "candidate": {"sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()},
        "baseline": {"sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()},
        "traces": [{"corpus_key": "77:1"}],
    }
    frozen_manifest = {"schema_version": 1, "entries": [entry]}
    frozen_manifest["manifest_sha256"] = attribution._sha256_json(frozen_manifest)
    comparison["corpus_manifest"] = frozen_manifest
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
    products = {"WOOL"}

    def fake_run(path, replay, recorded_seat, candidate_seat, checkpoints, windows, selected_products):
        assert recorded_seat == 1
        assert selected_products == products
        margin = 5.0 if Path(path) == candidate else -5.0
        return _run(seat=candidate_seat, margin=margin, products=products)

    monkeypatch.setattr(attribution, "_run_policy_against_trace", fake_run)
    report = attribution.build_report(
        comparison_path=comparison_path,
        candidate=candidate,
        baseline=baseline,
        replay_paths=[replay_path],
        checkpoints=[0, 1],
        windows=[(0, 1)],
        products=products,
        exclude_team="Us",
    )

    assert report["summary"]["strata"]["rescued"]["count"] == 2
    assert report["feature_labels"]["final_public_footprint"] == "retrospective_do_not_gate"
    assert report["feature_labels"]["per_policy_checkpoint_public_state"] == "online_safe"
    assert (
        report["feature_labels"]["checkpoint_candidate_minus_baseline_delta"]
        == "retrospective_counterfactual"
    )
    assert len(report["input_manifest"]["manifest_sha256"]) == 64
    assert report["traces"][0]["final_footprint_scope"] == "retrospective_do_not_gate"
    markdown = attribution.render_markdown(report)
    assert "online-safe" in markdown
    assert "retrospective counterfactuals" in markdown
    assert "diagnostic-only" in markdown

    del comparison["corpus_manifest"]["manifest_sha256"]
    comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
    try:
        attribution.build_report(
            comparison_path=comparison_path,
            candidate=candidate,
            baseline=baseline,
            replay_paths=[replay_path],
            checkpoints=[0, 1],
            windows=[(0, 1)],
            products=products,
            exclude_team="Us",
        )
    except ValueError as exc:
        assert "requires a SHA-256 self-digest" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("missing frozen manifest self-digest must fail closed")
