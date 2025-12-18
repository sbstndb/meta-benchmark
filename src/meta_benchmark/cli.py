from __future__ import annotations

import argparse
import sys
import time

from .constants import (
    DEFAULT_MAX_META_REPS,
    DEFAULT_MIN_META_REPS,
    DEFAULT_MIN_TIME_SEC,
    DEFAULT_OUTPUT_FILE,
    DEFAULT_REL_CI_THRESHOLD,
    EXIT_ERROR,
    EXIT_INTERRUPTED,
    EXIT_NO_BENCHMARKS,
    EXIT_SUCCESS,
)
from .exceptions import BenchmarkError
from .filters import build_filter_regex_for_cases
from .io_utils import write_summary
from .logging_config import logger, setup_logging
from .progress import print_live_progress, render_progress_line
from .runner import GoogleBenchmarkRunner, MetaConfig, ensure_dir
from .stats import (
    CaseStats,
    compute_summary,
    compute_unstable_cases,
    extract_case_values,
    update_stats,
)


def parse_args(argv: list[str] | None = None) -> MetaConfig:
    p = argparse.ArgumentParser(description="Google Benchmark meta-repetition runner")
    p.add_argument("--exe", required=True, help="Path to Google Benchmark executable")
    p.add_argument(
        "--min-meta-reps",
        type=int,
        default=DEFAULT_MIN_META_REPS,
        dest="min_meta_reps",
        help=f"Minimum meta repetitions before evaluating stability (default: {DEFAULT_MIN_META_REPS})",
    )
    p.add_argument(
        "--max-meta-reps",
        type=int,
        default=DEFAULT_MAX_META_REPS,
        dest="max_meta_reps",
        help=f"Maximum meta repetitions (default: {DEFAULT_MAX_META_REPS})",
    )
    p.add_argument(
        "--rel-ci-threshold",
        type=float,
        default=DEFAULT_REL_CI_THRESHOLD,
        dest="rel_ci_threshold",
        help=f"Target relative CI half-width (default: {DEFAULT_REL_CI_THRESHOLD} = {DEFAULT_REL_CI_THRESHOLD*100:.0f}%%)",
    )
    p.add_argument(
        "--min-time-sec",
        type=float,
        default=DEFAULT_MIN_TIME_SEC,
        dest="min_time_sec",
        help=f"Forwarded to Google Benchmark --benchmark_min_time (default: {DEFAULT_MIN_TIME_SEC})",
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
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        dest="output_file",
        help=f"Summary JSON output path (default: {DEFAULT_OUTPUT_FILE})",
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
    p.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Enable verbose/debug logging"
    )
    p.add_argument(
        "-q", "--quiet", action="store_true", default=False, help="Suppress info messages, only show warnings and errors"
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
        verbose=args.verbose,
    ), args.verbose, args.quiet


def get_stability_state(
    stats: dict[str, CaseStats], cfg: MetaConfig
) -> tuple[list[str], set[str]]:
    """Compute unstable and stable case sets.

    Returns:
        Tuple of (unstable_cases, stable_cases)
    """
    unstable = compute_unstable_cases(
        stats,
        rel_ci_threshold=cfg.rel_ci_threshold,
        min_meta_reps=cfg.min_meta_reps,
    )
    stable = set(stats.keys()) - set(unstable)
    return unstable, stable


def validate_config(cfg: MetaConfig) -> None:
    """Validate configuration argument consistency."""
    if cfg.min_meta_reps <= 0:
        raise ValueError("--min-meta-reps must be > 0")
    if cfg.max_meta_reps < cfg.min_meta_reps:
        raise ValueError("--max-meta-reps must be >= --min-meta-reps")
    if not (0 < cfg.rel_ci_threshold <= 1):
        raise ValueError("--rel-ci-threshold must be in (0, 1]")
    if cfg.min_time_sec <= 0:
        raise ValueError("--min-time-sec must be > 0")
    if cfg.pin_core is not None and cfg.pin_core < 0:
        raise ValueError("--pin-core must be >= 0")
    if cfg.warmup_sec is not None and cfg.warmup_sec < 0:
        raise ValueError("--warmup-sec must be >= 0")
    if cfg.repetitions is not None and cfg.repetitions <= 0:
        raise ValueError("--repetitions must be > 0")


