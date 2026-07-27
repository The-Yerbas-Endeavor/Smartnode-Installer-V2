#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("install.sh")
text = path.read_text(encoding="utf-8")

new_function = r'''install_bootstrap_for_user() {
    (( USE_BOOTSTRAP == 1 )) || return
    [[ -n "$BOOTSTRAP_URL" ]] || die "Latest bootstrap release has no bootstrap.zip asset."

    local user="$1" data="$2"
    local part="$data/.bootstrap.zip.part"
    local extract="$data/.bootstrap-install.$$"
    local available_bytes required_bytes actual_bytes extracted_bytes
    local safety_bytes=$((1024 * 1024 * 1024))

    available_bytes="$(df -PB1 "$data" | awk 'NR == 2 {print $4}')"
    [[ "$available_bytes" =~ ^[0-9]+$ ]] ||
        die "Unable to determine available disk space for bootstrap download for $user."

    if (( BOOTSTRAP_SIZE > 0 )); then
        required_bytes=$((BOOTSTRAP_SIZE + safety_bytes))
        info "Bootstrap archive size for $user: $(numfmt --to=iec-i --suffix=B "$BOOTSTRAP_SIZE")."
        info "Available storage for $user: $(numfmt --to=iec-i --suffix=B "$available_bytes")."

        if (( available_bytes < required_bytes )); then
            die "Insufficient disk space for bootstrap download for $user. Required at least $(numfmt --to=iec-i --suffix=B "$required_bytes"); available $(numfmt --to=iec-i --suffix=B "$available_bytes")."
        fi
    fi

    info "Downloading bootstrap for $user..."
    rm -f "$part"
    rm -rf "$extract"
    mkdir -p "$extract"

    if ! curl -fL --retry 3 --retry-delay 2 "$BOOTSTRAP_URL" -o "$part"; then
        available_bytes="$(df -PB1 "$data" | awk 'NR == 2 {print $4}')"
        rm -f "$part"
        rm -rf "$extract"

        if (( BOOTSTRAP_SIZE > 0 && available_bytes < BOOTSTRAP_SIZE )); then
            die "Insufficient disk space for bootstrap download for $user."
        fi

        die "Bootstrap download failed for $user."
    fi

    actual_bytes="$(stat -c '%s' "$part")"
    if (( BOOTSTRAP_SIZE > 0 && actual_bytes != BOOTSTRAP_SIZE )); then
        rm -f "$part"
        rm -rf "$extract"
        die "Bootstrap download incomplete for $user. Expected $(numfmt --to=iec-i --suffix=B "$BOOTSTRAP_SIZE"), but received $(numfmt --to=iec-i --suffix=B "$actual_bytes")."
    fi

    if ! unzip -tq "$part" >/dev/null; then
        rm -f "$part"
        rm -rf "$extract"
        die "Downloaded bootstrap.zip failed ZIP validation for $user."
    fi

    extracted_bytes="$(LC_ALL=C unzip -Z -t "$part" 2>/dev/null | awk '/bytes uncompressed/ {gsub(/,/, "", $3); print $3; exit}')"
    available_bytes="$(df -PB1 "$data" | awk 'NR == 2 {print $4}')"

    if [[ "$extracted_bytes" =~ ^[0-9]+$ ]]; then
        required_bytes=$((extracted_bytes + safety_bytes))
        if (( available_bytes < required_bytes )); then
            rm -f "$part"
            rm -rf "$extract"
            die "Insufficient disk space to extract bootstrap for $user. Required approximately $(numfmt --to=iec-i --suffix=B "$required_bytes"); available $(numfmt --to=iec-i --suffix=B "$available_bytes")."
        fi
    fi

    info "Extracting bootstrap directly for $user..."
    if ! unzip -q "$part" -d "$extract"; then
        rm -f "$part"
        rm -rf "$extract"
        die "Bootstrap extraction failed for $user."
    fi

    if [[ -d "$extract/bootstrap" ]]; then
        shopt -s dotglob nullglob
        mv "$extract/bootstrap"/* "$extract"/ 2>/dev/null || true
        shopt -u dotglob nullglob
        rmdir "$extract/bootstrap" 2>/dev/null || true
    fi

    rm -rf "$data/assets" "$data/blocks" "$data/chainstate" "$data/evodb" "$data/llmq"
    rsync -a --remove-source-files "$extract"/ "$data"/
    find "$extract" -depth -type d -empty -delete 2>/dev/null || true
    chown -R "$user:$user" "$data"

    rm -f "$part"
    rm -rf "$extract"
    info "Bootstrap installation completed for $user; temporary files deleted."
}

'''

pattern = re.compile(r'prepare_bootstrap_cache\(\) \{.*?\n\}\n\nis_public_ipv4\(\) \{', re.S)
if not pattern.search(text):
    raise SystemExit("Could not find prepare_bootstrap_cache() block")
text = pattern.sub(new_function + 'is_public_ipv4() {', text, count=1)

old_bootstrap_block = '''    if (( USE_BOOTSTRAP == 1 )); then
        info "Installing cached bootstrap for $user..."
        rm -rf "$data/assets" "$data/blocks" "$data/chainstate" "$data/evodb" "$data/llmq"
        cp -a --reflink=auto "$CACHE_DIR/bootstrap-current"/. "$data"/
        chown -R "$user:$user" "$data"
    fi
'''
new_bootstrap_block = '''    install_bootstrap_for_user "$user" "$data"
'''
if old_bootstrap_block not in text:
    raise SystemExit("Could not find cached bootstrap installation block")
text = text.replace(old_bootstrap_block, new_bootstrap_block, 1)

old_main_call = '    prepare_bootstrap_cache\n'
if old_main_call not in text:
    raise SystemExit("Could not find prepare_bootstrap_cache main call")
text = text.replace(old_main_call, '', 1)

path.write_text(text, encoding="utf-8")
