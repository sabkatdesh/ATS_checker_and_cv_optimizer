from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A


def test_get_profile_returns_saved_profile(client, backend):
    backend.store.profiles[USER_A] = {"user_id": USER_A, "full_name": "Test Person"}
    r = client.get("/profile", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"profile": {"user_id": USER_A, "full_name": "Test Person"}}


def test_get_profile_missing_is_none(client):
    r = client.get("/profile", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"profile": None}


def test_save_profile_empty_body_400(client):
    r = client.post("/profile", json={}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": "No data provided"}


def test_save_profile_drops_none_fields(client, backend):
    r = client.post("/profile", json={"full_name": "A", "email": None}, headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"message": "Profile saved successfully"}
    assert backend.store.profiles[USER_A] == {"full_name": "A", "user_id": USER_A}
