"""Pluggable LLM providers for OCR + PII detection.

`base.py` defines the provider-agnostic interface; concrete providers live in
sibling modules and are selected by `factory.get_provider`.
"""
