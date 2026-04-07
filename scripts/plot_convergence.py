#!/usr/bin/env python3
"""
Plot: Convergence of Meta-Repetitions

Runs N meta-repetitions (re-running ALL cases every time, no selective filtering).
After each rep, computes cumulative stats. Generates a 3-panel plot:
  1. Stable cases (count) vs rep number
  2. Average relative CI vs rep number
  3. Worst relative CI vs rep number
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

def run_benchmark(exe: str, pin_core: int | None,
                  min_time: float = 0.05) -> dict:
    args = [exe, "--benchmark_format=json", f"--benchmark_min_time={min_time}s",
            "--benchmark_enable_random_interleaving=true"]

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
# Main logic
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Convergence of meta-repetitions")
    parser.add_argument("--exe", required=True, help="Path to Google Benchmark executable")
    parser.add_argument("--output", default="plots/convergence.png",
                        help="Output plot path")
    parser.add_argument("--max-reps", type=int, default=20, dest="max_reps",
                        help="Number of meta-repetitions (default: 20)")
    parser.add_argument("--pin-core", type=int, default=None, dest="pin_core",
                        help="Pin benchmark to this CPU core")
    parser.add_argument("--ci-threshold", type=float, default=0.03, dest="ci_threshold",
                        help="Relative CI threshold for stability (default: 0.03 = 3%%)")
    parser.add_argument("--min-reps-stable", type=int, default=5, dest="min_reps_stable",
                        help="Minimum reps before a case can be considered stable (default: 5)")
    args = parser.parse_args()

    # Cumulative data: case_name -> list of all samples so far
    all_samples: dict[str, list[float]] = defaultdict(list)

    # Track metrics after each repetition
    rep_numbers: list[int] = []
    stable_counts: list[int] = []
    avg_cis: list[float] = []
    worst_cis: list[float] = []
    total_cases = 0

    print(f"Running {args.max_reps} meta-repetitions (all cases each time)...")

    for rep in range(1, args.max_reps + 1):
        print(f"  Rep {rep}/{args.max_reps} ...", end=" ", flush=True)
        doc = run_benchmark(args.exe, args.pin_core)
        values = extract_case_values(doc)
        if not values:
            print("no results, skipping")
            continue

        for name, val in values.items():
            all_samples[name].append(val)

        total_cases = len(all_samples)

        # Compute per-case CIs
        cis = []
        num_stable = 0
        worst_ci = 0.0
        for name, samples in all_samples.items():
            ci = rel_ci95_half(samples)
            if math.isfinite(ci):
                cis.append(ci)
                if ci > worst_ci:
                    worst_ci = ci
                if len(samples) >= args.min_reps_stable and ci <= args.ci_threshold:
                    num_stable += 1

        avg_ci = sum(cis) / len(cis) if cis else float("nan")

        rep_numbers.append(rep)
        stable_counts.append(num_stable)
        avg_cis.append(avg_ci * 100)  # percent
        worst_cis.append(worst_ci * 100)

        print(f"stable={num_stable}/{total_cases}, "
              f"avg_ci={avg_ci*100:.2f}%, worst_ci={worst_ci*100:.2f}%")

    # --- Plot ---
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("ggplot")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    color = "#4C72B0"

    # Panel 1: Stable cases
    ax = axes[0]
    ax.plot(rep_numbers, stable_counts, "o-", color=color, markersize=4)
    ax.axhline(y=total_cases, color="green", linestyle="--", alpha=0.7,
               label=f"Total cases ({total_cases})")
    ax.set_xlabel("Meta-repetition")
    ax.set_ylabel("Stable cases")
    ax.set_title("Stable Cases vs Repetitions", fontweight="bold")
    ax.legend(fontsize=9)
    ax.set_ylim(bottom=0)

    # Panel 2: Average CI
    ax = axes[1]
    ax.plot(rep_numbers, avg_cis, "o-", color="#DD8452", markersize=4)
    ax.axhline(y=args.ci_threshold * 100, color="red", linestyle="--", alpha=0.7,
               label=f"Threshold ({args.ci_threshold*100:.0f}%)")
    ax.set_xlabel("Meta-repetition")
    ax.set_ylabel("Average relative CI (%)")
    ax.set_title("Average CI vs Repetitions", fontweight="bold")
    ax.legend(fontsize=9)

    # Panel 3: Worst CI
    ax = axes[2]
    ax.plot(rep_numbers, worst_cis, "o-", color="#C44E52", markersize=4)
    ax.axhline(y=args.ci_threshold * 100, color="red", linestyle="--", alpha=0.7,
               label=f"Threshold ({args.ci_threshold*100:.0f}%)")
    ax.set_xlabel("Meta-repetition")
    ax.set_ylabel("Worst relative CI (%)")
    ax.set_title("Worst CI vs Repetitions", fontweight="bold")
    ax.legend(fontsize=9)

    fig.suptitle(f"Convergence over {args.max_reps} Meta-Repetitions",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    fig.savefig(args.output, dpi=150, bbox_inches="tight")
    print(f"\nSaved plot to {args.output}")


if __name__ == "__main__":
    main()
