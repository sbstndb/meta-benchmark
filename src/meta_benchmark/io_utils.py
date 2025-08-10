import json
from typing import Dict, Set

from .runner import MetaConfig
from .stats import CaseStats


def write_summary(output_file: str, config: MetaConfig, stats: Dict[str, CaseStats], stable_set: Set[str]) -> None:
    out_cases: Dict[str, Dict[str, float]] = {}
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
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


