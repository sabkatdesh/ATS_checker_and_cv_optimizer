from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A


def test_settings_endpoint_round_trip_via_preferences(client, backend):
    assert client.get("/settings", headers=auth_header()).json() == {"settings": {}}
    client.post("/settings", json={"accent_color": "#112233"}, headers=auth_header())
    client.post("/settings", json={"default_template": "classic"}, headers=auth_header())
    got = client.get("/settings", headers=auth_header()).json()["settings"]
    assert got == {"accent_color": "#112233", "default_template": "classic"}
    assert backend.profiles.prefs[USER_A] == got
