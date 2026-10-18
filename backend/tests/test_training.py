"""训练接口与 WebSocket 端到端测试，对应设计文档阶段四验收标准。"""

import json

from fastapi.testclient import TestClient


def _csv_bytes(rows: int) -> bytes:
    lines = ["f1,f2,label"]
    for index in range(rows):
        lines.append(f"{index}.0,{(index * 2) % 10}.0,{index % 2}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _upload(client: TestClient, headers: dict[str, str], rows: int = 60):
    return client.post(
        "/api/datasets",
        files={"file": ("d.csv", _csv_bytes(rows), "text/csv")},
        data={
            "feature_columns": json.dumps(["f1", "f2"]),
            "target_column": "label",
            "missing_strategy": "mean",
        },
        headers=headers,
    )


def _config(features: int = 2, units: int = 2) -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "n1", "type": "input", "params": {"features": features}},
            {
                "id": "n2",
                "type": "hidden",
                "params": {"units": 8, "activation": "relu"},
            },
            {
                "id": "n3",
                "type": "output",
                "params": {"units": units, "task": "classification"},
            },
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
        ],
    }


def _token(headers: dict[str, str]) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def test_train_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/train", json={})
    assert resp.status_code == 401
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


def test_rejects_invalid_config(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    dataset = _upload(client, auth_headers).json()

    broken = _config()
    broken["edges"].append({"source": "n3", "target": "n2"})

    resp = client.post(
        "/api/train",
        json={"dataset_id": dataset["id"], "model_config": broken},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_MODEL_CONFIG"


def test_rejects_missing_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    resp = client.post(
        "/api/train",
        json={"dataset_id": 99999, "model_config": _config()},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "DATASET_NOT_FOUND"


def test_other_user_cannot_train(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    dataset = _upload(client, auth_headers).json()

    bob = {"username": "bob", "password": "Str0ng!pass"}
    client.post("/api/auth/register", json=bob)
    bob_headers = {
        "Authorization": "Bearer "
        + client.post("/api/auth/login", json=bob).json()["access_token"]
    }

    resp = client.post(
        "/api/train",
        json={"dataset_id": dataset["id"], "model_config": _config()},
        headers=bob_headers,
    )
    assert resp.status_code == 403


def test_training_completes_and_saves_record(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    dataset = _upload(client, auth_headers).json()

    started = client.post(
        "/api/train",
        json={
            "dataset_id": dataset["id"],
            "model_config": _config(),
            "hyperparameters": {"epochs": 3, "batch_size": 8, "learning_rate": 0.01},
        },
        headers=auth_headers,
    )
    assert started.status_code == 202, started.text
    task_id = started.json()["task_id"]
    assert started.json()["total_epochs"] == 3

    events: list[dict] = []
    with client.websocket_connect(
        f"/ws/train/{task_id}?token={_token(auth_headers)}"
    ) as ws:
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in {"completed", "failed", "stopped"}:
                break

    types = [event["type"] for event in events]
    assert types[0] == "started"
    assert types.count("epoch") == 3
    assert types[-1] == "completed"

    final = events[-1]
    assert final["final_loss"] is not None
    assert final["final_accuracy"] is not None
    assert final["record_id"] is not None

    # 逐层统计用于顶栏的「权重 / 梯度 / 激活」视图
    epoch_event = next(event for event in events if event["type"] == "epoch")
    layer_stats = epoch_event["layer_stats"]
    assert {item["node_id"] for item in layer_stats} == {"n2", "n3"}
    for item in layer_stats:
        assert item["weight_norm"] > 0
        assert item["activation_mean"] >= 0

    records = client.get("/api/records", headers=auth_headers).json()
    assert records["total"] == 1
    record = records["items"][0]
    assert record["status"] == "success"
    assert record["task_id"] == task_id
    assert record["result_metrics"]["epochs"] == 3
    assert len(record["result_metrics"]["layer_stats"]) == 2


def test_stop_training(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    dataset = _upload(client, auth_headers, rows=300).json()

    started = client.post(
        "/api/train",
        json={
            "dataset_id": dataset["id"],
            "model_config": _config(),
            "hyperparameters": {"epochs": 100, "batch_size": 4},
        },
        headers=auth_headers,
    )
    task_id = started.json()["task_id"]

    with client.websocket_connect(
        f"/ws/train/{task_id}?token={_token(auth_headers)}"
    ) as ws:
        first = ws.receive_json()
        assert first["type"] == "started"

        stop = client.post(f"/api/train/{task_id}/stop", headers=auth_headers)
        assert stop.status_code == 200
        assert stop.json()["stopped"] is True

        terminal = None
        while True:
            event = ws.receive_json()
            if event["type"] in {"completed", "failed", "stopped"}:
                terminal = event
                break

    assert terminal is not None
    assert terminal["type"] in {"stopped", "completed"}

    records = client.get("/api/records", headers=auth_headers).json()
    assert records["total"] == 1
    assert records["items"][0]["status"] in {"interrupted", "success"}


def test_train_with_merge_topology(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    """含分支 / 汇合的拓扑也能训练，汇合按 concat 拼接。"""
    dataset = _upload(client, auth_headers).json()

    config = {
        "version": 1,
        "nodes": [
            {"id": "n1", "type": "input", "params": {"features": 2}},
            {"id": "a", "type": "hidden", "params": {"units": 4, "activation": "relu"}},
            {"id": "b", "type": "hidden", "params": {"units": 3, "activation": "tanh"}},
            {"id": "o", "type": "output", "params": {"units": 2, "task": "classification"}},
        ],
        "edges": [
            {"source": "n1", "target": "a"},
            {"source": "n1", "target": "b"},
            {"source": "a", "target": "o"},
            {"source": "b", "target": "o"},
        ],
    }

    started = client.post(
        "/api/train",
        json={
            "dataset_id": dataset["id"],
            "model_config": config,
            "hyperparameters": {"epochs": 2, "batch_size": 16},
        },
        headers=auth_headers,
    )
    assert started.status_code == 202, started.text
    task_id = started.json()["task_id"]

    with client.websocket_connect(
        f"/ws/train/{task_id}?token={_token(auth_headers)}"
    ) as ws:
        while True:
            event = ws.receive_json()
            if event["type"] in {"completed", "failed", "stopped"}:
                break

    assert event["type"] == "completed"
