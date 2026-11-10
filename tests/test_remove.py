"""Unprivileged regression checks for Smartnode removal."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RemovalTests(unittest.TestCase):
    def run_bash(self, commands):
        with tempfile.TemporaryDirectory() as td:
            script = 'source "$REPO/install.sh"\nLOG_FILE="$TEST_DIR/log"\n' + commands
            result = subprocess.run(
                ["bash", "-c", script],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": td},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_preserve_mode_only_removes_selected_node(self):
        out = self.run_bash(r'''STATE_DIR="$TEST_DIR/state"
        USERS_FILE="$STATE_DIR/users"
        mkdir -p "$STATE_DIR" "$TEST_DIR/ip4/.yerbascore"
        printf 'ip1\nip4\n' >"$USERS_FILE"
        echo secret > "$TEST_DIR/ip4/.yerbascore/yerbas.conf"
        EXISTING_USERS=(ip1 ip4)
        CONFIGURED_USERS=(ip1 ip4)
        getent() { printf 'ip4:x:1000:1000::%s/ip4:/bin/bash\n' "$TEST_DIR"; }
        smartnode_expected_home() { printf '%s/%s\n' "$TEST_DIR" "$1"; }
        systemctl() { [[ "$1" == is-active ]] && return 3; return 0; }
        remove_existing_smartnode <<< $'2\n1\nREMOVE ip4'
        [[ ! -e "$TEST_DIR/ip4/.yerbascore/yerbas.conf" ]]
        ls "$TEST_DIR/ip4/.yerbascore/yerbas.conf.removed."* >/dev/null
        grep -qx ip1 "$USERS_FILE"
        ! grep -qx ip4 "$USERS_FILE"
        [[ "${EXISTING_USERS[*]}" == ip1 ]]
        [[ "${CONFIGURED_USERS[*]}" == ip1 ]]
        [[ $(stat -c %a "$USERS_FILE") == 600 ]]''')
        self.assertIn("removed from management", out)

    def test_wrong_confirmation_does_not_change_anything(self):
        self.run_bash(r'''STATE_DIR="$TEST_DIR/state"
        USERS_FILE="$STATE_DIR/users"
        mkdir -p "$STATE_DIR" "$TEST_DIR/ip4/.yerbascore"
        echo ip4 >"$USERS_FILE"
        echo secret > "$TEST_DIR/ip4/.yerbascore/yerbas.conf"
        EXISTING_USERS=(ip4)
        getent() { printf 'ip4:x:1000:1000::%s/ip4:/bin/bash\n' "$TEST_DIR"; }
        smartnode_expected_home() { printf '%s/%s\n' "$TEST_DIR" "$1"; }
        systemctl() { exit 99; }
        userdel() { exit 99; }
        remove_existing_smartnode <<< $'1\n2\ncancel'
        grep -qx ip4 "$USERS_FILE"
        [[ -f "$TEST_DIR/ip4/.yerbascore/yerbas.conf" ]]''')

    def test_destructive_mode_only_targets_selected_user(self):
        out = self.run_bash(r'''STATE_DIR="$TEST_DIR/state"
        USERS_FILE="$STATE_DIR/users"
        mkdir -p "$STATE_DIR" "$TEST_DIR/ip4/.yerbascore"
        printf 'ip1\nip4\n' >"$USERS_FILE"
        echo secret > "$TEST_DIR/ip4/.yerbascore/yerbas.conf"
        EXISTING_USERS=(ip1 ip4)
        CONFIGURED_USERS=(ip1 ip4)
        getent() { printf 'ip4:x:1000:1000::%s/ip4:/bin/bash\n' "$TEST_DIR"; }
        smartnode_expected_home() { printf '%s/%s\n' "$TEST_DIR" "$1"; }
        systemctl() { [[ "$1" == is-active ]] && return 3; return 0; }
        userdel() { printf '%s\n' "$*" >"$TEST_DIR/userdel-call"; }
        remove_existing_smartnode <<< $'2\n2\nDELETE ip4'
        [[ "$(cat "$TEST_DIR/userdel-call")" == '-r ip4' ]]
        grep -qx ip1 "$USERS_FILE"
        ! grep -qx ip4 "$USERS_FILE"''')
        self.assertIn("removed from management", out)

    def test_service_stop_failure_is_safe(self):
        self.run_bash(r'''STATE_DIR="$TEST_DIR/state"
        USERS_FILE="$STATE_DIR/users"
        mkdir -p "$STATE_DIR" "$TEST_DIR/ip4/.yerbascore"
        echo ip4 >"$USERS_FILE"
        echo secret >"$TEST_DIR/ip4/.yerbascore/yerbas.conf"
        EXISTING_USERS=(ip4)
        getent() { printf 'ip4:x:1000:1000::%s/ip4:/bin/bash\n' "$TEST_DIR"; }
        smartnode_expected_home() { printf '%s/%s\n' "$TEST_DIR" "$1"; }
        systemctl() { return 1; }
        userdel() { exit 99; }
        if remove_existing_smartnode <<< $'1\n2\nDELETE ip4'; then exit 2; fi
        grep -qx ip4 "$USERS_FILE"
        [[ -f "$TEST_DIR/ip4/.yerbascore/yerbas.conf" ]]''')

    def test_menu_option_and_exit(self):
        out = self.run_bash(r'''INSTALLED_RELEASE=v2
        RELEASE_TAG=v2
        maintenance_menu <<< ''
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]''')
        self.assertIn("6) Remove Smartnode", out)
        self.assertIn("7) Exit (no changes)", out)

if __name__ == "__main__":
    unittest.main()
