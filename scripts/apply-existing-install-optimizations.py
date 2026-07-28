#!/usr/bin/env python3
from pathlib import Path

# Applies one-time setup and PoW-cache reuse optimizations for existing installs.
path = Path("install.sh")
text = path.read_text(encoding="utf-8")

old_main = '''    detect_existing_install
    detect_platform
    install_dependencies
    network_provisioning
    create_swap
    resolve_release

    if (( EXISTING_INSTALL == 0 || ADDITIONAL_USERS == 1 )); then
        prompt_yes_no "Download and install the latest bootstrap for each new node?" "N" && USE_BOOTSTRAP=1
        prompt_yes_no "Download and install the latest PoW cache?" "Y" && USE_POWCACHE=1
    fi
'''
new_main = '''    detect_existing_install
    detect_platform

    if (( EXISTING_INSTALL == 0 )); then
        install_dependencies
        network_provisioning
        create_swap
    else
        info "Additional-user mode: skipping required packages, firewall, Fail2Ban, network provisioning, and swap configuration."
    fi

    resolve_release

    if (( EXISTING_INSTALL == 0 || ADDITIONAL_USERS == 1 )); then
        prompt_yes_no "Download and install the latest bootstrap for each new node?" "N" && USE_BOOTSTRAP=1

        if (( EXISTING_INSTALL == 1 )); then
            if [[ -s "$CACHE_DIR/powcache.dat" ]]; then
                USE_POWCACHE=1
                info "Existing PoW cache detected. Reusing it for additional Smartnode users."
            else
                info "No shared PoW cache is available. New users will synchronize without a preloaded PoW cache."
            fi
        else
            prompt_yes_no "Download and install the latest PoW cache?" "Y" && USE_POWCACHE=1
        fi
    fi
'''

if old_main not in text:
    raise SystemExit("Expected main setup block was not found")
text = text.replace(old_main, new_main, 1)

old_powcache = '''    if (( USE_POWCACHE == 1 )); then
        [[ -n "$POWCACHE_URL" ]] || die "Latest bootstrap release has no powcache.dat."
        [[ -f "$CACHE_DIR/powcache.dat" ]] || curl -fL --retry 3 "$POWCACHE_URL" -o "$CACHE_DIR/powcache.dat"
        install -m 0644 -o "$user" -g "$user" "$CACHE_DIR/powcache.dat" "$data/powcache.dat"
    fi
'''
new_powcache = '''    if (( USE_POWCACHE == 1 )); then
        if [[ ! -s "$CACHE_DIR/powcache.dat" ]]; then
            [[ -n "$POWCACHE_URL" ]] || die "Latest bootstrap release has no powcache.dat."
            curl -fL --retry 3 "$POWCACHE_URL" -o "$CACHE_DIR/powcache.dat"
        fi
        install -m 0644 -o "$user" -g "$user" "$CACHE_DIR/powcache.dat" "$data/powcache.dat"
    fi
'''

if old_powcache not in text:
    raise SystemExit("Expected PoW cache install block was not found")
text = text.replace(old_powcache, new_powcache, 1)

path.write_text(text, encoding="utf-8")
