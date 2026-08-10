#!/usr/bin/env bash
set -Eeuo pipefail

# Yerbas Multi-User Smartnode Installer v2
VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COIN_NAME="Yerbas"
DAEMON="yerbasd"
CLI="yerbas-cli"
TX="yerbas-tx"
CONF_DIR_NAME=".yerbascore"
CONF_FILE="yerbas.conf"
YERB_REPO="The-Yerbas-Endeavor/yerbas"
BOOTSTRAP_REPO="The-Yerbas-Endeavor/YERB-Bootstrap"
INSTALL_ROOT="/opt/yerbas"
RELEASES_DIR="$INSTALL_ROOT/releases"
CURRENT_LINK="$INSTALL_ROOT/current"
CACHE_DIR="/var/cache/yerbas"
STATE_DIR="/var/lib/yerbas-installer"
USERS_FILE="$STATE_DIR/users"
SERVICE_TEMPLATE="/etc/systemd/system/yerbasd@.service"
MANAGER="/usr/local/sbin/yerbas-node-manager"
LOG_FILE="/var/log/yerbas-installer-v2.log"
DEFAULT_P2P_PORT=15420
DEFAULT_RPC_PORT=9494

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
YG="$GREEN"; CN="$RESET"
ARCH=""; UBUNTU_VERSION=""; RELEASE_TAG=""; WALLET_URL=""; BOOTSTRAP_URL=""; BOOTSTRAP_SIZE=0; POWCACHE_URL=""
USE_BOOTSTRAP=0; USE_POWCACHE=0
EXISTING_INSTALL=0; ADDITIONAL_USERS=1
CREATED_USERS=()
CONFIGURED_USERS=()
EXISTING_USERS=()
NEW_NODE_USERS=()
NETWORK_RESUME_FLAG="$STATE_DIR/network-resume"
NETWORK_ADDRESS_FILE="$STATE_DIR/network-addresses"
NETWORK_NETPLAN_FILE="/etc/netplan/10-ens3.yaml"
LEGACY_IPV6_RESUME_FLAG="$STATE_DIR/ipv6-resume"
RESUME_AFTER_NETWORK=0

trap 'echo -e "${RED}Installer failed on line $LINENO. See $LOG_FILE${RESET}" >&2' ERR

log() { printf '[%s] %s\n' "$(date -Is)" "$*" >> "$LOG_FILE"; }
info() { echo -e "${CYAN}$*${RESET}"; log "INFO: $*"; }
warn() { echo -e "${YELLOW}$*${RESET}"; log "WARN: $*"; }
die() { echo -e "${RED}ERROR: $*${RESET}" >&2; log "ERROR: $*"; exit 1; }

require_root() {
    [[ $EUID -eq 0 ]] || die "Run with sudo: sudo bash install-v2.sh"
}

yerbas_title() {
    clear || true
    echo -e "${YG}YYYYYYY       YYYYYYYEEEEEEEEEEEEEEEEEEEEEERRRRRRRRRRRRRRRRR   BBBBBBBBBBBBBBBBB               AAA                 SSSSSSSSSSSSSSS   "
    echo "Y:::::Y       Y:::::YE::::::::::::::::::::ER::::::::::::::::R  B::::::::::::::::B             A:::A              SS:::::::::::::::S  "
    echo "Y:::::Y       Y:::::YE::::::::::::::::::::ER::::::RRRRRR:::::R B::::::BBBBBB:::::B           A:::::A            S:::::SSSSSS::::::S  "
    echo "Y::::::Y     Y::::::YEE::::::EEEEEEEEE::::ERR:::::R     R:::::RBB:::::B     B:::::B         A:::::::A           S:::::S     SSSSSSS  "
    echo "YYY:::::Y   Y:::::YYY  E:::::E       EEEEEE  R::::R     R:::::R  B::::B     B:::::B        A:::::::::A          S:::::S              "
    echo "   Y:::::Y Y:::::Y     E:::::E               R::::R     R:::::R  B::::B     B:::::B       A:::::A:::::A         S:::::S              "
    echo "    Y:::::Y:::::Y      E::::::EEEEEEEEEE     R::::RRRRRR:::::R   B::::BBBBBB:::::B       A:::::A A:::::A         S::::SSSS           "
    echo "     Y:::::::::Y       E:::::::::::::::E     R:::::::::::::RR    B:::::::::::::BB       A:::::A   A:::::A         SS::::::SSSSS      "
    echo "      Y:::::::Y        E:::::::::::::::E     R::::RRRRRR:::::R   B::::BBBBBB:::::B     A:::::A     A:::::A          SSS::::::::SS    "
    echo "       Y:::::Y         E::::::EEEEEEEEEE     R::::R     R:::::R  B::::B     B:::::B   A:::::AAAAAAAAA:::::A            SSSSSS::::S   "
    echo "       Y:::::Y         E:::::E               R::::R     R:::::R  B::::B     B:::::B  A:::::::::::::::::::::A                S:::::S  "
    echo "       Y:::::Y         E:::::E       EEEEEE  R::::R     R:::::R  B::::B     B:::::B A:::::AAAAAAAAAAAAA:::::A               S:::::S  "
    echo "       Y:::::Y       EE::::::EEEEEEEE:::::ERR:::::R     R:::::RBB:::::BBBBBB::::::BA:::::A             A:::::A  SSSSSSS     S:::::S  "
    echo "    YYYY:::::YYYY    E::::::::::::::::::::ER::::::R     R:::::RB:::::::::::::::::BA:::::A               A:::::A S::::::SSSSSS:::::S  "
    echo "    Y:::::::::::Y    E::::::::::::::::::::ER::::::R     R:::::RB::::::::::::::::BA:::::A                 A:::::AS:::::::::::::::SS   "
    echo -e "    YYYYYYYYYYYYY    EEEEEEEEEEEEEEEEEEEEEERRRRRRRR     RRRRRRRBBBBBBBBBBBBBBBBBAAAAAAA                   AAAAAAASSSSSSSSSSSSSSS     ${CN}"
    echo
    echo "     ${COIN_NAME} Multi-User Smartnode Installer v${VERSION}"
    echo "     Shared binaries • isolated users • systemd instances • safe updates"
    echo
}

