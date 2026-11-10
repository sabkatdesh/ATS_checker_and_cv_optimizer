"""
Thin compatibility shim — delegates to core.pipeline.graph.

api.py imports run_pipeline_for_user, get_pipeline_state, resume_pipeline_for_user
from this module. This shim keeps that interface stable while all the real
pipeline logic now lives in core/pipeline/.
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from dotenv import load_dotenv
load_dotenv()

from core.pipeline.graph import (  # noqa: F401  (re-exported for api.py)
    run_pipeline_for_user,
    get_pipeline_state,
    resume_pipeline_for_user,
)
