#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")
old = '''create_swap() {
    local size_gb
    if swapon --show=NAME --noheadings | grep -qx '/swapfile'; then
        info "Existing /swapfile is active; leaving it unchanged."
        return
    fi
    if [[ -e /swapfile ]]; then
        warn "/swapfile exists but is not active; leaving it unchanged."
        return
    fi
    while true; do
        read -r -p "Swap size in GB [4]: " size_gb
        size_gb="${size_gb:-4}"
        [[ "$size_gb" =~ ^[1-9][0-9]*$ ]] && break
        echo "Enter a whole number greater than zero."
    done
    info "Creating ${size_gb} GB swap file..."
    fallocate -l "${size_gb}G" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
}
'''
new = '''create_swap() {
    local size_gb current_bytes current_gb default_gb=4

    current_bytes="$(swapon --show=SIZE --bytes --noheadings 2>/dev/null | awk '{total += $1} END {print total + 0}')"
    current_gb="$(awk -v bytes="$current_bytes" 'BEGIN {printf "%.1f", bytes / 1073741824}')"

    if (( current_bytes > 0 )); then
        info "Detected ${current_gb} GB of active swap."

        if swapon --show=NAME --noheadings 2>/dev/null | grep -qx '/swapfile'; then
            default_gb="$(awk -v bytes="$current_bytes" 'BEGIN {value = int((bytes + 1073741823) / 1073741824); print value > 0 ? value : 4}')"
            if ! prompt_yes_no "Would you like to adjust the /swapfile size?" "N"; then
                info "Keeping the current swap configuration."
                return 0
            fi
        else
            warn "Active swap exists, but it is not managed as /swapfile."
            if ! prompt_yes_no "Would you like to create an additional managed /swapfile?" "N"; then
                info "Keeping the current swap configuration."
                return 0
            fi
        fi
    else
        info "No active swap detected."
        if ! prompt_yes_no "Would you like to create a /swapfile?" "Y"; then
            info "Continuing without creating swap."
            return 0
        fi
    fi

    while true; do
        read -r -p "Desired /swapfile size in GB [$default_gb]: " size_gb
        size_gb="${size_gb:-$default_gb}"
        [[ "$size_gb" =~ ^[1-9][0-9]*$ ]] && break
        echo "Enter a whole number greater than zero."
    done

    if swapon --show=NAME --noheadings 2>/dev/null | grep -qx '/swapfile'; then
        info "Disabling the existing /swapfile..."
        swapoff /swapfile
    fi

    if [[ -e /swapfile ]]; then
        rm -f /swapfile
    fi

    info "Creating ${size_gb} GB swap file..."
    fallocate -l "${size_gb}G" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
}
'''
if old not in text:
    raise SystemExit("create_swap block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
