"""Unprivileged regression tests; never invoke the installer's main function."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def run_bash(self, body, expected=0):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                ['bash', '-c', 'source "$REPO/install.sh"\n'
                 'LOG_FILE="$TEST_DIR/installer.log"\n' + body],
                env={**os.environ, 'REPO': str(ROOT), 'TEST_DIR': temp},
                text=True, capture_output=True, timeout=10,
            )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_source_does_not_run_installer(self):
        self.run_bash('declare -F main >/dev/null')

    def test_valid_port_boundaries(self):
        self.run_bash('for port in 1024 9494 65535; do valid_port "$port"; done')

    def test_invalid_ports(self):
        self.run_bash('''for port in 0 1023 65536 09494 999999999999999999999999 -1 abc '1+1024' ''; do
            if valid_port "$port"; then exit 2; fi
        done''')

    def test_configured_ports_include_custom_homes_and_stopped_nodes(self):
        self.run_bash('''mkdir -p "$TEST_DIR/custom home/.yerbascore"
        printf 'rpcport=9494\nport=15420\n' > "$TEST_DIR/custom home/.yerbascore/yerbas.conf"
        getent() { printf 'alice:x:1000:1000::%s/custom home:/bin/bash\n' "$TEST_DIR"; }
        port_in_use() { return 1; }
        port_is_configured 9494
        port_is_configured 15420
        if port_is_available 9494; then exit 2; fi
        port_is_available 9495''')

    def test_next_port_skips_bound_and_configured_ports(self):
        result = self.run_bash('''port_in_use() { [[ "$1" == 9494 ]]; }
        port_is_configured() { [[ "$1" == 9495 ]]; }
        next_available_port 9494''')
        self.assertEqual(result.stdout.strip(), '9496')

    def test_next_port_skips_p2p(self):
        result = self.run_bash('''port_in_use() { return 1; }
        port_is_configured() { return 1; }
        next_available_port 15420''')
        self.assertEqual(result.stdout.strip(), '15421')

    def test_port_exhaustion_fails(self):
        self.run_bash('''port_in_use() { return 0; }
        next_available_port 65535''', expected=1)

    def test_disabled_bootstrap_succeeds_without_side_effects(self):
        self.run_bash('''USE_BOOTSTRAP=0
        curl() { exit 99; }
        install_bootstrap_for_user alice "$TEST_DIR/missing"
        [[ ! -e "$TEST_DIR/missing" ]]''')

    def test_standalone_manager_matches_repository(self):
        self.run_bash('''SCRIPT_DIR="$TEST_DIR"
        MANAGER="$TEST_DIR/yerbas-node-manager"
        install_manager
        cmp "$MANAGER" "$REPO/bin/yerbas-node-manager"
        [[ -x "$MANAGER" ]]''')

    def test_checkout_manager_matches_repository(self):
        self.run_bash('''MANAGER="$TEST_DIR/yerbas-node-manager"
        install_manager
        cmp "$MANAGER" "$REPO/bin/yerbas-node-manager"
        [[ -x "$MANAGER" ]]''')

    def test_existing_update_prompt_independent_of_adding_users(self):
        result = self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        USERS_FILE="$TEST_DIR/users"
        mkdir -p "$TEST_DIR/home/.yerbascore"
        touch "$TEST_DIR/home/.yerbascore/yerbas.conf"
        printf 'alice\\n' > "$USERS_FILE"
        getent() { printf 'alice:x:1000:1000::%s/home:/bin/bash\\n' "$TEST_DIR"; }
        id() { [[ "$1" == alice ]]; }
        prompt_yes_no() {
            case "$1" in
                "Update existing Smartnodes"*) return 0 ;;
                "Add additional Smartnode"*) return 1 ;;
                "Update/add IPv4"*) return 1 ;;
                *) return 1 ;;
            esac
        }
        detect_existing_install
        [[ "$EXISTING_INSTALL" == 1 ]]
        [[ "$RUN_WALLET_UPDATE" == 1 ]]
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]
        [[ "${EXISTING_USERS[0]}" == alice ]]''')
        self.assertIn('Existing Smartnode users: alice', result.stdout)

    def test_existing_update_declined_is_not_implicit(self):
        self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        mkdir -p "$TEST_DIR"
        ln -s "$TEST_DIR/release" "$CURRENT_LINK"
        prompt_yes_no() { return 1; }
        detect_existing_install
        [[ "$EXISTING_INSTALL" == 1 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]''')

    def test_network_maintenance_does_not_change_wallet_choice(self):
        self.run_bash('''RUN_WALLET_UPDATE=1
        prompt_yes_no() { return 1; }
        maintenance_menu
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]
        [[ "$RUN_WALLET_UPDATE" == 1 ]]''')

    def test_rollback_restores_version_and_target(self):
        self.run_bash('''STATE_DIR="$TEST_DIR/state"
        CURRENT_LINK="$TEST_DIR/current"
        previous="$TEST_DIR/releases/v1"
        mkdir -p "$STATE_DIR" "$previous" "$TEST_DIR/releases/v2"
        touch "$previous/$DAEMON" "$previous/$CLI"
        chmod +x "$previous/$DAEMON" "$previous/$CLI"
        printf '%s\n' "$previous" > "$STATE_DIR/previous-release"
        echo v2 > "$STATE_DIR/current-version"
        ln -s "$TEST_DIR/releases/v2" "$CURRENT_LINK"
        if rollback_release; then :; else exit 2; fi
        [[ "$(readlink "$CURRENT_LINK")" == "$previous" ]]
        [[ "$(cat "$STATE_DIR/current-version")" == v1 ]]
        [[ "$RELEASE_TAG" == v1 ]]''')

    def test_rollback_rejects_incomplete_release(self):
        self.run_bash('''STATE_DIR="$TEST_DIR/state"
        CURRENT_LINK="$TEST_DIR/current"
        mkdir -p "$STATE_DIR" "$TEST_DIR/v1"
        touch "$TEST_DIR/v1/$DAEMON"
        chmod +x "$TEST_DIR/v1/$DAEMON"
        echo "$TEST_DIR/v1" > "$STATE_DIR/previous-release"
        echo v2 > "$STATE_DIR/current-version"
        if rollback_release; then exit 2; fi
        [[ ! -e "$CURRENT_LINK" ]]
        [[ "$(cat "$STATE_DIR/current-version")" == v2 ]]''')

    def test_rollback_reports_link_failure(self):
        self.run_bash('''STATE_DIR="$TEST_DIR/state"
        CURRENT_LINK="$TEST_DIR/current"
        mkdir -p "$STATE_DIR" "$TEST_DIR/v1"
        touch "$TEST_DIR/v1/$DAEMON" "$TEST_DIR/v1/$CLI"
        chmod +x "$TEST_DIR/v1/"*
        echo "$TEST_DIR/v1" > "$STATE_DIR/previous-release"
        echo v2 > "$STATE_DIR/current-version"
        ln() { return 1; }
        if rollback_release; then exit 2; fi
        [[ "$(cat "$STATE_DIR/current-version")" == v2 ]]''')


if __name__ == '__main__':
    unittest.main()
