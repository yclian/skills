---
name: yclian-antigravity-sync-conversations
description: A tool/command to synchronize and merge Antigravity 2.0 app conversations, project configurations, and summaries from one source profile directory to a target profile directory.
allowed-tools:
  - run_command
  - read_file
  - write_file
---

# Sync Antigravity Conversations

A reusable agent skill to copy and merge conversation logs, transcripts, projects, and the local index file (`agyhub_summaries_proto.pb`) for the standalone **Antigravity 2.0** application from a source profile (e.g. backup or another machine) into a target profile.

## ⚠️ Important: Database Lock Warning
**Do NOT run this skill directly inside the active Antigravity desktop chat application.** 

Because the Antigravity application keeps the workspace databases (`.db` files) and the summaries index (`agyhub_summaries_proto.pb`) write-locked, running this script while the app is open will cause database lock failures.

### Recommended Workflows:
1. **External Terminal**: 
   * Close the Antigravity 2.0 app.
   * Open your system terminal (PowerShell or CMD).
   * Run:
     ```bash
     python sync.py --source <source_path> --target <target_path>
     ```
2. **Antigravity CLI**:
   * If running through the standalone Antigravity CLI tools outside of the active IDE instance, the database files are usually not locked, allowing safe operation.

---

## Requirements
* Python 3.x
* sqlite3 (built into Python)

## Folder Structure
```
sync-antigravity-conversations/
├── SKILL.md
└── sync.py
```

## How It Works
1. **Copies Project Configurations**: Copies `.json` project configurations from source to target `config/projects` folder.
2. **Copies/Merges Conversations**: Copies `.pb` chat transcripts. For workspace databases (`.db` files), it attachment-merges SQLite tables without losing existing local runs.
3. **Merges Index summaries**: Appends conversation summaries by concatenating the Protocol Buffer binary stream of `agyhub_summaries_proto.pb`.

## Script Arguments
* `--source`: Path to the source Antigravity folder (e.g., `C:\Users\username\.gemini-machine-a\antigravity`)
* `--target`: Path to the target Antigravity folder (e.g., `C:\Users\username\.gemini\antigravity`)
* `--force`: Override the running-app check and run anyway.

## Usage Instructions for the Agent
When requested to sync Antigravity conversations, the agent should:
1. Determine the source and target Antigravity directories.
2. Check if the Antigravity application is running.
3. **Instead of running it directly inside the app**, print the exact command the user needs to run externally, prompt them to close the app, and run it.
4. If the user explicitly asks to run it anyway, run the command with the `--force` flag.
