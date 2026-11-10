"""Unprivileged tests for per-Smartnode configuration editing."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EditSmartnodeTests(unittest.TestCase):
    def run_bash(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["bash", "-c", 'source "$REPO/install.sh"\n'
                 'LOG_FILE="$TEST_DIR/log"\n' + body],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": tmp},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result

    def test_menu_edits_and_returns_without_triggering_update(self):
        result = self.run_bash('''EXISTING_USERS=(alice)
        INSTALLED_RELEASE=v1
        RELEASE_TAG=v2
        edit_existing_smartnode() { echo "Editor selected"; }
        maintenance_menu <<< $'5\\n8'
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]''')
        self.assertIn('5) Edit Smartnode', result.stdout)
        self.assertIn('8) Exit (no changes)', result.stdout)
        self.assertIn('Editor selected', result.stdout)

    def test_rpc_edit_preserves_unrelated_settings_and_backup(self):
        result = self.run_bash('''EXISTING_USERS=(alice)
        mkdir -p "$TEST_DIR/alice/.yerbascore"
        conf="$TEST_DIR/alice/.yerbascore/yerbas.conf"
        printf 'rpcport=9494\\nport=15420\\nrpcpassword=secret\\n' > "$conf"
        chmod 0600 "$conf"
        getent() { printf 'alice:x:1000:1000::%s/alice:/bin/bash\\n' "$TEST_DIR"; }
        port_is_available() { return 0; }
        chown() { return 0; }
        systemctl() { [[ "$1" == is-active ]] && echo inactive; return 0; }
        edit_smartnode_setting alice rpcport 9495
        grep -qx 'rpcport=9495' "$conf"
        grep -qx 'rpcpassword=secret' "$conf"
        [[ $(grep -c '^rpcport=' "$conf") == 1 ]]
        cmp <(printf 'rpcport=9494\\nport=15420\\nrpcpassword=secret\\n') "$conf" || true
        ls "$conf".bak.* >/dev/null
        [[ $(stat -c %a "$conf") == 600 ]]''')
        self.assertIn('configuration backup:', result.stdout)
        self.assertNotIn('rpcpassword=secret', result.stdout)

    def test_bls_edit_keeps_secret_out_of_output(self):
        result = self.run_bash('''EXISTING_USERS=(alice)
        mkdir -p "$TEST_DIR/alice/.yerbascore"
        conf="$TEST_DIR/alice/.yerbascore/yerbas.conf"
        echo "rpcport=9494" > "$conf"
        getent() { printf 'alice:x:1000:1000::%s/alice:/bin/bash\\n' "$TEST_DIR"; }
        chown() { return 0; }
        systemctl() { echo inactive; }
        key="$(printf 'a%.0s' {1..64})"
        edit_smartnode_setting alice smartnodeblsprivkey "$key"
        grep -qx "smartnodeblsprivkey=$key" "$conf"''')
        self.assertNotIn('aaaaaaaaaaaaaaaa', result.stdout + result.stderr)

    def test_invalid_bls_cannot_modify_config(self):
        self.run_bash('''EXISTING_USERS=(alice)
        mkdir -p "$TEST_DIR/alice/.yerbascore"
        conf="$TEST_DIR/alice/.yerbascore/yerbas.conf"
        echo "rpcport=9494" > "$conf"
        getent() { printf 'alice:x:1000:1000::%s/alice:/bin/bash\\n' "$TEST_DIR"; }
        if edit_smartnode_setting alice smartnodeblsprivkey invalid; then exit 2; fi
        grep -qx 'rpcport=9494' "$conf"
        [[ $(find "$TEST_DIR" -name '*.bak.*' | wc -l) == 0 ]]''')

    def test_restart_failure_restores_original_config(self):
        self.run_bash('''EXISTING_USERS=(alice)
        mkdir -p "$TEST_DIR/alice/.yerbascore"
        conf="$TEST_DIR/alice/.yerbascore/yerbas.conf"
        echo "rpcport=9494" > "$conf"
        getent() { printf 'alice:x:1000:1000::%s/alice:/bin/bash\\n' "$TEST_DIR"; }
        chown() { return 0; }
        port_is_available() { return 0; }
        systemctl() {
            if [[ "$1" == is-active ]]; then echo active; return 0; fi
            [[ "$1" == restart ]] && return 1
            return 0
        }
        if edit_smartnode_setting alice rpcport 9495; then exit 2; fi
        grep -qx 'rpcport=9494' "$conf"''')

    def test_editor_cancel_does_not_change_any_node(self):
        result = self.run_bash('''EXISTING_USERS=(alice bob)
        edit_existing_smartnode <<< ""
        [[ "$RUN_WALLET_UPDATE" == 0 ]]''')
        self.assertIn('alice', result.stdout)
        self.assertIn('bob', result.stdout)


if __name__ == "__main__":
    unittest.main()
