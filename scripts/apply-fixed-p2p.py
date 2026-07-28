#!/usr/bin/env python3
from pathlib import Path

install = Path("install.sh")
text = install.read_text(encoding="utf-8")

old = '''    p2p="$(next_available_port "$DEFAULT_P2P_PORT")"
    rpc="$(next_available_port "$DEFAULT_RPC_PORT")"
    while true; do read -r -p "P2P port for $user [$p2p]: " v; p2p="${v:-$p2p}"; valid_port "$p2p" && ! port_in_use "$p2p" && break; echo "Port is invalid or in use."; done
    while true; do read -r -p "RPC port for $user [$rpc]: " v; rpc="${v:-$rpc}"; valid_port "$rpc" && [[ "$rpc" != "$p2p" ]] && ! port_in_use "$rpc" && break; echo "Port is invalid, duplicated, or in use."; done
    ip="$(select_server_ip "$user")"
'''
new = '''    p2p="$DEFAULT_P2P_PORT"
    rpc="$(next_available_port "$DEFAULT_RPC_PORT")"
    while true; do read -r -p "RPC port for $user [$rpc]: " v; rpc="${v:-$rpc}"; valid_port "$rpc" && [[ "$rpc" != "$p2p" ]] && ! port_in_use "$rpc" && break; echo "Port is invalid, duplicated, or in use."; done
    ip="$(select_server_ip "$user")"

    if grep -RqsE "^externalip=(\\[$ip\\]|$ip):$DEFAULT_P2P_PORT$" /home/*/.yerbascore/yerbas.conf 2>/dev/null; then
        die "Public IP $ip is already assigned to another Yerbas Smartnode. This installer requires one Smartnode per public IP."
    fi

    info "Using required Yerbas P2P port $DEFAULT_P2P_PORT for $user."
'''
if old not in text:
    raise SystemExit("P2P configuration block not found")
install.write_text(text.replace(old, new, 1), encoding="utf-8")

readme = Path("README.md")
r = readme.read_text(encoding="utf-8")
r = r.replace(
    "The installer asks for swap size, bootstrap options, the number of Smartnode users, usernames, ports, public IPs, and BLS private keys.",
    "The installer asks for swap size, bootstrap options, the number of Smartnode users, usernames, RPC ports, public IPs, and BLS private keys. Yerbas P2P port 15420 is assigned automatically."
)
r = r.replace(
    "Every node on the same server must use a unique RPC port. Every node bound to the same public IP must also use a unique P2P port. The installer proposes available ports beginning with:",
    "Every node on the same server must use a unique RPC port. This installer uses the deployment model of one Smartnode per public IP, and every Smartnode automatically uses the required Yerbas P2P port 15420."
)
r = r.replace(
    "```text\nP2P: 15420\nRPC: 9494\n```",
    "```text\nP2P: 15420 (fixed)\nRPC: 9494, 9495, 9496, ...\n```"
)
readme.write_text(r, encoding="utf-8")

# Trigger workflow after it exists.
