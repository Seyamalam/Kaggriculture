"""Benchmark a local agent against current public leaderboard action traces.

This is deliberately a replay-trace stress test.  Kaggle exposes public match
replays, not another team's adaptive source code.  Recorded actions therefore
stop adapting once a local simulation diverges from the original episode.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import io
import importlib.metadata
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # Supports module and direct-script execution.
    from scripts.replay_trace_gate import run_replay_trace_gate
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI
    from replay_trace_gate import run_replay_trace_gate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "main.py"
DEFAULT_CACHE = ROOT / "artifacts" / "leaderboard-replays"
DEFAULT_JSON = ROOT / "artifacts" / "leaderboard-benchmark.json"
DEFAULT_MARKDOWN = ROOT / "artifacts" / "leaderboard-benchmark.md"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        return converter()
    raise TypeError(f"expected dict-like Kaggle API object, got {type(value)!r}")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def leaderboard_rows(api: Any, competition: str, top: int) -> list[dict[str, Any]]:
    """Return a normalized current leaderboard snapshot."""
    # Kaggle prints an irrelevant next-page token even when the caller asked
    # for a bounded first page.
    with redirect_stdout(io.StringIO()):
        raw = api.competition_leaderboard_view(competition, page_size=top) or []
    rows = []
    for rank, item in enumerate(raw[:top], start=1):
        if item is None:
            continue
        row = _as_dict(item)
        rows.append(
            {
                "rank": rank,
                "team_id": int(row["teamId"]),
                "team_name": str(row["teamName"]),
                "rating": _number(row.get("score")),
                "submission_date": row.get("submissionDate"),
            }
        )
    return rows


def best_active_submission(api: Any, team_id: int) -> dict[str, Any] | None:
    """Select the active submission responsible for a team's best rating."""
    submissions = api.competition_team_submissions(team_id) or []
    normalized = [_as_dict(item) for item in submissions]
    if not normalized:
        return None
    best = max(
        normalized,
        key=lambda item: (
            _number(item.get("publicScore"), float("-inf")),
            str(item.get("dateSubmitted") or ""),
            int(item.get("id") or 0),
        ),
    )
    return {
        "submission_id": int(best["id"]),
        "rating": _number(best.get("publicScore")),
        "submitted_at": best.get("dateSubmitted"),
    }


