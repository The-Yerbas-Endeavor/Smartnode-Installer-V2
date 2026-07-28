#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

new = r'''create_swap() {
    local ram_kb ram_mb recommended_gb total_bytes total_gb
    local swapfile_bytes=0 swapfile_gb=0 free_bytes free_gb
    local choice size_gb required_bytes old_active=0 backup=""
    local swap_names swap_partitions zram_devices

    ram_kb="$(grep -m1 '^MemTotal:' /proc/meminfo | tr -s ' ' | cut -d' ' -f2)"
    ram_mb=$(( ram_kb / 1024 ))

    if (( ram_mb <= 2048 )); then
        recommended_gb=2
    elif (( ram_mb <= 8192 )); then
        recommended_gb=4
    else
        recommended_gb=2
    fi

    total_bytes="$(swapon --show=SIZE --bytes --noheadings 2>/dev/null | awk '{total += $1} END {print total + 0}')"
    total_gb=$(( (total_bytes + 1073741823) / 1073741824 ))
    free_bytes="$(df -B1 --output=avail / | tail -n1 | tr -d ' ')"
    free_gb=$(( free_bytes / 1073741824 ))
    swap_names="$(swapon --show=NAME --noheadings 2>/dev/null || true)"
    swap_partitions="$(printf '%s\n' "$swap_names" | grep '^/dev/' | grep -v '^/dev/zram' || true)"
    zram_devices="$(printf '%s\n' "$swap_names" | grep '^/dev/zram' || true)"

    if [[ -e /swapfile ]]; then
        swapfile_bytes="$(stat -c '%s' /swapfile 2>/dev/null || echo 0)"
        swapfile_gb=$(( (swapfile_bytes + 1073741823) / 1073741824 ))
    fi

    echo
    echo "=================================================="
    echo "                 Swap Configuration"
    echo "=================================================="
    printf '  RAM:                  %s MB\n' "$ram_mb"
    printf '  Recommended swap:     %s GB\n' "$recommended_gb"
    printf '  Total active swap:    %s GB\n' "$total_gb"
    printf '  Available disk:       %s GB\n' "$free_gb"
    if [[ -e /swapfile ]]; then
        printf '  Managed /swapfile:    %s GB%s\n' "$swapfile_gb" "$(printf '%s\n' "$swap_names" | grep -qx '/swapfile' && echo ' (active)' || echo ' (inactive)')"
    else
        echo "  Managed /swapfile:    not present"
    fi
    [[ -z "$swap_partitions" ]] || printf '  Swap partition(s):    %s\n' "$(echo "$swap_partitions" | paste -sd ', ' -)"
    [[ -z "$zram_devices" ]] || printf '  ZRAM device(s):       %s\n' "$(echo "$zram_devices" | paste -sd ', ' -)"
    echo "=================================================="

    if [[ -e /swapfile ]]; then
        echo "  1) Keep current swap configuration"
        echo "  2) Resize /swapfile"
        echo "  3) Remove /swapfile"
        echo "  4) Skip swap management"
        while true; do
            read -r -p "Selection [1]: " choice
            choice="${choice:-1}"
            [[ "$choice" =~ ^[1-4]$ ]] && break
            echo "Enter 1, 2, 3, or 4."
        done
    else
        echo "  1) Create /swapfile (${recommended_gb} GB recommended)"
        echo "  2) Keep current external swap configuration"
        echo "  3) Skip swap management"
        while true; do
            read -r -p "Selection [1]: " choice
            choice="${choice:-1}"
            [[ "$choice" =~ ^[1-3]$ ]] && break
            echo "Enter 1, 2, or 3."
        done
        case "$choice" in
            1) choice=2 ;;
            2|3) info "Keeping the current swap configuration."; return 0 ;;
        esac
    fi

    case "$choice" in
        1|4)
            info "Keeping the current swap configuration."
            return 0
            ;;
        3)
            if ! prompt_yes_no "Remove the managed /swapfile? External swap will not be changed." "N"; then
                info "Swap removal cancelled."
                return 0
            fi
            if printf '%s\n' "$swap_names" | grep -qx '/swapfile'; then
                swapoff /swapfile
            fi
            rm -f /swapfile
            sed -i '\|^/swapfile[[:space:]]|d' /etc/fstab
            info "Managed /swapfile removed."
            log "INFO: Removed managed /swapfile"
            return 0
            ;;
    esac

    while true; do
        read -r -p "Desired /swapfile size in GB [$recommended_gb]: " size_gb
        size_gb="${size_gb:-$recommended_gb}"
        [[ "$size_gb" =~ ^[1-9][0-9]*$ ]] || { echo "Enter a whole number greater than zero."; continue; }
        required_bytes=$(( size_gb * 1073741824 ))
        if (( required_bytes > free_bytes + swapfile_bytes )); then
            warn "Not enough disk space for a ${size_gb} GB swapfile."
            continue
        fi
        break
    done

    echo
    echo "Current /swapfile: ${swapfile_gb} GB"
    echo "New /swapfile:     ${size_gb} GB"
    prompt_yes_no "Proceed with this swap change?" "Y" || { info "Swap change cancelled."; return 0; }

    if printf '%s\n' "$swap_names" | grep -qx '/swapfile'; then
        old_active=1
        info "Disabling the existing /swapfile..."
        swapoff /swapfile
    fi

    if [[ -e /swapfile ]]; then
        backup="/swapfile.yerbas-backup.$$"
        mv /swapfile "$backup"
    fi

    if ! fallocate -l "${size_gb}G" /swapfile 2>/dev/null; then
        warn "fallocate is unavailable on this filesystem; using dd."
        if ! dd if=/dev/zero of=/swapfile bs=1M count=$(( size_gb * 1024 )) status=progress; then
            rm -f /swapfile
            [[ -z "$backup" ]] || mv "$backup" /swapfile
            (( old_active == 0 )) || swapon /swapfile || true
            die "Unable to allocate the new swapfile; the previous file was restored."
        fi
    fi

    chmod 600 /swapfile
    if ! mkswap /swapfile >/dev/null || ! swapon /swapfile; then
        swapoff /swapfile 2>/dev/null || true
        rm -f /swapfile
        [[ -z "$backup" ]] || mv "$backup" /swapfile
        (( old_active == 0 )) || swapon /swapfile || true
        die "Swap activation failed; the previous swapfile was restored."
    fi

    grep -q '^/swapfile[[:space:]]' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    rm -f "$backup"

    if ! swapon --show=NAME --noheadings 2>/dev/null | grep -qx '/swapfile'; then
        die "Swap verification failed: /swapfile is not active."
    fi
    [[ "$(stat -c '%a' /swapfile)" == "600" ]] || die "Swap verification failed: permissions are not 600."

    swapfile_bytes="$(swapon --show=NAME,SIZE --bytes --noheadings 2>/dev/null | awk '$1 == "/swapfile" {print $2; exit}')"
    swapfile_gb=$(( (swapfile_bytes + 1073741823) / 1073741824 ))
    info "Swap configuration complete: /swapfile is active at ${swapfile_gb} GB."
    log "INFO: Swap verified active size=${swapfile_gb}GB permissions=600 persistent=yes"
}
'''

pattern = re.compile(r'create_swap\(\) \{.*?\n\}\n\ngithub_latest_json\(\)', re.S)
replacement = new + '\ngithub_latest_json()'
updated, count = pattern.subn(lambda _m: replacement, text, count=1)
if count != 1:
    raise SystemExit("create_swap block not found or was ambiguous")
path.write_text(updated, encoding="utf-8")
