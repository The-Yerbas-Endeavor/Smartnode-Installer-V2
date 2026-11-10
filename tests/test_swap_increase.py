"""Unprivileged regression tests for additive swap maintenance."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IncreaseSwapTests(unittest.TestCase):
    def run_bash(self, script):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                ["bash", "-c", 'source "$REPO/install.sh"\nLOG_FILE="$TEST_DIR/log"\n'
                 'YERBAS_FSTAB="$TEST_DIR/fstab"\n'
                 'YERBAS_EXTRA_SWAP_PREFIX="$TEST_DIR/swap-extra"\n'
                 + script],
                env={**os.environ, "REPO": str(ROOT), "TEST_DIR": td},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result

    def test_add_swap_preserves_existing_and_persists_new_file(self):
        result = self.run_bash(r'''echo 'original fstab entry' > "$YERBAS_FSTAB"
        swapon() {
            if [[ "$1" == --show=SIZE ]]; then echo 2147483648; return 0; fi
            printf '%s\n' "$*" >"$TEST_DIR/swapon-called"
        }
        df() { printf 'Avail\n10737418240\n'; }
        fallocate() {
            [[ "$1" == -l ]] || return 99
            truncate -s 1M "$3"
        }
        mkswap() { return 0; }
        increase_swap <<< $'1\ny'
        [[ -f "$YERBAS_EXTRA_SWAP_PREFIX-1" ]]
        [[ $(stat -c %a "$YERBAS_EXTRA_SWAP_PREFIX-1") == 600 ]]
        grep -qx 'original fstab entry' "$YERBAS_FSTAB"
        grep -q 'swap-extra-1 none swap sw 0 0' "$YERBAS_FSTAB"
        [[ "$(cat "$TEST_DIR/swapon-called")" == "$YERBAS_EXTRA_SWAP_PREFIX-1" ]]''')
        self.assertIn("Added 1 GiB", result.stdout)

    def test_cancel_does_not_modify_swap(self):
        self.run_bash(r'''df() { printf 'Avail\n10737418240\n'; }
        swapon() { [[ "$1" == --show=SIZE ]] && echo 0; }
        fallocate() { exit 99; }
        increase_swap <<< ''
        [[ ! -e "$YERBAS_EXTRA_SWAP_PREFIX-1" ]]''')

    def test_insufficient_space_is_rejected(self):
        result = self.run_bash(r'''df() { printf 'Avail\n1073741824\n'; }
        swapon() { [[ "$1" == --show=SIZE ]] && echo 0; }
        fallocate() { exit 99; }
        increase_swap <<< '1'
        [[ ! -e "$YERBAS_EXTRA_SWAP_PREFIX-1" ]]''')
        self.assertIn("Insufficient disk space", result.stdout)

    def test_activation_failure_cleans_up_new_file(self):
        self.run_bash(r'''df() { printf 'Avail\n10737418240\n'; }
        swapon() {
            [[ "$1" == --show=SIZE ]] && { echo 0; return 0; }
            return 1
        }
        fallocate() { truncate -s 1M "$3"; }
        mkswap() { return 0; }
        if increase_swap <<< $'1\ny'; then exit 99; fi
        [[ ! -e "$YERBAS_EXTRA_SWAP_PREFIX-1" ]]
        [[ ! -e "$YERBAS_FSTAB" ]]''')

if __name__ == "__main__":
    unittest.main()
