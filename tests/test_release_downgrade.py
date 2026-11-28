"""Guard against downgrading a newer installed pilot to an older stable release."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseDowngradeTests(unittest.TestCase):
    def run_case(self, commands):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                ["bash", "-c", 'source "$REPO/install.sh"\nLOG_FILE="$TEST_DIR/log"\n' + commands],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": td},
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_old_stable_release_is_detected(self):
        self.run_case('''INSTALLED_RELEASE=v4.0.1.6-prune-compact-a46bf723
        RELEASE_TAG=v4.0.1.4
        release_is_older_than_installed''')

    def test_equal_release_is_not_downgrade(self):
        self.run_case('''INSTALLED_RELEASE=v4.0.1.6-pilot
        RELEASE_TAG=v4.0.1.6
        ! release_is_older_than_installed''')

    def test_newer_stable_release_is_not_downgrade(self):
        self.run_case('''INSTALLED_RELEASE=v4.0.1.4
        RELEASE_TAG=v4.0.1.6
        ! release_is_older_than_installed''')

    def test_update_menu_refuses_downgrade(self):
        out = self.run_case('''INSTALLED_RELEASE=v4.0.1.6-test
        RELEASE_TAG=v4.0.1.4
        maintenance_menu <<< $'2\\n9'
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$ADDITIONAL_USERS" == 0 ]]''')
        self.assertIn("Refusing to downgrade", out)
        self.assertIn("blocked: stable release older than installed", out)


if __name__ == "__main__":
    unittest.main()
