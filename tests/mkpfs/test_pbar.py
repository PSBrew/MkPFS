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


class TestProgressListener(unittest.TestCase):
    """Tests for the Option-B listener/progress-hook path."""

    def tearDown(self) -> None:
        # Reset module-level hook in case a test touched it.
        from mkpfs.pbar import default_listener as _dl

        if _dl is not None:
            import mkpfs.pbar as _pbar

            _pbar.default_listener = None

    def test_listener_via_constructor_receives_step_events(self) -> None:
        """A listener passed to Progress.__init__ should be called on each step()."""
        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        progress: Progress = Progress(enabled=True, listener=listener)
        progress.step("compress", 1, 4, bytes_processed=1024)
        progress.step("compress", 2, 4, bytes_processed=2048)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0], ("step", "compress", 1, 4, 1024))
        self.assertEqual(events[1], ("step", "compress", 2, 4, 2048))

    def test_listener_via_constructor_receives_status_events(self) -> None:
        """A listener passed to Progress.__init__ should be called on status()."""
        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        progress: Progress = Progress(enabled=True, listener=listener)
        progress.status("ready")
        progress.status("done")

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0], ("status", "ready"))
        self.assertEqual(events[1], ("status", "done"))

    def test_listener_suppresses_stderr_write_in_step(self) -> None:
        """When a listener is active step() should not write to stderr."""
        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        progress: Progress = Progress(enabled=True, listener=listener)
        stderr_buffer: StringIO = StringIO()
        with redirect_stderr(stderr_buffer):
            progress.step("scan", 1, 10, bytes_processed=100)
            progress.step("scan", 10, 10, bytes_processed=1000)

        self.assertEqual(len(events), 2)
        self.assertEqual(stderr_buffer.getvalue(), "")

    def test_listener_suppresses_stderr_write_in_status(self) -> None:
        """When a listener is active status() should not write to stderr."""
        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        progress: Progress = Progress(enabled=True, listener=listener)
        stderr_buffer: StringIO = StringIO()
        with redirect_stderr(stderr_buffer):
            progress.status("some message")

        self.assertEqual(len(events), 1)
        self.assertEqual(stderr_buffer.getvalue(), "")

    def test_listener_fires_before_enabled_check_in_step(self) -> None:
        """The listener should fire in step() even when enabled is False."""
        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        progress: Progress = Progress(enabled=False, listener=listener)
        progress.step("scan", 1, 10, bytes_processed=100)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], ("step", "scan", 1, 10, 100))

    def test_listener_fires_before_enabled_check_in_status(self) -> None:
        """The listener should fire in status() even when enabled is False."""
        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        progress: Progress = Progress(enabled=False, listener=listener)
        progress.status("secret")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], ("status", "secret"))

    def test_default_listener_wired_via_module_level_hook(self) -> None:
        """Setting default_listener should automatically wire it to new instances."""
        import mkpfs.pbar as _pbar

        events: list[tuple] = []

        def listener(*args: object) -> None:
            events.append(args)

        _pbar.default_listener = listener
        try:
            progress: Progress = Progress(enabled=True)
            progress.step("walk", 5, 10, bytes_processed=500)
        finally:
            _pbar.default_listener = None

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], ("step", "walk", 5, 10, 500))

    def test_default_listener_does_not_override_explicit_listener(self) -> None:
        """An explicit listener on the constructor should take precedence over default_listener."""
        import mkpfs.pbar as _pbar

        explicit_events: list[tuple] = []
        default_events: list[tuple] = []

        def explicit_listener(*args: object) -> None:
            explicit_events.append(args)

        def default_listener_fn(*args: object) -> None:
            default_events.append(args)

        _pbar.default_listener = default_listener_fn
        try:
            progress: Progress = Progress(enabled=True, listener=explicit_listener)
            progress.step("copy", 1, 3, bytes_processed=100)
        finally:
            _pbar.default_listener = None

        self.assertEqual(len(explicit_events), 1)
        self.assertEqual(len(default_events), 0)
