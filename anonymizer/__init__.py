"""Arabic scanned-PDF PII anonymization pipeline.

Pipeline: scanned PDF -> vision LLM (OCR + PII detection) -> local redaction
-> RTL Arabic .docx. See README.md for the architecture overview.
"""

__version__ = "1.0.0"
