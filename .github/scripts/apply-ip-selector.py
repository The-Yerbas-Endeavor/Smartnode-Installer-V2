from pathlib import Path

path = Path("install.sh")
text = path.read_text()

marker = "configure_user_node() {\n"
helper = r'''is_public_ipv4() {
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
    local user="$1" choice manual default=1 i ip
    local -a public_v4=() public_v6=() private_v4=() private_v6=() choices=() labels=()
    local candidate

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        if is_public_ipv4 "$candidate"; then public_v4+=("$candidate"); else private_v4+=("$candidate"); fi
    done < <({
        ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p'
        ip -o -4 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1
        curl -4fsS --max-time 4 https://api.ipify.org 2>/dev/null || true
        echo
    } | awk 'NF && !seen[$0]++')

    while read -r candidate; do
        [[ -n "$candidate" ]] || continue
        if is_public_ipv6 "$candidate"; then public_v6+=("$candidate"); else private_v6+=("$candidate"); fi
    done < <({
        ip -6 route get 2606:4700:4700::1111 2>/dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p'
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
        for i in "${!choices[@]}"; do printf ' %2d) %-39s (%s)\n' "$((i + 1))" "${choices[$i]}" "${labels[$i]}" >&2; done
    else
        echo "  No server IPv4 or IPv6 addresses were detected." >&2
    fi
    printf ' %2d) Enter a different address manually\n' "$((${#choices[@]} + 1))" >&2
    printf ' %2d) Leave externalip unset\n' "$((${#choices[@]} + 2))" >&2

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
            printf '%s\n' "${choices[$((choice - 1))]}"
            return
        elif ((choice == ${#choices[@]} + 1)); then
            read -r -p "Enter IPv4 or IPv6 address: " manual
            [[ -n "$manual" ]] || { echo "Address cannot be blank." >&2; continue; }
            manual="${manual#[}"; manual="${manual%]}"
            printf '%s\n' "$manual"
            return
        elif ((choice == ${#choices[@]} + 2)); then
            printf '\n'
            return
        fi
        echo "Invalid selection." >&2
    done
}

format_external_endpoint() {
    local ip="$1" port="$2"
    if [[ "$ip" == *:* ]]; then printf '[%s]:%s\n' "$ip" "$port"; else printf '%s:%s\n' "$ip" "$port"; fi
}

configure_user_node() {
'''

if "select_server_ip() {" not in text:
    text = text.replace(marker, helper, 1)

text = text.replace(
    '    read -r -p "Public IP for $user: " ip\n',
    '    ip="$(select_server_ip "$user")"\n',
    1,
)
text = text.replace(
    '    if [[ -n "$ip" ]]; then echo "externalip=$ip:$p2p" >>"$data/$CONF_FILE"; fi\n',
    '    if [[ -n "$ip" ]]; then endpoint="$(format_external_endpoint "$ip" "$p2p")"; echo "externalip=$endpoint" >>"$data/$CONF_FILE"; fi\n',
    1,
)
text = text.replace(
    '    local user="$1" home data p2p rpc ip bls rpcuser rpcpass\n',
    '    local user="$1" home data p2p rpc ip endpoint bls rpcuser rpcpass\n',
    1,
)

path.write_text(text)
