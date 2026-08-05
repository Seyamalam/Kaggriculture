from __future__ import annotations

from pathlib import Path
import json
import sys


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


def test_live_api_selection_normalizes_and_filters() -> None:
    api = _Api()
    rows = leaderboard_rows(api, "kaggriculture", 2)
    assert rows[0] == {
        "rank": 1,
        "team_id": 10,
        "team_name": "Leader",
        "rating": 3000.5,
        "submission_date": None,
    }
    assert best_active_submission(api, 10) == {
        "submission_id": 101,
        "rating": 3000.5,
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
        json.dumps({"info": {"EpisodeId": 77}, "steps": [[{}, {}], [{}, {}]]}),
        encoding="utf-8",
    )
    snapshot = {
        "competition": "kaggriculture",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "candidate": {"sha256": "old"},
        "settings": {"episodes_per_team": 1},
        "teams": [
            {
                "rank": 1,
                "team_id": 10,
                "team_name": "Leader",
                "rating": 3000.0,
                "submission_id": 101,
                "traces": [
                        {
                            "source_episode_id": 77,
                            "recorded_seat": 0,
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
        json.dumps({"info": {"EpisodeId": 99}, "steps": [[{}, {}], [{}, {}]]}),
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
