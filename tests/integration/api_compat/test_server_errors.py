from tests.fakes.backend import auth_header


def test_unhandled_store_error_is_plain_500(client, backend):
    backend.store.raise_on["get_user_sessions"] = RuntimeError("db down")
    r = client.get("/sessions", headers=auth_header())
    assert r.status_code == 500
    assert r.text == "Internal Server Error"
    assert "db down" not in r.text
