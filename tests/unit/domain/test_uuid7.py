import time
import uuid

from app.domain.common import uuid7


def test_uuid7_is_version_7_rfc_variant():
    u = uuid.UUID(uuid7())
    assert u.version == 7
    assert u.variant == uuid.RFC_4122


def test_uuid7_sorts_by_creation_time():
    ids = []
    for _ in range(5):
        ids.append(uuid7())
        time.sleep(0.002)
    assert ids == sorted(ids)
    assert len(set(ids)) == 5


def test_uuid7_embeds_the_millisecond_timestamp():
    before = int(time.time() * 1000)
    ms = uuid.UUID(uuid7()).int >> 80
    after = int(time.time() * 1000)
    assert before <= ms <= after
