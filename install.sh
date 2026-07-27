#!/usr/bin/env bash
set -Eeuo pipefail

# Yerbas Multi-User Smartnode Installer v2
VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
ARCH=""; UBUNTU_VERSION=""; RELEASE_TAG=""; WALLET_URL=""; BOOTSTRAP_URL=""; POWCACHE_URL=""
USE_BOOTSTRAP=0; USE_POWCACHE=0
CONFIGURED_USERS=()

trap 'echo -e "${RED}Installer failed on line $LINENO. See $LOG_FILE${RESET}" >&2' ERR

log() { printf '[%s] %s\n' "$(date -Is)" "$*" >> "$LOG_FILE"; }
info() { echo -e "${CYAN}$*${RESET}"; log "INFO: $*"; }
warn() { echo -e "${YELLOW}$*${RESET}"; log "WARN: $*"; }
die() { echo -e "${RED}ERROR: $*${RESET}" >&2; log "ERROR: $*"; exit 1; }

require_root() { [[ $EUID -eq 0 ]] || die "Run with sudo: sudo ./install.sh"; }

banner() {
    clear || true
    echo -e "${GREEN}Yerbas Multi-User Smartnode Installer v${VERSION}${RESET}"
    echo "Shared binaries • isolated users • systemd instances • safe updates"
}

prompt_yes_no() {
    local prompt="$1" default="${2:-N}" answer suffix="[y/N]"
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
    apt-get install -y ca-certificates curl jq unzip wget openssl pwgen ufw fail2ban util-linux rsync sudo
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
    local size_gb
    if swapon --show=NAME --noheadings | grep -qx '/swapfile'; then info "Existing /swapfile is active; leaving it unchanged."; return; fi
    if [[ -e /swapfile ]]; then warn "/swapfile exists but is not active; leaving it unchanged."; return; fi
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

github_latest_json() { curl -fsSL --retry 3 "https://api.github.com/repos/$1/releases/latest"; }
asset_url() {
    local json="$1" regex="$2"
    jq -er --arg regex "$regex" '.assets[] | select(.name | test($regex; "i")) | .browser_download_url' <<<"$json" | head -n1
}

resolve_release() {
    local release_json bootstrap_json wallet_regex
    info "Resolving latest Yerbas release..."
    release_json="$(github_latest_json "$YERB_REPO")" || die "Unable to query latest Yerbas release."
    RELEASE_TAG="$(jq -er '.tag_name' <<<"$release_json")"
    case "$ARCH:$UBUNTU_VERSION" in
        x86_64:22.04) wallet_regex='ubuntu-22\.04-x86-release\.(tar\.gz|tgz)$' ;;
        x86_64:24.04) wallet_regex='ubuntu-24\.04-x86-release\.(tar\.gz|tgz)$' ;;
        x86_64:26.04) wallet_regex='ubuntu-26\.04-x86-release\.(tar\.gz|tgz)$' ;;
        aarch64:*) wallet_regex='ubuntu-.*arm64-release\.(tar\.gz|tgz)$' ;;
    esac
    WALLET_URL="$(asset_url "$release_json" "$wallet_regex")" || die "No compatible wallet archive found in release $RELEASE_TAG."
    bootstrap_json="$(github_latest_json "$BOOTSTRAP_REPO")" || die "Unable to query latest bootstrap release."
    BOOTSTRAP_URL="$(asset_url "$bootstrap_json" '^bootstrap(-index)?\.zip$')" || true
    POWCACHE_URL="$(asset_url "$bootstrap_json" 'powcache\.dat$')" || true
    info "Latest wallet release: $RELEASE_TAG"
}

service_users() {
    systemctl list-unit-files 'yerbasd@*.service' --no-legend 2>/dev/null |
        awk '{print $1}' | sed -n 's/^yerbasd@\(.*\)\.service$/\1/p' | sort -u
}

stop_all_nodes() {
    local user
    while read -r user; do [[ -n "$user" ]] && systemctl stop "yerbasd@$user" || true; done < <(service_users)
}

