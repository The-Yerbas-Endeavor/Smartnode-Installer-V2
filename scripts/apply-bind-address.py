#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old = '''format_external_endpoint() {
    local ip="$1" port="$2"
    if [[ "$ip" == *:* ]]; then printf '[%s]:%s\\n' "$ip" "$port"; else printf '%s:%s\\n' "$ip" "$port"; fi
}
'''
new = '''format_external_endpoint() {
    local ip="$1" port="$2"
    if [[ "$ip" == *:* ]]; then printf '[%s]:%s\\n' "$ip" "$port"; else printf '%s:%s\\n' "$ip" "$port"; fi
}

format_bind_address() {
    local ip="$1"
    if [[ "$ip" == *:* ]]; then printf '[%s]\\n' "$ip"; else printf '%s\\n' "$ip"; fi
}
'''
if old not in text:
    raise SystemExit("format_external_endpoint block not found")
text = text.replace(old, new, 1)

old = '''    if [[ -n "$ip" ]]; then endpoint="$(format_external_endpoint "$ip" "$p2p")"; echo "externalip=$endpoint" >>"$data/$CONF_FILE"; fi
'''
new = '''    if [[ -n "$ip" ]]; then
        endpoint="$(format_external_endpoint "$ip" "$p2p")"
        echo "bind=$(format_bind_address "$ip")" >>"$data/$CONF_FILE"
        echo "externalip=$endpoint" >>"$data/$CONF_FILE"
    fi
'''
if old not in text:
    raise SystemExit("externalip config line not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

# Trigger workflow after creation.
