"""Default constants for meta-benchmark configuration."""

from __future__ import annotations

# Meta-repetition limits
DEFAULT_MIN_META_REPS = 5
DEFAULT_MAX_META_REPS = 30

# Statistical thresholds
DEFAULT_REL_CI_THRESHOLD = 0.03  # 3% relative confidence interval half-width

# Benchmark timing
DEFAULT_MIN_TIME_SEC = 0.05  # Minimum time per benchmark iteration

# Output
DEFAULT_OUTPUT_FILE = "meta_results.json"

# Exit codes
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NO_BENCHMARKS = 2
EXIT_INTERRUPTED = 130
