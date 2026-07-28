#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")
old = '''service_users() {
    systemctl list-unit-files 'yerbasd@*.service' --no-legend 2>/dev/null |
        awk '{print $1}' | sed -n 's/^yerbasd@\(.*\)\.service$/\1/p' | sort -u
}
'''
new = '''service_users() {
    { systemctl list-unit-files 'yerbasd@*.service' --no-legend 2>/dev/null || true; } |
        awk '{print $1}' | sed -n 's/^yerbasd@\(.*\)\.service$/\1/p' | sort -u
}
'''
if old not in text:
    raise SystemExit("service_users block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
