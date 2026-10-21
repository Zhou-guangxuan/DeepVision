"""训练记录 CRUD 测试，对应设计文档阶段一验收标准。"""

from fastapi.testclient import TestClient

SAMPLE_RECORD = {
    "task_id": "task-001",
    "model_config": {
        "version": 1,
        "nodes": [
            {"id": "n1", "type": "input", "params": {"features": 8}},
            {
                "id": "n2",
                "type": "hidden",
                "params": {"units": 128, "activation": "relu"},
            },
            {
                "id": "n3",
                "type": "output",
                "params": {"units": 2, "task": "classification"},
            },
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
        ],
    },
    "hyperparameters": {"epochs": 50, "batch_size": 32, "learning_rate": 0.001},
    "result_metrics": {
        "final_loss": 0.184,
        "final_accuracy": 0.943,
        "duration_sec": 126.4,
    },
    "status": "success",
}


def test_list_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/records")
    assert resp.status_code == 401
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


def test_create_record_with_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/api/records", json=SAMPLE_RECORD, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["task_id"] == "task-001"
    # 对外契约仍使用 model_config（设计文档 §6.3）
    assert "model_config" in body
    assert body["model_config"]["version"] == 1
    assert body["status"] == "success"


def test_list_returns_own_records(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/api/records", json=SAMPLE_RECORD, headers=auth_headers)
    second = dict(SAMPLE_RECORD, task_id="task-002")
    client.post("/api/records", json=second, headers=auth_headers)

    resp = client.get("/api/records", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 2


def test_get_single_record(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/records", json=SAMPLE_RECORD, headers=auth_headers
    ).json()
    resp = client.get(f"/api/records/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_missing_record_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/api/records/999999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "RECORD_NOT_FOUND"


def test_duplicate_task_id_conflicts(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert (
        client.post(
            "/api/records", json=SAMPLE_RECORD, headers=auth_headers
        ).status_code
        == 201
    )
    resp = client.post("/api/records", json=SAMPLE_RECORD, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "TASK_ID_TAKEN"


def test_other_user_cannot_read_record(client: TestClient) -> None:
    alice = {"username": "alice", "password": "Str0ng!pass"}
    bob = {"username": "bob", "password": "Str0ng!pass"}

    for user in (alice, bob):
        client.post("/api/auth/register", json=user)

    alice_headers = {
        "Authorization": "Bearer "
        + client.post("/api/auth/login", json=alice).json()["access_token"]
    }
    bob_headers = {
        "Authorization": "Bearer "
        + client.post("/api/auth/login", json=bob).json()["access_token"]
    }

    created = client.post(
        "/api/records", json=SAMPLE_RECORD, headers=alice_headers
    ).json()

    # Bob 不能读取 Alice 的记录
    resp = client.get(f"/api/records/{created['id']}", headers=bob_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"

    # Bob 的列表里看不到 Alice 的记录
    bob_list = client.get("/api/records", headers=bob_headers).json()
    assert bob_list["total"] == 0

    # Bob 不能删除 Alice 的记录
    assert (
        client.delete(f"/api/records/{created['id']}", headers=bob_headers).status_code
        == 403
    )


def test_delete_own_record(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/records", json=SAMPLE_RECORD, headers=auth_headers
    ).json()

    resp = client.delete(f"/api/records/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204

    assert (
        client.get(f"/api/records/{created['id']}", headers=auth_headers).status_code
        == 404
    )


def test_pagination_bounds(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/records", params={"page": 0}, headers=auth_headers)
    assert resp.status_code == 422

    resp = client.get("/api/records", params={"page_size": 101}, headers=auth_headers)
    assert resp.status_code == 422


def test_invalid_status_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = dict(SAMPLE_RECORD, status="unknown")
    resp = client.post("/api/records", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def _record_with_history(task_id: str, history: list[dict]) -> dict:
    record = dict(SAMPLE_RECORD)
    record["task_id"] = task_id
    record["result_metrics"] = {
        **SAMPLE_RECORD["result_metrics"],
        "history": history,
    }
    return record


def test_record_diagnosis_and_compare(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    history = [
        {
            "epoch": index + 1,
            "train_loss": round(0.9 - 0.05 * index, 4),
            "val_loss": round(0.95 - 0.04 * index, 4),
            "accuracy": 0.5,
        }
        for index in range(10)
    ]

    first = client.post(
        "/api/records",
        json=_record_with_history("task-d1", history),
        headers=auth_headers,
    ).json()
    second = client.post(
        "/api/records",
        json=_record_with_history("task-d2", history),
        headers=auth_headers,
    ).json()

    diagnosis = client.get(
        f"/api/records/{first['id']}/diagnosis", headers=auth_headers
    )
    assert diagnosis.status_code == 200
    body = diagnosis.json()
    assert body["healthy"] is True
    assert body["stats"]["epochs"] == 10

    compare = client.get(
        f"/api/records/compare?ids={first['id']},{second['id']}",
        headers=auth_headers,
    )
    assert compare.status_code == 200
    runs = compare.json()["runs"]
    assert [run["id"] for run in runs] == [first["id"], second["id"]]
    assert runs[0]["history"][0]["epoch"] == 1


def test_compare_requires_two_to_four_ids(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/api/records/compare?ids=1", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_SELECTION"


def test_rerun_requires_dataset(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = dict(SAMPLE_RECORD, task_id="task-r1")
    created = client.post("/api/records", json=payload, headers=auth_headers).json()

    resp = client.post(f"/api/records/{created['id']}/rerun", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "RERUN_UNAVAILABLE"
