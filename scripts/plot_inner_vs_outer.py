#!/usr/bin/env python3
"""
Plot: Inner vs Outer Repetitions

Compares 3 strategies (all 30 total samples):
  A: 1 outer x 30 inner reps  (Google Benchmark does all repetitions internally)
  B: 30 outer x 1 inner rep   (meta-benchmark re-invokes the binary 30 times)
  C: 5 outer x 6 inner reps   (mixed: 6 inner reps, re-invoked 5 times)

For each strategy, collects per-case times, computes 95% CIs, and generates
a bar chart comparing average relative CI half-width across cases.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Inline stats (self-contained, no imports from meta_benchmark)
# ---------------------------------------------------------------------------

TIME_UNIT_TO_NS = {"ns": 1.0, "us": 1_000.0, "ms": 1_000_000.0, "s": 1_000_000_000.0}

T_CRITICAL_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}
Z_CRITICAL_95 = 1.96


def normalize_to_ns(value: float, unit: str) -> float:
    factor = TIME_UNIT_TO_NS.get(unit)
    if factor is None:
        raise ValueError(f"Unknown time unit: {unit}")
    return value * factor


def extract_case_values(json_doc: dict) -> dict[str, float]:
    results: dict[str, float] = {}
    for row in json_doc.get("benchmarks", []):
        if row.get("aggregate_name"):
            continue
        name = row.get("name")
        real_time = row.get("real_time")
        time_unit = row.get("time_unit")
        if name is None or real_time is None or time_unit is None:
            continue
        results[name] = normalize_to_ns(float(real_time), str(time_unit))
    return results


def extract_case_values_multi(json_doc: dict) -> dict[str, list[float]]:
    """Extract per-case values when benchmark_repetitions > 1.

    Google Benchmark emits one row per repetition (same name, different
    repetition_index) plus aggregate rows.  We collect ALL non-aggregate
    rows grouped by run_name (or name).
    """
    results: dict[str, list[float]] = defaultdict(list)
    for row in json_doc.get("benchmarks", []):
        if row.get("aggregate_name"):
            continue
        name = row.get("run_name") or row.get("name")
        real_time = row.get("real_time")
        time_unit = row.get("time_unit")
        if name is None or real_time is None or time_unit is None:
            continue
        results[name].append(normalize_to_ns(float(real_time), str(time_unit)))
    return dict(results)


def rel_ci95_half(samples: list[float]) -> float:
    n = len(samples)
    if n < 2:
        return float("inf")
    mean = sum(samples) / n
    if mean == 0:
        return float("inf")
    var = sum((x - mean) ** 2 for x in samples) / (n - 1)
    stddev = math.sqrt(var)
    critical = T_CRITICAL_95.get(n - 1, Z_CRITICAL_95)
    half = critical * (stddev / math.sqrt(n))
    return half / mean


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(exe: str, pin_core: int | None, repetitions: int = 1,
                  min_time: float = 0.05) -> dict:
    args = [exe, "--benchmark_format=json", f"--benchmark_min_time={min_time}s"]
    if repetitions > 1:
        args.append(f"--benchmark_repetitions={repetitions}")
    args.append("--benchmark_enable_random_interleaving=true")

    preexec = None
    if pin_core is not None and hasattr(os, "sched_setaffinity"):
        def preexec():
            os.sched_setaffinity(0, {pin_core})

    result = subprocess.run(args, capture_output=True, text=True,
                            preexec_fn=preexec, check=False)
    if result.returncode != 0:
        print(f"Benchmark failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr[:500], file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def strategy_a(exe: str, pin_core: int | None, total: int = 30) -> dict[str, list[float]]:
    """1 outer invocation x N inner repetitions."""
    print(f"  Strategy A: 1 outer x {total} inner ...")
    doc = run_benchmark(exe, pin_core, repetitions=total)
    return extract_case_values_multi(doc)


def strategy_b(exe: str, pin_core: int | None, total: int = 30) -> dict[str, list[float]]:
    """N outer invocations x 1 inner repetition."""
    print(f"  Strategy B: {total} outer x 1 inner ...")
    all_values: dict[str, list[float]] = defaultdict(list)
    for i in range(total):
        print(f"    run {i+1}/{total}", end="\r")
        doc = run_benchmark(exe, pin_core, repetitions=1)
        for name, val in extract_case_values(doc).items():
            all_values[name].append(val)
    print()
    return dict(all_values)


def strategy_c(exe: str, pin_core: int | None, outer: int = 5,
               inner: int = 6) -> dict[str, list[float]]:
    """Mixed: outer invocations x inner repetitions."""
    print(f"  Strategy C: {outer} outer x {inner} inner ...")
    all_values: dict[str, list[float]] = defaultdict(list)
    for i in range(outer):
        print(f"    run {i+1}/{outer}", end="\r")
        doc = run_benchmark(exe, pin_core, repetitions=inner)
        for name, vals in extract_case_values_multi(doc).items():
            all_values[name].extend(vals)
    print()
    return dict(all_values)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def compute_avg_ci(values_by_case: dict[str, list[float]]) -> float:
    cis = []
    for samples in values_by_case.values():
        ci = rel_ci95_half(samples)
        if math.isfinite(ci):
            cis.append(ci)
    return sum(cis) / len(cis) if cis else float("nan")


def compute_median_ci(values_by_case: dict[str, list[float]]) -> float:
    cis = []
    for samples in values_by_case.values():
        ci = rel_ci95_half(samples)
        if math.isfinite(ci):
            cis.append(ci)
    if not cis:
        return float("nan")
    cis.sort()
    n = len(cis)
    if n % 2 == 1:
        return cis[n // 2]
    return (cis[n // 2 - 1] + cis[n // 2]) / 2


def compute_worst_ci(values_by_case: dict[str, list[float]]) -> float:
    worst = 0.0
    for samples in values_by_case.values():
        ci = rel_ci95_half(samples)
        if math.isfinite(ci) and ci > worst:
            worst = ci
    return worst


def plot_results(results: dict[str, dict[str, list[float]]], output: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("ggplot")

    labels = list(results.keys())
    avg_cis = [compute_avg_ci(results[k]) * 100 for k in labels]
    median_cis = [compute_median_ci(results[k]) * 100 for k in labels]
    worst_cis = [compute_worst_ci(results[k]) * 100 for k in labels]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    colors = ["#4C72B0", "#DD8452", "#55A868"]

    for ax, values, title in [
        (axes[0], avg_cis, "Average Relative CI (%)"),
        (axes[1], median_cis, "Median Relative CI (%)"),
        (axes[2], worst_cis, "Worst-Case Relative CI (%)"),
    ]:
        bars = ax.bar(labels, values, color=colors, edgecolor="black", linewidth=0.5)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel("Relative CI half-width (%)")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                    f"{val:.2f}%", ha="center", va="bottom", fontsize=9)

    fig.suptitle("Inner vs Outer Repetitions (30 total samples each)",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {output}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Inner vs Outer repetitions comparison")
    parser.add_argument("--exe", required=True, help="Path to Google Benchmark executable")
    parser.add_argument("--output", default="plots/inner_vs_outer.png",
                        help="Output plot path")
    parser.add_argument("--pin-core", type=int, default=None, dest="pin_core",
                        help="Pin benchmark to this CPU core")
    parser.add_argument("--total-samples", type=int, default=30,
                        help="Total samples per strategy (default: 30)")
    args = parser.parse_args()

    total = args.total_samples
    # Compute C's inner/outer split: find factors closest to sqrt
    inner_c = max(2, int(math.sqrt(total)))
    while total % inner_c != 0:
        inner_c -= 1
    outer_c = total // inner_c

    print(f"Running with {total} total samples per strategy")
    results = {}

    print("Strategy A: 1 outer x N inner")
    results["A: 1x" + str(total)] = strategy_a(args.exe, args.pin_core, total)

    print("Strategy B: N outer x 1 inner")
    results["B: " + str(total) + "x1"] = strategy_b(args.exe, args.pin_core, total)

    print(f"Strategy C: {outer_c} outer x {inner_c} inner")
    results[f"C: {outer_c}x{inner_c}"] = strategy_c(args.exe, args.pin_core,
                                                      outer=outer_c, inner=inner_c)

    plot_results(results, args.output)


if __name__ == "__main__":
    main()
