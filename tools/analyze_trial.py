"""试测数据分析：读 CSV → 描述统计 + 前后配对检验 + 分组比较。

只依赖 Python 标准库（本机虚拟环境没有 scipy），统计量为常见近似实现：

- 配对 t 检验（正态近似，小样本仅作参考）
- Wilcoxon 符号秩检验（正态近似 + 并列校正）
- Mann-Whitney U（正态近似 + 并列校正）
- McNemar 精确检验（二项分布）
- Wilson 比例置信区间
- 效应量 Cohen's dz

用法：

    python tools/analyze_trial.py 试测记录表.csv
    python tools/analyze_trial.py 试测记录表.csv --out 试测结果.md
    python tools/analyze_trial.py 试测记录表.csv --json 试测结果.json

注意：n 很小时（< 12）p 值不稳定，请以中位数、区间与效应量为主。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 基础统计


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _quantile(values: list[float], q: float) -> float:
    """线性插值分位数（与 numpy 默认方法一致）。"""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta 函数的连分式（Numerical Recipes betacf）。"""
    tiny = 1e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    result = d

    for step in range(1, 201):
        m2 = 2 * step
        aa = step * (b - step) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        result *= d * c

        aa = -(a + step) * (qab + step) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return result


def _betainc(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta 函数 I_x(a, b)。"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(log_beta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1 - x) / b


def _t_two_sided_p(t_stat: float, degrees: float) -> float:
    if degrees <= 0:
        return 1.0
    x = degrees / (degrees + t_stat * t_stat)
    return _betainc(degrees / 2.0, 0.5, x)


def _ranks(values: list[float]) -> tuple[list[float], float]:
    """平均秩；返回 (秩, 并列校正项 Σ(t³-t))。"""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    tie_correction = 0.0

    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end + 2) / 2.0  # 1-based 平均秩
        for position in range(index, end + 1):
            ranks[order[position]] = average
        ties = end - index + 1
        if ties > 1:
            tie_correction += ties**3 - ties
        index = end + 1

    return ranks, tie_correction


def wilcoxon_signed_rank(differences: list[float]) -> dict:
    """Wilcoxon 符号秩（正态近似，双尾）。"""
    nonzero = [value for value in differences if value != 0]
    count = len(nonzero)
    if count == 0:
        return {"n": 0, "p": 1.0, "statistic": 0.0}

    ranks, tie_correction = _ranks([abs(value) for value in nonzero])
    positive = sum(rank for rank, value in zip(ranks, nonzero) if value > 0)

    mean = count * (count + 1) / 4.0
    variance = count * (count + 1) * (2 * count + 1) / 24.0 - tie_correction / 48.0
    if variance <= 0:
        return {"n": count, "p": 1.0, "statistic": positive}

    z = (positive - mean) / math.sqrt(variance)
    p = 2 * (1 - _normal_cdf(abs(z)))
    return {"n": count, "p": min(1.0, max(0.0, p)), "statistic": positive, "z": z}


def mann_whitney(first: list[float], second: list[float]) -> dict:
    """Mann-Whitney U（正态近似，双尾）。"""
    if len(first) < 2 or len(second) < 2:
        return {"p": 1.0, "u": 0.0}

    combined = first + second
    ranks, tie_correction = _ranks(combined)
    rank_sum = sum(ranks[: len(first)])
    n1, n2 = len(first), len(second)
    u1 = rank_sum - n1 * (n1 + 1) / 2.0

    mean = n1 * n2 / 2.0
    variance = (
        n1 * n2 * (n1 + n2 + 1) / 12.0 - n1 * n2 * tie_correction / (12.0 * (n1 + n2) * (n1 + n2 - 1))
    )
    if variance <= 0:
        return {"p": 1.0, "u": u1}

    z = (u1 - mean) / math.sqrt(variance)
    p = 2 * (1 - _normal_cdf(abs(z)))
    return {"p": min(1.0, max(0.0, p)), "u": u1, "z": z}


def mcnemar_exact(before_only: int, after_only: int) -> float:
    """McNemar 精确检验（二项分布，双尾）。"""
    total = before_only + after_only
    if total == 0:
        return 1.0
    smaller = min(before_only, after_only)
    tail = sum(math.comb(total, k) for k in range(smaller + 1)) / (2**total)
    return min(1.0, 2 * tail)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


# ---------------------------------------------------------------- 数据读取


@dataclass
class Row:
    participant: str
    group: str
    values: dict[str, float | None] = field(default_factory=dict)


