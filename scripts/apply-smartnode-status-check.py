#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")
old = '''start_and_verify_nodes() {
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
new = '''start_and_verify_nodes() {
    local user home attempts status_output
    local max_attempts=24
    local retry_delay=5

    for user in "${CONFIGURED_USERS[@]}"; do
        info "Starting Smartnode for $user..."
        systemctl restart "yerbasd@$user"
        home="$(getent passwd "$user" | cut -d: -f6)"
        attempts=0

        info "Loading blocks and checking Smartnode status for $user. Wait up to 2 minutes. Roll one up..."
        until sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" getblockchaininfo >/dev/null 2>&1; do
            attempts=$((attempts + 1))
            if (( attempts >= max_attempts )); then
                warn "$user service is running, but RPC is still not ready after 2 minutes. The chain may still be loading. Check: journalctl -u yerbasd@$user"
                break
            fi
            sleep "$retry_delay"
        done

        if (( attempts >= max_attempts )); then
            continue
        fi

        info "$user RPC health check passed. Checking Smartnode status..."
        status_output="$(sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" smartnode status 2>&1 || true)"
        log "SMARTNODE STATUS $user: $status_output"

        if grep -q 'READY' <<<"$status_output"; then
            info "$user Smartnode is READY and ready to rock!"
        elif grep -q 'WAITING_FOR_PROTX' <<<"$status_output"; then
            warn "$user Smartnode is not ready yet: waiting for ProTx to appear on-chain."
        elif grep -qiE 'make sure server is running|could not connect|connection refused|couldn.t connect' <<<"$status_output"; then
            warn "$user could not query Smartnode status. Make sure the server is running and the correct RPC port is configured."
        else
            warn "$user returned an unexpected Smartnode status. Review $home/$CONF_DIR_NAME/$CONF_FILE and run: yerbas-node-manager cli $user smartnode status"
        fi
    done
}
'''
if old not in text:
    raise SystemExit("start_and_verify_nodes block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
