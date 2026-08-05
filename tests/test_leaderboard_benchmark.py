from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.leaderboard_benchmark as benchmark
from scripts.leaderboard_benchmark import (
    _download_replay,
    best_active_submission,
    build_report,
    build_report_from_snapshot,
    latest_public_episodes,
    leaderboard_rows,
    render_markdown,
    summarize,
)


class _Object:
    def __init__(self, **values):
        self.values = values

    def to_dict(self):
        return dict(self.values)


class _Api:
    def competition_leaderboard_view(self, competition, page_size):
        assert competition == "kaggriculture"
        assert page_size == 2
        return [
            _Object(teamId=10, teamName="Leader", score="3000.5"),
            _Object(teamId=20, teamName="Runner", score="2900.0"),
        ]

    def competition_team_submissions(self, team_id):
        assert team_id == 10
        return [
            _Object(id=100, publicScore="2800.0", dateSubmitted="2026-01-01"),
            _Object(id=101, publicScore="3000.5", dateSubmitted="2026-01-02"),
        ]

    def competition_list_episodes(self, submission_id):
        assert submission_id == 101
        return [
            _Object(
                id=3,
                state="COMPLETED",
                type="EPISODE_TYPE_PUBLIC",
                endTime="2026-01-03",
                agents=[{"submissionId": 101}],
            ),
            _Object(
                id=2,
                state="COMPLETED",
                type="EPISODE_TYPE_VALIDATION",
                endTime="2026-01-04",
                agents=[{"submissionId": 101}],
            ),
            _Object(
                id=4,
                state="RUNNING",
                type="EPISODE_TYPE_PUBLIC",
                endTime="2026-01-05",
                agents=[{"submissionId": 101}],
            ),
            _Object(
                id=1,
                state="COMPLETED",
                type="EPISODE_TYPE_PUBLIC",
                endTime="2026-01-01",
                agents=[{"submissionId": 101}],
            ),
        ]


def _immutable_snapshot_fixture(tmp_path, *, episode_id=77):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def agent(obs): return {}\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    replay_path = cache / f"episode-{episode_id}-replay.json"
    replay_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module_version": benchmark.importlib.metadata.version(
                    "kaggle-environments"
                ),
                "name": "kaggriculture",
                "configuration": {"seed": 5},
                "info": {"EpisodeId": episode_id},
                "steps": [
                    [{"observation": {"step": 0}}, {}],
                    [{"action": {"market": [["SELL", "MILK", 1]]}}, {}],
                ],
            }
        ),
        encoding="utf-8",
    )
    engine_version = benchmark.importlib.metadata.version("kaggle-environments")
    entry = benchmark._replay_manifest_entry(
        replay_path,
        submission_id=101,
        episode_id=episode_id,
        recorded_seat=0,
        expected_engine_version=engine_version,
    )
    manifest = {
        "schema_version": benchmark.CORPUS_SCHEMA_VERSION,
        "capture_cutoff": "2026-01-01T00:00:00+00:00",
        "engine_version": engine_version,
        "entries": [entry],
    }
    benchmark._finalize_manifest(manifest)
    key = f"101:{episode_id}:0"
    snapshot = {
        "schema_version": benchmark.REPORT_SCHEMA_VERSION,
        "competition": "kaggriculture",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "engine_version": engine_version,
        "candidate": {"sha256": "old"},
        "corpus_manifest": manifest,
        "settings": {"episodes_per_team": 1},
        "teams": [
            {
                "rank": 1,
                "team_id": 10,
                "team_name": "Leader",
                "leaderboard_rating": 3000.0,
                "submission_rating": 2999.0,
                "submission_id": 101,
                "traces": [
                    {
                        "source_episode_id": episode_id,
                        "recorded_seat": 0,
                        "corpus_key": key,
                        "source_public_match": {"agents": []},
                    }
                ],
            }
        ],
    }
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    return candidate, cache, replay_path, snapshot_path, snapshot


