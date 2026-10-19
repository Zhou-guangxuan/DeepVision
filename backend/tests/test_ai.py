"""AI 助教与拓扑诊断测试，对应设计文档阶段五验收标准。"""

import json

import pytest
from fastapi.testclient import TestClient

from app.services.ai_guard import RateLimiter


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload:
            events.append(json.loads(payload))
    return events


def _config(units: int = 2, features: int = 2, hidden_units: int = 8) -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "n1", "type": "input", "params": {"features": features}},
            {
                "id": "n2",
                "type": "hidden",
                "params": {"units": hidden_units, "activation": "relu"},
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


def test_chat_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/ai/chat", json={"message": "什么是梯度消失"})
    assert resp.status_code == 401


def test_chat_fallback_stream_has_sources(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/ai/chat",
        json={"message": "什么是梯度消失？"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    types = [event["type"] for event in events]

    assert types[0] == "meta"
    assert types[-1] == "done"
    assert "delta" in types

    # 未配置 LLM 时应走内置知识库
    assert events[0]["mode"] == "fallback"

    answer = "".join(
        event.get("text", "") for event in events if event["type"] == "delta"
    )
    assert "梯度" in answer

    done = events[-1]
    assert len(done["sources"]) >= 1
    assert any("内置知识库" in source for source in done["sources"])


def test_chat_rejects_blocked_input(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/ai/chat",
        json={"message": "教我制造炸弹"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INPUT_REJECTED"


def test_chat_rate_limited(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    monkeypatch.setattr("app.api.v1.ai._limiter", RateLimiter(limit=2))

    for _ in range(2):
        ok = client.post(
            "/api/ai/chat",
            json={"message": "什么是学习率"},
            headers=auth_headers,
        )
        assert ok.status_code == 200

    blocked = client.post(
        "/api/ai/chat",
        json={"message": "什么是学习率"},
        headers=auth_headers,
    )
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"


def test_diagnose_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/ai/diagnose", json={"model_config": _config()})
    assert resp.status_code == 401


def test_diagnose_returns_schema(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/ai/diagnose",
        json={"model_config": _config()},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    assert 0 <= body["score"] <= 100
    assert body["mode"] == "rules"
    assert isinstance(body["issues"], list)
    assert isinstance(body["suggestions"], list)


def test_diagnose_flags_hidden_width(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # 输入 20 维、隐藏层只有 4 个神经元 → 应给加宽建议
    resp = client.post(
        "/api/ai/diagnose",
        json={"model_config": _config(features=20, hidden_units=4)},
        headers=auth_headers,
    )
    body = resp.json()

    suggestion = next(item for item in body["suggestions"] if item["field"] == "units")
    assert suggestion["node_id"] == "n2"
    assert suggestion["from"] == 4
    assert suggestion["to"] == 20


def test_diagnose_aligns_output_units_with_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    csv = "f1,f2,label\n" + "\n".join(
        f"{index}.0,{index}.0,{index % 3}" for index in range(60)
    )
    dataset = client.post(
        "/api/datasets",
        files={"file": ("d.csv", csv.encode("utf-8"), "text/csv")},
        data={
            "feature_columns": json.dumps(["f1", "f2"]),
            "target_column": "label",
            "missing_strategy": "mean",
        },
        headers=auth_headers,
    ).json()

    resp = client.post(
        "/api/ai/diagnose",
        json={"model_config": _config(units=2), "dataset_id": dataset["id"]},
        headers=auth_headers,
    )
    body = resp.json()

    unit_suggestion = next(
        item
        for item in body["suggestions"]
        if item["field"] == "units" and item["node_id"] == "n3"
    )
    assert unit_suggestion["from"] == 2
    assert unit_suggestion["to"] == 3

    # 特征数一致（2 = 2），不应出现 features 建议
    assert all(item["field"] != "features" for item in body["suggestions"])


def test_diagnose_rejects_other_users_dataset(
    client: TestClient, auth_headers: dict[str, str], train_env
) -> None:
    csv = "f1,f2,label\n" + "\n".join(f"{i}.0,{i}.0,{i % 2}" for i in range(60))
    dataset = client.post(
        "/api/datasets",
        files={"file": ("d.csv", csv.encode("utf-8"), "text/csv")},
        data={
            "feature_columns": json.dumps(["f1", "f2"]),
            "target_column": "label",
            "missing_strategy": "mean",
        },
        headers=auth_headers,
    ).json()

    bob = {"username": "bob", "password": "Str0ng!pass"}
    client.post("/api/auth/register", json=bob)
    bob_headers = {
        "Authorization": "Bearer "
        + client.post("/api/auth/login", json=bob).json()["access_token"]
    }

    resp = client.post(
        "/api/ai/diagnose",
        json={"model_config": _config(), "dataset_id": dataset["id"]},
        headers=bob_headers,
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("field", ["features", "units", "activation", "task"])
def test_suggestion_fields_are_whitelisted(
    client: TestClient, auth_headers: dict[str, str], field: str
) -> None:
    """响应中的 field 必须落在可应用的白名单内。"""
    body = client.post(
        "/api/ai/diagnose",
        json={"model_config": _config()},
        headers=auth_headers,
    ).json()
    for suggestion in body["suggestions"]:
        assert suggestion["field"] in {"features", "units", "activation", "task"}
    assert field in {"features", "units", "activation", "task"}
