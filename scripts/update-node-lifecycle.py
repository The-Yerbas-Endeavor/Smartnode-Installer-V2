#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old_globals = '''CREATED_USERS=()
CONFIGURED_USERS=()
EXISTING_USERS=()
'''
new_globals = '''CREATED_USERS=()
CONFIGURED_USERS=()
EXISTING_USERS=()
NEW_NODE_USERS=()
'''
if old_globals not in text:
    raise SystemExit("user array globals not found")
text = text.replace(old_globals, new_globals, 1)

old_config_tail = '''    systemctl enable "yerbasd@$user"
    CONFIGURED_USERS+=("$user")
    unset bls rpcpass
}
'''
new_config_tail = '''    systemctl enable "yerbasd@$user"
    CONFIGURED_USERS+=("$user")
    NEW_NODE_USERS+=("$user")
    unset bls rpcpass
}
'''
if old_config_tail not in text:
    raise SystemExit("new-node tracking insertion point not found")
text = text.replace(old_config_tail, new_config_tail, 1)

start = text.find('start_and_verify_nodes() {\n')
end = text.find('\nrollback_release() {', start)
if start < 0 or end < 0:
    raise SystemExit("start_and_verify_nodes block not found")

lifecycle = r'''start_nodes() {
    local user failed=0

    for user in "$@"; do
        [[ -n "$user" ]] || continue
        info "Starting Smartnode service for $user..."
        if ! systemctl restart "yerbasd@$user"; then
            warn "$user service failed to restart. Check: journalctl -u yerbasd@$user"
            failed=1
        fi
    done

    return "$failed"
}

verify_services() {
    local user attempt
    local failed=0
    local max_attempts=15

    for user in "$@"; do
        [[ -n "$user" ]] || continue
        attempt=0
        until systemctl is-active --quiet "yerbasd@$user"; do
            attempt=$((attempt + 1))
            if (( attempt >= max_attempts )); then
                warn "$user service is not active. Check: journalctl -u yerbasd@$user"
                failed=1
                break
            fi
            sleep 2
        done

        if systemctl is-active --quiet "yerbasd@$user"; then
            info "$user service is active."
        fi
    done

    return "$failed"
}

verify_smartnodes() {
    local user home attempts status_output
    local max_attempts=24
    local retry_delay=5

    if (( $# == 0 )); then
        info "No newly configured Smartnodes require detailed status verification."
        return 0
    fi

    for user in "$@"; do
        [[ -n "$user" ]] || continue
        home="$(getent passwd "$user" | cut -d: -f6)"
        attempts=0

        info "Loading blocks and checking the newly configured Smartnode for $user. Wait up to 2 minutes. Roll one up..."
        until sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" getblockchaininfo >/dev/null 2>&1; do
            attempts=$((attempts + 1))
            if (( attempts >= max_attempts )); then
                warn "$user service is active, but RPC is still not ready after 2 minutes. The chain may still be loading. Check: journalctl -u yerbasd@$user"
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
text = text[:start] + lifecycle + text[end:]

old_main = '''    if ! start_and_verify_nodes; then
        rollback_release && start_and_verify_nodes || true
        die "One or more nodes failed after update; rollback attempted."
    fi
    summary
'''
new_main = '''    if ! start_nodes "${CONFIGURED_USERS[@]}" || ! verify_services "${CONFIGURED_USERS[@]}"; then
        if rollback_release; then
            start_nodes "${CONFIGURED_USERS[@]}" || true
            verify_services "${CONFIGURED_USERS[@]}" || true
        fi
        die "One or more Smartnode services failed after the update; rollback attempted."
    fi

    if (( EXISTING_INSTALL == 0 )); then
        verify_smartnodes "${CONFIGURED_USERS[@]}"
    elif (( ADDITIONAL_USERS == 1 )); then
        verify_smartnodes "${NEW_NODE_USERS[@]}"
        info "Existing Smartnodes were restarted and service-checked without running RPC or Smartnode status checks."
    else
        info "Existing Smartnodes were restarted and service-checked without running RPC or Smartnode status checks."
    fi
    summary
'''
if old_main not in text:
    raise SystemExit("main verification block not found")
text = text.replace(old_main, new_main, 1)

path.write_text(text, encoding="utf-8")
