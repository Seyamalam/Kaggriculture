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
REPORT_SCHEMA_VERSION = 2
CORPUS_SCHEMA_VERSION = 1
SUPPORTED_REPLAY_SCHEMA_VERSIONS = {1}


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


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _corpus_key(submission_id: int, episode_id: int, recorded_seat: int) -> str:
    return f"{submission_id}:{episode_id}:{recorded_seat}"


def _replay_action_trace(replay: dict[str, Any], recorded_seat: int) -> list[dict[str, Any]]:
    steps = replay.get("steps") or []
    trace = []
    for index in range(1, len(steps)):
        previous = steps[index - 1][recorded_seat]
        recorded = steps[index][recorded_seat]
        observation = previous.get("observation", {}) if isinstance(previous, dict) else {}
        try:
            observation_step = int(observation.get("step", index - 1))
        except (TypeError, ValueError):
            observation_step = index - 1
        action = recorded.get("action") if isinstance(recorded, dict) else None
        if isinstance(action, dict):
            trace.append({"observation_step": observation_step, "action": action})
    return trace


def _validated_replay_payload(path: Path, expected_episode_id: int) -> dict[str, Any]:
    try:
        replay = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid replay JSON at {path}: {exc}") from exc
    steps = replay.get("steps") or []
    actual_id = (replay.get("info") or {}).get("EpisodeId")
    try:
        payload_episode_id = int(actual_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"replay at {path} has no numeric info.EpisodeId") from exc
    if payload_episode_id != expected_episode_id:
        raise ValueError(
            f"replay payload EpisodeId {payload_episode_id} does not match "
            f"expected {expected_episode_id}: {path}"
        )
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], list):
        raise ValueError(f"replay at {path} has no usable steps")
    if len(steps[0]) < 2:
        raise ValueError(f"replay at {path} must contain at least two player states")
    return replay


def _replay_manifest_entry(
    path: Path,
    *,
    submission_id: int,
    episode_id: int,
    recorded_seat: int,
    expected_engine_version: str,
) -> dict[str, Any]:
    replay = _validated_replay_payload(path, episode_id)
    player_count = len(replay["steps"][0])
    if recorded_seat < 0 or recorded_seat >= player_count:
        raise ValueError(
            f"recorded seat {recorded_seat} is outside replay player count {player_count}"
        )
    replay_schema_version = replay.get("schema_version")
    if replay_schema_version not in SUPPORTED_REPLAY_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported replay schema_version {replay_schema_version!r}")
    module_version = str(replay.get("module_version") or "")
    if module_version != expected_engine_version:
        raise ValueError(
            f"replay module_version {module_version!r} does not match installed "
            f"kaggle-environments {expected_engine_version!r}"
        )
    environment_name = str(replay.get("name") or "")
    if environment_name != "kaggriculture":
        raise ValueError(f"unexpected replay environment {environment_name!r}")
    content = path.read_bytes()
    return {
        "key": _corpus_key(submission_id, episode_id, recorded_seat),
        "submission_id": submission_id,
        "source_episode_id": episode_id,
        "recorded_seat": recorded_seat,
        "replay_sha256": hashlib.sha256(content).hexdigest(),
        "replay_size_bytes": len(content),
        "payload_episode_id": episode_id,
        "replay_schema_version": replay_schema_version,
        "replay_module_version": module_version,
        "environment_name": environment_name,
        "configuration_sha256": _sha256_json(replay.get("configuration", {}) or {}),
        "action_trace_sha256": _sha256_json(
            _replay_action_trace(replay, recorded_seat)
        ),
    }


def _finalize_manifest(manifest: dict[str, Any]) -> None:
    manifest["entries"] = sorted(manifest["entries"], key=lambda entry: entry["key"])
    manifest["manifest_sha256"] = _sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )


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
                "leaderboard_rating": _number(row.get("score")),
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
        "submission_rating": _number(best.get("publicScore")),
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
            _validated_replay_payload(path, episode_id)
            return True
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


