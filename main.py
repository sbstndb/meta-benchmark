#!/usr/bin/env python3

from pathlib import Path
import importlib
from typing import Callable, cast
import sys


def _ensure_src_on_path() -> None:
    repo_root = Path(__file__).resolve().parent
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def main() -> int:
    _ensure_src_on_path()
    module = importlib.import_module("meta_benchmark.cli")
    cli_main = cast(Callable[[], int], getattr(module, "main"))
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
