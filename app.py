# app.py — Thai Customs ED01 Demo (STRICT INVOICE MODE, EN UI)
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
from openai import OpenAI

from pdf_text_extractor import extract_text_from_pdf
from thai_widget import render_declaration_widget
from weight_allocation import allocate_weights

# Optional fallback (only when invoice doesn't provide structured items)
from parts_catalog import DEMO_PARTS


# =============================
#  Config
# =============================
STRICT_BEGIN = "ED01_ITEMS_JSON_BEGIN"
STRICT_END = "ED01_ITEMS_JSON_END"

# STRICT mode is default for business demo: do NOT invent goods.
STRICT_INVOICE_MODE = True


# =============================
#  OpenAI init (optional)
# =============================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# =============================
#  Helpers: extract structured JSON block from invoice text
# =============================
def parse_strict_invoice_payload(invoice_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Looks for an embedded JSON payload inside the invoice PDF text:

    ED01_ITEMS_JSON_BEGIN
    { ... JSON ... }
    ED01_ITEMS_JSON_END

    Returns dict or None.
    """
    if not invoice_text:
        return None

    m = re.search(
        rf"{re.escape(STRICT_BEGIN)}\s*(\{{.*?\}})\s*{re.escape(STRICT_END)}",
        invoice_text,
        flags=re.S,
    )
    if not m:
        return None

    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def normalize_items_from_strict_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalise items from strict invoice payload into the ED01 item schema used by widget.
    Expected payload format (recommended):
    {
      "invoice_number": "...",
      "invoice_date": "...",
      "invoice_currency": "USD",
      "declared_weight_kg": 500,
      "items": [
        {
          "line_no": 1,
          "part_id": "INV-L1",
          "description_en": "...",
          "description_th": "...",
          "hs_code": "...",
          "quantity": 2,
          "unit": "piece",
          "unit_price": 100,
          "gross_weight_kg": 120.5
        }
      ]
    }
    """
    items = payload.get("items") or []
    out: List[Dict[str, Any]] = []

    for it in items:
        qty = float(it.get("quantity", 0) or 0)
        unit_price = float(it.get("unit_price", 0) or 0)

        out.append(
            {
                "part_id": it.get("part_id") or f"LINE-{it.get('line_no', '')}".strip("-"),
                "description_en": it.get("description_en", "") or "",
                "description_th": it.get("description_th", "") or "",
                "hs_code": it.get("hs_code", "") or "",
                "quantity": qty,
                "unit": it.get("unit", "piece") or "piece",
                "unit_price": unit_price,
                "total_value": round(qty * unit_price, 2),
                # optional, used if provided
                "gross_weight_kg": float(it.get("gross_weight_kg", 0) or 0),
            }
        )

    return out


# =============================
#  Helpers: parse invoice header fields from plain PDF text
# =============================
def parse_invoice_header_fields(invoice_text: Optional[str]) -> Dict[str, Any]:
    """
    Lightweight regex parsing to extract:
    - invoice_number
    - invoice_date
    - currency
    - invoice_total_amount (optional)
    - declared_weight_kg (optional)

    This is intentionally conservative: if not found -> empty.
    """
    if not invoice_text:
        return {}

    txt = invoice_text

    # Invoice No / Number
    inv_no = ""
    patterns_no = [
        r"(?:Invoice\s*(?:No\.?|Number)\s*[:#]?\s*)([A-Z0-9\-\/]+)",
        r"(?:INV(?:OICE)?\s*[:#]?\s*)([A-Z0-9\-\/]+)",
    ]
    for p in patterns_no:
        m = re.search(p, txt, flags=re.I)
        if m:
            inv_no = m.group(1).strip()
            break

    # Invoice Date (supports YYYY-MM-DD / DD-MMM-YYYY / DD/MM/YYYY etc.)
    inv_date = ""
    patterns_date = [
        r"(?:Invoice\s*Date\s*[:#]?\s*)(\d{4}[-/]\d{2}[-/]\d{2})",
        r"(?:Invoice\s*Date\s*[:#]?\s*)(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(?:Date\s*[:#]?\s*)(\d{4}[-/]\d{2}[-/]\d{2})",
        r"(?:Date\s*[:#]?\s*)(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ]
    for p in patterns_date:
        m = re.search(p, txt, flags=re.I)
        if m:
            inv_date = m.group(1).strip()
            break

    # Currency (USD/EUR/THB etc.)
    currency = ""
    m = re.search(r"(?:Currency\s*[:#]?\s*)([A-Z]{3})", txt, flags=re.I)
    if m:
        currency = m.group(1).upper().strip()
    else:
        # fallback: detect common currencies if repeated
        for c in ["USD", "EUR", "THB", "CNY", "JPY", "GBP"]:
            if re.search(rf"\b{c}\b", txt):
                currency = c
                break

    # Total Amount (very rough)
    total_amount = None
    # Example: "Total: 12,345.67 USD"
    m = re.search(r"(?:Grand\s*Total|Total\s*Amount|Total)\s*[:#]?\s*([\d,]+\.\d{2})", txt, flags=re.I)
    if m:
        try:
            total_amount = float(m.group(1).replace(",", ""))
        except Exception:
            total_amount = None

    # Declared / Total weight (kg)
    declared_weight_kg = None
    m = re.search(r"(?:Total\s*Weight|Gross\s*Weight)\s*[:#]?\s*([\d,]+(?:\.\d+)?)\s*(?:kg|kgs)\b", txt, flags=re.I)
    if m:
        try:
            declared_weight_kg = float(m.group(1).replace(",", ""))
        except Exception:
            declared_weight_kg = None

    out: Dict[str, Any] = {}
    if inv_no:
        out["invoice_number"] = inv_no
    if inv_date:
        out["invoice_date"] = inv_date
    if currency:
        out["invoice_currency"] = currency
    if total_amount is not None:
        out["invoice_total_amount"] = total_amount
    if declared_weight_kg is not None:
        out["declared_weight_kg"] = declared_weight_kg

    return out


# =============================
#  Weight allocation (STRICT)
# =============================
def apply_weight_logic(items: List[Dict[str, Any]], declared_weight_kg: float) -> Tuple[List[Dict[str, Any]], float]:
    """
    If items provide gross_weight_kg per line -> use it and compute totals.
    Else allocate declared_weight_kg across items using allocate_weights() (by value, then qty fallback).
    """
    if not items:
        return items, 0.0

    # If every item has positive gross_weight_kg -> use it
    have_line_weights = all(float(i.get("gross_weight_kg", 0) or 0) > 0 for i in items)
    if have_line_weights:
        total = 0.0
        for it in items:
            w = float(it.get("gross_weight_kg", 0) or 0)
            it["allocated_weight"] = round(w, 3)
            total += w
        return items, round(total, 3)

    # Otherwise allocate declared weight
    declared = float(declared_weight_kg or 0)
    if declared <= 0:
        # last resort: do not allocate
        for it in items:
            it["allocated_weight"] = 0.0
        return items, 0.0

    allocated_items = allocate_weights(items, declared)
    total_alloc = round(sum(float(i.get("allocated_weight", 0) or 0) for i in allocated_items), 3)
    return allocated_items, total_alloc


# =============================
#  Thai declaration narrative (optional)
# =============================
def call_openai_thai_declaration(data: Dict[str, Any]) -> str:
    """
    Generates a Thai official-style ED01 narrative.
    If OPENAI_API_KEY is missing, returns DEMO text (JSON preview).
    """
    if not client:
        return "[DEMO MODE]\n\n" + json.dumps(data, ensure_ascii=False, indent=2)

    system_prompt = (
        "คุณเป็นเจ้าหน้าที่ศุลกากรไทยระดับเชี่ยวชาญ "
        "ทำหน้าที่จัดทำคำอธิบายประกอบใบขนสินค้านำเข้า (ED01) "
        "ให้เขียนเป็นภาษาไทยทางการ แบ่งหัวข้อชัดเจน "
        "และยึดข้อมูลจาก JSON เท่านั้น ห้ามดัดแปลงหรือเพิ่มสินค้าใหม่."
    )

    user_prompt = json.dumps(data, ensure_ascii=False, indent=2)

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return resp.output[0].content[0].text


# =============================
#  Build ED01 payload (STRICT)
# =============================
def build_payload_strict(
    invoice_text: Optional[str],
    packing_text: Optional[str],
    transport_text: Optional[str],
    selected_demo_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    STRICT mode:
    - Prefer strict JSON payload embedded in invoice (1:1 lines).
    - If not available: do NOT invent items. For internal demo only, you may fallback to selected demo labels.
    """
    # Extract header fields conservatively from invoice text
    inv_fields = parse_invoice_header_fields(invoice_text)

    # 1) STRICT payload from invoice
    strict_payload = parse_strict_invoice_payload(invoice_text)

    items: List[Dict[str, Any]] = []
    declared_weight_kg = 0.0

    if strict_payload:
        items = normalize_items_from_strict_payload(strict_payload)
        declared_weight_kg = float(strict_payload.get("declared_weight_kg", 0) or 0)
        # override header if provided in strict payload
        inv_fields = {
            **inv_fields,
            **{k: v for k, v in strict_payload.items() if k in ["invoice_number", "invoice_date", "invoice_currency", "invoice_total_amount", "declared_weight_kg"]},
        }
    else:
        # 2) Fallback: only if user selected demo items (NOT for business-grade strict mode)
        # This is kept so you can still test UI without strict invoice payload.
        if selected_demo_labels:
            selected_ids = [lbl.split(" — ")[0] for lbl in selected_demo_labels]
            for p in DEMO_PARTS:
                if p["part_id"] in selected_ids:
                    qty = float(p.get("default_quantity", 1) or 1)
                    unit_price = 100.0
                    items.append(
                        {
                            "part_id": p["part_id"],
                            "description_en": p["description_en"],
                            "description_th": p["description_th"],
                            "hs_code": p["hs_code"],
                            "quantity": qty,
                            "unit": p["unit"],
                            "unit_price": unit_price,
                            "total_value": round(qty * unit_price, 2),
                            "gross_weight_kg": 0.0,
                        }
                    )
            # demo default only
            declared_weight_kg = 500.0

    # Apply weight logic
    items, total_alloc = apply_weight_logic(items, declared_weight_kg)

    payload: Dict[str, Any] = {
        "declaration_number": "ED01-DEMO-STRICT-0001",
        "mode": "STRICT_INVOICE" if strict_payload else "DEMO_FALLBACK",

        # Parties (still demo placeholders; later: parse from BL/Invoice)
        "importer_name": "Demo Importer Co., Ltd.",
        "consignee_name": "Demo Consignee Thailand Co., Ltd.",
        "shipper_name": "Demo Exporter International Ltd.",

        # Invoice fields (parsed / provided)
        "invoice_number": inv_fields.get("invoice_number", "N/A"),
        "invoice_date": inv_fields.get("invoice_date", ""),
        "invoice_currency": inv_fields.get("invoice_currency", ""),
        "invoice_total_amount": inv_fields.get("invoice_total_amount", None),

        # Raw extracted text (for auditability)
        "invoice_text": invoice_text or "(No invoice text extracted)",
        "packing_list_text": packing_text or "(No packing list text extracted)",
        "transport_doc_text": transport_text or "(No transport document text extracted)",

        # Transport info (demo placeholders; later: parse BL)
        "transport_info": {
            "vessel": "DEMO VESSEL / FLIGHT",
            "bl_no": "BL-DEMO-STRICT-001",
            "port_loading": "SHANGHAI, CN",
            "port_discharge": "LAEM CHABANG, TH",
        },

        # Weight totals
        "declared_weight_kg": round(float(declared_weight_kg or 0), 3),
        "total_allocated_weight_kg": round(float(total_alloc or 0), 3),

        # Commodity lines
        "items": items,
    }

    return payload


# =============================
#  Workflow for Gradio
# =============================
def workflow(
    selected_demo_labels: List[str],
    transport_pdf,
    packing_pdf,
    invoice_pdf,
) -> Tuple[str, str]:
    # Extract text from each PDF (bytes or file-like)
    transport_text = extract_text_from_pdf(transport_pdf) if transport_pdf else None
    packing_text = extract_text_from_pdf(packing_pdf) if packing_pdf else None
    invoice_text = extract_text_from_pdf(invoice_pdf) if invoice_pdf else None

    payload = build_payload_strict(
        invoice_text=invoice_text,
        packing_text=packing_text,
        transport_text=transport_text,
        selected_demo_labels=selected_demo_labels,
    )

    # Business-grade STRICT: if no strict items were found, warn clearly
    if STRICT_INVOICE_MODE and payload.get("mode") != "STRICT_INVOICE":
        warning = (
            "STRICT MODE WARNING: No structured invoice item block was found in the uploaded invoice.\n"
            "The app used DEMO_FALLBACK items for UI testing only.\n"
            "For business demo, upload the provided STRICT invoice PDF (with embedded ED01 JSON block)."
        )
        payload["warning"] = warning

    thai_text = call_openai_thai_declaration(payload)
    html_widget = render_declaration_widget(thai_text, payload)

    return json.dumps(payload, ensure_ascii=False, indent=2), html_widget


# =============================
#  Force English system strings (Gradio) via JS patch
# =============================
JS_FORCE_ENGLISH = r"""
() => {
  const replacements = [
    ["Перетащите файл сюда", "Drag and drop a file here"],
    ["или", "or"],
    ["Нажмите для загрузки", "Click to upload"],
    ["Загрузите файл", "Upload a file"],
    ["Удалить", "Remove"],
    ["Очистить", "Clear"],
    ["Ошибка", "Error"]
  ];

  const walk = (node) => {
    if (!node) return;
    if (node.nodeType === Node.TEXT_NODE) {
      let t = node.nodeValue;
      if (!t) return;
      for (const [ru, en] of replacements) {
        if (t.includes(ru)) t = t.replaceAll(ru, en);
      }
      node.nodeValue = t;
      return;
    }
    node.childNodes && node.childNodes.forEach(walk);
  };

  let tries = 0;
  const timer = setInterval(() => {
    walk(document.body);
    tries += 1;
    if (tries >= 20) clearInterval(timer);
  }, 300);
}
"""


# =============================
#  Build Gradio app (EN UI)
# =============================
def build_app() -> gr.Blocks:
    part_labels = [f"{p['part_id']} — {p['description_en']}" for p in DEMO_PARTS]

    with gr.Blocks(title="Thai Customs ED01 — Strict Invoice Demo") as demo:
        gr.Markdown(
            """
# Thai Customs ED01 — Strict Invoice Demo (Business-safe)

**Key rule:** 1 line in Commercial Invoice → 1 line in ED01 declaration (no invented goods).

**Upload 3 PDFs:**
1) Transport document (B/L / AWB / CMR)
2) Packing List
3) Commercial Invoice

