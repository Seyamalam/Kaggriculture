"""Kaggriculture candidate v2.

Self-contained deterministic policy.  Compared with v1 it limits seed stock to
near-term planting throughput, can unlock the full farm, and runs a small mixed
livestock operation whose fertilizer is routed to crops where it adds yield.
"""

from __future__ import annotations

import math
from typing import Any


CROPS = {
    "WHEAT": {"seed": 10, "first": 2, "finish": 4, "yield": 6, "base": 25, "ongoing": False},
    "CARROT": {"seed": 20, "first": 2, "finish": 3, "yield": 4, "base": 35, "ongoing": False},
    "TOMATO": {"seed": 50, "first": 8, "finish": 11, "yield": 4, "base": 60, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "finish": 16, "yield": 4, "base": 120, "ongoing": True},
    "MELON": {"seed": 80, "first": 10, "finish": 12, "yield": 6, "base": 250, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP", "product": "EGG", "cutoff": 18},
    "COW": {"cost": 400, "structure": "PASTURE", "product": "MILK", "cutoff": 15},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL", "cutoff": 16},
}

MARKET_PARAMS = {
    "WHEAT": (10_000, 400, "sqrt", 0.80, "log", 0.20),
    "CARROT": (10_000, 450, "log", 0.20, "sqrt", 0.70),
    "TOMATO": (10_000, 200, "linear", 0.40, "sqrt", 0.60),
    "STRAWBERRY": (10_000, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON": (10_000, 300, "log", 0.20, "sq", 3.60),
}

SALE_PRODUCTS = ("MELON", "STRAWBERRY", "WOOL", "MILK", "TOMATO", "EGG", "CARROT", "WHEAT")
LAND_PRICES = (1_000, 2_000, 4_000)
FIB_HIRE_COSTS = (1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610)
SHED_CAPACITY = 100


def _shape(name: str, value: float) -> float:
    value = max(0.0, value)
    if name == "linear":
        return value
    if name == "sq":
        return value * value
    if name == "sqrt":
        return math.sqrt(value)
    if name == "log":
        return math.log1p(value)
    return value


def _market_price(crop: str, inventory: int) -> int:
    base = CROPS[crop]["base"]
    i0, throughput, below_fn, below_target, above_fn, above_target = MARKET_PARAMS[crop]
    if inventory < i0:
        fn, target, sign, distance = below_fn, below_target, 1, i0 - inventory
    else:
        fn, target, sign, distance = above_fn, above_target, -1, inventory - i0
    amplitude = target * base / _shape(fn, throughput)
    return max(1, round(base + sign * amplitude * _shape(fn, distance)))


def _tiles(farm: dict[str, Any], kind: str | None = None) -> list[tuple[int, int, dict[str, Any]]]:
    found: list[tuple[int, int, dict[str, Any]]] = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict):
                continue
            if kind is None or tile.get("kind") == kind:
                found.append((x, y, tile))
    return found


def _crop_counts(farm: dict[str, Any]) -> dict[str, int]:
    counts = {crop: 0 for crop in CROPS}
    for _, _, tile in _tiles(farm, "PLANT"):
        crop = tile.get("crop")
        if crop in counts:
            counts[crop] += 1
    return counts


def _animal_counts(farm: dict[str, Any]) -> dict[str, int]:
    counts = {animal: 0 for animal in ANIMALS}
    for _, _, tile in _tiles(farm):
        animal = tile.get("animal")
        if animal in counts:
            counts[animal] += 1
    return counts


def _private_item_count(private: dict[str, Any], item: str) -> int:
    return int(private.get("shed", {}).get(item, 0)) + sum(
        int(inv.get(item, 0)) for inv in private.get("inventories", [])
    )


def _animal_goals(day: int) -> dict[str, int]:
    # Stage capital-intensive livestock behind the first fast-crop cash cycle.
    # Mixed products reduce exposure to one market curve without overwhelming
    # the service crew during the opening.
    return {
        "GOOSE": 1 if day < 4 else (2 if day <= ANIMALS["GOOSE"]["cutoff"] else 0),
        "COW": 0 if day < 4 else (1 if day <= ANIMALS["COW"]["cutoff"] else 0),
        "SHEEP": 0 if day < 8 else (1 if day <= ANIMALS["SHEEP"]["cutoff"] else 0),
    }


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _shed_access(farm: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    half = len(farm["tiles"]) // 2
    return ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))


