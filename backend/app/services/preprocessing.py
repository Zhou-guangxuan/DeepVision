"""训练前的数据预处理：缺失值 → 编码 → 标准化 → 划分。

设计取舍：

- 数值特征做 z-score 标准化，统计量只取训练集，避免验证集泄漏。
- 类别特征做独热编码；类别数超过上限直接报错，避免维度爆炸。
- 分类任务把标签编码为 0..k-1；回归任务要求标签为数值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from app.models.dataset import Dataset
from app.services import csv_service

TRAIN_RATIO = 0.8
RANDOM_SEED = 42
MAX_CATEGORIES = 50


class PreprocessError(ValueError):
    """预处理失败，message 可直接展示给用户。"""


@dataclass
class PreparedData:
    x_train: np.ndarray
    y_train: np.ndarray
    x_val: np.ndarray
    y_val: np.ndarray
    input_dim: int
    task: str
    num_classes: int | None = None
    classes: list[str] = field(default_factory=list)


def _load_dataframe(dataset: Dataset) -> pd.DataFrame:
    path = Path(dataset.file_path)
    if not path.exists():
        raise PreprocessError("数据集文件不存在，请重新上传")

    try:
        return csv_service.read_csv_bytes(path.read_bytes())
    except csv_service.CsvParseError as exc:
        raise PreprocessError(str(exc)) from exc


def _encode_features(df: pd.DataFrame, feature_columns: list[str]) -> np.ndarray:
    blocks: list[np.ndarray] = []

    for column in feature_columns:
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            blocks.append(series.astype("float64").to_numpy())
            continue

        values = series.astype("string").fillna("__missing__")
        uniques = list(pd.unique(values))
        if len(uniques) > MAX_CATEGORIES:
            raise PreprocessError(
                f"列「{column}」类别过多（{len(uniques)} 个），暂不支持独热编码"
            )
        for value in uniques:
            blocks.append((values == value).to_numpy(dtype="float64"))

    if not blocks:
        return np.zeros((len(df), 0), dtype="float64")

    return np.column_stack(blocks)


def _encode_target(
    df: pd.DataFrame,
    target_column: str,
    task: str,
) -> tuple[np.ndarray, int | None, list[str]]:
    series = df[target_column]

    if task == "classification":
        if pd.api.types.is_numeric_dtype(series):
            values = series.astype("int64")
            uniques = sorted(int(item) for item in pd.unique(values))
            mapping = {value: index for index, value in enumerate(uniques)}
            encoded = values.map(mapping).to_numpy(dtype="int64")
            return encoded, len(uniques), [str(item) for item in uniques]

        strings = series.astype("string")
        uniques = sorted(str(item) for item in pd.unique(strings))
        mapping = {value: index for index, value in enumerate(uniques)}
        encoded = strings.map(mapping).to_numpy(dtype="int64")
        return encoded, len(uniques), uniques

    if not pd.api.types.is_numeric_dtype(series):
        raise PreprocessError("回归任务的标签列必须是数值类型")
    return series.astype("float64").to_numpy(), None, []


def prepare_dataset(dataset: Dataset, task: str) -> PreparedData:
    """按数据集上记录的特征列、目标列与缺失值策略生成训练数据。"""
    features = list(dataset.feature_columns or [])
    if not features:
        raise PreprocessError("该数据集没有记录特征列，请重新上传")
    if not dataset.target_column:
        raise PreprocessError("该数据集没有记录目标列，请重新上传")

    df = _load_dataframe(dataset)

    missing = [
        column
        for column in [*features, dataset.target_column]
        if column not in df.columns
    ]
    if missing:
        raise PreprocessError("数据集中缺少列：" + "、".join(missing))

    try:
        df = csv_service.apply_missing_strategy(
            df, features, dataset.target_column, dataset.missing_strategy
        )
    except csv_service.CsvParseError as exc:
        raise PreprocessError(str(exc)) from exc

    if len(df) < 10:
        raise PreprocessError("有效样本少于 10 条，无法训练")

    y, num_classes, classes = _encode_target(df, dataset.target_column, task)
    x = _encode_features(df, features)

    if x.shape[1] == 0:
        raise PreprocessError("没有可用的特征列")

    rng = np.random.default_rng(RANDOM_SEED)
    indices = rng.permutation(len(df))
    split = int(len(df) * TRAIN_RATIO)
    train_idx, val_idx = indices[:split], indices[split:]

    if len(train_idx) == 0 or len(val_idx) == 0:
        raise PreprocessError("样本太少，无法划分训练集与验证集")

    x_train, x_val = x[train_idx], x[val_idx]

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std[std == 0] = 1.0

    x_train = (x_train - mean) / std
    x_val = (x_val - mean) / std

    dtype = "float32"
    if task == "classification":
        y_train = y[train_idx].astype("int64")
        y_val = y[val_idx].astype("int64")
    else:
        y_train = y[train_idx].astype(dtype)
        y_val = y[val_idx].astype(dtype)

    return PreparedData(
        x_train=x_train.astype(dtype),
        y_train=y_train,
        x_val=x_val.astype(dtype),
        y_val=y_val,
        input_dim=int(x.shape[1]),
        task=task,
        num_classes=num_classes,
        classes=classes,
    )
