"""教学实验室接口与实时通道测试。"""

import json

from fastapi.testclient import TestClient


def _token(headers: dict[str, str]) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def test_lab_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/lab/train", json={"config": {}})
    assert resp.status_code == 401


def test_lab_start_computes_parameter_count(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/lab/train",
        json={"config": {"hidden_layers": [8, 8]}},
        headers=auth_headers,
    )
    assert resp.status_code == 202, resp.text

    body = resp.json()
    assert body["task_id"]
    # 2→8→8→2：24 + 72 + 18 = 114
    assert body["parameter_count"] == 114


def test_lab_streams_epochs_and_visuals(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    started = client.post(
        "/api/lab/train",
        json={
            "config": {
                "hidden_layers": [6, 6],
                "activation": "tanh",
                "epochs": 2,
                "batch_size": 64,
                "learning_rate": 0.05,
            }
        },
        headers=auth_headers,
    )
    task_id = started.json()["task_id"]

    events: list[dict] = []
    with client.websocket_connect(
        f"/ws/lab/{task_id}?token={_token(auth_headers)}"
    ) as ws:
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in {"completed", "failed", "stopped"}:
                break

    types = [event["type"] for event in events]
    assert types[0] == "started"
    assert types.count("epoch") == 2
    assert types[-1] == "completed"

    assert any(event["type"] == "weights" for event in events)
    boundary = next(event for event in events if event["type"] == "boundary")
    assert boundary["size"] == 48
    assert len(boundary["values"]) == 48 * 48

    epoch = next(event for event in events if event["type"] == "epoch")
    assert "train_loss" in epoch
    assert "val_loss" in epoch
    assert "accuracy" in epoch
    assert "grad_norm" in epoch


def test_lab_pause_and_stop(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    started = client.post(
        "/api/lab/train",
        json={"config": {"hidden_layers": [8, 8], "epochs": 100}},
        headers=auth_headers,
    )
    task_id = started.json()["task_id"]

    with client.websocket_connect(
        f"/ws/lab/{task_id}?token={_token(auth_headers)}"
    ) as ws:
        first = ws.receive_json()
        assert first["type"] == "started"

        pause = client.post(f"/api/lab/{task_id}/pause", headers=auth_headers)
        assert pause.status_code == 200
        assert pause.json()["status"] == "paused"

        resume = client.post(f"/api/lab/{task_id}/resume", headers=auth_headers)
        assert resume.status_code == 200

        stop = client.post(f"/api/lab/{task_id}/stop", headers=auth_headers)
        assert stop.status_code == 200

        terminal = None
        while True:
            event = ws.receive_json()
            if event["type"] in {"completed", "failed", "stopped"}:
                terminal = event
                break

    assert terminal is not None
    assert terminal["type"] in {"stopped", "completed"}


def _train(client: TestClient, headers: dict[str, str], epochs: int = 2) -> str:
    started = client.post(
        "/api/lab/train",
        json={
            "config": {
                "hidden_layers": [6, 6],
                "epochs": epochs,
                "batch_size": 64,
            }
        },
        headers=headers,
    )
    task_id = started.json()["task_id"]
    with client.websocket_connect(
        f"/ws/lab/{task_id}?token={_token(headers)}"
    ) as ws:
        while True:
            event = ws.receive_json()
            if event["type"] in {"completed", "failed", "stopped"}:
                return task_id


def test_lab_inspect_attention_and_projection(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    task_id = _train(client, auth_headers)

    inspect = client.get(
        f"/api/lab/{task_id}/inspect?index=0", headers=auth_headers
    )
    assert inspect.status_code == 200, inspect.text
    body = inspect.json()
    # [2, 6, 6, 2]：两个隐藏层 + 一个输出层
    assert len(body["layers"]) == 3
    assert len(body["layers"][0]["activation"]) == 6
    assert len(body["layers"][0]["gradient"]) == 6
    # 输入 2 维 → 2 个注意力（梯度）值
    assert len(body["saliency"]) == 2
    assert len(body["input"]) == 2

    projection = client.get(
        f"/api/lab/{task_id}/projection?layer=0", headers=auth_headers
    )
    assert projection.status_code == 200, projection.text
    data = projection.json()
    assert data["points"]
    assert len(data["explained"]) == 2
    assert data["layer_count"] == 3

    # 训练记录落库，来源标记为 lab
    records = client.get("/api/records", headers=auth_headers).json()
    assert records["total"] == 1
    assert records["items"][0]["source"] == "lab"


def test_lab_inspect_requires_training(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    started = client.post(
        "/api/lab/train",
        json={"config": {"hidden_layers": [4], "epochs": 1}},
        headers=auth_headers,
    )
    task_id = started.json()["task_id"]

    resp = client.get(f"/api/lab/{task_id}/inspect", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "LAB_NOT_READY"
