"""Safe per-node pruning configuration regression tests (unprivileged)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PruningTests(unittest.TestCase):
    def run_case(self, body):
        with tempfile.TemporaryDirectory() as temp:
            setup = r'''
source "$REPO/install.sh"
LOG_FILE="$TEST_DIR/log"
EXISTING_USERS=(alice bob)
INSTALLED_RELEASE=4.0.1.6
CONF_DIR_NAME=.yerbascore
mkdir -p "$TEST_DIR/alice/.yerbascore" "$TEST_DIR/bob/.yerbascore"
printf 'rpcpassword=secret\nprune=0\n' > "$TEST_DIR/alice/.yerbascore/yerbas.conf"
printf 'rpcpassword=other\nprune=0\n' > "$TEST_DIR/bob/.yerbascore/yerbas.conf"
getent() { printf '%s:x:1000:1000::%s/%s:/bin/bash\n' "$2" "$TEST_DIR" "$2"; }
systemctl() { if [[ "$1" == is-active ]]; then echo inactive; else return 1; fi; }
chown() { return 0; }
'''
            result = subprocess.run(
                ["bash", "-c", setup + body],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": temp},
                text=True, capture_output=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_414_cannot_enable_pruning(self):
        result = self.run_case(r'''
INSTALLED_RELEASE=4.0.1.4
configure_smartnode_pruning <<< '1'
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('not eligible', result.stdout)

    def test_existing_history_requires_explicit_confirmation(self):
        result = self.run_case(r'''
mkdir -p "$TEST_DIR/alice/.yerbascore/blocks"
touch "$TEST_DIR/alice/.yerbascore/blocks/blk00000.dat"
configure_smartnode_pruning <<< '1'
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Archival migration cancelled', result.stdout)

    def test_existing_archive_can_configure_selected_node_only(self):
        result = self.run_case(r'''
mkdir -p "$TEST_DIR/alice/.yerbascore/blocks"
touch "$TEST_DIR/alice/.yerbascore/blocks/blk00000.dat"
echo 'txindex=1' >> "$TEST_DIR/alice/.yerbascore/yerbas.conf"
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< $'1\nMIGRATE alice\n2048'
grep -qx 'prune=2048' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'txindex=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
! grep -qx 'txindex=1' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Node remains stopped', result.stdout)

    def test_running_node_cannot_be_changed(self):
        result = self.run_case(r'''
systemctl() { echo active; }
configure_smartnode_pruning <<< '1'
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Stop alice first', result.stdout)

    def test_fresh_stopped_node_changes_only_selected_configuration(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< $'1\n2048'
grep -qx 'prune=2048' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'txindex=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'rpcpassword=secret' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
test "$(stat -c %a "$TEST_DIR/alice/.yerbascore/yerbas.conf")" == 600
ls "$TEST_DIR/alice/.yerbascore/yerbas.conf.prune-backup."* >/dev/null
''')
        self.assertIn('Node remains stopped', result.stdout)


    def test_minimum_prune_target_1024_is_accepted(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n1024')"
grep -qx 'prune=1024' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'txindex=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=1024', result.stdout)

    def test_below_minimum_prune_target_is_rejected(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n1023')"
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Minimum target 1024 MiB', result.stdout)

    def test_default_prune_target_is_1024(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n\nx')"
grep -qx 'prune=1024' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=1024', result.stdout)

    def test_cancel_does_not_modify_nodes(self):
        self.run_case(r'''
configure_smartnode_pruning <<< ''
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')


if __name__ == "__main__":
    unittest.main()