def _number(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_rows(path: Path) -> list[Row]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[Row] = []
        for index, record in enumerate(reader, start=1):
            participant = (record.get("participant_id") or f"P{index:02d}").strip()
            group = (record.get("group") or "single").strip() or "single"
            values = {
                key: _number(value)
                for key, value in record.items()
                if key not in {"participant_id", "group", "notes"}
            }
            rows.append(Row(participant=participant, group=group, values=values))
    return rows


# ---------------------------------------------------------------- 分析


PAIRED_METRICS = [
    ("pretest_score", "posttest_score", "结构测验（0–10）"),
    ("self_efficacy_pre", "self_efficacy_post", "自评均分（1–5）"),
]

SINGLE_METRICS = [
    ("first_run_minutes", "首次跑通时间（分钟）"),
    ("diagnosis_score", "诊断得分（0–3）"),
    ("migration_score", "迁移题（0–2）"),
    ("attempts", "尝试次数"),
]

BINARY_METRICS = [
    ("task_completed", "任务完成率"),
    ("rerun_consistent", "复现一致性"),
]


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _fmt_p(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def describe(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": _mean(values),
        "sd": _sd(values),
        "median": _median(values),
        "q1": _quantile(values, 0.25),
        "q3": _quantile(values, 0.75),
    }


def paired(values_pre: list[float], values_post: list[float]) -> dict:
    differences = [post - pre for pre, post in zip(values_pre, values_post, strict=True)]
    n = len(differences)
    if n == 0:
        return {"n": 0}

    average = _mean(differences)
    sd = _sd(differences)
    dz = average / sd if sd > 0 else None

    t_stat = None
    p_t = None
    if n >= 2 and sd > 0:
        t_stat = average / (sd / math.sqrt(n))
        p_t = _t_two_sided_p(t_stat, n - 1)

    wilcoxon = wilcoxon_signed_rank(differences)
    return {
        "n": n,
        "median_diff": _median(differences),
        "mean_diff": average,
        "dz": dz,
        "t": t_stat,
        "p_t": p_t,
        "p_wilcoxon": wilcoxon["p"],
    }


def analyze(rows: list[Row]) -> dict:
    report: dict = {"n_total": len(rows), "groups": {}, "metrics": {}}
    report["n_effective"] = sum(
        1 for row in rows if any(value is not None for value in row.values.values())
    )

    group_counts: dict[str, int] = {}
    for row in rows:
        group_counts[row.group] = group_counts.get(row.group, 0) + 1
    report["groups"] = group_counts

    for pre_key, post_key, label in PAIRED_METRICS:
        pairs = [
            (row.values.get(pre_key), row.values.get(post_key))
            for row in rows
            if row.values.get(pre_key) is not None
            and row.values.get(post_key) is not None
        ]
        pre_values = [pre for pre, _ in pairs if pre is not None]
        post_values = [post for _, post in pairs if post is not None]
        report["metrics"][label] = {
            "pre": describe(pre_values),
            "post": describe(post_values),
            "paired": paired(pre_values, post_values),
        }

    for key, label in SINGLE_METRICS:
        values = [row.values[key] for row in rows if row.values.get(key) is not None]
        report["metrics"][label] = {"describe": describe(values)}

    for key, label in BINARY_METRICS:
        values = [row.values[key] for row in rows if row.values.get(key) is not None]
        successes = sum(1 for value in values if value and value > 0)
        low, high = wilson_interval(successes, len(values))
        report["metrics"][label] = {
            "n": len(values),
            "rate": (successes / len(values)) if values else None,
            "ci": [low, high],
        }

    # 分组比较：只比较「非 single」的组
    real_groups = [name for name in group_counts if name != "single"]
    if len(real_groups) >= 2:
        first, second = real_groups[0], real_groups[1]
        for key in ("first_run_minutes", "diagnosis_score"):
            first_values = [
                row.values[key]
                for row in rows
                if row.group == first and row.values.get(key) is not None
            ]
            second_values = [
                row.values[key]
                for row in rows
                if row.group == second and row.values.get(key) is not None
            ]
            if len(first_values) >= 2 and len(second_values) >= 2:
                test = mann_whitney(first_values, second_values)
                report.setdefault("group_tests", []).append(
                    {
                        "metric": key,
                        "first": first,
                        "second": second,
                        "median_first": _median(first_values),
                        "median_second": _median(second_values),
                        "p": test["p"],
                    }
                )

    # 检查表里是否同时存在前后测（用于 McNemar 的场景：完成率前后）
    before = [
        row.values.get("task_completed")
        for row in rows
        if row.values.get("task_completed") is not None
    ]
    report["completed_count"] = sum(1 for value in before if value and value > 0)

    return report


# ---------------------------------------------------------------- 输出


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# 试测结果摘要")
    lines.append("")
    lines.append(
        f"样本量：**{report['n_total']}**（其中有数据的 {report.get('n_effective', report['n_total'])} 行）"
        f"　分组：{report['groups']}"
    )
    lines.append("")

    lines.append("## 1. 指标描述")
    lines.append("")
    lines.append("| 指标 | n | 均值 | 标准差 | 中位数 | IQR |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for label, data in report["metrics"].items():
        if "describe" in data:
            item = data["describe"]
            if item["n"] == 0:
                lines.append(f"| {label} | 0 | — | — | — | — |")
                continue
            lines.append(
                f"| {label} | {item['n']} | {_fmt(item['mean'])} | {_fmt(item['sd'])} | "
                f"{_fmt(item['median'])} | {_fmt(item['q1'])}–{_fmt(item['q3'])} |"
            )
        elif "pre" in data:
            pre = data["pre"]
            post = data["post"]
            if pre.get("n", 0) == 0 or post.get("n", 0) == 0:
                lines.append(f"| {label}（前测 / 后测） | 0 | — | — | — | — |")
                continue
            lines.append(
                f"| {label}（前测） | {pre['n']} | {_fmt(pre['mean'])} | {_fmt(pre['sd'])} | "
                f"{_fmt(pre['median'])} | {_fmt(pre['q1'])}–{_fmt(pre['q3'])} |"
            )
            lines.append(
                f"| {label}（后测） | {post['n']} | {_fmt(post['mean'])} | {_fmt(post['sd'])} | "
                f"{_fmt(post['median'])} | {_fmt(post['q1'])}–{_fmt(post['q3'])} |"
            )
        else:
            rate = data.get("rate")
            low, high = data.get("ci", (0, 0))
            lines.append(
                f"| {label} | {data['n']} | {_fmt(rate, 3)} | — | — | "
                f"95% CI {_fmt(low, 3)}–{_fmt(high, 3)} |"
            )
    lines.append("")

    lines.append("## 2. 前后配对比较")
    lines.append("")
    lines.append("| 指标 | n | 差值中位数 | Cohen's dz | Wilcoxon p | t 检验 p |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for label, data in report["metrics"].items():
        if "paired" not in data:
            continue
        item = data["paired"]
        if item.get("n", 0) == 0:
            lines.append(f"| {label} | 0 | — | — | — | — |")
            continue
        lines.append(
            f"| {label} | {item['n']} | {_fmt(item['median_diff'])} | "
            f"{_fmt(item['dz'])} | {_fmt_p(item['p_wilcoxon'])} | {_fmt_p(item['p_t'])} |"
        )
    lines.append("")

    if report.get("group_tests"):
        lines.append("## 3. 分组比较（Mann-Whitney）")
        lines.append("")
        lines.append("| 指标 | 组 A 中位数 | 组 B 中位数 | p |")
        lines.append("| --- | --- | --- | --- |")
        for item in report["group_tests"]:
            lines.append(
                f"| {item['metric']} | {item['first']}: {_fmt(item['median_first'])} | "
                f"{item['second']}: {_fmt(item['median_second'])} | {_fmt_p(item['p'])} |"
            )
        lines.append("")

    lines.append("## 4. 阅读提示")
    lines.append("")
    if report["n_total"] < 12:
        lines.append("- 样本量 < 12，p 值不稳定，**不要据此下强结论**；以中位数与效应量为主。")
    lines.append("- 单组前后测无法排除练习效应，结论应写「前后有变化」，而不是「平台导致」。")
    lines.append("- 效应量参考：|dz| ≈ 0.2 小、0.5 中、0.8 大；n 小的时候区间比 p 值更可靠。")
    lines.append("- 不要因为不显著就删数据或改口径；把不显著如实写进报告。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="分析试测记录表")
    parser.add_argument("csv", type=Path, help="试测记录表 CSV 路径")
    parser.add_argument("--out", type=Path, help="把 Markdown 结果写入文件")
    parser.add_argument("--json", type=Path, help="把原始统计写入 JSON 文件")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"找不到文件：{args.csv}")
        return 1

    rows = load_rows(args.csv)
    if not rows:
        print("CSV 里没有数据行")
        return 1

    report = analyze(rows)
    markdown = render_markdown(report)
    print(markdown)

    if args.out:
        args.out.write_text(markdown, encoding="utf-8")
        print(f"\n已写入：{args.out}")
    if args.json:
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已写入：{args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
