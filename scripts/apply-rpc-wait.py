#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")
old = '''start_and_verify_nodes() {
    local user home attempts
    for user in "${CONFIGURED_USERS[@]}"; do
        info "Starting Smartnode for $user..."
        systemctl restart "yerbasd@$user"
        home="$(getent passwd "$user" | cut -d: -f6)"
        attempts=0
        until sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" getblockchaininfo >/dev/null 2>&1; do
            attempts=$((attempts + 1))
            if (( attempts >= 12 )); then warn "$user service started but RPC is not ready. Check: journalctl -u yerbasd@$user"; break; fi
            sleep 5
        done
        if (( attempts < 12 )); then info "$user RPC health check passed."; fi
    done
}
'''
new = '''start_and_verify_nodes() {
    local user home attempts
    local max_attempts=24
    local retry_delay=5

    for user in "${CONFIGURED_USERS[@]}"; do
        info "Starting Smartnode for $user..."
        systemctl restart "yerbasd@$user"
        home="$(getent passwd "$user" | cut -d: -f6)"
        attempts=0

        info "Waiting up to 2 minutes for $user to load the chain and make RPC available..."
        until sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" getblockchaininfo >/dev/null 2>&1; do
            attempts=$((attempts + 1))
            if (( attempts >= max_attempts )); then
                warn "$user service is running, but RPC is still not ready after 2 minutes. The chain may still be loading. Check: journalctl -u yerbasd@$user"
                break
            fi
            sleep "$retry_delay"
        done

        if (( attempts < max_attempts )); then
            info "$user RPC health check passed."
        fi
    done
}
'''
if old not in text:
    raise SystemExit("start_and_verify_nodes block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Triggered migration; remove this helper after application.