def test_live_api_selection_normalizes_and_filters() -> None:
    api = _Api()
    rows = leaderboard_rows(api, "kaggriculture", 2)
    assert rows[0] == {
        "rank": 1,
        "team_id": 10,
        "team_name": "Leader",
        "leaderboard_rating": 3000.5,
        "submission_date": None,
    }
    assert best_active_submission(api, 10) == {
        "submission_id": 101,
        "submission_rating": 3000.5,
        "submitted_at": "2026-01-02",
    }
    assert [episode["id"] for episode in latest_public_episodes(api, 101, 2)] == [3, 1]


def test_summary_and_markdown_make_open_loop_boundary_visible() -> None:
    report = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "competition": "kaggriculture",
        "candidate": {"path": "/tmp/main.py", "sha256": "abc"},
        "settings": {"top": 1},
        "teams": [
            {
                "rank": 1,
                "team_name": "A|B",
                "team_id": 1,
                "rating": 3000.0,
                "submission_id": 9,
                "traces": [
                    {
                        "source_episode_id": 7,
                        "recorded_seat": 0,
                        "both_seats_won": False,
                        "episodes": [
                            {
                                "candidate_win": True,
                                "margin": 10.0,
                                "invalid_episode": False,
                            },
                            {
                                "candidate_win": False,
                                "margin": -2.0,
                                "invalid_episode": False,
                            },
                            {
                                "candidate_win": True,
                                "margin": 999.0,
                                "invalid_episode": True,
                            },
                        ],
                    }
                ],
            }
        ],
    }
    report["summary"] = summarize(report)
    assert report["summary"]["win_rate"] == 0.5
    assert report["summary"]["mean_margin"] == 4.0
    assert report["summary"]["invalid_simulations"] == 1
    assert report["summary"]["unique_trace_keys"] == 1
    assert report["summary"]["unique_source_episodes"] == 1
    assert report["summary"]["cluster_adjusted_win_rate"] == 0.5
    assert report["summary"]["mean_absolute_paired_seat_margin_divergence"] == 0.0
    markdown = render_markdown(report)
    assert "A\\|B" in markdown
    assert "1-1" in markdown
    assert "INVALID: 1" in markdown
    assert "open-loop" in markdown
    assert "not source-code execution" in markdown


def test_snapshot_reuse_runs_without_live_api(tmp_path, monkeypatch) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def agent(obs): return {}\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "episode-77-replay.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module_version": benchmark.importlib.metadata.version(
                    "kaggle-environments"
                ),
                "name": "kaggriculture",
                "configuration": {"seed": 5},
                "info": {"EpisodeId": 77},
                "steps": [[{"observation": {"step": 0}}, {}], [{"action": {}}, {}]],
            }
        ),
        encoding="utf-8",
    )
    entry = benchmark._replay_manifest_entry(
        cache / "episode-77-replay.json",
        submission_id=101,
        episode_id=77,
        recorded_seat=0,
        expected_engine_version=benchmark.importlib.metadata.version(
            "kaggle-environments"
        ),
    )
    manifest = {
        "schema_version": benchmark.CORPUS_SCHEMA_VERSION,
        "capture_cutoff": "2026-01-01T00:00:00+00:00",
        "engine_version": benchmark.importlib.metadata.version("kaggle-environments"),
        "entries": [entry],
    }
    benchmark._finalize_manifest(manifest)
    snapshot = {
        "schema_version": benchmark.REPORT_SCHEMA_VERSION,
        "competition": "kaggriculture",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "engine_version": benchmark.importlib.metadata.version("kaggle-environments"),
        "candidate": {"sha256": "old"},
        "corpus_manifest": manifest,
        "settings": {"episodes_per_team": 1},
        "teams": [
            {
                "rank": 1,
                "team_id": 10,
                "team_name": "Leader",
                "leaderboard_rating": 3000.0,
                "submission_rating": 2999.0,
                "submission_id": 101,
                "traces": [
                        {
                            "source_episode_id": 77,
                            "recorded_seat": 0,
                            "corpus_key": "101:77:0",
                            "source_public_match": {"agents": []},
                    }
                ],
            }
        ],
    }
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    def fake_gate(candidate_path, replay_path, *, opponent_seat):
        assert Path(candidate_path) == candidate.resolve()
        assert Path(replay_path).name == "episode-77-replay.json"
        assert opponent_seat == 0
        return {
            "source_episode_id": 77,
            "source_seed": 5,
            "recorded_opponent_team": "Leader",
            "recorded_opponent_seat": 0,
            "episodes": [
                {
                    "candidate_seat": 0,
                    "candidate_reward": 120.0,
                    "trace_reward": 100.0,
                    "margin": 20.0,
                    "candidate_win": True,
                    "invalid_episode": False,
                    "statuses": ["DONE", "DONE"],
                },
                {
                    "candidate_seat": 1,
                    "candidate_reward": 110.0,
                    "trace_reward": 100.0,
                    "margin": 10.0,
                    "candidate_win": True,
                    "invalid_episode": False,
                    "statuses": ["DONE", "DONE"],
                },
            ],
        }

    monkeypatch.setattr(benchmark, "run_replay_trace_gate", fake_gate)
    report = build_report_from_snapshot(
        snapshot_path,
        candidate=candidate,
        cache_dir=cache,
    )
    assert report["summary"]["wins"] == 2
    assert report["summary"]["teams_swept"] == 1
    assert report["settings"]["snapshot_candidate_sha256"] == "old"
    assert report["teams"][0]["leaderboard_rating"] == 3000.0
    assert report["teams"][0]["submission_rating"] == 2999.0
    assert report["corpus_manifest"] == manifest