install_shared_release() {
    local release_dir="$RELEASES_DIR/$RELEASE_TAG" temp archive binary_dir previous=""
    [[ -L "$CURRENT_LINK" ]] && previous="$(readlink -f "$CURRENT_LINK" || true)"
    if [[ ! -x "$release_dir/$DAEMON" ]]; then
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
    else
        info "Release $RELEASE_TAG is already installed."
    fi
    ln -sfn "$release_dir" "$CURRENT_LINK"
    ln -sfn "$CURRENT_LINK/$DAEMON" "/usr/local/bin/$DAEMON"
    ln -sfn "$CURRENT_LINK/$CLI" "/usr/local/bin/$CLI"
    [[ -f "$CURRENT_LINK/$TX" ]] && ln -sfn "$CURRENT_LINK/$TX" "/usr/local/bin/$TX"
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
    id "$user" &>/dev/null && return
    while true; do
        read -r -s -p "Password for new user $user: " password; echo
        read -r -s -p "Confirm password: " confirmation; echo
        [[ -n "$password" && "$password" == "$confirmation" ]] && break
        echo "Passwords are empty or do not match."
    done
    useradd -m -s /bin/bash "$user"
    printf '%s:%s\n' "$user" "$password" | chpasswd
    unset password confirmation
}

next_available_port() {
    local port="$1"
    while port_in_use "$port" || grep -RqsE "^(port|rpcport)=$port$" /home/*/.yerbascore/yerbas.conf 2>/dev/null; do ((port++)); done
    echo "$port"
}

prepare_bootstrap_cache() {
    (( USE_BOOTSTRAP == 1 )) || return
    [[ -n "$BOOTSTRAP_URL" ]] || die "Latest bootstrap release has no bootstrap ZIP."
    local zip="$CACHE_DIR/${BOOTSTRAP_URL##*/}" extract="$CACHE_DIR/bootstrap-current"
    [[ -f "$zip" ]] || curl -fL --retry 3 "$BOOTSTRAP_URL" -o "$zip"
    unzip -tq "$zip" >/dev/null || die "Bootstrap ZIP validation failed."
    rm -rf "$extract"; mkdir -p "$extract"
    unzip -q "$zip" -d "$extract"
    if [[ -d "$extract/bootstrap" ]]; then mv "$extract/bootstrap"/* "$extract"/ 2>/dev/null || true; rmdir "$extract/bootstrap" 2>/dev/null || true; fi
}

configure_user_node() {
    local user="$1" home data p2p rpc ip bls rpcuser rpcpass v existing_p2p
    home="$(getent passwd "$user" | cut -d: -f6)"; data="$home/$CONF_DIR_NAME"
    install -d -m 0700 -o "$user" -g "$user" "$data"
    if [[ -f "$data/$CONF_FILE" ]]; then
        info "Existing Smartnode configuration found for $user; preserving configuration and blockchain data."
        grep -qxF "$user" "$USERS_FILE" || echo "$user" >> "$USERS_FILE"
        existing_p2p="$(sed -n 's/^port=//p' "$data/$CONF_FILE" | head -n1)"
        [[ -n "$existing_p2p" ]] && ufw allow "$existing_p2p/tcp"
        systemctl enable "yerbasd@$user"
        CONFIGURED_USERS+=("$user")
        return
    fi
    p2p="$(next_available_port "$DEFAULT_P2P_PORT")"
    rpc="$(next_available_port "$DEFAULT_RPC_PORT")"
    while true; do read -r -p "P2P port for $user [$p2p]: " v; p2p="${v:-$p2p}"; valid_port "$p2p" && ! port_in_use "$p2p" && break; echo "Port is invalid or in use."; done
    while true; do read -r -p "RPC port for $user [$rpc]: " v; rpc="${v:-$rpc}"; valid_port "$rpc" && [[ "$rpc" != "$p2p" ]] && ! port_in_use "$rpc" && break; echo "Port is invalid, duplicated, or in use."; done
    read -r -p "Public IP for $user: " ip
    read -r -s -p "BLS private key for $user (may be blank): " bls; echo
    rpcuser="yerbas_${user}"; rpcpass="$(openssl rand -hex 32)"
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
    [[ -n "$ip" ]] && echo "externalip=$ip:$p2p" >>"$data/$CONF_FILE"
    [[ -n "$bls" ]] && echo "smartnodeblsprivkey=$bls" >>"$data/$CONF_FILE"
    chown "$user:$user" "$data/$CONF_FILE"; chmod 0600 "$data/$CONF_FILE"
    if (( USE_POWCACHE == 1 )); then
        [[ -n "$POWCACHE_URL" ]] || die "Latest bootstrap release has no powcache.dat."
        [[ -f "$CACHE_DIR/powcache.dat" ]] || curl -fL --retry 3 "$POWCACHE_URL" -o "$CACHE_DIR/powcache.dat"
        install -m 0644 -o "$user" -g "$user" "$CACHE_DIR/powcache.dat" "$data/powcache.dat"
    fi
    if (( USE_BOOTSTRAP == 1 )); then
        info "Installing cached bootstrap for $user..."
        rm -rf "$data/assets" "$data/blocks" "$data/chainstate" "$data/evodb" "$data/llmq"
        cp -a --reflink=auto "$CACHE_DIR/bootstrap-current"/. "$data"/
        chown -R "$user:$user" "$data"
    fi
    grep -qxF "$user" "$USERS_FILE" || echo "$user" >> "$USERS_FILE"
    ufw allow "$p2p/tcp"
    systemctl enable "yerbasd@$user"
    CONFIGURED_USERS+=("$user")
    unset bls rpcpass
}

configure_multiple_users() {
    local count i user
    while true; do
        read -r -p "How many Smartnode users should be installed or configured? [1]: " count
        count="${count:-1}"
        [[ "$count" =~ ^[1-9][0-9]*$ ]] && break
        echo "Enter a whole number greater than zero."
    done
    for ((i=1; i<=count; i++)); do
        while true; do
            read -r -p "Smartnode username $i/$count: " user
            valid_username "$user" && break
            echo "Use a valid lowercase Linux username."
        done
        ensure_user "$user"
        configure_user_node "$user"
    done
}

start_and_verify_nodes() {
    local user home attempts
    for user in "${CONFIGURED_USERS[@]}"; do
        info "Starting Smartnode for $user..."
        systemctl restart "yerbasd@$user"
        home="$(getent passwd "$user" | cut -d: -f6)"; attempts=0
        until sudo -u "$user" "$CLI" -datadir="$home/$CONF_DIR_NAME" getblockchaininfo >/dev/null 2>&1; do
            ((attempts++))
            if (( attempts >= 12 )); then warn "$user service started but RPC is not ready. Check: journalctl -u yerbasd@$user"; break; fi
            sleep 5
        done
        (( attempts < 12 )) && info "$user RPC health check passed."
    done
}

rollback_release() {
    local previous
    previous="$(cat "$STATE_DIR/previous-release" 2>/dev/null || true)"
    [[ -n "$previous" && -x "$previous/$DAEMON" ]] || return 1
    warn "Rolling back shared binaries to $previous"
    ln -sfn "$previous" "$CURRENT_LINK"
}

install_manager() {
    if [[ -f "$SCRIPT_DIR/bin/yerbas-node-manager" ]]; then
        install -m 0755 "$SCRIPT_DIR/bin/yerbas-node-manager" "$MANAGER"
    else
        die "bin/yerbas-node-manager is missing. Clone the complete repository before running install.sh."
    fi
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
    : > "$LOG_FILE"
    banner
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
    prepare_bootstrap_cache
    configure_multiple_users
    if ! start_and_verify_nodes; then
        rollback_release && start_and_verify_nodes || true
        die "One or more nodes failed after update; rollback attempted."
    fi
    summary
}

main "$@"