def latest_public_episodes(
    api: Any,
    submission_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Return the newest completed public episodes for one submission."""
    episodes = []
    for item in api.competition_list_episodes(submission_id) or []:
        episode = _as_dict(item)
        if episode.get("state") != "COMPLETED":
            continue
        if episode.get("type") != "EPISODE_TYPE_PUBLIC":
            continue
        agents = episode.get("agents") or []
        if not any(int(agent.get("submissionId") or -1) == submission_id for agent in agents):
            continue
        episodes.append(episode)
    episodes.sort(
        key=lambda item: (
            str(item.get("endTime") or item.get("createTime") or ""),
            int(item.get("id") or 0),
        ),
        reverse=True,
    )
    return episodes[:limit]


def _download_replay(api: Any, episode_id: int, cache_dir: Path, refresh: bool) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"episode-{episode_id}-replay.json"

    def valid_replay() -> bool:
        try:
            replay = json.loads(path.read_text(encoding="utf-8"))
            steps = replay.get("steps") or []
            actual_id = (replay.get("info") or {}).get("EpisodeId")
            return bool(steps) and len(steps[0]) >= 2 and int(actual_id) == episode_id
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False

    if refresh or not valid_replay():
        if path.exists():
            path.unlink()
        api.competition_episode_replay(episode_id, path=str(cache_dir), quiet=True)
    if not valid_replay():
        raise ValueError(f"Kaggle did not produce a valid replay at {path}")
    return path


def _compact_gate(gate: dict[str, Any]) -> dict[str, Any]:
    episodes = []
    for episode in gate["episodes"]:
        episodes.append(
            {
                "candidate_seat": int(episode["candidate_seat"]),
                "candidate_reward": float(episode["candidate_reward"]),
                "trace_reward": float(episode["trace_reward"]),
                "margin": float(episode["margin"]),
                "candidate_win": bool(episode["candidate_win"]),
                "invalid_episode": bool(episode["invalid_episode"]),
                "statuses": list(episode["statuses"]),
            }
        )
    return {
        "source_episode_id": gate["source_episode_id"],
        "source_seed": gate["source_seed"],
        "recorded_team": gate["recorded_opponent_team"],
        "recorded_seat": int(gate["recorded_opponent_seat"]),
        "episodes": episodes,
        "wins": sum(
            episode["candidate_win"] and not episode["invalid_episode"]
            for episode in episodes
        ),
        "losses": sum(
            not episode["candidate_win"] and not episode["invalid_episode"]
            for episode in episodes
        ),
        "invalid": sum(episode["invalid_episode"] for episode in episodes),
        "mean_margin": statistics.mean(episode["margin"] for episode in episodes),
        "minimum_margin": min(episode["margin"] for episode in episodes),
        "both_seats_won": bool(episodes)
        and all(
            episode["candidate_win"] and not episode["invalid_episode"]
            for episode in episodes
        ),
        "zero_invalid_episodes": not any(episode["invalid_episode"] for episode in episodes),
    }


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    traces = [
        trace
        for team in report["teams"]
        for trace in team.get("traces", [])
    ]
    episodes = [episode for trace in traces for episode in trace["episodes"]]
    valid_episodes = [episode for episode in episodes if not episode["invalid_episode"]]
    if not episodes:
        return {
            "teams_requested": report["settings"]["top"],
            "teams_benchmarked": 0,
            "trace_episodes": 0,
            "simulations": 0,
            "valid_simulations": 0,
            "invalid_simulations": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "mean_margin": 0.0,
            "median_margin": 0.0,
            "teams_swept": 0,
            "errors": sum(bool(team.get("error")) for team in report["teams"]),
        }
    wins = sum(episode["candidate_win"] for episode in valid_episodes)
    return {
        "teams_requested": report["settings"]["top"],
        "teams_benchmarked": sum(bool(team.get("traces")) for team in report["teams"]),
        "trace_episodes": len(traces),
        "simulations": len(episodes),
        "valid_simulations": len(valid_episodes),
        "invalid_simulations": len(episodes) - len(valid_episodes),
        "wins": wins,
        "losses": len(valid_episodes) - wins,
        "win_rate": wins / len(valid_episodes) if valid_episodes else 0.0,
        "mean_margin": (
            statistics.mean(episode["margin"] for episode in valid_episodes)
            if valid_episodes
            else 0.0
        ),
        "median_margin": (
            statistics.median(episode["margin"] for episode in valid_episodes)
            if valid_episodes
            else 0.0
        ),
        "teams_swept": sum(
            bool(team.get("traces"))
            and all(trace["both_seats_won"] for trace in team["traces"])
            for team in report["teams"]
        ),
        "errors": sum(bool(team.get("error")) for team in report["teams"]),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    title_prefix = "Saved-snapshot" if report.get("settings", {}).get("snapshot") else "Live"
    lines = [
        f"# {title_prefix} leaderboard replay-trace benchmark",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Candidate: `{report['candidate']['path']}`  ",
        f"SHA-256: `{report['candidate']['sha256']}`  ",
        f"Competition: `{report['competition']}`",
        "",
        "## Summary",
        "",
        f"- Teams benchmarked: {summary['teams_benchmarked']} / {summary['teams_requested']}",
        f"- Recorded traces: {summary['trace_episodes']}",
        f"- Both-seat simulations: {summary['simulations']}",
        f"- Invalid simulations: {summary['invalid_simulations']}",
        f"- Wins/losses: {summary['wins']} / {summary['losses']}",
        f"- Win rate: {summary['win_rate']:.1%}",
        f"- Mean margin: {summary['mean_margin']:+,.1f}",
        f"- Median margin: {summary['median_margin']:+,.1f}",
        f"- Teams swept across every sampled trace: {summary['teams_swept']}",
        f"- Team/trace errors: {summary['errors']}",
        "",
        "## Leaderboard traces",
        "",
        "| Rank | Team | Rating | Submission | Traces | W-L | Mean margin | Result |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for team in report["teams"]:
        traces = team.get("traces", [])
        episodes = [episode for trace in traces for episode in trace["episodes"]]
        valid = [episode for episode in episodes if not episode["invalid_episode"]]
        invalid = len(episodes) - len(valid)
        wins = sum(episode["candidate_win"] for episode in valid)
        losses = len(valid) - wins
        mean_margin = statistics.mean(episode["margin"] for episode in valid) if valid else 0
        if team.get("error"):
            result = f"ERROR: {team['error']}"
        elif invalid:
            result = f"INVALID: {invalid}"
        elif traces and all(trace["both_seats_won"] for trace in traces):
            result = "SWEEP"
        elif traces:
            result = "MIXED/LOSS"
        else:
            result = "NO TRACE"
        lines.append(
            "| {rank} | {name} | {rating:,.1f} | {submission} | {traces} | "
            "{wins}-{losses} | {margin:+,.1f} | {result} |".format(
                rank=team["rank"],
                name=str(team["team_name"]).replace("|", "\\|"),
                rating=team["rating"],
                submission=team.get("submission_id", "-"),
                traces=len(traces),
                wins=wins,
                losses=losses,
                margin=mean_margin,
                result=str(result).replace("|", "\\|"),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The benchmark replays public recorded actions open-loop by observation step.",
            "Once the candidate changes the market or board, the trace cannot adapt to the new state.",
            "This is an adversarial regression/stress test, not source-code execution and not",
            "an estimator of live Bradley--Terry win probability. Raw replays are cached under",
            "`artifacts/` and must remain untracked.",
            "",
        ]
    )
    return "\n".join(lines)


def build_report(
    api: Any,
    *,
    competition: str,
    candidate: Path,
    top: int,
    episodes_per_team: int,
    cache_dir: Path,
    refresh: bool,
) -> dict[str, Any]:
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "competition": competition,
        "candidate": {
            "path": str(candidate),
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        },
        "engine_version": importlib.metadata.version("kaggle-environments"),
        "kaggle_api_version": importlib.metadata.version("kaggle"),
        "method": "latest public completed episode actions, replayed open-loop from both seats",
        "settings": {
            "top": top,
            "episodes_per_team": episodes_per_team,
            "cache_dir": str(cache_dir.expanduser().resolve()),
            "refresh": refresh,
        },
        "teams": [],
    }
    pending: list[tuple[dict[str, Any], dict[str, Any], Path]] = []

    # Complete every network operation before starting kaggle-environments.
    # The simulator creates multiprocessing resources on macOS; interleaving
    # further authenticated API calls after a full episode can leave the HTTP
    # client waiting indefinitely.
    for row in leaderboard_rows(api, competition, top):
        team = dict(row)
        team["traces"] = []
        report["teams"].append(team)
        try:
            submission = best_active_submission(api, team["team_id"])
            if submission is None:
                raise RuntimeError("no active public submission")
            team.update(submission)
            episodes = latest_public_episodes(
                api,
                submission["submission_id"],
                episodes_per_team,
            )
            if not episodes:
                raise RuntimeError("no completed public episode")
            for episode in episodes:
                episode_id = int(episode["id"])
                replay = _download_replay(api, episode_id, cache_dir, refresh)
                recorded_seat = next(
                    (
                        index
                        for index, agent in enumerate(episode.get("agents") or [])
                        if int(agent.get("submissionId") or -1)
                        == submission["submission_id"]
                    ),
                    None,
                )
                if recorded_seat is None:
                    raise RuntimeError(
                        f"submission {submission['submission_id']} absent from episode {episode_id}"
                    )
                episode["recorded_seat"] = recorded_seat
                pending.append((team, episode, replay))
        except Exception as exc:  # keep the rest of a live snapshot usable
            team["error"] = f"{type(exc).__name__}: {exc}"

    for team, episode, replay in pending:
        try:
            gate = run_replay_trace_gate(
                candidate,
                replay,
                opponent_seat=int(episode["recorded_seat"]),
            )
            compact = _compact_gate(gate)
            compact["source_public_match"] = {
                "created_at": episode.get("createTime"),
                "ended_at": episode.get("endTime"),
                "agents": episode.get("agents") or [],
            }
            team["traces"].append(compact)
        except Exception as exc:  # preserve other downloaded traces
            team["error"] = f"{type(exc).__name__}: {exc}"
    report["summary"] = summarize(report)
    return report


def build_report_from_snapshot(
    snapshot_path: Path,
    *,
    candidate: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    """Re-run a candidate against the exact traces selected by an earlier report."""
    snapshot_path = snapshot_path.expanduser().resolve()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "competition": snapshot["competition"],
        "candidate": {
            "path": str(candidate),
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        },
        "engine_version": importlib.metadata.version("kaggle-environments"),
        "kaggle_api_version": importlib.metadata.version("kaggle"),
        "method": "exact saved leaderboard snapshot actions, replayed open-loop from both seats",
        "settings": {
            "top": len(snapshot["teams"]),
            "episodes_per_team": snapshot.get("settings", {}).get("episodes_per_team", 1),
            "cache_dir": str(cache_dir.expanduser().resolve()),
            "refresh": False,
            "snapshot": str(snapshot_path),
            "snapshot_generated_at": snapshot.get("generated_at"),
            "snapshot_candidate_sha256": snapshot.get("candidate", {}).get("sha256"),
        },
        "teams": [],
    }
    for old_team in snapshot["teams"]:
        team = {
            key: old_team.get(key)
            for key in (
                "rank",
                "team_id",
                "team_name",
                "rating",
                "submission_date",
                "submission_id",
                "submitted_at",
            )
        }
        team["traces"] = []
        report["teams"].append(team)
        for old_trace in old_team.get("traces", []):
            episode_id = int(old_trace["source_episode_id"])
            replay = cache_dir.expanduser().resolve() / f"episode-{episode_id}-replay.json"
            try:
                if not replay.is_file():
                    raise FileNotFoundError(
                        f"cached replay missing for episode {episode_id}: {replay}"
                    )
                recorded_seat = old_trace.get("recorded_seat")
                if recorded_seat is None:
                    agents = (old_trace.get("source_public_match") or {}).get("agents") or []
                    recorded_seat = next(
                        (
                            index
                            for index, agent in enumerate(agents)
                            if int(agent.get("submissionId") or -1)
                            == int(team.get("submission_id") or -2)
                        ),
                        None,
                    )
                if recorded_seat is None:
                    raise RuntimeError(f"recorded seat unavailable for episode {episode_id}")
                gate = run_replay_trace_gate(
                    candidate,
                    replay,
                    opponent_seat=int(recorded_seat),
                )
                compact = _compact_gate(gate)
                compact["source_public_match"] = old_trace.get("source_public_match", {})
                team["traces"].append(compact)
            except Exception as exc:
                team["error"] = f"{type(exc).__name__}: {exc}"
    report["summary"] = summarize(report)
    return report


def _api() -> Any:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", default="kaggriculture")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--episodes-per-team", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="reuse the exact teams/episodes in an earlier JSON report; performs no API refresh",
    )
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.top < 1 or args.episodes_per_team < 1:
        parser.error("--top and --episodes-per-team must be positive")
    if args.output.expanduser().resolve() == args.markdown.expanduser().resolve():
        parser.error("--output and --markdown must differ")

    if args.snapshot:
        if args.snapshot.expanduser().resolve() == args.output.expanduser().resolve():
            parser.error("--output must differ from --snapshot")
        report = build_report_from_snapshot(
            args.snapshot,
            candidate=args.candidate,
            cache_dir=args.cache_dir,
        )
    else:
        report = build_report(
            _api(),
            competition=args.competition,
            candidate=args.candidate,
            top=args.top,
            episodes_per_team=args.episodes_per_team,
            cache_dir=args.cache_dir,
            refresh=args.refresh,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"JSON: {args.output.resolve()}")
    print(f"Markdown: {args.markdown.resolve()}")
    summary = report["summary"]
    if not summary["teams_benchmarked"]:
        return 2
    return 1 if summary["errors"] or summary["invalid_simulations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
