#!/usr/bin/env python3
# Applies the production IPv6 generation and verification correction.
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old_generate = r'''generate_ipv6_addresses() {
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
'''
new_generate = r'''generate_ipv6_addresses() {
    local current_address="$1" count="$2"
    python3 - "$current_address" "$count" <<'PY'
import ipaddress
import sys

interface = ipaddress.IPv6Interface(sys.argv[1])
count = int(sys.argv[2])
base = int(interface.ip) & ~0xff

for suffix in range(1, count + 1):
    address = ipaddress.IPv6Address(base | suffix)
    print(f"{address.compressed}/{interface.network.prefixlen}")
PY
}

ipv6_address_is_active() {
    local interface="$1" expected="$2"
    ip -j -6 addr show dev "$interface" 2>/dev/null | python3 - "$expected" <<'PY'
import ipaddress
import json
import sys

expected = ipaddress.IPv6Address(sys.argv[1].split('/', 1)[0])
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
            if ipaddress.IPv6Address(local) == expected:
                raise SystemExit(0)
        except ValueError:
            continue
raise SystemExit(1)
PY
}
'''
if old_generate not in text:
    raise SystemExit("IPv6 generator block not found")
text = text.replace(old_generate, new_generate, 1)

text = text.replace(
    'generated="$(generate_ipv6_addresses "$ipv6_prefix" "$count")" || die "Unable to generate IPv6 addresses."',
    'generated="$(generate_ipv6_addresses "$current_ipv6" "$count")" || die "Unable to generate IPv6 addresses."',
    1,
)
text = text.replace(
    'info "Generated IPv6 addresses from $ipv6_prefix/64:"',
    'info "Generated IPv6 addresses using the current server IPv6 address $current_ipv6:"',
    1,
)

old_verify = r'''    netplan apply
    sleep 3
    while read -r address; do
        [[ -n "$address" ]] || continue
        ip -6 addr show dev "$interface" | grep -Fq "${address%/*}/" || die "IPv6 verification failed for ${address%/*}."
    done <"$IPV6_ADDRESS_FILE"

    info "All requested IPv6 addresses are active on $interface."
'''
new_verify = r'''    netplan apply

    while read -r address; do
        [[ -n "$address" ]] || continue
        verified=0
        for attempt in {1..15}; do
            if ipv6_address_is_active "$interface" "$address"; then
                verified=1
                break
            fi
            sleep 2
        done

        if (( verified == 0 )); then
            warn "IPv6 verification failed for ${address%/*}. Restoring the previous netplan configuration."
            ip -6 addr show dev "$interface" | tee -a "$LOG_FILE" >&2 || true
            if [[ -n "$backup_file" && -f "$backup_file" ]]; then
                cp -a "$backup_file" "$IPV6_NETPLAN_FILE"
            else
                rm -f "$IPV6_NETPLAN_FILE"
            fi
            netplan generate >>"$LOG_FILE" 2>&1 || true
            netplan apply >>"$LOG_FILE" 2>&1 || true
            rm -f "$IPV6_ADDRESS_FILE"
            die "IPv6 verification failed for ${address%/*}; the previous network configuration was restored."
        fi
    done <"$IPV6_ADDRESS_FILE"

    info "All requested IPv6 addresses are active on $interface."
'''
if old_verify not in text:
    raise SystemExit("IPv6 verification block not found")
text = text.replace(old_verify, new_verify, 1)

text = text.replace('local dns_list dns_yaml count generated address backup_file', 'local dns_list dns_yaml count generated address backup_file verified attempt', 1)

path.write_text(text, encoding="utf-8")
