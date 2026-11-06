"""Unprivileged checks for the boot-status scripts embedded in install.sh."""
from pathlib import Path
import os
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

    def test_login_banner_runs_live_check_with_bounded_wait_and_fallback(self):
        banner = heredoc("BOOT_STATUS_MOTD")
        self.assertIn("yerbas-boot-status --live", banner)
        self.assertIn("timeout 16", banner)
        self.assertIn('cat "$report"', banner)
        self.assertIn("Live Smartnode status unavailable", banner)
        self.assertNotIn("systemctl restart", banner)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "motd"
            path.write_text(banner)
            result = subprocess.run(["sh", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_each_live_run_reads_fresh_height_without_rewriting_boot_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_dir = root / "run"
            users_file = root / "users"
            users_file.write_text("alice\\n")
            home = root / "alice"
            (home / ".yerbascore").mkdir(parents=True)
            (home / ".yerbascore" / "yerbas.conf").write_text("port=15420\\n")
            mock_bin = root / "bin"
            mock_bin.mkdir()
            cli = root / "yerbas-cli"
            cli.write_text("#!/bin/sh\\nexit 0\\n")
            cli.chmod(0o755)
            height = root / "height"
            height.write_text("1155920\\n")
            commands = {
                "systemctl": "#!/bin/sh\\nif [ \"$1\" = is-active ]; then echo active; else echo enabled; fi\\n",
                "getent": "#!/bin/sh\\nprintf 'alice:x:1000:1000::%s:/bin/bash\\\\n' \"$FAKE_HOME\"\\n",
                "runuser": "#!/bin/sh\\ncase \"$*\" in *getblockcount) cat \"$FAKE_HEIGHT\";; *) echo '{\"state\":\"READY\"}';; esac\\n",
            }
            for name, content in commands.items():
                path = mock_bin / name
                path.write_text(content)
                path.chmod(0o755)

            script = heredoc("BOOT_STATUS_SCRIPT")
            script = script.replace(
                "users_file=/var/lib/yerbas-installer/users",
                "users_file=" + str(users_file),
            ).replace(
                "report_dir=/run/yerbas-smartnodes",
                "report_dir=" + str(report_dir),
            ).replace(
                "cli=/opt/yerbas/current/yerbas-cli",
                "cli=" + str(cli),
            )
            path = root / "yerbas-boot-status"
            path.write_text(script)
            path.chmod(0o755)
            env = {
                **os.environ,
                "PATH": str(mock_bin) + os.pathsep + os.environ["PATH"],
                "FAKE_HOME": str(home),
                "FAKE_HEIGHT": str(height),
            }

            snapshot = subprocess.run(
                ["bash", str(path)], env=env, capture_output=True, text=True,
                timeout=10,
            )
            self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
            cached = (report_dir / "status").read_text()
            self.assertIn("1155920", cached)

            height.write_text("1155921\\n")
            live = subprocess.run(
                ["bash", str(path), "--live"], env=env,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(live.returncode, 0, live.stderr)
            self.assertIn("Yerbas Smartnode status at SSH login", live.stdout)
            self.assertIn("1155921", live.stdout)
            self.assertIn("Smartnode: READY", live.stdout)
            self.assertEqual((report_dir / "status").read_text(), cached)

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
