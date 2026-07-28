#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

text = text.replace(
    'USE_BOOTSTRAP=0; USE_POWCACHE=0\nCREATED_USERS=()\nCONFIGURED_USERS=()\n',
    'USE_BOOTSTRAP=0; USE_POWCACHE=0\nEXISTING_INSTALL=0; ADDITIONAL_USERS=1\nCREATED_USERS=()\nCONFIGURED_USERS=()\nEXISTING_USERS=()\n',
    1,
)

anchor = '''configure_multiple_users() {
    local count i user
    while true; do
        read -r -p "How many Smartnode users should be installed or configured? [1]: " count
'''
replacement = '''detect_existing_install() {
    local user home

    if [[ -L "$CURRENT_LINK" || -x "$CURRENT_LINK/$DAEMON" || -s "$USERS_FILE" ]] || compgen -G "/home/*/$CONF_DIR_NAME/$CONF_FILE" >/dev/null; then
        EXISTING_INSTALL=1
    fi

    (( EXISTING_INSTALL == 1 )) || return

    while read -r user; do
        [[ -n "$user" ]] || continue
        id "$user" &>/dev/null || continue
        home="$(getent passwd "$user" | cut -d: -f6)"
        [[ -f "$home/$CONF_DIR_NAME/$CONF_FILE" ]] || continue
        [[ " ${EXISTING_USERS[*]} " == *" $user "* ]] || EXISTING_USERS+=("$user")
    done < <({ cat "$USERS_FILE" 2>/dev/null || true; find /home -mindepth 3 -maxdepth 3 -path "*/$CONF_DIR_NAME/$CONF_FILE" -printf '%h\\n' 2>/dev/null | sed -E 's#^/home/([^/]+)/.*#\\1#'; } | sort -u)

    info "Existing Yerbas installation detected."
    if ((${#EXISTING_USERS[@]})); then
        info "Existing Smartnode users: ${EXISTING_USERS[*]}"
        CONFIGURED_USERS+=("${EXISTING_USERS[@]}")
    fi

    if prompt_yes_no "Add additional Smartnode users to this installation?" "Y"; then
        ADDITIONAL_USERS=1
    else
        ADDITIONAL_USERS=0
        info "No additional users will be added. Existing nodes and shared binaries will be updated and checked."
    fi
}

configure_multiple_users() {
    local count i user prompt_text="How many Smartnode users should be installed or configured? [1]: "
    (( EXISTING_INSTALL == 1 )) && prompt_text="How many additional Smartnode users should be added? [1]: "
    while true; do
        read -r -p "$prompt_text" count
'''
if anchor not in text:
    raise SystemExit("configure_multiple_users anchor not found")
text = text.replace(anchor, replacement, 1)

old_main = '''    initialize_paths
    detect_platform
    install_dependencies
    create_swap
    resolve_release

    prompt_yes_no "Download and install the latest bootstrap for each new node?" "N" && USE_BOOTSTRAP=1
    prompt_yes_no "Download and install the latest PoW cache?" "Y" && USE_POWCACHE=1

    stop_all_nodes
    install_shared_release
    install_service_template
    install_manager
    configure_multiple_users
'''
new_main = '''    initialize_paths
    detect_existing_install
    detect_platform
    install_dependencies
    create_swap
    resolve_release

    if (( EXISTING_INSTALL == 0 || ADDITIONAL_USERS == 1 )); then
        prompt_yes_no "Download and install the latest bootstrap for each new node?" "N" && USE_BOOTSTRAP=1
        prompt_yes_no "Download and install the latest PoW cache?" "Y" && USE_POWCACHE=1
    fi

    stop_all_nodes
    install_shared_release
    install_service_template
    install_manager
    (( EXISTING_INSTALL == 0 || ADDITIONAL_USERS == 1 )) && configure_multiple_users
'''
if old_main not in text:
    raise SystemExit("main block not found")
text = text.replace(old_main, new_main, 1)

path.write_text(text, encoding="utf-8")

readme = Path("README.md")
r = readme.read_text(encoding="utf-8")
needle = "Existing `yerbas.conf`, BLS keys, wallets, and blockchain data are preserved. The shared binaries are updated for all configured users."
replacement = needle + " When an existing installation is detected, the installer lists the existing Smartnode users and asks whether additional users should be added. Choosing no updates and checks the existing installation without creating another user."
if needle in r and replacement not in r:
    r = r.replace(needle, replacement, 1)
readme.write_text(r, encoding="utf-8")

# Trigger workflow after creation.
