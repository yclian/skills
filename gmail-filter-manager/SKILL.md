---
name: gmail-filter-manager
description: Compose, validate, and safely deploy Gmail gateway routing filters (Terraform) without hitting silent delivery-time failures. Enforces flat boolean clauses, partition symmetry, and pre-apply canary checks.
allowed-tools:
  - run_command
  - view_file
  - replace_file_content
---

# Gmail Filter Manager

Compiles, validates, and updates Gmail gateway routing filters in Terraform (`filters.auto.tfvars.json`).

Prevents the recurring silent-failure bug where Gmail's SMTP delivery engine silently drops filter execution (both archiving and forwarding) due to unsupported query constructs.

---

## 1. Supported Topologies & Architectures

This skill is designed around an inbound gateway and tiered inbox partition.

### Battle-Tested Architecture (1 Gateway + 2-Tier Inboxes / 3 Accounts)
The primary production implementation runs across **3 email accounts**:
1. **Gateway Catch-All (`gateway@yourdomain.com`)**: Receives all incoming domain mail. Holds zero permanent mail, only routes.
2. **Tier 1 - Actionable / Primary (`primary@gmail.com`)**: Receives high-signal personal mail, VIP correspondence, financial statements, security alerts, and life-planning confirmations (hotel stays, flights, booking confirmations).
3. **Tier 2 - Low Signal / Marketing (`newsletters@gmail.com`)**: Quarantines marketing blasts, promotional offers, social digests, and commercial noise.

### Alternative Topologies It Totally Works Under
While battle-tested on the 3-account gateway model, the exact same **3-Filter Disjoint Positive Partition** directly powers:

1. **Single-Account In-Place Archiving (1 Email Account)**:
   - Instead of forwarding to separate Gmail accounts, the 3 filters operate directly inside a single Gmail account.
   - **F1**: Skips the inbox (`removeLabelIds: ["INBOX"]`) and applies label `Newsletters` for marketing senders.
   - **F2**: Leaves all general correspondence in `INBOX`.
   - **F3**: Pulls back any receipt, security, or booking email matching F1 senders back into `INBOX` and marks `Important`.
   - *Why this matters*: Solves the ubiquitous Gmail bug where users try to build "archive newsletter senders unless it's a receipt" rules in a single inbox and hit silent delivery failures due to nested negations.

2. **N-Tier Downstream Routing (N Email Accounts)**:
   - A gateway fanning out to 3 or more downstream mailboxes:
     - Tier 1: Actionable / VIP / Direct Contacts
     - Tier 2: Reading / Subscriptions / Curated Digests
     - Tier 3: Bulk Promos / E-commerce Discounts / Disposable Registrations

3. **Team / Organization Inbound Dispatch (Shared vs. Private)**:
   - A business domain catch-all (`inbound@company.com`) routing high-signal transactional, billing, and security notices to founders or duty officers (Tier 1) while isolating SaaS digests, cold outreach, and vendor newsletters to a shared team archive or group (Tier 2).

4. **Multi-Domain Catch-All Consolidation**:
   - Multiple vanity or project domains (`me@domainA.com`, `contact@domainB.com`) consolidated into a single structured gateway filter partition.

---

## 2. The Core Problem & Engine Limits

Gmail maintains two completely different query evaluation engines:
1. **The Search Index Parser (Web / API Search)**: Accepts full boolean nesting, complex parenthetical trees, and compound operators like `-(subject:(...) OR (to:... subject:...))`.
2. **The SMTP Delivery Filter Engine (Incoming Mail Rules)**: Executes strictly at delivery time. **It silently fails** when queries contain:
   - Nested compound conditions inside a negation (e.g. `-(A OR (B C))` or `-(to:... subject:...)`).
   - The Terraform `negated_query` attribute (which drops email forwarding silently).
   - Queries approaching ~3,000 characters (silent query truncation).

When delivery-time rule evaluation fails, **Gmail does not report an error or throw a bounce**; it simply skips the filter actions, leaving mail unforwarded and unarchived.

---

## 3. The 3-Filter Disjoint Positive Partition Architecture

Gateway traffic is partitioned across three disjoint filters:

```
                  ┌───────────────────────────────┐
                  │   Incoming Gateway Traffic    │
                  └──────────────┬────────────────┘
                                 │
                 Is it in Tier-2 Target Scope?
               (to: aliases, curated promo senders)
                                 │
                   ┌─────────────┴─────────────┐
                   │ YES                       │ NO
                   ▼                           ▼
        Does it contain Receipt,        [Filter 2 (F2)]
        Security, or Life-Planning      Tier-1 Default:
        pullback keywords / ICS?        (to:yourdomain.com) -(Tier 2 scope)
                   │                    FORWARD -> tier1@example.com
           ┌───────┴───────┐
           │ NO            │ YES
           ▼               ▼
     [Filter 1 (F1)]  [Filter 3 (F3)]
     Tier-2 Normal:   Tier-1 Pullback:
     (Tier 2 scope)   (Tier 2 scope)
     -subject:(...)   (subject:(...) OR filename:ics ...)
     -filename:ics    FORWARD -> tier1@example.com
     -from:...
     FORWARD -> tier2@example.com
     ARCHIVE (skip INBOX)
```

---

## 4. Mandatory Compiler Invariants

When modifying `filters.auto.tfvars.json`:

1. **Flat Top-Level Negations in F1**:
   - ✅ `(scope) -subject:(...) -filename:ics -from:...`
   - ❌ `(scope) -(subject:(...) OR filename:ics OR (to:... subject:...))` (Nested compound booleans cause silent failure).
2. **Symmetric Pullback (F1 <-> F3)**:
   - Any keyword or filetype excluded in F1's tail (`-subject:(...)`) MUST appear symmetrically in F3's positive inclusion clause (`(subject:(...))`).
3. **No `negated_query` Attribute**:
   - Always use positive `query` attribute with disjoint set subtraction in F2.
4. **Clean Scope Separation**:
   - High-touch personal or transactional aliases should remain outside the Tier 2 scope rather than relying on brittle subject-matching rules.

---

## 5. Standard Operational Workflow

Whenever adding or adjusting gateway filters:

### Step 1: Run the Pre-Apply Linter
```bash
python scripts/lint_filters.py --path path/to/filters.auto.tfvars.json
```
Ensure all compiler invariants pass with 0 errors.

### Step 2: Apply via Terraform with Pinned Credentials
```bash
terraform plan
terraform apply
```

### Step 3: Sync Updated Filter IDs
Update the generated filter IDs in `filters.auto.tfvars.json` so Terraform state stays reconciled.

### Step 4: Run Post-Apply Canary Probe
Send canary probe messages across all 3 filter paths and verify that:
- F1: Gateway copy is archived (`removeLabelIds: ["INBOX"]`)
- F2: Delivered to Tier 1
- F3: Pulled back to Tier 1
