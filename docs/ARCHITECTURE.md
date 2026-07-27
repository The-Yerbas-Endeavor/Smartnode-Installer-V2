# v2 Architecture

## Shared binaries

Yerbas releases are installed in versioned directories:

```text
/opt/yerbas/releases/<release-tag>/
/opt/yerbas/current -> /opt/yerbas/releases/<release-tag>/
```

Global command symlinks point to `/opt/yerbas/current`.

## Per-user nodes

Each Smartnode runs as its own Linux user and stores data in:

```text
/home/<user>/.yerbascore/
```

Each node has its own RPC credentials, RPC port, P2P port, BLS key, and service instance.

## systemd

The template service is instantiated as:

```bash
systemctl enable --now yerbasd@USER
```

## Updates

Rerunning the installer downloads the latest compatible Yerbas release, installs it in a new versioned directory, updates the `current` symlink, and restarts configured instances. User data and existing `yerbas.conf` files are preserved.

## Bootstrap cache

The latest bootstrap is downloaded once into `/var/cache/yerbas` and copied to each newly configured node. Writable blockchain directories are never shared between running users.
