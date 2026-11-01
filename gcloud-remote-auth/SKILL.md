---
name: gcloud-remote-auth
description: >-
  Re-authenticate Google Cloud CLI (`gcloud`) and Application Default Credentials (ADC)
  in remote, SSH, container, or headless sessions where the agent shell has no interactive
  stdin. Use when `/gcloud-remote-auth` is invoked, when the user asks for a gcloud login
  link, or whenever `gcloud`, `bq`, `dataform`, Terraform, or Google Cloud SDKs fail with
  expired credentials, `Reauthentication required`, or `DefaultCredentialsError`.
---

# GCloud Remote Auth (`gcloud-remote-auth`)

Non-interactive two-step `gcloud` and Application Default Credentials (`ADC`) login workflow for AI agents running on remote hosts, containers, or shells that cannot pipe interactive `stdin` into a running process.

> **Never refuse `--no-launch-browser` due to non-interactive stdin**:
> When `gcloud` or ADC credentials expire, do **not** tell the user *"my shell has no input to type into, run `! gcloud` yourself"* and do **not** abandon live verification. Run [`scripts/gcloud_remote_auth.py`](./scripts/gcloud_remote_auth.py) using the three-step sequence below so the user gets a clickable OAuth link directly in chat.

## Routing & Mode Selection

| Scenario | Flag to pass to `start` | Underlying `gcloud` Command |
| :--- | :--- | :--- |
| **Default (Both `gcloud` CLI + ADC)** | *(none)* | `gcloud auth login --update-adc --no-launch-browser --quiet` |
| **Specific Google Account** | `--account user@domain.com` | Adds `--account=user@domain.com` |
| **ADC Only (Preserve separate CLI account)** | `--adc-only` | `gcloud auth application-default login --no-launch-browser --quiet` |
| **BigQuery Federated Google Drive / Sheets** | `--enable-gdrive-access` | Adds `--enable-gdrive-access` |

---

## Step 1: Start Session & Drop the OAuth Link

Resolve `<SKILL_DIR>` to the directory containing this `SKILL.md` file (for example `~/.agents/skills/gcloud-remote-auth` or `~/.claude/skills/gcloud-remote-auth`), and run `start`:

```bash
python "<SKILL_DIR>/scripts/gcloud_remote_auth.py" start
```
*(If `python` is not on `PATH` on macOS/Linux, use `python3`).*

**Completion Criteria for Step 1**:
1. Command exits with code `0` and outputs a line matching `AUTH_URL: https://accounts.google.com/...`.
2. Present the exact URL to the user as a clickable Markdown link in chat.
3. Ask the user to open the link in their local browser, complete Google sign-in, and paste the verification code back in chat. Stop and wait for the user's reply.

---

## Step 2: Complete Login with the Verification Code

When the user replies with the single-use verification code from their browser, pass it to `finish` via standard input (or single quotes so shell metacharacters are never expanded):

```bash
printf '%s' '<VERIFICATION_CODE>' | python "<SKILL_DIR>/scripts/gcloud_remote_auth.py" finish --stdin
```

**Completion Criteria for Step 2**:
- **If exit code is `0`**: Both `gcloud` and ADC credentials are saved and the temporary `~/.cache/gcloud-remote-auth` session files (`code.txt`, `out.log`, `worker.pid`) are automatically purged. Proceed immediately to **Step 3**.
- **If exit code is non-zero** (for example, the code was mistyped, expired, or the background worker timed out after 10 minutes):
  - The single-use PKCE `gcloud` process has terminated and cannot accept another code.
  - Run **Step 1 (`start`)** again to generate a fresh `AUTH_URL` and provide the new link to the user.

---

## Step 3: Verify CLI & ADC Token Health

Always verify that both `gcloud` CLI and Application Default Credentials can mint live access tokens before resuming the user's original task:

```bash
python "<SKILL_DIR>/scripts/gcloud_remote_auth.py" status
```

**Completion Criteria for Step 3**:
- Command exits with code `0` and confirms both `OK: gcloud CLI access token is valid and active` and `OK: Application Default Credentials (ADC) token is valid and active`.
- Once verified, immediately resume the original `gcloud` / `bq` / database inspection task that triggered the re-authentication.