def run_meta_benchmark_loop(
    runner: GoogleBenchmarkRunner,
    cfg: MetaConfig,
    all_stats: dict[str, CaseStats],
) -> tuple[int, set[str]]:
    """Main benchmark loop separated for testability.

    Returns:
        Tuple of (total_runs, stable_cases)
    """
    stable_cases: set[str] = set()
    total_runs = 0

    while True:
        total_runs += 1
        logger.debug("Starting meta-run %d/%d", total_runs, cfg.max_meta_reps)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        raw_path = None
        if cfg.save_raw_dir:
            raw_path = f"{cfg.save_raw_dir}/run_{total_runs}_{timestamp}.json"

        # First run or filtered rerun
        if total_runs == 1:
            filter_regex = cfg.base_filter
            logger.debug("First run, using base filter: %s", filter_regex or "(none)")
        else:
            # Find unstable cases
            unstable, stable_cases = get_stability_state(all_stats, cfg)
            if not unstable:
                logger.debug("All cases stable, stopping")
                break
            filter_regex = build_filter_regex_for_cases(unstable)
            logger.debug("Re-running %d unstable cases", len(unstable))

        json_doc = runner.run(
            filter_regex=filter_regex,
            min_time_sec=cfg.min_time_sec,
            extra_args=cfg.extra_gb_args,
            save_json_path=raw_path,
        )

        values = extract_case_values(json_doc)
        if not values:
            if total_runs == 1:
                logger.error("No benchmarks matched. Check --exe and --base-filter.")
                return total_runs, stable_cases
            logger.debug("No values extracted, stopping")
            break

        update_stats(all_stats, values)
        logger.debug("Updated stats for %d cases", len(values))

        # Snapshot summary at each iteration
        _, _stable_now = get_stability_state(all_stats, cfg)
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
            _, stable_cases = get_stability_state(all_stats, cfg)
            break

    return total_runs, stable_cases


def handle_keyboard_interrupt(
    all_stats: dict[str, CaseStats],
    cfg: MetaConfig,
) -> int:
    """Graceful handling of Ctrl+C interruption."""
    _, _stable_now = get_stability_state(all_stats, cfg)

    if cfg.live_progress and sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()

    write_summary(cfg.output_file, cfg, all_stats, _stable_now)
    num_cases = len(all_stats)
    num_stable = len(_stable_now)
    # Infer total_runs from max count in stats
    total_runs = max((s.count for s in all_stats.values()), default=0)
    print(f"Meta runs: {total_runs}, cases: {num_cases}, stable: {num_stable}/{num_cases}")
    return EXIT_INTERRUPTED


def handle_benchmark_error(e: BenchmarkError) -> int:
    """Handle benchmark execution errors."""
    print(f"Benchmark error: {e}", file=sys.stderr)
    return EXIT_ERROR


def finalize_and_report(
    all_stats: dict[str, CaseStats],
    stable_cases: set[str],
    cfg: MetaConfig,
    total_runs: int,
) -> None:
    """Finalize benchmark run and output report."""
    # Finish the live line and move to newline
    if cfg.live_progress and sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()

    write_summary(cfg.output_file, cfg, all_stats, stable_cases)
    num_cases = len(all_stats)
    num_stable = len(stable_cases)
    print(f"Meta runs: {total_runs}, cases: {num_cases}, stable: {num_stable}/{num_cases}")


def main(argv: list[str] | None = None) -> int:
    cfg, verbose, quiet = parse_args(argv)

    # Set up logging before anything else
    setup_logging(verbose=verbose, quiet=quiet)

    logger.info("Starting meta-benchmark with exe=%s", cfg.exe)
    logger.debug(
        "Config: min_meta_reps=%d, max_meta_reps=%d, rel_ci_threshold=%.3f",
        cfg.min_meta_reps,
        cfg.max_meta_reps,
        cfg.rel_ci_threshold,
    )

    try:
        validate_config(cfg)
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        return EXIT_ERROR

    ensure_dir(cfg.save_raw_dir)

    try:
        runner = GoogleBenchmarkRunner(
            cfg.exe,
            pin_core=cfg.pin_core,
            repetitions=cfg.repetitions,
            warmup_sec=cfg.warmup_sec,
        )
    except FileNotFoundError as e:
        logger.error("Failed to initialize runner: %s", e)
        return EXIT_ERROR

    all_stats: dict[str, CaseStats] = {}

    try:
        total_runs, stable_cases = run_meta_benchmark_loop(runner, cfg, all_stats)
        # Check for early exit due to no benchmarks matched
        if total_runs == 1 and not all_stats:
            return EXIT_NO_BENCHMARKS
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return handle_keyboard_interrupt(all_stats, cfg)
    except BenchmarkError as e:
        logger.error("Benchmark error: %s", e)
        return handle_benchmark_error(e)

    finalize_and_report(all_stats, stable_cases, cfg, total_runs)
    logger.info("Completed successfully")
    return EXIT_SUCCESS


