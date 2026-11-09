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
| **Named gcloud profile (e.g. work, personal)** | `--profile NAME` on `start`, `finish` **and** `status` | Runs under `~/.config/gcloud/NAME`: sets `CLOUDSDK_CONFIG` and `GOOGLE_APPLICATION_CREDENTIALS` |

**Profiles.** If the user keeps one gcloud folder per account (`~/.config/gcloud/<name>`, root overridable with `GCLOUD_PROFILES_ROOT`), pass the same `--profile <name>` to all three steps whenever the user names an account other than the one the session started with (for example "sign in personal"). Without it, the script follows whatever `CLOUDSDK_CONFIG` the agent inherited. Each profile keeps its own session folder, so a pending personal sign-in survives a new work sign-in. Never set only `CLOUDSDK_CONFIG` by hand: `status` checks ADC through `GOOGLE_APPLICATION_CREDENTIALS` and would report the other profile.

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

---

## Step 4: Fallback for OAuth Clients Requiring Localhost Redirect (`ssh -L 8085`)

When authenticating headless tools (`gog auth`, newer `gcloud` OAuth client flows, or Workspace OAuth credentials) where Google's OAuth endpoint rejects out-of-band copy-paste verification codes (`redirect_uri=http://localhost:<PORT>` required):

1. **Never use deprecated `--no-browser` flags** on tools that require a loopback HTTP callback listener.
2. **Use SSH Localhost Port Forwarding** from the interactive workstation (`Aili` / `Suzu`) to the headless host (`Arwen` / `Adara`):
   ```bash
   # 1. Start the OAuth login listener on the remote headless host (captures the ephemeral localhost port, e.g. 8085)
   # 2. From the local workstation with a logged-in browser, forward that exact localhost port:
   ssh -N -L 8085:127.0.0.1:8085 yclian@arwen.dikdik-dojo.ts.net
   ```
3. Open the emitted `https://accounts.google.com/o/oauth2/auth?...&redirect_uri=http://localhost:8085/...` URL in the local workstation browser. Upon consent, the browser redirects to `localhost:8085`, which tunnels through SSH directly into the remote CLI's loopback listener and completes token exchange cleanly.
