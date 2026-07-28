#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old = '''ExecStart=/bin/bash -lc '/usr/bin/tmux has-session -t $RESUME_TMUX_SESSION 2>/dev/null || /usr/bin/tmux new-session -d -s $RESUME_TMUX_SESSION "/bin/bash -lc \\"/bin/bash $RESUME_SCRIPT --resume 2>&1 | /usr/bin/tee -a $LOG_FILE; status=\\\\${PIPESTATUS[0]}; echo; echo Resume installer exited with status \\\\$status.; echo Review $LOG_FILE for details.; exec /bin/bash\\""' '''.strip()

replacement = '''ExecStart=/bin/bash -lc '/usr/bin/tmux has-session -t $RESUME_TMUX_SESSION 2>/dev/null || /usr/bin/tmux new-session -d -s $RESUME_TMUX_SESSION "/bin/bash -lc \\"/bin/bash $RESUME_SCRIPT --resume 2>&1 | /usr/bin/tee -a $LOG_FILE; echo; echo Resume installer stopped.; echo Review $LOG_FILE for details.; exec /bin/bash\\""' '''.strip()

if old not in text:
    # Match the current generated line more defensively.
    lines = text.splitlines()
    changed = False
    for i, line in enumerate(lines):
        if line.startswith("ExecStart=/bin/bash -lc '") and "PIPESTATUS" in line and "Resume installer exited with status" in line:
            lines[i] = replacement
            changed = True
            break
    if not changed:
        raise SystemExit("resume ExecStart line not found")
    text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
else:
    text = text.replace(old, replacement, 1)

path.write_text(text, encoding="utf-8")
