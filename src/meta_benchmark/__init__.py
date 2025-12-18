"""Meta Benchmark package.

Run Google Benchmark binaries with statistical meta-repetitions until results stabilize.
"""

__version__ = "0.1.0"

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
from .cpu_affinity import (
    get_cpu_count,
    is_affinity_supported,
    set_affinity,
    set_process_affinity,
    validate_core_id,
)
from .exceptions import BenchmarkError
from .logging_config import logger, setup_logging
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
from .io_utils import write_json_atomic, write_summary
from .progress import render_progress_line, print_live_progress

__all__ = [
    "__version__",
    # Constants
    "DEFAULT_MAX_META_REPS",
    "DEFAULT_MIN_META_REPS",
    "DEFAULT_MIN_TIME_SEC",
    "DEFAULT_OUTPUT_FILE",
    "DEFAULT_REL_CI_THRESHOLD",
    "EXIT_ERROR",
    "EXIT_INTERRUPTED",
    "EXIT_NO_BENCHMARKS",
    "EXIT_SUCCESS",
    # CPU affinity
    "get_cpu_count",
    "is_affinity_supported",
    "set_affinity",
    "set_process_affinity",
    "validate_core_id",
    # Classes and exceptions
    "BenchmarkError",
    "logger",
    "setup_logging",
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
    "write_json_atomic",
    "write_summary",
    "render_progress_line",
    "print_live_progress",
]


