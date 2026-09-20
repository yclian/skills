# Connector path — queries, budget, edge cases

The Gmail connector path is the one that matters: it is the only path that works
in an unattended scheduled run, because it needs no shell, no filesystem and no
local OAuth token.

## Call budget

**3–8 calls per run.** If you are about to exceed that, stop and re-read this file.

| Call | Count | Purpose |
| :-- | :-- | :-- |
| Q1 signal | 1–3 | Everything that might need the user |
| Q2 still-open | 1 | Unread internal threads carried from earlier days |
| Q3 suppressed | 0–1 | Honest pipeline count |
| `get_thread` | 0–5 | Disambiguate a genuinely unclear internal ask |

v1 of this skill made roughly 101 calls, because it listed message IDs and then
fetched metadata for each one. Do not reintroduce that: the minimal thread view
already carries every field the rules need.

## Window

Compute in `identity.timezone`, not UTC.

| Day | Window |
| :-- | :-- |
| Monday | `after:{the Saturday just past}` |
| Tue–Sat | `after:{yesterday}` |

Format `YYYY/MM/DD`. Gmail interprets a bare date as midnight in the account's
own timezone.

**Why day-granular rather than `newer_than:1d`.** Scheduled runs fire late — the
app was closed at 08:30 and opened at 10:00. A rolling 24-hour window would
silently drop 08:30–10:00. A date window over-includes by a few hours instead,
and the new-vs-carried marking absorbs the overlap honestly.

**Do not widen the window when results look sparse.** A quiet weekend is a real
answer. Widening would resurface Friday items the user already saw on Saturday.
Longer absences are handled interactively with `--since`.

## Q1 — signal

```
in:inbox after:{date}
  -category:promotions -category:social {each query.exclude}
  (from:{each internal_domain} OR {each query.include_extra})
```

- `pageSize: 50`, `view: THREAD_VIEW_MINIMAL`
- Paginate to at most **3 pages**. If a 4th `nextPageToken` exists, note
  truncation in the header rather than chasing it.
- MINIMAL returns per message: `id`, `sender`, `to_recipients`, `cc_recipients`,
  `date`, `label_ids`, `subject`, `snippet`. That is everything Step 5 needs.

## Q2 — still open

```
in:inbox is:unread older_than:1d newer_than:{still_open_days}d
  to:{identity.email}
  -category:promotions -category:social
  {each noise.pipeline_senders as -from:} {each aggregate.senders as -from:}
```

Unread **and addressed to the user** **and** older than a day is the zero-write
proxy for "surfaced before, still not actioned". Exclude any thread already in
Q1 client side. Render these in their own `⏳ Still open` section with
`(since {date})`.

This is how the brief avoids showing the user the same untouched thread as
"new" every morning for a week.

**`to:` is load-bearing, not optional.** An earlier draft of this query used
`(from:{internal_domain} OR is:important)` without it and returned a 201-thread
estimate — essentially the user's entire unread backlog, which is not the same
question. "Still open" means *someone is waiting on you*, and the sharpest
available proxy for that is being on the To line. Mail sent to a group alias the
user happens to be in is not someone waiting on the user.

High-volume automation senders are excluded here too: their backlog belongs in
the aggregated row in its own bucket, not repeated in this section.

## Q3 — suppressed count

```
in:inbox after:{date} from:{pipeline_senders joined by OR}
```

`view: THREAD_VIEW_METADATA_ONLY`, one page. Report the count, or `50+` if a
next page token exists. Skip entirely when
`report.show_suppressed_counts = false`.

**Why this exists.** v1 printed a suppression count computed client-side from
results the query had *already excluded server-side* — so it was near-always
zero and the number was decorative. Either count honestly or do not claim a
number.

## get_thread — the only per-thread call

Use `view: PLAIN_TEXT`, and only when **all** of these hold:

- the sender is an internal human (not a no-reply, not a system address), and
- the snippet does not settle whether something is being asked of the user, and
- the thread would land in Leadership or Team.

Hard cap 5 per run. Past the cap, mark the row `(unverified)` and move on. Never
open a thread in Digests, Security, or anything already classified as noise —
those buckets are decided by sender and keyword, and opening them buys nothing.

## Edge cases

**Threads resurface despite exclusions.** Gmail matches messages, then returns
their whole thread. A thread containing one promotional message and one real
message comes back even under `-category:promotions`. This is why Step 5 drops
noise client-side as well — and why the rule is *latest sender*, not any sender.

**Chat relays.** Google Chat mentions arrive from a no-reply relay address. The
real person is named in the subject. Extract them, render as
`{Person} (via Chat)`, and bucket as Team.

**A thread with no subject.** Render `(no subject)` rather than an empty cell.

**Sender display names containing a pipe.** Escape or replace it — a raw `|`
breaks the markdown table.

**Account mismatch.** If `identity.email` never appears in the `to` or `cc` of
any Q1 result, the connector may be bound to a different mailbox. Warn in the
header; do not abort — a user who is only ever Bcc'd is unusual but possible.

**Zero results.** Emit the empty state with real counts, never a bare "nothing
found" — the counts are what prove the query ran rather than failed.
