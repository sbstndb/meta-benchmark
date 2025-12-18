from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any

from .exceptions import BenchmarkError
from .runner import MetaConfig
from .stats import CaseStats


def write_json_atomic(output_file: str, data: Any) -> None:
    """Write JSON data atomically to avoid corruption.

    Writes to a temporary file first, then atomically replaces the target file.
    This ensures the output file is never in a partially-written state.
    """
    dir_path = os.path.dirname(output_file) or "."
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=dir_path,
            delete=False,
            suffix=".tmp",
            encoding="utf-8",
        ) as f:
            json.dump(data, f, indent=2)
            temp_path = f.name
        os.replace(temp_path, output_file)  # Atomic on POSIX
    except OSError as e:
        # Clean up temp file if it exists
        if temp_path and os.path.exists(temp_path):
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
        raise BenchmarkError(
            f"Failed to write to {output_file}",
            error=str(e),
        ) from e


def write_summary(output_file: str, config: MetaConfig, stats: dict[str, CaseStats], stable_set: set[str]) -> None:
    out_cases: dict[str, dict[str, float]] = {}
    for name, s in sorted(stats.items()):
        out_cases[name] = {
            "count": s.count,
            "mean_ns": s.mean,
            "stddev_ns": s.stddev if s.count >= 2 else 0.0,
            "rel_ci95_half": s.rel_ci95_half() if s.count >= 2 else float("inf"),
            "stable": name in stable_set,
        }
    payload = {
        "version": 1,
        "params": {
            "rel_ci_threshold": config.rel_ci_threshold,
            "min_meta_reps": config.min_meta_reps,
            "max_meta_reps": config.max_meta_reps,
        },
        "cases": out_cases,
    }
    write_json_atomic(output_file, payload)


