"""工作台草稿接口测试。"""

from fastapi.testclient import TestClient


def test_draft_requires_auth(client: TestClient) -> None:
    assert client.get("/api/workspace/draft").status_code == 401
    assert client.put("/api/workspace/draft", json={}).status_code == 401


def test_draft_roundtrip(client: TestClient, auth_headers: dict[str, str]) -> None:
    empty = client.get("/api/workspace/draft", headers=auth_headers)
    assert empty.status_code == 200
    assert empty.json()["graph"] is None

    payload = {
        "nodes": [
            {"id": "n1", "type": "input", "params": {"features": 2}},
            {"id": "n2", "type": "output", "params": {"units": 2}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        "saved_at": "2026-10-22T00:00:00Z",
    }
    saved = client.put("/api/workspace/draft", json=payload, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["graph"]["nodes"][0]["id"] == "n1"

    loaded = client.get("/api/workspace/draft", headers=auth_headers)
    body = loaded.json()
    assert body["graph"]["edges"][0]["source"] == "n1"
    assert body["updated_at"] is not None


def test_draft_is_per_user(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.put(
        "/api/workspace/draft",
        json={"nodes": [{"id": "n1"}], "edges": []},
        headers=auth_headers,
    )

    other_payload = {"username": "draft-user", "password": "Str0ng!pass"}
    client.post("/api/auth/register", json=other_payload)
    other_token = client.post("/api/auth/login", json=other_payload).json()[
        "access_token"
    ]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    other = client.get("/api/workspace/draft", headers=other_headers)
    assert other.status_code == 200
    assert other.json()["graph"] is None
