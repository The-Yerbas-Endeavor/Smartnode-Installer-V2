"""Read-only, unprivileged tests for the installed manager status command."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ManagerStatusTests(unittest.TestCase):
    def run_status(self, rpc_mode="good", prune="256"):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fakebin = root / "bin"
            fakebin.mkdir()
            home = root / "home" / "ip1" / ".yerbascore"
            home.mkdir(parents=True)
            (home / "yerbas.conf").write_text("rpcpassword=secret\nprune=" + prune + "\n")
            (root / "users").write_text("ip1\n")
            manager = (ROOT / "bin" / "yerbas-node-manager").read_text()
            manager = manager.replace(
                'USERS_FILE="/var/lib/yerbas-installer/users"',
                'USERS_FILE="' + str(root / "users") + '"')
            manager = manager.replace(
                'CLI="/usr/local/bin/yerbas-cli"',
                'CLI="' + str(fakebin / "yerbas-cli") + '"')
            script = root / "manager"
            script.write_text(manager)
            script.chmod(0o700)
            mocks = {
                "systemctl": '#!/bin/bash\n'
                             'case "$1" in\n'
                             '  is-active) echo active;;\n'
                             '  is-enabled) echo enabled;;\n'
                             '  show) echo "path=$TEST_DIR/bin/yerbasd ; argv[]=stub";;\n'
                             'esac\n',
                "getent": '#!/bin/bash\n'
                          'echo "ip1:x:1000:1000::$TEST_DIR/home/ip1:/bin/bash"\n',
                "timeout": '#!/bin/bash\nshift\nexec "$@"\n',
                "sudo": '#!/bin/bash\nshift 3\nexec "$@"\n',
                "yerbasd": '#!/bin/bash\necho "Yerbas Core Daemon v4.0.1.6-test"\n',
                "yerbas-cli": '#!/bin/bash\n'
                              'case "${!#}" in\n'
                              '  status) echo \'{"state":"READY"}\';;\n'
                              '  getblockchaininfo)\n'
                              '    if [[ "$RPC_MODE" == fail ]]; then exit 1; fi\n'
                              '    echo \'{"blocks":1171455,"pruned":true,"pruneheight":1011353,"initialblockdownload":false}\';;\n'
                              'esac\n',
            }
            for name, body in mocks.items():
                p = fakebin / name
                p.write_text(body)
                p.chmod(0o700)
            result = subprocess.run(
                [str(script), "status"],
                env={**os.environ, "PATH": str(fakebin) + ":" + os.environ["PATH"],
                     "TEST_DIR": temp, "RPC_MODE": rpc_mode},
                text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_status_includes_core_and_pruning(self):
        out = self.run_status()
        for expected in [
            "service=active", "enabled=enabled", "Core version: 4.0.1.6-test",
            "Smartnode: READY", "Block height: 1171455",
            "Pruning: enabled (configured: 256 MiB target; prune height: 1011353)",
            "IBD: No",
        ]:
            self.assertIn(expected, out)

    def test_rpc_failure_still_reports_configuration(self):
        out = self.run_status(rpc_mode="fail")
        self.assertIn("Pruning: unavailable (configured: 256 MiB target; RPC unavailable)", out)
        self.assertIn("Block height: unavailable", out)


if __name__ == "__main__":
    unittest.main()
