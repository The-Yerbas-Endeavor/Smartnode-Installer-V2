"""Regression tests for node configurations discovered without a users-list entry."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DiscoveredRemovalTests(unittest.TestCase):
    def run_case(self, mode, confirm, expect_removed):
        with tempfile.TemporaryDirectory() as td:
            setup = """
STATE_DIR="$TEST_DIR/state"
USERS_FILE="$STATE_DIR/users"
mkdir -p "$STATE_DIR" "$TEST_DIR/ip6/.yerbascore"
echo ip1 >"$USERS_FILE"
echo privatekey >"$TEST_DIR/ip6/.yerbascore/yerbas.conf"
EXISTING_USERS=(ip1 ip6)
CONFIGURED_USERS=(ip1 ip6)
getent() { echo "ip6:x:1000:1000::$TEST_DIR/ip6:/bin/bash"; }
smartnode_expected_home() { echo "$TEST_DIR/$1"; }
systemctl() {
    if [[ "$1" == is-active ]]; then return 3; fi
    return 0
}
userdel() { echo "$*" >"$TEST_DIR/deletion"; }
remove_existing_smartnode <<INPUT
2
""" + mode + """
""" + confirm + """
INPUT
"""
            checks = (
                """
test ! -e "$TEST_DIR/ip6/.yerbascore/yerbas.conf"
test -f "$TEST_DIR/deletion"
grep -qx ip1 "$USERS_FILE"
"""
                if expect_removed else
                """
test -f "$TEST_DIR/ip6/.yerbascore/yerbas.conf"
test ! -e "$TEST_DIR/deletion"
grep -qx ip1 "$USERS_FILE"
"""
            )
            script = 'source "$REPO/install.sh"\nLOG_FILE="$TEST_DIR/log"\n' + setup + checks
            result = subprocess.run(
                ["bash", "-c", script],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": td},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("absent from the managed-users file", result.stdout)

    def test_ip6_unregistered_permanent_removal(self):
        self.run_case("2", "DELETE ip6", True)

    def test_ip6_unregistered_confirmation_required(self):
        self.run_case("2", "DELETE ip5", False)


if __name__ == "__main__":
    unittest.main()
