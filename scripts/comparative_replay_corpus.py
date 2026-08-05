"""Compare a candidate and baseline against a local Kaggriculture replay corpus.

Every replay supplies one immutable, open-loop recorded opponent.  Candidate
and baseline are each run against that same action trace from both runtime
seats.  The resulting candidate-minus-baseline margin delta isolates policy
changes from the recorded opponent and source seed; it does not reconstruct an
adaptive opponent or estimate live ladder win probability.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import statistics
from typing import Any

try:  # Supports module and direct-script execution.
    from scripts.replay_trace_gate import run_replay_trace_gate
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI
    from replay_trace_gate import run_replay_trace_gate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "main.py"
DEFAULT_JSON = ROOT / "artifacts" / "comparative-replay-corpus.json"
DEFAULT_MARKDOWN = ROOT / "artifacts" / "comparative-replay-corpus.md"
SCHEMA_VERSION = 2
CORPUS_SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def validate_path_roles(
    *,
    candidate: Path,
    baseline: Path,
    replay_paths: list[Path],
    output: Path | None = None,
    markdown: Path | None = None,
) -> tuple[Path, Path, list[Path], Path | None, Path | None]:
    """Resolve paths and reject every unsafe read/write role collision."""
    candidate = _resolved(candidate)
    baseline = _resolved(baseline)
    replays = [_resolved(path) for path in replay_paths]
    output = _resolved(output) if output is not None else None
    markdown = _resolved(markdown) if markdown is not None else None

    if candidate == baseline:
        raise ValueError("candidate and baseline resolve to the same file")
    if len(replays) != len(set(replays)):
        raise ValueError("replay inputs contain duplicate resolved paths")
    input_roles = {candidate: "candidate", baseline: "baseline"}
    for replay in replays:
        prior = input_roles.get(replay)
        if prior is not None:
            raise ValueError(f"replay input collides with {prior}: {replay}")
        input_roles[replay] = "replay"

    writes = [("output", output), ("markdown", markdown)]
    if output is not None and markdown is not None and output == markdown:
        raise ValueError("output and markdown resolve to the same path")
    for role, path in writes:
        if path is None:
            continue
        prior = input_roles.get(path)
        if prior is not None:
            raise ValueError(f"{role} collides with {prior} input: {path}")
        if path.is_dir():
            raise IsADirectoryError(path)
    return candidate, baseline, replays, output, markdown


def _team_names(replay: dict[str, Any]) -> list[str]:
    info = replay.get("info", {}) or {}
    names = info.get("TeamNames")
    if isinstance(names, list) and names:
        return [str(name) for name in names]
    agents = info.get("Agents")
    if isinstance(agents, list):
        return [
            str(agent.get("Name", "")) if isinstance(agent, dict) else ""
            for agent in agents
        ]
    return []


def resolve_corpus_seat(
    replay: dict[str, Any],
    *,
    opponent_seat: int | None = None,
    recorded_team: str | None = None,
    exclude_team: str | None = None,
) -> int:
    """Resolve exactly one recorded trace seat using one selection mode."""
    supplied = sum(
        value is not None for value in (opponent_seat, recorded_team, exclude_team)
    )
    if supplied != 1:
        raise ValueError(
            "provide exactly one of opponent_seat, recorded_team, or exclude_team"
        )
    player_count = len(replay["steps"][0])
    if opponent_seat is not None:
        if not 0 <= opponent_seat < player_count:
            raise ValueError(
                f"opponent seat must be between 0 and {player_count - 1}"
            )
        return opponent_seat

    names = _team_names(replay)
    if len(names) != player_count:
        raise ValueError(
            f"replay exposes {len(names)} team names for {player_count} players"
        )
    if recorded_team is not None:
        wanted = recorded_team.casefold()
        matches = [
            index for index, name in enumerate(names) if name.casefold() == wanted
        ]
    else:
        assert exclude_team is not None
        excluded = exclude_team.casefold()
        matches = [
            index for index, name in enumerate(names) if name.casefold() != excluded
        ]
    if len(matches) != 1:
        mode = "recorded team" if recorded_team is not None else "non-excluded team"
        available = ", ".join(repr(name) for name in names) or "<unavailable>"
        raise ValueError(
            f"{mode} matched {len(matches)} seats; available teams: {available}"
        )
    return matches[0]


def _latest_observation(replay: dict[str, Any], seat: int) -> dict[str, Any]:
    for states in reversed(replay["steps"]):
        if seat >= len(states) or not isinstance(states[seat], dict):
            continue
        observation = states[seat].get("observation")
        if isinstance(observation, dict) and observation.get("farms"):
            return observation
    return {}


def recorded_public_footprint(
    replay: dict[str, Any], recorded_seat: int
) -> dict[str, Any]:
    """Extract a stable public production footprint for cluster summaries."""
    observation = _latest_observation(replay, recorded_seat)
    farms = observation.get("farms") or []
    farm = farms[recorded_seat] if recorded_seat < len(farms) else {}
    farm = farm if isinstance(farm, dict) else {}
    animals: dict[str, int] = {}
    crops: dict[str, int] = {}
    pastures = 0
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PASTURE":
                pastures += 1
            animal = tile.get("animal")
            if animal:
                animals[str(animal)] = animals.get(str(animal), 0) + 1
            if tile.get("kind") == "PLANT" and tile.get("crop"):
                crop = str(tile["crop"])
                crops[crop] = crops.get(crop, 0) + 1
    return {
        "hands": len(farm.get("hands", []) or []),
        "unlocked_quadrants": len(farm.get("unlocked_quadrants", []) or []),
        "pastures": pastures,
        "animals": dict(sorted(animals.items())),
        "crops": dict(sorted(crops.items())),
    }


def _footprint_key(footprint: dict[str, Any]) -> str:
    return json.dumps(footprint, sort_keys=True, separators=(",", ":"))


def _replay_action_trace(
    replay: dict[str, Any], recorded_seat: int
) -> list[dict[str, Any]]:
    trace = []
    for index in range(1, len(replay["steps"])):
        previous = replay["steps"][index - 1][recorded_seat]
        recorded = replay["steps"][index][recorded_seat]
        observation = previous.get("observation", {}) if isinstance(previous, dict) else {}
        try:
            observation_step = int(observation.get("step", index - 1))
        except (TypeError, ValueError):
            observation_step = index - 1
        action = recorded.get("action") if isinstance(recorded, dict) else None
        if isinstance(action, dict):
            trace.append({"observation_step": observation_step, "action": action})
    return trace


def _load_replay_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    content = path.read_bytes()
    try:
        replay = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid replay JSON at {path}: {exc}") from exc
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ValueError(f"replay at {path} must contain at least two steps")
    if not all(isinstance(states, list) and states for states in steps):
        raise ValueError(f"every replay step at {path} must contain player states")
    return replay, content


def _manifest_entry(
    path: Path,
    replay: dict[str, Any],
    content: bytes,
    recorded_seat: int,
    engine_version: str,
) -> dict[str, Any]:
    info = replay.get("info", {}) or {}
    try:
        episode_id = int(info["EpisodeId"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"replay at {path} has no numeric info.EpisodeId") from exc
    raw_seed = info.get("seed", (replay.get("configuration", {}) or {}).get("seed"))
    if raw_seed is None:
        raise ValueError(f"replay at {path} has no resolved seed")
    try:
        seed = int(raw_seed)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"replay at {path} has a non-numeric seed") from exc
    module_version = str(replay.get("module_version") or "")
    if module_version != engine_version:
        raise ValueError(
            f"replay module_version {module_version!r} does not match installed "
            f"kaggle-environments {engine_version!r}: {path}"
        )
    if replay.get("name") != "kaggriculture":
        raise ValueError(f"replay at {path} is not a kaggriculture replay")
    if replay.get("schema_version") != 1:
        raise ValueError(
            f"replay at {path} has unsupported schema_version "
            f"{replay.get('schema_version')!r}"
        )
    return {
        "composite_key": f"{episode_id}:{recorded_seat}",
        "source_episode_id": episode_id,
        "source_seed": seed,
        "recorded_seat": recorded_seat,
        "replay_path": str(path),
        "replay_sha256": hashlib.sha256(content).hexdigest(),
        "replay_size_bytes": len(content),
        "replay_schema_version": replay["schema_version"],
        "replay_module_version": module_version,
        "environment_name": replay["name"],
        "configuration_sha256": _sha256_json(replay.get("configuration", {}) or {}),
        "action_trace_sha256": _sha256_json(
            _replay_action_trace(replay, recorded_seat)
        ),
    }


def _validate_file_snapshot(
    path: Path, *, expected_sha256: str, expected_size: int, role: str
) -> None:
    content = path.read_bytes()
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if len(content) != expected_size or actual_sha256 != expected_sha256:
        raise RuntimeError(f"{role} changed after corpus capture: {path}")


def _finalize_manifest(entries: list[dict[str, Any]], engine_version: str) -> dict[str, Any]:
    ordered = sorted(entries, key=lambda entry: entry["composite_key"])
    manifest: dict[str, Any] = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "engine_version": engine_version,
        "entries": ordered,
    }
    manifest["manifest_sha256"] = _sha256_json(manifest)
    return manifest


def _compact_episode(episode: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_seat": int(episode["candidate_seat"]),
        "margin": float(episode["margin"]),
        "invalid_episode": bool(episode["invalid_episode"]),
        "statuses": list(episode.get("statuses", [])),
    }


def _comparisons(
    baseline_gate: dict[str, Any], candidate_gate: dict[str, Any]
) -> list[dict[str, Any]]:
    baseline = {
        int(episode["candidate_seat"]): episode
        for episode in baseline_gate["episodes"]
    }
    candidate = {
        int(episode["candidate_seat"]): episode
        for episode in candidate_gate["episodes"]
    }
    if set(baseline) != {0, 1} or set(candidate) != {0, 1}:
        raise ValueError("both gates must contain exactly one episode for each seat")
    rows = []
    for seat in (0, 1):
        baseline_episode = baseline[seat]
        candidate_episode = candidate[seat]
        invalid = bool(
            baseline_episode["invalid_episode"]
            or candidate_episode["invalid_episode"]
        )
        baseline_margin = float(baseline_episode["margin"])
        candidate_margin = float(candidate_episode["margin"])
        rows.append(
            {
                "runtime_seat": seat,
                "baseline_margin": baseline_margin,
                "candidate_margin": candidate_margin,
                "delta": candidate_margin - baseline_margin,
                "invalid_comparison": invalid,
                "baseline_statuses": list(baseline_episode.get("statuses", [])),
                "candidate_statuses": list(candidate_episode.get("statuses", [])),
            }
        )
    return rows


def _delta_summary(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in comparisons if not row["invalid_comparison"]]
    deltas = [float(row["delta"]) for row in valid]
    return {
        "comparisons": len(comparisons),
        "valid_comparisons": len(valid),
        "invalid_comparisons": len(comparisons) - len(valid),
        "positive": sum(delta > 0 for delta in deltas),
        "unchanged": sum(delta == 0 for delta in deltas),
        "negative": sum(delta < 0 for delta in deltas),
        "mean_delta": statistics.mean(deltas) if deltas else 0.0,
        "median_delta": statistics.median(deltas) if deltas else 0.0,
        "minimum_delta": min(deltas, default=0.0),
        "maximum_delta": max(deltas, default=0.0),
    }


def _cluster_rows(
    traces: list[dict[str, Any]], field: str
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for trace in traces:
        groups.setdefault(str(trace[field]), []).append(trace)
    rows = []
    for key, members in groups.items():
        comparisons = [
            comparison
            for trace in members
            for comparison in trace.get("comparisons", [])
        ]
        row = {"key": key, "traces": len(members), **_delta_summary(comparisons)}
        if field == "footprint_key":
            row["footprint"] = members[0]["recorded_public_footprint"]
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["traces"], row["key"]))


def summarize(
    report: dict[str, Any], *, max_negative_comparisons: int, min_mean_delta: float
) -> dict[str, Any]:
    comparisons = [
        comparison
        for trace in report["traces"]
        for comparison in trace.get("comparisons", [])
    ]
    summary = {
        "replay_files": len(report["traces"]),
        "successful_traces": sum(not trace.get("error") for trace in report["traces"]),
        "trace_errors": sum(bool(trace.get("error")) for trace in report["traces"]),
        **_delta_summary(comparisons),
    }
    valid_trace_means = [
        statistics.mean(
            comparison["delta"]
            for comparison in trace["comparisons"]
            if not comparison["invalid_comparison"]
        )
        for trace in report["traces"]
        if trace.get("comparisons")
        and any(
            not comparison["invalid_comparison"]
            for comparison in trace["comparisons"]
        )
    ]
    summary.update(
        {
            "traces_improved": sum(delta > 0 for delta in valid_trace_means),
            "traces_unchanged": sum(delta == 0 for delta in valid_trace_means),
            "traces_regressed": sum(delta < 0 for delta in valid_trace_means),
            "mean_trace_delta": (
                statistics.mean(valid_trace_means) if valid_trace_means else 0.0
            ),
            "max_negative_comparisons": max_negative_comparisons,
            "min_mean_delta": min_mean_delta,
        }
    )
    summary["passed"] = bool(
        summary["valid_comparisons"]
        and summary["trace_errors"] == 0
        and summary["invalid_comparisons"] == 0
        and summary["negative"] <= max_negative_comparisons
        and summary["mean_delta"] >= min_mean_delta
    )
    return summary


def build_report(
    *,
    candidate: Path,
    baseline: Path,
    replay_paths: list[Path],
    opponent_seat: int | None = None,
    recorded_team: str | None = None,
    exclude_team: str | None = None,
    max_negative_comparisons: int = 0,
    min_mean_delta: float = 0.0,
) -> dict[str, Any]:
    if max_negative_comparisons < 0:
        raise ValueError("max_negative_comparisons must be non-negative")
    if not math.isfinite(min_mean_delta):
        raise ValueError("min_mean_delta must be finite")
    candidate, baseline, replay_paths, _, _ = validate_path_roles(
        candidate=candidate,
        baseline=baseline,
        replay_paths=replay_paths,
    )
    for agent in (candidate, baseline):
        if not agent.is_file():
            raise FileNotFoundError(agent)
    candidate_content = candidate.read_bytes()
    baseline_content = baseline.read_bytes()
    candidate_sha256 = hashlib.sha256(candidate_content).hexdigest()
    baseline_sha256 = hashlib.sha256(baseline_content).hexdigest()
    engine_version = importlib.metadata.version("kaggle-environments")

    prepared: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    manifest_entries = []
    seen_composite: dict[str, Path] = {}
    seen_content: dict[str, Path] = {}
    for path in sorted(replay_paths, key=lambda value: str(value)):
        if not path.is_file():
            raise FileNotFoundError(path)
        replay, content = _load_replay_snapshot(path)
        seat = resolve_corpus_seat(
            replay,
            opponent_seat=opponent_seat,
            recorded_team=recorded_team,
            exclude_team=exclude_team,
        )
        entry = _manifest_entry(path, replay, content, seat, engine_version)
        prior_composite = seen_composite.get(entry["composite_key"])
        prior_content = seen_content.get(entry["replay_sha256"])
        duplicate_reasons = []
        if prior_composite is not None:
            duplicate_reasons.append(
                f"duplicate episode/seat composite {entry['composite_key']} "
                f"({prior_composite} and {path})"
            )
        if prior_content is not None:
            duplicate_reasons.append(
                f"duplicate replay content {entry['replay_sha256']} "
                f"({prior_content} and {path})"
            )
        if duplicate_reasons:
            raise ValueError("; ".join(duplicate_reasons))
        seen_composite[entry["composite_key"]] = path
        seen_content[entry["replay_sha256"]] = path
        manifest_entries.append(entry)
        prepared.append((path, replay, entry))

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "candidate and baseline replayed open-loop against identical traces from both seats",
        "candidate": {
            "path": str(candidate),
            "sha256": candidate_sha256,
            "size_bytes": len(candidate_content),
        },
        "baseline": {
            "path": str(baseline),
            "sha256": baseline_sha256,
            "size_bytes": len(baseline_content),
        },
        "engine_version": engine_version,
        "corpus_manifest": _finalize_manifest(manifest_entries, engine_version),
        "selection": {
            "opponent_seat": opponent_seat,
            "recorded_team": recorded_team,
            "exclude_team": exclude_team,
        },
        "traces": [],
    }
    for path, replay, entry in prepared:
        trace: dict[str, Any] = {
            "replay_path": str(path),
            "corpus_key": entry["composite_key"],
        }
        report["traces"].append(trace)
        try:
            _validate_file_snapshot(
                candidate,
                expected_sha256=candidate_sha256,
                expected_size=len(candidate_content),
                role="candidate",
            )
            _validate_file_snapshot(
                baseline,
                expected_sha256=baseline_sha256,
                expected_size=len(baseline_content),
                role="baseline",
            )
            _validate_file_snapshot(
                path,
                expected_sha256=entry["replay_sha256"],
                expected_size=entry["replay_size_bytes"],
                role="replay",
            )
            seat = int(entry["recorded_seat"])
            names = _team_names(replay)
            footprint = recorded_public_footprint(replay, seat)
            baseline_gate = run_replay_trace_gate(
                str(baseline), path, opponent_seat=seat
            )
            _validate_file_snapshot(
                path,
                expected_sha256=entry["replay_sha256"],
                expected_size=entry["replay_size_bytes"],
                role="replay",
            )
            candidate_gate = run_replay_trace_gate(
                str(candidate), path, opponent_seat=seat
            )
            _validate_file_snapshot(
                path,
                expected_sha256=entry["replay_sha256"],
                expected_size=entry["replay_size_bytes"],
                role="replay",
            )
            for label, gate in (
                ("baseline", baseline_gate),
                ("candidate", candidate_gate),
            ):
                if int(gate.get("source_episode_id")) != entry["source_episode_id"]:
                    raise RuntimeError(
                        f"{label} gate returned a different source episode"
                    )
                if int(gate.get("source_seed")) != entry["source_seed"]:
                    raise RuntimeError(f"{label} gate returned a different source seed")
            trace.update(
                {
                    "source_episode_id": entry["source_episode_id"],
                    "source_seed": entry["source_seed"],
                    "recorded_seat": seat,
                    "recorded_team": names[seat] if seat < len(names) else None,
                    "recorded_public_footprint": footprint,
                    "footprint_key": _footprint_key(footprint),
                    "baseline_episodes": [
                        _compact_episode(episode)
                        for episode in baseline_gate["episodes"]
                    ],
                    "candidate_episodes": [
                        _compact_episode(episode)
                        for episode in candidate_gate["episodes"]
                    ],
                    "comparisons": _comparisons(baseline_gate, candidate_gate),
                }
            )
            trace["summary"] = _delta_summary(trace["comparisons"])
        except Exception as exc:  # preserve the remainder of a large corpus
            trace["error"] = f"{type(exc).__name__}: {exc}"

    _validate_file_snapshot(
        candidate,
        expected_sha256=candidate_sha256,
        expected_size=len(candidate_content),
        role="candidate",
    )
    _validate_file_snapshot(
        baseline,
        expected_sha256=baseline_sha256,
        expected_size=len(baseline_content),
        role="baseline",
    )

    report["summary"] = summarize(
        report,
        max_negative_comparisons=max_negative_comparisons,
        min_mean_delta=min_mean_delta,
    )
    report["clusters"] = {
        "recorded_team": _cluster_rows(
            [trace for trace in report["traces"] if not trace.get("error")],
            "recorded_team",
        ),
        "public_footprint": _cluster_rows(
            [trace for trace in report["traces"] if not trace.get("error")],
            "footprint_key",
        ),
    }
    return report


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|")


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Comparative replay-corpus gate",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Candidate: `{report['candidate']['path']}`  ",
        f"Baseline: `{report['baseline']['path']}`  ",
        f"Engine: `kaggle-environments=={report['engine_version']}`  ",
        f"Corpus manifest SHA-256: `{report['corpus_manifest']['manifest_sha256']}`",
        "",
        "## Summary",
        "",
        f"- Gate: {'PASS' if summary['passed'] else 'FAIL'}",
        f"- Successful traces/errors: {summary['successful_traces']} / {summary['trace_errors']}",
        f"- Valid/invalid seat comparisons: {summary['valid_comparisons']} / {summary['invalid_comparisons']}",
        f"- Positive/unchanged/negative: {summary['positive']} / {summary['unchanged']} / {summary['negative']}",
        f"- Mean candidate-minus-baseline margin: {summary['mean_delta']:+,.1f}",
        f"- Median delta: {summary['median_delta']:+,.1f}",
        f"- Minimum/maximum delta: {summary['minimum_delta']:+,.1f} / {summary['maximum_delta']:+,.1f}",
        f"- Improved/unchanged/regressed traces: {summary['traces_improved']} / {summary['traces_unchanged']} / {summary['traces_regressed']}",
        "",
        "## Traces",
        "",
        "| Episode | Recorded team | Seat 0 delta | Seat 1 delta | Mean | Result |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for trace in report["traces"]:
        if trace.get("error"):
            lines.append(
                f"| - | - | - | - | - | ERROR: {_escape(trace['error'])} |"
            )
            continue
        valid = [
            row for row in trace["comparisons"] if not row["invalid_comparison"]
        ]
        by_seat = {row["runtime_seat"]: row for row in trace["comparisons"]}
        mean_delta = statistics.mean(row["delta"] for row in valid) if valid else 0.0
        result = (
            "INVALID"
            if len(valid) != 2
            else (
                "IMPROVED"
                if mean_delta > 0
                else "REGRESSED" if mean_delta < 0 else "UNCHANGED"
            )
        )
        lines.append(
            "| {episode} | {team} | {seat0:+,.1f} | {seat1:+,.1f} | "
            "{mean:+,.1f} | {result} |".format(
                episode=trace.get("source_episode_id", "-"),
                team=_escape(trace.get("recorded_team", "")),
                seat0=by_seat.get(0, {}).get("delta", 0.0),
                seat1=by_seat.get(1, {}).get("delta", 0.0),
                mean=mean_delta,
                result=result,
            )
        )
    lines.extend(
        [
            "",
            "## Public-footprint clusters",
            "",
            "| Traces | Comparisons | + / = / - | Mean delta | Footprint |",
            "|---:|---:|---:|---:|---|",
        ]
    )
    for cluster in report["clusters"]["public_footprint"]:
        lines.append(
            "| {traces} | {comparisons} | {positive} / {unchanged} / {negative} | "
            "{mean:+,.1f} | `{footprint}` |".format(
                traces=cluster["traces"],
                comparisons=cluster["comparisons"],
                positive=cluster["positive"],
                unchanged=cluster["unchanged"],
                negative=cluster["negative"],
                mean=cluster["mean_delta"],
                footprint=_escape(
                    json.dumps(cluster["footprint"], sort_keys=True, separators=(",", ":"))
                ),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Recorded actions are keyed only by observation step and remain open-loop after divergence.",
            "A delta is comparative stress-test evidence against an identical historical schedule,",
            "not execution of another team's source and not a live win-rate estimate.",
            "",
        ]
    )
    return "\n".join(lines)


def _replay_paths(directory: Path, pattern: str) -> list[Path]:
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    paths = sorted(path for path in directory.glob(pattern) if path.is_file())
    if not paths:
        raise FileNotFoundError(f"no replay files matched {pattern!r} under {directory}")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--replays-dir", type=Path, required=True)
    parser.add_argument("--pattern", default="*.json")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--opponent-seat", type=int)
    selector.add_argument("--recorded-team")
    selector.add_argument("--exclude-team")
    parser.add_argument("--max-negative-comparisons", type=int, default=0)
    parser.add_argument("--min-mean-delta", type=float, default=0.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    if args.max_negative_comparisons < 0:
        parser.error("--max-negative-comparisons must be non-negative")
    if not math.isfinite(args.min_mean_delta):
        parser.error("--min-mean-delta must be finite")
    replay_paths = _replay_paths(args.replays_dir, args.pattern)
    try:
        candidate, baseline, replay_paths, output, markdown = validate_path_roles(
            candidate=args.candidate,
            baseline=args.baseline,
            replay_paths=replay_paths,
            output=args.output,
            markdown=args.markdown,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    assert output is not None and markdown is not None

    report = build_report(
        candidate=candidate,
        baseline=baseline,
        replay_paths=replay_paths,
        opponent_seat=args.opponent_seat,
        recorded_team=args.recorded_team,
        exclude_team=args.exclude_team,
        max_negative_comparisons=args.max_negative_comparisons,
        min_mean_delta=args.min_mean_delta,
    )
    # Re-resolve immediately before writing so a newly introduced symlink or
    # alias cannot redirect a report onto an input file during a long corpus run.
    _, _, _, checked_output, checked_markdown = validate_path_roles(
        candidate=candidate,
        baseline=baseline,
        replay_paths=replay_paths,
        output=output,
        markdown=markdown,
    )
    assert checked_output == output and checked_markdown == markdown
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rendered = render_markdown(report)
    markdown.write_text(rendered, encoding="utf-8")
    print(rendered)
    print(f"\nJSON: {output}")
    print(f"Markdown: {markdown}")
    if not report["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
