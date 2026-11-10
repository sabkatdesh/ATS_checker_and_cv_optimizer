"""Backward-compatibility shim. New code should import from core.parsers.safe_parser."""
from core.parsers.safe_parser import safe_llm_parse, SafeParser

__all__ = ["safe_llm_parse", "SafeParser"]
