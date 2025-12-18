"""Logging configuration for meta-benchmark."""

from __future__ import annotations

import logging
import sys

# Module-level logger for the package
logger = logging.getLogger("meta_benchmark")


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure logging for meta-benchmark.

    Args:
        verbose: Enable DEBUG level logging.
        quiet: Suppress INFO messages, only show WARNING and above.
        log_file: Optional file path to write logs to.
    """
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Configure the package logger
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates on reconfiguration
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False
