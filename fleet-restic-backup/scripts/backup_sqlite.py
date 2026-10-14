#!/usr/bin/env python3
"""
backup_sqlite.py -- Atomic SQLite pre-backup snapshot utility.

Walks specified root directories and creates WAL-safe, consistent
`<dbname>.bak-nightly` copies for every `.db` or `.sqlite` file using
the SQLite online backup API.

Usage:
    python backup_sqlite.py <dir1> <dir2> ...
"""

import os
import sys
import sqlite3
from pathlib import Path

EXCLUDE_DIR_PATTERNS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    ".npm",
    "cache",
}

def is_excluded(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIR_PATTERNS:
            return True
    return False

def backup_database(db_path: Path) -> bool:
    bak_path = db_path.with_name(f"{db_path.name}.bak-nightly")
    try:
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
        dst = sqlite3.connect(str(bak_path), timeout=10.0)
        with dst:
            src.backup(dst, pages=100)
        dst.close()
        src.close()
        print(f"SQLite backup ok: {db_path} -> {bak_path}")
        return True
    except Exception as e:
        print(f"WARN: Failed to snapshot {db_path}: {e}", file=sys.stderr)
        return False

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <directory_path> [...]", file=sys.stderr)
        sys.exit(1)

    targets = [Path(p).resolve() for p in sys.argv[1:]]
    success_count = 0
    fail_count = 0

    for target in targets:
        if not target.exists():
            continue

        if target.is_file() and target.suffix in (".db", ".sqlite", ".sqlite3"):
            if backup_database(target):
                success_count += 1
            else:
                fail_count += 1
            continue

        for root, dirs, files in os.walk(target):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_PATTERNS]

            for f in files:
                f_path = root_path / f
                if f.endswith((".db", ".sqlite", ".sqlite3")):
                    if f.endswith(".bak-nightly"):
                        continue
                    if backup_database(f_path):
                        success_count += 1
                    else:
                        fail_count += 1

    print(f"Completed SQLite pre-backup: {success_count} succeeded, {fail_count} warnings/failures.")
    # Exit 0 even on partial warnings so overall backup does not crash
    sys.exit(0)

if __name__ == "__main__":
    main()
