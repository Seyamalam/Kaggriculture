from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.comparative_replay_corpus as corpus


def _replay(team_names=("Our Team", "Opponent")) -> dict:
    farms = [
        {
            "hands": [{}, {}],
            "unlocked_quadrants": ["NW"],
            "tiles": [[None]],
        },
        {
            "hands": [{}, {}, {}],
            "unlocked_quadrants": ["NW", "NE"],
            "tiles": [
                [
                    {"kind": "PASTURE", "animal": "COW"},
                    {"kind": "PASTURE", "animal": "SHEEP"},
                    {"kind": "PLANT", "crop": "STRAWBERRY"},
                ]
            ],
        },
    ]
    observation = {"step": 1, "farms": farms}
    return {
        "schema_version": 1,
        "module_version": "1.32.4",
        "name": "kaggriculture",
        "info": {"EpisodeId": 77, "TeamNames": list(team_names), "seed": 5},
        "configuration": {"seed": 5},
        "steps": [
            [
                {"observation": {"step": 0, "farms": farms}},
                {"observation": {"step": 0, "farms": farms}},
            ],
            [
                {"observation": observation, "action": {}},
                {"observation": observation, "action": {}},
            ],
        ],
    }


def _gate(path: str | Path, *, candidate: bool) -> dict:
    margins = [14.0, -2.0] if candidate else [10.0, -5.0]
    return {
        "source_episode_id": 77,
        "source_seed": 5,
        "episodes": [
            {
                "candidate_seat": seat,
                "margin": margin,
                "invalid_episode": False,
                "statuses": ["DONE", "DONE"],
            }
            for seat, margin in enumerate(margins)
        ],
    }


def test_resolve_corpus_seat_supports_all_three_modes() -> None:
    replay = _replay()

    assert corpus.resolve_corpus_seat(replay, opponent_seat=1) == 1
    assert corpus.resolve_corpus_seat(replay, recorded_team="opPONENT") == 1
    assert corpus.resolve_corpus_seat(replay, exclude_team="our team") == 1


def test_resolve_corpus_seat_rejects_ambiguous_or_missing_names() -> None:
    replay = _replay(("Same", "Same"))

    try:
        corpus.resolve_corpus_seat(replay, recorded_team="Same")
    except ValueError as exc:
        assert "matched 2 seats" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("ambiguous team must be rejected")

    try:
        corpus.resolve_corpus_seat(replay, recorded_team="Same", opponent_seat=0)
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("multiple selection modes must be rejected")


def test_public_footprint_is_stable_and_money_free() -> None:
    footprint = corpus.recorded_public_footprint(_replay(), 1)

    assert footprint == {
        "hands": 3,
        "unlocked_quadrants": 2,
        "pastures": 2,
        "animals": {"COW": 1, "SHEEP": 1},
        "crops": {"STRAWBERRY": 1},
    }