def _error_trace(
    entry: dict[str, Any],
    source_public_match: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    return {
        "source_episode_id": int(entry["source_episode_id"]),
        "recorded_seat": int(entry["recorded_seat"]),
        "corpus_key": str(entry["key"]),
        "source_public_match": source_public_match,
        "episodes": [],
        "both_seats_won": False,
        "error": f"{type(exc).__name__}: {exc}",
    }


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    traces = [
        trace
        for team in report["teams"]
        for trace in team.get("traces", [])
    ]
    episodes = [episode for trace in traces for episode in trace["episodes"]]
    valid_episodes = [episode for episode in episodes if not episode["invalid_episode"]]
    trace_keys = [
        trace.get("corpus_key")
        or _corpus_key(
            int(team.get("submission_id") or -1),
            int(trace["source_episode_id"]),
            int(trace["recorded_seat"]),
        )
        for team in report["teams"]
        for trace in team.get("traces", [])
    ]
    source_episode_clusters: dict[int, list[dict[str, Any]]] = {}
    trace_counts_by_source: dict[int, int] = {}
    for trace in traces:
        source_episode_id = int(trace["source_episode_id"])
        trace_counts_by_source[source_episode_id] = (
            trace_counts_by_source.get(source_episode_id, 0) + 1
        )
        source_episode_clusters.setdefault(source_episode_id, []).extend(
            episode for episode in trace["episodes"] if not episode["invalid_episode"]
        )
    cluster_win_rates = [
        statistics.mean(float(episode["candidate_win"]) for episode in cluster)
        for cluster in source_episode_clusters.values()
        if cluster
    ]
    cluster_mean_margins = [
        statistics.mean(episode["margin"] for episode in cluster)
        for cluster in source_episode_clusters.values()
        if cluster
    ]
    paired_seat_divergences = [
        abs(trace["episodes"][0]["margin"] - trace["episodes"][1]["margin"])
        for trace in traces
        if len(trace["episodes"]) == 2
        and not any(episode["invalid_episode"] for episode in trace["episodes"])
    ]
    manifest_entries = (report.get("corpus_manifest") or {}).get("entries") or []
    raw_win_rate = (
        statistics.mean(float(episode["candidate_win"]) for episode in valid_episodes)
        if valid_episodes
        else 0.0
    )
    raw_mean_margin = (
        statistics.mean(episode["margin"] for episode in valid_episodes)
        if valid_episodes
        else 0.0
    )
    cluster_adjusted_win_rate = (
        statistics.mean(cluster_win_rates) if cluster_win_rates else 0.0
    )
    cluster_adjusted_mean_margin = (
        statistics.mean(cluster_mean_margins) if cluster_mean_margins else 0.0
    )
    cluster_fields = {
        "unique_trace_keys": len(set(trace_keys)),
        "duplicate_trace_keys": len(trace_keys) - len(set(trace_keys)),
        "unique_source_episodes": len(source_episode_clusters),
        "shared_source_episode_clusters": sum(
            count > 1 for count in trace_counts_by_source.values()
        ),
        "max_traces_per_source_episode": max(
            trace_counts_by_source.values(), default=0
        ),
        "unique_replay_payloads": len(
            {
                entry["replay_sha256"]
                for entry in manifest_entries
                if entry.get("replay_sha256")
            }
        ),
        "unique_action_traces": len(
            {
                entry["action_trace_sha256"]
                for entry in manifest_entries
                if entry.get("action_trace_sha256")
            }
        ),
        "cluster_adjusted_win_rate": cluster_adjusted_win_rate,
        "cluster_adjusted_mean_margin": cluster_adjusted_mean_margin,
        "cluster_vs_raw_win_rate_divergence": cluster_adjusted_win_rate - raw_win_rate,
        "cluster_vs_raw_mean_margin_divergence": (
            cluster_adjusted_mean_margin - raw_mean_margin
        ),
        "mean_absolute_paired_seat_margin_divergence": (
            statistics.mean(paired_seat_divergences) if paired_seat_divergences else 0.0
        ),
        "trace_errors": sum(bool(trace.get("error")) for trace in traces),
        "completed_trace_gates": sum(bool(trace["episodes"]) for trace in traces),
    }
    if not episodes:
        return {
            "teams_requested": report["settings"]["top"],
            "teams_benchmarked": sum(
                bool(team.get("traces")) for team in report["teams"]
            ),
            "trace_episodes": len(traces),
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
            **cluster_fields,
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
        **cluster_fields,
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
        f"Competition: `{report['competition']}`  ",
        "Corpus capture cutoff: "
        f"`{(report.get('corpus_manifest') or {}).get('capture_cutoff', '-')}`  ",
        "Corpus manifest SHA-256: "
        f"`{(report.get('corpus_manifest') or {}).get('manifest_sha256', '-')}`",
        "",
        "## Summary",
        "",
        f"- Teams benchmarked: {summary['teams_benchmarked']} / {summary['teams_requested']}",
        f"- Recorded traces: {summary['trace_episodes']}",
        f"- Completed trace gates: {summary['completed_trace_gates']}",
        f"- Unique trace keys: {summary['unique_trace_keys']}",
        f"- Unique source episodes: {summary['unique_source_episodes']}",
        f"- Unique replay payloads: {summary['unique_replay_payloads']}",
        f"- Unique recorded action traces: {summary['unique_action_traces']}",
        f"- Shared source-episode clusters: {summary['shared_source_episode_clusters']}",
        f"- Both-seat simulations: {summary['simulations']}",
        f"- Invalid simulations: {summary['invalid_simulations']}",
        f"- Wins/losses: {summary['wins']} / {summary['losses']}",
        f"- Win rate: {summary['win_rate']:.1%}",
        f"- Mean margin: {summary['mean_margin']:+,.1f}",
        f"- Median margin: {summary['median_margin']:+,.1f}",
        "- Source-episode cluster-adjusted win rate: "
        f"{summary['cluster_adjusted_win_rate']:.1%}",
        "- Cluster-vs-raw win-rate divergence: "
        f"{summary['cluster_vs_raw_win_rate_divergence']:+.1%}",
        "- Source-episode cluster-adjusted mean margin: "
        f"{summary['cluster_adjusted_mean_margin']:+,.1f}",
        "- Cluster-vs-raw mean-margin divergence: "
        f"{summary['cluster_vs_raw_mean_margin_divergence']:+,.1f}",
        "- Mean absolute paired-seat margin divergence: "
        f"{summary['mean_absolute_paired_seat_margin_divergence']:+,.1f}",
        f"- Teams swept across every sampled trace: {summary['teams_swept']}",
        f"- Teams with errors: {summary['errors']}",
        f"- Trace simulation errors: {summary['trace_errors']}",
        "",
        "## Leaderboard traces",
        "",
        "| Rank | Team | Leaderboard rating | Submission rating | Submission | "
        "Traces | W-L | Mean margin | Result |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|",
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
            "| {rank} | {name} | {leaderboard_rating:,.1f} | "
            "{submission_rating:,.1f} | {submission} | {traces} | "
            "{wins}-{losses} | {margin:+,.1f} | {result} |".format(
                rank=team["rank"],
                name=str(team["team_name"]).replace("|", "\\|"),
                leaderboard_rating=team.get(
                    "leaderboard_rating", team.get("rating", 0.0)
                ),
                submission_rating=team.get("submission_rating", 0.0),
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
    capture_cutoff = datetime.now(UTC).isoformat()
    engine_version = importlib.metadata.version("kaggle-environments")
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "competition": competition,
        "candidate": {
            "path": str(candidate),
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        },
        "engine_version": engine_version,
        "kaggle_api_version": importlib.metadata.version("kaggle"),
        "method": "latest public completed episode actions, replayed open-loop from both seats",
        "settings": {
            "top": top,
            "episodes_per_team": episodes_per_team,
            "cache_dir": str(cache_dir.expanduser().resolve()),
            "refresh": refresh,
        },
        "corpus_manifest": {
            "schema_version": CORPUS_SCHEMA_VERSION,
            "capture_cutoff": capture_cutoff,
            "engine_version": engine_version,
            "entries": [],
        },
        "teams": [],
    }
    pending: list[tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]] = []
    seen_corpus_keys: set[str] = set()

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
                entry = _replay_manifest_entry(
                    replay,
                    submission_id=submission["submission_id"],
                    episode_id=episode_id,
                    recorded_seat=recorded_seat,
                    expected_engine_version=engine_version,
                )
                if entry["key"] in seen_corpus_keys:
                    raise ValueError(f"duplicate corpus key {entry['key']}")
                seen_corpus_keys.add(entry["key"])
                report["corpus_manifest"]["entries"].append(entry)
                pending.append((team, episode, replay, entry))
        except Exception as exc:  # keep the rest of a live snapshot usable
            team["error"] = f"{type(exc).__name__}: {exc}"

    for team, episode, replay, entry in pending:
        source_public_match = {
            "created_at": episode.get("createTime"),
            "ended_at": episode.get("endTime"),
            "agents": episode.get("agents") or [],
        }
        try:
            gate = run_replay_trace_gate(
                candidate,
                replay,
                opponent_seat=int(episode["recorded_seat"]),
            )
            compact = _compact_gate(gate)
            compact["corpus_key"] = entry["key"]
            compact["source_public_match"] = source_public_match
            team["traces"].append(compact)
        except Exception as exc:  # preserve other downloaded traces
            team["error"] = f"{type(exc).__name__}: {exc}"
            team["traces"].append(_error_trace(entry, source_public_match, exc))
    _finalize_manifest(report["corpus_manifest"])
    report["summary"] = summarize(report)
    return report


def _validate_snapshot_manifest(
    snapshot: dict[str, Any], expected_engine_version: str
) -> dict[str, dict[str, Any]]:
    if snapshot.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"snapshot schema_version {snapshot.get('schema_version')!r} is unsupported; "
            "capture a fresh immutable corpus"
        )
    if snapshot.get("engine_version") != expected_engine_version:
        raise ValueError(
            f"snapshot engine {snapshot.get('engine_version')!r} does not match installed "
            f"kaggle-environments {expected_engine_version!r}"
        )
    manifest = snapshot.get("corpus_manifest")
    if not isinstance(manifest, dict):
        raise ValueError("snapshot has no corpus_manifest")
    if manifest.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported corpus manifest schema {manifest.get('schema_version')!r}"
        )
    if manifest.get("engine_version") != expected_engine_version:
        raise ValueError("corpus manifest engine_version does not match installed engine")
    capture_cutoff = manifest.get("capture_cutoff")
    try:
        parsed_cutoff = datetime.fromisoformat(str(capture_cutoff))
    except ValueError as exc:
        raise ValueError("corpus manifest capture_cutoff is not ISO-8601") from exc
    if parsed_cutoff.tzinfo is None:
        raise ValueError("corpus manifest capture_cutoff must include a timezone")
    expected_manifest_hash = _sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    if manifest.get("manifest_sha256") != expected_manifest_hash:
        raise ValueError("corpus manifest digest mismatch")

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("corpus manifest entries must be a list")
    entry_by_key: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("corpus manifest entry must be an object")
        expected_key = _corpus_key(
            int(entry["submission_id"]),
            int(entry["source_episode_id"]),
            int(entry["recorded_seat"]),
        )
        if entry.get("key") != expected_key:
            raise ValueError(
                "corpus entry key does not match composite identity: "
                f"{entry.get('key')}"
            )
        if expected_key in entry_by_key:
            raise ValueError(f"duplicate corpus key {expected_key}")
        entry_by_key[expected_key] = entry

    trace_keys = []
    for team in snapshot.get("teams", []):
        for trace in team.get("traces", []):
            expected_key = _corpus_key(
                int(team["submission_id"]),
                int(trace["source_episode_id"]),
                int(trace["recorded_seat"]),
            )
            if trace.get("corpus_key") != expected_key:
                raise ValueError(
                    "trace corpus key does not match composite identity: "
                    f"{trace.get('corpus_key')}"
                )
            trace_keys.append(expected_key)
    if len(trace_keys) != len(set(trace_keys)):
        raise ValueError("snapshot contains duplicate composite trace keys")
    if set(trace_keys) != set(entry_by_key):
        raise ValueError("snapshot traces and corpus manifest entries do not match")
    return entry_by_key


