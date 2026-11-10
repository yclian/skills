---
name: todo-in-obsidian
description: Review, triage, and carry forward TODOs across weekly journal notes in Obsidian. It runs a full backlog review with disposition codes (DAL, DSE, KIV, NIN...), effort estimates, delegability calls, a recommended disposition per item, bulk-accept, carry-forward into the new week's note, and delegation check-ins. Use whenever the user wants to review weekly entries, do a backlog or TODO review, close out last week, carry over todos, triage open items, revive deferred (DLT) items, check on delegated items, or plan the coming week from their journal. Trigger even on casual phrasing like "what's still open from last week", "clean up my todos", "run through last week and carry over", or "help me plan this week". Always requires access to the weekly journal folder - ask for it first.
metadata:
  version: 2.3.0
example-prompts:
  - "What's still open from last week's journal? Help me triage and roll over my TODOs."
  - "Close out last week's Obsidian note and plan this week's backlog."
  - "Check whether my delegated items have moved and nudge the ones that haven't."
related:
  - work-signal
  - calendar-tbd-recommender
references:
  - title: "Obsidian Tasks Plugin Documentation"
    url: "https://publish.obsidian.md/tasks/"
  - title: "yclian/skills Repository"
    url: "https://github.com/yclian/skills"
---

# Weekly TODO Management in Obsidian

This skill manages TODOs across weekly journal notes. Gather every open item, research it, and recommend a disposition for each. Let the user accept the recommendations in bulk or override them item by item, then close out the old notes and carry the live items into the new week.

Obsidian, with the Tasks plugin's checkbox format, is the only assumed tooling. Everything else belongs to the user and must be discovered, not assumed: paths, filenames, section names, trackers and people.

## Step 0 — Access and overlay (always)

1. **Journal folder.** You will always need access to the user's journal folder before doing anything else. Ask where it lives and request access with the directory-access tool (`mcp__cowork__request_cowork_directory` or equivalent), unless it is already mounted. Never assume a path from a previous session or from an example.
2. **User overlay.** Look for a personal overlay skill, conventionally named `todo-in-obsidian.local` or `<user>-weekly-todos.local.md`. An overlay binds this engine to one vault and holds the user's sections, shorthand, trackers, people and consent defaults. Read it after this file. **The overlay wins over this file, and what is actually on disk wins over both.**

## Step 1 — Learn the vault's conventions (first run, or when unsure)

Before extracting anything, sample a few recent notes and the vault's template.

**Finding the template.** Never hardcode a template filename. Glob the output folder (the folder the new note will be written to) case-insensitively for `*template*.md`. This catches `_Template.md`, `Template.md`, `Weekly Template.md`, `template-weekly.md` and similar.
- Search the output folder first, then its parent, then any `Templates/` or `_templates/` sibling.
- If exactly one file matches, use it. If several match, show the user the list and ask which one.
- If none match, derive the structure from the most recent existing note, and say so rather than inventing headings.

Apply this same lookup wherever a template is needed, including when creating a note for a future week.

Then learn:

- **Note naming pattern.** One note per ISO week is the norm, e.g. `Y26.W31 <journal title>.md` (year `YNN`, week `WNN`). Some notes span weeks (e.g. `W52-53`). Recent notes may sit at the folder root, with older ones archived in subfolders (e.g. `Y24/`, `Y25/`). Derive the actual pattern from the files present, and confirm with the user if it's ambiguous.
- **Section structure.** Find which headings hold TODOs. A typical template has `### Top priorities` and `### Other priorities`, sometimes `### Goal planning` or `### In progress / parallel`. Meeting-notes sections (executives, team members, customers) also collect checkboxes inline.
- **Working-state sections.** Blocks such as `## Sessions` or `### Cursors` hold resume commands and scratch state. They are not TODOs. See "Learned conventions".
- **Linked material.** Folders like `Dispatch/` or `Attachments/` are not weekly notes, but items often wikilink into them (breakdowns, specs, drafts). Follow those links.
- **Week phrasing.** Refer to weeks as `YYYY.WNN` (e.g. `2026.W31`) in prose and reports.

