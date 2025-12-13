# weight_allocation.py
from typing import List, Dict, Any


def allocate_weights(items: List[Dict[str, Any]], total_weight: float) -> List[Dict[str, Any]]:
    """
    Automatic weight allocation across declared items (Thai customs-style fallback logic).

    Primary: proportional to customs value per item (quantity * unit_price).
    Fallback: proportional to quantity if total value is zero.

    - Rounds to 3 decimals
    - Adjusts a single line to make the total EXACTLY match total_weight
    - Avoids negative allocations and preserves the total
    """

    if not items or total_weight <= 0:
        return items

    # Sanitise inputs: negative qty/price -> treat as 0 for allocation purposes
    values: List[float] = []
    quantities: List[float] = []

    for item in items:
        qty = float(item.get("quantity", 0) or 0)
        price = float(item.get("unit_price", 0) or 0)

        qty = max(qty, 0.0)
        price = max(price, 0.0)

        quantities.append(qty)
        values.append(qty * price)

    total_value = sum(values)

    # Compute raw weights
    if total_value > 0:
        raw_weights = [(v / total_value) * total_weight for v in values]
    else:
        total_qty = sum(quantities)
        if total_qty <= 0:
            # If everything is zero, split evenly
            raw_weights = [total_weight / len(items)] * len(items)
        else:
            raw_weights = [(q / total_qty) * total_weight for q in quantities]

    # Round to 3 decimals
    rounded = [round(w, 3) for w in raw_weights]

    # Choose a stable line for balancing: the one with the largest rounded weight
    idx = max(range(len(rounded)), key=lambda i: rounded[i])

    diff = round(total_weight - sum(rounded), 3)
    rounded[idx] = round(rounded[idx] + diff, 3)

    # If balancing caused a negative value (rare but possible), fix by shifting deficit
    if rounded[idx] < 0:
        deficit = -rounded[idx]
        rounded[idx] = 0.0

        # redistribute deficit from other lines proportionally to their current weights
        pool = sum(rounded) or 1.0
        for i in range(len(rounded)):
            if i == idx:
                continue
            take = round((rounded[i] / pool) * deficit, 3)
            rounded[i] = round(max(rounded[i] - take, 0.0), 3)

        # final micro-balance
        final_diff = round(total_weight - sum(rounded), 3)
        j = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[j] = round(rounded[j] + final_diff, 3)

    # Write back
    for item, w in zip(items, rounded):
        item["allocated_weight"] = float(w)

    return items
