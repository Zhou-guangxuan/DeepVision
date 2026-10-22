"""教学实验室接口与实时通道测试。"""

import time

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
    assert len(boundary["classes"]) == 48 * 48
    assert len(boundary["confidence"]) == 48 * 48
    assert set(boundary["classes"]) <= {0, 1}

    epoch = next(event for event in events if event["type"] == "epoch")
    assert "train_loss" in epoch
    assert "val_loss" in epoch
    assert "accuracy" in epoch
    assert "grad_norm" in epoch
    # 逐 epoch 的输入注意力（输入 2 维）
    assert len(epoch["attention"]) == 2


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
    with client.websocket_connect(f"/ws/lab/{task_id}?token={_token(headers)}") as ws:
        while True:
            event = ws.receive_json()
            if event["type"] in {"completed", "failed", "stopped"}:
                return task_id


def test_lab_inspect_attention_and_projection(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    task_id = _train(client, auth_headers)

    inspect = client.get(f"/api/lab/{task_id}/inspect?index=0", headers=auth_headers)
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
    assert data["method"] == "pca"
    assert data["points"]
    assert len(data["explained"]) == 2
    assert data["layer_count"] == 3

    # 训练记录落库，来源标记为 lab
    records = client.get("/api/records", headers=auth_headers).json()
    assert records["total"] == 1
    assert records["items"][0]["source"] == "lab"


def test_lab_attention_history_and_tsne(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    task_id = _train(client, auth_headers, epochs=3)

    history = client.get(f"/api/lab/{task_id}/attention", headers=auth_headers)
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["epochs"] == [1, 2, 3]
    assert len(body["series"]) == 2
    assert all(len(item["values"]) == 3 for item in body["series"])

    tsne = client.get(
        f"/api/lab/{task_id}/projection?layer=0&method=tsne", headers=auth_headers
    )
    assert tsne.status_code == 200, tsne.text
    mapped = tsne.json()
    assert mapped["method"] == "tsne"
    assert mapped["explained"] == []
    assert len(mapped["points"]) > 0


def test_lab_custom_input_and_output_units(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    """输入神经元数与输出类别数可调：4 → 6 → 3。"""
    started = client.post(
        "/api/lab/train",
        json={
            "config": {
                "input_units": 4,
                "output_units": 3,
                "hidden_layers": [6],
                "epochs": 2,
                "batch_size": 64,
            }
        },
        headers=auth_headers,
    )
    assert started.status_code == 202, started.text
    # 4×6+6 + 6×3+3 = 51
    assert started.json()["parameter_count"] == 51
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

    started_event = events[0]
    assert started_event["input_units"] == 4
    assert started_event["output_units"] == 3
    assert events[-1]["type"] == "completed", events[-1]

    boundary = next(event for event in events if event["type"] == "boundary")
    assert set(boundary["classes"]) <= {0, 1, 2}
    assert {point["label"] for point in boundary["points"]} <= {0, 1, 2}

    # 注意力维度跟随输入神经元数
    epoch = next(event for event in events if event["type"] == "epoch")
    assert len(epoch["attention"]) == 4


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


def test_lab_curve_diagnosis(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    """教学任务的曲线诊断复用记录级规则引擎。"""
    task_id = _train(client, auth_headers, epochs=8)

    resp = client.get(f"/api/lab/{task_id}/diagnosis", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stats"]["epochs"] == 8
    assert isinstance(body["issues"], list)
    assert body["summary"]


def test_lab_auto_tuning(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    """自动调参：2 次试验跑完后给出最佳配置。"""
    started = client.post(
        "/api/lab/tune",
        json={"config": {"hidden_layers": [8]}, "trials": 2, "epochs": 2},
        headers=auth_headers,
    )
    assert started.status_code == 200, started.text
    tune_id = started.json()["tune_id"]
    assert started.json()["total"] == 2

    state = started.json()
    deadline = time.time() + 60
    while time.time() < deadline:
        state = client.get(f"/api/lab/tune/{tune_id}", headers=auth_headers).json()
        if state["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert state["status"] == "completed", state
    assert len(state["trials"]) == 2
    assert state["best"] is not None
    assert 0.0 <= state["best"]["accuracy"] <= 1.0
    assert state["best"]["learning_rate"] > 0


def test_tune_not_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/lab/tune/not-exist", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["code"] == "TUNE_NOT_FOUND"


def test_lab_compression(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    """剪枝后非零参数减少；量化后体积变小；三种方案准确率都在 [0,1]。"""
    task_id = _train(client, auth_headers, epochs=8)

    resp = client.get(
        f"/api/lab/{task_id}/compression",
        params={"sparsity": 0.4},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    baseline = body["baseline"]
    pruned = body["pruned"]
    quantized = body["quantized"]

    assert baseline["params"] > 0
    assert pruned["nonzero"] < baseline["params"]
    assert pruned["sparsity"] == 0.4
    # 权重本身：int8 应小于 float32（序列化体积可能被元数据反超）
    assert quantized["weight_bytes"] < baseline["weight_bytes"]
    assert quantized["compression_ratio"] > 1

    for item in (baseline, pruned, quantized):
        assert 0.0 <= item["accuracy"] <= 1.0


def test_lab_snapshot_replay(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    """快照回放：列出快照并恢复任意 epoch 的决策边界。"""
    task_id = _train(client, auth_headers, epochs=8)

    listed = client.get(f"/api/lab/{task_id}/snapshots", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    snapshots = listed.json()["snapshots"]
    assert len(snapshots) >= 3
    assert snapshots[0]["epoch"] == 1

    epoch = snapshots[1]["epoch"]
    detail = client.get(
        f"/api/lab/{task_id}/snapshot",
        params={"epoch": epoch},
        headers=auth_headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["epoch"] == epoch
    assert 0.0 <= body["accuracy"] <= 1.0
    assert len(body["boundary"]["classes"]) > 0


def test_lab_snapshot_missing_epoch(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    task_id = _train(client, auth_headers, epochs=4)

    resp = client.get(
        f"/api/lab/{task_id}/snapshot",
        params={"epoch": 999},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "LAB_SNAPSHOT_FAILED"