def _step_toward(position: tuple[int, int], target: tuple[int, int]) -> list[str]:
    x, y = position
    tx, ty = target
    dx, dy = tx - x, ty - y
    if abs(dx) >= abs(dy) and dx:
        return ["EAST" if dx > 0 else "WEST"]
    if dy:
        return ["SOUTH" if dy > 0 else "NORTH"]
    return ["PASS"]


def _crop_scores(obs: dict[str, Any]) -> dict[str, float]:
    player = int(obs["player"])
    farms = obs["farms"]
    market = obs["market"]
    own = _crop_counts(farms[player])
    other = _crop_counts(farms[1 - player]) if len(farms) == 2 else {crop: 0 for crop in CROPS}
    day = int(obs.get("day", 0))
    scores: dict[str, float] = {}
    for crop, info in CROPS.items():
        # Two days cover the last harvest, return trip, drop, and market sale.
        if day + int(info["finish"]) + 2 >= 30:
            scores[crop] = -1_000_000.0
            continue
        inventory = int(market["inventory"].get(crop, 10_000))
        visible_supply = (own[crop] + other[crop] + 4) * int(info["yield"])
        projected = _market_price(crop, inventory + visible_supply)
        current = int(market["prices"].get(crop, info["base"]))
        expected = 0.35 * current + 0.65 * projected
        profit = int(info["yield"]) * expected - int(info["seed"])
        scores[crop] = profit / int(info["finish"])
        # A farm that ties all opening cash up for ten days can no longer hire
        # or feed.  Prefer one fast cash cycle before expanding into premiums.
        money = float(farms[player].get("money", 0))
        if day < 7 and money < 2_500 and int(info["first"]) > 4:
            scores[crop] *= 0.25
    return scores


def _planned_builds(obs: dict[str, Any]) -> list[tuple[int, int, list[str]]]:
    farm = obs["farms"][obs["player"]]
    day = int(obs.get("day", 0))
    goals = _animal_goals(day)
    required = {
        "COOP": goals["GOOSE"],
        "PASTURE": goals["COW"] + goals["SHEEP"],
    }
    existing = {"COOP": 0, "PASTURE": 0}
    for _, _, tile in _tiles(farm):
        kind = tile.get("kind")
        if kind in existing:
            existing[kind] += 1

    access = _shed_access(farm)
    empty = [
        (x, y)
        for y, row in enumerate(farm["tiles"])
        for x, tile in enumerate(row)
        if tile is None
    ]
    empty.sort(key=lambda pos: (min(_distance(pos, shed) for shed in access), pos[1], pos[0]))
    builds: list[tuple[int, int, list[str]]] = []
    for kind in ("COOP", "PASTURE"):
        for _ in range(max(0, required[kind] - existing[kind])):
            if not empty:
                break
            x, y = empty.pop(0)
            builds.append((x, y, ["BUILD_" + kind]))
    return builds


def _fertilizer_targets(obs: dict[str, Any]) -> list[tuple[int, int]]:
    farm = obs["farms"][obs["player"]]
    day = int(obs.get("day", 0))
    targets: list[tuple[int, int, int]] = []
    priority = {"STRAWBERRY": 0, "TOMATO": 1, "WHEAT": 2, "CARROT": 3}
    for x, y, tile in _tiles(farm, "PLANT"):
        crop = tile.get("crop")
        if crop not in priority or int(tile.get("fertilized_until_day", -1)) >= day:
            continue
        age = day - int(tile.get("planted_day", day))
        if CROPS[crop]["ongoing"]:
            useful = age >= int(CROPS[crop]["first"]) - 2
        else:
            window = (int(CROPS[crop]["finish"]) + 1) // 2
            useful = window <= age <= int(CROPS[crop]["finish"])
        if useful:
            targets.append((priority[crop], x, y))
    return [(x, y) for _, x, y in sorted(targets)]


def _should_harvest(tile: dict[str, Any], obs: dict[str, Any]) -> bool:
    units = int(tile.get("yield_units", 0))
    if units <= 0:
        return False
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    step = int(obs.get("step", day * 24 + hour))
    if day >= 28:
        return hour < 13
    max_life = int(tile.get("max_lifespan_step", -1))
    if max_life >= 0 and max_life - step <= 4:
        return True
    if "animal" in tile:
        # Avoid the animal's held-yield cap; frequent small harvests are cheap.
        return units >= 2 or hour >= 15
    crop = tile.get("crop")
    age = day - int(tile.get("planted_day", day))
    if crop in ("WHEAT", "CARROT", "MELON"):
        return age >= int(CROPS[crop]["finish"]) or units >= int(CROPS[crop]["yield"])
    return units >= 3 or (day >= 27 and units > 0)


