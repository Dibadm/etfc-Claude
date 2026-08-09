from fastapi.testclient import TestClient

from app.main import app


def test_global_rate_limit_allows_normal_usage():
    client = TestClient(app)
    for _ in range(50):
        r = client.get("/status")
        assert r.status_code == 200


def test_global_rate_limit_blocks_after_threshold():
    client = TestClient(app, headers={"X-Forwarded-For": "198.51.100.7"})
    for _ in range(180):
        r = client.get("/status")
        assert r.status_code == 200, r.text

    r = client.get("/status")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_global_rate_limit_is_per_ip():
    client_a = TestClient(app, headers={"X-Forwarded-For": "198.51.100.10"})
    client_b = TestClient(app, headers={"X-Forwarded-For": "198.51.100.11"})

    for _ in range(180):
        client_a.get("/status")

    assert client_a.get("/status").status_code == 429
    # A different IP is completely unaffected by client_a's usage
    assert client_b.get("/status").status_code == 200
