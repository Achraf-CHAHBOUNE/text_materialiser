"""Provider-agnostic interface for the OCR + PII-detection step.

Any provider (cloud vision LLM, or a hybrid self-hosted OCR + PII detector)
implements `DocumentAI.process` and returns a `BatchResult`. Swapping providers
therefore touches only the factory + .env, never the pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class PIIEntity:
    text: str   # verbatim value as it appears in the OCR text
    type: str   # name | address | national_id | passport | phone | email | dob | other


@dataclass
class BatchResult:
    """Result of processing one page-batch."""
    pages: List[str] = field(default_factory=list)        # OCR text, one entry per page (in order)
    pii: List[PIIEntity] = field(default_factory=list)     # PII detected anywhere in the batch
    court: str = ""                                        # blue-header court (context)
    category: str = ""                                     # black-text chamber (the classification)
    input_tokens: int = 0
    output_tokens: int = 0


class DocumentAI(ABC):
    """Detects PII + classifies a document. No replacement happens here.

    Two entry points so we only pay for OCR when the input is actually a scan:
      - process_pdf:  scanned PDF bytes -> OCR text + PII + category
      - process_text: already-extracted text -> PII + category only (pages empty)
    """

    @abstractmethod
    def process_pdf(self, pdf_bytes: bytes) -> BatchResult:
        ...

    @abstractmethod
    def process_text(self, text: str) -> BatchResult:
        ...
