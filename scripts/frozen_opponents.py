"""Deterministic, versioned local opponents for paired candidate evaluation.

These policies deliberately use no module-level episode state.  Calling either
agent with the same observation always returns the same action, which makes
them useful regression targets across processes and seat swaps.
"""

from __future__ import annotations

from typing import Any


CROP_DATA = {
    "WHEAT": {"seed": 10, "harvest_day": 4},
    "CARROT": {"seed": 20, "harvest_day": 3},
    "TOMATO": {"seed": 50, "harvest_day": 8},
}
PRODUCTS = ("WOOL", "MILK", "EGG", "TOMATO", "CARROT", "WHEAT")
SHED_CAPACITY = 100


def _distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def _step_toward(position: tuple[int, int], target: tuple[int, int]) -> list[str]:
    x, y = position
    tx, ty = target
    dx, dy = tx - x, ty - y
    if abs(dx) >= abs(dy) and dx:
        return ["EAST" if dx > 0 else "WEST"]
    if dy:
        return ["SOUTH" if dy > 0 else "NORTH"]
    return ["PASS"]


def _shed_access(farm: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    half = len(farm["tiles"]) // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _assign_tasks(
    obs: dict[str, Any],
    tasks: list[tuple[int, int, int, list[Any]]],
) -> tuple[list[Any], list[list[Any]]]:
    """Greedily match unique tasks to units with deterministic tie breaks."""
    player = int(obs["player"])
    farm = obs["farms"][player]
    positions = [tuple(farm["farmer"]), *(tuple(pos) for pos in farm.get("hands", []))]
    inventories = obs.get("private", {}).get("inventories", [])
    access = _shed_access(farm)
    assignments: dict[int, tuple[tuple[int, int], list[Any]]] = {}
    available = set(range(len(positions)))

    # Inventory routing comes before farm work.  Production goes home, while
    # purchased geese and feed move from the shed to their destinations.
    animal_tiles: list[tuple[int, int, dict[str, Any]]] = []
    empty_coops: list[tuple[int, int]] = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal"):
                animal_tiles.append((x, y, tile))
            elif isinstance(tile, dict) and tile.get("kind") == "COOP":
                empty_coops.append((x, y))

    reserved_coops: set[tuple[int, int]] = set()
    for unit in sorted(list(available)):
        inventory = inventories[unit] if unit < len(inventories) else {}
        position = positions[unit]
        goose_count = int(inventory.get("GOOSE", 0))
        wheat_count = int(inventory.get("WHEAT", 0))
        carried_product = sum(int(inventory.get(item, 0)) for item in PRODUCTS)
        if goose_count and empty_coops:
            candidates = [tile for tile in empty_coops if tile not in reserved_coops]
            if candidates:
                target = min(candidates, key=lambda tile: (_distance(position, tile), tile))
                reserved_coops.add(target)
                action = ["PLACE", "GOOSE"] if position == target else _step_toward(position, target)
                assignments[unit] = (target, action)
                available.remove(unit)
                continue
        if wheat_count:
            hungry = [
                (x, y)
                for x, y, tile in animal_tiles
                if not bool(tile.get("fed_today", False))
            ]
            if hungry:
                target = min(hungry, key=lambda tile: (_distance(position, tile), tile))
                action = ["FEED"] if position == target else _step_toward(position, target)
                assignments[unit] = (target, action)
                available.remove(unit)
                continue
        if carried_product:
            target = min(access, key=lambda tile: (_distance(position, tile), tile))
            action = ["DROP"] if position == target else _step_toward(position, target)
            assignments[unit] = (target, action)
            available.remove(unit)

    pending = list(tasks)
    while pending and available:
        _, unit, task_index = min(
            (
                (priority, _distance(positions[unit], (x, y)), unit, x, y),
                unit,
                index,
            )
            for index, (priority, x, y, _action) in enumerate(pending)
            for unit in available
        )
        priority, x, y, operation = pending.pop(task_index)
        del priority
        position = positions[unit]
        assignments[unit] = ((x, y), operation if position == (x, y) else _step_toward(position, (x, y)))
        available.remove(unit)

    actions = [assignments.get(index, (position, ["PASS"]))[1] for index, position in enumerate(positions)]
    return actions[0], actions[1:]


def _crop_tasks(
    obs: dict[str, Any],
    crop_for_tile,
    reserved: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int, int, list[Any]]]:
    player = int(obs["player"])
    farm = obs["farms"][player]
    seeds = {name: int(obs["private"].get("seeds", {}).get(name, 0)) for name in CROP_DATA}
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    tasks: list[tuple[int, int, int, list[Any]]] = []
    empty: list[tuple[int, int]] = []
    reserved = reserved or set()

    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if (x, y) in reserved:
                continue
            if tile is None:
                empty.append((x, y))
            elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                tasks.append((2, x, y, ["DIG"]))
            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crop = str(tile.get("crop"))
                age = day - int(tile.get("planted_day", day))
                ready = int(tile.get("yield_units", 0)) > 0 and age >= CROP_DATA.get(crop, {}).get("harvest_day", 99)
                if not bool(tile.get("watered_today", False)) and day < 29:
                    priority = -1 if int(tile.get("consecutive_unwatered", 0)) else 0
                    tasks.append((priority, x, y, ["WATER"]))
                elif ready and (day < 29 or hour < 15):
                    tasks.append((1, x, y, ["HARVEST"]))

    if hour >= 15 or day >= 25:
        return tasks
    for x, y in empty:
        crop = crop_for_tile(x, y)
        if seeds.get(crop, 0) <= 0:
            continue
        tasks.append((4, x, y, ["PLANT", crop]))
        seeds[crop] -= 1
    return tasks