def test_snapshot_rejects_changed_cached_replay_bytes(tmp_path) -> None:
    candidate, cache, replay_path, snapshot_path, _ = _immutable_snapshot_fixture(
        tmp_path
    )
    replay_path.write_text(
        replay_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="replay_sha256 mismatch"):
        build_report_from_snapshot(
            snapshot_path,
            candidate=candidate,
            cache_dir=cache,
        )


def test_snapshot_rejects_wrong_payload_episode_id(tmp_path) -> None:
    candidate, cache, replay_path, snapshot_path, _ = _immutable_snapshot_fixture(
        tmp_path
    )
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["info"]["EpisodeId"] = 78
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    with pytest.raises(
        ValueError, match="payload EpisodeId 78 does not match expected 77"
    ):
        build_report_from_snapshot(
            snapshot_path,
            candidate=candidate,
            cache_dir=cache,
        )


@pytest.mark.parametrize(
    ("mutation", "expected_field"),
    [
        ("configuration", "configuration_sha256 mismatch"),
        ("action", "action_trace_sha256 mismatch"),
    ],
)
def test_snapshot_semantic_digests_detect_forged_replay_change(
    tmp_path, mutation, expected_field
) -> None:
    candidate, cache, replay_path, snapshot_path, snapshot = (
        _immutable_snapshot_fixture(tmp_path)
    )
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    if mutation == "configuration":
        replay["configuration"]["seed"] = 999
    else:
        replay["steps"][1][0]["action"]["market"][0][2] = 99
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    # Simulate an attacker updating only the coarse file identity. The
    # independently committed semantic digests must still fail closed.
    entry = snapshot["corpus_manifest"]["entries"][0]
    content = replay_path.read_bytes()
    entry["replay_sha256"] = benchmark.hashlib.sha256(content).hexdigest()
    entry["replay_size_bytes"] = len(content)
    benchmark._finalize_manifest(snapshot["corpus_manifest"])
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_field):
        build_report_from_snapshot(
            snapshot_path,
            candidate=candidate,
            cache_dir=cache,
        )


def test_snapshot_rejects_engine_and_manifest_schema_drift(tmp_path) -> None:
    candidate, cache, _, snapshot_path, snapshot = _immutable_snapshot_fixture(
        tmp_path
    )
    snapshot["engine_version"] = "0.0.0"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot engine"):
        build_report_from_snapshot(
            snapshot_path,
            candidate=candidate,
            cache_dir=cache,
        )

    snapshot["engine_version"] = benchmark.importlib.metadata.version(
        "kaggle-environments"
    )
    snapshot["corpus_manifest"]["schema_version"] = 999
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported corpus manifest schema"):
        build_report_from_snapshot(
            snapshot_path,
            candidate=candidate,
            cache_dir=cache,
        )


