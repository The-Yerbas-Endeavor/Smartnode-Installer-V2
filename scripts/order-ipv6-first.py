#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")
old = '''    install_dependencies
    create_swap
    ipv6_provisioning
    resolve_release
'''
new = '''    install_dependencies
    ipv6_provisioning
    create_swap
    resolve_release
'''
if old not in text:
    raise SystemExit("installer stage order not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Workflow trigger after workflow creation.
