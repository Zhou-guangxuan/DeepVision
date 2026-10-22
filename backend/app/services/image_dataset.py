"""内置合成图像数据集（圆 vs 方）。

不依赖外部下载：随机生成两类几何图形，带轻微噪声与位置抖动，
让卷积网络有可学的局部结构，同时保持完全离线可跑。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

CLASSES = ["圆形", "方形"]
DEFAULT_SIZE = 16
DEFAULT_SAMPLES = 1200


def generate(
    samples: int = DEFAULT_SAMPLES,
    size: int = DEFAULT_SIZE,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """返回 (x, y)：x 形状 (N, 1, size, size)，取值 0–1；y 为 0/1。"""
    rng = np.random.default_rng(seed)
    samples = max(100, min(int(samples), 5000))
    size = max(8, min(int(size), 32))
    per_class = samples // 2

    grid_y, grid_x = np.mgrid[0:size, 0:size]
    images: list[np.ndarray] = []
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
            images.append(np.clip(image, 0.0, 1.0))
            labels.append(label)

    x = np.stack(images)[:, None, :, :].astype("float32")
    y = np.asarray(labels, dtype="int64")

    order = rng.permutation(len(x))
    return x[order], y[order]


def save(directory: str, user_id: int, x: np.ndarray, y: np.ndarray) -> str:
    path = (
        Path(directory)
        / f"user_{user_id}_image_{np.random.default_rng().integers(1e9)}.npz"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, x=x, y=y)
    return str(path)


def load(file_path: str) -> tuple[np.ndarray, np.ndarray]:
    data = np.load(file_path)
    return data["x"].astype("float32"), data["y"].astype("int64")