def test_snapshot_rejects_duplicate_composite_keys_even_with_valid_digest(tmp_path) -> None:
    candidate, cache, _, snapshot_path, snapshot = _immutable_snapshot_fixture(
        tmp_path
    )
    manifest = snapshot["corpus_manifest"]
    manifest["entries"].append(dict(manifest["entries"][0]))
    benchmark._finalize_manifest(manifest)
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate corpus key"):
        build_report_from_snapshot(
            snapshot_path,
            candidate=candidate,
            cache_dir=cache,
        )


def test_failed_live_trace_preserves_candidate_independent_snapshot(
    tmp_path, monkeypatch
) -> None:
    class Api:
        def competition_leaderboard_view(self, competition, page_size):
            return [_Object(teamId=10, teamName="Leader", score="3000")]

        def competition_team_submissions(self, team_id):
            return [_Object(id=101, publicScore="2999")]

        def competition_list_episodes(self, submission_id):
            return [
                _Object(
                    id=77,
                    state="COMPLETED",
                    type="EPISODE_TYPE_PUBLIC",
                    endTime="2026-01-01",
                    agents=[{"submissionId": 101}, {"submissionId": 7}],
                )
            ]

    candidate, cache, replay_path, _, _ = _immutable_snapshot_fixture(tmp_path)
    monkeypatch.setattr(
        benchmark,
        "_download_replay",
        lambda api, episode_id, cache_dir, refresh: replay_path,
    )

    def failed_gate(*args, **kwargs):
        raise RuntimeError("candidate exploded")

    monkeypatch.setattr(benchmark, "run_replay_trace_gate", failed_gate)
    live_report = build_report(
        Api(),
        competition="kaggriculture",
        candidate=candidate,
        top=1,
        episodes_per_team=1,
        cache_dir=cache,
        refresh=False,
    )
    assert len(live_report["corpus_manifest"]["entries"]) == 1
    assert len(live_report["teams"][0]["traces"]) == 1
    failed_trace = live_report["teams"][0]["traces"][0]
    assert failed_trace["corpus_key"] == "101:77:0"
    assert failed_trace["episodes"] == []
    assert "candidate exploded" in failed_trace["error"]
    assert live_report["summary"]["teams_benchmarked"] == 1
    assert live_report["summary"]["trace_episodes"] == 1
    assert live_report["summary"]["completed_trace_gates"] == 0
    assert live_report["summary"]["trace_errors"] == 1
    benchmark._validate_snapshot_manifest(
        live_report,
        benchmark.importlib.metadata.version("kaggle-environments"),
    )

    snapshot_path = tmp_path / "failed-live-report.json"
    snapshot_path.write_text(json.dumps(live_report), encoding="utf-8")

    def successful_gate(candidate_path, replay, *, opponent_seat):
        return {
            "source_episode_id": 77,
            "source_seed": 5,
            "recorded_opponent_team": "Leader",
            "recorded_opponent_seat": opponent_seat,
            "episodes": [
                {
                    "candidate_seat": seat,
                    "candidate_reward": 120.0,
                    "trace_reward": 100.0,
                    "margin": 20.0,
                    "candidate_win": True,
                    "invalid_episode": False,
                    "statuses": ["DONE", "DONE"],
                }
                for seat in (0, 1)
            ],
        }

    monkeypatch.setattr(benchmark, "run_replay_trace_gate", successful_gate)
    rerun = build_report_from_snapshot(
        snapshot_path,
        candidate=candidate,
        cache_dir=cache,
    )
    assert rerun["corpus_manifest"] == live_report["corpus_manifest"]
    assert rerun["summary"]["completed_trace_gates"] == 1
    assert rerun["summary"]["wins"] == 2


