import sys
from typing import Optional, Tuple


def render_progress_line(
    run_idx: int,
    max_runs: int,
    num_cases: int,
    num_stable: int,
    worst: Optional[Tuple[str, float]],
    num_unstable: int,
) -> str:
    width = 30
    ratio = min(1.0, run_idx / max_runs if max_runs > 0 else 0.0)
    filled = int(width * ratio)
    bar = "█" * filled + "░" * (width - filled)
    stable_pct = (100.0 * num_stable / num_cases) if num_cases else 0.0
    if worst is None:
        worst_txt = "worst: n/a"
    else:
        _, rci = worst
        worst_txt = f"worst {min(100.0, rci*100):.2f}%"
    return f"[{bar}] run {run_idx}/{max_runs} | cases {num_cases} | stable {num_stable} ({stable_pct:.0f}%) | {worst_txt} | pending {num_unstable}"


def print_live_progress(line: str, enabled: bool) -> None:
    if enabled and sys.stdout.isatty():
        sys.stdout.write("\r\x1b[2K" + line)
        sys.stdout.flush()


