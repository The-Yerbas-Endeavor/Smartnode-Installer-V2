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
ARCH=""; UBUNTU_VERSION=""; RELEASE_TAG=""; WALLET_URL=""; BOOTSTRAP_URL=""; POWCACHE_URL=""
USE_BOOTSTRAP=0; USE_POWCACHE=0
CREATED_USERS=()
CONFIGURED_USERS=()

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
    BOOTSTRAP_URL="$(asset_url "$bootstrap_json" '^bootstrap(-index)?\.zip$')" || true
    POWCACHE_URL="$(asset_url "$bootstrap_json" 'powcache\.dat$')" || true
}

service_users() {
    systemctl list-unit-files 'yerbasd@*.service' --no-legend 2>/dev/null |
        awk '{print $1}' | sed -n 's/^yerbasd@\(.*\)\.service$/\1/p' | sort -u
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

prepare_bootstrap_cache() {
    (( USE_BOOTSTRAP == 1 )) || return
    [[ -n "$BOOTSTRAP_URL" ]] || die "Latest bootstrap release has no bootstrap ZIP."
    local zip="$CACHE_DIR/${BOOTSTRAP_URL##*/}" extract="$CACHE_DIR/bootstrap-current"
    if [[ ! -f "$zip" ]]; then
        info "Downloading bootstrap once for all users..."
        curl -fL --retry 3 "$BOOTSTRAP_URL" -o "$zip"
    fi
    unzip -tq "$zip" >/dev/null || die "Bootstrap ZIP validation failed."
    rm -rf "$extract"; mkdir -p "$extract"
    unzip -q "$zip" -d "$extract"
    if [[ -d "$extract/bootstrap" ]]; then mv "$extract/bootstrap"/* "$extract"/ 2>/dev/null || true; rmdir "$extract/bootstrap" 2>/dev/null || true; fi
}

configure_user_node() {
    local user="$1" home data p2p rpc ip bls rpcuser rpcpass
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

    p2p="$(next_available_port "$DEFAULT_P2P_PORT")"
    rpc="$(next_available_port "$DEFAULT_RPC_PORT")"
    while true; do read -r -p "P2P port for $user [$p2p]: " v; p2p="${v:-$p2p}"; valid_port "$p2p" && ! port_in_use "$p2p" && break; echo "Port is invalid or in use."; done
    while true; do read -r -p "RPC port for $user [$rpc]: " v; rpc="${v:-$rpc}"; valid_port "$rpc" && [[ "$rpc" != "$p2p" ]] && ! port_in_use "$rpc" && break; echo "Port is invalid, duplicated, or in use."; done
    read -r -p "Public IP for $user: " ip
    read -r -s -p "BLS private key for $user (may be blank): " bls; echo
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
    if [[ -n "$ip" ]]; then echo "externalip=$ip:$p2p" >>"$data/$CONF_FILE"; fi
    if [[ -n "$bls" ]]; then echo "smartnodeblsprivkey=$bls" >>"$data/$CONF_FILE"; fi
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
        count="${count:-1}"; [[ "$count" =~ ^[1-9][0-9]*$ ]] && break; echo "Enter a whole number greater than zero."
    done
    for ((i=1; i<=count; i++)); do
        while true; do
            read -r -p "Smartnode username $i/$count: " user
            valid_username "$user" || { echo "Use a valid lowercase Linux username."; continue; }
            break
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
    : > "$LOG_FILE"
    banner
    initialize_paths
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
