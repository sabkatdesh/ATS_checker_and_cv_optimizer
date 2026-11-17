from app.domain.jd.schemas import JobDescriptionStructured
from app.pipeline.nodes.jd_extract import jd_extract
from tests.pipeline.helpers import ctx, deps_for, run


def test_jd_extract_puts_jd_text_in_a_data_block():
    jd = JobDescriptionStructured(job_title="Backend Engineer")
    gw, deps = deps_for({"jd_extract": [jd]})
    out = run(jd_extract({"jd_text": "the jd"}, deps=deps, ctx=ctx()))
    assert out == {"jd": jd}
    req = gw.requests[0]
    assert req.step == "jd_extract" and req.output_schema is JobDescriptionStructured
    assert "<job_description>\nthe jd\n</job_description>" in req.messages[0].content
