#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old = '''select_server_ip() {
    local user="$1" choice manual default=1 i ip
    local -a public_v4=() public_v6=() private_v4=() private_v6=() choices=() labels=()
    local candidate

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        if is_public_ipv4 "$candidate"; then public_v4+=("$candidate"); else private_v4+=("$candidate"); fi
    done < <({
        ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \\([^ ]*\\).*/\\1/p'
        ip -o -4 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1
        curl -4fsS --max-time 4 https://api.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++')

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        if is_public_ipv6 "$candidate"; then public_v6+=("$candidate"); else private_v6+=("$candidate"); fi
    done < <({
        ip -6 route get 2606:4700:4700::1111 2>/dev/null | sed -n 's/.* src \\([^ ]*\\).*/\\1/p'
        ip -o -6 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | sed 's/%.*//'
        curl -6fsS --max-time 4 https://api64.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++')

    for ip in "${public_v4[@]}"; do choices+=("$ip"); labels+=("Public IPv4"); done
    for ip in "${public_v6[@]}"; do choices+=("$ip"); labels+=("Public IPv6"); done
    for ip in "${private_v4[@]}"; do choices+=("$ip"); labels+=("Private IPv4"); done
    for ip in "${private_v6[@]}"; do choices+=("$ip"); labels+=("Private IPv6"); done

    echo >&2
    echo "Select the external IP address for $user" >&2
    echo >&2
    if ((${#choices[@]})); then
        for i in "${!choices[@]}"; do printf ' %2d) %-39s (%s)\\n' "$((i + 1))" "${choices[$i]}" "${labels[$i]}" >&2; done
    else
        echo "  No server IPv4 or IPv6 addresses were detected." >&2
    fi
    printf ' %2d) Enter a different address manually\\n' "$((${#choices[@]} + 1))" >&2
    printf ' %2d) Leave externalip unset\\n' "$((${#choices[@]} + 2))" >&2

    while true; do
        if ((${#choices[@]})); then
            read -r -p "Selection [$default]: " choice
            choice="${choice:-$default}"
        else
            read -r -p "Selection [1]: " choice
            choice="${choice:-1}"
        fi
        [[ "$choice" =~ ^[0-9]+$ ]] || { echo "Enter a menu number." >&2; continue; }
        if ((choice >= 1 && choice <= ${#choices[@]})); then
            printf '%s\\n' "${choices[$((choice - 1))]}"
            return
        elif ((choice == ${#choices[@]} + 1)); then
            read -r -p "Enter IPv4 or IPv6 address: " manual
            [[ -n "$manual" ]] || { echo "Address cannot be blank." >&2; continue; }
            manual="${manual#[}"; manual="${manual%]}"
            printf '%s\\n' "$manual"
            return
        elif ((choice == ${#choices[@]} + 2)); then
            printf '\\n'
            return
        fi
        echo "Invalid selection." >&2
    done
}
'''

new = '''select_server_ip() {
    local user="$1" choice manual default=1 i ip
    local -a public_v4=() public_v6=() choices=() labels=()
    local candidate

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        is_public_ipv4 "$candidate" && public_v4+=("$candidate")
    done < <({
        ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \\([^ ]*\\).*/\\1/p'
        ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1
        curl -4fsS --max-time 4 https://api.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++')

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        is_public_ipv6 "$candidate" && public_v6+=("$candidate")
    done < <({
        ip -6 route get 2606:4700:4700::1111 2>/dev/null | sed -n 's/.* src \\([^ ]*\\).*/\\1/p'
        ip -o -6 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | sed 's/%.*//'
        curl -6fsS --max-time 4 https://api64.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++')

    for ip in "${public_v4[@]}"; do choices+=("$ip"); labels+=("Public IPv4"); done
    for ip in "${public_v6[@]}"; do choices+=("$ip"); labels+=("Public IPv6"); done

    echo >&2
    echo "Select the public external IP address for $user" >&2
    echo >&2

    if ((${#choices[@]} == 0)); then
        die "No public IPv4 or IPv6 addresses were detected on this server."
    fi

    for i in "${!choices[@]}"; do
        printf ' %2d) %-39s (%s)\\n' "$((i + 1))" "${choices[$i]}" "${labels[$i]}" >&2
    done
    printf ' %2d) Enter a different public IP manually\\n' "$((${#choices[@]} + 1))" >&2

    while true; do
        read -r -p "Selection [$default]: " choice
        choice="${choice:-$default}"
        [[ "$choice" =~ ^[0-9]+$ ]] || { echo "Enter a menu number." >&2; continue; }

        if ((choice >= 1 && choice <= ${#choices[@]})); then
            printf '%s\\n' "${choices[$((choice - 1))]}"
            return
        elif ((choice == ${#choices[@]} + 1)); then
            read -r -p "Enter public IPv4 or IPv6 address: " manual
            [[ -n "$manual" ]] || { echo "Address cannot be blank." >&2; continue; }
            manual="${manual#[}"; manual="${manual%]}"

            if is_public_ipv4 "$manual" || is_public_ipv6 "$manual"; then
                printf '%s\\n' "$manual"
                return
            fi

            echo "Enter a public IPv4 or IPv6 address." >&2
            continue
        fi

        echo "Invalid selection." >&2
    done
}
'''

if old not in text:
    raise SystemExit("select_server_ip function did not match expected content")

path.write_text(text.replace(old, new, 1), encoding="utf-8")
