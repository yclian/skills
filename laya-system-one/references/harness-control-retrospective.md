# Architectural Retrospective: Harness Gating vs. Application SDK

> **Context**: Between 2026-09-20 and 2026-09-23, we conducted deep experiments attempting to wire **Laya** (System 1 ModernBERT) as an automated mechanical reflex gatekeeper inside agent harnesses (Claude Code, Antigravity/agy, and OpenCode).  
> This retrospective records why this attempt was undertaken, how it was implemented, the technical friction encountered, and why aligning with the **TypeSafe SDK Philosophy** (using System 1 inside application code and fleet pipelines) is the superior architectural model.

---

## 1. The Hypothesis: Why the Attempt Was Made

When Daniel Kahneman's dual-process cognitive framing (*System 1 Fast Reflex vs. System 2 Slow Deliberation*) was popularized by TypeSafe AI's Jev, it was natural to imagine a cognitive hierarchy:
* **The Agent Harness**: An LLM (Claude 3.7 Opus, Gemini 2.5 Pro) that plans, reasons, and speaks.
* **The Problem**: Frontier LLMs burn thousands of expensive reasoning tokens on trivial micro-judgments (e.g., checking if a bash command exited with a 403, classifying a git diff, or verifying whether a shell command is destructive).
* **The Vision**: Intercept the agent harness *before* it burns tokens. Insert ModernBERT (~35ms on CPU, $0.00 token cost) as an involuntary subconscious reflex directly on the harness's tool rails.

---

## 2. What Was Built (The Harness Control Layer)

To force the harness to delegate to Laya, we built:

1. **Claude Code Lifecycle Hooks (`~/.claude/settings.json`)**:
   * A Python `PostToolUse` hook script (`laya-triage-hook.py`) that intercepted `Bash` and terminal stderr.
   * If a non-zero exit code or traceback was detected, it made an out-of-band HTTP call to Laya's `/decide` endpoint on Arwen and injected the classified error category (`PERMISSION_AUTH_DENIED`, `MISSING_DEPENDENCY`, etc.) back into the transcript stream.
2. **Antigravity Lifecycle Hooks (`~/.agents/hooks.json`)**:
   * An `agy-laya-hook.py` script handling protojson payloads on `PreToolUse` (evaluating `laya_is_safe` on `run_command` arguments to catch `rm -rf`, `--force`, or drop tables) and `PostToolUse` (error diagnosis).
3. **Global Steering & Precedence Directives**:
   * `~/AGENTS.md`, `~/.agents/AGENTS.md`, and `~/.claude/rules/laya-triage.md` mandating that the model invoke `laya_*` as its first tool step before thinking or writing regexes.
4. **Single-Argument Shortcut Tools**:
   * `laya_triage_git(diff_or_message)` and `laya_is_safe(command)` in `server.py` to eliminate the friction of constructing complex JSON `{text, options: {...}}` payloads.

---

## 3. Why It Encountered Friction (The Reality Check)

When analyzing telemetry across thousands of real production tool invocations in repositories like `servicerocket-ops/context` and `servicerocket-coe/skills`, **zero organic decisions were made by Laya**. The agent bypassed Laya on almost every step unless explicitly ordered by a user prompt.

The reasons are structural to frontier LLM agent design:

### A. The Agent Thinks in Token Space, Not Tool Space
* Claude Code and Antigravity formulate their intent and micro-decisions **implicitly inside their `<thinking>` blocks**.
* When Claude considers whether an error is an auth failure or a syntax error, it doesn't pause to formalize a prompt, make an MCP network round-trip, wait for an external model, parse the JSON, and resume. It resolves the ambiguity in its own autoregressive forward pass.
* Expecting an LLM to volunteer to call an external 0.4B model for its own internal reasoning is asking it to act contrary to its primary objective function.

### B. Protocol Incompatibility & Asymmetric Hook APIs
* **Claude Code** expects plain text hook stderr/stdout logging.
* **Antigravity** expects strict protojson (`decision`, `reason`, `overwrite`, `injectSteps`).
* Maintaining brittle OS-level hook bridges across Windows PowerShell, Linux systemd, Tailscale sockets, and multiple client agent versions introduces high operational drag for negligible token savings.

### C. The Prompt-Caching Invalidation Trap
* Injecting dynamic, out-of-band hook messages into an active session alters the conversation prefix.
* When the agent next calls Claude or Gemini, the prompt cache prefix can be invalidated, wiping out the 90% prompt-caching discount and costing far more money than Laya saved.

---

## 4. The Canonical Alternative: The TypeSafe Philosophy

Examining TypeSafe AI's official skill (`typesafe-ai/SKILL.md`) revealed that **TypeSafe never attempted harness control**. 

Their model is strictly **application-centric**:
1. **The Agent is the Builder, Not the Patient**: The agent is the engineer writing the software; Laya is an SDK primitive inside the software being built.
2. **Deterministic Pipelines Own the Volume**: The true scale for System 1 is **background batch data** where no human is sitting in a chat terminal:
   * Event routers & webhook ingestors (filtering 10,000 GitHub notifications or Slack pings).
   * Scheduled cron jobs (e.g. `daily_macro_radar.py` filtering noise before Gemini Flash).
   * Fast data extraction (evaluating `Choice` and `Noul` over streaming DB records in ~35ms).

---

## 5. Conditions for Re-evaluating Harness Control

If you ever wish to revisit harness-level reflex control in the future, do **not** do it via prompt guidelines or loose shell hooks. Re-evaluate only if:

1. **Native Client Sidecars**: The agent runtime natively integrates local embedding/encoder models directly in C++ / Rust into its prompt pipeline (e.g., Cursor or Antigravity IDE building local speculative execution into the binary).
2. **Strict Headless Cron Watchdogs**: When building a fully headless CLI watchdog (e.g., an automated CI/CD pipeline or self-healing daemon) that has zero human chat interaction, wrapping script execution with a deterministic Laya triage gate is clean and isolated.
3. **Hard Security / Air-Gap Policies**: Where an enterprise enforces an immutable local pre-tool proxy that blocks destructive commands at the OS transport layer before packets reach cloud LLM endpoints.

---
*Authored: 2026-09-23 | Retrospective preserved under `laya-system-one/references/harness-control-retrospective.md`*
