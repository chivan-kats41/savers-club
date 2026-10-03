"""The project is developed on Linux but run on Windows too. Guard against Linux-only code."""
import re
from datetime import datetime, timezone as dt_tz
from pathlib import Path

from django.test import SimpleTestCase

from hub.selectors import clock_label

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"env", "node_modules", "staticfiles", ".git", "vendor", "__pycache__"}


class PortabilityTests(SimpleTestCase):
    def test_no_glibc_only_strftime_flags(self):
        """%-d / %-I etc. crash on Windows ("Invalid format string"); %#d crashes on Linux."""
        bad = []
        for path in ROOT.rglob("*"):
            if path.suffix not in {".py", ".html", ".txt"} or any(part in SKIP for part in path.parts):
                continue
            if path.name == Path(__file__).name:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if re.search(r"strftime|date:|time:|%[-#][a-zA-Z]", line) and re.search(r"%[-#][a-zA-Z]", line):
                    bad.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
        self.assertEqual(bad, [], "Platform-specific date format found:\n" + "\n".join(bad))

    def test_clock_label(self):
        d = lambda h, m: datetime(2026, 10, 3, h, m, tzinfo=dt_tz.utc)
        self.assertEqual(clock_label(d(0, 5)), "12:05 AM")
        self.assertEqual(clock_label(d(9, 0)), "9:00 AM")
        self.assertEqual(clock_label(d(12, 30)), "12:30 PM")
        self.assertEqual(clock_label(d(18, 7)), "6:07 PM")
