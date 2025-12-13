import asyncio
from typing import Dict, Any, List

from mcp.server import Server
from mcp.types import TextContent


server = Server("ThaiCustomsMCP")


# ---------------------------
# Utils
# ---------------------------
def allocate_weights(items: List[Dict[str, Any]], total_weight: float) -> List[Dict[str, Any]]:
    if not items or total_weight <= 0:
        return items

    values = [
        float(i.get("quantity", 0)) * float(i.get("unit_price", 0))
        for i in items
    ]
    total_value = sum(values)

    if total_value <= 0:
        qty_sum = sum(float(i.get("quantity", 0)) for i in items) or 1
        raw = [(float(i.get("quantity", 0)) / qty_sum) * total_weight for i in items]
    else:
        raw = [(v / total_value) * total_weight for v in values]

    rounded = [round(w, 3) for w in raw]
    diff = round(total_weight - sum(rounded), 3)
    rounded[-1] += diff

    for item, w in zip(items, rounded):
        item["allocated_weight_kg"] = max(round(w, 3), 0.0)

    return items


# ---------------------------
# MCP Tools
# ---------------------------
@server.tool()
async def ping() -> TextContent:
    return TextContent(type="text", text="pong")


@server.tool()
async def generate_ed01(payload: Dict[str, Any]) -> TextContent:
    """
    Generate draft Thai Customs ED01 structure from invoice / BL data.
    """

    items = payload.get("items", [])
    total_weight = sum(float(i.get("gross_weight", 0) or 0) for i in items)

    # Normalize items
    normalized_items = []
    for i in items:
        qty = float(i.get("quantity", 0))
        price = float(i.get("unit_price", 0))
        total_value = qty * price

        normalized_items.append(
            {
                "description": i.get("description"),
                "hs_code": i.get("hs_code"),
                "quantity": qty,
                "unit_price": price,
                "total_value": total_value,
                "origin_country": payload.get("origin_country"),
            }
        )

    normalized_items = allocate_weights(normalized_items, total_weight)

    customs_value = sum(i["total_value"] for i in normalized_items)
    duty_rate = 0.05
    vat_rate = 0.07

    duty = customs_value * duty_rate
    vat = (customs_value + duty) * vat_rate

    ed01 = {
        "parties": {
            "shipper": payload.get("shipper"),
            "consignee": payload.get("consignee"),
        },
        "invoice": {
            "invoice_no": payload.get("invoice_no"),
            "invoice_date": payload.get("invoice_date"),
            "currency": payload.get("currency"),
            "incoterm": payload.get("incoterm"),
            "customs_value": round(customs_value, 2),
        },
        "transport": {
            "port_loading": payload.get("port_loading"),
            "port_discharge": payload.get("port_discharge"),
            "origin_country": payload.get("origin_country"),
        },
        "commodities": normalized_items,
        "taxes": {
            "import_duty": round(duty, 2),
            "vat": round(vat, 2),
            "total_taxes": round(duty + vat, 2),
        },
        "weights": {
            "declared_gross_weight_kg": total_weight,
            "allocated_total_weight_kg": round(
                sum(i["allocated_weight_kg"] for i in normalized_items), 3
            ),
        },
        "thai_explanatory_block": (
            "เอกสารฉบับนี้เป็นร่างใบขนสินค้านำเข้า (ED01) "
            "จัดทำจากข้อมูลในใบกำกับสินค้าและเอกสารขนส่ง "
            "เพื่อใช้ในการเตรียมการยื่นพิธีการศุลกากรเท่านั้น"
        ),
    }

    return TextContent(type="json", text=ed01)


# ---------------------------
# Entrypoint
# ---------------------------
async def main():
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