def _verify_cached_replay_entry(
    replay_path: Path,
    entry: dict[str, Any],
    expected_engine_version: str,
) -> None:
    actual = _replay_manifest_entry(
        replay_path,
        submission_id=int(entry["submission_id"]),
        episode_id=int(entry["source_episode_id"]),
        recorded_seat=int(entry["recorded_seat"]),
        expected_engine_version=expected_engine_version,
    )
    for field in (
        "key",
        "replay_sha256",
        "replay_size_bytes",
        "payload_episode_id",
        "replay_schema_version",
        "replay_module_version",
        "environment_name",
        "configuration_sha256",
        "action_trace_sha256",
    ):
        if actual[field] != entry.get(field):
            raise ValueError(
                f"cached replay {field} mismatch for corpus key {entry['key']}: "
                f"expected {entry.get(field)!r}, got {actual[field]!r}"
            )


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
    engine_version = importlib.metadata.version("kaggle-environments")
    entry_by_key = _validate_snapshot_manifest(snapshot, engine_version)
    resolved_cache_dir = cache_dir.expanduser().resolve()
    for entry in entry_by_key.values():
        episode_id = int(entry["source_episode_id"])
        replay_path = resolved_cache_dir / f"episode-{episode_id}-replay.json"
        if not replay_path.is_file():
            raise FileNotFoundError(
                f"cached replay missing for episode {episode_id}: {replay_path}"
            )
        _verify_cached_replay_entry(replay_path, entry, engine_version)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "competition": snapshot["competition"],
        "candidate": {
            "path": str(candidate),
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        },
        "engine_version": engine_version,
        "kaggle_api_version": importlib.metadata.version("kaggle"),
        "method": "exact saved leaderboard snapshot actions, replayed open-loop from both seats",
        "settings": {
            "top": len(snapshot["teams"]),
            "episodes_per_team": snapshot.get("settings", {}).get("episodes_per_team", 1),
            "cache_dir": str(resolved_cache_dir),
            "refresh": False,
            "snapshot": str(snapshot_path),
            "snapshot_generated_at": snapshot.get("generated_at"),
            "snapshot_candidate_sha256": snapshot.get("candidate", {}).get("sha256"),
        },
        "corpus_manifest": snapshot["corpus_manifest"],
        "teams": [],
    }
    for old_team in snapshot["teams"]:
        team = {
            key: old_team.get(key)
            for key in (
                "rank",
                "team_id",
                "team_name",
                "leaderboard_rating",
                "submission_rating",
                "submission_date",
                "submission_id",
                "submitted_at",
            )
        }
        team["traces"] = []
        report["teams"].append(team)
        for old_trace in old_team.get("traces", []):
            episode_id = int(old_trace["source_episode_id"])
            corpus_key = str(old_trace["corpus_key"])
            entry = entry_by_key[corpus_key]
            replay = resolved_cache_dir / f"episode-{episode_id}-replay.json"
            try:
                recorded_seat = int(entry["recorded_seat"])
                gate = run_replay_trace_gate(
                    candidate,
                    replay,
                    opponent_seat=int(recorded_seat),
                )
                compact = _compact_gate(gate)
                compact["corpus_key"] = corpus_key
                compact["source_public_match"] = old_trace.get("source_public_match", {})
                team["traces"].append(compact)
            except Exception as exc:
                team["error"] = f"{type(exc).__name__}: {exc}"
                team["traces"].append(
                    _error_trace(
                        entry,
                        old_trace.get("source_public_match", {}),
                        exc,
                    )
                )
    report["summary"] = summarize(report)
    return report


