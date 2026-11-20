from tests.fakes.backend import auth_header


def test_unhandled_store_error_is_constant_500(client, backend):
    backend.sessions.raise_on["list_for_user"] = RuntimeError("db down")
    r = client.get("/sessions", headers=auth_header())
    assert r.status_code == 500
    assert r.json()["code"] == "INTERNAL_ERROR"
    assert "db down" not in r.text
