"""Pull the text out of an imported file.

Its own module so that import workers can use it in a separate process without
loading the whole web application.
"""
from __future__ import annotations

import io


def extract(name: str, data: bytes) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(data)).pages)
    return data.decode("utf-8", "ignore")
