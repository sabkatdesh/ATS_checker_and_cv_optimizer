def test_root_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "CV Optimizer API is running"}


def test_templates_needs_no_auth(client, backend):
    backend.store.templates = [{"id": "classic"}]
    r = client.get("/templates")
    assert r.status_code == 200
    assert r.json() == {"templates": [{"id": "classic"}]}
