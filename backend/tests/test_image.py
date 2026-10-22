"""图像实验线：内置图像数据集与固定 CNN 训练。"""

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


def test_create_image_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    resp = client.post(
        "/api/datasets/image",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    dataset = resp.json()
    assert dataset["kind"] == "image"
    assert dataset["sample_count"] == 200
    assert dataset["feature_count"] == 64
    assert dataset["stats"]["size"] == 8


def test_image_dataset_preview(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    created = client.post(
        "/api/datasets/image",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    ).json()

    resp = client.get(
        f"/api/datasets/{created['id']}/preview",
        params={"count": 4},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["size"] == 8
    assert len(body["samples"]) == 4
    assert len(body["samples"][0]["pixels"]) == 8
    assert len(body["samples"][0]["pixels"][0]) == 8


def test_preview_rejects_tabular_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    csv = "a,b,label\n" + "\n".join(
        f"{index},{index * 2},{index % 2}" for index in range(30)
    )
    uploaded = client.post(
        "/api/datasets",
        files={"file": ("t.csv", csv.encode("utf-8"), "text/csv")},
        data={"feature_columns": '["a","b"]', "target_column": "label"},
        headers=auth_headers,
    ).json()

    resp = client.get(f"/api/datasets/{uploaded['id']}/preview", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "NOT_IMAGE_DATASET"


def test_image_training_runs(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    dataset = client.post(
        "/api/datasets/image",
        params={"samples": 200, "size": 8},
        headers=auth_headers,
    ).json()

    started = client.post(
        "/api/train/image",
        json={
            "dataset_id": dataset["id"],
            "hyperparameters": {"epochs": 2, "batch_size": 16},
        },
        headers=auth_headers,
    )
    assert started.status_code == 202, started.text

    events = _collect(client, started.json()["task_id"], auth_headers)
    assert events[0]["type"] == "started"
    assert events[-1]["type"] == "completed", events[-1]
    assert 0.0 <= events[-1]["final_accuracy"] <= 1.0

    records = client.get("/api/records", headers=auth_headers).json()
    assert records["total"] == 1
    record = records["items"][0]
    assert record["result_metrics"]["epochs"] == 2

    image_eval = record["result_metrics"]["image_eval"]
    assert len(image_eval["confusion"]) == 2
    assert len(image_eval["samples"]) > 0
    assert len(image_eval["samples"][0]["pixels"]) == 8

    detail = client.get(
        f"/api/records/{record['id']}/image-eval", headers=auth_headers
    )
    assert detail.status_code == 200
    assert detail.json()["size"] == 8


def test_image_training_rejects_tabular(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    csv = "a,b,label\n" + "\n".join(
        f"{index},{index * 2},{index % 2}" for index in range(30)
    )
    dataset = client.post(
        "/api/datasets",
        files={"file": ("t.csv", csv.encode("utf-8"), "text/csv")},
        data={"feature_columns": '["a","b"]', "target_column": "label"},
        headers=auth_headers,
    ).json()

    resp = client.post(
        "/api/train/image",
        json={"dataset_id": dataset["id"], "hyperparameters": {"epochs": 1}},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "NOT_IMAGE_DATASET"
