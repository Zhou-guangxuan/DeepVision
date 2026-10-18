"""CSV 数据集解析与预处理。

职责：读取上传的 CSV → 推断列类型 → 按策略处理缺失值 → 计算统计量。
真正的文件落盘与入库分别由调用方完成。
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.schemas.dataset import DatasetStats, FeatureStats

MISSING_STRATEGIES = ("mean", "median", "mode", "drop")
TARGET_DISTRIBUTION_LIMIT = 20


class CsvParseError(ValueError):
    """解析失败；message 可直接展示给用户。"""


def _read_dataframe(raw: bytes) -> pd.DataFrame:
    """按 UTF-8（含 BOM）→ GBK 的顺序尝试解码。"""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except pd.errors.EmptyDataError as exc:
            raise CsvParseError("文件内容为空") from exc
        except pd.errors.ParserError as exc:
            raise CsvParseError("CSV 格式错误，无法解析") from exc
    raise CsvParseError("文件编码无法识别，请使用 UTF-8 或 GBK") from last_error


def describe_columns(df: pd.DataFrame) -> list[dict]:
    """推断每列类型并统计缺失值数量。"""
    columns: list[dict] = []
    for name in df.columns:
        series = df[name]
        if pd.api.types.is_numeric_dtype(series):
            dtype = "number"
        elif pd.api.types.is_datetime64_any_dtype(series):
            dtype = "date"
        else:
            dtype = "category"
        columns.append(
            {
                "name": str(name),
                "dtype": dtype,
                "missing": int(series.isna().sum()),
            }
        )
    return columns


def apply_missing_strategy(
    df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    strategy: str,
) -> pd.DataFrame:
    """按策略处理缺失值，返回新 DataFrame。"""
    if strategy not in MISSING_STRATEGIES:
        raise CsvParseError(f"缺失值策略「{strategy}」不受支持")

    subset = [*feature_columns, target_column]

    if strategy == "drop":
        return df.dropna(subset=subset).reset_index(drop=True)

    result = df.copy()
    for column in subset:
        series = result[column]
        if not series.isna().any():
            continue

        if strategy in ("mean", "median"):
            if not pd.api.types.is_numeric_dtype(series):
                label = "均值" if strategy == "mean" else "中位数"
                raise CsvParseError(
                    f"列「{column}」不是数值类型，无法用{label}填充"
                )
            fill = series.mean() if strategy == "mean" else series.median()
        else:  # mode
            modes = series.mode(dropna=True)
            if modes.empty:
                raise CsvParseError(f"列「{column}」没有可用于填充的众数")
            fill = modes.iloc[0]

        if pd.isna(fill):
            raise CsvParseError(f"列「{column}」无法计算填充值")
        result[column] = series.fillna(fill)

    return result.reset_index(drop=True)


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 6)


def _column_stats(df: pd.DataFrame, column: str) -> FeatureStats:
    series = df[column]
    if pd.api.types.is_numeric_dtype(series) and len(series) > 0:
        variance = series.var(ddof=1) if len(series) > 1 else 0.0
        return FeatureStats(
            name=str(column),
            mean=_safe_float(series.mean()),
            variance=_safe_float(variance),
        )
    return FeatureStats(name=str(column), mean=None, variance=None)


def compute_stats(
    df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
) -> DatasetStats:
    features = [_column_stats(df, column) for column in feature_columns]
    target = (
        _column_stats(df, target_column) if target_column in df.columns else None
    )

    distribution: dict[str, int] = {}
    if target_column in df.columns:
        counts = df[target_column].value_counts(dropna=True)
        for key, value in counts.head(TARGET_DISTRIBUTION_LIMIT).items():
            distribution[str(key)] = int(value)

    return DatasetStats(
        features=features,
        target=target,
        target_distribution=distribution,
    )


def preprocess(
    raw: bytes,
    feature_columns: list[str],
    target_column: str,
    strategy: str,
) -> dict:
    """解析并预处理，返回入库所需的结构。"""
    if not feature_columns:
        raise CsvParseError("请至少选择一个特征列")
    if target_column in feature_columns:
        raise CsvParseError("目标列不能同时作为特征列")

    df = _read_dataframe(raw)
    if len(df) == 0:
        raise CsvParseError("文件没有数据行")

    missing_columns = [
        column
        for column in [*feature_columns, target_column]
        if column not in df.columns
    ]
    if missing_columns:
        raise CsvParseError("以下列不存在：" + "、".join(missing_columns))

    processed = apply_missing_strategy(df, feature_columns, target_column, strategy)
    if len(processed) == 0:
        raise CsvParseError("按所选缺失值策略处理后没有剩余样本")

    return {
        # 列信息取自原始文件，缺失数反映上传时的真实情况
        "columns_meta": describe_columns(df),
        "stats": compute_stats(processed, feature_columns, target_column),
        "sample_count": int(len(processed)),
        "feature_count": len(feature_columns),
    }


def save_dataset_file(root: str, user_id: int, raw: bytes) -> str:
    """把原始 CSV 落盘，返回相对路径。"""
    directory = Path(root) / "datasets" / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}.csv"
    path.write_bytes(raw)
    return str(path)