def _crop_tasks(obs: dict[str, Any], reserved: set[tuple[int, int]]) -> list[tuple[int, int, int, list[Any]]]:
    farm = obs["farms"][obs["player"]]
    private = obs["private"]
    tasks: list[tuple[int, int, int, list[Any]]] = []
    empty: list[tuple[int, int]] = []
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile is None:
                if (x, y) not in reserved:
                    empty.append((x, y))
                continue
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "WEED":
                tasks.append((3, x, y, ["DIG"]))
                continue
            if tile.get("kind") != "PLANT":
                continue
            ready = _should_harvest(tile, obs)
            if not tile.get("watered_today", False) and day < 29:
                urgent = int(tile.get("consecutive_unwatered", 0)) >= 1
                tasks.append((-1 if urgent else (0 if ready else 1), x, y, ["WATER"]))
            elif ready:
                tasks.append((0, x, y, ["HARVEST"]))

    if hour >= 14:
        return tasks
    scores = _crop_scores(obs)
    seeds = {crop: int(private.get("seeds", {}).get(crop, 0)) for crop in CROPS}
    ranked = sorted(CROPS, key=lambda crop: (-scores[crop], crop))
    for x, y in empty:
        crop = next((name for name in ranked if seeds[name] > 0 and scores[name] > 0), None)
        if crop is None:
            break
        tasks.append((5, x, y, ["PLANT", crop]))
        seeds[crop] -= 1
    return tasks