banner() {
    yerbas_title
}

prompt_yes_no() {
    local prompt="$1" default="${2:-N}" answer
    local suffix="[y/N]"
    [[ "$default" == "Y" ]] && suffix="[Y/n]"
    while true; do
        read -r -p "$prompt $suffix: " answer
        answer="${answer:-$default}"
        case "${answer,,}" in y|yes) return 0 ;; n|no) return 1 ;; *) echo "Enter y or n." ;; esac
    done
}

valid_username() { [[ "$1" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; }
valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 1024 && $1 <= 65535 )); }
port_in_use() { ss -H -lntup 2>/dev/null | awk '{print $5}' | grep -Eq "(^|:)$1$"; }

initialize_paths() {
    install -d -m 0755 "$INSTALL_ROOT" "$RELEASES_DIR" "$CACHE_DIR" "$STATE_DIR"
    touch "$USERS_FILE" "$LOG_FILE"
    chmod 0600 "$USERS_FILE"
}

detect_platform() {
    [[ -r /etc/os-release ]] || die "Cannot detect operating system."
    . /etc/os-release
    UBUNTU_VERSION="${VERSION_ID:-}"
    ARCH="$(uname -m)"
    [[ "${ID:-}" == "ubuntu" ]] || die "Ubuntu is required."
    case "$UBUNTU_VERSION" in 22.04|24.04|26.04) ;; *) die "Supported Ubuntu versions: 22.04, 24.04, 26.04." ;; esac
    case "$ARCH" in x86_64|aarch64) ;; *) die "Unsupported architecture: $ARCH" ;; esac
    info "Detected Ubuntu $UBUNTU_VERSION on $ARCH."
}

install_dependencies() {
    info "Installing required packages and server protections..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ca-certificates curl jq unzip wget openssl pwgen ufw fail2ban util-linux rsync
    systemctl enable --now fail2ban
    install -d -m 0755 /etc/fail2ban/jail.d
    cat >/etc/fail2ban/jail.d/yerbas-sshd.local <<'JAIL'
[sshd]
enabled = true
port = ssh
maxretry = 3
JAIL
    systemctl restart fail2ban
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow OpenSSH
    ufw --force enable
}

