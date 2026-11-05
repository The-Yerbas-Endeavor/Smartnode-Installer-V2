"""Unprivileged checks for the boot-status scripts embedded in install.sh."""
from pathlib import Path
import subprocess
import tempfile
import unittest

INSTALL = (Path(__file__).resolve().parents[1] / "install.sh").read_text()


def heredoc(label):
    opening = "<<" + "'" + label + "'" + "\n"
    before, found, tail = INSTALL.partition(opening)
    if not found:
        raise AssertionError("Missing heredoc: " + label)
    content, found, _ = tail.partition("\n" + label + "\n")
    if not found:
        raise AssertionError("Unterminated heredoc: " + label)
    return content + "\n"


class BootStatusTests(unittest.TestCase):
    def test_script_syntax(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "yerbas-boot-status"
            path.write_text(heredoc("BOOT_STATUS_SCRIPT"))
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_login_banner_only_reads_cached_report(self):
        banner = heredoc("BOOT_STATUS_MOTD")
        self.assertNotIn("yerbas-cli", banner)
        self.assertNotIn("systemctl", banner)
        self.assertIn("cat \"$report\"", banner)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "motd"
            path.write_text(banner)
            result = subprocess.run(["sh", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_timer_runs_after_boot_without_blocking_startup(self):
        timer = heredoc("BOOT_STATUS_TIMER")
        service = heredoc("BOOT_STATUS_UNIT")
        self.assertIn("OnBootSec=180s", timer)
        self.assertIn("WantedBy=timers.target", timer)
        self.assertIn("Type=oneshot", service)
        self.assertIn("TimeoutStartSec=240", service)
        self.assertNotIn("Requires=yerbasd@", service)

    def test_report_is_read_only_and_uses_atomic_replace(self):
        reporter = heredoc("BOOT_STATUS_SCRIPT")
        self.assertIn('mv -f "$temp" "$report"', reporter)
        self.assertIn("chmod 0644", reporter)
        self.assertIn("smartnode status", reporter)
        self.assertIn("getblockcount", reporter)
        self.assertIn("timeout 8", reporter)
        self.assertNotIn("systemctl restart", reporter)


if __name__ == "__main__":
    unittest.main()