Obsidian Tasks format: `- [ ] item` is open and `- [x] item ✅ YYYY-MM-DD` is done. The Tasks plugin appends the completion date, so always append it when checking items programmatically.

## Disposition codes (prefixes)

Codes are written as `- [x] CODE | item ✅ date`. Checking the box strikes the item through in Obsidian.

| Code | Meaning | Terminal? |
|---|---|---|
| DAL | Duplicated to another list — the item was copied elsewhere, usually to the new week's note | Yes here; lives on in the target list |
| DBO | Done elsewhere by others — resolved without the user's action | Yes |
| DLT | Deferred to a later time — parked deliberately; detect DLT items in reviews a few weeks later and ask whether to revive them | Soft; must be resurfaced |
| DSE | Delegated to someone else | Yes here; track the delegate |
| GFN | Good for now | Yes |
| IMN | In motion now | No — active; leave open or add a note |
| KIV | Keep in view — parked, revisit later | Soft; resurfaces in reviews |
| NAN | No action needed | Yes |
| NFN | No further action needed (assumed completed) | Yes |
| NFE | Not feasible (to execute) | Yes |
| NIN | Not important now | Yes |
| NLR | No longer relevant | Yes |
| NQE | Not qualified for execution | Yes |

**DAL rule: never mark an item DAL without creating the duplicate in the target list in the same operation.** DAL means "this intent lives, or lived and was done, in another list". It also applies retroactively, with a pointer link. NLR is strictly for items that are genuinely no longer relevant and have no successor anywhere.

## Review algorithm

1. **Gather.** Read the last N weekly notes: about 4 for a routine review, 10 for a deep one; ask if the user hasn't said. Determine the current ISO week. If a calendar is connected, read the target week first to build the week context: travel, PTO, events and hard deadlines. Request events in the user's time zone, and ignore personal or recurring placeholder blocks. List which notes exist and flag any gaps.
2. **Extract** every unchecked item, scanning the whole note, and record its source week and section. Also scan older notes for `DLT |` items closed in earlier reviews, list them separately, and ask whether to revive them.
3. **Research before asking.** Collect evidence for each item before classifying it:
   - follow its wikilinks, including into `Dispatch/`-style folders;
   - read the text around it in the note (a bare "Goals" line may be explained two lines up);
   - check the current status of any ticket key;
   - search connected chat, mail or memory for the item's keywords.

   Ask the user only when all of that comes up empty, and say what you checked ("no ticket, nothing in Dispatch, no chat hits — what is this?").
