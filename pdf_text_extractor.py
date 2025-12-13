# pdf_text_extractor.py
from __future__ import annotations

from typing import Optional, Union
import fitz  # PyMuPDF


def extract_text_from_pdf(file: Union[str, bytes, bytearray, None]) -> Optional[str]:
    """
    Robust extractor for Gradio uploads.

    Supports:
      - filepath (recommended): str
      - raw bytes: bytes / bytearray

    Returns:
      - extracted text (str) or None if empty / failed
    """
    if not file:
        print("[PDF] No file provided")
        return None

    try:
        # Preferred path: filepath string
        if isinstance(file, str):
            print(f"[PDF] Reading from filepath: {file}")
            doc = fitz.open(file)
        elif isinstance(file, (bytes, bytearray)):
            print("[PDF] Reading from bytes")
            doc = fitz.open(stream=bytes(file), filetype="pdf")
        else:
            print(f"[PDF] Unsupported type: {type(file)}")
            return None

        text_chunks = []
        for i in range(len(doc)):
            page = doc.load_page(i)
            page_text = page.get_text() or ""
            print(f"[PDF] Page {i+1}: {len(page_text)} chars")
            text_chunks.append(page_text)

        text = "\n".join(text_chunks).strip()
        if not text:
            print("[PDF WARNING] No text extracted (maybe scanned PDF)")
            return None

        return text

    except Exception as e:
        print("[PDF ERROR]", repr(e))
        return None
