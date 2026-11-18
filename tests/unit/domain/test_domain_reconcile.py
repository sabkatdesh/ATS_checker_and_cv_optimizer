import pytest

from app.domain.cv.domain_config import Domain
from app.domain.cv.domain_reconcile import reconcile_domain

G, M, T = Domain.GENERAL, Domain.MEDICAL, Domain.TECH


@pytest.mark.parametrize(
    ("cv", "jd", "want"),
    [(M, G, M), (G, T, T), (G, G, G), (M, T, M)],
)
def test_reconcile_domain(cv, jd, want):
    assert reconcile_domain(cv, jd) is want
