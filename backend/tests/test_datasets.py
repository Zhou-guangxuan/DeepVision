"""数据集上传与预处理测试，对应设计文档阶段三验收标准。"""

import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings

CSV = b"f1,f2,label\n1.0,2.0,0\n2.0,4.0,0\n3.0,6.0,1\n4.0,8.0,1\n"

CSV_WITH_MISSING = b"f1,f2,label\n1.0,2.0,0\n,4.0,0\n3.0,,1\n4.0,8.0,1\n"


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    """把数据集存储目录指向临时目录，避免污染仓库。"""
    settings = Settings(storage_dir=str(tmp_path / "storage"))
    monkeypatch.setattr("app.api.v1.datasets.get_settings", lambda: settings)
    return settings


def _upload(
    client: TestClient,
    headers: dict[str, str],
    raw: bytes,
    *,
    filename: str = "data.csv",
    features: list[str] | None = None,
    target: str = "label",
    strategy: str = "mean",
):
    return client.post(
        "/api/datasets",
        files={"file": (filename, raw, "text/csv")},
        data={
            "feature_columns": json.dumps(features or ["f1", "f2"]),
            "target_column": target,
            "missing_strategy": strategy,
            "name": filename,
        },
        headers=headers,
    )


def test_upload_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/datasets")
    assert resp.status_code == 401
    assert resp.json()["code"] == "NOT_AUTHENTICATED"


def test_upload_parses_and_returns_meta(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, CSV)
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["sample_count"] == 4
    assert body["feature_count"] == 2
    assert body["target_column"] == "label"
    assert body["missing_strategy"] == "mean"
    assert [column["name"] for column in body["columns_meta"]] == [
        "f1",
        "f2",
        "label",
    ]
    assert body["columns_meta"][0]["dtype"] == "number"


def test_stats_match_pandas(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    body = _upload(client, auth_headers, CSV).json()

    df = pd.read_csv(io.BytesIO(CSV))
    assert body["sample_count"] == len(df)

    f1 = next(item for item in body["stats"]["features"] if item["name"] == "f1")
    assert abs(f1["mean"] - float(df["f1"].mean())) < 1e-6
    assert abs(f1["variance"] - float(df["f1"].var(ddof=1))) < 1e-6

    label = body["stats"]["target"]
    assert abs(label["mean"] - float(df["label"].mean())) < 1e-6
    assert body["stats"]["target_distribution"] == {"0": 2, "1": 2}


def test_drop_strategy_reduces_samples(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, CSV_WITH_MISSING, strategy="drop")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 有缺失的是第 2、3 行，删除后剩 2 行
    assert body["sample_count"] == 2


def test_mean_strategy_keeps_samples(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, CSV_WITH_MISSING, strategy="mean")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["sample_count"] == 4

    # 填充后 f1 的均值应为 (1+2.6667+3+4)/4
    df = pd.read_csv(io.BytesIO(CSV_WITH_MISSING))
    filled = df["f1"].fillna(df["f1"].mean())
    f1 = next(item for item in body["stats"]["features"] if item["name"] == "f1")
    assert abs(f1["mean"] - float(filled.mean())) < 1e-6


def test_rejects_non_csv(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, CSV, filename="data.txt")
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_rejects_empty_file(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, b"")
    assert resp.status_code == 400
    assert resp.json()["code"] == "EMPTY_FILE"


def test_rejects_too_large(
    client: TestClient, auth_headers: dict[str, str], tmp_path, monkeypatch
) -> None:
    settings = Settings(storage_dir=str(tmp_path / "storage"), max_upload_bytes=10)
    monkeypatch.setattr("app.api.v1.datasets.get_settings", lambda: settings)

    resp = _upload(client, auth_headers, b"a,b\n" + b"1,2\n" * 100)
    assert resp.status_code == 413
    assert resp.json()["code"] == "FILE_TOO_LARGE"


def test_rejects_unparsable_content(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    """字节序列既不是合法 UTF-8 也无法按 GBK 解析。"""
    raw = b"\xff\xfe\xff\xfe\xff\xfe"
    resp = _upload(client, auth_headers, raw)
    assert resp.status_code == 400
    assert resp.json()["code"] == "CSV_PARSE_ERROR"


def test_rejects_unknown_column(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, CSV, features=["f1", "ghost"])
    assert resp.status_code == 400
    assert resp.json()["code"] == "CSV_PARSE_ERROR"
    assert "ghost" in resp.json()["message"]


def test_rejects_target_in_features(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    resp = _upload(client, auth_headers, CSV, features=["f1", "label"])
    assert resp.status_code == 400
    assert "目标列" in resp.json()["message"]


def test_drop_all_rows_rejected(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    raw = b"f1,label\n,0\n,1\n"
    resp = _upload(client, auth_headers, raw, features=["f1"], strategy="drop")
    assert resp.status_code == 400
    assert "没有剩余样本" in resp.json()["message"]


def test_list_and_detail(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    created = _upload(client, auth_headers, CSV).json()

    listing = client.get("/api/datasets", headers=auth_headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]

    detail = client.get(f"/api/datasets/{created['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["stats"]["features"][0]["name"] == "f1"


def test_other_user_cannot_read(
    client: TestClient, auth_headers: dict[str, str], storage
) -> None:
    created = _upload(client, auth_headers, CSV).json()

    bob = {"username": "bob", "password": "Str0ng!pass"}
    client.post("/api/auth/register", json=bob)
    bob_headers = {
        "Authorization": "Bearer "
        + client.post("/api/auth/login", json=bob).json()["access_token"]
    }

    resp = client.get(f"/api/datasets/{created['id']}", headers=bob_headers)
    assert resp.status_code == 403

    listing = client.get("/api/datasets", headers=bob_headers).json()
    assert listing["total"] == 0
