#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")
old = '    (( EXISTING_INSTALL == 1 )) || return\n'
new = '    if (( EXISTING_INSTALL == 0 )); then\n        return 0\n    fi\n'
if old not in text:
    raise SystemExit("existing-install early return not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
