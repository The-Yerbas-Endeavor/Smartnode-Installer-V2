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
# Mock per-instance service binaries. Global INSTALLED_RELEASE remains a shared
# release label for other installer paths, but must not authorize pruning.
node_core_binary() { printf '/opt/yerbas/releases/test-%s/yerbasd\n' "$1"; }
node_core_version() {
    local version="${NODE_CORE_VERSION:-$INSTALLED_RELEASE}"
    [[ "$version" =~ ^v?([0-9]+[.][0-9]+[.][0-9]+[.][0-9]+)($|[-+]) ]] || return 1
    printf '%s\n' "${BASH_REMATCH[1]}"
}
core_prune_minimum_mib() { printf '256\n'; }
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
        self.assertIn('requires a verified 4.0.1.6 build', result.stdout)

    def test_newer_instance_is_eligible_with_older_shared_release(self):
        result = self.run_case(r'''
INSTALLED_RELEASE=4.0.1.4
NODE_CORE_VERSION=4.0.1.6
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256')"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=256', result.stdout)

    def test_older_instance_rejected_with_newer_shared_release(self):
        result = self.run_case(r'''
INSTALLED_RELEASE=4.0.1.6
NODE_CORE_VERSION=4.0.1.4
configure_smartnode_pruning <<< '1'
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('requires a verified 4.0.1.6 build', result.stdout)

    def test_missing_instance_binary_fails_closed(self):
        result = self.run_case(r'''
node_core_binary() { return 1; }
configure_smartnode_pruning <<< '1'
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn("Cannot verify alice service's Core binary", result.stdout)

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

    def test_running_node_declined_stop_preserves_service_and_config(self):
        result = self.run_case(r'''
systemctl() {
  if [[ "$1" == is-active ]]; then echo active; return 0; fi
  echo "unexpected service command" >&2; return 1
}
prompt_yes_no() {
  case "$1" in
    "Set prune="*) return 0 ;;
    "Stop alice now"*) return 1 ;;
    *) return 1 ;;
  esac
}
configure_smartnode_pruning <<< "$(printf '1\n256')"
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('No service or configuration changed', result.stdout)

    def test_running_node_stops_only_selected_after_approval(self):
        result = self.run_case(r'''
systemctl() {
  if [[ "$1" == is-active ]]; then
    if [[ "$2" == "yerbasd@alice" && ! -f "$TEST_DIR/alice-stopped" ]]; then echo active; else echo inactive; fi
    return 0
  fi
  if [[ "$1" == stop && "$2" == "yerbasd@alice" ]]; then touch "$TEST_DIR/alice-stopped"; return 0; fi
  return 1
}
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256')"
test -f "$TEST_DIR/alice-stopped"
grep -qx 'txindex=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Start it manually', result.stdout)

    def test_supported_commit_suffix_can_configure_pruning(self):
        result = self.run_case(r'''
INSTALLED_RELEASE=v4.0.1.6-a46bf72
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256')"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=256', result.stdout)

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


    def test_minimum_prune_target_256_is_accepted(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256')"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'txindex=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=256', result.stdout)

    def test_below_minimum_prune_target_is_rejected(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n255')"
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Installed Core minimum is 256 MiB', result.stdout)

    def test_default_prune_target_is_256(self):
        result = self.run_case(r'''
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n\nx')"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=256', result.stdout)

    def test_installed_old_core_rejects_256_then_accepts_1024(self):
        result = self.run_case(r'''
core_prune_minimum_mib() { printf '945\n'; }
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256\n1024')"
grep -qx 'prune=1024' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Installed Core minimum is 945 MiB', result.stdout)

    def test_old_core_can_cancel_without_changes(self):
        result = self.run_case(r'''
core_prune_minimum_mib() { printf '945\n'; }
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n\nq')"
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Cancelled', result.stdout)

    def test_unverifiable_core_refuses_changes(self):
        result = self.run_case(r'''
core_prune_minimum_mib() { return 1; }
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256')"
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn("Could not verify installed Core", result.stdout)

    def test_existing_pruned_node_can_resize_to_256(self):
        result = self.run_case(r'''
sed -i 's/prune=0/prune=1024/' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
mkdir -p "$TEST_DIR/alice/.yerbascore/blocks"
touch "$TEST_DIR/alice/.yerbascore/blocks/blk00000.dat"
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\nRESIZE alice\n256')"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')
        self.assertIn('Configured txindex=0 and prune=256', result.stdout)

    def test_existing_pruned_node_requires_resize_confirmation(self):
        result = self.run_case(r'''
sed -i 's/prune=0/prune=1024/' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
mkdir -p "$TEST_DIR/alice/.yerbascore/blocks"
touch "$TEST_DIR/alice/.yerbascore/blocks/blk00000.dat"
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\nMIGRATE alice\n256')"
grep -qx 'prune=1024' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
''')
        self.assertIn('Prune target update cancelled', result.stdout)

    def test_current_target_is_noop(self):
        result = self.run_case(r'''
sed -i 's/prune=0/prune=256/' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
prompt_yes_no() { return 0; }
configure_smartnode_pruning <<< "$(printf '1\n256')"
grep -qx 'prune=256' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
test "$(find "$TEST_DIR/alice/.yerbascore" -name '*prune-backup*' | wc -l)" -eq 0
''')
        self.assertIn('Target unchanged', result.stdout)

    def test_cancel_does_not_modify_nodes(self):
        self.run_case(r'''
configure_smartnode_pruning <<< ''
grep -qx 'prune=0' "$TEST_DIR/alice/.yerbascore/yerbas.conf"
grep -qx 'prune=0' "$TEST_DIR/bob/.yerbascore/yerbas.conf"
''')


if __name__ == "__main__":
    unittest.main()
