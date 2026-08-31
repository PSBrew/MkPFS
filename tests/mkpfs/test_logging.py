import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

import mkpfs.logging as mlogging


class TestLoggingHelpers(unittest.TestCase):
    """Tests for the lightweight logging helper module."""

    def test_supports_utf8_returns_false_when_env_override_is_set(self) -> None:
        """The UTF-8 support check should honor the disabling environment variable."""
        with patch.dict("os.environ", {"MKPFS_NO_UTF8": "1"}, clear=False):
            self.assertFalse(mlogging.supports_utf8())

    def test_icon_returns_ascii_value_when_utf8_output_is_disabled(self) -> None:
        """The icon lookup should return ASCII fallbacks when UTF-8 output is disabled."""
        with patch.dict("os.environ", {"MKPFS_NO_UTF8": "1"}, clear=False):
            self.assertEqual(mlogging.icon("info"), "INFO")

    def test_icon_returns_utf8_glyph_when_stdout_encoding_supports_it(self) -> None:
        """The icon lookup should return a glyph when stdout reports UTF-8 support."""

        class DummyOut:
            """Simple stdout stub with a UTF-8 encoding attribute."""

            encoding: str = "utf-8"

        with patch.dict("os.environ", {}, clear=True), patch.object(sys, "stdout", DummyOut()):
            self.assertTrue(mlogging.supports_utf8())
            self.assertNotEqual(mlogging.icon("ok"), "OK")

    def test_log_sends_info_to_stdout_and_error_to_stderr(self) -> None:
        """The log helpers should write informational and error output to different streams."""
        stdout_buffer: StringIO = StringIO()
        stderr_buffer: StringIO = StringIO()
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            mlogging.info("hello world", icon_name=None)
            mlogging.error("bad stuff", icon_name=None)

        self.assertIn("hello world", stdout_buffer.getvalue())
        self.assertIn("bad stuff", stderr_buffer.getvalue())

    def test_log_falls_back_when_stream_rejects_message_body_unicode(self) -> None:
        """If the stream codec rejects non-ASCII in the message body, log() should print an ASCII-safe fallback."""

        class FailingStdout:
            encoding: str = "cp1252"  # simulate Windows pipe

            def __init__(self) -> None:
                self.data: str = ""

            def write(self, s: str) -> int:
                # Reject any non-ASCII bytes (simulate cp1252 failure on emoji)
                if any(ord(ch) > 0x7F for ch in s):
                    raise UnicodeEncodeError("cp1252", s, 0, 1, "non-ASCII not encodable")
                self.data += s
                return len(s)

            def flush(self) -> None:  # pragma: no cover - noop
                return

            def isatty(self) -> bool:  # pragma: no cover
                return False

        fake = FailingStdout()
        with patch.object(sys, "stdout", fake):
            # Emoji in the message body should trigger the fallback
            mlogging.info("🎉 done", icon_name=None)
        # Fallback should have printed ASCII-safe content containing the message text
        self.assertIn("done", fake.data)
        # Ensure no raw emoji slipped through
        self.assertNotIn("🎉", fake.data)

    def test_log_falls_back_when_icon_glyph_rejected_despite_utf8_claim(self) -> None:
        """If stdout claims UTF-8 but rejects glyphs at write(), log() must fall back to ASCII icon."""

        class LyingStdout:
            # Report UTF-8 to make supports_utf8() return True
            encoding: str = "utf-8"

            def __init__(self) -> None:
                self.data: str = ""

            def write(self, s: str) -> int:
                # Reject any non-ASCII to simulate downstream cp1252 pipe
                if any(ord(ch) > 0x7F for ch in s):
                    raise UnicodeEncodeError("cp1252", s, 0, 1, "non-ASCII not encodable")
                self.data += s
                return len(s)

            def flush(self) -> None:  # pragma: no cover - noop
                return

            def isatty(self) -> bool:  # pragma: no cover
                return False

        fake = LyingStdout()
        with patch.object(sys, "stdout", fake), patch.dict("os.environ", {}, clear=True):
            mlogging.info("done", icon_name="success")
        # Fallback should have switched the icon to ASCII and preserved message text
        self.assertIn("SUCCESS", fake.data)
        self.assertIn("done", fake.data)
        # No raw emoji should be present
        self.assertNotIn("🎉", fake.data)
