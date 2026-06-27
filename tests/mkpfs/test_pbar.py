import time
import unittest
from contextlib import redirect_stderr
from io import StringIO

from mkpfs import utils
from mkpfs.pbar import Progress


class TestProgressBarHelpers(unittest.TestCase):
    """Tests for terminal progress rendering helpers."""

    def test_human_readable_size_reaches_petabyte_branch(self) -> None:
        """The human-readable size helper should format petabyte-scale values with PB units."""
        self.assertIn("PB", utils.human_readable_size(1024**5))

    def test_progress_step_reports_speed_eta_and_status_when_enabled(self) -> None:
        """Enabled progress output should include throughput details and the status line on stderr."""
        progress: Progress = Progress(enabled=True)
        stderr_buffer: StringIO = StringIO()
        progress.phase_start_time["compress"] = time.time() - 2.0
        progress.phase_bytes["compress"] = 1024 * 1024
        with redirect_stderr(stderr_buffer):
            progress.step("compress", 1, 4, bytes_processed=1024 * 1024)
            progress.phase_start_time["walk"] = time.time() - 1.0
            progress.step("walk", 1, 10, bytes_processed=0)
            progress.status("status-line")

        stderr_text: str = stderr_buffer.getvalue()
        self.assertTrue("ETA" in stderr_text or "items/s" in stderr_text)
        self.assertIn("status-line", stderr_text)

    def test_progress_methods_emit_nothing_when_disabled(self) -> None:
        """Disabled progress output should not write anything to stderr."""
        progress: Progress = Progress(enabled=False)
        stderr_buffer: StringIO = StringIO()
        with redirect_stderr(stderr_buffer):
            progress.step("scan", 1, 10, bytes_processed=100)
            progress.status("status msg")

        self.assertEqual(stderr_buffer.getvalue(), "")

    def test_progress_step_writes_percentage_output_when_enabled(self) -> None:
        """An enabled progress bar should render a percentage marker to stderr."""
        progress: Progress = Progress(enabled=True, width=10)
        stderr_buffer: StringIO = StringIO()
        with redirect_stderr(stderr_buffer):
            progress.step("scan", 1, 2, bytes_processed=100)
            progress.step("scan", 2, 2, bytes_processed=200)

        self.assertIn("%", stderr_buffer.getvalue())

    def test_simple_style_prints_concise_status_once_per_phase(self) -> None:
        """Simple style should write a one-line status per phase and avoid duplicate lines."""
        progress: Progress = Progress(enabled=True, style="simple")
        stderr_buffer: StringIO = StringIO()
        with redirect_stderr(stderr_buffer):
            # Multiple updates for the same phase should produce only one line.
            progress.step("compress", 1, 100, bytes_processed=1024)
            progress.step("compress", 50, 100, bytes_processed=1024 * 1024)
            # A new phase should produce a new concise line.
            progress.step("verify", 1, 10, bytes_processed=0)
        text: str = stderr_buffer.getvalue()
        # Only one line for compress
        self.assertEqual(text.count("Compressing files..."), 1)
        self.assertIn("Verifying files...", text)
