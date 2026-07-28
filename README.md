# Yerbas Smartnode Installer v2

A one-command Ubuntu installer and updater for running multiple isolated Yerbas Smartnodes on one server.

## Highlights

- Shared, versioned Yerbas binaries in `/opt/yerbas`
- Separate Linux user and data directory for every Smartnode
- One `systemd` service instance per user
- Automatic startup after reboot
- Unique P2P and RPC ports
- Latest compatible Yerbas GitHub release
- Latest bootstrap and PoW cache support
- Existing node configuration and blockchain data preserved on updates
- UFW, Fail2ban, swap configuration, health checks, and centralized management

## Supported systems

- Ubuntu 22.04
- Ubuntu 24.04
- Ubuntu 26.04
- x86_64
- aarch64 when a compatible Yerbas release asset exists

## One-command installation

```bash
curl -fsSL https://raw.githubusercontent.com/The-Yerbas-Endeavor/Smartnode-Installer-V2/main/install.sh -o install.sh
chmod +x install.sh
sudo ./install.sh
```

The installer asks for swap size, bootstrap options, the number of Smartnode users, usernames, RPC ports, public IPs, and BLS private keys. Yerbas P2P port 15420 is assigned automatically.

## Layout after installation

```text
/opt/yerbas/releases/<version>/   Versioned wallet binaries
/opt/yerbas/current               Active-release symlink
/usr/local/bin/yerbasd            Global daemon command
/usr/local/bin/yerbas-cli         Global CLI command
/etc/systemd/system/yerbasd@.service
/var/cache/yerbas                 Shared PoW cache and installer downloads
/var/lib/yerbas-installer/users   Managed user list
/home/<user>/.yerbascore          Per-user node data
```

## Managing nodes

```bash
yerbas-node-manager status
yerbas-node-manager info USER
yerbas-node-manager restart USER
yerbas-node-manager logs USER
yerbas-node-manager cli USER getblockchaininfo
yerbas-node-manager cli USER getnetworkinfo
yerbas-node-manager cli USER smartnode status
```

The Smartnode status command reports states such as `READY` or `WAITING_FOR_PROTX`:

```bash
yerbas-node-manager cli mrx2 smartnode status
```

Direct systemd commands also work:

```bash
sudo systemctl status yerbasd@USER
sudo systemctl restart yerbasd@USER
sudo journalctl -u yerbasd@USER -f
```

## Updating

Run the installer again:

```bash
sudo ./install.sh
```

Existing `yerbas.conf`, BLS keys, wallets, and blockchain data are preserved. The shared binaries are updated for all configured users.

## Multiple nodes and ports

Every node on the same server must use a unique RPC port. This installer uses the deployment model of one Smartnode per public IP, and every Smartnode automatically uses the required Yerbas P2P port 15420.

```text
P2P: 15420 (fixed)
RPC: 9494, 9495, 9496, ...
```

## Security notes

- Smartnode users are not automatically granted sudo access.
- Configuration files are created with mode `0600`.
- RPC is restricted to localhost by default.
- BLS keys and RPC passwords should never be committed to Git.
- Review firewall and SSH access before disconnecting from a remote server.

## Repository layout

```text
install.sh                         Main interactive installer/updater
bin/yerbas-node-manager           Installed management utility
systemd/yerbasd@.service          systemd template reference
config/nodes.conf.example         Future noninteractive configuration example
docs/ARCHITECTURE.md              Design documentation
.github/workflows/shellcheck.yml  Shell validation workflow
```

## Validation

```bash
bash -n install.sh
bash -n bin/yerbas-node-manager
shellcheck install.sh bin/yerbas-node-manager
```

## Important deployment note

Test v2 on a fresh Ubuntu VPS before using it on production Smartnodes. The script changes packages, firewall rules, swap, users, systemd services, and node data directories.