def _unit_actions(obs: dict[str, Any]) -> tuple[list[Any], list[list[Any]]]:
    farm = obs["farms"][obs["player"]]
    private = obs["private"]
    positions = [tuple(farm["farmer"]), *(tuple(pos) for pos in farm.get("hands", []))]
    inventories = list(private.get("inventories", []))
    while len(inventories) < len(positions):
        inventories.append({})
    remaining = set(range(len(positions)))
    assignments: dict[int, tuple[int, int, list[Any]]] = {}
    access = _shed_access(farm)

    def assign_carriers(item: str, targets: list[tuple[int, int]], operation: list[Any]) -> list[tuple[int, int]]:
        unfilled = list(targets)
        while unfilled:
            eligible = [i for i in remaining if int(inventories[i].get(item, 0)) > 0]
            if not eligible:
                break
            distance, index, target_index = min(
                (_distance(positions[i], target), i, j)
                for i in eligible
                for j, target in enumerate(unfilled)
            )
            del distance
            target = unfilled.pop(target_index)
            assignments[index] = (target[0], target[1], operation)
            remaining.remove(index)
        return unfilled

    # First finish multi-turn inventory workflows.  Animal placement precedes
    # feeding/fertilizing because an unused purchased animal has zero value.
    empty_structures = {"COOP": [], "PASTURE": []}
    animals_on_map: list[tuple[int, int, dict[str, Any]]] = []
    for x, y, tile in _tiles(farm):
        if tile.get("kind") in empty_structures and "animal" not in tile:
            empty_structures[tile["kind"]].append((x, y))
        if "animal" in tile:
            animals_on_map.append((x, y, tile))
    for animal in ("GOOSE", "COW", "SHEEP"):
        kind = ANIMALS[animal]["structure"]
        empty_structures[kind] = assign_carriers(animal, empty_structures[kind], ["PLACE", animal])

    unfed = [(x, y) for x, y, tile in animals_on_map if not tile.get("fed_today", False)]
    unfed = assign_carriers("WHEAT", unfed, ["FEED"])
    fertilizer_targets = assign_carriers("FERTILIZER", _fertilizer_targets(obs), ["FERTILIZE"])

    # Return sale inventory before the evening cutoff. Utility inventory is
    # retained while a matching task exists.
    hour = int(obs.get("hour", 0))
    day = int(obs.get("day", 0))
    shed_used = sum(int(value) for value in private.get("shed", {}).values())
    drop_room = max(0, SHED_CAPACITY - shed_used)
    for index in sorted(list(remaining)):
        inv = inventories[index]
        sale_load = sum(int(inv.get(item, 0)) for item in SALE_PRODUCTS)
        utility_load = sum(int(inv.get(item, 0)) for item in (*ANIMALS, "FERTILIZER"))
        liquidating = day >= 29 or (day >= 28 and hour >= 12)
        if sale_load <= 0 or (not liquidating and hour < 17 and sale_load < 20):
            continue
        position = positions[index]
        target = min(access, key=lambda pos: (_distance(position, pos), pos))
        if position == target:
            total = sum(int(value) for value in inv.values())
            action = ["DROP"] if total <= drop_room else ["PASS"]
            if action[0] == "DROP":
                drop_room -= total
        else:
            action = _step_toward(position, target)
        assignments[index] = (position[0], position[1], action)
        remaining.remove(index)
        del utility_load

    # Units at (or routed to) the shed pick up exactly one service item.  This
    # distributes feed across animals instead of stranding it on one carrier.
    shed = private.get("shed", {})

    def assign_pickups(item: str, count: int) -> None:
        available = min(count, int(shed.get(item, 0)))
        for serial in range(available):
            if not remaining:
                return
            target = access[serial % len(access)]
            _, index = min((_distance(positions[i], target), i) for i in remaining)
            assignments[index] = (target[0], target[1], ["PICKUP", item, 1])
            remaining.remove(index)

    assign_pickups("WHEAT", len(unfed) if day < 29 else 0)
    for animal in ("GOOSE", "COW", "SHEEP"):
        kind = ANIMALS[animal]["structure"]
        assign_pickups(animal, min(len(empty_structures[kind]), _private_item_count(private, animal)))
    assign_pickups("FERTILIZER", len(fertilizer_targets) if day < 28 else 0)

    builds = _planned_builds(obs)
    reserved = {(x, y) for x, y, _ in builds}
    tasks = _crop_tasks(obs, reserved)
    tasks.extend((4, x, y, action) for x, y, action in builds)
    fertilizer_stock = _private_item_count(private, "FERTILIZER")
    fertilizer_room = max(0, min(8, len(_fertilizer_targets(obs))) - fertilizer_stock)
    for x, y, tile in animals_on_map:
        if day < 29 and tile.get("fed_today", False) and not tile.get("cared_today", False):
            tasks.append((1, x, y, ["CARE"]))
        if day < 28 and fertilizer_room > 0 and tile.get("fertilizer_available", False):
            tasks.append((2, x, y, ["COLLECT_FERTILIZER"]))
            fertilizer_room -= 1
        if _should_harvest(tile, obs):
            tasks.append((0, x, y, ["HARVEST"]))

    # Preserve urgent on-tile commitments, then perform deterministic global
    # nearest-task matching.  Each task is removed exactly once.
    for index in sorted(list(remaining)):
        local = [
            (task[0], task_index)
            for task_index, task in enumerate(tasks)
            if task[0] <= 0 and (task[1], task[2]) == positions[index]
        ]
        if not local:
            continue
        _, task_index = min(local)
        task = tasks.pop(task_index)
        assignments[index] = (task[1], task[2], task[3])
        remaining.remove(index)

    for priority in sorted({task[0] for task in tasks}):
        while remaining:
            choices = [(j, task) for j, task in enumerate(tasks) if task[0] == priority]
            if not choices:
                break
            _, index, task_index = min(
                (_distance(positions[i], (task[1], task[2])), i, j)
                for i in remaining
                for j, task in choices
            )
            task = tasks.pop(task_index)
            assignments[index] = (task[1], task[2], task[3])
            remaining.remove(index)

    actions: list[list[Any]] = []
    for index, position in enumerate(positions):
        assignment = assignments.get(index)
        if assignment is None:
            actions.append(["PASS"])
            continue
        tx, ty, operation = assignment
        actions.append(operation if position == (tx, ty) else _step_toward(position, (tx, ty)))
    return actions[0], actions[1:]


def _hire_cost(start: int, count: int) -> int:
    return sum(FIB_HIRE_COSTS[start : start + count])


