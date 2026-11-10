# Yerbas Smartnode Installer v2

A one-command Ubuntu installer and updater for running multiple isolated Yerbas Smartnodes on one server.

```bash
curl -fsSL https://raw.githubusercontent.com/The-Yerbas-Endeavor/Smartnode-Installer-V2/main/install.sh -o install.sh
chmod +x install.sh
sudo ./install.sh
```

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

## Smartnode status after reboot

The installer registers a read-only systemd timer that creates a status report about **3 minutes after each server boot**. It reports all registered Smartnodes (service active/enabled state, Smartnode readiness when RPC is available, and block height), without restarting or modifying any nodes. A slow-to-start Smartnode may initially show `RPC unavailable or still loading`.

On **every SSH login**, the banner requests fresh, read-only Smartnode states and block heights. Each per-node RPC query is limited to two seconds and the complete login refresh has a 16-second timeout, so an unavailable node cannot block SSH indefinitely. If the refresh times out or fails, the banner clearly labels and displays the saved boot report instead of presenting stale data as current. The boot timer still creates its snapshot around three minutes after startup.

```bash
sudo journalctl -u yerbas-boot-status.service -b --no-pager
cat /run/yerbas-smartnodes/status
sudo systemctl start yerbas-boot-status.service  # refresh immediately
```

The boot-status script is `/usr/local/sbin/yerbas-boot-status`, and the timer is `yerbas-boot-status.timer`. The report resides in `/run` and is regenerated after reboot. Run the installer again to install these startup hooks on an existing server.

## Updating

Run the installer again:

```bash
sudo ./install.sh
```

Existing `yerbas.conf`, BLS keys, wallets, and blockchain data are preserved. When an existing installation is detected, the installer lists its Smartnode users and installed wallet release, checks the latest compatible Yerbas release, then displays one menu:

```text
1) Add Smartnode
2) Update Smartnodes
3) Update/add IPv4 or IPv6 address
4) Display Current Smartnodes' status
5) Edit Smartnode
6) Remove Smartnode
7) Exit (no changes)
```

Choose one operation; pressing Enter defaults to exit without changes. Option 4 displays every existing Smartnode user's systemd service status (active/enabled), its RPC Smartnode state, and block height when available. It is read-only, handles unavailable RPC or stopped services, and returns to the menu without changing nodes. The installer also prints this status report automatically after a successful fresh installation, wallet update, or new-node addition, including newly created nodes. If the installed wallet release is already current, option 2 is marked `already current` and cannot initiate an update. If a wallet update is selected, shared binaries are changed and existing services rolling-restarted one at a time. Adding a new user can also require changing the shared wallet binaries; in that case the installer asks for explicit consent before touching existing nodes.


## Editing an existing Smartnode

Choose **5) Edit Smartnode** to select an installed Smartnode user and change its **external IP address**, **BLS private key**, or **RPC port**. Edits are limited to these settings; existing wallet files, blockchain data, RPC credentials, and unrelated configuration lines are preserved.

The editor validates the requested field, makes a permission-restricted backup of `yerbas.conf`, and requires explicit confirmation before saving. It restarts **only the selected Smartnode** if its service was active, and restores the previous configuration if that restart fails. A stopped Smartnode remains stopped until its next manual or normal start. The editor does not display BLS private keys.

When changing an external IP, make sure it is provisioned on the server and matches the registered ProTx service endpoint. A configuration change alone cannot modify the on-chain ProTx registration.

## Removing a Smartnode

Choose **6) Remove Smartnode** and select exactly one installed node. Two removal modes are offered:

- **Disable and unregister (recommended):** Stop and disable only that node, remove it from the installer-managed users list, and rename its `yerbas.conf` to a timestamped `yerbas.conf.removed.*` file. The Linux account, BLS configuration backup, blockchain and other data remain in place for recovery. The renamed config prevents the node from being automatically rediscovered by the installer.
- **Permanently delete:** Stop and disable only that node, then remove its dedicated Linux account and complete `/home/USERNAME` directory (including BLS key, blockchain and wallet data) with `userdel -r`. This is irreversible without an external backup.

Both modes require typing **REMOVE USERNAME** or **DELETE USERNAME** exactly. Only registered managed nodes whose home directory is exactly `/home/USERNAME` are eligible. Failure to stop the service aborts removal. The other Smartnodes, shared Yerbas binaries, common service template and P2P firewall rules are not modified.

Removing the server installation does **not** revoke, deregister, or update any on-chain ProTx registration or collateral. Preserve the operator key if it will be reused.

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
python3 -m unittest discover -s tests -v
```

The regression tests run without root, use temporary directories and mocked system commands, and never run the installer against the host. They cover RPC port selection, optional bootstrap behavior, manager parity for single-file downloads, and release rollback.

## Important deployment note

Test v2 on a fresh Ubuntu VPS before using it on production Smartnodes. The script changes packages, firewall rules, swap, users, systemd services, and node data directories.
