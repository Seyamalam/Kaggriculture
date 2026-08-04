"""Paired-seat ablation of the candidate-v3 sheep count.

The candidate is imported once, then evaluated with prefixes of its fixed
``SHEEP_TILES`` layout.  A temporary market wrapper caps purchases to the
active prefix; without that cap the original four-sheep schedule would buy
animals for pasture slots intentionally removed by the ablation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Iterator

try:
    from scripts.tournament import run_paired_tournament
except ModuleNotFoundError:  # Direct ``python scripts/sheep_ablation.py`` execution.
    from tournament import run_paired_tournament


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COUNTS = (1, 2, 3, 4)
Agent = Callable[[dict[str, Any]], dict[str, Any]]


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sheep_in_system(obs: dict[str, Any]) -> int:
    player = int(obs["player"])
    farm = obs["farms"][player]
    private = obs["private"]
    placed = sum(
        1
        for row in farm["tiles"]
        for tile in row
        if isinstance(tile, dict) and tile.get("animal") == "SHEEP"
    )
    shed = int(private.get("shed", {}).get("SHEEP", 0))
    carried = sum(
        int(inventory.get("SHEEP", 0))
        for inventory in private.get("inventories", [])
    )
    return placed + shed + carried


@contextmanager
def sheep_count(candidate: Any, count: int) -> Iterator[Agent]:
    """Temporarily bound candidate pasture slots and sheep purchases."""
    original_tiles = tuple(candidate.SHEEP_TILES)
    original_market = candidate._market_actions
    if not 1 <= count <= len(original_tiles):
        raise ValueError(f"count must be between 1 and {len(original_tiles)}")

    def bounded_market(obs: dict[str, Any]) -> list[list[Any]]:
        orders = original_market(obs)
        owned = _sheep_in_system(obs)
        bounded: list[list[Any]] = []
        for order in orders:
            if not (isinstance(order, list) and order[:2] == ["BUY_ANIMAL", "SHEEP"]):
                bounded.append(order)
                continue
            requested = int(order[2]) if len(order) >= 3 else 0
            allowed = min(requested, max(0, count - owned))
            if allowed > 0:
                bounded.append(["BUY_ANIMAL", "SHEEP", allowed])
                owned += allowed
        return bounded

    candidate.SHEEP_TILES = original_tiles[:count]
    candidate._market_actions = bounded_market
    try:
        yield candidate.agent
    finally:
        candidate.SHEEP_TILES = original_tiles
        candidate._market_actions = original_market


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in ("episodes", "pairs")
    }


def run_ablation(*, pairs: int, seed: int, counts: tuple[int, ...] = DEFAULT_COUNTS) -> dict[str, Any]:
    candidate = _load_module(ROOT / "agents" / "candidate_v3_sheep.py", "candidate_v3_sheep_ablation")
    opponent = _load_module(ROOT / "main.py", "main_v1_ablation")
    original_tiles = tuple(candidate.SHEEP_TILES)
    original_market = candidate._market_actions
    results: dict[str, Any] = {}

    if not counts or any(count not in DEFAULT_COUNTS for count in counts):
        raise ValueError(f"counts must be a non-empty subset of {DEFAULT_COUNTS}")
    for count in counts:
        with sheep_count(candidate, count) as policy:
            report = run_paired_tournament(policy, opponent.agent, pairs=pairs, seed=seed)
        if tuple(candidate.SHEEP_TILES) != original_tiles or candidate._market_actions is not original_market:
            raise RuntimeError("candidate globals were not restored after ablation arm")
        results[str(count)] = _summary(report)

    ranked = sorted(
        counts,
        key=lambda count: (
            float(results[str(count)]["mean_paired_margin"]),
            int(results[str(count)]["paired_wins"]),
            -count,
        ),
        reverse=True,
    )
    best = ranked[0]
    return {
        "candidate": "agents/candidate_v3_sheep.py",
        "opponent": "main.py",
        "seed_pairs_per_count": pairs,
        "base_seed": seed,
        "counts": list(counts),
        "results": results,
        "recommendation": {
            "sheep_count": best,
            "criterion": "highest mean paired margin; paired wins then lower count break ties",
            "mean_paired_margin": results[str(best)]["mean_paired_margin"],
            "paired_wins": results[str(best)]["paired_wins"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--counts", type=int, nargs="+", default=list(DEFAULT_COUNTS))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.pairs <= 0:
        parser.error("--pairs must be positive")
    report = run_ablation(pairs=args.pairs, seed=args.seed, counts=tuple(dict.fromkeys(args.counts)))
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
