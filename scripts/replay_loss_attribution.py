"""Attribute candidate replay-corpus gains and losses to time and market execution.

The harness re-runs candidate and baseline against the same immutable recorded
action trace from both seats.  It records engine-committed SELL units/revenue,
bank-margin checkpoints, causal time-window deltas, and outcome strata.  Only
each policy's contemporaneous public checkpoint state is online-safe.  Commit
events, candidate-minus-baseline deltas, final outcomes, and final-footprint
groupings are diagnostic or retrospective and are labelled accordingly.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterator

from kaggle_environments import make

try:  # Supports module and direct-script execution.
    from scripts.comparative_replay_corpus import (
        _canonical_json,
        _replay_action_trace,
        _sha256_json,
        recorded_public_footprint,
        resolve_corpus_seat,
        validate_path_roles,
    )
    from scripts.replay_trace_gate import (
        RecordedActionPolicy,
        _load_candidate,
        _replay_configuration,
        load_replay,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI
    from comparative_replay_corpus import (
        _canonical_json,
        _replay_action_trace,
        _sha256_json,
        recorded_public_footprint,
        resolve_corpus_seat,
        validate_path_roles,
    )
    from replay_trace_gate import (
        RecordedActionPolicy,
        _load_candidate,
        _replay_configuration,
        load_replay,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "artifacts" / "replay-loss-attribution.json"
DEFAULT_MARKDOWN = ROOT / "artifacts" / "replay-loss-attribution.md"
SCHEMA_VERSION = 1
SUPPORTED_COMPARISON_SCHEMA_VERSION = 2
SUPPORTED_CORPUS_MANIFEST_SCHEMA_VERSION = 1


def _get(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _parse_int_list(value: str) -> list[int]:
    try:
        values = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    except ValueError as exc:
        raise ValueError("checkpoints must be comma-separated integers") from exc
    if not values or values[0] < 0:
        raise ValueError("checkpoints must contain non-negative integers")
    return values


def _parse_windows(value: str) -> list[tuple[int, int]]:
    windows = []
    try:
        for item in value.split(","):
            start, end = (int(part.strip()) for part in item.split(":"))
            if start < 0 or end <= start:
                raise ValueError
            windows.append((start, end))
    except ValueError as exc:
        raise ValueError("windows must be comma-separated START:END pairs") from exc
    if not windows:
        raise ValueError("at least one window is required")
    ordered = sorted(windows)
    if ordered != windows or any(left[1] > right[0] for left, right in zip(windows, windows[1:])):
        raise ValueError("windows must be ordered and non-overlapping")
    return windows


def _file_identity(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _validate_identity(identity: dict[str, Any], role: str) -> None:
    path = Path(identity["path"])
    content = path.read_bytes()
    if len(content) != identity["size_bytes"] or hashlib.sha256(content).hexdigest() != identity["sha256"]:
        raise RuntimeError(f"{role} changed during attribution: {path}")


def _validate_replay_identity(identity: dict[str, Any]) -> None:
    path = Path(identity["replay_path"])
    content = path.read_bytes()
    if (
        len(content) != identity["replay_size_bytes"]
        or hashlib.sha256(content).hexdigest() != identity["replay_sha256"]
    ):
        raise RuntimeError(f"replay changed during attribution: {path}")


@contextmanager
def _capture_market_ledger() -> Iterator[list[dict[str, Any]]]:
    """Instrument the pinned engine's real commit path without changing it."""
    engine = importlib.import_module("kaggle_environments.envs.kaggriculture.kaggriculture")
    original_process = engine._process_market  # noqa: SLF001
    original_commit = engine._commit_unit  # noqa: SLF001
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    def commit(op, item, price, farm, private, market, shed_capacity=100):
        player = current.get("players", {}).get(id(farm))
        result = original_commit(op, item, price, farm, private, market, shed_capacity)
        if result and op == "SELL" and player is not None:
            events.append(
                {
                    "step": int(current["step"]),
                    "day": int(current["step"]) // int(current["turns_per_day"]),
                    "phase": int(current["step"]) % int(current["shop_interval"]),
                    "shop_phase": int(current["step"])
                    % int(current["shop_interval"]),
                    "center_phase": int(current["step"])
                    % int(current["center_interval"]),
                    "runtime_seat": int(player),
                    "product": str(item),
                    "price": float(price),
                    "revenue": float(price),
                }
            )
        return result

    def process(state, env):
        observation = state[0].observation
        farms = observation.farms
        step = int(_get(observation, "step", 0) or 0)
        turns_per_day = max(1, int(_get(env.configuration, "turnsPerDay", 24) or 24))
        shop_interval = max(
            1,
            int(_get(env.configuration, "townShopSellInterval", 4) or 4),
        )
        center_interval = max(
            1,
            int(_get(env.configuration, "townCenterSellInterval", 12) or 12),
        )
        current["step"] = step
        current["turns_per_day"] = turns_per_day
        current["shop_interval"] = shop_interval
        current["center_interval"] = center_interval
        current["players"] = {id(farm): index for index, farm in enumerate(farms)}
        return original_process(state, env)

    engine._commit_unit = commit  # type: ignore[attr-defined]  # noqa: SLF001
    engine._process_market = process  # type: ignore[attr-defined]  # noqa: SLF001
    try:
        yield events
    finally:
        engine._process_market = original_process  # type: ignore[attr-defined]  # noqa: SLF001
        engine._commit_unit = original_commit  # type: ignore[attr-defined]  # noqa: SLF001


