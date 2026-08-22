"""Arabic document PII anonymization pipeline.

Pipeline: PDF/DOCX -> (vision OCR or local text) -> LLM PII detection + chamber
classification -> local redaction -> RTL Arabic .docx + index.csv.
See README.md for the architecture overview.
"""
from .config import Settings
from .pipeline import Pipeline, RunOptions

__version__ = "1.0.0"
__all__ = ["Settings", "Pipeline", "RunOptions", "__version__"]
