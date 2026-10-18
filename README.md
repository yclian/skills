# AI Agent Skills

A collection of agent skills I find others could benefit from.

## Available Skills

### 🔄 [sync-antigravity-conversations](./sync-antigravity-conversations)
Synchronizes and merges conversation transcripts, project configurations, workspace databases, and summary indexes between different profile directories of the standalone **Antigravity 2.0** application.

### 🧩 [antigravity-extras](./antigravity-extras)
Operational tribal knowledge, hidden internals, quirks, and runbooks for **Google Antigravity / Antigravity 2.0** that agents don't natively know about themselves. Includes persistent Scheduled Tasks (sidecars), runtime lifecycles, and profile architectures.

### ✉️ [gmail-filter-manager](./gmail-filter-manager)
Compiles, validates, and safely deploys Gmail gateway routing filters (Terraform) without hitting silent delivery-time failures. Enforces flat boolean clauses, partition symmetry, and pre-apply canary checks.

### 🍸 [calendar-tbd-recommender](./calendar-tbd-recommender)
Audits Google Calendar for events marked with placeholder locations (TBD, TBC, ???, or blank), dynamically detects travel & flight context, and recommends personalized dining, cocktail, or coffee venues from a curated taste graph. Includes direct event patching.

### ⚡ [laya-system-one](./laya-system-one)
Sets up, operates, and builds with **Laya**: a local, non-autoregressive "System 1" decision engine powered by ModernBERT-large (395M). Delivers typed judgments (Choice, Noul, Score) in ~35ms on standard CPU (~842 MB RAM, $0.00 token cost). Includes 1-command installer, FastAPI daemon, Model Context Protocol (MCP) gateway for Claude Code and Antigravity CLI, and LiteLLM OpenAI proxy endpoints.

### ✅ [todo-in-obsidian](./todo-in-obsidian)
Reviews, triages, and carries forward TODOs across weekly journal notes in Obsidian. Runs a structured backlog review with disposition codes (DAL, DSE, KIV, NIN...), effort estimates, delegability assessments, and per-item user confirmation, then closes out old notes and rolls deserving items into the new week.

### 🎯 [work-signal](./work-signal)
Morning triage engine for a work Gmail inbox: surfaces what actually needs human attention (leadership threads, security alerts, access approvals, colleague asks), suppresses high-volume CI and vendor noise, and renders an executive Markdown brief in chat. Includes dual execution paths (Claude Gmail connector vs. local Node 18+ CLI).

### 🛡️ [fleet-restic-backup](./fleet-restic-backup)
Orchestrates multi-node encrypted backups across mixed-OS fleets (Linux servers, Windows workstations, macOS laptops) into a unified, deduplicated **Restic** repository. Implements zero-downtime SQLite `.backup` pre-hooks, Windows live Volume Shadow Copy (VSS), cross-platform SFTP link tolerance, non-fatal warning degradation, and automated Grandfather-Father-Son (GFS) retention.

### 📐 [engineering](./engineering) (`yclian-engineering`)
Software engineering, verification, packaging, resilience, and git history standards designed for the **agentic coding era**—where code generation is cheap, mocked unit tests become tautologies, and reality-anchored verification + clean human review are the bottlenecks. Features **Dual-Boundary (Reality-and-Oracle) Verification** (ingress reality capture via `fixtures/` and contrastive pairs, pure-transform core with TDD/property tests, egress scenario suites backed by ranked oracles and `afterEach` invariant sweeps), thin zero-magic abstractions, the 3-tier packaging progression, multi-instance state persistence, and Conventional Commit + logical-category commit squashing rules.

## Installation

To install skills from this repository:
```bash
npx skills add https://github.com/yclian/skills.git
```
