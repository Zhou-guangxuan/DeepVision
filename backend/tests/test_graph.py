"""拓扑校验接口测试，对应设计文档阶段二验收标准。"""

from fastapi.testclient import TestClient


def _config(nodes: list[dict], edges: list[dict]) -> dict:
    return {"version": 1, "nodes": nodes, "edges": edges}


CHAIN = _config(
    [
        {"id": "n1", "type": "input", "params": {"features": 8}},
        {"id": "n2", "type": "hidden", "params": {"units": 128, "activation": "relu"}},
        {"id": "n3", "type": "hidden", "params": {"units": 64, "activation": "relu"}},
        {"id": "n4", "type": "output", "params": {"units": 2, "task": "classification"}},
    ],
    [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3"},
        {"source": "n3", "target": "n4"},
    ],
)


def test_validate_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/graph/validate", json=CHAIN)
    assert resp.status_code == 401
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


def test_valid_chain_accepted(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post("/api/graph/validate", json=CHAIN, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["warnings"] == []


def test_empty_graph_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.post(
        "/api/graph/validate", json=_config([], []), headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_cycle_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "hidden", "params": {}},
            {"id": "n3", "type": "output", "params": {}},
        ],
        [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n3", "target": "n2"},
        ],
    )
    resp = client.post("/api/graph/validate", json=payload, headers=auth_headers)
    body = resp.json()
    assert body["valid"] is False
    assert any("环" in error for error in body["errors"])


def test_self_loop_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "output", "params": {}},
        ],
        [{"source": "n1", "target": "n1"}, {"source": "n1", "target": "n2"}],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is False
    assert any("自身" in error for error in body["errors"])


def test_duplicate_edge_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "output", "params": {}},
        ],
        [
            {"source": "n1", "target": "n2"},
            {"source": "n1", "target": "n2"},
        ],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is False
    assert any("重复连线" in error for error in body["errors"])


def test_missing_input_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = _config(
        [{"id": "n1", "type": "output", "params": {}}],
        [],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is False
    assert any("输入层" in error for error in body["errors"])


def test_unknown_node_reference_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "output", "params": {}},
        ],
        [{"source": "n1", "target": "ghost"}],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is False
    assert any("不存在" in error for error in body["errors"])


def test_branch_reported_as_warning(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """分支结构合法（DAG），但当前 MLP 训练器不支持，应给 warning 而非 error。"""
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "hidden", "params": {}},
            {"id": "n3", "type": "hidden", "params": {}},
            {"id": "n4", "type": "output", "params": {}},
        ],
        [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n2", "target": "n4"},
        ],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is True
    assert any("分支" in warning for warning in body["warnings"])


def test_disconnected_node_reported_as_warning(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "output", "params": {}},
            {"id": "n3", "type": "hidden", "params": {}},
        ],
        [{"source": "n1", "target": "n2"}],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is True
    assert any("未连接" in warning for warning in body["warnings"])
