from __future__ import annotations

import math
from dataclasses import dataclass, field


TIME_UNIT_TO_NS = {
    "ns": 1.0,
    "us": 1_000.0,
    "ms": 1_000_000.0,
    "s": 1_000_000_000.0,
}


# t critical values for 95% two-sided CI, by degrees of freedom (n-1).
# For df > 30, approximate with 1.96
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}
Z_CRITICAL_95 = 1.96


@dataclass
class CaseStats:
    samples_ns: list[float] = field(default_factory=list)

    def add(self, value_ns: float) -> None:
        self.samples_ns.append(value_ns)

    @property
    def count(self) -> int:
        return len(self.samples_ns)

    @property
    def mean(self) -> float:
        if not self.samples_ns:
            return float("nan")
        return sum(self.samples_ns) / len(self.samples_ns)

    @property
    def stddev(self) -> float:
        n = len(self.samples_ns)
        if n < 2:
            return float("nan")
        m = self.mean
        var = sum((x - m) ** 2 for x in self.samples_ns) / (n - 1)
        return math.sqrt(var)

    def rel_ci95_half(self) -> float:
        n = len(self.samples_ns)
        if n < 2:
            return float("inf")
        critical = T_CRITICAL_95.get(n - 1, Z_CRITICAL_95)
        half = critical * (self.stddev / math.sqrt(n))
        return half / self.mean if self.mean != 0 else float("inf")


def normalize_to_ns(value: float, unit: str) -> float:
    factor = TIME_UNIT_TO_NS.get(unit)
    if factor is None:
        raise ValueError(f"Unknown time unit: {unit}")
    return value * factor


def extract_case_values(json_doc: dict) -> dict[str, float]:
    results: dict[str, float] = {}
    benches = json_doc.get("benchmarks", [])
    for row in benches:
        if row.get("aggregate_name"):
            continue
        name = row.get("name")
        real_time = row.get("real_time")
        time_unit = row.get("time_unit")
        if name is None or real_time is None or time_unit is None:
            continue
        results[name] = normalize_to_ns(float(real_time), str(time_unit))
    return results


def update_stats(all_stats: dict[str, CaseStats], new_values: dict[str, float]) -> None:
    for name, value_ns in new_values.items():
        if name not in all_stats:
            all_stats[name] = CaseStats()
        all_stats[name].add(value_ns)


def compute_unstable_cases(
    all_stats: dict[str, CaseStats], *, rel_ci_threshold: float, min_meta_reps: int
) -> list[str]:
    unstable: list[str] = []
    for name, stats in all_stats.items():
        if stats.count < min_meta_reps:
            unstable.append(name)
            continue
        if stats.rel_ci95_half() > rel_ci_threshold:
            unstable.append(name)
    return unstable


def compute_summary(
    all_stats: dict[str, CaseStats],
    rel_ci_threshold: float,
    min_meta_reps: int,
) -> tuple[int, int, tuple[str, float] | None, int]:
    num_cases = len(all_stats)
    unstable = compute_unstable_cases(
        all_stats, rel_ci_threshold=rel_ci_threshold, min_meta_reps=min_meta_reps
    )
    num_stable = num_cases - len(unstable)
    worst_case: tuple[str, float] | None = None
    worst_rci: float = float("-inf")
    for name, stats in all_stats.items():
        if stats.count < 2:
            continue
        rci = stats.rel_ci95_half()
        if math.isfinite(rci) and rci > worst_rci:
            worst_case = (name, rci)
            worst_rci = rci
    return num_cases, num_stable, worst_case, len(unstable)


