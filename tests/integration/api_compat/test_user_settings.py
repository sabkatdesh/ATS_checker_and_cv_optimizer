from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A


def test_get_settings_none_is_empty_dict(client):
    r = client.get("/settings", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"settings": {}}


def test_post_settings_empty_400(client):
    r = client.post("/settings", json={}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": "No settings provided"}


def test_post_settings_saves(client, backend):
    r = client.post("/settings", json={"accent_color": "#112233"}, headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"message": "Settings saved"}
    assert backend.store.settings[USER_A] == {"accent_color": "#112233"}