def _public_farm_counts(farm: Any) -> dict[str, Any]:
    animals: dict[str, int] = {}
    crops: dict[str, int] = {}
    for row in _get(farm, "tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal:
                animals[str(animal)] = animals.get(str(animal), 0) + 1
            if tile.get("kind") == "PLANT" and tile.get("crop"):
                crop = str(tile["crop"])
                crops[crop] = crops.get(crop, 0) + 1
    return {
        "money": float(_get(farm, "money", 0.0) or 0.0),
        "hands": len(_get(farm, "hands", []) or []),
        "animals": dict(sorted(animals.items())),
        "crops": dict(sorted(crops.items())),
    }


def _checkpoint_rows(env: Any, candidate_seat: int, checkpoints: list[int]) -> dict[str, Any]:
    wanted = set(checkpoints)
    rows: dict[str, Any] = {}
    for states in env.steps:
        observation = states[0].observation
        step = int(_get(observation, "step", -1))
        if step not in wanted:
            continue
        farms = observation.farms
        opponent_seat = 1 - candidate_seat
        candidate_farm = farms[candidate_seat]
        opponent_farm = farms[opponent_seat]
        candidate_bank = float(_get(candidate_farm, "money", 0.0) or 0.0)
        opponent_bank = float(_get(opponent_farm, "money", 0.0) or 0.0)
        rows[str(step)] = {
            "step": step,
            "candidate_bank": candidate_bank,
            "trace_bank": opponent_bank,
            "margin": candidate_bank - opponent_bank,
            "candidate_public_farm": _public_farm_counts(candidate_farm),
            "trace_public_farm": _public_farm_counts(opponent_farm),
            "trace_capital_lead": opponent_bank - candidate_bank,
            "feature_scope": "online_safe",
        }
    missing = wanted - {int(step) for step in rows}
    if missing:
        raise ValueError(f"simulation omitted checkpoints {sorted(missing)}")
    return rows


def _ledger_summary(
    events: list[dict[str, Any]],
    *,
    actor_seat: int,
    products: set[str],
    windows: list[tuple[int, int]],
    shop_interval: int = 4,
) -> dict[str, Any]:
    selected = [
        event
        for event in events
        if event["runtime_seat"] == actor_seat and event["product"] in products
    ]

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        units = len(items)
        revenue = sum(event["revenue"] for event in items)
        return {
            "executed_units": units,
            "realized_revenue": revenue,
            "weighted_mean_price": revenue / units if units else 0.0,
            "floor_units": sum(event["price"] <= 1.0 for event in items),
            "post_shop_demand_units": sum(event["shop_phase"] == 1 for event in items),
        }

    by_product = {
        product: aggregate([event for event in selected if event["product"] == product])
        for product in sorted(products)
    }
    by_phase = {
        str(phase): aggregate([event for event in selected if event["phase"] == phase])
        for phase in range(shop_interval)
    }
    by_window = {
        f"{start}:{end}": aggregate(
            [event for event in selected if start <= event["step"] < end]
        )
        for start, end in windows
    }
    return {
        **aggregate(selected),
        "by_product": by_product,
        "by_phase": by_phase,
        "by_window": by_window,
        "shop_phase_modulus": shop_interval,
        "feature_scope": "diagnostic_event_time_not_policy_observable",
    }


def _run_policy_against_trace(
    policy_path: Path,
    replay: dict[str, Any],
    recorded_seat: int,
    candidate_seat: int,
    checkpoints: list[int],
    windows: list[tuple[int, int]],
    products: set[str],
) -> dict[str, Any]:
    policy, _ = _load_candidate(str(policy_path))
    trace_policy = RecordedActionPolicy(replay, recorded_seat)
    agents = [trace_policy, trace_policy]
    agents[candidate_seat] = policy
    configuration, seed = _replay_configuration(replay)
    turns_per_day = max(1, int(configuration.get("turnsPerDay", 24) or 24))
    shop_interval = max(
        1, int(configuration.get("townShopSellInterval", 4) or 4)
    )
    center_interval = max(
        1, int(configuration.get("townCenterSellInterval", 12) or 12)
    )
    env = make("kaggriculture", configuration=configuration, debug=True)
    with _capture_market_ledger() as events:
        env.run(agents)
    final = env.steps[-1]
    rewards = [float(state.reward or 0.0) for state in final]
    statuses = [str(state.status) for state in final]
    opponent_seat = 1 - candidate_seat
    return {
        "source_seed": seed,
        "candidate_seat": candidate_seat,
        "timing_configuration": {
            "turns_per_day": turns_per_day,
            "town_shop_sell_interval": shop_interval,
            "town_center_sell_interval": center_interval,
            "source": "replay configuration with engine defaults when omitted",
        },
        "statuses": statuses,
        "invalid_episode": len(statuses) != 2 or any(status != "DONE" for status in statuses),
        "candidate_bank": rewards[candidate_seat],
        "trace_bank": rewards[opponent_seat],
        "margin": rewards[candidate_seat] - rewards[opponent_seat],
        "checkpoints": _checkpoint_rows(env, candidate_seat, checkpoints),
        "candidate_market": _ledger_summary(
            events,
            actor_seat=candidate_seat,
            products=products,
            windows=windows,
            shop_interval=shop_interval,
        ),
        "trace_market": _ledger_summary(
            events,
            actor_seat=opponent_seat,
            products=products,
            windows=windows,
            shop_interval=shop_interval,
        ),
    }


def _stratum(baseline_margin: float, candidate_margin: float) -> str:
    if candidate_margin == baseline_margin:
        return "unchanged"
    if baseline_margin < 0 < candidate_margin:
        return "rescued"
    if baseline_margin < 0 and candidate_margin == 0:
        return "loss_to_tie_improved"
    if baseline_margin > 0 > candidate_margin:
        return "harmed_to_loss"
    if baseline_margin == 0 and candidate_margin < 0:
        return "tie_to_loss_regressed"
    if baseline_margin == 0 and candidate_margin > 0:
        return "tie_to_win_improved"
    if baseline_margin > 0 and candidate_margin == 0:
        return "win_to_tie_regressed"
    if baseline_margin < 0 and candidate_margin < 0:
        return "still_loss_improved" if candidate_margin > baseline_margin else "still_loss_regressed"
    if baseline_margin > 0 and candidate_margin > 0:
        return "improved_win" if candidate_margin > baseline_margin else "regressed_but_still_win"
    raise ValueError(
        f"unclassified outcome transition {baseline_margin} -> {candidate_margin}"
    )


def _comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    checkpoints: list[int],
    windows: list[tuple[int, int]],
    products: set[str],
) -> dict[str, Any]:
    margin_delta = candidate["margin"] - baseline["margin"]
    own_bank_delta = candidate["candidate_bank"] - baseline["candidate_bank"]
    trace_bank_delta = candidate["trace_bank"] - baseline["trace_bank"]
    checkpoint_deltas = {
        str(step): candidate["checkpoints"][str(step)]["margin"]
        - baseline["checkpoints"][str(step)]["margin"]
        for step in checkpoints
    }
    window_deltas = {
        f"{start}:{end}": (
            checkpoint_deltas[str(end)] - checkpoint_deltas[str(start)]
        )
        for start, end in windows
    }
    product_deltas = {}
    for product in sorted(products):
        own_candidate = candidate["candidate_market"]["by_product"][product]
        own_baseline = baseline["candidate_market"]["by_product"][product]
        trace_candidate = candidate["trace_market"]["by_product"][product]
        trace_baseline = baseline["trace_market"]["by_product"][product]
        product_deltas[product] = {
            "own_executed_units": own_candidate["executed_units"] - own_baseline["executed_units"],
            "own_realized_revenue": own_candidate["realized_revenue"] - own_baseline["realized_revenue"],
            "trace_executed_units": trace_candidate["executed_units"] - trace_baseline["executed_units"],
            "trace_realized_revenue": trace_candidate["realized_revenue"] - trace_baseline["realized_revenue"],
        }
    ordered_checkpoint_deltas = [
        (step, checkpoint_deltas[str(step)]) for step in checkpoints
    ]
    first_permanent_negative = next(
        (
            step
            for index, (step, delta) in enumerate(ordered_checkpoint_deltas)
            if delta < 0
            and all(later_delta < 0 for _, later_delta in ordered_checkpoint_deltas[index:])
        ),
        None,
    )
    worst_window = min(window_deltas, key=window_deltas.get) if window_deltas else None
    denial_contribution = -trace_bank_delta
    return {
        "runtime_seat": candidate["candidate_seat"],
        "invalid_comparison": baseline["invalid_episode"] or candidate["invalid_episode"],
        "baseline_margin": baseline["margin"],
        "candidate_margin": candidate["margin"],
        "margin_delta": margin_delta,
        "own_bank_delta": own_bank_delta,
        "trace_bank_delta": trace_bank_delta,
        "own_bank_contribution": own_bank_delta,
        "denial_contribution": denial_contribution,
        "denial_share": (
            denial_contribution / margin_delta if margin_delta > 0 else None
        ),
        "bank_decomposition_residual": margin_delta
        - (own_bank_delta - trace_bank_delta),
        "stratum": _stratum(baseline["margin"], candidate["margin"]),
        "checkpoint_margin_deltas": checkpoint_deltas,
        "window_incremental_margin_deltas": window_deltas,
        "first_permanent_negative_delta_checkpoint": first_permanent_negative,
        "worst_incremental_window": worst_window,
        "product_execution_deltas": product_deltas,
        "feature_scope": {
            "checkpoint_margin_deltas": "retrospective_counterfactual",
            "window_incremental_margin_deltas": "retrospective_causal",
            "stratum": "retrospective_outcome",
        },
    }


