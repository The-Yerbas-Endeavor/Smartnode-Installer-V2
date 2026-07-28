#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

marker = 'EXISTING_USERS=()\n'
globals_block = '''EXISTING_USERS=()
IPV6_RESUME_FLAG="$STATE_DIR/ipv6-resume"
IPV6_ADDRESS_FILE="$STATE_DIR/ipv6-addresses"
IPV6_NETPLAN_FILE="/etc/netplan/10-ens3.yaml"
RESUME_AFTER_IPV6=0
'''
if marker not in text:
    raise SystemExit("global insertion marker not found")
text = text.replace(marker, globals_block, 1)

insert_before = 'github_latest_json() { curl -fsSL --retry 3 "https://api.github.com/repos/$1/releases/latest"; }\n'
ipv6_functions = r'''normalize_ipv6_prefix64() {
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
    local prefix="$1" count="$2"
    python3 - "$prefix" "$count" <<'PY'
import ipaddress
import sys
network = ipaddress.IPv6Network(f"{sys.argv[1]}/64", strict=False)
count = int(sys.argv[2])
for host in range(1, count + 1):
    print(f"{ipaddress.IPv6Address(int(network.network_address) + host).compressed}/64")
PY
}

ipv6_provisioning() {
    local interface ipv4_cidr ipv4_gateway current_ipv6 ipv6_prefix
    local dns_list dns_yaml count generated address backup_file

    if [[ -f "$IPV6_RESUME_FLAG" ]]; then
        RESUME_AFTER_IPV6=1
        rm -f "$IPV6_RESUME_FLAG"
        if [[ -s "$IPV6_ADDRESS_FILE" ]]; then
            info "IPv6 provisioning was completed before the previous reboot."
            sed 's/^/  - /' "$IPV6_ADDRESS_FILE"
        fi
        return 0
    fi

    if ! prompt_yes_no "Would you like to create new IPv6 addresses?" "N"; then
        info "Skipping IPv6 address creation."
        return 0
    fi

    while true; do
        read -r -p "How many new IPv6 addresses should be created? [1]: " count
        count="${count:-1}"
        [[ "$count" =~ ^[1-9][0-9]*$ ]] && (( count <= 256 )) && break
        echo "Enter a whole number from 1 through 256."
    done

    interface="$(ip -4 route show default 2>/dev/null | awk 'NR == 1 {print $5}')"
    [[ -n "$interface" ]] || die "Unable to detect the primary network interface."

    ipv4_cidr="$(ip -o -4 addr show dev "$interface" scope global | awk 'NR == 1 {print $4}')"
    [[ -n "$ipv4_cidr" ]] || die "Unable to detect the current IPv4 address and prefix on $interface."

    ipv4_gateway="$(ip -4 route show default dev "$interface" 2>/dev/null | awk 'NR == 1 {print $3}')"
    [[ -n "$ipv4_gateway" ]] || die "Unable to detect the IPv4 default gateway on $interface."

    current_ipv6="$(ip -o -6 addr show dev "$interface" scope global | awk '$4 !~ /^fe80:/ {print $4; exit}')"
    [[ -n "$current_ipv6" ]] || die "No global IPv6 address was detected on $interface. Ask the hosting provider to assign an IPv6 /64 first."

    ipv6_prefix="$(normalize_ipv6_prefix64 "$current_ipv6")" || die "Unable to derive an IPv6 /64 from $current_ipv6."
    generated="$(generate_ipv6_addresses "$ipv6_prefix" "$count")" || die "Unable to generate IPv6 addresses."

    while read -r address; do
        [[ -n "$address" ]] || continue
        if ip -6 addr show dev "$interface" | grep -Fq "${address%/*}/"; then
            die "Generated address ${address%/*} is already assigned. Refusing to overwrite an existing IPv6 address."
        fi
    done <<<"$generated"

    dns_list="$(resolvectl dns "$interface" 2>/dev/null | sed -n 's/^[^:]*:[[:space:]]*//p' | tr ' ' '\n' | grep -E '^[0-9a-fA-F:.]+$' | head -n4 || true)"
    if [[ -z "$dns_list" ]]; then
        dns_list="$(grep -E '^nameserver[[:space:]]+' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | grep -vE '^(127\\.|::1$)' | head -n4 || true)"
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
    if [[ -e "$IPV6_NETPLAN_FILE" ]]; then
        backup_file="$IPV6_NETPLAN_FILE.backup.$(date +%Y%m%d-%H%M%S)"
        cp -a "$IPV6_NETPLAN_FILE" "$backup_file"
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
        echo "        - '$ipv4_cidr'"
        echo "        - '$current_ipv6'"
        while read -r address; do
            [[ -n "$address" ]] && echo "        - '$address'"
        done <<<"$generated"
        echo "      nameservers:"
        echo "        addresses: [$dns_yaml]"
        echo "      routes:"
        echo "        - to: default"
        echo "          via: '$ipv4_gateway'"
    } >"$IPV6_NETPLAN_FILE"
    chmod 0600 "$IPV6_NETPLAN_FILE"

    printf '%s\n' "$generated" >"$IPV6_ADDRESS_FILE"
    chmod 0600 "$IPV6_ADDRESS_FILE"

    info "Generated IPv6 addresses from $ipv6_prefix/64:"
    sed 's/^/  - /' "$IPV6_ADDRESS_FILE"
    info "Netplan configuration written to $IPV6_NETPLAN_FILE."

    if ! netplan generate >>"$LOG_FILE" 2>&1; then
        [[ -z "$backup_file" ]] || cp -a "$backup_file" "$IPV6_NETPLAN_FILE"
        die "Netplan validation failed. The previous 10-ens3.yaml was restored when available."
    fi

    warn "Applying network changes can interrupt this SSH connection."
    if ! prompt_yes_no "Apply the new netplan configuration now?" "Y"; then
        [[ -z "$backup_file" ]] || cp -a "$backup_file" "$IPV6_NETPLAN_FILE"
        rm -f "$IPV6_ADDRESS_FILE"
        info "IPv6 changes were not applied."
        return 0
    fi

    netplan apply
    sleep 3
    while read -r address; do
        [[ -n "$address" ]] || continue
        ip -6 addr show dev "$interface" | grep -Fq "${address%/*}/" || die "IPv6 verification failed for ${address%/*}."
    done <"$IPV6_ADDRESS_FILE"

    info "All requested IPv6 addresses are active on $interface."
    log "INFO: IPv6 provisioning interface=$interface count=$count prefix=$ipv6_prefix"

    touch "$IPV6_RESUME_FLAG"
    sync
    warn "The server must reboot to complete IPv6 provisioning. Your SSH session will disconnect."
    echo "After reconnecting, run the installer again; it will continue after this stage:"
    echo "  sudo bash $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
    read -r -p "Press Enter to reboot now, or Ctrl+C to reboot later..."
    systemctl reboot
    exit 0
}

'''
if insert_before not in text:
    raise SystemExit("IPv6 function insertion marker not found")
text = text.replace(insert_before, ipv6_functions + insert_before, 1)

old_main = '''main() {
    require_root
    : > "$LOG_FILE"
    banner
    initialize_paths
    detect_existing_install
    detect_platform
    install_dependencies
    create_swap
    resolve_release
'''
new_main = '''main() {
    require_root
    initialize_paths
    if [[ ! -f "$IPV6_RESUME_FLAG" ]]; then
        : > "$LOG_FILE"
    fi
    banner
    detect_existing_install
    detect_platform
    install_dependencies
    create_swap
    ipv6_provisioning
    resolve_release
'''
if old_main not in text:
    raise SystemExit("main function marker not found")
text = text.replace(old_main, new_main, 1)

path.write_text(text, encoding="utf-8")

# Workflow trigger after the workflow file exists.