create_swap() {
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

validate_ipv4_cidr() {
    local address="$1"
    python3 - "$address" <<'PY'
import ipaddress
import sys

try:
    interface = ipaddress.IPv4Interface(sys.argv[1])
except ValueError:
    raise SystemExit(1)

ip = interface.ip
if ip.is_unspecified or ip.is_loopback or ip.is_multicast or ip.is_link_local:
    raise SystemExit(1)
print(interface.with_prefixlen)
PY
}

normalize_ipv6_prefix64() {
    local address="$1"
    python3 - "$address" <<'PY'
import ipaddress
import sys
try:
    interface = ipaddress.IPv6Interface(sys.argv[1])
except ValueError:
    raise SystemExit(1)
print(interface.network.network_address.compressed)
PY
}

generate_ipv6_addresses() {
    local current_address="$1" count="$2"
    python3 - "$current_address" "$count" <<'PY'
import ipaddress
import sys

interface = ipaddress.IPv6Interface(sys.argv[1])
count = int(sys.argv[2])
base = int(interface.ip) & ~0xff

for suffix in range(1, count + 1):
    address = ipaddress.IPv6Address(base | suffix)
    if address == interface.ip:
        continue
    print(f"{address.compressed}/{interface.network.prefixlen}")
PY
}

network_address_is_active() {
    local family="$1" interface="$2" expected="$3"
    local command_family
    [[ "$family" == "4" ]] && command_family="-4" || command_family="-6"

    ip -j "$command_family" addr show dev "$interface" 2>/dev/null | \
        python3 -c '
import ipaddress
import json
import sys

expected = ipaddress.ip_address(sys.argv[1].split("/", 1)[0])
try:
    links = json.load(sys.stdin)
except json.JSONDecodeError:
    raise SystemExit(1)

for link in links:
    for info in link.get("addr_info", []):
        local = info.get("local")
        if not local:
            continue
        try:
            if ipaddress.ip_address(local) == expected:
                raise SystemExit(0)
        except ValueError:
            continue
raise SystemExit(1)
' "$expected"
}

restore_network_configuration() {
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

network_provisioning() {
    local interface primary_ipv4 ipv4_gateway current_ipv6="" ipv6_prefix=""
    local dns_list dns_yaml backup_file address normalized family verified attempt
    local add_ipv4=0 add_ipv6=0 ipv4_count=0 ipv6_count=0 generated_ipv6=""
    local -a current_ipv4_addresses=() current_ipv6_addresses=() supplied_ipv4=()

    if [[ -f "$NETWORK_RESUME_FLAG" || -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then
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

    prompt_yes_no "Would you like to add additional IPv4 addresses supplied by your server host?" "N" && add_ipv4=1
    prompt_yes_no "Would you like to create additional IPv6 addresses?" "N" && add_ipv6=1

    if (( add_ipv4 == 0 && add_ipv6 == 0 )); then
        info "Skipping additional network address provisioning."
        return 0
    fi

    interface="$(ip -4 route show default 2>/dev/null | awk 'NR == 1 {print $5}')"
    [[ -n "$interface" ]] || die "Unable to detect the primary network interface."

    mapfile -t current_ipv4_addresses < <(ip -o -4 addr show dev "$interface" scope global | awk '{print $4}' | sort -u)
    ((${#current_ipv4_addresses[@]})) || die "Unable to detect the current IPv4 address and prefix on $interface."
    primary_ipv4="${current_ipv4_addresses[0]}"

    ipv4_gateway="$(ip -4 route show default dev "$interface" 2>/dev/null | awk 'NR == 1 {print $3}')"
    [[ -n "$ipv4_gateway" ]] || die "Unable to detect the IPv4 default gateway on $interface."

    mapfile -t current_ipv6_addresses < <(ip -o -6 addr show dev "$interface" scope global | awk '$4 !~ /^fe80:/ {print $4}' | sort -u)
    if ((${#current_ipv6_addresses[@]})); then
        current_ipv6="${current_ipv6_addresses[0]}"
    fi

    if (( add_ipv4 == 1 )); then
        while true; do
            read -r -p "How many host-supplied IPv4 addresses should be added? [1]: " ipv4_count
            ipv4_count="${ipv4_count:-1}"
            [[ "$ipv4_count" =~ ^[1-9][0-9]*$ ]] && (( ipv4_count <= 64 )) && break
            echo "Enter a whole number from 1 through 64."
        done

        for ((attempt=1; attempt<=ipv4_count; attempt++)); do
            while true; do
                read -r -p "IPv4 address $attempt/$ipv4_count in CIDR format (example 203.0.113.25/24): " address
                normalized="$(validate_ipv4_cidr "$address" 2>/dev/null || true)"
                if [[ -z "$normalized" ]]; then
                    echo "Enter a valid host-supplied IPv4 address with its CIDR prefix."
                    continue
                fi
                if printf '%s\n' "${current_ipv4_addresses[@]}" "${supplied_ipv4[@]}" | grep -Fxq "$normalized"; then
                    echo "That IPv4 address is already configured or already entered."
                    continue
                fi
                supplied_ipv4+=("$normalized")
                break
            done
        done
    fi

    if (( add_ipv6 == 1 )); then
        [[ -n "$current_ipv6" ]] || die "No global IPv6 address was detected on $interface. Ask the hosting provider to assign an IPv6 /64 first."
        while true; do
            read -r -p "How many new IPv6 addresses should be created? [1]: " ipv6_count
            ipv6_count="${ipv6_count:-1}"
            [[ "$ipv6_count" =~ ^[1-9][0-9]*$ ]] && (( ipv6_count <= 256 )) && break
            echo "Enter a whole number from 1 through 256."
        done

        ipv6_prefix="$(normalize_ipv6_prefix64 "$current_ipv6")" || die "Unable to derive an IPv6 /64 from $current_ipv6."
        generated_ipv6="$(generate_ipv6_addresses "$current_ipv6" "$ipv6_count")" || die "Unable to generate IPv6 addresses."

        while read -r address; do
            [[ -n "$address" ]] || continue
            if ip -6 addr show dev "$interface" | grep -Fq "${address%/*}/"; then
                die "Generated address ${address%/*} is already assigned. Refusing to overwrite an existing IPv6 address."
            fi
        done <<<"$generated_ipv6"
    fi

    dns_list="$(resolvectl dns "$interface" 2>/dev/null | sed -n 's/^[^:]*:[[:space:]]*//p' | tr ' ' '\n' | grep -E '^[0-9a-fA-F:.]+$' | head -n4 || true)"
    if [[ -z "$dns_list" ]]; then
        dns_list="$(grep -E '^nameserver[[:space:]]+' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | grep -vE '^(127\.|::1$)' | head -n4 || true)"
    fi
    [[ -n "$dns_list" ]] || dns_list="1.1.1.1"

    dns_yaml=""
    while read -r address; do
        [[ -n "$address" ]] || continue
        [[ -z "$dns_yaml" ]] || dns_yaml+=", "
        dns_yaml+="'$address'"
    done <<<"$dns_list"

    install -d -m 0755 /etc/netplan "$STATE_DIR"
    backup_file=""
    if [[ -e "$NETWORK_NETPLAN_FILE" ]]; then
        backup_file="$NETWORK_NETPLAN_FILE.backup.$(date +%Y%m%d-%H%M%S)"
        cp -a "$NETWORK_NETPLAN_FILE" "$backup_file"
    fi

    {
        echo "network:"
        echo "  version: 2"
        echo "  renderer: networkd"
        echo "  ethernets:"
        echo "    $interface:"
        echo "      dhcp4: no"
        echo "      dhcp6: no"
        echo "      addresses:"
        for address in "${current_ipv4_addresses[@]}"; do echo "        - '$address'"; done
        for address in "${supplied_ipv4[@]}"; do echo "        - '$address'"; done
        for address in "${current_ipv6_addresses[@]}"; do echo "        - '$address'"; done
        while read -r address; do
            [[ -n "$address" ]] && echo "        - '$address'"
        done <<<"$generated_ipv6"
        echo "      nameservers:"
        echo "        addresses: [$dns_yaml]"
        echo "      routes:"
        echo "        - to: default"
        echo "          via: '$ipv4_gateway'"
    } >"$NETWORK_NETPLAN_FILE"
    chmod 0600 "$NETWORK_NETPLAN_FILE"

    : >"$NETWORK_ADDRESS_FILE"
    for address in "${supplied_ipv4[@]}"; do printf 'IPv4 %s\n' "$address" >>"$NETWORK_ADDRESS_FILE"; done
    while read -r address; do
        [[ -n "$address" ]] && printf 'IPv6 %s\n' "$address" >>"$NETWORK_ADDRESS_FILE"
    done <<<"$generated_ipv6"
    chmod 0600 "$NETWORK_ADDRESS_FILE"

    if ((${#supplied_ipv4[@]})); then
        info "Host-supplied IPv4 addresses to add:"
        printf '  - %s\n' "${supplied_ipv4[@]}"
    fi
    if [[ -n "$generated_ipv6" ]]; then
        info "Generated IPv6 addresses using the current server IPv6 address $current_ipv6:"
        sed 's/^/  - /' <<<"$generated_ipv6"
    fi
    info "Netplan configuration written to $NETWORK_NETPLAN_FILE."

    if ! netplan generate >>"$LOG_FILE" 2>&1; then
        restore_network_configuration "$backup_file"
        die "Netplan validation failed; the previous network configuration was restored."
    fi

    warn "Applying network changes can interrupt this SSH connection."
    if ! prompt_yes_no "Apply the new network configuration now?" "Y"; then
        restore_network_configuration "$backup_file"
        info "Network address changes were not applied."
        return 0
    fi

    if ! netplan apply >>"$LOG_FILE" 2>&1; then
        restore_network_configuration "$backup_file"
        die "Netplan apply failed; the previous network configuration was restored."
    fi

    for address in "${supplied_ipv4[@]}"; do
        verified=0
        for attempt in {1..15}; do
            network_address_is_active 4 "$interface" "$address" && { verified=1; break; }
            sleep 2
        done
        if (( verified == 0 )); then
            warn "IPv4 verification failed for ${address%/*}. Restoring the previous network configuration."
            ip -4 addr show dev "$interface" | tee -a "$LOG_FILE" >&2 || true
            restore_network_configuration "$backup_file"
            die "IPv4 verification failed for ${address%/*}; the previous network configuration was restored."
        fi
    done

    while read -r address; do
        [[ -n "$address" ]] || continue
        verified=0
        for attempt in {1..15}; do
            network_address_is_active 6 "$interface" "$address" && { verified=1; break; }
            sleep 2
        done
        if (( verified == 0 )); then
            warn "IPv6 verification failed for ${address%/*}. Restoring the previous network configuration."
            ip -6 addr show dev "$interface" | tee -a "$LOG_FILE" >&2 || true
            restore_network_configuration "$backup_file"
            die "IPv6 verification failed for ${address%/*}; the previous network configuration was restored."
        fi
    done <<<"$generated_ipv6"

    info "All requested network addresses are active on $interface."
    log "INFO: Network provisioning interface=$interface ipv4_added=${#supplied_ipv4[@]} ipv6_added=$ipv6_count prefix=$ipv6_prefix"

    rm -f "$NETWORK_RESUME_FLAG" "$LEGACY_IPV6_RESUME_FLAG"
    info "Network provisioning is active and persistent. Continuing installation without reboot."
    return 0
}

github_latest_json() { curl -fsSL --retry 3 "https://api.github.com/repos/$1/releases/latest"; }
asset_url() {
    local json="$1" regex="$2"
    jq -er --arg regex "$regex" '.assets[] | select(.name | test($regex; "i")) | .browser_download_url' <<<"$json" | head -n1
}

resolve_release() {
    local release_json bootstrap_json wallet_regex available_assets
    info "Resolving latest Yerbas release..."
    release_json="$(github_latest_json "$YERB_REPO")" || die "Unable to query latest Yerbas release."
    RELEASE_TAG="$(jq -er '.tag_name' <<<"$release_json")" || die "Latest Yerbas release does not contain a valid tag."

    case "$ARCH:$UBUNTU_VERSION" in
        x86_64:22.04) wallet_regex='^yerbas-ubuntu-22\.04-x86-release-[0-9]+(\.[0-9]+)*\.(tar\.gz|tgz)$' ;;
        x86_64:24.04) wallet_regex='^yerbas-ubuntu-24\.04-x86-release-[0-9]+(\.[0-9]+)*\.(tar\.gz|tgz)$' ;;
        x86_64:26.04) wallet_regex='^yerbas-ubuntu-26\.04-x86-release-[0-9]+(\.[0-9]+)*\.(tar\.gz|tgz)$' ;;
        aarch64:22.04) wallet_regex='^yerbas-ubuntu-22\.04-arm64-release-[0-9]+(\.[0-9]+)*\.(tar\.gz|tgz)$' ;;
        aarch64:24.04) wallet_regex='^yerbas-ubuntu-24\.04-arm64-release-[0-9]+(\.[0-9]+)*\.(tar\.gz|tgz)$' ;;
        aarch64:26.04) wallet_regex='^yerbas-ubuntu-26\.04-arm64-release-[0-9]+(\.[0-9]+)*\.(tar\.gz|tgz)$' ;;
        *) die "No release matcher for Ubuntu $UBUNTU_VERSION on $ARCH." ;;
    esac

    WALLET_URL="$(asset_url "$release_json" "$wallet_regex" || true)"
    if [[ -z "$WALLET_URL" ]]; then
        available_assets="$(jq -r '.assets[].name' <<<"$release_json")"
        {
            echo "Available assets in release $RELEASE_TAG:"
            sed 's/^/  - /' <<<"$available_assets"
        } | tee -a "$LOG_FILE" >&2
        die "No compatible Yerbas wallet archive for Ubuntu $UBUNTU_VERSION on $ARCH."
    fi

    info "Latest wallet release: $RELEASE_TAG"
    info "Selected wallet archive: ${WALLET_URL##*/}"

    bootstrap_json="$(github_latest_json "$BOOTSTRAP_REPO")" || die "Unable to query latest bootstrap release."
    BOOTSTRAP_URL="$(asset_url "$bootstrap_json" '^bootstrap\.zip$')" || true
    BOOTSTRAP_SIZE="$(
    jq -er '
        .assets[]
        | select(.name | ascii_downcase == "bootstrap.zip")
        | .size
    ' <<<"$bootstrap_json" | head -n1
)" || BOOTSTRAP_SIZE=0
    POWCACHE_URL="$(asset_url "$bootstrap_json" 'powcache\.dat$')" || true
}

service_users() {
    { systemctl list-unit-files 'yerbasd@*.service' --no-legend 2>/dev/null || true; } |
        awk '{print $1}' | sed -n 's/^yerbasd@\(.*\)\.service$/\1/p' | sort -u
    return 0
}

stop_all_nodes() {
    local user
    while read -r user; do
        [[ -n "$user" ]] || continue
        systemctl stop "yerbasd@$user" || true
    done < <(service_users)
}

install_shared_release() {
    local release_dir="$RELEASES_DIR/$RELEASE_TAG" temp archive binary_dir previous=""
    if [[ -L "$CURRENT_LINK" ]]; then previous="$(readlink -f "$CURRENT_LINK" || true)"; fi
    if [[ -x "$release_dir/$DAEMON" ]]; then
        info "Release $RELEASE_TAG is already installed."
    else
        temp="$(mktemp -d)"; archive="$temp/yerbas.tar.gz"
        info "Downloading Yerbas $RELEASE_TAG..."
        curl -fL --retry 3 "$WALLET_URL" -o "$archive"
        tar -tzf "$archive" >/dev/null || die "Wallet archive validation failed."
        tar -xzf "$archive" -C "$temp"
        binary_dir="$(find "$temp" -type f -name "$DAEMON" -printf '%h\n' | head -n1)"
        [[ -n "$binary_dir" ]] || die "$DAEMON was not found in the archive."
        install -d -m 0755 "$release_dir"
        cp -a "$binary_dir"/. "$release_dir"/
        chmod 0755 "$release_dir/$DAEMON" "$release_dir/$CLI"
        [[ -f "$release_dir/$TX" ]] && chmod 0755 "$release_dir/$TX"
        rm -rf "$temp"
    fi
    ln -sfn "$release_dir" "$CURRENT_LINK"
    ln -sfn "$CURRENT_LINK/$DAEMON" /usr/local/bin/$DAEMON
    ln -sfn "$CURRENT_LINK/$CLI" /usr/local/bin/$CLI
    [[ -f "$CURRENT_LINK/$TX" ]] && ln -sfn "$CURRENT_LINK/$TX" /usr/local/bin/$TX
    echo "$previous" > "$STATE_DIR/previous-release"
    echo "$RELEASE_TAG" > "$STATE_DIR/current-version"
}

install_service_template() {
    if [[ -f "$SCRIPT_DIR/systemd/yerbasd@.service" ]]; then
        install -m 0644 "$SCRIPT_DIR/systemd/yerbasd@.service" "$SERVICE_TEMPLATE"
    else
        cat >"$SERVICE_TEMPLATE" <<'SERVICE'
[Unit]
Description=Yerbas Smartnode for %i
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
User=%i
Group=%i
WorkingDirectory=/opt/yerbas/current
ExecStart=/opt/yerbas/current/yerbasd -daemon -datadir=/home/%i/.yerbascore
ExecStop=/opt/yerbas/current/yerbas-cli -datadir=/home/%i/.yerbascore stop
Restart=on-failure
RestartSec=10
TimeoutStartSec=180
TimeoutStopSec=180
LimitNOFILE=65536
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
SERVICE
    fi
    systemctl daemon-reload
}

ensure_user() {
    local user="$1" password confirmation
    if id "$user" &>/dev/null; then return; fi
    while true; do
        read -r -s -p "Password for new user $user: " password; echo
        read -r -s -p "Confirm password: " confirmation; echo
        [[ -n "$password" && "$password" == "$confirmation" ]] && break
        echo "Passwords are empty or do not match."
    done
    useradd -m -s /bin/bash "$user"
    printf '%s:%s\n' "$user" "$password" | chpasswd
    CREATED_USERS+=("$user")
    unset password confirmation
}

next_available_port() {
    local port="$1"
    while port_in_use "$port" || grep -RqsE "^(port|rpcport)=$port$" /home/*/.yerbascore/yerbas.conf 2>/dev/null; do ((port++)); done
    echo "$port"
}

install_bootstrap_for_user() {
    (( USE_BOOTSTRAP == 1 )) || return
    [[ -n "$BOOTSTRAP_URL" ]] || die "Latest bootstrap release has no bootstrap.zip asset."

    local user="$1" data="$2"
    local part="$data/.bootstrap.zip.part"
    local extract="$data/.bootstrap-install.$$"
    local available_bytes required_bytes actual_bytes extracted_bytes
    local safety_bytes=$((1024 * 1024 * 1024))

    available_bytes="$(df -PB1 "$data" | awk 'NR == 2 {print $4}')"
    [[ "$available_bytes" =~ ^[0-9]+$ ]] ||
        die "Unable to determine available disk space for bootstrap download for $user."

    if (( BOOTSTRAP_SIZE > 0 )); then
        required_bytes=$((BOOTSTRAP_SIZE + safety_bytes))
        info "Bootstrap archive size for $user: $(numfmt --to=iec-i --suffix=B "$BOOTSTRAP_SIZE")."
        info "Available storage for $user: $(numfmt --to=iec-i --suffix=B "$available_bytes")."

        if (( available_bytes < required_bytes )); then
            die "Insufficient disk space for bootstrap download for $user. Required at least $(numfmt --to=iec-i --suffix=B "$required_bytes"); available $(numfmt --to=iec-i --suffix=B "$available_bytes")."
        fi
    fi

    info "Downloading bootstrap for $user..."
    rm -f "$part"
    rm -rf "$extract"
    mkdir -p "$extract"

    if ! curl -fL --retry 3 --retry-delay 2 "$BOOTSTRAP_URL" -o "$part"; then
        available_bytes="$(df -PB1 "$data" | awk 'NR == 2 {print $4}')"
        rm -f "$part"
        rm -rf "$extract"

        if (( BOOTSTRAP_SIZE > 0 && available_bytes < BOOTSTRAP_SIZE )); then
            die "Insufficient disk space for bootstrap download for $user."
        fi

        die "Bootstrap download failed for $user."
    fi

    actual_bytes="$(stat -c '%s' "$part")"
    if (( BOOTSTRAP_SIZE > 0 && actual_bytes != BOOTSTRAP_SIZE )); then
        rm -f "$part"
        rm -rf "$extract"
        die "Bootstrap download incomplete for $user. Expected $(numfmt --to=iec-i --suffix=B "$BOOTSTRAP_SIZE"), but received $(numfmt --to=iec-i --suffix=B "$actual_bytes")."
    fi

    if ! unzip -tq "$part" >/dev/null; then
        rm -f "$part"
        rm -rf "$extract"
        die "Downloaded bootstrap.zip failed ZIP validation for $user."
    fi

    extracted_bytes="$(LC_ALL=C unzip -Z -t "$part" 2>/dev/null | awk '/bytes uncompressed/ {gsub(/,/, "", $3); print $3; exit}')"
    available_bytes="$(df -PB1 "$data" | awk 'NR == 2 {print $4}')"

    if [[ "$extracted_bytes" =~ ^[0-9]+$ ]]; then
        required_bytes=$((extracted_bytes + safety_bytes))
        if (( available_bytes < required_bytes )); then
            rm -f "$part"
            rm -rf "$extract"
            die "Insufficient disk space to extract bootstrap for $user. Required approximately $(numfmt --to=iec-i --suffix=B "$required_bytes"); available $(numfmt --to=iec-i --suffix=B "$available_bytes")."
        fi
    fi

    info "Extracting bootstrap directly for $user..."
    if ! unzip -q "$part" -d "$extract"; then
        rm -f "$part"
        rm -rf "$extract"
        die "Bootstrap extraction failed for $user."
    fi

    if [[ -d "$extract/bootstrap" ]]; then
        shopt -s dotglob nullglob
        mv "$extract/bootstrap"/* "$extract"/ 2>/dev/null || true
        shopt -u dotglob nullglob
        rmdir "$extract/bootstrap" 2>/dev/null || true
    fi

    rm -rf "$data/assets" "$data/blocks" "$data/chainstate" "$data/evodb" "$data/llmq"
    rsync -a --remove-source-files "$extract"/ "$data"/
    find "$extract" -depth -type d -empty -delete 2>/dev/null || true
    chown -R "$user:$user" "$data"

    rm -f "$part"
    rm -rf "$extract"
    info "Bootstrap installation completed for $user; temporary files deleted."
}

is_public_ipv4() {
    local ip="$1"
    [[ "$ip" =~ ^10\. ]] && return 1
    [[ "$ip" =~ ^127\. ]] && return 1
    [[ "$ip" =~ ^169\.254\. ]] && return 1
    [[ "$ip" =~ ^192\.168\. ]] && return 1
    [[ "$ip" =~ ^172\.(1[6-9]|2[0-9]|3[01])\. ]] && return 1
    [[ "$ip" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\. ]] && return 1
    return 0
}

is_public_ipv6() {
    local ip="${1,,}"
    [[ "$ip" == ::1 ]] && return 1
    [[ "$ip" == fe8* || "$ip" == fe9* || "$ip" == fea* || "$ip" == feb* ]] && return 1
    [[ "$ip" == fc* || "$ip" == fd* ]] && return 1
    return 0
}

select_server_ip() {
    local user="$1" choice manual default=0 i ip
    local -a public_v4=() public_v6=() choices=() labels=()
    local candidate

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        is_public_ipv4 "$candidate" && public_v4+=("$candidate")
    done < <({
        ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p'
        ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1
        curl -4fsS --max-time 4 https://api.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++')

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        is_public_ipv6 "$candidate" && public_v6+=("$candidate")
    done < <({
        ip -6 route get 2606:4700:4700::1111 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p'
        ip -o -6 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | sed 's/%.*//'
        curl -6fsS --max-time 4 https://api64.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++' | python3 -c 'import ipaddress,sys; print("\n".join(sorted((x.strip() for x in sys.stdin if x.strip()), key=ipaddress.ip_address)))')

    for ip in "${public_v4[@]}"; do choices+=("$ip"); labels+=("Public IPv4"); done
    for ip in "${public_v6[@]}"; do choices+=("$ip"); labels+=("Public IPv6"); done

    echo >&2
    echo "Select the public external IP address for $user" >&2
    echo >&2

    if ((${#choices[@]} == 0)); then
        die "No public IPv4 or IPv6 addresses were detected on this server."
    fi

    for i in "${!choices[@]}"; do
        printf ' %2d) %-39s (%s)\n' "$i" "${choices[$i]}" "${labels[$i]}" >&2
    done
    printf ' %2d) Enter a different public IP manually\n' "${#choices[@]}" >&2

    while true; do
        read -r -p "Selection [$default]: " choice
        choice="${choice:-$default}"
        [[ "$choice" =~ ^[0-9]+$ ]] || { echo "Enter a menu number." >&2; continue; }

        if ((choice >= 0 && choice < ${#choices[@]})); then
            printf '%s\n' "${choices[$choice]}"
            return
        elif ((choice == ${#choices[@]})); then
            read -r -p "Enter public IPv4 or IPv6 address: " manual
            [[ -n "$manual" ]] || { echo "Address cannot be blank." >&2; continue; }
            manual="${manual#[}"; manual="${manual%]}"

            if is_public_ipv4 "$manual" || is_public_ipv6 "$manual"; then
                printf '%s\n' "$manual"
                return
            fi

            echo "Enter a public IPv4 or IPv6 address." >&2
            continue
        fi

        echo "Invalid selection." >&2
    done
}

format_external_endpoint() {
    local ip="$1" port="$2"
    if [[ "$ip" == *:* ]]; then printf '[%s]:%s\n' "$ip" "$port"; else printf '%s:%s\n' "$ip" "$port"; fi
}

format_bind_address() {
    local ip="$1"
    if [[ "$ip" == *:* ]]; then printf '[%s]\n' "$ip"; else printf '%s\n' "$ip"; fi
}

configure_user_node() {
    local user="$1" home data p2p rpc ip endpoint bls rpcuser rpcpass
    home="$(getent passwd "$user" | cut -d: -f6)"; data="$home/$CONF_DIR_NAME"
    install -d -m 0700 -o "$user" -g "$user" "$data"

    if [[ -f "$data/$CONF_FILE" ]]; then
        info "Existing Smartnode configuration found for $user; preserving configuration and blockchain data."
        grep -qxF "$user" "$USERS_FILE" || echo "$user" >> "$USERS_FILE"
        local existing_p2p
        existing_p2p="$(sed -n 's/^port=//p' "$data/$CONF_FILE" | head -n1)"
        [[ -n "$existing_p2p" ]] && ufw allow "$existing_p2p/tcp"
        systemctl enable "yerbasd@$user"
        CONFIGURED_USERS+=("$user")
        return
    fi

    p2p="$DEFAULT_P2P_PORT"
    rpc="$(next_available_port "$DEFAULT_RPC_PORT")"
    while true; do read -r -p "RPC port for $user [$rpc]: " v; rpc="${v:-$rpc}"; valid_port "$rpc" && [[ "$rpc" != "$p2p" ]] && ! port_in_use "$rpc" && break; echo "Port is invalid, duplicated, or in use."; done
    ip="$(select_server_ip "$user")"

    if grep -RqsE "^externalip=(\[$ip\]|$ip):$DEFAULT_P2P_PORT$" /home/*/.yerbascore/yerbas.conf 2>/dev/null; then
        die "Public IP $ip is already assigned to another Yerbas Smartnode. This installer requires one Smartnode per public IP."
    fi

    info "Using required Yerbas P2P port $DEFAULT_P2P_PORT for $user."
    while true; do
        bls=""
        preview=""
        printf "BLS private key for %s: " "$user"

        while IFS= read -r -s -n1 ch; do
            if [[ -z "$ch" ]]; then
                printf '\n'
                break
            fi

            if [[ "$ch" == $'\177' || "$ch" == $'\b' ]]; then
                if (( ${#bls} > 0 )); then
                    bls="${bls%?}"
                fi
            else
                bls+="$ch"
            fi

            if (( ${#bls} >= 8 )); then
                preview="${bls:0:4}...${bls: -4}"
            elif (( ${#bls} >= 4 )); then
                preview="${bls:0:4}..."
            else
                preview="$bls"
            fi

            printf '\r\033[2KBLS private key for %s: %s' "$user" "$preview"
        done

        [[ -n "$bls" ]] || {
            echo "BLS private key is required."
            continue
        }

        if (( ${#bls} < 8 )); then
            echo "BLS private key is too short."
            continue
        fi

        break
    done
    rpcuser="yerbas_${user}"
    rpcpass="$(openssl rand -hex 32)"

    if [[ -f "$data/$CONF_FILE" ]]; then cp -a "$data/$CONF_FILE" "$data/$CONF_FILE.backup.$(date +%Y%m%d-%H%M%S)"; fi
    umask 077
    cat >"$data/$CONF_FILE" <<EOF_CONF
rpcallowip=127.0.0.1
listen=1
server=1
daemon=1
rpcuser=$rpcuser
rpcpassword=$rpcpass
rpcport=$rpc
port=$p2p
EOF_CONF
    if [[ -n "$ip" ]]; then
        endpoint="$(format_external_endpoint "$ip" "$p2p")"
        echo "bind=$(format_bind_address "$ip")" >>"$data/$CONF_FILE"
        echo "externalip=$endpoint" >>"$data/$CONF_FILE"
    fi
    if [[ -n "$bls" ]]; then echo "smartnodeblsprivkey=$bls" >>"$data/$CONF_FILE"; fi
    chown "$user:$user" "$data/$CONF_FILE"; chmod 0600 "$data/$CONF_FILE"

    if (( USE_POWCACHE == 1 )); then
        if [[ ! -s "$CACHE_DIR/powcache.dat" ]]; then
            [[ -n "$POWCACHE_URL" ]] || die "Latest bootstrap release has no powcache.dat."
            curl -fL --retry 3 "$POWCACHE_URL" -o "$CACHE_DIR/powcache.dat"
        fi
        install -m 0644 -o "$user" -g "$user" "$CACHE_DIR/powcache.dat" "$data/powcache.dat"
    fi
    install_bootstrap_for_user "$user" "$data"

    grep -qxF "$user" "$USERS_FILE" || echo "$user" >> "$USERS_FILE"
    ufw allow "$p2p/tcp"
    systemctl enable "yerbasd@$user"
    CONFIGURED_USERS+=("$user")
    NEW_NODE_USERS+=("$user")
    unset bls rpcpass
}

detect_existing_install() {
    local user home

    if [[ -L "$CURRENT_LINK" || -x "$CURRENT_LINK/$DAEMON" || -s "$USERS_FILE" ]] || compgen -G "/home/*/$CONF_DIR_NAME/$CONF_FILE" >/dev/null; then
        EXISTING_INSTALL=1
    fi

    if (( EXISTING_INSTALL == 0 )); then
        return 0
    fi

    while read -r user; do
        [[ -n "$user" ]] || continue
        id "$user" &>/dev/null || continue
        home="$(getent passwd "$user" | cut -d: -f6)"
        [[ -f "$home/$CONF_DIR_NAME/$CONF_FILE" ]] || continue
        [[ " ${EXISTING_USERS[*]} " == *" $user "* ]] || EXISTING_USERS+=("$user")
    done < <({ cat "$USERS_FILE" 2>/dev/null || true; find /home -mindepth 3 -maxdepth 3 -path "*/$CONF_DIR_NAME/$CONF_FILE" -printf '%h\n' 2>/dev/null | sed -E 's#^/home/([^/]+)/.*#\1#'; } | sort -u)

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
    local -a users_to_configure=()
    (( EXISTING_INSTALL == 1 )) && prompt_text="How many additional Smartnode users should be added? [1]: "

    while true; do
        read -r -p "$prompt_text" count
        count="${count:-1}"; [[ "$count" =~ ^[1-9][0-9]*$ ]] && break; echo "Enter a whole number greater than zero."
    done

    for ((i=1; i<=count; i++)); do
        while true; do
            read -r -p "Smartnode username $i/$count: " user
            valid_username "$user" || { echo "Use a valid lowercase Linux username."; continue; }
            break
        done
        ensure_user "$user"
        users_to_configure+=("$user")
    done

    prompt_yes_no "Download and install the latest bootstrap for each new node?" "N" && USE_BOOTSTRAP=1

    if (( EXISTING_INSTALL == 1 )); then
        if [[ -s "$CACHE_DIR/powcache.dat" ]]; then
            USE_POWCACHE=1
            info "Existing PoW cache detected. Reusing it for additional Smartnode users."
        else
            info "No shared PoW cache is available. New users will synchronize without a preloaded PoW cache."
        fi
    else
        prompt_yes_no "Download and install the latest PoW cache?" "Y" && USE_POWCACHE=1
    fi

    for user in "${users_to_configure[@]}"; do
        configure_user_node "$user"
    done
}

start_nodes() {
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

        info "Loading blocks and waiting for RPC for $user. Wait up to 2 minutes. Roll one up..."
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

        info "$user RPC health check passed. Waiting for Smartnode readiness..."
        attempts=0

        while (( attempts < max_attempts )); do
            status_output="$(sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" smartnode status 2>&1 || true)"
            log "SMARTNODE STATUS $user attempt $((attempts + 1))/$max_attempts: $status_output"

            if grep -qiE '"state"[[:space:]]*:[[:space:]]*"READY"|"status"[[:space:]]*:[[:space:]]*"Ready"' <<<"$status_output"; then
                echo
      echo -e "${GREEN}============================================================${RESET}"
      echo -e "${GREEN}  ★ $user Smartnode is READY and ready to rock! ★${RESET}"
      echo -e "${GREEN}============================================================${RESET}"
      echo
      log "INFO: $user Smartnode is READY and ready to rock!"
                break
            fi

            attempts=$((attempts + 1))

            if grep -q 'WAITING_FOR_PROTX' <<<"$status_output"; then
                if (( attempts >= max_attempts )); then
                    warn "$user Smartnode is still waiting for ProTx after 2 minutes."
                    break
                fi
                sleep "$retry_delay"
                continue
            fi

            if grep -qiE 'make sure server is running|could not connect|connection refused|couldn.t connect' <<<"$status_output"; then
                if (( attempts >= max_attempts )); then
                    warn "$user could not query Smartnode status after 2 minutes. Make sure the server is running and the correct RPC port is configured."
                    break
                fi
                sleep "$retry_delay"
                continue
            fi

            if (( attempts >= max_attempts )); then
                warn "$user did not report READY within 2 minutes. Review $home/$CONF_DIR_NAME/$CONF_FILE and run: yerbas-node-manager cli $user smartnode status"
                break
            fi

            sleep "$retry_delay"
        done
    done
}

rollback_release() {
    local previous
    previous="$(cat "$STATE_DIR/previous-release" 2>/dev/null || true)"
    [[ -n "$previous" && -x "$previous/$DAEMON" ]] || return 1
    warn "Rolling back shared binaries to $previous"
    ln -sfn "$previous" "$CURRENT_LINK"
    return 0
}

install_manager() {
    if [[ -f "$SCRIPT_DIR/bin/yerbas-node-manager" ]]; then
        install -m 0755 "$SCRIPT_DIR/bin/yerbas-node-manager" "$MANAGER"
        return
    fi
    cat >"$MANAGER" <<'MANAGER_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
USERS_FILE=/var/lib/yerbas-installer/users
usage(){ echo "Usage: yerbas-node-manager {status|start|stop|restart|logs|cli} [user]"; }
users(){ [[ -f "$USERS_FILE" ]] && sort -u "$USERS_FILE"; }
cmd="${1:-}"; user="${2:-}"
case "$cmd" in
 status) while read -r u; do [[ -n "$u" ]] || continue; printf '%-20s ' "$u"; systemctl is-active "yerbasd@$u" || true; done < <(users) ;;
 start|stop|restart) [[ -n "$user" ]] || { usage; exit 1; }; systemctl "$cmd" "yerbasd@$user" ;;
 logs) [[ -n "$user" ]] || { usage; exit 1; }; journalctl -u "yerbasd@$user" -f ;;
 cli) [[ -n "$user" ]] || { usage; exit 1; }; shift 2; home="$(getent passwd "$user"|cut -d: -f6)"; sudo -u "$user" /usr/local/bin/yerbas-cli -datadir="$home/.yerbascore" "$@" ;;
 *) usage; exit 1 ;;
esac
MANAGER_SCRIPT
    chmod 0755 "$MANAGER"
}

summary() {
    echo
    echo -e "${GREEN}Yerbas multi-user installation finished.${RESET}"
    echo "Version: $RELEASE_TAG"
    echo "Shared binaries: $CURRENT_LINK"
    echo "Configured users: ${CONFIGURED_USERS[*]:-(none)}"
    echo "Status: yerbas-node-manager status"
    echo "Logs: yerbas-node-manager logs USER"
    echo "CLI: yerbas-node-manager cli USER getblockchaininfo"
}

main() {
    require_root
    initialize_paths
    if [[ ! -f "$NETWORK_RESUME_FLAG" && ! -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then
        : > "$LOG_FILE"
    fi
    banner
    detect_existing_install
    detect_platform

    if (( EXISTING_INSTALL == 0 )); then
        install_dependencies
        network_provisioning
        create_swap
    else
        info "Additional-user mode: skipping required packages, firewall, Fail2Ban, network provisioning, and swap configuration."
    fi

    resolve_release

    stop_all_nodes
    install_shared_release
    install_service_template
    install_manager
    (( EXISTING_INSTALL == 0 || ADDITIONAL_USERS == 1 )) && configure_multiple_users

    if ! start_nodes "${CONFIGURED_USERS[@]}" || ! verify_services "${CONFIGURED_USERS[@]}"; then
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
}

main "$@"