4. **Trace repeats.** The same intent often reappears reworded across weeks ("Confirm system roles" → "Ship role clean-up" → "Resume role clean-up"). Merge these into one item; its age is the number of weeks since it first appeared. An age of 3 weeks or more is a signal: the item is either strategic but stuck (resume it and make it bounded) or not important (shelve it).
5. **Classify** each item:
   - **Resume/start** — strategic or high priority. Signals: an explicit exec or CEO ask; compliance or security exposure; it blocks a stated FY ship goal; it is a people obligation (reviews, feedback, kudos); someone is waiting on the user's decision; it keeps being carried while still referenced elsewhere.
   - **Shelve** — assign a code: NIN (deprioritized), NLR (superseded or obsolete), KIV (blocked on a dependency — name it), NFE/NQE (can't be executed), NFN (probably already done), NAN/GFN (fine as it is). An external ask more than 6 months old with no movement defaults to a proposed NLR.
   - **Quick wins** — batchable in one sitting; list them separately.
6. **Estimate effort**: `quick` ≈ 1 hour · `small` ≈ half a day · `mid` ≈ half a week · `huge` ≈ a week.
7. **Assess delegability.** Delegated items get done reliably when the task is bounded and well specified. Where possible, turn a vague "resume X" into a bounded spec plus a DSE. Judgment calls (roadmaps, budget or compliance decisions, people reviews, exec demos) stay with the owner; the delegate can prepare the options.
8. **Present** one compact numbered list of every open item, grouped by suggested disposition: carry high, delegate, carry low, shelve, quick wins, new for the week, DLT revivals, housekeeping.
   - **Every line carries a recommendation:** `n. item · age · effort · owner · → CODE + target section/day`.
   - Split big parents as 1a, 1b, 1c.
   - Mark a line `?` only when research turned up nothing, and give it a one-line question.
   - Flag "X is waiting on you" explicitly.
9. **Decide.** Consent is always explicit, but it can come in bulk:
   - **Per item:** the user replies by number ("3 DSE, 7 NIN, 12 done").
   - **Bulk-accept:** "run", "go", "apply" or "accept all" applies every line that has a recommendation. The user can add exceptions by number ("run, except 8 NIN"). `?` lines are never applied by a bulk-accept; they stay open in the source note.
   - **Silence is not consent.** Unanswered numbers stay open.
   - **Always need an explicit, item-specific yes:** messages sent to people, new tickets in shared trackers, and deletions. An instruction like "remind them" or "Jira it for X" counts as that yes.
   - **Unattended or scheduled runs** produce the report and stop. The only exception is creating the new week's note skeleton, when the overlay pre-authorizes it.

## Close-out mechanics (after decisions)

For each decided item, in the **source (old) note**:

- **Done** (the user confirms it): plain `- [x] <item> ✅ <today>`, no code.
- **Carry forward:** `- [x] DAL | <item> ✅ <today>`, AND append `- [ ] <item>` to the new week's note under the matching section. Keep links and context; rewrite it as a bounded action if the review produced one. If the target note doesn't exist yet, ask before creating it, and build it from the template found in Step 1.
- **Delegate:** `- [x] DSE | <item> ✅ <today>`, naming the delegate, the ticket key and the check-in date in the item text. A delegation is only complete when it has actually been handed over. See "Delegation as one action".
- **Shelve:** `- [x] <NIN|NLR|KIV|NFE|NQE|NFN|NAN|GFN> | <item> ✅ <today>`. For KIV, note the unblocking condition and a revisit date.
- **Repeats and supersession:** if an item repeats across several old notes, or is superseded by work tracked elsewhere, close **every** occurrence as `DAL` with a pointer, e.g. `→ tracked in [[<new week's note>]]`. When the carried item is retitled or merged, note the new title in the closed source item the same way.
- **"high" / "low":** high goes to the top-priorities section of the target note, low to the other-priorities section.
- **New codes:** the user may coin a code mid-review. Confirm its meaning, record it in the overlay (or in this file, if it's generic), then apply it.

**Edit rules.** Preserve the original wording, links and the indentation of sub-items. Only prepend the code, check the box, and append the ✅ date and any pointer. Sub-checkboxes under a closed parent are closed with it, unless they are still independently live.

**Batch edits.** When closing more than a handful of items:
- back up the touched notes first;
- match each item by a unique text anchor, and abort the whole batch before writing if any anchor matches zero or several lines;
- afterwards, diff against the backup to prove that only the checkbox, code, date and pointer changed.

## Delegation as one action

When the user says "delegate to X", "assign to X" or "Jira it for X", do the whole hand-off, not just the label:

1. **Find before you create.** Search the tracker for an existing ticket (by text, the parent epic's children, and recent tickets).
2. **Create it if needed, under a parent that fits by meaning.** If the parent the user named doesn't fit (for example, it's another team's epic), say so and offer the right one. Never file under a parent that doesn't fit.
3. **Assign it**, and set the tracker's target-date and priority fields. Trackers often default priority to Low, so match the parent's priority.
4. **Write the spec** in the description, or as a comment on an existing ticket:
   - the outcome;
   - what "done" looks like;
   - two or three resources;
   - who makes the final call, when the delegate is preparing a decision rather than making it;
   - the check-in date and the target date.
5. **Mirror and close.** Add the matching task to the delegation list if the overlay defines one, then close the journal item `DSE`.
6. **Check load.** Count the delegate's open delegations. If they would pass the overlay's threshold (default 4), or if several are due in the same week, say so before handing over more.

## Delegation check-ins

For each open delegation, read the ticket's last update and its last comment, and put it in one of three groups:

- **Moved:** there's a recent comment or status change from the delegate. Report it and do nothing else.
- **Blocked on the owner:** the user promised something (a reply, a deliverable), or the delegate is waiting on a decision outside their remit (budget, policy, another team, a people call). **Do not nudge the delegate.** List these as the user's own actions.
- **Approval requests aren't blockers.** If the delegate asked the user to approve a choice inside their own remit (e.g. which of two technical options to use), treat the item as stalled on the delegate, not blocked on the owner. The nudge back is "your call — decide and proceed".
- **Stalled:** no movement since the hand-off or the last check-in. Propose one grouped reminder to the stalled delegates, each with their ticket, the "done means" line, and a date to post status by. Send it only with an explicit yes.

## Learned conventions & pitfalls

- **TODOs hide outside the priority sections.** Checkboxes appear under meeting-notes headings, where asks were captured mid-meeting. Scan the whole note, not just the priorities block.
- **Exec asks are a priority signal.** An item attributed to the CEO or an executive (e.g. a `<Name>>` prefix quoting them) defaults to resume/high unless the user says otherwise.
- **FY-level goal blocks are not weekly items.** Sections like `### Goal planning` hold quarterly or yearly goals. Leave them out of the weekly carry-forward; they belong in goal docs. Do note when a weekly item is the execution of one of them.
- **Working-state blocks carry, but aren't triaged.** Resume commands and session IDs under `## Sessions` (or similar) are not TODOs. When creating the new week's note, carry the still-live entries into its working-state block as a compact list, and ask once if it's unclear which are still live.
- **Past-dated children of a carried tree.** Don't silently re-date them or drop them. Group them under "Catch-up — dates passed, confirm done", inside the carried parent.
- **Calendar time zones.** Connectors may return events in the calendar's home zone rather than the user's. Request the user's zone, and convert before writing day tags.
- **Indentation is inconsistent** (`- [ ]` vs ` - [ ]`) between and within notes. When editing, match and preserve the exact original whitespace; never reformat.
- **Hidden Unicode characters lurk in pasted blocks**, such as non-breaking spaces inside `[ ]` checkboxes in AI- or web-pasted lists. They render as normal spaces but break exact-match edits. If an edit fails on a line that looks right, retry with a short anchor that skips the checkbox, or match using U+00A0 in the brackets. When verifying with a regex, use `- \[[^x]\]` (not `- \[ \]`) so NBSP checkboxes are caught.
- **Deeply indented sub-items:** don't guess the tab/space mix. Anchor the match on the unique text after `- [ ]` instead of on leading whitespace.
- **Verify after editing.** Grep the touched notes with `- \[[^x]\]` to confirm that only deliberately open items remain, and report any leftovers. Also watch for stray `- [ ]` prefixes on non-TODO lines (e.g. inside a pasted code fence); these are formatting bugs to strip, not items to triage. If the overlay defines mirror lists, check that every `DSE |` and `KIV |` close has its mirror.
- **Sync awareness.** Vaults commonly sync (Google Drive, iCloud, Obsidian Sync) and can change on disk mid-session, leaving conflict files like `(conflict 2025-03-31...)`. Expect anchors to shift, re-read before dependent edits, and mention conflict files to the user rather than editing them.
- **Note-per-week gaps exist** (skipped weeks, spans like `W46-48`). When the user gives a week range, list which notes actually exist and flag the gaps.
- **Learning loop.** When the user corrects you, coins shorthand, or answers a question you shouldn't have needed to ask, propose a one-line addition to the overlay at the end of the run. Generic lessons belong in this file; user-specific ones belong in the overlay.

## Leadership guardrails

Delegation and shelving affect people, and clear is kind:
- When delegating, spec the outcome, not the method.
- When shelving someone's request, tell them.
- Don't nudge a delegate for a delay that is waiting on the owner.
- When an instruction would quietly drop a commitment made to another person (a reply owed, a debrief promised), say so once before applying it.
- People-related items (feedback, performance reviews, kudos, 1:1s) are never shelved silently and never delegated.
