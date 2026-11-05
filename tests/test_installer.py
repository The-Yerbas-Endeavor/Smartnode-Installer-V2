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

    def test_existing_install_displays_installed_wallet_release(self):
        result = self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        mkdir -p "$TEST_DIR/releases/v4.0.0.4"
        touch "$TEST_DIR/releases/v4.0.0.4/$DAEMON"
        chmod +x "$TEST_DIR/releases/v4.0.0.4/$DAEMON"
        ln -s "$TEST_DIR/releases/v4.0.0.4" "$CURRENT_LINK"
        prompt_yes_no() { return 1; }
        detect_existing_install
        [[ "$INSTALLED_RELEASE" == v4.0.0.4 ]]''')
        self.assertIn(
            'Currently installed Yerbas wallet release: v4.0.0.4',
            result.stdout,
        )

    def test_existing_install_displays_unknown_if_version_unavailable(self):
        result = self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        ln -s "$TEST_DIR/missing" "$CURRENT_LINK"
        prompt_yes_no() { return 1; }
        detect_existing_install
        [[ -z "$INSTALLED_RELEASE" ]]''')
        self.assertIn(
            'Currently installed Yerbas wallet release: unknown',
            result.stdout,
        )

    def test_existing_install_does_not_ask_separate_questions(self):
        result = self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        ln -s "$TEST_DIR/missing" "$CURRENT_LINK"
        prompt_yes_no() { echo "Unexpected prompt" >&2; return 99; }
        detect_existing_install
        [[ "$EXISTING_INSTALL" == 1 ]]''')
        self.assertNotIn('Unexpected prompt', result.stderr)

    def test_unified_menu_select_add(self):
        result = self.run_bash('''INSTALLED_RELEASE=v1
        RELEASE_TAG=v2
        maintenance_menu <<< 1
        [[ "$ADDITIONAL_USERS" == 1 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]''')
        self.assertIn('1) Add Smartnode', result.stdout)
        self.assertIn('2) Update Smartnodes', result.stdout)
        self.assertIn('3) Update/add IPv4 or IPv6 address', result.stdout)

    def test_unified_menu_select_wallet_update(self):
        self.run_bash('''INSTALLED_RELEASE=v1
        RELEASE_TAG=v2
        maintenance_menu <<< 2
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_WALLET_UPDATE" == 1 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]''')

    def test_unified_menu_select_ip_update(self):
        self.run_bash('''INSTALLED_RELEASE=v1
        RELEASE_TAG=v2
        maintenance_menu <<< 3
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 1 ]]''')

    def test_unified_menu_default_exits(self):
        self.run_bash('''INSTALLED_RELEASE=v1
        RELEASE_TAG=v2
        maintenance_menu <<< ""
        [[ "$ADDITIONAL_USERS" == 0 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$RUN_NETWORK_UPDATE" == 0 ]]''')

    def test_unified_menu_current_wallet_cannot_be_updated(self):
        result = self.run_bash('''INSTALLED_RELEASE=v2
        RELEASE_TAG=v2
        maintenance_menu <<< $'2\\n5'
        [[ "$RUN_WALLET_UPDATE" == 0 ]]
        [[ "$ADDITIONAL_USERS" == 0 ]]''')
        self.assertIn('already current', result.stdout)

    def test_current_release_skips_update_prompt(self):
        result = self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        STATE_DIR="$TEST_DIR/state"
        mkdir -p "$TEST_DIR/releases/v2" "$STATE_DIR"
        touch "$TEST_DIR/releases/v2/$DAEMON"
        chmod +x "$TEST_DIR/releases/v2/$DAEMON"
        ln -s "$TEST_DIR/releases/v2" "$CURRENT_LINK"
        echo v1 > "$STATE_DIR/current-version"
        RELEASE_TAG=v2
        prompt_yes_no() { echo "Unexpected prompt" >&2; return 99; }
        prompt_wallet_update_if_needed
        [[ "$INSTALLED_RELEASE" == v2 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]''')
        self.assertIn('already current (v2)', result.stdout)
        self.assertNotIn('Unexpected prompt', result.stderr)

    def test_older_release_asks_before_updating(self):
        self.run_bash('''CURRENT_LINK="$TEST_DIR/current"
        mkdir -p "$TEST_DIR/releases/v1"
        touch "$TEST_DIR/releases/v1/$DAEMON"
        chmod +x "$TEST_DIR/releases/v1/$DAEMON"
        ln -s "$TEST_DIR/releases/v1" "$CURRENT_LINK"
        RELEASE_TAG=v2
        prompt_yes_no() { [[ "$1" == *"Yerbas v2?"* ]] && return 1; return 99; }
        prompt_wallet_update_if_needed
        [[ "$INSTALLED_RELEASE" == v1 ]]
        [[ "$RUN_WALLET_UPDATE" == 0 ]]''')

    def test_unknown_release_asks_before_updating(self):
        self.run_bash('''CURRENT_LINK="$TEST_DIR/missing"
        RELEASE_TAG=v2
        prompt_yes_no() { [[ "$1" == *"Yerbas v2?"* ]]; }
        prompt_wallet_update_if_needed
        [[ -z "$INSTALLED_RELEASE" ]]
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