def test_build_report_compares_identical_seats_and_clusters(
    tmp_path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    candidate.write_text("def agent(obs): return {}\n", encoding="utf-8")
    baseline.write_text("def agent(obs): return {}\n", encoding="utf-8")
    replay_path = tmp_path / "episode-77-replay.json"
    replay_path.write_text(json.dumps(_replay()), encoding="utf-8")
    calls = []

    def fake_gate(agent, replay, *, opponent_seat):
        calls.append((Path(agent).resolve(), Path(replay).resolve(), opponent_seat))
        return _gate(replay, candidate=Path(agent).resolve() == candidate.resolve())

    monkeypatch.setattr(corpus, "run_replay_trace_gate", fake_gate)
    report = corpus.build_report(
        candidate=candidate,
        baseline=baseline,
        replay_paths=[replay_path],
        exclude_team="Our Team",
    )

    assert calls == [
        (baseline.resolve(), replay_path.resolve(), 1),
        (candidate.resolve(), replay_path.resolve(), 1),
    ]
    assert [row["delta"] for row in report["traces"][0]["comparisons"]] == [
        4.0,
        3.0,
    ]
    assert report["summary"]["mean_delta"] == 3.5
    assert report["summary"]["passed"] is True
    assert report["clusters"]["recorded_team"][0]["key"] == "Opponent"
    assert report["clusters"]["public_footprint"][0]["traces"] == 1
    markdown = corpus.render_markdown(report)
    assert "candidate-minus-baseline" in markdown
    assert "Open-loop" in markdown or "open-loop" in markdown
    assert "| 77 | Opponent | +4.0 | +3.0 | +3.5 | IMPROVED |" in markdown


def test_invalid_or_negative_comparison_fails_gate(tmp_path, monkeypatch) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    candidate.write_text("def agent(obs): return {}\n", encoding="utf-8")
    baseline.write_text("def agent(obs): return {}\n", encoding="utf-8")
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(json.dumps(_replay()), encoding="utf-8")

    def fake_gate(agent, replay, *, opponent_seat):
        gate = _gate(replay, candidate=Path(agent).resolve() == candidate.resolve())
        if Path(agent).resolve() == candidate.resolve():
            gate["episodes"][0]["margin"] = 1.0
            gate["episodes"][1]["invalid_episode"] = True
        return gate

    monkeypatch.setattr(corpus, "run_replay_trace_gate", fake_gate)
    report = corpus.build_report(
        candidate=candidate,
        baseline=baseline,
        replay_paths=[replay_path],
        opponent_seat=1,
    )

    assert report["summary"]["negative"] == 1
    assert report["summary"]["invalid_comparisons"] == 1
    assert report["summary"]["passed"] is False


def test_manifest_records_replay_identity_and_engine(tmp_path, monkeypatch) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    candidate.write_text("def agent(obs): return {'candidate': 1}\n", encoding="utf-8")
    baseline.write_text("def agent(obs): return {'baseline': 1}\n", encoding="utf-8")
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(json.dumps(_replay()), encoding="utf-8")

    monkeypatch.setattr(
        corpus,
        "run_replay_trace_gate",
        lambda agent, replay, opponent_seat: _gate(
            replay, candidate=Path(agent).resolve() == candidate.resolve()
        ),
    )
    report = corpus.build_report(
        candidate=candidate,
        baseline=baseline,
        replay_paths=[replay_path],
        opponent_seat=1,
    )
    manifest = report["corpus_manifest"]
    entry = manifest["entries"][0]

    assert report["schema_version"] == 2
    assert manifest["engine_version"] == "1.32.4"
    assert len(manifest["manifest_sha256"]) == 64
    assert entry["composite_key"] == "77:1"
    assert entry["source_seed"] == 5
    assert entry["replay_size_bytes"] == replay_path.stat().st_size
    assert len(entry["replay_sha256"]) == 64
    assert len(entry["configuration_sha256"]) == 64
    assert len(entry["action_trace_sha256"]) == 64


def test_path_roles_reject_resolved_read_write_collisions(tmp_path) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    replay = tmp_path / "replay.json"
    for path in (candidate, baseline, replay):
        path.write_text("{}", encoding="utf-8")
    alias = tmp_path / "candidate-alias.py"
    alias.symlink_to(candidate)

    for values, expected in (
        (
            {"candidate": candidate, "baseline": alias, "replay_paths": [replay]},
            "same file",
        ),
        (
            {
                "candidate": candidate,
                "baseline": baseline,
                "replay_paths": [replay, replay],
            },
            "duplicate resolved paths",
        ),
        (
            {
                "candidate": candidate,
                "baseline": baseline,
                "replay_paths": [replay],
                "output": replay,
            },
            "collides with replay",
        ),
        (
            {
                "candidate": candidate,
                "baseline": baseline,
                "replay_paths": [replay],
                "output": tmp_path / "report",
                "markdown": tmp_path / "report",
            },
            "same path",
        ),
    ):
        try:
            corpus.validate_path_roles(**values)
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover - assertion aid
            raise AssertionError(f"expected collision: {values}")


def test_duplicate_corpus_identity_and_non_finite_threshold_fail_closed(
    tmp_path,
) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    candidate.write_text("def agent(obs): return {'candidate': 1}\n", encoding="utf-8")
    baseline.write_text("def agent(obs): return {'baseline': 1}\n", encoding="utf-8")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(_replay()), encoding="utf-8")
    changed = _replay()
    changed["configuration"]["startingMoney"] = 4000
    second.write_text(json.dumps(changed), encoding="utf-8")

    try:
        corpus.build_report(
            candidate=candidate,
            baseline=baseline,
            replay_paths=[first, second],
            opponent_seat=1,
        )
    except ValueError as exc:
        assert "duplicate episode/seat composite 77:1" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("duplicate composite must be rejected")

    second.write_bytes(first.read_bytes())
    try:
        corpus.build_report(
            candidate=candidate,
            baseline=baseline,
            replay_paths=[first, second],
            opponent_seat=1,
        )
    except ValueError as exc:
        assert "duplicate replay content" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("duplicate content must be rejected")

    try:
        corpus.build_report(
            candidate=candidate,
            baseline=baseline,
            replay_paths=[first],
            opponent_seat=1,
            min_mean_delta=float("nan"),
        )
    except ValueError as exc:
        assert "must be finite" in str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("NaN threshold must be rejected")


def test_replay_mutation_during_gate_is_reported(tmp_path, monkeypatch) -> None:
    candidate = tmp_path / "candidate.py"
    baseline = tmp_path / "baseline.py"
    candidate.write_text("def agent(obs): return {'candidate': 1}\n", encoding="utf-8")
    baseline.write_text("def agent(obs): return {'baseline': 1}\n", encoding="utf-8")
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(json.dumps(_replay()), encoding="utf-8")

    def mutating_gate(agent, replay, *, opponent_seat):
        replay_path.write_text(json.dumps({**_replay(), "mutated": True}), encoding="utf-8")
        return _gate(replay, candidate=False)

    monkeypatch.setattr(corpus, "run_replay_trace_gate", mutating_gate)
    report = corpus.build_report(
        candidate=candidate,
        baseline=baseline,
        replay_paths=[replay_path],
        opponent_seat=1,
    )

    assert report["summary"]["passed"] is False
    assert report["summary"]["trace_errors"] == 1
    assert "replay changed after corpus capture" in report["traces"][0]["error"]
