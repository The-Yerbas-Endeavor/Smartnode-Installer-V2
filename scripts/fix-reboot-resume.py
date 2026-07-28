#!/usr/bin/env python3
from pathlib import Path

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old = '''    cat >"$RESUME_SERVICE" <<EOF
[Unit]
Description=Resume Yerbas Smartnode Installer after network reboot
Wants=network-online.target
After=network-online.target
ConditionPathExists=$NETWORK_RESUME_FLAG

[Service]
Type=oneshot
ExecStart=/usr/bin/tmux new-session -d -s $RESUME_TMUX_SESSION /bin/bash $RESUME_SCRIPT --resume
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable yerbas-installer-resume.service >/dev/null
'''

new = '''    cat >"$RESUME_SERVICE" <<EOF
[Unit]
Description=Resume Yerbas Smartnode Installer after network reboot
Wants=network-online.target
After=network-online.target
ConditionPathExists=$NETWORK_RESUME_FLAG

[Service]
Type=oneshot
Environment=TERM=xterm-256color
ExecStartPre=/bin/sleep 15
ExecStart=/bin/bash -lc '/usr/bin/tmux has-session -t $RESUME_TMUX_SESSION 2>/dev/null || /usr/bin/tmux new-session -d -s $RESUME_TMUX_SESSION "/bin/bash -lc \\\"/bin/bash $RESUME_SCRIPT --resume 2>&1 | /usr/bin/tee -a $LOG_FILE; status=\\\\${PIPESTATUS[0]}; echo; echo Resume installer exited with status \\\\$status.; echo Review $LOG_FILE for details.; exec /bin/bash\\\""'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable yerbas-installer-resume.service >/dev/null
'''

if old not in text:
    raise SystemExit("resume service block not found")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
