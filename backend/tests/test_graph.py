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


def test_branch_is_valid_and_has_plan(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """分支结构是合法拓扑，应当通过校验并生成执行计划。

    n3 是死分支（输出不影响最终结果），因此只给 warning。
    """
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
    assert body["execution_plan"] is not None
    assert any("不会影响最终结果" in warning for warning in body["warnings"])


def test_merge_plan_concatenates_inputs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """汇合节点：两个隐藏层同时连到输出层，执行计划应按 concat 合并。"""
    payload = _config(
        [
            {"id": "n1", "type": "input", "params": {}},
            {"id": "n2", "type": "hidden", "params": {}},
            {"id": "n3", "type": "hidden", "params": {}},
            {"id": "n4", "type": "output", "params": {}},
        ],
        [
            {"source": "n1", "target": "n2"},
            {"source": "n1", "target": "n3"},
            {"source": "n2", "target": "n4"},
            {"source": "n3", "target": "n4"},
        ],
    )
    body = client.post(
        "/api/graph/validate", json=payload, headers=auth_headers
    ).json()
    assert body["valid"] is True, body["errors"]

    plan = body["execution_plan"]
    assert plan["merge"] == "concat"
    assert plan["order"][0] == "n1"
    assert plan["order"][-1] == "n4"

    steps = {step["node_id"]: step for step in plan["steps"]}
    assert steps["n4"]["inputs"] == ["n2", "n3"]


def test_unreachable_node_rejected(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """无法从输入层到达的节点无法参与计算，应报错。"""
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
    assert body["valid"] is False
    assert any("无法从输入层到达" in error for error in body["errors"])
