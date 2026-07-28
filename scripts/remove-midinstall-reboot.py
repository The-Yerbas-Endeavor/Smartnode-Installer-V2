#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

text = text.replace(
    'RESUME_SCRIPT="/usr/local/lib/yerbas-installer/install.sh"\nRESUME_SERVICE="/etc/systemd/system/yerbas-installer-resume.service"\nRESUME_TMUX_SESSION="yerbas-installer"\n',
    '',
    1,
)

text = text.replace(
    'apt-get install -y ca-certificates curl jq unzip wget openssl pwgen ufw fail2ban util-linux rsync tmux',
    'apt-get install -y ca-certificates curl jq unzip wget openssl pwgen ufw fail2ban util-linux rsync',
    1,
)

text, count = re.subn(
    r'\nremove_installer_resume_service\(\) \{.*?\n\}\n\nschedule_installer_resume\(\) \{.*?\n\}\n\nnetwork_provisioning\(\) \{',
    '\nnetwork_provisioning() {',
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("Unable to remove obsolete reboot-resume functions")

old_resume = '''    if [[ -f "$NETWORK_RESUME_FLAG" || -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then
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
new_resume = '''    if [[ -f "$NETWORK_RESUME_FLAG" || -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then
        RESUME_AFTER_NETWORK=1
        rm -f "$NETWORK_RESUME_FLAG" "$LEGACY_IPV6_RESUME_FLAG"
        systemctl disable yerbas-installer-resume.service >/dev/null 2>&1 || true
        rm -f /etc/systemd/system/yerbas-installer-resume.service
        systemctl daemon-reload >/dev/null 2>&1 || true
        if [[ -s "$NETWORK_ADDRESS_FILE" ]]; then
            info "Network address provisioning was completed before the previous interruption."
            sed 's/^/  - /' "$NETWORK_ADDRESS_FILE"
        fi
        info "Continuing installation after completed network provisioning."
        return 0
    fi
'''
if old_resume not in text:
    raise SystemExit("Existing network-resume block not found")
text = text.replace(old_resume, new_resume, 1)

old_reboot = '''    touch "$NETWORK_RESUME_FLAG"
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
new_reboot = '''    rm -f "$NETWORK_RESUME_FLAG" "$LEGACY_IPV6_RESUME_FLAG"
    info "Network provisioning is active and persistent. Continuing installation without reboot."
    return 0
'''
if old_reboot not in text:
    raise SystemExit("Existing network reboot block not found")
text = text.replace(old_reboot, new_reboot, 1)

path.write_text(text, encoding="utf-8")
