"""Kaggriculture v6: adaptive eight-pasture livestock policy.

The submission is intentionally self-contained: Kaggle only needs this file and
the top-level ``agent`` function.  The policy uses deterministic task matching,
cheap daily labor, market-aware crop selection, and automatic liquidation.
"""

from __future__ import annotations

import math
from typing import Any


CROPS = {
    "WHEAT": {"seed": 10, "maturity": 4, "yield": 4, "base": 25},
    "CARROT": {"seed": 20, "maturity": 3, "yield": 3, "base": 35},
    "TOMATO": {"seed": 50, "maturity": 11, "yield": 4, "base": 60},
    "STRAWBERRY": {"seed": 100, "maturity": 16, "yield": 4, "base": 120},
    "MELON": {"seed": 80, "maturity": 10, "yield": 6, "base": 250},
}

MARKET_PARAMS = {
    "WHEAT": (10_000, 400, "sqrt", 0.80, "log", 0.20),
    "CARROT": (10_000, 450, "log", 0.20, "sqrt", 0.70),
    "TOMATO": (10_000, 200, "linear", 0.40, "sqrt", 0.60),
    "STRAWBERRY": (10_000, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON": (10_000, 300, "log", 0.20, "sq", 3.60),
}

PRODUCTS = (
    "MELON",
    "STRAWBERRY",
    "TOMATO",
    "CARROT",
    "WHEAT",
    "MILK",
    "WOOL",
    "EGG",
    "FERTILIZER",
)

LAND_PRICES = (1_000, 2_000, 4_000)
FIB_HIRE_COSTS = (1, 1, 2, 3, 5, 8, 13, 21, 34, 55)
# The first four are the proven v4 layout. The extra four stay in the NE
# quadrant and preserve all four shed access tiles at (4/5, 4/5).
PASTURE_TILES = ((4, 3), (3, 4), (3, 3), (2, 4), (5, 3), (6, 3), (6, 4), (7, 4))
CORE_SHEEP_TILES = PASTURE_TILES[:4]
FLEX_TILES = PASTURE_TILES[4:]
ANIMAL_COSTS = {"COW": 400, "SHEEP": 500}
LIVESTOCK = ("SHEEP", "COW")
OPPONENT_SHEEP_THRESHOLD = 2
PURE_SCALE_DAY = 14
FALLBACK_COUNT = 0


def _owned_animals(obs: dict[str, Any], animal: str) -> int:
    player = int(obs["player"])
    farm = obs["farms"][player]
    private = obs.get("private", {})
    return sum(
        1
        for row in farm["tiles"]
        for tile in row
        if isinstance(tile, dict) and tile.get("animal") == animal
    ) + int(private.get("shed", {}).get(animal, 0)) + sum(
        int(inv.get(animal, 0)) for inv in private.get("inventories", [])
    )


def _mixed_livestock_response(obs: dict[str, Any]) -> bool:
    """Use visible sheep pressure in a bounded window, then latch with cows."""
    if _owned_animals(obs, "COW"):
        return True
    day = int(obs.get("day", 0))
    if day < 5 or day > 10 or _owned_animals(obs, "SHEEP") < 2:
        return False
    player = int(obs["player"])
    opponent = obs["farms"][1 - player]
    visible_sheep = sum(
        1
        for row in opponent["tiles"]
        for tile in row
        if isinstance(tile, dict) and tile.get("animal") == "SHEEP"
    )
    return visible_sheep >= OPPONENT_SHEEP_THRESHOLD


def _target_portfolio(obs: dict[str, Any]) -> dict[str, int]:
    day = int(obs.get("day", 0))
    if day < 5:
        return {"SHEEP": 1, "COW": 0}
    if day < 7:
        return {"SHEEP": 2, "COW": 0}
    if _mixed_livestock_response(obs):
        return {"SHEEP": 4, "COW": 4}
    if day < PURE_SCALE_DAY:
        return {"SHEEP": 4, "COW": 0}
    return {"SHEEP": 8, "COW": 0}


def _pasture_plan(obs: dict[str, Any]) -> dict[tuple[int, int], str]:
    plan = {tile: "SHEEP" for tile in CORE_SHEEP_TILES}
    # Keep the flexible NE slots vacant until the day-seven choice is made.
    # Otherwise an opening sheep may occupy a future cow slot merely because
    # that pasture happens to be closer to the shed.
    day = int(obs.get("day", 0))
    if day >= 7 and _mixed_livestock_response(obs):
        flex_animal = "COW"
        plan.update({tile: flex_animal for tile in FLEX_TILES})
    elif day > 10:
        flex_animal = "SHEEP"
        plan.update({tile: flex_animal for tile in FLEX_TILES})
    return plan


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
    info = CROPS[crop]
    base = info["base"]
    i0, throughput, below_fn, below_target, above_fn, above_target = MARKET_PARAMS[crop]
    if inventory < i0:
        fn, target, sign, distance = below_fn, below_target, 1, i0 - inventory
    else:
        fn, target, sign, distance = above_fn, above_target, -1, inventory - i0
    amplitude = target * base / _shape(fn, throughput)
    return max(1, round(base + sign * amplitude * _shape(fn, distance)))


def _tile_counts(farm: dict[str, Any]) -> dict[str, int]:
    counts = {crop: 0 for crop in CROPS}
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crop = tile.get("crop")
                if crop in counts:
                    counts[crop] += 1
    return counts


def _crop_scores(obs: dict[str, Any]) -> dict[str, float]:
    """Estimate profit/day after visible future supply hits the shared market."""
    player = obs["player"]
    farms = obs["farms"]
    market = obs["market"]
    own_counts = _tile_counts(farms[player])
    other_counts = _tile_counts(farms[1 - player]) if len(farms) == 2 else {c: 0 for c in CROPS}
    days_left = max(0, 30 - int(obs.get("day", 0)))

    scores: dict[str, float] = {}
    for crop, info in CROPS.items():
        if info["maturity"] >= days_left:
            scores[crop] = -1_000_000.0
            continue
        current_inventory = int(market["inventory"].get(crop, 10_000))
        visible_output = (own_counts[crop] + other_counts[crop] + 8) * info["yield"]
        projected_price = _market_price(crop, current_inventory + visible_output)
        current_price = int(market["prices"].get(crop, info["base"]))
        # The average of the current and post-batch quotes is conservative for
        # convex glut curves and discourages crowded premium crops.
        expected_price = (current_price + projected_price) / 2.0
        profit = info["yield"] * expected_price - info["seed"]
        scores[crop] = profit / info["maturity"]
    return scores


def _should_harvest(tile: dict[str, Any], obs: dict[str, Any]) -> bool:
    units = int(tile.get("yield_units", 0))
    if units <= 0:
        return False
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    step = int(obs.get("step", day * 24 + int(obs.get("hour", 0))))
    if day >= 29:
        # Leave enough turns to walk the carried goods back, DROP, observe the
        # shed balance, and issue the final SELL order.
        return hour < 13
    max_lifespan = int(tile.get("max_lifespan_step", -1))
    if max_lifespan >= 0 and max_lifespan - step <= 4:
        return True
    crop = tile.get("crop")
    planted = int(tile.get("planted_day", day))
    age = day - planted
    if crop == "WHEAT":
        return age >= 4 or units >= 4
    if crop == "CARROT":
        return age >= 3 or units >= 3
    if crop == "MELON":
        return age >= 10 and units >= 6
    if crop in ("TOMATO", "STRAWBERRY"):
        return units >= 4
    return False


def _task_list(obs: dict[str, Any]) -> list[tuple[int, int, int, list[Any]]]:
    """Return unique tile tasks as (priority, x, y, action)."""
    player = obs["player"]
    farm = obs["farms"][player]
    private = obs["private"]
    tasks: list[tuple[int, int, int, list[Any]]] = []
    empty: list[tuple[int, int]] = []

    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if tile is None:
                if (x, y) in PASTURE_TILES:
                    tasks.append((-3, x, y, ["BUILD_PASTURE"]))
                    continue
                empty.append((x, y))
                continue
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "WEED":
                tasks.append((3, x, y, ["DIG"]))
                continue
            if tile.get("animal") in LIVESTOCK:
                day = int(obs.get("day", 0))
                hour = int(obs.get("hour", 0))
                if day < 29 and tile.get("fed_today", False) and not tile.get("cared_today", False):
                    tasks.append((-2, x, y, ["CARE"]))
                if tile.get("yield_units", 0) and (day < 29 or hour < 11):
                    tasks.append((-1, x, y, ["HARVEST"]))
                if tile.get("fertilizer_available", False) and (day < 29 or hour < 11):
                    tasks.append((0, x, y, ["COLLECT_FERTILIZER"]))
                continue
            if tile.get("kind") != "PLANT":
                continue
            ready = _should_harvest(tile, obs)
            if not tile.get("watered_today", False) and int(obs.get("day", 0)) < 29:
                # A just-planted crop starts with one missed watering and dies
                # at end-of-day if it is not serviced immediately.
                if int(tile.get("consecutive_unwatered", 0)) >= 1:
                    priority = -1
                else:
                    priority = 0 if ready else 1
                tasks.append((priority, x, y, ["WATER"]))
            elif ready:
                tasks.append((0, x, y, ["HARVEST"]))

    seeds = {crop: int(private.get("seeds", {}).get(crop, 0)) for crop in CROPS}
    scores = _crop_scores(obs)
    ranked = sorted(CROPS, key=lambda crop: (-scores[crop], crop))
    # Reserve the evening for watering and shed logistics.  Planting later can
    # strand a distant crop when carriers peel off toward the shed.
    if int(obs.get("hour", 0)) >= 15:
        return tasks

    days_left = max(0, 30 - int(obs.get("day", 0)))
    for x, y in empty:
        # A purchased seed is a sunk cost. Plant it whenever there is enough
        # biological and logistics time, even if the market moved meanwhile.
        crop = next(
            (
                name
                for name in ranked
                if seeds[name] > 0 and int(CROPS[name]["maturity"]) + 2 < days_left
            ),
            None,
        )
        if crop is None:
            break
        tasks.append((4, x, y, ["PLANT", crop]))
        seeds[crop] -= 1

    return tasks


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(position: tuple[int, int], target: tuple[int, int]) -> list[str]:
    x, y = position
    tx, ty = target
    dx, dy = tx - x, ty - y
    if abs(dx) >= abs(dy) and dx:
        return ["EAST" if dx > 0 else "WEST"]
    if dy:
        return ["SOUTH" if dy > 0 else "NORTH"]
    return ["PASS"]


def _unit_actions(obs: dict[str, Any]) -> tuple[list[Any], list[list[Any]]]:
    player = obs["player"]
    farm = obs["farms"][player]
    positions = [tuple(farm["farmer"]), *(tuple(pos) for pos in farm.get("hands", []))]
    assignments: dict[int, tuple[int, int, list[Any]]] = {}
    remaining_units = set(range(len(positions)))
    inventories = obs.get("private", {}).get("inventories", [])
    shed = obs.get("private", {}).get("shed", {})
    shed_used = sum(int(value) for value in shed.values())
    drop_room = max(0, 100 - shed_used)
    hour = int(obs.get("hour", 0))
    day = int(obs.get("day", 0))
    board_size = len(farm["tiles"])
    half = board_size // 2
    shed_access = ((half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half))
    pickup_access = tuple(
        (x, y) for x, y in shed_access if farm["tiles"][y][x] != "LOCKED"
    )

    livestock_tiles: list[tuple[int, int, dict[str, Any]]] = []
    empty_pastures: list[tuple[int, int]] = []
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict):
                continue
            if tile.get("animal") in LIVESTOCK:
                livestock_tiles.append((x, y, tile))
            elif tile.get("kind") == "PASTURE":
                empty_pastures.append((x, y))

    def inventory(index: int) -> dict[str, Any]:
        return inventories[index] if index < len(inventories) else {}

    def assign_carriers(item: str, targets: list[tuple[int, int]], operation: list[Any]) -> list[tuple[int, int]]:
        unfilled = list(targets)
        while unfilled:
            eligible = [i for i in remaining_units if int(inventory(i).get(item, 0)) > 0]
            if not eligible:
                break
            _, unit, target_index = min(
                (_distance(positions[i], target), i, j)
                for i in eligible
                for j, target in enumerate(unfilled)
            )
            target = unfilled.pop(target_index)
            assignments[unit] = (target[0], target[1], operation)
            remaining_units.remove(unit)
        return unfilled

    # Finish purchased-animal placement and daily feeding before any crop work.
    pasture_plan = _pasture_plan(obs)
    empty_by_animal = {
        animal: [tile for tile in empty_pastures if pasture_plan.get(tile) == animal]
        for animal in LIVESTOCK
    }
    for animal in LIVESTOCK:
        empty_by_animal[animal] = assign_carriers(
            animal,
            empty_by_animal[animal],
            ["PLACE", animal],
        )
    hungry = [(x, y) for x, y, tile in livestock_tiles if not tile.get("fed_today", False)]
    if day < 29:
        hungry = assign_carriers("WHEAT", hungry, ["FEED"])

    # Harvested goods must enter the shed before market orders can sell them.
    # Route carriers home immediately; otherwise a large harvest silently loses
    # everything beyond the 100-item end-of-day shed cap.
    for index in list(remaining_units):
        inv = inventory(index)
        carried = sum(int(value) for value in inv.values())
        animal_sale_load = (
            int(inv.get("WOOL", 0))
            + int(inv.get("MILK", 0))
            + int(inv.get("FERTILIZER", 0))
        )
        final_day = day >= 29
        if carried <= 0 or (animal_sale_load <= 0 and not final_day and hour < 17 and carried < 24):
            continue
        position = positions[index]
        target = min(shed_access, key=lambda tile: (_distance(position, tile), tile))
        if position == target:
            action = ["DROP"] if carried <= drop_room else ["PASS"]
            if action[0] == "DROP":
                drop_room -= carried
        else:
            action = _step_toward(position, target)
        assignments[index] = (position[0], position[1], action)
        remaining_units.remove(index)

    # Pull service inventory from the shed. One feed carrier can visit adjacent
    # pastures in succession; livestock pickups are distributed one per carrier.
    def assign_pickup(item: str, quantity: int) -> None:
        if quantity <= 0 or not remaining_units or not pickup_access:
            return
        _, unit, target = min(
            (_distance(positions[i], access), i, access)
            for i in remaining_units
            for access in pickup_access
        )
        assignments[unit] = (target[0], target[1], ["PICKUP", item, quantity])
        remaining_units.remove(unit)

    for animal in LIVESTOCK:
        animals_in_shed = int(shed.get(animal, 0))
        for _ in range(min(animals_in_shed, len(empty_by_animal[animal]))):
            assign_pickup(animal, 1)
    feed_available = int(shed.get("WHEAT", 0))
    if day < 29 and hungry and feed_available > 0:
        assign_pickup("WHEAT", min(len(hungry), feed_available))

    tasks = _task_list(obs)

    # Preserve obvious one-turn commitments before global rematching.  This is
    # especially important after PLANT: the planter is already on the new crop
    # and should WATER in place instead of walking away while a distant worker
    # is reassigned to it.
    for unit_index in sorted(list(remaining_units)):
        position = positions[unit_index]
        local = [
            (task[0], task_index)
            for task_index, task in enumerate(tasks)
            if task[0] <= 0 and (task[1], task[2]) == position
        ]
        if not local:
            continue
        _, task_index = min(local)
        task = tasks.pop(task_index)
        assignments[unit_index] = (task[1], task[2], task[3])
        remaining_units.remove(unit_index)

    for priority in sorted({task[0] for task in tasks}):
        while remaining_units:
            candidates = [(index, task) for index, task in enumerate(tasks) if task[0] == priority]
            if not candidates:
                break
            distance, unit_index, task_index = min(
                (
                    _distance(positions[unit_index], (task[1], task[2])),
                    unit_index,
                    task_index,
                )
                for unit_index in remaining_units
                for task_index, task in candidates
            )
            del distance
            task = tasks.pop(task_index)
            assignments[unit_index] = (task[1], task[2], task[3])
            remaining_units.remove(unit_index)

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
    player = obs["player"]
    farm = obs["farms"][player]
    private = obs["private"]
    day = int(obs.get("day", 0))
    hour = int(obs.get("hour", 0))
    money = float(farm["money"])
    orders: list[list[Any]] = []
    active = sum(_tile_counts(farm).values())
    seed_stock = sum(int(private.get("seeds", {}).get(crop, 0)) for crop in CROPS)

    inventories = private.get("inventories", [])
    placed_animals = {
        animal: sum(
            1
            for row in farm["tiles"]
            for tile in row
            if isinstance(tile, dict) and tile.get("animal") == animal
        )
        for animal in LIVESTOCK
    }
    carried_animals = {
        animal: sum(int(inv.get(animal, 0)) for inv in inventories)
        for animal in LIVESTOCK
    }
    carried_wheat = sum(int(inv.get("WHEAT", 0)) for inv in inventories)

    # Liquidate carried production as soon as it reaches the shed.  Fertilizer
    # is deliberately sold rather than accumulated; feed wheat is reserved.
    # inventory is worthless at the terminal step.
    shed = private.get("shed", {})
    placed_livestock = sum(placed_animals.values())
    feed_reserve = 0 if day >= 29 else max(2, placed_livestock * 2)
    for product in sorted(PRODUCTS, key=lambda item: -int(obs["market"]["prices"].get(item, 0))):
        quantity = int(shed.get(product, 0))
        if product == "WHEAT":
            quantity = max(0, quantity - max(0, feed_reserve - carried_wheat))
        if quantity > 0 and len(orders) < 10:
            orders.append(["SELL", product, quantity])

    unlocked = len(farm.get("unlocked_quadrants", ["NW"]))
    land_cost = LAND_PRICES[unlocked - 1] if unlocked <= len(LAND_PRICES) else None
    buy_land = False
    if land_cost is not None and unlocked < 2 and day <= 18:
        buy_land = (day == 0 and unlocked == 1 and money >= 2_000) or (
            day >= 8 and money >= land_cost + 3_000
        )
    if buy_land and len(orders) < 10:
        orders.append(["BUY_LAND"])
        money -= land_cost or 0

    # Preserve the proven 1 -> 2 sheep opening. At day seven either complete
    # eight sheep or diversify the four safe NE slots into cows.
    target_portfolio = _target_portfolio(obs)
    animals_in_system = {
        animal: placed_animals[animal]
        + carried_animals[animal]
        + int(shed.get(animal, 0))
        for animal in LIVESTOCK
    }
    total_animals = sum(animals_in_system.values())
    if day <= 14:
        for animal in LIVESTOCK:
            if animals_in_system[animal] >= target_portfolio[animal] or len(orders) >= 10:
                continue
            reserve = 250 + max(2, total_animals + 1) * 25 * 2
            cost = ANIMAL_COSTS[animal]
            if money >= cost + reserve:
                orders.append(["BUY_ANIMAL", animal, 1])
                money -= cost
                animals_in_system[animal] += 1
                total_animals += 1

    wheat_stock = int(shed.get("WHEAT", 0)) + carried_wheat
    feed_target = 0 if day >= 29 else max(4, total_animals * 2)
    if total_animals and wheat_stock < feed_target and len(orders) < 10:
        count = feed_target - wheat_stock
        price = int(obs["market"]["prices"].get("WHEAT", 25))
        if money >= count * price + 150:
            orders.append(["BUY_PRODUCT", "WHEAT", count])
            money -= count * price

    # Labor is cheap at first but Fibonacci costs become material before the
    # first harvest.  Scale the crew to the actual cultivated workload and keep
    # a cash runway instead of blindly hiring ten workers every day.
    current_hands = len(farm.get("hands", []))
    workload = active + seed_stock + placed_livestock * 3
    target_hands = min(10, max(6, math.ceil(workload / 12) + 3))
    if hour <= 2 and current_hands < target_hands:
        slots = 10 - len(orders)
        desired = min(target_hands - current_hands, slots)
        affordable = 0
        for count in range(1, desired + 1):
            if _hire_cost(int(farm.get("hires_today", 0)), count) <= money:
                affordable = count
        for _ in range(affordable):
            orders.append(["HIRE"])
        money -= _hire_cost(int(farm.get("hires_today", 0)), affordable)

    # Keep only enough seeds to fill the unlocked land; buy in small batches so
    # the crop choice can react to the opponent and changing market prices.
    pending_tiles = 25 if buy_land else 0
    # Two-tile slack absorbs same-turn harvest/plant and weed snapshot races;
    # without it the market can buy one seed for a tile another unit just used.
    capacity = max(0, min(75, 25 * unlocked + pending_tiles) - len(PASTURE_TILES) - 2)
    # Eight-sheep service work dominates mornings after day 7. Keep at most
    # one seed waiting, replenish only while two useful actions per hand still
    # leave headroom beyond the three daily sheep jobs, and stop after hour 6.
    # Already-owned seeds remain eligible through _task_list's maturity cutoff.
    service_headroom = current_hands * 2 - placed_livestock * 3
    gap = (
        min(max(0, capacity - active - seed_stock), max(0, 1 - seed_stock))
        if service_headroom > 0
        else 0
    )
    if gap > 0 and len(orders) < 10 and day <= 21 and hour <= 6:
        scores = _crop_scores(obs)
        days_left = max(0, 30 - day)
        purchase_cutoff = {
            "WHEAT": 16,
            "CARROT": 16,
            "TOMATO": 5,
            "STRAWBERRY": 0,
            "MELON": 5,
        }
        feasible = [
            name
            for name in CROPS
            if scores[name] > 0
            and day <= purchase_cutoff[name]
            and int(CROPS[name]["maturity"]) + 4 < days_left
        ]
        crop = max(feasible, key=lambda name: (scores[name], name)) if feasible else None
        daily_labor = _hire_cost(0, target_hands)
        runway_days = min(12, max(1, 30 - day))
        cash_reserve = 100 + daily_labor * runway_days
        spendable = max(0.0, money - cash_reserve)
        if crop is not None and spendable >= CROPS[crop]["seed"]:
            count = min(1, gap, int(spendable // CROPS[crop]["seed"]))
            if count > 0:
                orders.append(["BUY_SEED", crop, count])

    return orders[:10]


def _agent_impl(obs: dict[str, Any]) -> dict[str, Any]:
    """Run the policy without masking exceptions, for local validation."""
    farmer, hands = _unit_actions(obs)
    market = _market_actions(obs)
    return {"farmer": farmer, "hands": hands, "market": market}


def agent(obs: dict[str, Any]) -> dict[str, Any]:
    """Kaggle entry point with an observable defensive fallback."""
    global FALLBACK_COUNT
    try:
        return _agent_impl(obs)
    except Exception:
        FALLBACK_COUNT += 1
        # Invalid actions are silent no-ops, but an exception would invalidate
        # the whole submission.  A defensive PASS preserves ladder eligibility.
        farms = obs.get("farms", [])
        player = int(obs.get("player", 0))
        hand_count = len(farms[player].get("hands", [])) if player < len(farms) else 0
        return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hand_count)], "market": []}
