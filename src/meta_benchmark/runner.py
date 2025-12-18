from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess
import tempfile
from dataclasses import dataclass

from .cpu_affinity import create_affinity_preexec, set_process_affinity, validate_core_id
from .exceptions import BenchmarkError
from .logging_config import logger


@dataclass
class MetaConfig:
    exe: str
    min_meta_reps: int
    max_meta_reps: int
    rel_ci_threshold: float
    min_time_sec: float
    warmup_sec: float | None
    base_filter: str | None
    extra_gb_args: list[str]
    output_file: str
    save_raw_dir: str | None
    pin_core: int | None
    repetitions: int | None
    live_progress: bool
    timeout_sec: float
    verbose: bool = False


class GoogleBenchmarkRunner:
    def __init__(
        self,
        exe_path: str,
        pin_core: int | None = None,
        repetitions: int | None = None,
        warmup_sec: float | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        self.exe_path = exe_path
        self.pin_core = pin_core
        self.repetitions = repetitions
        self.warmup_sec = warmup_sec
        self.timeout_sec = timeout_sec
        if not os.path.isfile(exe_path) or not os.access(exe_path, os.X_OK):
            raise FileNotFoundError(f"Executable not found or not executable: {exe_path}")
        logger.debug("Initialized GoogleBenchmarkRunner with exe=%s", exe_path)

    def run(
        self,
        *,
        filter_regex: str | None,
        min_time_sec: float,
        extra_args: list[str],
        save_json_path: str | None,
    ) -> dict:
        args = [self.exe_path, "--benchmark_format=json"]
        if filter_regex:
            args.append(f"--benchmark_filter={filter_regex}")
        if min_time_sec is not None:
            args.append(f"--benchmark_min_time={min_time_sec}")
        if self.warmup_sec is not None and self.warmup_sec > 0:
            args.append(f"--benchmark_min_warmup_time={self.warmup_sec}")
        # Safe defaults to reduce instability
        args.extend([
            "--benchmark_counters_tabular=false",
            "--benchmark_enable_random_interleaving=true",
        ])
        if self.repetitions is not None and self.repetitions > 0:
            args.append(f"--benchmark_repetitions={self.repetitions}")
        args.extend(extra_args)

        logger.debug("Running benchmark with args: %s", " ".join(args))

        # Set up CPU affinity (cross-platform)
        preexec_fn = create_affinity_preexec(self.pin_core)
        is_windows = platform.system() == "Windows"

        try:
            if is_windows:
                # On Windows, start process then set affinity
                with subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                ) as popen_proc:
                    # Set affinity on the spawned process
                    if self.pin_core is not None and validate_core_id(self.pin_core):
                        set_process_affinity(popen_proc.pid, self.pin_core)
                    stdout_str, stderr_str = popen_proc.communicate(timeout=self.timeout_sec)
                    returncode = popen_proc.returncode
            else:
                # On POSIX, use preexec_fn for child process affinity
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    preexec_fn=preexec_fn,
                    check=False,
                    timeout=self.timeout_sec,
                )
                stdout_str = result.stdout or ""
                stderr_str = result.stderr or ""
                returncode = result.returncode
        except subprocess.TimeoutExpired as e:
            raise BenchmarkError(
                "Benchmark timed out",
                command=args,
                error=str(e),
            ) from e
        except OSError as e:
            raise BenchmarkError(
                "Failed to execute benchmark",
                command=args,
                error=str(e),
            ) from e

        if returncode != 0:
            raise BenchmarkError(
                f"Benchmark failed (code {returncode})",
                stderr=stderr_str,
                command=args,
            )

        stdout = stdout_str.strip()
        if not stdout:
            data: dict = {"benchmarks": []}
            logger.debug("Benchmark returned empty output")
        else:
            try:
                data = json.loads(stdout)
                num_benchmarks = len(data.get("benchmarks", []))
                logger.debug("Benchmark completed: %d results parsed", num_benchmarks)
            except json.JSONDecodeError as e:
                raise BenchmarkError(
                    "Invalid JSON output from benchmark",
                    stdout=stdout[:500] if len(stdout) > 500 else stdout,
                    error=str(e),
                    command=args,
                ) from e

        if save_json_path is not None:
            _write_json_atomic(save_json_path, data)
            logger.debug("Saved raw results to %s", save_json_path)

        return data


def _write_json_atomic(output_file: str, data: dict) -> None:
    """Write JSON data atomically to avoid corruption."""
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
        if temp_path and os.path.exists(temp_path):
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
        raise BenchmarkError(
            f"Failed to save benchmark results to {output_file}",
            error=str(e),
        ) from e


def ensure_dir(path: str | None) -> None:
    if path is None:
        return
    os.makedirs(path, exist_ok=True)