def _summary(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in comparisons if not row["invalid_comparison"]]
    strata: dict[str, list[dict[str, Any]]] = {}
    for row in valid:
        strata.setdefault(row["stratum"], []).append(row)
    return {
        "comparisons": len(comparisons),
        "valid_comparisons": len(valid),
        "invalid_comparisons": len(comparisons) - len(valid),
        "mean_margin_delta": statistics.mean(row["margin_delta"] for row in valid) if valid else 0.0,
        "median_margin_delta": statistics.median(row["margin_delta"] for row in valid) if valid else 0.0,
        "strata": {
            name: {
                "count": len(rows),
                "mean_margin_delta": statistics.mean(row["margin_delta"] for row in rows),
                "median_margin_delta": statistics.median(row["margin_delta"] for row in rows),
                "minimum_margin_delta": min(row["margin_delta"] for row in rows),
                "seat_0": sum(row["runtime_seat"] == 0 for row in rows),
                "seat_1": sum(row["runtime_seat"] == 1 for row in rows),
            }
            for name, rows in sorted(strata.items())
        },
    }


def _comparison_manifest_map(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = (comparison.get("corpus_manifest") or {}).get("entries") or []
    return {
        str(entry.get("composite_key") or entry.get("key")): entry
        for entry in entries
    }


def build_report(
    *,
    comparison_path: Path,
    candidate: Path,
    baseline: Path,
    replay_paths: list[Path],
    checkpoints: list[int],
    windows: list[tuple[int, int]],
    products: set[str],
    opponent_seat: int | None = None,
    recorded_team: str | None = None,
    exclude_team: str | None = None,
) -> dict[str, Any]:
    comparison_path = comparison_path.expanduser().resolve()
    candidate, baseline, replay_paths, _, _ = validate_path_roles(
        candidate=candidate,
        baseline=baseline,
        replay_paths=replay_paths,
    )
    for path in (comparison_path, candidate, baseline, *replay_paths):
        if not path.is_file():
            raise FileNotFoundError(path)
    if comparison_path in {candidate, baseline, *replay_paths}:
        raise ValueError("comparison report collides with an agent or replay input")
    if not products:
        raise ValueError("at least one product is required")
    required_checkpoints = {value for window in windows for value in window}
    if not required_checkpoints.issubset(checkpoints):
        raise ValueError("every window boundary must also be a checkpoint")

    comparison_identity = _file_identity(comparison_path)
    candidate_identity = _file_identity(candidate)
    baseline_identity = _file_identity(baseline)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    engine_version = importlib.metadata.version("kaggle-environments")
    if comparison.get("schema_version") != SUPPORTED_COMPARISON_SCHEMA_VERSION:
        raise ValueError(
            "comparison report has unsupported schema_version "
            f"{comparison.get('schema_version')!r}; expected "
            f"{SUPPORTED_COMPARISON_SCHEMA_VERSION}"
        )
    if comparison.get("engine_version") != engine_version:
        raise ValueError("comparison report engine does not match installed engine")
    if comparison.get("candidate", {}).get("sha256") != candidate_identity["sha256"]:
        raise ValueError("candidate digest does not match comparison report")
    if comparison.get("baseline", {}).get("sha256") != baseline_identity["sha256"]:
        raise ValueError("baseline digest does not match comparison report")
    frozen_manifest = comparison.get("corpus_manifest") or {}
    if (
        frozen_manifest.get("schema_version")
        != SUPPORTED_CORPUS_MANIFEST_SCHEMA_VERSION
    ):
        raise ValueError(
            "comparison corpus manifest has unsupported schema_version "
            f"{frozen_manifest.get('schema_version')!r}; expected "
            f"{SUPPORTED_CORPUS_MANIFEST_SCHEMA_VERSION}"
        )
    claimed_manifest_sha256 = frozen_manifest.get("manifest_sha256")
    if not isinstance(claimed_manifest_sha256, str) or len(claimed_manifest_sha256) != 64:
        raise ValueError("comparison corpus manifest requires a SHA-256 self-digest")
    calculated_manifest_sha256 = _sha256_json(
        {
            key: value
            for key, value in frozen_manifest.items()
            if key != "manifest_sha256"
        }
    )
    if claimed_manifest_sha256 != calculated_manifest_sha256:
        raise ValueError("comparison corpus manifest self-digest is invalid")
    expected_manifest = _comparison_manifest_map(comparison)
    expected_trace_keys = {str(trace["corpus_key"]) for trace in comparison.get("traces", [])}

    prepared = []
    entries = []
    seen_keys = set()
    for replay_path in sorted(replay_paths, key=str):
        replay = load_replay(replay_path)
        seat = resolve_corpus_seat(
            replay,
            opponent_seat=opponent_seat,
            recorded_team=recorded_team,
            exclude_team=exclude_team,
        )
        episode_id = int((replay.get("info") or {})["EpisodeId"])
        key = f"{episode_id}:{seat}"
        if key in seen_keys:
            raise ValueError(f"duplicate corpus key {key}")
        seen_keys.add(key)
        if key not in expected_trace_keys or key not in expected_manifest:
            raise ValueError(f"replay {key} is absent from the frozen comparison corpus")
        content = replay_path.read_bytes()
        identity = {
            "composite_key": key,
            "source_episode_id": episode_id,
            "recorded_seat": seat,
            "replay_path": str(replay_path),
            "replay_sha256": hashlib.sha256(content).hexdigest(),
            "replay_size_bytes": len(content),
            "configuration_sha256": _sha256_json(replay.get("configuration", {}) or {}),
            "action_trace_sha256": _sha256_json(_replay_action_trace(replay, seat)),
        }
        expected = expected_manifest[key]
        for field in ("replay_sha256", "replay_size_bytes", "configuration_sha256", "action_trace_sha256"):
            if expected.get(field) != identity[field]:
                raise ValueError(f"replay {key} changed field {field}")
        entries.append(identity)
        prepared.append((replay_path, replay, seat, identity))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "engine_version": engine_version,
        "comparison": comparison_identity,
        "candidate": candidate_identity,
        "baseline": baseline_identity,
        "entries": sorted(entries, key=lambda entry: entry["composite_key"]),
        "frozen_corpus_trace_count": len(expected_trace_keys),
        "selected_trace_count": len(seen_keys),
        "selected_corpus_keys_sha256": _sha256_json(sorted(seen_keys)),
    }
    manifest["manifest_sha256"] = _sha256_json(manifest)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_version": engine_version,
        "method": "engine-committed replay-trace market and checkpoint attribution",
        "settings": {
            "checkpoints": checkpoints,
            "windows": [f"{start}:{end}" for start, end in windows],
            "products": sorted(products),
            "timing_semantics": (
                "day and demand phases are derived per replay from turnsPerDay, "
                "townShopSellInterval, and townCenterSellInterval; engine defaults "
                "24/4/12 apply only when a field is omitted"
            ),
        },
        "feature_labels": {
            "per_policy_checkpoint_public_state": "online_safe",
            "checkpoint_candidate_minus_baseline_delta": "retrospective_counterfactual",
            "executed_market_events": "diagnostic_event_time_not_policy_observable",
            "window_effect": "retrospective_causal",
            "outcome_stratum": "retrospective_outcome",
            "final_public_footprint": "retrospective_do_not_gate",
        },
        "input_manifest": manifest,
        "traces": [],
    }
    all_comparisons = []
    for replay_path, replay, seat, identity in prepared:
        trace_row: dict[str, Any] = {
            "corpus_key": identity["composite_key"],
            "source_episode_id": identity["source_episode_id"],
            "recorded_seat": seat,
            "final_recorded_public_footprint": recorded_public_footprint(replay, seat),
            "final_footprint_scope": "retrospective_do_not_gate",
            "comparisons": [],
        }
        report["traces"].append(trace_row)
        for runtime_seat in (0, 1):
            baseline_run = _run_policy_against_trace(
                baseline, replay, seat, runtime_seat, checkpoints, windows, products
            )
            candidate_run = _run_policy_against_trace(
                candidate, replay, seat, runtime_seat, checkpoints, windows, products
            )
            row = _comparison(
                baseline_run, candidate_run, checkpoints, windows, products
            )
            row["baseline"] = baseline_run
            row["candidate"] = candidate_run
            trace_row["comparisons"].append(row)
            all_comparisons.append(row)
            _validate_replay_identity(identity)
            _validate_identity(candidate_identity, "candidate")
            _validate_identity(baseline_identity, "baseline")
            _validate_identity(comparison_identity, "comparison report")
    report["summary"] = _summary(all_comparisons)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Replay loss attribution",
        "",
        f"Generated: {report['generated_at']}",
        f"Engine: `kaggle-environments=={report['engine_version']}`  ",
        f"Input manifest: `{report['input_manifest']['manifest_sha256']}`",
        "",
        "## Summary",
        "",
        f"- Valid/invalid comparisons: {summary['valid_comparisons']} / {summary['invalid_comparisons']}",
        f"- Mean/median margin delta: {summary['mean_margin_delta']:+,.1f} / {summary['median_margin_delta']:+,.1f}",
        "",
        "| Stratum | Count | Mean delta | Median | Minimum | Seat 0/1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in summary["strata"].items():
        lines.append(
            f"| {name} | {row['count']} | {row['mean_margin_delta']:+,.1f} | "
            f"{row['median_margin_delta']:+,.1f} | {row['minimum_margin_delta']:+,.1f} | "
            f"{row['seat_0']}/{row['seat_1']} |"
        )
    lines.extend(
        [
            "",
            "Each policy's checkpoint public state is online-safe. Candidate-minus-baseline",
            "checkpoint deltas are retrospective counterfactuals. Engine-committed market events are exact",
            "diagnostics but are not directly policy-observable. Window effects and outcome strata are retrospective; final",
            "farm footprints are explicitly diagnostic-only and must not become policy gates.",
            "",
            "Recorded opponents remain open-loop after divergence, so attribution is causal for",
            "this frozen schedule rather than an estimate of live adaptive win probability.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--replays-dir", type=Path, required=True)
    parser.add_argument("--pattern", default="episode-*-replay.json")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--opponent-seat", type=int)
    selector.add_argument("--recorded-team")
    selector.add_argument("--exclude-team")
    parser.add_argument("--checkpoints", default="289,433,577,719")
    parser.add_argument("--windows", default="289:433,433:577,577:719")
    parser.add_argument("--products", default="MILK,WOOL,STRAWBERRY,MELON")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    try:
        checkpoints = _parse_int_list(args.checkpoints)
        windows = _parse_windows(args.windows)
        products = {item.strip().upper() for item in args.products.split(",") if item.strip()}
        replay_paths = sorted(
            path.resolve()
            for path in args.replays_dir.expanduser().resolve().glob(args.pattern)
            if path.is_file()
        )
        if not replay_paths:
            raise FileNotFoundError("no replay files matched the corpus pattern")
        candidate, baseline, replay_paths, output, markdown = validate_path_roles(
            candidate=args.candidate,
            baseline=args.baseline,
            replay_paths=replay_paths,
            output=args.output,
            markdown=args.markdown,
        )
        comparison = args.comparison.expanduser().resolve()
        assert output is not None and markdown is not None
        if comparison in {candidate, baseline, output, markdown, *replay_paths}:
            raise ValueError("comparison report collides with another path role")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    report = build_report(
        comparison_path=comparison,
        candidate=candidate,
        baseline=baseline,
        replay_paths=replay_paths,
        checkpoints=checkpoints,
        windows=windows,
        products=products,
        opponent_seat=args.opponent_seat,
        recorded_team=args.recorded_team,
        exclude_team=args.exclude_team,
    )
    rendered = render_markdown(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(rendered, encoding="utf-8")
    print(rendered)
    print(f"\nJSON: {output}")
    print(f"Markdown: {markdown}")
    if report["summary"]["invalid_comparisons"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
