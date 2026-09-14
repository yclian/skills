# Gmail Filter Manager

A production-grade compiler, validator, and safe deployment runbook for **Gmail-as-Code** filter topologies using Terraform.

Prevents the recurring silent-failure bug where Gmail's SMTP delivery engine silently drops filter execution (both archiving and forwarding) due to unsupported query constructs.

---

## Supported Topologies

### Tested Implementation: 1 Gateway + 2-Tier Inboxes (3 Accounts)
- **Gateway Catch-All (`gateway@yourdomain.com`)**: Ingestion point for custom domain. Holds zero mail.
- **Tier 1 (`primary@gmail.com`)**: Personal correspondence, VIPs, receipts, security alerts, and life-planning confirmations (hotel stays, flights, bookings).
- **Tier 2 (`newsletters@gmail.com`)**: Quarantines marketing blasts, retail promos, and social digests.

### Other Supported Topologies
- **Single-Account In-Place Archiving (1 Account)**: Uses the exact same 3-filter partition to auto-archive promotional lists while pulling receipts and booking alerts back into the Primary inbox.
- **N-Tier Downstream Routing (3+ Accounts)**: Gateway fanning out to Actionable, Reading, and Disposable mailboxes.
- **Team / Organization Inbound Dispatch**: Routes billing and security alerts to duty officers (Tier 1) while dumping SaaS digests into shared team channels (Tier 2).

---

## Quick Start

### 1. Validate Filters with Linter
```bash
python scripts/lint_filters.py --path path/to/filters.auto.tfvars.json
```

### 2. Safely Add Alias / Sender to Tier-2
```bash
python scripts/add_alias.py promo@yourdomain.com --path path/to/filters.auto.tfvars.json
python scripts/add_alias.py marketing.domain.com --sender --path path/to/filters.auto.tfvars.json
```
