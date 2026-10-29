from fastapi.testclient import TestClient

from tests.testing_app import KEY


def test_declared_failures_lock_until_success_clears(sample_client: TestClient) -> None:
    busy = {"amount": "5", "fail_at": "busy"}
    assert sample_client.post("/test/limited-calc", json=busy, headers=KEY).status_code == 503
    assert sample_client.post("/test/limited-calc", json=busy, headers=KEY).status_code == 503
    locked = sample_client.post("/test/limited-calc", json={"amount": "5"}, headers=KEY)
    assert locked.status_code == 429


def test_undeclared_errors_and_success_do_not_count(sample_client: TestClient) -> None:
    busy = {"amount": "5", "fail_at": "busy", "vip": True}
    assert sample_client.post("/test/limited-calc", json=busy, headers=KEY).status_code == 503
    ok = sample_client.post("/test/limited-calc", json={"amount": "5", "vip": True}, headers=KEY)
    assert ok.status_code == 200
    for _ in range(2):
        response = sample_client.post("/test/limited-calc", json=busy, headers=KEY)
        assert response.status_code == 503
    again = sample_client.post("/test/limited-calc", json={"amount": "5", "vip": True}, headers=KEY)
    assert again.status_code == 429
