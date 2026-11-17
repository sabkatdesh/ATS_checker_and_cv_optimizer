from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.pipeline.nodes.cv_extract import cv_extract
from tests.pipeline.helpers import ctx, deps_for, persona_cv, run


def test_cv_extract_returns_source_cv_and_passes_domain():
    cv = persona_cv()
    gw, deps = deps_for({"cv_extract": [cv]})
    state = {"cv_text": "my cv", "jd": JobDescriptionStructured(domain="medical")}
    out = run(cv_extract(state, deps=deps, ctx=ctx()))
    assert out == {"source_cv": cv}
    req = gw.requests[0]
    assert req.output_schema is UniversalCVStructured
    content = req.messages[0].content
    assert "<cv>\nmy cv\n</cv>" in content and "medical professional" in content
