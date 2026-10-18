"""预处理与 DAG 模型的单元测试。"""

from pathlib import Path

import numpy as np
import pytest
import torch

from app.models.dataset import Dataset
from app.services.dag_model import build_dag_net
from app.services.preprocessing import PreprocessError, prepare_dataset


def _write_csv(path: Path, header: str, rows: list[str]) -> Path:
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _numeric_dataset(path: Path, features: list[str], target: str = "label") -> Dataset:
    return Dataset(
        user_id=1,
        name="d",
        columns_meta=[],
        feature_columns=features,
        target_column=target,
        missing_strategy="mean",
        stats={},
        sample_count=0,
        feature_count=0,
        file_path=str(path),
    )


def test_numeric_preprocessing(tmp_path: Path) -> None:
    rows = [f"{i}.0,{(i * 2)}.0,{i % 2}" for i in range(60)]
    path = _write_csv(tmp_path / "d.csv", "f1,f2,label", rows)

    prepared = prepare_dataset(_numeric_dataset(path, ["f1", "f2"]), "classification")

    assert prepared.input_dim == 2
    assert prepared.num_classes == 2
    assert prepared.classes == ["0", "1"]
    assert prepared.x_train.shape == (48, 2)
    assert prepared.x_val.shape == (12, 2)
    # 训练集标准化后均值应接近 0
    assert abs(float(np.mean(prepared.x_train))) < 1e-5


def test_categorical_feature_is_one_hot(tmp_path: Path) -> None:
    colors = ["red", "green", "blue"]
    rows = [f"{i}.0,{i}.0,{colors[i % 3]},0" for i in range(60)]
    path = _write_csv(tmp_path / "d.csv", "f1,f2,color,label", rows)

    dataset = _numeric_dataset(path, ["f1", "f2", "color"])
    prepared = prepare_dataset(dataset, "classification")

    # 2 个数值列 + 3 个类别列独热
    assert prepared.input_dim == 5


def test_rejects_high_cardinality(tmp_path: Path) -> None:
    rows = [f"{i}.0,id_{i},0" for i in range(60)]
    path = _write_csv(tmp_path / "d.csv", "f1,code,label", rows)

    dataset = _numeric_dataset(path, ["f1", "code"])
    with pytest.raises(PreprocessError):
        prepare_dataset(dataset, "classification")


def test_rejects_too_few_samples(tmp_path: Path) -> None:
    rows = [f"{i}.0,{i % 2}" for i in range(5)]
    path = _write_csv(tmp_path / "d.csv", "f1,label", rows)

    dataset = _numeric_dataset(path, ["f1"])
    with pytest.raises(PreprocessError):
        prepare_dataset(dataset, "classification")


def test_regression_target_must_be_numeric(tmp_path: Path) -> None:
    rows = [f"{i}.0,label_{i}" for i in range(20)]
    path = _write_csv(tmp_path / "d.csv", "f1,label", rows)

    dataset = _numeric_dataset(path, ["f1"])
    with pytest.raises(PreprocessError):
        prepare_dataset(dataset, "regression")


PLAN = {
    "merge": "concat",
    "order": ["n1", "n2", "n3", "n4"],
    "steps": [
        {"node_id": "n1", "type": "input", "inputs": []},
        {"node_id": "n2", "type": "hidden", "inputs": ["n1"]},
        {"node_id": "n3", "type": "hidden", "inputs": ["n1"]},
        {"node_id": "n4", "type": "output", "inputs": ["n2", "n3"]},
    ],
}

NODES = {
    "n1": {"id": "n1", "type": "input", "params": {}},
    "n2": {"id": "n2", "type": "hidden", "params": {"units": 5, "activation": "relu"}},
    "n3": {"id": "n3", "type": "hidden", "params": {"units": 3, "activation": "tanh"}},
    "n4": {"id": "n4", "type": "output", "params": {"units": 2}},
}


def test_dag_forward_with_concat_merge() -> None:
    net = build_dag_net(PLAN, NODES, input_dim=4)
    output = net(torch.zeros(8, 4))
    assert output.shape == (8, 2)


def test_dag_backward_runs() -> None:
    net = build_dag_net(PLAN, NODES, input_dim=4)
    x = torch.randn(6, 4)
    target = torch.tensor([0, 1, 0, 1, 0, 1])
    loss = torch.nn.CrossEntropyLoss()(net(x), target)
    loss.backward()

    # 汇合节点的输入维度应为 5 + 3 = 8
    first_linear = net.ops["n4"]
    assert isinstance(first_linear, torch.nn.Linear)
    assert first_linear.in_features == 8
