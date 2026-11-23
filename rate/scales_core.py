"""36 角色单局表现量表（82017 / 难度 3 / v0.1）。

只读加载 JSON 元数据与 NPZ 冻结参考分布，不训练、不修改参考数据。
同时兼容完整包中 101 的旧公式键，以及 101/130 的旧承伤数组键。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class ScaleError(ValueError):
    """输入数据或量表文件不符合评分要求。"""


def round10(value: float) -> float:
    return float(np.round(float(value), 10))


def empirical_percentile(reference: np.ndarray, value: float) -> float:
    """冻结参考分布上的中点秩百分位，返回 0～1。"""
    ref = np.asarray(reference, dtype=float)
    if ref.ndim != 1 or len(ref) == 0:
        raise ScaleError("参考分布必须是非空一维数组。")
    left = np.searchsorted(ref, value, side="left")
    right = np.searchsorted(ref, value, side="right")
    return float((left + right) / (2 * len(ref)))


# 统一公式分项：(指标名, NPZ 参考键候选)。旧公式键也归一到同一套计算。
_METRICS = {
    "p_global": ("dmg_rate", ("dmg_rate",)),
    "p_mid": ("dmg_rate_8", ("dmg_rate_8",)),
    "p_transfer": ("transfer_rate", ("transfer_rate",)),
    "p_transfer7": ("transfer_rate_7", ("transfer_rate_7",)),
    "p_move": ("move_rate", ("move_rate",)),
    "p_healing": ("tret_rate", ("tret_rate",)),
    "p_injury": ("neg_inj_rate", ("neg_inj_rate", "negative_inj_rate")),
    "transfer_rate": ("transfer_rate", ("transfer_rate",)),
    "transfer_rate_7": ("transfer_rate_7", ("transfer_rate_7",)),
    "negative_inj_rate_percentile": (
        "neg_inj_rate",
        ("neg_inj_rate", "negative_inj_rate"),
    ),
}
_SURVIVAL_KEYS = {"survival_cap", "death_component"}


class ScaleBank:
    """按 hero_id 懒加载并缓存角色量表。"""

    def __init__(self, scale_root: str | Path):
        self.scale_root = Path(scale_root).resolve()
        if not self.scale_root.is_dir():
            raise ScaleError(f"量表目录不存在：{self.scale_root}")
        self._cache: dict[int, tuple[dict[str, Any], dict[str, np.ndarray]]] = {}

    @staticmethod
    def _number(row: Mapping[str, Any], key: str) -> float:
        if key not in row or row[key] is None or row[key] == "":
            raise ScaleError(f"缺少评分字段：{key}")
        try:
            value = float(row[key])
        except (TypeError, ValueError) as exc:
            raise ScaleError(f"评分字段 {key} 不是数值：{row[key]!r}") from exc
        if not math.isfinite(value):
            raise ScaleError(f"评分字段 {key} 不是有限数值。")
        return value

    def _load(self, hero_id: int) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
        if hero_id in self._cache:
            return self._cache[hero_id]

        scale_dir = self.scale_root / str(hero_id)
        metadata_files = list(scale_dir.glob("*_score_metadata_v0_1.json"))
        if len(metadata_files) != 1:
            raise ScaleError(f"角色 {hero_id} 的量表元数据数量不是 1。")

        with metadata_files[0].open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if int(raw["hero_id"]) != hero_id:
            raise ScaleError(f"角色 {hero_id} 的目录与元数据不一致。")

        # 完整包中少数角色沿用旧字段，读取时归一，不改原始 JSON。
        metadata = dict(raw)
        metadata["scale_id"] = raw.get("scale_id", raw.get("score_version", ""))
        metadata["version"] = raw.get("version", "v0.1")
        metadata["reference_rows"] = int(
            raw.get("reference_rows", raw.get("reference_n", 0))
        )
        metadata["reference_unique_uids"] = int(
            raw.get("reference_unique_uids", raw.get("reference_uids", 0))
        )
        metadata["role_type"] = raw.get("role_type", raw.get("role", ""))
        metadata.setdefault("sample_confidence", "未标注")
        metadata.setdefault("status", "")
        metadata.setdefault("usage_label", "")
        metadata.setdefault("usage_warning", "")

        reference_path = scale_dir / raw["reference_file"]
        with np.load(reference_path, allow_pickle=False) as data:
            references = {key: np.asarray(data[key], dtype=float) for key in data.files}
        if "raw_score" not in references:
            raise ScaleError(f"角色 {hero_id} 缺少 raw_score 参考分布。")
        for key, values in references.items():
            if values.ndim != 1 or len(values) == 0:
                raise ScaleError(f"角色 {hero_id} 的参考数组 {key} 不是非空一维数组。")
            if not np.all(np.isfinite(values)) or np.any(values[:-1] > values[1:]):
                raise ScaleError(f"角色 {hero_id} 的参考数组 {key} 不是有限升序数组。")

        self._cache[hero_id] = (metadata, references)
        return metadata, references

    def _metric_value(self, metric: str, row: Mapping[str, Any], rounds: float) -> float:
        # 在线评分使用原始字段；审计 CSV 缺少部分中间原始值时，可复用其率化字段。
        if metric == "dmg_rate":
            if "dmg" in row:
                return round10(self._number(row, "dmg") / rounds)
            return round10(self._number(row, "dmg_rate"))
        if metric == "dmg_rate_8":
            if "dmg_1_8" in row:
                return round10(self._number(row, "dmg_1_8") / min(8.0, rounds))
            return round10(self._number(row, "dmg_rate_8"))
        if metric == "transfer_rate":
            if "transfer" in row:
                return round10(self._number(row, "transfer") / rounds)
            return round10(self._number(row, "transfer_rate"))
        if metric == "transfer_rate_7":
            if "transfer_1_7" in row:
                return round10(self._number(row, "transfer_1_7") / min(7.0, rounds))
            return round10(self._number(row, "transfer_rate_7"))
        if metric == "move_rate":
            if "move" in row:
                return round10(self._number(row, "move") / rounds)
            return round10(self._number(row, "move_rate"))
        if metric == "tret_rate":
            if "tret" in row:
                return round10(self._number(row, "tret") / rounds)
            return round10(self._number(row, "tret_rate"))
        if metric == "neg_inj_rate":
            if "inj" in row:
                return -round10(self._number(row, "inj") / rounds)
            for key in ("neg_inj_rate", "negative_inj_rate"):
                if key in row:
                    return round10(self._number(row, key))
            return -round10(self._number(row, "inj_rate"))
        raise ScaleError(f"未知评分指标：{metric}")

    def score_one(self, row: Mapping[str, Any]) -> dict[str, Any]:
        hero_id = int(self._number(row, "hero_id"))
        metadata, references = self._load(hero_id)

        map_id = int(self._number(row, "map_id"))
        difficulty = int(self._number(row, "difficulty"))
        if map_id != int(metadata["map_id"]):
            raise ScaleError(
                f"量表仅支持地图 {metadata['map_id']}，本局为 {map_id}。"
            )
        if difficulty != int(metadata["difficulty"]):
            raise ScaleError(
                f"量表仅支持难度 {metadata['difficulty']}，本局为 {difficulty}。"
            )

        rounds = self._number(row, "rounds")
        if rounds <= 0:
            raise ScaleError("rounds 必须大于 0。")

        raw_score = 0.0
        components: dict[str, float] = {}
        metrics: dict[str, float] = {}
        formula = metadata["formula"]
        for formula_key, weight_value in formula.items():
            weight = float(weight_value)
            if formula_key in _SURVIVAL_KEYS:
                if "died" in row:
                    component = float(
                        np.clip(1.0 - self._number(row, "died") / 3.0, 0.0, 1.0)
                    )
                else:
                    key = "survival_cap" if "survival_cap" in row else "death_component"
                    component = float(
                        np.clip(self._number(row, key), 0.0, 1.0)
                    )
                canonical_key = "survival_cap"
            else:
                if formula_key not in _METRICS:
                    raise ScaleError(f"角色 {hero_id} 使用未知公式分项：{formula_key}")
                metric, reference_keys = _METRICS[formula_key]
                value = self._metric_value(metric, row, rounds)
                reference_key = next(
                    (key for key in reference_keys if key in references), None
                )
                if reference_key is None:
                    raise ScaleError(
                        f"角色 {hero_id} 缺少 {metric} 对应的参考分布。"
                    )
                component = empirical_percentile(references[reference_key], value)
                metrics[metric] = value
                canonical_key = formula_key
            components[canonical_key] = float(component)
            raw_score += weight * component

        overall_percentile = 100.0 * empirical_percentile(
            references["raw_score"], raw_score
        )
        return {
            "scale_id": metadata["scale_id"],
            "version": metadata["version"],
            "hero_id": hero_id,
            "hero_name": metadata["hero_name"],
            "role_type": metadata["role_type"],
            "map_id": map_id,
            "difficulty": difficulty,
            "raw_score": float(raw_score),
            "overall_percentile": float(overall_percentile),
            "components": components,
            "metrics": metrics,
            "reference_rows": metadata["reference_rows"],
            "reference_unique_uids": metadata["reference_unique_uids"],
            "sample_confidence": metadata["sample_confidence"],
            "status": metadata["status"],
            "usage_label": metadata["usage_label"],
            "usage_warning": metadata["usage_warning"],
        }

    def score_many(self, rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """逐行评分；一局四行即返回四个独立结果。"""
        return [self.score_one(row) for row in rows]
