"""Backward-compatibility shim. New code should import from core.ats.ats_checker."""
from core.ats.ats_checker import compute_final_match, ATSChecker

__all__ = ["compute_final_match", "ATSChecker"]
