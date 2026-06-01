"""Progress / progress-bar helpers.

This module provides the Progress class used by CLI build flows.
"""

from __future__ import annotations

import sys
import time

from .utils import human_readable_size


class Progress:
    """Simple terminal progress helper used by CLI build flows.

    The Progress class writes progress updates to stderr. It is intentionally
    lightweight and has no external dependencies to keep CLI startup fast.

    Attributes:
        enabled: Whether progress output is active.
        width: Width of the visual progress bar in characters.
    """

    def __init__(self, enabled: bool = True, width: int = 32) -> None:
        self.enabled: bool = enabled
        self.width: int = width
        self.last_phase: str | None = None
        self.phase_start_time: dict[str, float] = {}
        self.phase_bytes: dict[str, int] = {}  # Track bytes processed per phase
        self.phase_last_len: dict[str, int] = {}  # Track last written line length per phase

    def step(self, phase: str, done: int, total: int, bytes_processed: int = 0) -> None:
        """Update progress for a named phase.

        Args:
            phase: Logical phase name shown in the progress line (for example
                'compress' or 'write').
            done: Number of completed units for this phase.
            total: Total units for this phase.
            bytes_processed: Optional number of bytes processed; when provided
                the progress will display byte-based throughput and ETA.
        """
        if not self.enabled:
            return

        # Initialize phase tracking if needed
        if phase not in self.phase_start_time:
            self.phase_start_time[phase] = time.time()
            self.phase_bytes[phase] = 0

        if bytes_processed > 0:
            self.phase_bytes[phase] = bytes_processed

        total = max(total, 1)
        done = max(0, min(done, total))
        ratio: float = done / total
        fill: int = int(self.width * ratio)
        bar: str = "#" * fill + "-" * (self.width - fill)
        pct: int = int(ratio * 100)

        # Calculate speed and ETA
        elapsed: float = time.time() - self.phase_start_time[phase]
        speed_str: str = ""
        eta_str: str = ""

        if elapsed > 0.1 and done > 0:
            if bytes_processed > 0:
                speed: float = self.phase_bytes[phase] / elapsed
                speed_str = f" @ {human_readable_size(int(speed))}/s"
                if done < total:
                    remaining_bytes: float = (self.phase_bytes[phase] / done) * (total - done)
                    eta_secs: float = remaining_bytes / speed if speed > 0 else 0
                    eta_str = f" ETA {int(eta_secs)}s" if eta_secs < 3600 else f" ETA {eta_secs / 60:.1f}m"
            else:
                speed: float = done / elapsed
                speed_str = f" {speed:.1f} items/s"
                if done < total:
                    eta_secs: float = (total - done) / speed if speed > 0 else 0
                    eta_str = f" ETA {int(eta_secs)}s" if eta_secs < 3600 else f" ETA {eta_secs / 60:.1f}m"

        line: str = f"[{bar}] {pct:3d}% {phase}{speed_str}{eta_str}"
        last_len: int = self.phase_last_len.get(phase, 0)
        padding: int = max(0, last_len - len(line))
        sys.stderr.write(f"\r{line}{' ' * padding}")
        self.phase_last_len[phase] = len(line)
        if done >= total:
            sys.stderr.write("\n")
            # Reset phase tracking
            self.phase_start_time.pop(phase, None)
            self.phase_bytes.pop(phase, None)
            self.phase_last_len.pop(phase, None)
        sys.stderr.flush()
        self.last_phase = phase

    def status(self, message: str) -> None:
        """Print a status message without progress bar.

        This always writes to stderr so CLI output and progress remain separate
        from normal stdout usage.
        """
        if not self.enabled:
            return
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
