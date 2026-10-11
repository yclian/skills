---
name: sync-antigravity-conversations
description: Synchronize and merge Antigravity conversations, transcripts, brain artifacts, project configurations, and summary databases from a source profile or backup archive into a target profile directory.
allowed-tools:
  - run_command
  - read_file
  - write_file
example-prompts:
  - "Sync my Antigravity conversations from my laptop backup zip into my local profile."
  - "Merge conversation transcripts and summary databases from a secondary profile directory."
related:
  - antigravity-extras
references:
  - title: "yclian/skills Repository"
    url: "https://github.com/yclian/skills"
  - title: "SQLite Write-Ahead Logging (WAL)"
    url: "https://www.sqlite.org/wal.html"
---

# Sync Antigravity Conversations

A reusable agent skill to copy and merge conversation logs, transcripts, brain artifacts, projects, and the local index files (`conversation_summaries.db`, `agyhub_summaries_proto.pb`, and `jetbox_summaries_proto.pb`) for **Antigravity** (Desktop, CLI, and IDE profiles) from a source profile directory or backup zip archive into a target profile directory.

## ⚠️ Important: Database Lock Warning
**Do NOT run this skill if the Antigravity desktop application is actively write-locking the workspace.**

Because the Antigravity application keeps the workspace databases (`.db` files) and summary index write-locked, running this script while the app is actively updating those databases will cause lock failures.

### Recommended Workflows:
1. **External Terminal**: 
   * Close the Antigravity desktop app.
   * Open your system terminal (PowerShell or CMD).
   * Run:
     ```bash
     python sync.py --source <source_path_or_zip> --target <target_path> --days 30
     ```
2. **Antigravity CLI**:
   * If running through the standalone Antigravity CLI tools outside of an active desktop GUI instance, database files are accessible and can be merged cleanly. Pass `--force` if needed to bypass process check.

---

## Requirements
* Python 3.8+ (uses built-in standard libraries: `sqlite3`, `zipfile`, `shutil`, `argparse`, `datetime`)

## Folder Structure
```
sync-antigravity-conversations/
├── SKILL.md
└── sync.py
```

## How It Works
1. **Source Flexibility**: Automatically detects if `--source` is a `.zip` archive (e.g. `gemini-aili.zip`), a full `.gemini` folder, or an individual profile directory (`antigravity`, `antigravity-cli`, `antigravity-ide`).
2. **Multi-Profile Sync**: Scans and syncs all present profiles under `.gemini` (`antigravity`, `antigravity-cli`, `antigravity-ide`), or operates on a single profile if explicitly targeted.
3. **Date Filtering**: Supports `--days <N>` and `--since <YYYY-MM-DD>` to selectively import conversations within a recent time window (e.g. last 30 days) using authoritative SQLite summary timestamps.
4. **Copies Conversation Files**: Copies `.pb` chat transcripts and `.db` workspace runs. For `.db` files that already exist in target, it attachment-merges SQLite tables without losing existing local runs.
5. **Syncs Brain Artifacts**: Recursively copies conversation task plans, transcripts (`transcript.jsonl`), checkpoints, and markdown artifacts from `brain/<conversation_id>/`.
6. **Syncs Annotations**: Copies corresponding `<conversation_id>.pbtxt` annotation files.
7. **Merges Summaries Database**: Merges rows into `conversation_summaries.db`, ensuring newly imported conversations appear directly in the Antigravity UI and history panels.
8. **Appends Protocol Buffer Index**: Appends the binary stream of conversation summaries to `agyhub_summaries_proto.pb` (for Antigravity desktop) or `jetbox_summaries_proto.pb` (for CLI).
9. **Copies Project Configurations**: Copies referenced project `.json` configurations from source `config/projects` to target `config/projects`.
10. **Automatic Backups**: Creates `.bak` copies before modifying target SQLite databases or protobuf indices.

## Script Arguments
* `--source`: Path to the source Antigravity profile directory or `.zip` archive (e.g., `gemini-aili.zip` or `C:\Users\username\.gemini-backup`).
* `--target`: Path to the target directory (default: `C:\Users\username\.gemini`).
* `--days`: (Optional) Integer. Only import conversations active/modified in the last N days (e.g., `--days 30`).
* `--since`: (Optional) ISO date string. Only import conversations active/modified on or after this date (e.g., `--since 2026-08-29`).
* `--dry-run`: (Optional) Simulate and report what will be imported without making any changes.
* `--force`: (Optional) Override running-app process check and execute anyway.

## Usage Examples

### Import only conversations from the last 30 days from a zip archive:
```bash
python sync.py --source "C:\Users\username\Downloads\gemini-aili.zip" --target "C:\Users\username\.gemini" --days 30
```

### Dry-run preview:
```bash
python sync.py --source "C:\Users\username\Downloads\gemini-aili.zip" --target "C:\Users\username\.gemini" --days 30 --dry-run
```
