from __future__ import annotations

import argparse
import sys
import time
from typing import Dict, Optional

from .filters import build_filter_regex_for_cases
from .io_utils import write_summary
from .progress import print_live_progress, render_progress_line
from .runner import GoogleBenchmarkRunner, MetaConfig, ensure_dir
from .stats import (
    CaseStats,
    compute_summary,
    compute_unstable_cases,
    extract_case_values,
    update_stats,
)


def parse_args(argv: Optional[list[str]] = None) -> MetaConfig:
    p = argparse.ArgumentParser(description="Google Benchmark meta-repetition runner")
    p.add_argument("--exe", required=True, help="Path to Google Benchmark executable")
    p.add_argument(
        "--min-meta-reps",
        type=int,
        default=5,
        dest="min_meta_reps",
        help="Minimum meta repetitions before evaluating stability",
    )
    p.add_argument(
        "--max-meta-reps", type=int, default=30, dest="max_meta_reps", help="Maximum meta repetitions"
    )
    p.add_argument(
        "--rel-ci-threshold",
        type=float,
        default=0.03,
        dest="rel_ci_threshold",
        help="Target relative CI half-width (e.g. 0.03 = 3%%)",
    )
    p.add_argument(
        "--min-time-sec",
        type=float,
        default=0.05,
        dest="min_time_sec",
        help="Forwarded to Google Benchmark --benchmark_min_time",
    )
    p.add_argument(
        "--warmup-sec",
        type=float,
        default=None,
        dest="warmup_sec",
        help="Optional warmup time in seconds (forwards --benchmark_min_warmup_time)",
    )
    p.add_argument(
        "--base-filter",
        type=str,
        default=None,
        dest="base_filter",
        help="Optional base filter (regex) to select a subset of benchmarks",
    )
    p.add_argument(
        "--gb-arg",
        action="append",
        default=[],
        dest="extra_gb_args",
        help="Extra args passed to the benchmark executable (repeatable)",
    )
    p.add_argument(
        "--output", type=str, default="meta_results.json", dest="output_file", help="Summary JSON output path"
    )
    p.add_argument(
        "--save-raw",
        type=str,
        default=None,
        dest="save_raw_dir",
        help="Directory to store raw JSON outputs for each run",
    )
    p.add_argument(
        "--pin-core", type=int, default=None, dest="pin_core", help="Pin benchmark process to a given CPU core index (Linux)"
    )
    p.add_argument(
        "--repetitions",
        type=int,
        default=None,
        dest="repetitions",
        help="If set, passes --benchmark_repetitions=N to Google Benchmark",
    )
    p.add_argument(
        "--no-live", action="store_true", default=False, dest="no_live", help="Disable live single-line progress output"
    )
    args = p.parse_args(argv)

    return MetaConfig(
        exe=args.exe,
        min_meta_reps=args.min_meta_reps,
        max_meta_reps=args.max_meta_reps,
        rel_ci_threshold=args.rel_ci_threshold,
        min_time_sec=args.min_time_sec,
        warmup_sec=args.warmup_sec,
        base_filter=args.base_filter,
        extra_gb_args=args.extra_gb_args,
        output_file=args.output_file,
        save_raw_dir=args.save_raw_dir,
        pin_core=args.pin_core,
        repetitions=args.repetitions,
        live_progress=(not args.no_live),
    )


def main(argv: Optional[list[str]] = None) -> int:
    cfg = parse_args(argv)
    ensure_dir(cfg.save_raw_dir)

    runner = GoogleBenchmarkRunner(
        cfg.exe,
        pin_core=cfg.pin_core,
        repetitions=cfg.repetitions,
        warmup_sec=cfg.warmup_sec,
    )

    all_stats: Dict[str, CaseStats] = {}
    stable_cases: set = set()

    total_runs = 0
    try:
        while True:
            total_runs += 1
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            raw_path = None
            if cfg.save_raw_dir:
                raw_path = f"{cfg.save_raw_dir}/run_{total_runs}_{timestamp}.json"

            # First run or filtered rerun
            if total_runs == 1:
                filter_regex = cfg.base_filter
            else:
                # Find unstable cases
                unstable = compute_unstable_cases(
                    all_stats, rel_ci_threshold=cfg.rel_ci_threshold, min_meta_reps=cfg.min_meta_reps
                )
                # stable set is all known minus unstable
                stable_cases = set(all_stats.keys()) - set(unstable)
                if not unstable:
                    break
                filter_regex = build_filter_regex_for_cases(unstable)

            json_doc = runner.run(
                filter_regex=filter_regex,
                min_time_sec=cfg.min_time_sec,
                extra_args=cfg.extra_gb_args,
                save_json_path=raw_path,
            )

            values = extract_case_values(json_doc)
            if not values:
                if total_runs == 1:
                    print("No benchmarks matched. Check --exe and --base-filter.", file=sys.stderr)
                    return 2
                break

            update_stats(all_stats, values)

            # Snapshot summary at each iteration
            _unstable_now = compute_unstable_cases(
                all_stats, rel_ci_threshold=cfg.rel_ci_threshold, min_meta_reps=cfg.min_meta_reps
            )
            _stable_now = set(all_stats.keys()) - set(_unstable_now)
            write_summary(cfg.output_file, cfg, all_stats, _stable_now)

            # Live progress update after each run
            num_cases, num_stable, worst, num_unstable = compute_summary(
                all_stats, cfg.rel_ci_threshold, cfg.min_meta_reps
            )
            print_live_progress(
                render_progress_line(
                    total_runs, cfg.max_meta_reps, num_cases, num_stable, worst, num_unstable
                ),
                enabled=cfg.live_progress,
            )

            if total_runs >= cfg.max_meta_reps:
                unstable = compute_unstable_cases(
                    all_stats, rel_ci_threshold=cfg.rel_ci_threshold, min_meta_reps=cfg.min_meta_reps
                )
                stable_cases = set(all_stats.keys()) - set(unstable)
                break
    except KeyboardInterrupt:
        # Graceful snapshot on Ctrl+C
        _unstable_now = compute_unstable_cases(
            all_stats, rel_ci_threshold=cfg.rel_ci_threshold, min_meta_reps=cfg.min_meta_reps
        )
        _stable_now = set(all_stats.keys()) - set(_unstable_now)
        if cfg.live_progress and sys.stdout.isatty():
            sys.stdout.write("\n")
            sys.stdout.flush()
        write_summary(cfg.output_file, cfg, all_stats, _stable_now)
        num_cases = len(all_stats)
        num_stable = len(_stable_now)
        print(f"Meta runs: {total_runs}, cases: {num_cases}, stable: {num_stable}/{num_cases}")
        return 130

    # Finish the live line and move to newline
    if cfg.live_progress and sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()

    write_summary(cfg.output_file, cfg, all_stats, stable_cases)
    num_cases = len(all_stats)
    num_stable = len(stable_cases)
    print(f"Meta runs: {total_runs}, cases: {num_cases}, stable: {num_stable}/{num_cases}")
    return 0