def test_summary_reports_cluster_weighting_and_seat_divergence() -> None:
    def trace(key, source_episode_id, margins, wins):
        return {
            "corpus_key": key,
            "source_episode_id": source_episode_id,
            "recorded_seat": int(key.rsplit(":", 1)[-1]),
            "both_seats_won": all(wins),
            "episodes": [
                {
                    "candidate_win": win,
                    "margin": margin,
                    "invalid_episode": False,
                }
                for margin, win in zip(margins, wins, strict=True)
            ],
        }

    report = {
        "settings": {"top": 2},
        "teams": [
            {
                "submission_id": 10,
                "traces": [
                    trace("10:1:0", 1, [-5.0, -15.0], [False, False]),
                    trace("10:1:1", 1, [-10.0, -10.0], [False, False]),
                ],
            },
            {
                "submission_id": 20,
                "traces": [trace("20:2:0", 2, [10.0, 30.0], [True, True])],
            },
        ],
    }
    result = summarize(report)
    assert result["trace_episodes"] == 3
    assert result["unique_trace_keys"] == 3
    assert result["unique_source_episodes"] == 2
    assert result["shared_source_episode_clusters"] == 1
    assert result["max_traces_per_source_episode"] == 2
    assert result["win_rate"] == pytest.approx(1 / 3)
    assert result["cluster_adjusted_win_rate"] == 0.5
    assert result["cluster_vs_raw_win_rate_divergence"] == pytest.approx(1 / 6)
    assert result["cluster_adjusted_mean_margin"] == 5.0
    assert result["cluster_vs_raw_mean_margin_divergence"] == 5.0
    assert result["mean_absolute_paired_seat_margin_divergence"] == 10.0


def test_corrupt_cached_replay_is_redownloaded(tmp_path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    replay = cache / "episode-88-replay.json"
    replay.write_text("partial download", encoding="utf-8")

    class Api:
        calls = 0

        def competition_episode_replay(self, episode_id, path, quiet):
            assert episode_id == 88
            assert Path(path) == cache
            assert quiet is True
            self.calls += 1
            replay.write_text(
                json.dumps(
                    {"info": {"EpisodeId": 88}, "steps": [[{}, {}], [{}, {}]]}
                ),
                encoding="utf-8",
            )

    api = Api()
    assert _download_replay(api, 88, cache, refresh=False) == replay
    assert api.calls == 1
    assert _download_replay(api, 88, cache, refresh=False) == replay
    assert api.calls == 1


def test_live_build_resolves_recorded_seat_by_submission_id(tmp_path, monkeypatch) -> None:
    calls = []

    class Api:
        def competition_leaderboard_view(self, competition, page_size):
            calls.append("leaderboard")
            return [_Object(teamId=10, teamName="Renamed Team", score="3000")]

        def competition_team_submissions(self, team_id):
            calls.append("submissions")
            return [_Object(id=101, publicScore="3000")]

        def competition_list_episodes(self, submission_id):
            calls.append("episodes")
            return [
                _Object(
                    id=99,
                    state="COMPLETED",
                    type="EPISODE_TYPE_PUBLIC",
                    endTime="2026-01-01",
                    agents=[{"submissionId": 7}, {"submissionId": 101}],
                )
            ]

    candidate = tmp_path / "candidate.py"
    candidate.write_text("def agent(obs): return {}\n", encoding="utf-8")
    replay = tmp_path / "episode-99-replay.json"
    replay.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module_version": benchmark.importlib.metadata.version(
                    "kaggle-environments"
                ),
                "name": "kaggriculture",
                "configuration": {"seed": 3},
                "info": {"EpisodeId": 99},
                "steps": [[{"observation": {"step": 0}}, {}], [{"action": {}}, {}]],
            }
        ),
        encoding="utf-8",
    )

    def fake_download(api, episode_id, cache_dir, refresh):
        calls.append("download")
        return replay

    def fake_gate(candidate_path, replay_path, *, opponent_seat):
        calls.append("gate")
        assert opponent_seat == 1
        return {
            "source_episode_id": 99,
            "source_seed": 3,
            "recorded_opponent_team": "Old Team Name",
            "recorded_opponent_seat": 1,
            "episodes": [
                {
                    "candidate_seat": seat,
                    "candidate_reward": 120.0,
                    "trace_reward": 100.0,
                    "margin": 20.0,
                    "candidate_win": True,
                    "invalid_episode": False,
                    "statuses": ["DONE", "DONE"],
                }
                for seat in (0, 1)
            ],
        }

    monkeypatch.setattr(benchmark, "_download_replay", fake_download)
    monkeypatch.setattr(benchmark, "run_replay_trace_gate", fake_gate)
    report = build_report(
        Api(),
        competition="kaggriculture",
        candidate=candidate,
        top=1,
        episodes_per_team=1,
        cache_dir=tmp_path,
        refresh=False,
    )
    assert report["summary"]["wins"] == 2
    assert calls == ["leaderboard", "submissions", "episodes", "download", "gate"]
    assert report["schema_version"] == benchmark.REPORT_SCHEMA_VERSION
    assert report["teams"][0]["leaderboard_rating"] == 3000.0
    assert report["teams"][0]["submission_rating"] == 3000.0
    entry = report["corpus_manifest"]["entries"][0]
    assert entry["key"] == "101:99:1"
    assert entry["payload_episode_id"] == 99
    assert len(entry["replay_sha256"]) == 64
    assert len(entry["configuration_sha256"]) == 64
    assert len(entry["action_trace_sha256"]) == 64


