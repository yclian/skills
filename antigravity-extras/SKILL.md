---
name: antigravity-extras
description: Operational tribal knowledge, hidden internals, quirks, and runbooks for Google Antigravity / Antigravity 2.0 that the assistant does not natively know about itself. Covers persistent scheduled tasks (sidecars), browser automation (/browser) CDP boot-up and security quirks, application runtime lifecycle, profile architectures, and process quirks.
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

## 4. Browser Automation (`/browser`): Chrome DevTools Protocol (CDP) & Profile Isolation Quirks

### 4.1 Subagent Architecture
When a user issues the `/browser` slash command, Antigravity spawns an autonomous subagent with `typeName: "browser"` (Role: `Browser Automation Agent`).
The agent connects over Chrome DevTools Protocol (CDP) at `http://127.0.0.1:9222` to attach to open windows, capture screenshots, evaluate DOM selectors, and inspect network traffic.

### 4.2 The Critical Pitfall: Chrome's Silent Security Suppression
When booting Chrome for remote debugging, agents and developers frequently run:
```bash
chrome.exe --remote-debugging-port=9222
```
**Why it fails silently**:
1. Chrome's Chromium security sandbox **refuses to open `--remote-debugging-port` on the default user profile directory** (`%LOCALAPPDATA%\Google\Chrome\User Data`).
2. If another standard Chrome window is already open under that profile, or if launched without an explicit isolated profile directory, Chrome simply attaches to the existing process.
3. To protect saved credentials, personal cookies, and OAuth tokens from local malware, Chrome **silently suppresses `--remote-debugging-port`**.
4. A normal browser window appears, but port `9222` remains closed (`Connection refused`). Diagnostic checks (`Test-NetConnection -Port 9222` or `curl http://localhost:9222/json`) fail completely.

### 4.3 The Solution: Mandatory `--user-data-dir`
Chrome **strictly mandates** an isolated profile directory to activate remote debugging:
```powershell
& "C:\Program Files\Google\Chrome Beta\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$HOME\.chrome-debug"
```
- **Process Isolation**: Spawns an independent process tree that binds `127.0.0.1:9222` immediately.
- **Session Persistence**: Because `$HOME\.chrome-debug` is persistent on disk, logins (e.g. store admin dashboards, SaaS apps) completed inside this window are preserved across sessions. You only need to authenticate once.

### 4.4 The Antigravity Subagent Discovery Hook: `DevToolsActivePort`
Antigravity's built-in `chrome_devtools` tool in the `browser` subagent does **not** rely solely on probing `http://127.0.0.1:9222`. On Windows, it performs filesystem discovery by reading:
`C:\Users\<user>\AppData\Local\Google\Chrome\User Data\DevToolsActivePort`

**File Format**:
```text
<port>
<browser_context_path>
```
*Example:*
```text
9222
/devtools/browser/7c98bcae-2ab1-4ed1-9c78-68cf5d6fb04d
```

**The Subagent Disconnect Failure Mode**:
1. When you run Chrome Beta, or run Chrome with an isolated profile (`--user-data-dir="~/.chrome-debug"`), Chrome does not write `DevToolsActivePort` to standard `Google\Chrome\User Data`.
2. When launched with an explicit port like `--remote-debugging-port=9222`, Chrome does not dynamically write this file.
3. If `AppData\Local\Google\Chrome\User Data\DevToolsActivePort` is missing or contains a **stale browser session UUID**, the subagent's `chrome_devtools` tool immediately fails with:
   > `Could not find DevToolsActivePort for chrome at C:\Users\<user>\AppData\Local\Google\Chrome\User Data\DevToolsActivePort`
4. **The Fix**: The active port and live browser context path from `http://127.0.0.1:9222/json/version` must be synchronized into `DevToolsActivePort` in `%LOCALAPPDATA%\Google\Chrome\User Data` (handled automatically by `python scripts/browser_debug.py sync` or `launch`).

### 4.5 Binary Selection: Chrome Beta vs. Chrome Stable
In many developer environments, **Chrome Beta** is preferred for debugging and testing to keep developer tools and experimental configurations separate from standard browsing:
- **Chrome Beta (Windows)**: `C:\Program Files\Google\Chrome Beta\Application\chrome.exe`
- **Chrome Stable (Windows)**: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- **Edge (Windows Fallback)**: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`

> [!WARNING]
> Always verify which binary the user intended to use. Never launch Chrome Stable if the user has requested Chrome Beta.

### 4.6 Anti-Patterns & Common Traps
1. **Never Create Symlinks in Chrome or DevTools Directories**:
   - DevTools Protocol is built natively into the Chromium binary.
   - Creating filesystem junctions or symlinks (e.g. trying to link devtools folders) risks breaking auto-updates and corrupting Chrome's installation.
2. **`chrome://inspect` URL Trap**:
   - The correct Chrome internal URL for inspecting remote targets and devices is `chrome://inspect/#devices`.
   - Navigating to `chrome://inspect/#remote-debugging` produces an empty or invalid view.
3. **Orphan Background Processes**:
   - If port 9222 remains locked after closing the visible browser window, a background Chrome child process or headless worker may still be lingering. Check with `Get-Process chrome` or `netstat -ano | findstr 9222`.

### 4.7 Verification Runbook
```powershell
# 1. Verify port 9222 is listening
Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue

# 2. Check CDP metadata endpoint
(Invoke-RestMethod -Uri "http://localhost:9222/json/version").Browser

# 3. List inspectable open tabs
(Invoke-RestMethod -Uri "http://localhost:9222/json/list") | Select-Object title, url
```

### 4.8 Helper CLI Script (`browser_debug.py`)
Use the included helper script under `scripts/`:
```bash
# Check if CDP port is open and report connected browser info
python scripts/browser_debug.py status

# Synchronize live WebSocket context path into DevToolsActivePort for Antigravity subagent
python scripts/browser_debug.py sync

# List inspectable pages and tabs
python scripts/browser_debug.py list-tabs

# Scan for installed browser binaries across system
python scripts/browser_debug.py find-browsers

# Launch Chrome Beta with isolated profile, verify port, and auto-sync DevToolsActivePort
python scripts/browser_debug.py launch --channel beta
```

---

## 5. File Locks & Safe Operations

- **Locked Files**: While the Antigravity desktop application is running, SQLite `.db` files and `agyhub_summaries_proto.pb` are write-locked by Electron. Direct writes to these files will fail with OS sharing violations (`os error 33`).
- **Profile Merging / Syncing**: If copying or merging conversations across profiles, refer to [`sync-antigravity-conversations`](../sync-antigravity-conversations/SKILL.md) and execute only when the app is closed or via an external terminal.

---

## 6. Adding New Knowledge to This Skill

When you discover new quirks or internal behavior not covered in system prompts:
1. Document the misconception vs. the actual implementation.
2. Provide file paths and reproduction evidence.
3. If applicable, add or update a CLI script under `scripts/`.