def _market_actions(obs: dict[str, Any]) -> list[list[Any]]:
    farm = obs["farms"][obs["player"]]
    private = obs["private"]
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    money = float(farm["money"])
    orders: list[list[Any]] = []
    crops = _crop_counts(farm)
    active = sum(crops.values())
    animals = _animal_counts(farm)
    animal_total = sum(animals.values())
    shed = private.get("shed", {})

    # Always expose harvested value to the market; only wheat needed for the
    # next feeding round is retained.
    wheat_reserve = animal_total + 1 if day < 29 else 0
    for product in sorted(SALE_PRODUCTS, key=lambda item: -int(obs["market"]["prices"].get(item, 0))):
        quantity = int(shed.get(product, 0))
        if product == "WHEAT":
            quantity = max(0, quantity - wheat_reserve)
        if quantity > 0:
            orders.append(["SELL", product, quantity])

    unlocked = len(farm.get("unlocked_quadrants", ["NW"]))
    land_cost = LAND_PRICES[unlocked - 1] if unlocked <= len(LAND_PRICES) else None
    buy_land = False
    if land_cost is not None:
        if unlocked == 1 and day == 0 and money >= 2_000:
            buy_land = True
        elif unlocked == 2 and day <= 10 and money >= land_cost + 3_500:
            buy_land = True
        elif unlocked == 3 and day <= 12 and money >= land_cost + 7_000:
            buy_land = True
    if buy_land:
        orders.append(["BUY_LAND"])
        money -= float(land_cost or 0)

    # Buy only animals that have a real or same-turn planned structure slot.
    goals = _animal_goals(day)
    planned = _planned_builds(obs)
    structure_slots = {
        "COOP": sum(1 for _, _, tile in _tiles(farm) if tile.get("kind") == "COOP" and "animal" not in tile),
        "PASTURE": sum(1 for _, _, tile in _tiles(farm) if tile.get("kind") == "PASTURE" and "animal" not in tile),
    }
    for _, _, action in planned:
        structure_slots[action[0].replace("BUILD_", "")] += 1
    bought_animal = False
    for animal in ("GOOSE", "COW", "SHEEP"):
        in_system = animals[animal] + _private_item_count(private, animal)
        kind = ANIMALS[animal]["structure"]
        if (
            in_system < goals[animal]
            and structure_slots[kind] > 0
            and money >= int(ANIMALS[animal]["cost"]) + 1_500
            and len(orders) < 10
            and not bought_animal
        ):
            orders.append(["BUY_ANIMAL", animal, 1])
            structure_slots[kind] -= 1
            money -= int(ANIMALS[animal]["cost"])
            bought_animal = True

    # Feeding stock is purchased at the dynamic wheat quote only when farm
    # production and carried stock cannot cover today's unfed animals.
    unfed = sum(
        1
        for _, _, tile in _tiles(farm)
        if "animal" in tile and not tile.get("fed_today", False)
    )
    wheat_stock = _private_item_count(private, "WHEAT")
    feed_gap = max(0, unfed - wheat_stock)
    if feed_gap > 0 and day < 29 and money >= feed_gap * int(obs["market"]["prices"].get("WHEAT", 25)) + 300:
        orders.append(["BUY_PRODUCT", "WHEAT", feed_gap])

    # Seed stock is capped by what the current crew can plant before the
    # afternoon service window.  This directly prevents terminal seed piles.
    seed_stock = sum(int(private.get("seeds", {}).get(crop, 0)) for crop in CROPS)
    builds_count = len(planned)
    empty_now = sum(tile is None for row in farm["tiles"] for tile in row)
    # Keep two empty-tile slack: purchases execute after this turn's unit
    # actions, while weed/build/plant changes are based on the older snapshot.
    future_empty = max(0, empty_now + (25 if buy_land else 0) - builds_count - 2)
    current_units = 1 + len(farm.get("hands", []))
    plant_budget = max(0, min(3, current_units // 3 + 1, future_empty) - seed_stock)
    if plant_budget > 0 and day <= 22 and hour <= 6 and len(orders) < 10:
        scores = _crop_scores(obs)
        crop = max(CROPS, key=lambda name: (scores[name], name))
        reserve = 500 + animal_total * 30 + _hire_cost(0, min(10, max(1, current_units)))
        spendable = max(0.0, money - reserve)
        if scores[crop] > 0 and spendable >= int(CROPS[crop]["seed"]):
            count = min(plant_budget, int(spendable // int(CROPS[crop]["seed"])))
            if count > 0:
                orders.append(["BUY_SEED", crop, count])
                money -= count * int(CROPS[crop]["seed"])

    workload = active + seed_stock + animal_total * 2
    target_hands = min(12, max(8, math.ceil(workload / 12) + 5))
    current_hands = len(farm.get("hands", []))
    if hour <= 2 and current_hands < target_hands and len(orders) < 10:
        desired = min(target_hands - current_hands, 10 - len(orders))
        affordable = 0
        hires_today = int(farm.get("hires_today", 0))
        for count in range(1, desired + 1):
            if _hire_cost(hires_today, count) <= money:
                affordable = count
        orders.extend([["HIRE"] for _ in range(affordable)])

    return orders[:10]


def agent(obs: dict[str, Any]) -> dict[str, Any]:
    """Kaggle entry point."""
    try:
        farmer, hands = _unit_actions(obs)
        market = _market_actions(obs)
        return {"farmer": farmer, "hands": hands, "market": market}
    except Exception:
        farms = obs.get("farms", [])
        player = int(obs.get("player", 0))
        hand_count = len(farms[player].get("hands", [])) if player < len(farms) else 0
        return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hand_count)], "market": []}
