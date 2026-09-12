---
name: antigravity-extras
description: Operational tribal knowledge, hidden internals, quirks, and runbooks for Google Antigravity / Antigravity 2.0 that the assistant does not natively know about itself. Covers persistent scheduled tasks (sidecars), application runtime lifecycle, profile architectures, and process quirks.
allowed-tools:
  - run_command
  - view_file
  - write_to_file
  - replace_file_content
---

# Antigravity Extras: The Self-Knowledge Gap

A living repository of tribal knowledge, runtime architecture, hidden internals, and operational runbooks for **Google Antigravity / Antigravity 2.0** that the agent does not natively know about itself from default prompt instructions.

Whenever you encounter behavior where Antigravity's host environment differs from standard prompt assumptions, refer to and update this skill.

---

## 1. Scheduled Tasks: Ephemeral `/schedule` vs. Persistent Sidecars

### The Pitfall
When a user asks to *"schedule a recurring prompt"* or runs `/schedule cron="..."`, agents typically default to calling the conversational `schedule` tool. 
- **What happens**: The agent spins an ephemeral in-conversation background timer (`<conversation-id>/task-N`).
- **Why it breaks**: It does **not** appear in the left-hand navigation under **Antigravity > Scheduled Tasks**, and any server restart, app reload, or machine sleep terminates it permanently.

### The Reality: Scheduled Tasks are Sidecars
Persistent, app-level scheduled tasks in Antigravity are implemented via the built-in **Sidecar** subsystem.

#### Configuration Structure
1. **Sidecar Definition File**:
   `~/.gemini/config/sidecars/<task-name>/sidecar.json`
   ```json
   {
     "builtin": "schedule",
     "args": [
       "<cron-expression>",
       "agentapi",
       "new-conversation",
       "<prompt-to-run>"
     ],
     "display_name": "<Display Title in UI>"
   }
   ```
2. **Registration in Config**:
   `~/.gemini/config/config.json` under `"sidecars"`:
   ```json
   {
     "sidecars": {
       "<task-name>": {
         "enabled": true,
         "projectId": "<project-uuid>"
       }
     }
   }
   ```
   *(The `projectId` maps to a registered project in `~/.gemini/config/projects/<uuid>.json`).*

#### Runtime Characteristics
- **Immediate Detection**: Antigravity's internal Go scheduler daemon (`schedule.go`) watches `config.json`. The moment a sidecar is registered or enabled, it starts a scheduler thread.
- **Timezone**: The 5-field cron expression is evaluated in the **machine's local time** (e.g. SGT / UTC+8).
- **Jitter**: The scheduler automatically calculates a jitter offset (e.g. 1–10 minutes) so tasks don't stampede the agent API at the top of the hour.
- **Verification Logs**: Checked at `~/.gemini/antigravity/sidecar_data/<task-name>/logs/<timestamp>.log`.

### Management CLI Utility
Use the included helper script:
```bash
# List all tasks
python scripts/task_manager.py list

# Add a persistent task
python scripts/task_manager.py add \
  --name "morning-standup-brief" \
  --display-name "Morning Standup Brief" \
  --cron "15 8 * * 1-5" \
  --prompt "Review my calendar and unread notifications and draft a standup summary."

# Check daemon status & next fire time
python scripts/task_manager.py status --name "morning-standup-brief"
```

---

## 2. Server Restarts & Background Task Lifecycle

When Antigravity reloads or restarts its backend server, it emits a system notice:
> `[Notice] All your subagents and background tasks have been stopped due to server restart.`

### What survives a restart:
- Registered **Sidecars** (persistent background schedulers).
- Project configurations in `~/.gemini/config/projects/`.
- Conversation transcripts in `~/.gemini/antigravity/brain/<convo-id>/.system_generated/logs/`.
- Brain artifacts and scratchpads.

### What is killed on restart:
- In-memory subagents (`invoke_subagent`).
- Conversational timers created via the agent `schedule` tool.
- Active background command executions (`run_command` daemon / async tasks).

---

## 3. Antigravity Filesystem & Profile Layout

On Windows, Antigravity splits state across `~/.gemini`:

| Path | Purpose |
| :--- | :--- |
| `~/.gemini/config/config.json` | Global settings, permission grants, and active sidecars. |
| `~/.gemini/config/projects/<uuid>.json` | Project configurations (workspace folder URIs, per-project permissions). |
| `~/.gemini/config/sidecars/<name>/` | Sidecar definitions (`sidecar.json`). |
| `~/.gemini/antigravity/sidecar_data/<name>/` | Runtime logs and data written by active sidecars. |
| `~/.gemini/antigravity/brain/<convo-id>/` | Chat history, artifacts, task logs, and transcripts. |
| `~/.gemini/antigravity/agyhub_summaries_proto.pb` | Serialized protobuf index of conversation summaries and desktop project state. |

---

## 4. File Locks & Safe Operations

- **Locked Files**: While the Antigravity desktop application is running, SQLite `.db` files and `agyhub_summaries_proto.pb` are write-locked by Electron. Direct writes to these files will fail with OS sharing violations (`os error 33`).
- **Profile Merging / Syncing**: If copying or merging conversations across profiles, refer to [`sync-antigravity-conversations`](../sync-antigravity-conversations/SKILL.md) and execute only when the app is closed or via an external terminal.

---

## 5. Adding New Knowledge to This Skill

When you discover new quirks or internal behavior not covered in system prompts:
1. Document the misconception vs. the actual implementation.
2. Provide file paths and reproduction evidence.
3. If applicable, add or update a CLI script under `scripts/`.