def _api() -> Any:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def _validate_cli_paths(
    *,
    candidate: Path,
    cache_dir: Path,
    output: Path,
    markdown: Path,
    snapshot: Path | None,
) -> None:
    if output == markdown:
        raise ValueError("--output and --markdown must differ")

    write_targets = {"--output": output, "--markdown": markdown}
    read_targets = {"--candidate": candidate}
    if snapshot is not None:
        read_targets["--snapshot"] = snapshot
    for write_name, write_path in write_targets.items():
        for read_name, read_path in read_targets.items():
            if write_path == read_path:
                raise ValueError(f"{write_name} must differ from {read_name}")
        if write_path == cache_dir or write_path.is_relative_to(cache_dir):
            raise ValueError(
                f"{write_name} must be outside --cache-dir to avoid overwriting replay data"
            )


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
    args.candidate = args.candidate.expanduser().resolve()
    args.cache_dir = args.cache_dir.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    args.markdown = args.markdown.expanduser().resolve()
    if args.snapshot is not None:
        args.snapshot = args.snapshot.expanduser().resolve()
    try:
        _validate_cli_paths(
            candidate=args.candidate,
            cache_dir=args.cache_dir,
            output=args.output,
            markdown=args.markdown,
            snapshot=args.snapshot,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.snapshot:
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
    return (
        1
        if summary["errors"]
        or summary.get("trace_errors", 0)
        or summary["invalid_simulations"]
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
