from typing import Any, Dict, List


def render_declaration_widget(thai_text: str, payload: Dict[str, Any]) -> str:
    """
    Renders an ED01-style HTML widget:
      - Parties
      - Transport Info
      - Invoice Details (No/Date/Currency/Total)
      - Commodity List (WITH Allocated Weight column)
      - Duty & VAT
      - Weight Allocation (audit table)
      - Thai explanatory text
      - Print / PDF button
    """

    items: List[Dict[str, Any]] = payload.get("items", [])

    # Currency (fallback)
    currency = (payload.get("invoice_currency") or "USD").strip()

    # Customs value based on item totals
    customs_value = sum(float(i.get("total_value", 0) or 0) for i in items)

    # Rates (demo defaults; can be turned into env vars later)
    duty_rate = float(payload.get("duty_rate") or 0.05)
    vat_rate = float(payload.get("vat_rate") or 0.07)

    duty_amount = customs_value * duty_rate
    vat_amount = (customs_value + duty_amount) * vat_rate
    total_taxes = duty_amount + vat_amount

    # Weight reconciliation
    declared_weight = float(payload.get("declared_weight_kg") or 0.0)
    allocated_weight = float(payload.get("total_allocated_weight_kg") or 0.0)
    weight_diff = round(allocated_weight - declared_weight, 3)

    # Helpers
    def fmt(x: Any, ndigits: int = 2) -> str:
        try:
            return f"{float(x):,.{ndigits}f}"
        except Exception:
            return str(x)

    def safe(x: Any) -> str:
        return "" if x is None else str(x)

    # -------------------------------------------------
    # Commodity rows (now includes Allocated Weight kg)
    # -------------------------------------------------
    rows_html = ""
    for idx, it in enumerate(items, start=1):
        allocated_w = float(it.get("allocated_weight", 0.0) or 0.0)

        rows_html += f"""
        <tr>
          <td>{idx}</td>
          <td>{safe(it.get('description_th', ''))}<br/><small>{safe(it.get('description_en', ''))}</small></td>
          <td>{safe(it.get('hs_code', ''))}</td>
          <td>{fmt(it.get('quantity', 0), 0)} {safe(it.get('unit', ''))}</td>
          <td>{fmt(allocated_w, 3)}</td>
          <td>{fmt(it.get('unit_price', 0))}</td>
          <td>{fmt(it.get('total_value', 0))}</td>
        </tr>
        """

    # -------------------------------------------------
    # Weight allocation audit table (kept as separate)
    # -------------------------------------------------
    weight_rows_html = ""
    for idx, it in enumerate(items, start=1):
        weight_rows_html += f"""
        <tr>
          <td>{idx}</td>
          <td>{safe(it.get('part_id', ''))}</td>
          <td>{safe(it.get('hs_code', ''))}</td>
          <td>{fmt(it.get('quantity', 0), 0)} {safe(it.get('unit', ''))}</td>
          <td>{fmt(it.get('allocated_weight', 0), 3)}</td>
        </tr>
        """

    # Invoice totals
    invoice_total = payload.get("invoice_total_amount")
    invoice_total_display = invoice_total if invoice_total is not None else customs_value

    # -------------------------------------------------
    # HTML Widget
    # -------------------------------------------------
    html = f"""
<style>
  .ed01-container {{
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    max-width: 980px;
    margin: 0 auto;
    border: 1px solid #d0d7de;
    background: #ffffff;
    padding: 16px 24px 32px 24px;
    color: #111827;
  }}

  .ed01-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 12px;
  }}

  .ed01-section-title {{
    font-weight: 700;
    margin: 18px 0 10px 0;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 6px;
  }}

  table.ed01-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}

  table.ed01-table th, table.ed01-table td {{
    border: 1px solid #d1d5db;
    padding: 6px 8px;
    vertical-align: top;
  }}

  table.ed01-table th {{
    background: #f3f4f6;
    font-weight: 700;
    white-space: nowrap;
  }}

  .muted {{
    color: #6b7280;
    font-size: 11px;
  }}

  .ed01-footer-note {{
    font-size: 10px;
    color: #6b7280;
    margin-top: 16px;
  }}

  .ed01-print-btn {{
    margin-top: 12px;
    padding: 10px 16px;
    background: #2563eb;
    color: white;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
  }}

  .ed01-print-btn:hover {{
    background: #1d4ed8;
  }}

  .ed01-badge-demo {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    background: #facc15;
    font-size: 10px;
    font-weight: 800;
    margin-left: 8px;
  }}

  .ed01-kv {{
    font-size: 11px;
    line-height: 1.4;
  }}

  .right {{
    text-align: right;
  }}

  .nowrap {{
    white-space: nowrap;
  }}
</style>

<div class="ed01-container">

  <div class="ed01-header">
    <div>
      <div style="font-weight:800;font-size:18px;">ใบขนสินค้านำเข้า (ED01)</div>
      <div class="muted">Thai Customs Import Declaration — Demo Draft</div>
    </div>
    <div class="ed01-kv right">
      <div><b>ใบขนเลขที่ (Declaration No.):</b> {safe(payload.get('declaration_number',''))} <span class="ed01-badge-demo">DEMO</span></div>
      <div class="muted">Auto-generated (for demonstration only)</div>
    </div>
  </div>

  <!-- 1) Parties -->
  <div class="ed01-section-title">1) ข้อมูลคู่ค้า (Parties)</div>
  <table class="ed01-table">
    <tr>
      <th>ผู้นำเข้า (Importer)</th>
      <th>ผู้รับสินค้า (Consignee)</th>
      <th>ผู้ส่งออก (Shipper)</th>
    </tr>
    <tr>
      <td>{safe(payload.get('importer_name',''))}</td>
      <td>{safe(payload.get('consignee_name',''))}</td>
      <td>{safe(payload.get('shipper_name',''))}</td>
    </tr>
  </table>

  <!-- 2) Transport -->
  <div class="ed01-section-title">2) ข้อมูลการขนส่ง (Transport Information)</div>
  <table class="ed01-table">
    <tr>
      <th>เรือ / เที่ยวบิน (Vessel / Flight)</th>
      <th>เลขที่ B/L หรือ AWB</th>
      <th>ท่าเรือต้นทาง (Port of Loading)</th>
      <th>ท่าเรือปลายทาง (Port of Discharge)</th>
    </tr>
    <tr>
      <td>{safe(payload.get('transport_info', {}).get('vessel', ''))}</td>
      <td>{safe(payload.get('transport_info', {}).get('bl_no', ''))}</td>
      <td>{safe(payload.get('transport_info', {}).get('port_loading', ''))}</td>
      <td>{safe(payload.get('transport_info', {}).get('port_discharge', ''))}</td>
    </tr>
  </table>

  <!-- 3) Invoice details -->
  <div class="ed01-section-title">3) ข้อมูลใบกำกับสินค้า (Invoice Details)</div>
  <table class="ed01-table">
    <tr>
      <th class="nowrap">Invoice No</th>
      <th class="nowrap">Invoice Date</th>
      <th class="nowrap">Currency</th>
      <th class="nowrap">Total Amount</th>
    </tr>
    <tr>
      <td>{safe(payload.get('invoice_number',''))}</td>
      <td>{safe(payload.get('invoice_date',''))}</td>
      <td>{safe(payload.get('invoice_currency',''))}</td>
      <td>{fmt(invoice_total_display)} {currency}</td>
    </tr>
  </table>

  <!-- 4) Commodity List -->
  <div class="ed01-section-title">4) รายการสินค้า (Commodity List)</div>
  <table class="ed01-table">
    <tr>
      <th>ลำดับ</th>
      <th>รายละเอียดสินค้า</th>
      <th>HS Code</th>
      <th>ปริมาณ</th>
      <th class="nowrap">น้ำหนักจัดสรร (kg)</th>
      <th class="nowrap">ราคาต่อหน่วย ({currency})</th>
      <th class="nowrap">ราคารวม ({currency})</th>
    </tr>
    {rows_html}
    <tr>
      <td colspan="4" class="right"><b>Declared Gross Weight (kg)</b></td>
      <td><b>{fmt(declared_weight, 3)}</b></td>
      <td colspan="2" class="muted">From packing list / shipment gross weight</td>
    </tr>
    <tr>
      <td colspan="4" class="right"><b>Allocated Total (kg)</b></td>
      <td><b>{fmt(allocated_weight, 3)}</b></td>
      <td colspan="2" class="muted">Allocated across HS lines</td>
    </tr>
    <tr>
      <td colspan="4" class="right"><b>Difference (kg)</b></td>
      <td><b>{fmt(weight_diff, 3)}</b></td>
      <td colspan="2" class="muted">Should be 0.000 after reconciliation</td>
    </tr>
  </table>

  <!-- 5) Duty & VAT -->
  <div class="ed01-section-title">5) ค่าภาษี (Duty & VAT Summary)</div>
  <table class="ed01-table">
    <tr>
      <th>รายการ</th>
      <th class="nowrap">จำนวนเงิน ({currency})</th>
      <th class="nowrap">อัตรา</th>
    </tr>
    <tr>
      <td>มูลค่าศุลกากร (Customs Value)</td>
      <td>{fmt(customs_value)} {currency}</td>
      <td>-</td>
    </tr>
    <tr>
      <td>อากรขาเข้า (Import Duty)</td>
      <td>{fmt(duty_amount)} {currency}</td>
      <td>{duty_rate*100:.1f}%</td>
    </tr>
    <tr>
      <td>ภาษีมูลค่าเพิ่ม (VAT)</td>
      <td>{fmt(vat_amount)} {currency}</td>
      <td>{vat_rate*100:.1f}%</td>
    </tr>
    <tr>
      <td><b>ภาษีรวมทั้งสิ้น (Total Taxes)</b></td>
      <td><b>{fmt(total_taxes)} {currency}</b></td>
      <td>-</td>
    </tr>
  </table>

  <!-- 5b) Weight Allocation (Audit view) -->
  <div class="ed01-section-title">5b) การจัดสรรน้ำหนัก (Weight Allocation — Audit View)</div>
  <table class="ed01-table">
    <tr>
      <th>ลำดับ</th>
      <th>รหัสสินค้า (Part ID)</th>
      <th>HS Code</th>
      <th>ปริมาณ</th>
      <th class="nowrap">น้ำหนักจัดสรร (kg)</th>
    </tr>
    {weight_rows_html}
    <tr>
      <td colspan="4" class="right"><b>Declared Weight (รวม)</b></td>
      <td><b>{fmt(declared_weight, 3)}</b></td>
    </tr>
    <tr>
      <td colspan="4" class="right"><b>Allocated Weight (รวม)</b></td>
      <td><b>{fmt(allocated_weight, 3)}</b></td>
    </tr>
    <tr>
      <td colspan="4" class="right"><b>Difference</b></td>
      <td><b>{fmt(weight_diff, 3)}</b></td>
    </tr>
  </table>

  <!-- 6) Thai explanatory text -->
  <div class="ed01-section-title">6) หมายเหตุ / ข้อความประกอบการสำแดง</div>
  <div style="font-size:11px;white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;padding:10px 12px;border-radius:6px;">
    {thai_text}
  </div>

  <button class="ed01-print-btn" onclick="window.print()">ดาวน์โหลดเป็น PDF (Print / Save as PDF)</button>

  <div class="ed01-footer-note">
    * เอกสารนี้เป็นฉบับร่างจากระบบอัตโนมัติ ใช้เพื่อการสาธิตเท่านั้น ไม่สามารถนำไปยื่นต่อกรมศุลกากรได้จริง
  </div>

</div>
"""
    return html
