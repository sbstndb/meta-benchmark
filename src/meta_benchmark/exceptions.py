"""Custom exceptions for meta-benchmark."""

from __future__ import annotations


class BenchmarkError(Exception):
    """Exception raised when a benchmark operation fails."""

    def __init__(
        self,
        message: str,
        *,
        stderr: str | None = None,
        stdout: str | None = None,
        command: list | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.stdout = stdout
        self.command = command
        self.error = error

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.command:
            parts.append(f"Command: {' '.join(self.command)}")
        if self.error:
            parts.append(f"Error: {self.error}")
        if self.stderr:
            parts.append(f"Stderr: {self.stderr}")
        if self.stdout:
            parts.append(f"Stdout: {self.stdout}")
        return "\n".join(parts)
