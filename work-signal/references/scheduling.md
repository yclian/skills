# Scheduling the morning run

The scheduled run uses the **Gmail connector path**. It cannot use the Node CLI:
a scheduled run has no shell on the host, and the sandbox it does have cannot
reach your filesystem or your OAuth token.

## The task

| Field | Value |
| :-- | :-- |
| taskId | `work-signal-0830` |
| title | `Work Signal · Mon–Sat 08:30` |
| cron | `30 8 * * 1-6` |
| timezone | local — cron is evaluated in the user's timezone, not UTC |
| notify on completion | true |

`1-6` is Monday through Saturday. For weekdays only, use `1-5`.

## The prompt, verbatim

Each run starts with no memory of the conversation that created it, so the
prompt is self-contained.

```
UNATTENDED RUN - Work Signal morning brief. No one is watching this session.
Do not ask questions, do not offer connector or setup cards, do not create or
modify scheduled tasks, do not label, archive, draft, or send anything. Read-only.
Output goes to this chat only, as markdown. No HTML artifact, no files.

1. Load the `work-signal` skill and follow its Unattended mode on the Gmail
   connector path (tools: search_threads, get_thread). If the skill cannot be
   loaded, output exactly: "Work Signal could not run: work-signal skill not
   found - republish it with node build/publish-cowork.mjs" and stop.
2. Mailbox: {identity.email}. Timezone: {identity.timezone}.
   Write weeks as ISO weeks, e.g. 2026.W38.
3. Window: if today is Monday, Gmail `after:` last Saturday's date; otherwise
   `after:` yesterday's date (format YYYY/MM/DD).
4. If the Gmail connector errors or is disconnected, output one line starting
   "Work Signal could not run:" with the error and the fix (reconnect Gmail
   under Settings > Connectors, then run /work-signal). Never present an error
   as an empty inbox.
5. If nothing needs attention, output the skill's empty state with scanned and
   suppressed counts so it is clear the run succeeded.
```

**The prompt deliberately carries no copy of the query, the buckets or the noise
lists.** That would be another copy of the logic, drifting from the config the
moment either changed. If the skill cannot be loaded, the run fails loudly
instead of quietly running a stale duplicate.

## Publishing to an assistant with its own skill store

Some assistants (Claude's Cowork mode among them) load skills from their own
store rather than from your filesystem, and accept only a single self-contained
`SKILL.md` — no `config/`, no `references/`. A scheduled run there cannot read
`work-signal.local/signal.toml` at all.

`build/publish-cowork.mjs` handles this: it reads the skill, the references and
your private config, and emits one self-contained document with the taxonomy
inlined and the version stamped in.

```bash
node build/publish-cowork.mjs > /tmp/work-signal.cowork.md
```

Then save that as the skill named `work-signal` in the assistant's store.

The generated file contains your real names and addresses. It goes only to your
own account. **Never publish it anywhere shared.**

### Publish checklist

Run this whenever the config or the skill changes — a saved copy does not update
itself, and a stale one fails silently.

1. Bump `[meta] version` in `signal.toml` and the version line in `SKILL.md`
2. Commit the shareable half
3. `node build/publish-cowork.mjs`
4. Save the output as the `work-signal` skill (overwrite)
5. Run `/work-signal` once interactively
6. **Check the footer version matches what you just set** — this is the whole
   point of the version stamp

## Risks of an unattended run

| Risk | What happens | Mitigation |
| :-- | :-- | :-- |
| Connector OAuth expired | Would otherwise render as "nothing needs you" | Prompt rule 4 forces a failure line. An empty inbox and a broken connector must never look alike |
| App closed at 08:30 | Task runs on next launch | The day-granular window means a late run loses nothing that day. Past midnight the day is lost — the `⏳ Still open` section catches the carry-over next morning |
| Skill not loaded | Would otherwise improvise a brief from nothing | Prompt rule 1 makes it fail by name |
| Stale published copy | Runs against last month's taxonomy | Version stamp in the footer |
| Sudden volume spike | Q1 truncates at 3 pages | Truncation is noted in the header, not hidden |
| **Tool permission prompt** | An unattended run pauses forever waiting for an approval nobody is there to give | **Click "Run now" on the task once, from the Scheduled sidebar.** Approvals granted during a run are stored on the task and reused by later runs. Do this before trusting the first real 08:30 fire — it is the single most likely cause of a silent no-show |

## Verifying it actually works

Creating the task is not evidence it runs. Before trusting it:

1. Create a **one-shot** task with `fireAt` 15 minutes out, same prompt, a
   throwaway taskId.
2. Watch where the output appears and confirm it is a complete brief or a
   proper empty state — and that it asks no questions and offers no cards.
3. Delete the throwaway task.
4. Only then create the recurring one.

The Monday window is the one thing a dry run cannot prove, because it only
differs on a Monday. Check the first Monday brief: its window should start on
the previous Saturday, and the header should say so.
