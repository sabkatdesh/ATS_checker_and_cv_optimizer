"""Which profession domain a run uses when the CV and the job disagree."""

from app.domain.cv.domain_config import Domain


def reconcile_domain(cv_domain: Domain, jd_domain: Domain) -> Domain:
    """The CV domain wins (the candidate knows their profession), then the JD domain."""
    for domain in (cv_domain, jd_domain):
        if domain != Domain.GENERAL:
            return domain
    return Domain.GENERAL