def _market_sales(obs: dict[str, Any]) -> list[list[Any]]:
    shed = obs["private"].get("shed", {})
    prices = obs["market"].get("prices", {})
    orders: list[list[Any]] = []
    for item in sorted(PRODUCTS, key=lambda name: (-int(prices.get(name, 0)), name)):
        count = int(shed.get(item, 0))
        if count:
            orders.append(["SELL", item, count])
    return orders


def _hire_orders(obs: dict[str, Any], target: int) -> list[list[str]]:
    farm = obs["farms"][int(obs["player"])]
    if int(obs.get("hour", 0)) > 1:
        return []
    missing = max(0, target - len(farm.get("hands", [])))
    return [["HIRE"] for _ in range(missing)]


def crop_specialist(obs: dict[str, Any]) -> dict[str, Any]:
    """A stable 25-tile carrot rotation that is stronger than ``starter``."""
    player = int(obs["player"])
    farm = obs["farms"][player]
    private = obs["private"]
    day = int(obs.get("day", 0))
    active = sum(
        1
        for row in farm["tiles"]
        for tile in row
        if isinstance(tile, dict) and tile.get("kind") == "PLANT"
    )
    seeds = int(private.get("seeds", {}).get("CARROT", 0))
    market = _market_sales(obs) + _hire_orders(obs, 9)
    if day < 24 and len(market) < 10:
        gap = max(0, 25 - active - seeds)
        affordable = max(0, (int(farm["money"]) - 250) // CROP_DATA["CARROT"]["seed"])
        count = min(8, gap, affordable)
        if count:
            market.append(["BUY_SEED", "CARROT", count])
    tasks = _crop_tasks(obs, lambda _x, _y: "CARROT")
    farmer, hands = _assign_tasks(obs, tasks)
    return {"farmer": farmer, "hands": hands, "market": market[:10]}


def diversified_baseline(obs: dict[str, Any]) -> dict[str, Any]:
    """A fixed crop mix plus three cared-for geese and daily feed logistics."""
    player = int(obs["player"])
    farm = obs["farms"][player]
    private = obs["private"]
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    coop_targets = {(3, 3), (3, 4), (4, 3)}
    tasks: list[tuple[int, int, int, list[Any]]] = []
    occupied_geese = 0
    empty_coops = 0
    hungry = 0
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if (x, y) in coop_targets and tile is None:
                tasks.append((-3, x, y, ["BUILD_COOP"]))
            elif isinstance(tile, dict) and tile.get("kind") == "COOP":
                if tile.get("animal") == "GOOSE":
                    occupied_geese += 1
                    if not bool(tile.get("fed_today", False)):
                        hungry += 1
                        tasks.append((-2, x, y, ["FEED"]))
                    elif int(tile.get("yield_units", 0)) > 0:
                        tasks.append((-1, x, y, ["HARVEST"]))
                    elif not bool(tile.get("cared_today", False)):
                        tasks.append((1, x, y, ["CARE"]))
                else:
                    empty_coops += 1

    shed = private.get("shed", {})
    inventories = private.get("inventories", [])
    carried_geese = sum(int(inv.get("GOOSE", 0)) for inv in inventories)
    carried_wheat = sum(int(inv.get("WHEAT", 0)) for inv in inventories)
    access = set(_shed_access(farm))
    positions = [tuple(farm["farmer"]), *(tuple(pos) for pos in farm.get("hands", []))]
    if empty_coops and int(shed.get("GOOSE", 0)) > 0 and not carried_geese:
        for x, y in sorted(access):
            if (x, y) in positions:
                tasks.append((-4, x, y, ["PICKUP", "GOOSE", 1]))
                break
    if hungry and int(shed.get("WHEAT", 0)) > 0 and not carried_wheat:
        for x, y in sorted(access):
            if (x, y) in positions:
                tasks.append((-4, x, y, ["PICKUP", "WHEAT", hungry]))
                break

    def crop_for_tile(x: int, y: int) -> str:
        return "TOMATO" if (x + 2 * y) % 5 == 0 else "CARROT"

    tasks.extend(_crop_tasks(obs, crop_for_tile, coop_targets))
    market = _market_sales(obs) + _hire_orders(obs, 10)
    owned_geese = occupied_geese + empty_coops + int(shed.get("GOOSE", 0)) + carried_geese
    if day == 0 and owned_geese < 3 and len(market) < 10:
        market.append(["BUY_ANIMAL", "GOOSE", 3 - owned_geese])
    wheat_available = int(shed.get("WHEAT", 0)) + carried_wheat
    if occupied_geese and wheat_available < occupied_geese and hour <= 1 and len(market) < 10:
        market.append(["BUY_PRODUCT", "WHEAT", occupied_geese - wheat_available])

    if day < 23 and len(market) < 10:
        active_by_crop = {crop: 0 for crop in CROP_DATA}
        for row in farm["tiles"]:
            for tile in row:
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    crop = tile.get("crop")
                    if crop in active_by_crop:
                        active_by_crop[crop] += 1
        seed_stock = private.get("seeds", {})
        targets = {"CARROT": 18, "TOMATO": 4}
        for crop in ("CARROT", "TOMATO"):
            gap = max(0, targets[crop] - active_by_crop[crop] - int(seed_stock.get(crop, 0)))
            reserve = 500
            affordable = max(0, (int(farm["money"]) - reserve) // CROP_DATA[crop]["seed"])
            count = min(6, gap, affordable)
            if count and len(market) < 10:
                market.append(["BUY_SEED", crop, count])

    farmer, hands = _assign_tasks(obs, tasks)
    return {"farmer": farmer, "hands": hands, "market": market[:10]}


FROZEN_OPPONENTS = {
    "crop-specialist": crop_specialist,
    "diversified-baseline": diversified_baseline,
}

