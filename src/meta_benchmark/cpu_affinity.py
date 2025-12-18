"""Cross-platform CPU affinity management.

This module provides CPU pinning functionality that works across:
- Linux (via psutil or native os.sched_setaffinity)
- Windows (via psutil)
- FreeBSD (via psutil)
- macOS (limited support, logs warning)

Install psutil for best cross-platform support:
    pip install meta-benchmark[affinity]
"""

from __future__ import annotations

import os
import platform
from typing import Callable

from .logging_config import logger

# Track if psutil is available
_PSUTIL_AVAILABLE = False
try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment]


def is_affinity_supported() -> bool:
    """Check if CPU affinity is supported on this platform."""
    if _PSUTIL_AVAILABLE:
        return platform.system() in ("Linux", "Windows", "FreeBSD")
    # Fallback: Linux-only with native API
    return platform.system() == "Linux" and hasattr(os, "sched_setaffinity")


def get_cpu_count() -> int:
    """Get the number of available CPUs."""
    if _PSUTIL_AVAILABLE:
        return psutil.cpu_count(logical=True) or os.cpu_count() or 1
    return os.cpu_count() or 1


def validate_core_id(core_id: int) -> bool:
    """Validate that a core ID is valid for this system."""
    if core_id < 0:
        return False
    return core_id < get_cpu_count()


def set_affinity(core_id: int) -> bool:
    """Set CPU affinity for the current process.

    Args:
        core_id: The CPU core index to pin to.

    Returns:
        True if affinity was set successfully, False otherwise.
    """
    system = platform.system()

    if not validate_core_id(core_id):
        logger.warning(
            "Invalid core_id %d: system has %d cores (0-%d)",
            core_id,
            get_cpu_count(),
            get_cpu_count() - 1,
        )
        return False

    # Try psutil first (cross-platform)
    if _PSUTIL_AVAILABLE:
        try:
            p = psutil.Process()
            p.cpu_affinity([core_id])
            logger.debug("Set CPU affinity to core %d via psutil", core_id)
            return True
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as e:
            logger.warning("Failed to set CPU affinity via psutil: %s", e)
            return False
        except AttributeError:
            # cpu_affinity not supported on this platform (e.g., macOS)
            if system == "Darwin":
                logger.warning("CPU affinity is not supported on macOS")
            else:
                logger.warning("CPU affinity not available on this platform")
            return False

    # Fallback: Linux native API
    if system == "Linux" and hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, {core_id})
            logger.debug("Set CPU affinity to core %d via os.sched_setaffinity", core_id)
            return True
        except OSError as e:
            logger.warning("Failed to set CPU affinity: %s", e)
            return False

    logger.warning(
        "CPU affinity not supported on %s. Install psutil for cross-platform support: "
        "pip install meta-benchmark[affinity]",
        system,
    )
    return False


def create_affinity_preexec(core_id: int | None) -> Callable[[], None] | None:
    """Create a preexec_fn for subprocess that sets CPU affinity.

    This is used with subprocess.Popen/run to set affinity in child processes.

    Args:
        core_id: The CPU core to pin to, or None to skip affinity.

    Returns:
        A callable for preexec_fn, or None if affinity should not be set.
    """
    if core_id is None:
        return None

    if not validate_core_id(core_id):
        logger.warning(
            "Invalid core_id %d: system has %d cores (0-%d)",
            core_id,
            get_cpu_count(),
            get_cpu_count() - 1,
        )
        return None

    system = platform.system()

    # On Windows, preexec_fn is not supported - affinity must be set after spawn
    if system == "Windows":
        logger.debug("preexec_fn not supported on Windows, affinity will be set post-spawn")
        return None

    def _set_affinity() -> None:
        """Set CPU affinity in child process."""
        try:
            if _PSUTIL_AVAILABLE:
                p = psutil.Process()
                p.cpu_affinity([core_id])
            elif hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(0, {core_id})
        except (OSError, AttributeError):
            # Best-effort; don't crash the child process
            pass

    return _set_affinity


def set_process_affinity(pid: int, core_id: int) -> bool:
    """Set CPU affinity for a specific process by PID.

    Useful for setting affinity on Windows where preexec_fn doesn't work.

    Args:
        pid: Process ID to set affinity for.
        core_id: The CPU core to pin to.

    Returns:
        True if affinity was set successfully, False otherwise.
    """
    if not validate_core_id(core_id):
        return False

    if not _PSUTIL_AVAILABLE:
        logger.warning("psutil required to set affinity by PID")
        return False

    try:
        p = psutil.Process(pid)
        p.cpu_affinity([core_id])
        logger.debug("Set CPU affinity for PID %d to core %d", pid, core_id)
        return True
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, AttributeError) as e:
        logger.warning("Failed to set CPU affinity for PID %d: %s", pid, e)
        return False
