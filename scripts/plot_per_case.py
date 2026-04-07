#!/usr/bin/env python3
"""
Plot: Per-Case Trajectories

Runs N meta-repetitions, collecting raw per-run data. Picks 6 representative
cases and plots running mean + CI bands over time for each case in a 2x3
subplot grid.
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


def running_mean(samples: list[float]) -> list[float]:
    """Compute cumulative running mean."""
    means = []
    total = 0.0
    for i, v in enumerate(samples, 1):
        total += v
        means.append(total / i)
    return means


def running_ci_bands(samples: list[float]) -> tuple[list[float], list[float]]:
    """Compute running CI bands (lower, upper) at each step."""
    lowers = []
    uppers = []
    for k in range(1, len(samples) + 1):
        sub = samples[:k]
        n = len(sub)
        mean = sum(sub) / n
        if n < 2:
            lowers.append(mean)
            uppers.append(mean)
            continue
        var = sum((x - mean) ** 2 for x in sub) / (n - 1)
        stddev = math.sqrt(var)
        critical = T_CRITICAL_95.get(n - 1, Z_CRITICAL_95)
        half = critical * (stddev / math.sqrt(n))
        lowers.append(mean - half)
        uppers.append(mean + half)
    return lowers, uppers


def rel_ci95_half_final(samples: list[float]) -> float:
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
# Case selection
# ---------------------------------------------------------------------------

def pick_representative_cases(all_samples: dict[str, list[float]],
                              n: int = 6) -> list[str]:
    """Pick N representative cases spanning different CI levels.

    Strategy: sort by final relative CI, pick evenly spaced.
    """
    # Filter cases with enough data
    valid = [(name, rel_ci95_half_final(samples))
             for name, samples in all_samples.items()
             if len(samples) >= 2 and math.isfinite(rel_ci95_half_final(samples))]

    if not valid:
        return list(all_samples.keys())[:n]

    valid.sort(key=lambda x: x[1])

    if len(valid) <= n:
        return [v[0] for v in valid]

    # Pick evenly spaced indices
    step = (len(valid) - 1) / (n - 1)
    indices = [round(i * step) for i in range(n)]
    return [valid[i][0] for i in indices]


def shorten_name(name: str, max_len: int = 40) -> str:
    """Shorten a long benchmark name for plot titles."""
    if len(name) <= max_len:
        return name
    # Try to extract the meaningful part
    # e.g., BM_PowGeneric_T<foo_wrapper<uint16_t, uint16_t>, ...>
    # Keep the wrapper name
    import re
    m = re.search(r'<(\w+)<', name)
    if m:
        short = m.group(1)
        # Also get the type
        types = re.findall(r'uint\d+_t', name)
        if types:
            short += f"<{types[0]}>"
        return short
    return name[:max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_trajectories(all_samples: dict[str, list[float]], cases: list[str],
                      output: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("ggplot")

    nrows, ncols = 2, 3
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 9))
    axes_flat = axes.flatten()

    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"]

    for idx, case_name in enumerate(cases):
        if idx >= len(axes_flat):
            break
        ax = axes_flat[idx]
        samples = all_samples[case_name]
        reps = list(range(1, len(samples) + 1))

        means = running_mean(samples)
        lowers, uppers = running_ci_bands(samples)

        color = colors[idx % len(colors)]

        # Plot raw samples
        ax.scatter(reps, samples, alpha=0.3, s=15, color=color, label="Raw", zorder=2)

        # Plot running mean
        ax.plot(reps, means, color=color, linewidth=2, label="Running mean", zorder=3)

        # Plot CI bands
        ax.fill_between(reps, lowers, uppers, alpha=0.2, color=color, label="95% CI")

        final_ci = rel_ci95_half_final(samples)
        title = shorten_name(case_name)
        ax.set_title(f"{title}\nCI={final_ci*100:.2f}%", fontsize=9, fontweight="bold")
        ax.set_xlabel("Repetition")
        ax.set_ylabel("Time (ns)")
        ax.legend(fontsize=7, loc="upper right")

    # Hide any unused subplots
    for idx in range(len(cases), len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle("Per-Case Convergence Trajectories",
                 fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {output}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Per-case convergence trajectories")
    parser.add_argument("--exe", required=True, help="Path to Google Benchmark executable")
    parser.add_argument("--output", default="plots/per_case_trajectories.png",
                        help="Output plot path")
    parser.add_argument("--max-reps", type=int, default=20, dest="max_reps",
                        help="Number of meta-repetitions (default: 20)")
    parser.add_argument("--pin-core", type=int, default=None, dest="pin_core",
                        help="Pin benchmark to this CPU core")
    parser.add_argument("--num-cases", type=int, default=6, dest="num_cases",
                        help="Number of representative cases to plot (default: 6)")
    args = parser.parse_args()

    all_samples: dict[str, list[float]] = defaultdict(list)

    print(f"Running {args.max_reps} meta-repetitions...")
    for rep in range(1, args.max_reps + 1):
        print(f"  Rep {rep}/{args.max_reps}", end="\r", flush=True)
        doc = run_benchmark(args.exe, args.pin_core)
        values = extract_case_values(doc)
        for name, val in values.items():
            all_samples[name].append(val)
    print()

    print(f"Collected data for {len(all_samples)} cases")

    # Pick representative cases
    cases = pick_representative_cases(dict(all_samples), n=args.num_cases)
    print(f"Selected {len(cases)} representative cases:")
    for c in cases:
        ci = rel_ci95_half_final(all_samples[c])
        print(f"  {shorten_name(c, 60)}: final CI = {ci*100:.2f}%")

    plot_trajectories(dict(all_samples), cases, args.output)


if __name__ == "__main__":
    main()
