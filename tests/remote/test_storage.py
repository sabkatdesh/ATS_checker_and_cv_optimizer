"""Private buckets: no public URLs, short-lived signed URLs, and no direct client access.

storage.objects has RLS on and no policy for anon/authenticated (0900), so a user's JWT can
neither upload, list nor download anything, under any prefix; only the secret key can.
"""

import time

import httpx
import pytest

from app.domain.common import uuid7
from tests.remote._auth_admin import key_headers
from tests.remote._rest import StorageHttp, listed_names, public_object_url
from tests.remote._seed import BUCKET_TYPES

SIGNED_TTL_S = 5  # the app uses 600 s; short here so expiry is observable
EXPIRY_WAIT_S = 7


NO_CACHE = {"Cache-Control": "no-cache"}


def test_buckets_exist_and_are_private(remote_env, http: httpx.Client) -> None:
    for bucket in BUCKET_TYPES:
        resp = http.get(
            f"{remote_env.base_url}/storage/v1/bucket/{bucket}",
            headers=key_headers(remote_env.secret_key.get_secret_value()),
        )
        assert resp.status_code == 200, bucket
        assert resp.json()["public"] is False, bucket


@pytest.mark.parametrize("bucket", list(BUCKET_TYPES))
def test_bucket_objects_not_public(
    bucket, user_a, blob_storage, cleanup_prefixes, remote_env, http: httpx.Client
) -> None:
    cleanup_prefixes.append(user_a.id)
    ctype, data = BUCKET_TYPES[bucket]
    path = f"{user_a.id}/{uuid7()}/m4test"
    blob_storage.put(bucket, path, data, ctype)
    resp = http.get(public_object_url(remote_env.base_url, bucket, path))
    assert resp.status_code in (400, 401, 403, 404)
    assert data not in resp.content


def test_signed_url_works_then_expires(user_a, blob_storage, cleanup_prefixes, http) -> None:
    cleanup_prefixes.append(user_a.id)
    path = f"{user_a.id}/{uuid7()}/cv.pdf"
    data = BUCKET_TYPES["renders"][1]
    blob_storage.put("renders", path, data, "application/pdf")
    url = blob_storage.signed_url("renders", path, SIGNED_TTL_S)
    # A second object signed now but never fetched before expiry: no CDN copy can exist for
    # its URL, so the late response must come from the origin's token check. (A second URL
    # for the same path could be byte-identical when signed in the same second.)
    unseen_path = f"{path}.copy.pdf"
    blob_storage.put("renders", unseen_path, data, "application/pdf")
    unseen = blob_storage.signed_url("renders", unseen_path, SIGNED_TTL_S)
    first = http.get(url, headers=NO_CACHE)
    assert first.status_code == 200 and first.content == data
    time.sleep(EXPIRY_WAIT_S)
    late = http.get(unseen, headers=NO_CACHE)
    assert late.status_code >= 400 and data not in late.content


def test_user_jwt_cannot_upload_or_list_other_prefix(
    user_a, user_b, blob_storage, storage_http, service_storage: StorageHttp, cleanup_prefixes
) -> None:
    cleanup_prefixes.extend([user_a.id, user_b.id])
    ctype, data = BUCKET_TYPES["renders"]
    b_folder = f"{user_b.id}/{uuid7()}"
    blob_storage.put("renders", f"{b_folder}/cv.pdf", data, ctype)
    as_a: StorageHttp = storage_http(user_a)

    # Upload: refused into B's prefix, and into A's own prefix too (no client policies).
    for folder in (b_folder, f"{user_a.id}/{uuid7()}"):
        resp = as_a.upload("renders", f"{folder}/evil.pdf", data, ctype)
        assert resp.status_code >= 400, folder
        assert "evil.pdf" not in listed_names(service_storage.list("renders", folder))

    # List and download of B's objects: nothing visible.
    assert listed_names(as_a.list("renders", b_folder)) == []
    assert listed_names(as_a.list("renders", user_b.id)) == []
    resp = as_a.download("renders", f"{b_folder}/cv.pdf")
    assert resp.status_code >= 400 and data not in resp.content
    # The object is really there (seen with the secret key).
    assert "cv.pdf" in listed_names(service_storage.list("renders", b_folder))


def test_anon_cannot_list_or_upload(storage_http, user_b, blob_storage, cleanup_prefixes):
    cleanup_prefixes.append(user_b.id)
    ctype, data = BUCKET_TYPES["renders"]
    folder = f"{user_b.id}/{uuid7()}"
    blob_storage.put("renders", f"{folder}/cv.pdf", data, ctype)
    anon: StorageHttp = storage_http(None)
    assert listed_names(anon.list("renders", folder)) == []
    assert anon.upload("renders", f"{folder}/x.pdf", data, ctype).status_code >= 400