@pytest.mark.parametrize(
    ("collision", "message"),
    [
        ("same_writes", "--output and --markdown must differ"),
        ("output_candidate", "--output must differ from --candidate"),
        ("markdown_snapshot", "--markdown must differ from --snapshot"),
        ("output_snapshot", "--output must differ from --snapshot"),
        ("output_in_cache", "--output must be outside --cache-dir"),
        ("markdown_in_cache", "--markdown must be outside --cache-dir"),
    ],
)
def test_cli_path_collisions_fail_closed(tmp_path, collision, message) -> None:
    candidate = (tmp_path / "candidate.py").resolve()
    cache = (tmp_path / "cache").resolve()
    output = (tmp_path / "report.json").resolve()
    markdown = (tmp_path / "report.md").resolve()
    snapshot = (tmp_path / "snapshot.json").resolve()
    if collision == "same_writes":
        markdown = output
    elif collision == "output_candidate":
        output = candidate
    elif collision == "markdown_snapshot":
        markdown = snapshot
    elif collision == "output_snapshot":
        output = snapshot
    elif collision == "output_in_cache":
        output = cache / "report.json"
    elif collision == "markdown_in_cache":
        markdown = cache / "report.md"

    with pytest.raises(ValueError, match=message):
        benchmark._validate_cli_paths(
            candidate=candidate,
            cache_dir=cache,
            output=output,
            markdown=markdown,
            snapshot=snapshot,
        )


def test_main_resolves_expanded_paths_before_build_and_write(
    tmp_path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def agent(obs): return {}\n", encoding="utf-8")
    captured = {}

    def fake_build(api, **kwargs):
        captured.update(kwargs)
        return {
            "summary": {
                "teams_benchmarked": 1,
                "errors": 0,
                "invalid_simulations": 0,
            }
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(benchmark, "_api", lambda: object())
    monkeypatch.setattr(benchmark, "build_report", fake_build)
    monkeypatch.setattr(benchmark, "render_markdown", lambda report: "report\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "leaderboard_benchmark.py",
            "--candidate",
            "./candidate.py",
            "--cache-dir",
            "./artifacts/../cache",
            "--output",
            "./out/../report.json",
            "--markdown",
            "./out/../report.md",
        ],
    )

    assert benchmark.main() == 0
    assert captured["candidate"] == candidate.resolve()
    assert captured["cache_dir"] == (tmp_path / "cache").resolve()
    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "report.md").is_file()
