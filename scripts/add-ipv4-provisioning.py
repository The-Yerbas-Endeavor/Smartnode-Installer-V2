#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old_globals = '''IPV6_RESUME_FLAG="$STATE_DIR/ipv6-resume"
IPV6_ADDRESS_FILE="$STATE_DIR/ipv6-addresses"
IPV6_NETPLAN_FILE="/etc/netplan/10-ens3.yaml"
RESUME_AFTER_IPV6=0
'''
new_globals = '''NETWORK_RESUME_FLAG="$STATE_DIR/network-resume"
NETWORK_ADDRESS_FILE="$STATE_DIR/network-addresses"
NETWORK_NETPLAN_FILE="/etc/netplan/10-ens3.yaml"
LEGACY_IPV6_RESUME_FLAG="$STATE_DIR/ipv6-resume"
RESUME_AFTER_NETWORK=0
'''
if old_globals not in text:
    raise SystemExit("network globals block not found")
text = text.replace(old_globals, new_globals, 1)

text = text.replace(
    'if [[ ! -f "$IPV6_RESUME_FLAG" ]]; then',
    'if [[ ! -f "$NETWORK_RESUME_FLAG" && ! -f "$LEGACY_IPV6_RESUME_FLAG" ]]; then',
    1,
)
text = text.replace('    ipv6_provisioning\n', '    network_provisioning\n', 1)

start = text.find('normalize_ipv6_prefix64() {\n')
end = text.find('\ngithub_latest_json() {', start)
if start < 0 or end < 0:
    raise SystemExit("network provisioning block not found")

network_block = r'''validate_ipv4_cidr() {
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
        if [[ -s "$NETWORK_ADDRESS_FILE" ]]; then
            info "Network address provisioning was completed before the previous reboot."
            sed 's/^/  - /' "$NETWORK_ADDRESS_FILE"
        fi
        return 0
    fi

    prompt_yes_no "Would you like to add IPv4 addresses supplied by your server host?" "N" && add_ipv4=1
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

    touch "$NETWORK_RESUME_FLAG"
    sync
    warn "The server must reboot to complete network provisioning. Your SSH session will disconnect."
    echo "After reconnecting, run the installer again; it will continue after this stage:"
    echo "  sudo bash $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
    read -r -p "Press Enter to reboot now, or Ctrl+C to reboot later..."
    systemctl reboot
    exit 0
}
'''

text = text[:start] + network_block + text[end:]
path.write_text(text, encoding="utf-8")
