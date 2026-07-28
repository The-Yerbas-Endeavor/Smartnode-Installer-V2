#!/usr/bin/env python3
# Applies one-time prompt wording and automatic post-reboot resume support.
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

text = text.replace(
    'NETWORK_NETPLAN_FILE="/etc/netplan/10-ens3.yaml"\nLEGACY_IPV6_RESUME_FLAG="$STATE_DIR/ipv6-resume"\nRESUME_AFTER_NETWORK=0',
    'NETWORK_NETPLAN_FILE="/etc/netplan/10-ens3.yaml"\nLEGACY_IPV6_RESUME_FLAG="$STATE_DIR/ipv6-resume"\nRESUME_SCRIPT="/usr/local/lib/yerbas-installer/install.sh"\nRESUME_SERVICE="/etc/systemd/system/yerbas-installer-resume.service"\nRESUME_TMUX_SESSION="yerbas-installer"\nRESUME_AFTER_NETWORK=0',
    1,
)

text = text.replace(
    'apt-get install -y ca-certificates curl jq unzip wget openssl pwgen ufw fail2ban util-linux rsync',
    'apt-get install -y ca-certificates curl jq unzip wget openssl pwgen ufw fail2ban util-linux rsync tmux',
    1,
)

text = text.replace(
    'prompt_yes_no "Would you like to add IPv4 addresses supplied by your server host?" "N" && add_ipv4=1',
    'prompt_yes_no "Would you like to add additional IPv4 addresses supplied by your server host?" "N" && add_ipv4=1',
    1,
)

marker = '''restore_network_configuration() {
    local backup_file="$1"
    if [[ -n "$backup_file" && -f "$backup_file" ]]; then
        cp -a "$backup_file" "$NETWORK_NETPLAN_FILE"
    else
        rm -f "$NETWORK_NETPLAN_FILE"
    fi
    netplan generate >>"$LOG_FILE" 2>&1 || true
    netplan apply >>"$LOG_FILE" 2>&1 || true
    rm -f "$NETWORK_ADDRESS_FILE"
}
'''

addition = marker + r'''
remove_installer_resume_service() {
    systemctl disable yerbas-installer-resume.service >/dev/null 2>&1 || true
    rm -f "$RESUME_SERVICE"
    systemctl daemon-reload >/dev/null 2>&1 || true
}

schedule_installer_resume() {
    local source_script
    source_script="$(readlink -f "${BASH_SOURCE[0]}")"
    [[ -f "$source_script" ]] || die "Unable to locate the running installer for automatic resume."

    install -d -m 0755 "$(dirname "$RESUME_SCRIPT")"
    install -m 0755 "$source_script" "$RESUME_SCRIPT"

    cat >"$RESUME_SERVICE" <<EOF
[Unit]
Description=Resume Yerbas Smartnode Installer after network reboot
Wants=network-online.target
After=network-online.target
ConditionPathExists=$NETWORK_RESUME_FLAG

[Service]
Type=oneshot
ExecStart=/usr/bin/tmux new-session -d -s $RESUME_TMUX_SESSION /bin/bash $RESUME_SCRIPT --resume
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable yerbas-installer-resume.service >/dev/null
}
'''

if marker not in text:
    raise SystemExit("restore_network_configuration block not found")
text = text.replace(marker, addition, 1)

old_resume = '''    if [[ -f "$NETWORK_RESUME_FLAG" || -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then
        RESUME_AFTER_NETWORK=1
        rm -f "$NETWORK_RESUME_FLAG" "$LEGACY_IPV6_RESUME_FLAG"
        if [[ -s "$NETWORK_ADDRESS_FILE" ]]; then
            info "Network address provisioning was completed before the previous reboot."
            sed 's/^/  - /' "$NETWORK_ADDRESS_FILE"
        fi
        return 0
    fi
'''
new_resume = '''    if [[ -f "$NETWORK_RESUME_FLAG" || -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then
        RESUME_AFTER_NETWORK=1
        rm -f "$NETWORK_RESUME_FLAG" "$LEGACY_IPV6_RESUME_FLAG"
        remove_installer_resume_service
        if [[ -s "$NETWORK_ADDRESS_FILE" ]]; then
            info "Network address provisioning was completed before the previous reboot."
            sed 's/^/  - /' "$NETWORK_ADDRESS_FILE"
        fi
        info "Installer resumed automatically after reboot."
        return 0
    fi
'''
if old_resume not in text:
    raise SystemExit("network resume block not found")
text = text.replace(old_resume, new_resume, 1)

old_reboot = '''    touch "$NETWORK_RESUME_FLAG"
    sync
    warn "The server must reboot to complete network provisioning. Your SSH session will disconnect."
    echo "After reconnecting, run the installer again; it will continue after this stage:"
    echo "  sudo bash $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
    read -r -p "Press Enter to reboot now, or Ctrl+C to reboot later..."
    systemctl reboot
    exit 0
'''
new_reboot = '''    touch "$NETWORK_RESUME_FLAG"
    schedule_installer_resume
    sync
    warn "The server must reboot to complete network provisioning. Your SSH session will disconnect."
    echo "The installer will resume automatically after reboot in tmux session: $RESUME_TMUX_SESSION"
    echo "After reconnecting, view or continue it with:"
    echo "  sudo tmux attach -t $RESUME_TMUX_SESSION"
    echo "Installer output is also recorded in: $LOG_FILE"
    read -r -p "Press Enter to reboot now, or Ctrl+C to reboot later..."
    systemctl reboot
    exit 0
'''
if old_reboot not in text:
    raise SystemExit("network reboot block not found")
text = text.replace(old_reboot, new_reboot, 1)

path.write_text(text, encoding="utf-8")
