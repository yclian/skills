# 🛡️ Fleet Restic Backup

A generic, battle-tested agent skill and runbook for orchestrating multi-node encrypted backups across mixed-OS fleets (Linux servers, Windows workstations, macOS laptops) into a unified, deduplicated [Restic](https://restic.readthedocs.io/) repository.

---

## Features

- **Asymmetric Hub-and-Spoke Architecture**: Remote client nodes do not hold repository passwords or storage credentials. If an edge machine is compromised, historical backups cannot be tampered with.
- **Zero-Downtime SQLite Pre-Hooks**: Uses the native SQLite online `.backup` API to capture consistent point-in-time snapshots of live databases without stopping services or risking WAL corruption.
- **Windows Live VSS Snapshotting**: Backs up active Windows development trees, user dotfiles, and open database files seamlessly via Volume Shadow Copy (`--use-fs-snapshot`).
- **Cross-Platform Link Tolerance**: Configured with `--sftp-skip-links` and non-fatal warning degradation to eliminate crash loops from directory junctions and broken cross-platform symlinks.
- **Automated GFS Retention**: Enforces Grandfather-Father-Son snapshot pruning (`keep-daily 7`, `keep-weekly 5`, `keep-monthly 12`, `keep-yearly 3`) and automated repository integrity checks.

---

## Directory Structure

```
fleet-restic-backup/
├── SKILL.md                          # Full architectural guide and invariants
├── README.md                         # Quick reference & overview
└── scripts/
    ├── fleet-backup.ps1              # Windows Hub orchestrator template
    ├── fleet-maintenance.ps1         # Automated retention and integrity checks
    ├── backup_sqlite.py              # Cross-platform atomic SQLite snapshot helper
    └── prepare-node.sh               # POSIX server pre-hook script template
```

---

## Quick Start

### 1. Initialize Restic Repository
```bash
restic init --repo <BACKUP_DIR>/.restic-repo --password-file <SECRETS_DIR>/restic-password.txt
```

### 2. Configure Node Pre-Hooks
Deploy `prepare-node.sh` to server nodes and register it in `sudoers` so the backup service user can run it unattended:
```bash
backup-operator ALL=(ALL) NOPASSWD: /usr/local/sbin/prepare-node.sh
```

### 3. Run or Schedule Orchestration
Run the backup script directly or register it via Windows Task Scheduler (`NT AUTHORITY\SYSTEM`) or Linux `systemd.timer`:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\fleet-backup.ps1
```
