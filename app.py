# app.py
from __future__ import annotations

import json
import os
import traceback
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
from openai import OpenAI

from parts_catalog import DEMO_PARTS
from pdf_text_extractor import extract_text_from_pdf
from thai_widget import render_declaration_widget
from weight_allocation import allocate_weights


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def call_openai_thai_declaration(data: Dict[str, Any]) -> str:
    """
    Generate an official-style ED01 narrative in Thai.
    If OPENAI_API_KEY is not set, returns DEMO MODE JSON.
    """
    if not client:
        return "[DEMO MODE]\n\n" + json.dumps(data, ensure_ascii=False, indent=2)

    system_prompt = (
        "คุณเป็นเจ้าหน้าที่ศุลกากรไทยระดับเชี่ยวชาญ "
        "ทำหน้าที่จัดทำคำอธิบายประกอบใบขนสินค้านำเข้า (ED01) "
        "ให้เขียนเป็นภาษาไทยทางการ แบ่งหัวข้อชัดเจน "
        "และยึดข้อมูลจาก JSON เท่านั้น ห้ามดัดแปลง."
    )

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False, indent=2)},
        ],
    )

    return resp.output[0].content[0].text


def build_payload(
    selected_ids: List[str],
    invoice_text: Optional[str],
    packing_text: Optional[str],
    transport_text: Optional[str],
) -> Dict[str, Any]:

    items: List[Dict[str, Any]] = []

    for p in DEMO_PARTS:
        if p["part_id"] in selected_ids:
            unit_price = 100  # demo price (later: parse real invoice)
            qty = p["default_quantity"]
            total_value = qty * unit_price
            items.append(
                {
                    "part_id": p["part_id"],
                    "description_en": p["description_en"],
                    "description_th": p["description_th"],
                    "hs_code": p["hs_code"],
                    "quantity": qty,
                    "unit": p["unit"],
                    "unit_price": unit_price,
                    "total_value": total_value,
                }
            )

    TOTAL_DECLARED_WEIGHT_KG = 500.0
    if items:
        items = allocate_weights(items, TOTAL_DECLARED_WEIGHT_KG)

    payload: Dict[str, Any] = {
        "declaration_number": "ED01-DEMO-0001",
        "importer_name": "Demo Importer Co., Ltd.",
        "consignee_name": "Demo Consignee Thailand Co., Ltd.",
        "shipper_name": "Demo Exporter International Ltd.",
        "invoice_number": "INV-DEMO-001",

        # keep extracted texts (for demo transparency)
        "invoice_text": invoice_text or "(No invoice text extracted)",
        "packing_list_text": packing_text or "(No packing list text extracted)",
        "transport_doc_text": transport_text or "(No transport document text extracted)",

        "transport_info": {
            "vessel": "DEMO VESSEL / FLIGHT",
            "bl_no": "BL-DEMO-001",
            "port_loading": "SHANGHAI, CN",
            "port_discharge": "LAEM CHABANG, TH",
        },

        "declared_weight_kg": TOTAL_DECLARED_WEIGHT_KG,
        "total_allocated_weight_kg": round(sum(i.get("allocated_weight", 0.0) for i in items), 3),
        "items": items,
    }

    return payload


def workflow(
    selected_labels: List[str],
    transport_pdf_path: Optional[str],
    packing_pdf_path: Optional[str],
    invoice_pdf_path: Optional[str],
) -> Tuple[str, str, str]:
    """
    Returns:
      - JSON payload (string)
      - HTML widget
      - Run log (string)  <-- so errors are visible in UI
    """
    try:
        if not selected_labels:
            return "[]", "<p>Please select at least one item.</p>", "No items selected."

        selected_ids = [label.split(" — ")[0] for label in selected_labels]

        # NOTE: file inputs are filepaths
        transport_text = extract_text_from_pdf(transport_pdf_path) if transport_pdf_path else None
        packing_text = extract_text_from_pdf(packing_pdf_path) if packing_pdf_path else None
        invoice_text = extract_text_from_pdf(invoice_pdf_path) if invoice_pdf_path else None

        payload = build_payload(
            selected_ids=selected_ids,
            invoice_text=invoice_text,
            packing_text=packing_text,
            transport_text=transport_text,
        )

        thai_text = call_openai_thai_declaration(payload)
        html_widget = render_declaration_widget(thai_text, payload)

        run_log = "OK. Generated ED01 draft successfully."
        return json.dumps(payload, ensure_ascii=False, indent=2), html_widget, run_log

    except Exception:
        tb = traceback.format_exc()
        # Show readable error inside UI
        return "{}", "<p><b>Error:</b> see log panel.</p>", tb


# ---- Force English (Gradio dropzone system strings) ----
JS_FORCE_ENGLISH = r"""
() => {
  const replacements = [
    ["Перетащите файл сюда", "Drag and drop a file here"],
    ["Нажмите для загрузки", "Click to upload"],
    ["или", "or"],
    ["Ошибка", "Error"],
  ];

  const replaceText = (root) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {
      let t = node.nodeValue || "";
      for (const [ru, en] of replacements) {
        if (t.includes(ru)) t = t.split(ru).join(en);
      }
      node.nodeValue = t;
    }
  };

  // initial
  replaceText(document.body);

  // keep patching while Gradio renders/upgrades DOM
  const obs = new MutationObserver(() => replaceText(document.body));
  obs.observe(document.body, { childList: true, subtree: true });

  // safety stop after 60s
  setTimeout(() => obs.disconnect(), 60000);
}
"""


def build_app() -> gr.Blocks:
    part_labels = [f"{p['part_id']} — {p['description_en']}" for p in DEMO_PARTS]

    with gr.Blocks(title="Thai Customs ED01 — Automated Declaration Demo") as demo:
        gr.Markdown(
            """
# TH Thai Customs ED01 — Automated Declaration Demo

1. Select demo auto parts  
2. Upload three documents (PDF): **Transport document**, **Packing List**, **Commercial Invoice**  
3. Generate an **ED01 draft in Thai** with item table, Duty/VAT summary, QR-code, PDF print, and **weight allocation**
            """.strip()
        )

        with gr.Row():
            with gr.Column(scale=1):
                parts = gr.CheckboxGroup(
                    label="Auto Parts (select items to declare)",
                    choices=part_labels,
                    value=part_labels,
                )

                # IMPORTANT: use filepath for stability on share/HF/Railway
                transport_pdf = gr.File(
                    label="1) Transport document (B/L, AWB, CMR) — PDF",
                    file_types=[".pdf"],
                    type="filepath",
                )
                packing_pdf = gr.File(
                    label="2) Packing List — PDF",
                    file_types=[".pdf"],
                    type="filepath",
                )
                invoice_pdf = gr.File(
                    label="3) Commercial Invoice — PDF",
                    file_types=[".pdf"],
                    type="filepath",
                )

                run = gr.Button("Generate ED01 Declaration")

            with gr.Column(scale=1):
                json_output = gr.Code(label="Generated ED01 Payload (JSON)", language="json", interactive=False)
                run_log = gr.Textbox(label="Run log (errors will appear here)", lines=10)

        html_output = gr.HTML(label="ED01 Declaration Preview")

        run.click(
            workflow,
            inputs=[parts, transport_pdf, packing_pdf, invoice_pdf],
            outputs=[json_output, html_output, run_log],
        )

        # Ensure JS patch always runs
        demo.load(lambda: None, js=JS_FORCE_ENGLISH, inputs=None, outputs=None)

    return demo
