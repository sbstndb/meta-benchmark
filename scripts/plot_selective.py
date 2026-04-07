#!/usr/bin/env python3
"""
Plot: Selective vs Non-Selective Filtering

Runs meta-benchmark twice:
  1. With selective filtering (re-run only unstable cases after min_reps)
  2. Without selective filtering (re-run ALL cases every time)

Compares: wall time, stable cases at convergence, average CI.
Generates a 3-panel comparison bar chart.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

# ---------------------------------------------------------------------------
# Inline stats
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

# RE2 metacharacters that need escaping for Google Benchmark's --benchmark_filter
_RE2_META = frozenset(r"\.+*?()[]{}^$|")


def _escape_for_re2(s: str) -> str:
    return "".join(f"\\{c}" if c in _RE2_META else c for c in s)


def build_filter_regex(cases: list[str]) -> str | None:
    if not cases:
        return None
    escaped = [_escape_for_re2(c) for c in cases]
    return "^(" + "|".join(escaped) + ")$"


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

def run_benchmark(exe: str, pin_core: int | None, filter_regex: str | None = None,
                  min_time: float = 0.05) -> dict:
    args = [exe, "--benchmark_format=json", f"--benchmark_min_time={min_time}s",
            "--benchmark_enable_random_interleaving=true"]
    if filter_regex:
        args.append(f"--benchmark_filter={filter_regex}")

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
# Meta-benchmark modes
# ---------------------------------------------------------------------------

def run_nonselective(exe: str, pin_core: int | None, max_reps: int,
                     ci_threshold: float, min_reps: int) -> dict:
    """Run ALL cases every repetition (no selective filtering)."""
    print("  [Non-selective] Running all cases every repetition...")
    all_samples: dict[str, list[float]] = defaultdict(list)

    t0 = time.monotonic()
    for rep in range(1, max_reps + 1):
        print(f"    Rep {rep}/{max_reps}", end="\r", flush=True)
        doc = run_benchmark(exe, pin_core)
        for name, val in extract_case_values(doc).items():
            all_samples[name].append(val)
    elapsed = time.monotonic() - t0
    print()

    # Compute final stats
    total_cases = len(all_samples)
    cis = []
    num_stable = 0
    for name, samples in all_samples.items():
        ci = rel_ci95_half(samples)
        if math.isfinite(ci):
            cis.append(ci)
            if len(samples) >= min_reps and ci <= ci_threshold:
                num_stable += 1

    avg_ci = sum(cis) / len(cis) if cis else float("nan")

    return {
        "wall_time": elapsed,
        "total_cases": total_cases,
        "stable_cases": num_stable,
        "avg_ci": avg_ci,
    }


def run_selective(exe: str, pin_core: int | None, max_reps: int,
                  ci_threshold: float, min_reps: int) -> dict:
    """Run with selective filtering: after min_reps, only re-run unstable cases."""
    print("  [Selective] Running with selective filtering...")
    all_samples: dict[str, list[float]] = defaultdict(list)

    t0 = time.monotonic()
    for rep in range(1, max_reps + 1):
        # Determine which cases to run
        if rep == 1:
            filter_regex = None  # first run: all cases
        else:
            # Find unstable cases
            unstable = []
            for name, samples in all_samples.items():
                if len(samples) < min_reps:
                    unstable.append(name)
                    continue
                ci = rel_ci95_half(samples)
                if ci > ci_threshold:
                    unstable.append(name)

            if not unstable:
                print(f"    All cases stable at rep {rep}, stopping early.")
                break
            filter_regex = build_filter_regex(unstable)
            print(f"    Rep {rep}/{max_reps}: re-running {len(unstable)} unstable cases",
                  end="\r", flush=True)

        doc = run_benchmark(exe, pin_core, filter_regex=filter_regex)
        for name, val in extract_case_values(doc).items():
            all_samples[name].append(val)

    elapsed = time.monotonic() - t0
    print()

    # Compute final stats
    total_cases = len(all_samples)
    cis = []
    num_stable = 0
    for name, samples in all_samples.items():
        ci = rel_ci95_half(samples)
        if math.isfinite(ci):
            cis.append(ci)
            if len(samples) >= min_reps and ci <= ci_threshold:
                num_stable += 1

    avg_ci = sum(cis) / len(cis) if cis else float("nan")

    return {
        "wall_time": elapsed,
        "total_cases": total_cases,
        "stable_cases": num_stable,
        "avg_ci": avg_ci,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_comparison(sel: dict, nonsel: dict, output: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("ggplot")

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    labels = ["Selective", "Non-selective"]
    colors = ["#55A868", "#C44E52"]

    # Panel 1: Wall time
    ax = axes[0]
    vals = [sel["wall_time"], nonsel["wall_time"]]
    bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_title("Wall Time (seconds)", fontweight="bold")
    ax.set_ylabel("Seconds")
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                f"{val:.1f}s", ha="center", va="bottom", fontsize=10)

    # Panel 2: Stable cases
    ax = axes[1]
    total = max(sel["total_cases"], nonsel["total_cases"])
    vals = [sel["stable_cases"], nonsel["stable_cases"]]
    bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.5)
    ax.axhline(y=total, color="gray", linestyle="--", alpha=0.5,
               label=f"Total ({total})")
    ax.set_title("Stable Cases", fontweight="bold")
    ax.set_ylabel("Count")
    ax.legend(fontsize=9)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                str(val), ha="center", va="bottom", fontsize=10)

    # Panel 3: Average CI
    ax = axes[2]
    vals = [sel["avg_ci"] * 100, nonsel["avg_ci"] * 100]
    bars = ax.bar(labels, vals, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_title("Average Relative CI (%)", fontweight="bold")
    ax.set_ylabel("Relative CI half-width (%)")
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{val:.2f}%", ha="center", va="bottom", fontsize=10)

    fig.suptitle("Selective vs Non-Selective Filtering",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {output}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Selective vs Non-selective filtering comparison")
    parser.add_argument("--exe", required=True, help="Path to Google Benchmark executable")
    parser.add_argument("--output", default="plots/selective_vs_nonselective.png",
                        help="Output plot path")
    parser.add_argument("--max-reps", type=int, default=15, dest="max_reps",
                        help="Max meta-repetitions (default: 15)")
    parser.add_argument("--pin-core", type=int, default=None, dest="pin_core",
                        help="Pin benchmark to this CPU core")
    parser.add_argument("--ci-threshold", type=float, default=0.03, dest="ci_threshold",
                        help="Relative CI threshold (default: 0.03 = 3%%)")
    parser.add_argument("--min-reps-stable", type=int, default=5, dest="min_reps_stable",
                        help="Min reps before considering stability (default: 5)")
    args = parser.parse_args()

    print(f"Max reps: {args.max_reps}, CI threshold: {args.ci_threshold*100:.0f}%")
    print()

    # Run selective first
    sel_result = run_selective(args.exe, args.pin_core, args.max_reps,
                               args.ci_threshold, args.min_reps_stable)
    print(f"  Selective: {sel_result['wall_time']:.1f}s, "
          f"stable={sel_result['stable_cases']}/{sel_result['total_cases']}, "
          f"avg_ci={sel_result['avg_ci']*100:.2f}%")
    print()

    # Run non-selective
    nonsel_result = run_nonselective(args.exe, args.pin_core, args.max_reps,
                                      args.ci_threshold, args.min_reps_stable)
    print(f"  Non-selective: {nonsel_result['wall_time']:.1f}s, "
          f"stable={nonsel_result['stable_cases']}/{nonsel_result['total_cases']}, "
          f"avg_ci={nonsel_result['avg_ci']*100:.2f}%")

    plot_comparison(sel_result, nonsel_result, args.output)


if __name__ == "__main__":
    main()
