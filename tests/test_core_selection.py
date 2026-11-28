"""Unprivileged regression tests for per-node staged Core selection."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CoreSelectionTests(unittest.TestCase):
    def run_case(self, body):
        with tempfile.TemporaryDirectory() as temp:
            script = r'''
source "$REPO/install.sh"
LOG_FILE="$TEST_DIR/log"
SYSTEMD_INSTANCE_DIR="$TEST_DIR/systemd"
RELEASES_DIR="$TEST_DIR/releases"
CURRENT_LINK="$TEST_DIR/current"
EXISTING_USERS=(ip1 mrx)
mkdir -p "$RELEASES_DIR/stable" "$RELEASES_DIR/candidate" "$SYSTEMD_INSTANCE_DIR"
touch "$RELEASES_DIR/stable/yerbasd" "$RELEASES_DIR/stable/yerbas-cli"
touch "$RELEASES_DIR/candidate/yerbasd" "$RELEASES_DIR/candidate/yerbas-cli"
chmod +x "$RELEASES_DIR"/*/*
stat() { if [[ "$1" == -c && "$2" == %u ]]; then echo 0; else command stat "$@"; fi; }
node_core_version() {
    if [[ "$1" == "$RELEASES_DIR/candidate/yerbasd" ]]; then echo 4.0.1.6; else echo 4.0.1.4; fi
}
node_core_binary() {
    if [[ -f "$SYSTEMD_INSTANCE_DIR/yerbasd@$1.service.d/override.conf" ]]; then
        echo "$RELEASES_DIR/candidate/yerbasd"
    else
        echo "$RELEASES_DIR/stable/yerbasd"
    fi
}
systemctl() {
    case "$1" in
        is-active) [[ -f "$TEST_DIR/stopped" ]] && echo inactive || echo active ;;
        stop) [[ "$2" == yerbasd@ip1.service ]] || return 15; touch "$TEST_DIR/stopped" ;;
        daemon-reload) touch "$TEST_DIR/reloaded" ;;
        *) return 17 ;;
    esac
}
pgrep() { return 1; }
'''
            result = subprocess.run(
                ["bash", "-c", script + body],
                cwd=ROOT, env={**os.environ, "REPO": str(ROOT), "TEST_DIR": temp},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_only_selected_node_gets_override(self):
        out = self.run_case(r'''
configure_smartnode_core_release <<< $'1\n1\nSWITCH ip1'
test -f "$SYSTEMD_INSTANCE_DIR/yerbasd@ip1.service.d/override.conf"
! test -e "$SYSTEMD_INSTANCE_DIR/yerbasd@mrx.service.d/override.conf"
test -f "$TEST_DIR/stopped"
test -f "$TEST_DIR/reloaded"
grep -Fq "$RELEASES_DIR/candidate/yerbasd" "$SYSTEMD_INSTANCE_DIR/yerbasd@ip1.service.d/override.conf"
''')
        self.assertIn("remains stopped", out)

    def test_existing_override_never_overwritten(self):
        out = self.run_case(r'''
mkdir -p "$SYSTEMD_INSTANCE_DIR/yerbasd@ip1.service.d"
printf 'custom\n' > "$SYSTEMD_INSTANCE_DIR/yerbasd@ip1.service.d/override.conf"
configure_smartnode_core_release <<< '1'
grep -qx custom "$SYSTEMD_INSTANCE_DIR/yerbasd@ip1.service.d/override.conf"
! test -f "$TEST_DIR/stopped"
''')
        self.assertIn("refusing to overwrite", out)

    def test_unsafe_staged_release_name_not_listed(self):
        out = self.run_case(r'''
mkdir -p "$RELEASES_DIR/unsafe name"
touch "$RELEASES_DIR/unsafe name/yerbasd" "$RELEASES_DIR/unsafe name/yerbas-cli"
chmod +x "$RELEASES_DIR/unsafe name/"*
configure_smartnode_core_release <<< $'1\n'
! test -f "$TEST_DIR/stopped"
''')
        self.assertNotIn("unsafe name", out)

    def test_decline_confirmation_does_not_stop_node(self):
        out = self.run_case(r'''
configure_smartnode_core_release <<< $'1\n1\nNO'
! test -e "$SYSTEMD_INSTANCE_DIR/yerbasd@ip1.service.d/override.conf"
! test -f "$TEST_DIR/stopped"
''')
        self.assertIn("Cancelled", out)

    def test_downgrade_refused_without_stopping(self):
        out = self.run_case(r'''
node_core_binary() { echo "$RELEASES_DIR/candidate/yerbasd"; }
configure_smartnode_core_release <<< $'1\n2'
! test -f "$TEST_DIR/stopped"
''')
        self.assertIn("Downgrade refused", out)


if __name__ == "__main__":
    unittest.main()