The system will extract invoice header fields (No/Date/Currency), build ED01 payload, allocate weight, and render a Thai form-style draft.
            """.strip()
        )

        with gr.Row():
            with gr.Column(scale=1):
                # Demo selection kept only as a fallback for UI testing
                demo_parts = gr.CheckboxGroup(
                    label="Demo parts (fallback only if invoice has no structured items)",
                    choices=part_labels,
                    value=[],
                )

                transport_pdf = gr.File(
                    label="1) Transport document (B/L, AWB, CMR, etc.) — PDF",
                    file_types=[".pdf"],
                    type="binary",
                )
                packing_pdf = gr.File(
                    label="2) Packing List — PDF",
                    file_types=[".pdf"],
                    type="binary",
                )
                invoice_pdf = gr.File(
                    label="3) Commercial Invoice — PDF (STRICT)",
                    file_types=[".pdf"],
                    type="binary",
                )

                run = gr.Button("Generate ED01 Declaration")

            with gr.Column(scale=1):
                json_output = gr.Code(
                    label="Generated ED01 Payload (JSON)",
                    language="json",
                    interactive=False,
                )

        html_output = gr.HTML(label="ED01 Declaration Preview (Thai form-style widget)")

        run.click(
            workflow,
            inputs=[demo_parts, transport_pdf, packing_pdf, invoice_pdf],
            outputs=[json_output, html_output],
        )

        demo.load(fn=None, inputs=None, outputs=None, js=JS_FORCE_ENGLISH)

    return demo


# Local run (optional). Railway should use main.py.
if __name__ == "__main__":
    build_app().launch(show_error=True)
