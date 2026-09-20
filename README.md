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

## Installation

To install skills from this repository:
```bash
npx skills add git@github.com:yclian/skills.git
```
