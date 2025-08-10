from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MetaConfig:
    exe: str
    min_meta_reps: int
    max_meta_reps: int
    rel_ci_threshold: float
    min_time_sec: float
    warmup_sec: Optional[float]
    base_filter: Optional[str]
    extra_gb_args: List[str]
    output_file: str
    save_raw_dir: Optional[str]
    pin_core: Optional[int]
    repetitions: Optional[int]
    live_progress: bool


class GoogleBenchmarkRunner:
    def __init__(
        self,
        exe_path: str,
        pin_core: Optional[int] = None,
        repetitions: Optional[int] = None,
        warmup_sec: Optional[float] = None,
    ) -> None:
        self.exe_path = exe_path
        self.pin_core = pin_core
        self.repetitions = repetitions
        self.warmup_sec = warmup_sec
        if not os.path.isfile(exe_path) or not os.access(exe_path, os.X_OK):
            raise FileNotFoundError(f"Executable not found or not executable: {exe_path}")

    def run(
        self,
        *,
        filter_regex: Optional[str],
        min_time_sec: float,
        extra_args: List[str],
        save_json_path: Optional[str],
    ) -> Dict:
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

        preexec_fn = None
        if self.pin_core is not None and hasattr(os, "sched_setaffinity"):
            core_id = int(self.pin_core)

            def _set_affinity() -> None:
                try:
                    os.sched_setaffinity(0, {core_id})
                except OSError:
                    # Best-effort; affinity setting may require privileges or differ by platform
                    return

            preexec_fn = _set_affinity

        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=preexec_fn,
            check=False,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            raise RuntimeError(f"Benchmark process failed with code {proc.returncode}")

        stdout = (proc.stdout or "").strip()
        if not stdout:
            data: Dict = {"benchmarks": []}
        else:
            import json

            data = json.loads(stdout)

        if save_json_path is not None:
            import json

            with open(save_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        return data


def ensure_dir(path: Optional[str]) -> None:
    if path is None:
        return
    os.makedirs(path, exist_ok=True)


