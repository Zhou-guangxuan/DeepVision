"""内置多模态数据集：图像 + 表格特征（圆 vs 方）。

每个样本同时包含：
- 一张 16×16 灰度几何图形；
- 4 个从图像统计出来的表格特征（面积占比、包围盒宽高、填充率）。

两路信息都带噪声：只看图像或只看表格都能到较高准确率，但都存在错例，
融合后能同时利用「形状轮廓」与「填充率/面积」两类证据。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

CLASSES = ["圆形", "方形"]
TABULAR_FEATURES = ["面积占比", "包围盒宽度", "包围盒高度", "填充率"]
DEFAULT_SIZE = 16
DEFAULT_SAMPLES = 1200


def generate(
    samples: int = DEFAULT_SAMPLES,
    size: int = DEFAULT_SIZE,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """返回 (images, tabular, labels)。

    images: (N, 1, size, size)，0–1
    tabular: (N, 4)，0–1
    labels: (N,)，0=圆形 / 1=方形
    """
    rng = np.random.default_rng(seed)
    samples = max(100, min(int(samples), 5000))
    size = max(8, min(int(size), 32))
    per_class = samples // 2

    grid_y, grid_x = np.mgrid[0:size, 0:size]
    images: list[np.ndarray] = []
    tabular: list[list[float]] = []
    labels: list[int] = []

    for label in (0, 1):
        for _ in range(per_class):
            image = np.zeros((size, size), dtype="float32")
            center_y, center_x = rng.uniform(0.32, 0.68, size=2) * size
            radius = rng.uniform(0.18, 0.32) * size

            if label == 0:
                mask = (grid_y - center_y) ** 2 + (grid_x - center_x) ** 2 <= (
                    radius**2
                )
            else:
                half = radius * 0.95
                mask = (np.abs(grid_y - center_y) <= half) & (
                    np.abs(grid_x - center_x) <= half
                )

            image[mask] = 1.0
            image += rng.normal(0, 0.05, size=(size, size))
            image = np.clip(image, 0.0, 1.0)

            # 表格特征由带噪图像统计得到，模拟「另一路传感器」
            binary = image > 0.5
            ys, xs = np.nonzero(binary)
            if len(xs) == 0:
                binary = mask
                ys, xs = np.nonzero(mask)
            width = (xs.max() - xs.min() + 1) / size
            height = (ys.max() - ys.min() + 1) / size
            area = float(binary.mean())
            box = max(1, (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
            fill = float(binary.sum() / box)

            values = np.array([area, width, height, fill], dtype="float32")
            values += rng.normal(0, 0.01, size=4).astype("float32")
            tabular.append(np.clip(values, 0.0, 1.0).tolist())
            images.append(image)
            labels.append(label)

    x = np.stack(images)[:, None, :, :].astype("float32")
    t = np.asarray(tabular, dtype="float32")
    y = np.asarray(labels, dtype="int64")

    order = rng.permutation(len(x))
    return x[order], t[order], y[order]


def save(
    directory: str,
    user_id: int,
    x: np.ndarray,
    t: np.ndarray,
    y: np.ndarray,
) -> str:
    path = (
        Path(directory)
        / f"user_{user_id}_multimodal_{np.random.default_rng().integers(1e9)}.npz"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, x=x, t=t, y=y)
    return str(path)


def load(file_path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data = np.load(file_path)
    return (
        data["x"].astype("float32"),
        data["t"].astype("float32"),
        data["y"].astype("int64"),
    )
