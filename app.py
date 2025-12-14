# app.py — Thai Customs ED01 (STRICT DEMO) — Gradio 4.x
# Rule: 1 item in Commercial Invoice -> 1 line in Declaration (ED01)
# No catalog-based auto-fill. No hallucinations.

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from pdf_text_extractor import extract_text_from_pdf
from weight_allocation import allocate_weights
from thai_widget import render_declaration_widget


# -----------------------------
# STRICT parsers (robust enough for demo PDFs)
# -----------------------------

def _clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "")).strip()


def _find_label(text: str, label: str) -> str:
    """
    Finds 'Label: value' in a PDF text block. Returns value or ''.
    """
    if not text:
        return ""
    # allow some variations of spaces
    pattern = re.compile(rf"{re.escape(label)}\s*:\s*(.+)", re.IGNORECASE)
    for line in text.splitlines():
        m = pattern.search(line)
        if m:
            return _clean(m.group(1))
    return ""


def parse_bl_strict(bl_text: str) -> Dict[str, Any]:
    """
    Extracts transport & parties hints from B/L STRICT demo.
    Expected labels (but tolerant):
      Shipper, Consignee, B/L No, Port of Loading, Port of Discharge, Vessel,
      Number of Packages, Packaging Type, Gross Weight, Measurement (CBM)
    """
    out: Dict[str, Any] = {"transport_info": {}}

    shipper = _find_label(bl_text, "Shipper")
    consignee = _find_label(bl_text, "Consignee")

    if shipper:
        out["shipper_name"] = shipper
    if consignee:
        out["consignee_name"] = consignee

    # Transport core
    bl_no = _find_label(bl_text, "B/L No")
    pol = _find_label(bl_text, "Port of Loading")
    pod = _find_label(bl_text, "Port of Discharge")
    vessel = _find_label(bl_text, "Vessel")

    if bl_no:
        out["transport_info"]["bl_no"] = bl_no
    if pol:
        out["transport_info"]["port_loading"] = pol
    if pod:
        out["transport_info"]["port_discharge"] = pod
    if vessel:
        out["transport_info"]["vessel"] = vessel

    # Packages / packaging / weights
    # Supports either:
    #   "Number of Packages: 1 pallet"
    # or separate:
    #   "Number of Packages: 1"
    #   "Packaging Type: PALLET"
    # and:
    #   "Gross Weight: 250.0 KGS"
    #   "Measurement (CBM): 1.2"
    gross_re = re.compile(r"Gross Weight\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*KGS?", re.IGNORECASE)
    cbm_re = re.compile(r"Measurement\s*\(CBM\)\s*:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
    pkg_mix_re = re.compile(r"Number of Packages\s*:\s*([0-9]+)\s*([A-Za-z]+)", re.IGNORECASE)
    pkg_num_re = re.compile(r"Number of Packages\s*:\s*([0-9]+)", re.IGNORECASE)
    pkg_type_re = re.compile(r"Packaging Type\s*:\s*([A-Za-z0-9 \-_/]+)", re.IGNORECASE)

    m = gross_re.search(bl_text or "")
    if m:
        out["transport_info"]["gross_weight_kg"] = float(m.group(1))

    m = cbm_re.search(bl_text or "")
    if m:
        out["transport_info"]["measurement_cbm"] = float(m.group(1))

    m = pkg_mix_re.search(bl_text or "")
    if m:
        out["transport_info"]["packages"] = int(m.group(1))
        out["transport_info"]["package_type"] = _clean(m.group(2)).upper()
    else:
        m1 = pkg_num_re.search(bl_text or "")
        if m1:
            out["transport_info"]["packages"] = int(m1.group(1))
        m2 = pkg_type_re.search(bl_text or "")
        if m2:
            out["transport_info"]["package_type"] = _clean(m2.group(1)).upper()

    return out


def parse_invoice_strict(inv_text: str) -> Dict[str, Any]:
    """
    STRICT invoice parser:
    - extracts invoice header fields if present
    - extracts items ONLY from invoice (no add-ons)

    Works with common patterns:
      Invoice No: ...
      Invoice Date: ...
      Currency: USD
    Items: tries to find table-like lines containing HS code + qty + price.

    Output:
      {
        invoice_number, invoice_date, invoice_currency,
        importer_name, consignee_name, shipper_name (if present),
        items: [{part_id, description_en, hs_code, quantity, unit, unit_price, total_value}]
      }
    """
    out: Dict[str, Any] = {"items": []}

    out["invoice_number"] = _find_label(inv_text, "Invoice No") or _find_label(inv_text, "Invoice Number")
    out["invoice_date"] = _find_label(inv_text, "Invoice Date") or _find_label(inv_text, "Date")
    out["invoice_currency"] = (_find_label(inv_text, "Currency") or "USD").upper()

    # Sometimes parties are included in invoice
    shipper = _find_label(inv_text, "Shipper")
    consignee = _find_label(inv_text, "Consignee")
    importer = _find_label(inv_text, "Importer")

    if shipper:
        out["shipper_name"] = shipper
    if consignee:
        out["consignee_name"] = consignee
    if importer:
        out["importer_name"] = importer

    # Item extraction heuristic:
    # Look for lines with HS-like pattern: dddd.dd.dd or dddd.dd.dd.dd etc.
    hs_re = re.compile(r"(?P<hs>\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?)")
    num_re = re.compile(r"[-+]?\d+(?:\.\d+)?")

    # Try to detect rows where HS code exists and at least 2 numbers after it (qty, unit price)
    lines = [l.strip() for l in (inv_text or "").splitlines() if l.strip()]
    candidates: List[Tuple[str, str]] = []
    for l in lines:
        m = hs_re.search(l)
        if not m:
            continue
        hs = m.group("hs")
        candidates.append((hs, l))

    items: List[Dict[str, Any]] = []
    for idx, (hs, line) in enumerate(candidates, start=1):
        # Remove excessive separators
        clean_line = re.sub(r"[|]+", " ", line)
        clean_line = re.sub(r"\s{2,}", " ", clean_line).strip()

        # Remove label-like fragments
        # Split at HS code to isolate description (left side) and numbers (right side)
        parts = clean_line.split(hs, 1)
        left = parts[0].strip(" -:") if parts else ""
        right = parts[1] if len(parts) > 1 else ""

        # description guess: take leftmost text (fallback if empty)
        description = left if left else f"Item {idx}"

        # numbers on the right: expect qty, unit_price, maybe total_value
        nums = [n for n in num_re.findall(right)]
        qty = float(nums[0]) if len(nums) >= 1 else 1.0
        unit_price = float(nums[1]) if len(nums) >= 2 else 0.0

        # unit guess
        unit = "piece"
        unit_m = re.search(r"\b(piece|pcs|pc|set|sets|kg|kgs|box|boxes|carton|cartons|pallet|pallets)\b", right, re.IGNORECASE)
        if unit_m:
            u = unit_m.group(1).lower()
            unit = "piece" if u in {"pcs", "pc"} else u

        total_value = float(nums[2]) if len(nums) >= 3 else round(qty * unit_price, 2)

        items.append(
            {
                "part_id": f"P{idx:03d}",
                "description_en": description,
                "description_th": "",  # optional; can be filled later
                "hs_code": hs,
                "quantity": int(qty) if abs(qty - int(qty)) < 1e-9 else qty,
                "unit": unit,
                "unit_price": unit_price,
                "total_value": total_value,
            }
        )

    # STRICT: if we didn't parse any rows, keep empty list (no hallucinations)
    out["items"] = items
    return out


def parse_packing_list_strict(pl_text: str) -> Dict[str, Any]:
    """
    Packing List may contain declared weight too.
    We keep it optional; BL is the primary freight weight source in this demo.
    """
    out: Dict[str, Any] = {}
    gross_re = re.compile(r"Gross Weight\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*KGS?", re.IGNORECASE)
    m = gross_re.search(pl_text or "")
    if m:
        out["declared_weight_kg"] = float(m.group(1))

    pkg_mix_re = re.compile(r"Number of Packages\s*:\s*([0-9]+)\s*([A-Za-z]+)", re.IGNORECASE)
    m = pkg_mix_re.search(pl_text or "")
    if m:
        out["packages"] = int(m.group(1))
        out["package_type"] = _clean(m.group(2)).upper()

    return out


# -----------------------------
# Thai explanatory text (demo)
# -----------------------------

def build_thai_explanatory(payload: Dict[str, Any]) -> str:
    """
    Demo-only explanatory text in Thai/English mix.
    No external APIs.
    """
    ti = payload.get("transport_info", {}) or {}
    inv_no = payload.get("invoice_number", "")
    bl_no = ti.get("bl_no", "")
    pol = ti.get("port_loading", "")
    pod = ti.get("port_discharge", "")
    gw = payload.get("declared_weight_kg", "")

    lines = [
        "เอกสารฉบับร่างเพื่อการสาธิต (DEMO DRAFT) — ไม่สามารถนำไปยื่นจริงได้",
        f"- อ้างอิงใบกำกับสินค้า (Invoice): {inv_no}",
        f"- อ้างอิงใบตราส่งสินค้า (B/L): {bl_no}",
        f"- เส้นทางขนส่ง: {pol} → {pod}",
        f"- น้ำหนักรวม (Gross Weight): {gw} kg",
        "",
        "หมายเหตุ: ระบบสาธิตนี้สร้างโครงร่าง ED01 จากเอกสารการค้า (Invoice / Packing List / B/L) "
        "และจัดสรรน้ำหนักตามสัดส่วนมูลค่าสินค้า (fallback: ตามจำนวน).",
    ]
    return "\n".join(lines)


# -----------------------------
# Core pipeline (STRICT)
# -----------------------------

def generate_ed01_from_pdfs(
    bl_file: Any,
    pl_file: Any,
    inv_file: Any,
) -> Tuple[str, str]:
    """
    Returns: (html_widget, json_payload_pretty)
    """
    bl_text = extract_text_from_pdf(bl_file) or ""
    pl_text = extract_text_from_pdf(pl_file) or ""
    inv_text = extract_text_from_pdf(inv_file) or ""

    # STRICT: items only from invoice
    inv_data = parse_invoice_strict(inv_text)
    items: List[Dict[str, Any]] = inv_data.get("items", []) or []

    # If invoice has no parseable items, do not invent anything
    if not items:
        payload = {
            "error": "No items parsed from Commercial Invoice. STRICT mode does not add items automatically.",
            "timestamp_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }
        html = f"""
        <div style="font-family:Segoe UI,system-ui;max-width:900px;margin:0 auto;border:1px solid #ef4444;padding:14px;">
          <div style="font-weight:700;color:#b91c1c;">STRICT DEMO ERROR</div>
          <div style="margin-top:8px;">No items were extracted from the Commercial Invoice PDF.</div>
          <div style="margin-top:8px;color:#6b7280;font-size:12px;">
            Please use the provided STRICT invoice sample or ensure the invoice contains HS code + quantity + unit price in text format.
          </div>
        </div>
        """
        return html, json.dumps(payload, ensure_ascii=False, indent=2)

    # Merge parties/transport from BL, optional packing list hints
    bl_data = parse_bl_strict(bl_text)
    pl_data = parse_packing_list_strict(pl_text)

    payload: Dict[str, Any] = {}
    payload.update(inv_data)
    payload.update(bl_data)

    # Transport info merge
    payload.setdefault("transport_info", {})
    payload["transport_info"].update(bl_data.get("transport_info", {}) or {})

    # Declared weight: prefer BL gross weight, fallback PL, fallback 0
    declared_weight = (
        float(payload.get("transport_info", {}).get("gross_weight_kg") or 0)
        or float(pl_data.get("declared_weight_kg") or 0)
        or 0.0
    )
    payload["declared_weight_kg"] = round(declared_weight, 3)

    # Packages: prefer BL, fallback PL
    if not payload["transport_info"].get("packages") and pl_data.get("packages"):
        payload["transport_info"]["packages"] = pl_data["packages"]
    if not payload["transport_info"].get("package_type") and pl_data.get("package_type"):
        payload["transport_info"]["package_type"] = pl_data["package_type"]

    # Compute totals
    for it in items:
        qty = float(it.get("quantity", 0) or 0)
        unit_price = float(it.get("unit_price", 0) or 0)
        if not it.get("total_value"):
            it["total_value"] = round(qty * unit_price, 2)

    payload["items"] = items
    payload["invoice_total_amount"] = round(sum(float(i.get("total_value", 0) or 0) for i in items), 2)

    # Weight allocation (STRICT): allocate only across invoice items
    allocated_items = allocate_weights(items, total_weight=payload["declared_weight_kg"])
    payload["items"] = allocated_items
    payload["total_allocated_weight_kg"] = round(sum(float(i.get("allocated_weight", 0) or 0) for i in allocated_items), 3)

    # Simple declaration number (demo)
    if not payload.get("declaration_number"):
        payload["declaration_number"] = f"ED01-DEMO-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    thai_text = build_thai_explanatory(payload)
    html = render_declaration_widget(thai_text=thai_text, payload=payload)

    return html, json.dumps(payload, ensure_ascii=False, indent=2)


# -----------------------------
# Gradio App
# -----------------------------

def build_app() -> gr.Blocks:
    with gr.Blocks(
        title="Thai Customs ED01 — STRICT Demo",
        analytics_enabled=False,
    ) as demo:
        gr.Markdown(
            "# Thai Customs ED01 — STRICT Demo\n"
            "Upload **Bill of Lading**, **Packing List**, and **Commercial Invoice** PDFs.\n\n"
            "**STRICT rule:** Commercial Invoice line items are the single source of truth — no auto-added items."
        )

        with gr.Row():
            bl_file = gr.File(label="1) Transport document (B/L, AWB, CMR) — PDF", file_types=[".pdf"])
        with gr.Row():
            pl_file = gr.File(label="2) Packing List — PDF", file_types=[".pdf"])
        with gr.Row():
            inv_file = gr.File(label="3) Commercial Invoice — PDF", file_types=[".pdf"])

        generate_btn = gr.Button("Generate ED01 (STRICT)")
        gr.Markdown("---")

        with gr.Row():
            html_out = gr.HTML(label="ED01 Widget / Print View")
        with gr.Row():
            json_out = gr.Code(label="Extracted ED01 JSON (STRICT)", language="json")

        def _run(bl, pl, inv):
            return generate_ed01_from_pdfs(bl, pl, inv)

        generate_btn.click(_run, inputs=[bl_file, pl_file, inv_file], outputs=[html_out, json_out])

        gr.Markdown(
            "—\n"
            "Demo build: runs entirely inside the app. No external APIs."
        )

    return demo


if __name__ == "__main__":
    app = build_app()
    app.queue()
    app.launch()
