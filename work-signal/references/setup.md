# Setup

Two ways to run this. Pick one; you do not need both.

| | Gmail connector | Node CLI |
| :-- | :-- | :-- |
| Works in a scheduled/unattended run | **yes** | no |
| Needs a shell | no | yes |
| Needs your own OAuth client | no | yes |
| Setup time | a minute | twenty minutes |

If you use Claude with a Gmail connector, use the connector. The CLI exists for
terminal agents and for people whose assistant has no mail connector.

## Config, either way

```
<skills-root>/work-signal/            the skill
<skills-root>/work-signal.local/      your config — create this
    signal.toml
```

Copy `config/signal.example.toml` to `../work-signal.local/signal.toml` and edit.
At minimum set `[identity] email`, `internal_domains` and `timezone`, then add
the people whose mail always matters to `[buckets.leadership] senders`.

The `.local` directory deliberately has **no SKILL.md**. That keeps it from
being discovered as a skill of its own, and stops it shadowing this one by name.
Keep it out of version control — it holds real names and addresses.

To put it elsewhere, set `$WORK_SIGNAL_CONFIG` to the file path.

### Tuning it

The lists are meant to be edited over the first week or two. When the brief
surfaces something that was not worth surfacing, say "that's noise" — the skill
will propose the exact TOML line, with a `# YYYY.WNN` comment recording when and
why. Accept it, or do not.

Prune the other direction quarterly: a vendor sender that has not appeared in
the suppressed count for a quarter is dead weight.

## Path A — Gmail connector

1. Connect Gmail in your assistant's connector settings.
2. Create the config as above.
3. Run `/work-signal`.

Check the footer of the first brief: it names the path, the config version and
the call count. A call count above 8 means something is wrong — see
`references/connector-path.md`.

For the scheduled morning run, see `references/scheduling.md`.

## Path B — Node CLI

**Requirements:** Node 18 or newer (for global `fetch`).

```bash
cd <skills-root>/work-signal
npm install          # one dependency: smol-toml
```

**Google OAuth client:**

1. Create or pick a Google Cloud project.
2. Enable the **Gmail API**.
3. Create an OAuth client ID of type **Desktop app**.
4. Download the JSON and save it as `~/.config/work-signal/credentials.json`
   (or wherever `[auth] dir` / `$WORK_SIGNAL_AUTH_DIR` points).

**Scope:** `https://www.googleapis.com/auth/gmail.readonly` — read-only, and
that is all this skill ever needs. If a future version adds labelling, it will
ask for `gmail.modify` explicitly and tell you why.

**Authorise once:**

```bash
node src/work-signal.mjs --auth
```

This opens a browser, completes the loopback flow on `127.0.0.1`, and writes
`token.json` beside the credentials. Later runs refresh silently.

**Network:** outbound HTTPS to `oauth2.googleapis.com` and `gmail.googleapis.com`.

**Test:**

```bash
node src/work-signal.mjs --days 2 --format md
```

### Flags

| Flag | Effect |
| :-- | :-- |
| `--days N` | Override the window, in days |
| `--since YYYY-MM-DD` | Absolute window start — use after time away |
| `--as-of YYYY-MM-DD` | Pretend today is this date. For testing Monday logic on a Wednesday |
| `--unread` | Restrict to unread |
| `--format json\|md` | `json` feeds an agent's judgement pass; `md` is human-readable |
| `--auth` | Run the OAuth flow and exit |
| `--config PATH` | Explicit config path |

## Note on `npx`

`npx github:user/repo` needs the repository root to be the package, so it does
not work while this skill is a subdirectory of a multi-skill repo. Clone and run
`node src/work-signal.mjs`. If the CLI ever gets its own repository, `npx` comes
for free.

## Troubleshooting

**"Config not found"** — the engine looked at `$WORK_SIGNAL_CONFIG`, then
`../work-signal.local/signal.toml`, then the bundled example. Check you created
the `.local` directory *beside* the skill, not inside it.

**Brief is empty but the inbox is not** — check the footer's scanned count. If it
is zero, the query matched nothing: your `internal_domains` is probably wrong, or
`[query] exclude` is too aggressive.

**Everything lands in Team** — your bucket sender lists are empty, or written as
bare substrings. Senders must be `local-part@`, a full address, or `@domain`.

**An unrelated colleague keeps appearing in Leadership** — a sender rule is too
loose. `"sam"` is not a rule; `"sam.patel@"` is.
