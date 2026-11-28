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
        self.assertIn("Pruning: unavailable (configuration missing)", out)

    def test_menu_status_defaults_to_existing_users(self):
        out = self.run_bash('''EXISTING_USERS=(old)
        systemctl() { echo active; }
        getent() { return 1; }
        display_smartnode_statuses''')
        self.assertIn("Smartnode: old", out)

    def blockchain_status(self, response, config="prune=256", rpc_ok=True):
        import shlex
        return self.run_bash(r'''EXISTING_USERS=(alice)
        CURRENT_LINK="$TEST_DIR/bin"
        mkdir -p "$CURRENT_LINK" "$TEST_DIR/alice/.yerbascore"
        touch "$CURRENT_LINK/yerbas-cli"
        chmod +x "$CURRENT_LINK/yerbas-cli"
        systemctl() { echo inactive; }
        getent() { printf 'alice:x:1000:1000::%s/alice:/bin/bash\n' "$TEST_DIR"; }
        # No commands may escape to a real service or RPC endpoint.
        timeout() {
            case "${*: -1}" in
                status) printf '{"state":"READY"}';;
                getblockchaininfo) printf '%s' "$RESPONSE"; return "$RPC_EXIT";;
                *) return 99;;
            esac
        }
        ''' + "\nRESPONSE=" + shlex.quote(response) +
            "\nRPC_EXIT=" + str(0 if rpc_ok else 1) +
            "\nprintf '%s\\n' " + shlex.quote(config) +
            ' > "$TEST_DIR/alice/.yerbascore/yerbas.conf"\n' +
            "display_smartnode_statuses\n")

    def test_config_and_runtime_can_differ(self):
        out = self.blockchain_status('{"blocks":42,"pruned":false,"initialblockdownload":false}')
        self.assertIn("Configured prune target (global): 256 MiB", out)
        self.assertIn("Pruning: disabled (configured: 256 MiB target)", out)
        self.assertIn("Pruned (RPC mode): No", out)
        self.assertIn("Prune height: not applicable", out)
        self.assertIn("Initial block download: No", out)
        self.assertNotIn("Synced: Yes", out)
        self.assertNotIn("ChainLocks: Yes", out)

    def test_pruned_snapshot_and_zero_height(self):
        out = self.blockchain_status('{"blocks":1200,"pruned":true,"pruneheight":0,"initialblockdownload":true}')
        self.assertIn("Block height: 1200", out)
        self.assertIn("Pruning: enabled (configured: 256 MiB target; prune height: 0)", out)
        self.assertIn("Pruned (RPC mode): Yes", out)
        self.assertIn("Prune height: 0", out)
        self.assertIn("Initial block download: Yes", out)

    def test_missing_fields_do_not_imply_false(self):
        out = self.blockchain_status('{}')
        self.assertIn("Pruning: unavailable (configured: 256 MiB target)", out)
        self.assertIn("Pruned (RPC mode): unavailable", out)
        self.assertIn("Block height: unavailable", out)

    def test_invalid_and_failed_rpc_are_nonfatal(self):
        for response, ok in [('not json', True), ('[]', True), ('{}', False)]:
            with self.subTest(response=response, ok=ok):
                out = self.blockchain_status(response, rpc_ok=ok)
                self.assertIn("Blockchain: RPC unavailable or invalid response", out)
                self.assertIn("Pruning: unavailable (configured: 256 MiB target; RPC unavailable)", out)
                self.assertIn("Configured prune target (global): 256 MiB", out)

    def test_invalid_field_types_are_unavailable(self):
        out = self.blockchain_status('{"blocks":"wrong","pruned":true,"pruneheight":-1}')
        self.assertIn("Block height: unavailable", out)
        self.assertIn("Prune height: unavailable", out)
        self.assertIn("Pruning: enabled (configured: 256 MiB target; prune height: unavailable)", out)

    def test_configuration_modes_and_comments(self):
        for config, expected in [
            ('prune=0', 'disabled'), ('prune=1', 'manual'),
            ('# prune=256', 'not set'), ('prune=abc', 'invalid or duplicated'),
            ('prune=256\nprune=512', 'invalid or duplicated'),
            ('[test]\nprune=512', 'not set'),
        ]:
            with self.subTest(config=config):
                self.assertIn('Configured prune (global): ' + expected,
                              self.blockchain_status('{}', config))
        self.assertIn('Configured prune target (global): 512 MiB',
                      self.blockchain_status('{}', '  prune = 512 # target'))

    def test_empty_status_is_nonfatal(self):
        out = self.run_bash('''EXISTING_USERS=()
        display_smartnode_statuses''')
        self.assertIn("No configured Smartnodes were found.", out)


if __name__ == "__main__":
    unittest.main()
