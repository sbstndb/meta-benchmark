"""Meta Benchmark package.

Public API re-exports for convenience.
"""

from .runner import GoogleBenchmarkRunner, MetaConfig, ensure_dir
from .stats import (
    CaseStats,
    TIME_UNIT_TO_NS,
    T_CRITICAL_95,
    Z_CRITICAL_95,
    normalize_to_ns,
    extract_case_values,
    update_stats,
    compute_unstable_cases,
    compute_summary,
)
from .filters import build_filter_regex_for_cases
from .io_utils import write_summary
from .progress import render_progress_line, print_live_progress

__all__ = [
    "GoogleBenchmarkRunner",
    "MetaConfig",
    "ensure_dir",
    "CaseStats",
    "TIME_UNIT_TO_NS",
    "T_CRITICAL_95",
    "Z_CRITICAL_95",
    "normalize_to_ns",
    "extract_case_values",
    "update_stats",
    "compute_unstable_cases",
    "compute_summary",
    "build_filter_regex_for_cases",
    "write_summary",
    "render_progress_line",
    "print_live_progress",
]


