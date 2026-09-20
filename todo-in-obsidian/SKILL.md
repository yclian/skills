---
name: todo-in-obsidian
description: Review, triage, and carry forward TODOs across weekly journal notes in Obsidian. It runs a full backlog review with disposition codes (DAL, DSE, KIV, NIN...), effort estimates, delegability calls, and carry-forward into the new week's note. Use whenever the user wants to review weekly entries, do a backlog or TODO review, close out last week, carry over todos, triage open items, revive deferred (DLT) items, or plan the coming week from their journal. Trigger even on casual phrasing like "what's still open from last week", "clean up my todos", or "help me plan this week". Always requires access to the weekly journal folder — ask for it first.
metadata:
  version: 2.2.0
---

# Weekly TODO Management in Obsidian

Manage TODOs across weekly journal notes: gather every open item, triage each with a disposition code, estimate effort and delegability, decide item-by-item with the user, then close out old notes and carry deserving items into the new week. Obsidian (with the Tasks plugin's checkbox format) is the only assumed tooling; everything else — paths, filenames, section names — belongs to the user and must be discovered, not assumed.

## Step 0 — Get journal folder access (always)

This skill operates on the user's Obsidian journal folder, and you will **always** need access to it before doing anything else. Ask the user where their weekly journal lives and request access via the directory-access request tool (`mcp__cowork__request_cowork_directory` or equivalent) unless it is already mounted. Never assume a path from a previous session or from examples — vaults move, and different users keep them in different places.

## Step 1 — Learn the vault's conventions (first run, or when unsure)

Before extracting anything, sample a few recent notes and the vault's template to learn:

**Finding the template.** Never hardcode a template filename. Glob the output folder (the folder the new note will be written to) case-insensitively for `*template*.md` — this catches `_Template.md`, `Template.md`, `Weekly Template.md`, `template-weekly.md` and so on. Search the output folder first, then its parent, then any `Templates/` or `_templates/` sibling. If exactly one matches, use it. If several match, show the user the list and ask which one. If none match, derive the structure from the most recent existing note instead, and say so rather than inventing headings. Apply this same lookup everywhere a template is needed, including when creating a note for a future week.

Then learn:

- **Note naming pattern.** One note per ISO week is the norm, e.g. `Y26.W31 <journal title>.md` (year `YNN`, week `WNN`). Some notes span weeks (e.g. `W52-53`). Recent notes may sit at the folder root with older ones archived in subfolders (e.g. `Y24/`, `Y25/`). Derive the actual pattern from the files present; confirm with the user if ambiguous.
- **Section structure.** Find which headings hold TODOs. A typical template: `### Top priorities`, `### Other priorities`, occasionally `### Goal planning` or `### In progress / parallel`, plus meeting-notes sections (executives, team members, customers) where checkboxes get captured inline.
- **Week phrasing.** Refer to weeks as `YYYY.WNN` (e.g. `2026.W31`) in prose and reports.

Obsidian Tasks format: `- [ ] item` open, `- [x] item ✅ YYYY-MM-DD` done — the completion date is appended by the Tasks plugin; always append it when checking items programmatically.

## Disposition codes (prefixes)

Codes are written as `- [x] CODE | item ✅ date`. Checking the box strikes the item in Obsidian.

| Code | Meaning | Terminal? |
|---|---|---|
| DAL | Duplicated to another list — item copied elsewhere (usually the new week's note) | Yes here; lives on in the target list |
| DBO | Done elsewhere by others — resolved without the user's action | Yes |
| DLT | Deferred to a later time — parked deliberately; in reviews a few weeks later, detect DLT items and ask whether to revive | Soft; must be resurfaced |
| DSE | Delegated to someone else | Yes here; track delegate |
| GFN | Good for now | Yes |
| IMN | In motion now | No — active, leave open or note |
| KIV | Keep in view — parked, revisit later | Soft; resurfaces in reviews |
| NAN | No action needed | Yes |
| NFN | No further action needed (assumed completed) | Yes |
| NFE | Not feasible (to execute) | Yes |
| NIN | Not important now | Yes |
| NLR | No longer relevant | Yes |
| NQE | Not qualified for execution | Yes |

**DAL rule: never mark an item DAL without actually creating the duplicate in the target list in the same operation.** DAL means "this intent lives (or lived and was done) in another list" — it applies retroactively too, with a pointer link. NLR is strictly for items genuinely no longer relevant, with no successor anywhere.

## Review algorithm

1. **Gather**: read the last N weekly notes (default ~4 for routine reviews, 10 for deep reviews; ask if unspecified). Determine the current ISO week.
2. **Extract** all unchecked items; note source week and section. Also scan older notes for `DLT |` items closed in earlier reviews — list them separately and ask whether to revive.
3. **Trace repeats**: the same intent often reappears reworded across weeks (e.g. "Confirm system roles" → "Ship role clean-up" → "Resume role clean-up"). Merge into one item; age = weeks since first appearance. Age ≥ 3 weeks is a signal: either strategic-but-stuck (resume, make bounded) or not important (shelve).
4. **Classify** each item:
   - **Resume/start** — strategic or high priority. Signals: explicit exec/CEO ask; compliance or security exposure; blocks a stated FY ship goal; people obligations (reviews, feedback, kudos); repeatedly carried while still referenced elsewhere.
   - **Shelve** — assign a code: NIN (deprioritized), NLR (superseded/obsolete), KIV (blocked on a dependency — name it), NFE/NQE (can't be executed), NFN (probably already done), NAN/GFN (fine as-is).
   - **Quick wins** — batchable in one sitting; list separately.
5. **Estimate effort**: `quick` ≈ 1 hour · `small` ≈ half a day · `mid` ≈ half a week · `huge` ≈ a week.
6. **Assess delegability**: DSE items complete reliably when the task is bounded and well-specified. Convert vague "resume X" items into a bounded spec + DSE where possible. Judgment calls (roadmaps, budget/compliance decisions, people reviews, exec demos) stay with the owner.
7. **Present** one compact numbered list of all open items grouped by suggested disposition (resume/carry high, carry low, DSE, shelve, quick wins, DLT revivals, housekeeping) with effort + delegability columns. Reference weeks as `YYYY.WNN`.
8. **Decide per item with the user** — never strike or carry without confirmation. The user replies compactly by number ("3 DSE, 7 NIN, 12 done"). **Unanswered numbers are NOT consent** — confirm them explicitly before editing. In unattended/scheduled runs, produce the report and stop; edits happen only after the user replies.

## Close-out mechanics (after decisions)

For each decided item, in the **source (old) note**:

- Actually done (user confirms "done"): plain `- [x] <item> ✅ <today>` — no code.
- Carry forward: `- [x] DAL | <item> ✅ <today>` AND append `- [ ] <item>` to the new week's note under the matching section (high vs low priority; keep links and context, rewrite as a bounded action if the review produced one). If the target note doesn't exist yet, ask before creating it, and build it from the template found in Step 1 (the `*template*.md` lookup) rather than from memory of another vault.
- Delegate: `- [x] DSE | <item> ✅ <today>` — name the delegate in the item text if not obvious, and ensure the delegation actually happens (message/ticket).
- Shelve: `- [x] <NIN|NLR|KIV|NFE|NQE|NFN|NAN|GFN> | <item> ✅ <today>`. For KIV, note the unblocking condition.
- If an item repeats across several old notes, or is superseded by work tracked elsewhere, close **every** occurrence as `DAL` with a pointer, e.g. `→ tracked in [[<new week's note>]]`. When the carried item is retitled or merged, note the new title in the closed source item the same way.
- During per-item decisions the user may say "high"/"low": high → the top-priorities section, low → the other-priorities section in the target note. The user may also coin new codes mid-review — confirm the meaning, add them to this skill's taxonomy, then apply.

Edit rules: preserve original wording, links, and indentation of sub-items; only prepend the code, check the box, and append the ✅ date. Sub-checkboxes under a closed parent get closed with it unless still independently live.

## Learned conventions & pitfalls

- **TODOs hide outside the priority sections.** Checkboxes appear under meeting-notes headings (execs, team members, customers — asks captured mid-meeting) — scan the whole note, not just the priorities block.
- **Exec asks are a priority signal.** An item attributed to the CEO/executives (e.g. a `<Name>>` prefix quoting them) defaults to resume/high unless the user says otherwise.
- **FY-level goal blocks are not weekly items.** Sections like `### Goal planning` hold quarter/year goals — leave them out of weekly carry-forward; they belong in goal docs. Do note when a weekly item is the execution of one of them.
- **Indentation is inconsistent** (`- [ ]` vs ` - [ ]`) between and within notes — when editing, match and preserve the exact original whitespace; never reformat.
- **Hidden Unicode characters lurk in pasted blocks** (e.g. non-breaking spaces inside `[ ]` checkboxes in AI/web-pasted lists). They render as normal spaces but break exact-match edits. If an edit fails on a line that looks right, retry with a short anchor that skips the checkbox, or match using U+00A0 in the brackets. When verifying with regex, use `- \[[^x]\]` (not `- \[ \]`) so NBSP checkboxes are caught.
- **Deeply indented sub-items**: don't guess the tab/space mix — anchor the match on the unique text after `- [ ]` instead of leading whitespace.
- **Verify after editing**: grep the touched notes with `- \[[^x]\]` to confirm only deliberately-open items remain; report leftovers. Also watch for stray `- [ ]` prefixes on non-TODO lines (e.g. a pasted code fence) — these are formatting bugs to strip, not items to triage.
- **Sync awareness.** Vaults commonly sync (Google Drive, iCloud, Obsidian Sync) and may change on disk mid-session, leaving conflict files like `(conflict 2025-03-31...)`. Expect anchors to shift; re-read before dependent edits and mention conflict files to the user rather than editing them.
- **Note-per-week gaps exist** (skipped weeks, spans like `W46-48`) — when the user gives a week range, list which notes actually exist and flag gaps.

## Leadership guardrails

Delegation and shelving affect people — clear is kind: when DSE-ing, spec the outcome, not the method; when shelving someone's request, tell them. People-related items (feedback, performance reviews, kudos, 1:1s) are never shelved silently and never delegated.
