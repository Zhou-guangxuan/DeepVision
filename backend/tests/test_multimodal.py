"""多模态实验线：图像 + 表格特征融合。"""

from fastapi.testclient import TestClient


def _token(headers: dict[str, str]) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _collect(client: TestClient, task_id: str, headers: dict[str, str]) -> list[dict]:
    events: list[dict] = []
    with client.websocket_connect(f"/ws/train/{task_id}?token={_token(headers)}") as ws:
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] in {"completed", "failed", "stopped"}:
                return events


def test_create_multimodal_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    resp = client.post(
        "/api/datasets/multimodal",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    dataset = resp.json()
    assert dataset["kind"] == "multimodal"
    assert dataset["sample_count"] == 200
    assert dataset["feature_count"] == 64 + 4
    assert dataset["stats"]["tabular_dim"] == 4
    assert len(dataset["stats"]["tabular_features"]) == 4


def test_multimodal_dataset_preview(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    created = client.post(
        "/api/datasets/multimodal",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    ).json()

    resp = client.get(
        f"/api/datasets/{created['id']}/preview/multimodal",
        params={"count": 4},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["size"] == 8
    assert len(body["samples"]) == 4
    assert len(body["samples"][0]["pixels"]) == 8
    assert len(body["samples"][0]["tabular"]) == 4
    assert len(body["feature_names"]) == 4


def test_multimodal_preview_rejects_image_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    image = client.post(
        "/api/datasets/image",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    ).json()

    resp = client.get(
        f"/api/datasets/{image['id']}/preview/multimodal", headers=auth_headers
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "NOT_MULTIMODAL_DATASET"


def test_multimodal_training_runs(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    dataset = client.post(
        "/api/datasets/multimodal",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    ).json()

    started = client.post(
        "/api/train/multimodal",
        json={
            "dataset_id": dataset["id"],
            "hyperparameters": {"epochs": 2, "batch_size": 16},
        },
        headers=auth_headers,
    )
    assert started.status_code == 202, started.text

    events = _collect(client, started.json()["task_id"], auth_headers)
    assert events[0]["type"] == "started"
    assert events[0]["mode"] == "multimodal"
    assert events[-1]["type"] == "completed", events[-1]
    assert 0.0 <= events[-1]["final_accuracy"] <= 1.0

    records = client.get("/api/records", headers=auth_headers).json()
    assert records["total"] == 1
    record = records["items"][0]

    evaluation = record["result_metrics"]["image_eval"]
    assert len(evaluation["confusion"]) == 2
    assert len(evaluation["samples"]) > 0
    assert len(evaluation["samples"][0]["tabular"]) == 4
    assert len(evaluation["feature_names"]) == 4

    detail = client.get(f"/api/records/{record['id']}/image-eval", headers=auth_headers)
    assert detail.status_code == 200
    assert len(detail.json()["samples"][0]["tabular"]) == 4

    rerun = client.post(f"/api/records/{record['id']}/rerun", headers=auth_headers)
    assert rerun.status_code == 202, rerun.text
    assert rerun.json()["total_epochs"] == 2
