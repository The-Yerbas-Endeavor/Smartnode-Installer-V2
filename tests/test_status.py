"""Read-only status reporting tests for newly added and existing Smartnodes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StatusTests(unittest.TestCase):
    def run_bash(self, body):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                ["bash", "-c", 'source "$REPO/install.sh"\n' + body],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": temp},
                text=True, capture_output=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_all_explicit_users_reported_including_new(self):
        out = self.run_bash('''EXISTING_USERS=(old)
        CONFIGURED_USERS=(old new)
        systemctl() { echo inactive; }
        getent() { return 1; }
        display_smartnode_statuses "${CONFIGURED_USERS[@]}"''')
        self.assertIn("Smartnode: old", out)
        self.assertIn("Smartnode: new", out)
        self.assertIn("Service: inactive", out)
        self.assertIn("configuration unavailable", out)

    def test_menu_status_defaults_to_existing_users(self):
        out = self.run_bash('''EXISTING_USERS=(old)
        systemctl() { echo active; }
        getent() { return 1; }
        display_smartnode_statuses''')
        self.assertIn("Smartnode: old", out)

    def test_empty_status_is_nonfatal(self):
        out = self.run_bash('''EXISTING_USERS=()
        display_smartnode_statuses''')
        self.assertIn("No configured Smartnodes were found.", out)


if __name__ == "__main__":
    unittest.main()
