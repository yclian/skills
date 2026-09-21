# Laya: Self-Hosted System 1 Decision Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Model: ModernBERT-large](https://img.shields.io/badge/Backbone-ModernBERT--large%20(395M)-green.svg)](https://huggingface.co/convaiinnovations/laya)
[![Architecture: System 1](https://img.shields.io/badge/Architecture-System%201%20Fast%20Reflex-purple.svg)](https://github.com/typesafe-ai/skills)

**Laya** brings Daniel Kahneman's **System 1 (fast, intuitive reflex)** to local and fleet AI stacks. 

While traditional LLMs (Gemini, Claude, Qwen) are **System 2**—slow, autoregressive token generators built for human prose—modern software agents mostly need **fast, typed semantic judgments**:
* *Is this email an invoice?* (`Noul` $\rightarrow$ `0.94`)
* *Which of 4 error categories caused this crash?* (`Choice` $\rightarrow$ `PERMISSION_AUTH_DENIED`)
* *Classify 500 incoming commits without burning $10 in cloud tokens.*

Laya evaluates state in a **single non-autoregressive forward pass on standard CPU in ~35ms** with **~842 MB RAM** and **$0.00 token cost forever**.

---

## 1. Prep & Setup the Backend

### A. Instant Local Demo (2 Commands)
```bash
git clone https://github.com/yclian/skills.git && cd skills/laya-system-one
uv run python scripts/server.py
```
*(Or run `bash scripts/install_laya.sh` for an automated systemd Linux installer).*

### B. Expose over Tailscale (1 Command)
Make Laya available securely across your entire tailnet with zero port-forwarding:
```bash
tailscale serve --bg --https=443 http://127.0.0.1:8500
```
Your backend is now live at `https://<your-node>.dikdik-dojo.ts.net/mcp`.

---

## 2. Install the Skill & Configure MCP

### Install the Agent Skill
Give your coding agents (Claude Code, Antigravity, Cursor, Codex) the decision paradigms, prompt rules, and error triage heuristics:

```bash
# Using skills CLI
npx skills add yclian/skills --skill laya-system-one

# Or manual clone
git clone https://github.com/yclian/skills.git ~/.agents/skills/laya-system-one
```

### Wire the MCP Server

#### Claude Code (CLI)
```bash
claude mcp add -s user --transport http laya https://<your-host>.ts.net/mcp
```

#### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "laya": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<your-host>.ts.net/mcp"]
    }
  }
}
```

#### Antigravity IDE & CLI (`mcp_config.json`)
```json
{
  "mcpServers": {
    "laya": {
      "serverUrl": "https://<your-host>.ts.net/mcp",
      "timeout": 10000
    }
  }
}
```

---

## 3. Monitor Telemetry & Stats

### Live Decision Stream
Watch choices, calibrated confidence scores, and latencies live in your terminal:
```bash
ssh <your-server> "journalctl -u laya -f | grep '⚡'"
```
**Sample live stream:**
```text
⚡ [laya_decide] choice='truck' conf=0.75 latency=151.8ms | input='Moving 10 tons of steel coils...'
⚡ [laya_classify] choice='DOCS_UPDATE' conf=0.86 latency=229.6ms | input='docs(laya): add architecture...'
⚡ [laya_triage_error] choice='PERMISSION_AUTH_DENIED' conf=0.97 latency=607.1ms | input='HTTP 403 Forbidden...'
```

### Query Live Stats & 4-Tier Routing Breakdown
```bash
curl -s http://localhost:8500/stats | jq .
# Or via Tailscale:
curl -s https://<your-host>.ts.net/stats | jq .
```

**Real-time output:**
```json
{
  "uptime_seconds": 1240.5,
  "total_decisions": 48,
  "avg_latency_ms": 234.12,
  "routing_summary": {
    "system_1_resolved_pct": "68.8%",
    "system_2_cheap_rag_pct": "14.6%",
    "system_2_deep_reasoning_pct": "10.4%",
    "human_escalation_pct": "6.2%"
  },
  "confidence_tiers": {
    "high_local": { "threshold": ">= 0.75", "action": "Local System 1 (ModernBERT CPU)", "percentage": "68.8%" },
    "mid_cheap_rag": { "threshold": "0.50 - 0.74", "action": "Fast Cloud / RAG (Flash / Qwen 35B)", "percentage": "14.6%" },
    "low_deep_reasoning": { "threshold": "0.25 - 0.49", "action": "Deep System 2 (Gemini Pro / Claude Sonnet)", "percentage": "10.4%" },
    "bad_human_escalation": { "threshold": "< 0.25", "action": "Human Escalation / Ambiguity Tripwire", "percentage": "6.2%" }
  }
}
```

---

## 4. Confidence-Driven Escalation Across Agent Harnesses

How do agent harnesses (**Antigravity**, **Claude Code**, and **OpenCode**) behave when evaluating Laya's calibrated confidence score?

| Confidence Tier | Cloud LLM Called? | Antigravity (Gemini) | Claude Code (Anthropic) | OpenCode (Local / Cloud) |
| :--- | :---: | :--- | :--- | :--- |
| **High ($\ge 0.75$)** | **No** (0 tokens) | Accepts choice immediately; skips internal reasoning turns and executes. | Accepts choice immediately; skips multi-turn reasoning and proceeds. | Resolves task step locally; bypasses LLM prompt queue entirely. |
| **Mid ($0.50–0.74$)** | **Harness decides** | Low-stakes: accepts. High-stakes: spawns subagent (`Model: 'flash'` or `'pro'`). | Low-stakes: accepts. High-stakes: triggers extended thinking or subagent review. | Shunts payload to fast speculative tier (e.g. local Qwen coder or cheap cloud model). |
| **Low ($0.25–0.49$)** | **Yes (System 2)** | Detects competing options; escalates to **Gemini Pro** (`invoke_subagent(Model: 'pro')`). | Detects ambiguity; escalates to **Claude Sonnet / Opus** with deep reasoning enabled. | Routes payload to primary frontier reasoning tier (Gemini Pro / Sonnet). |
| **Bad ($< 0.25$)** | **Human Prompted** | **Ambiguity Tripwire**. Halts execution and fires `ask_question` modal. | **Ambiguity Tripwire**. Halts execution and prompts human via interactive CLI. | Emits an execution breakpoint in OpenCode UI/terminal requiring human selection. |

> **Autonomous Gateway Mode (LiteLLM / Cron)**:  
> When run headlessly behind LiteLLM (`model="laya-decision"`), **High** returns the typed JSON choice in ~35ms with zero cloud egress ($0.00). **Mid** routes to fast models (`gemini-flash`), **Low** escalates to deep models (`gemini-pro`), and **Bad** flags an alert (e.g. Telegram via Hermes) for human confirmation.

---

## Quick Test Verification

Test your running server with a single REST call:
```bash
curl -X POST http://localhost:8500/decide \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Moving 10 tons of steel coils between cities",
    "options": {
      "bicycle": "urban bike paths",
      "truck": "heavy freight highway"
    }
  }'
```
**Response:**
```json
{
  "answers": {
    "decision": {
      "choice": "truck",
      "confidence": 0.7509,
      "probabilities": { "bicycle": 0.0415, "truck": 0.9585 }
    }
  },
  "latency_ms": 151.83
}
```

---

## Acknowledgements & Ecosystem

**[NandhaKishorM](https://github.com/NandhaKishorM/laya)** — the original creator of the Laya Python library (`pip install laya`), the `convaiinnovations/laya` HuggingFace model family, and the RLCD training methodology that makes non-autoregressive typed decisions possible. This skill is built directly on top of his work. He built this *before* TypeSafe called it System 1.

**[TypeSafe AI's Jev](https://github.com/typesafe-ai/skills)** — the cloud-managed System 1 decision service that popularized the paradigm. Inspired by Daniel Kahneman's dual-process cognitive framework (*Thinking, Fast and Slow*).

**[@receptron/laya](https://github.com/receptron/laya)** — Node.js/TypeScript ONNX runtime port for zero-Python in-process execution.

* Choose **NandhaKishorM's Laya** (this skill) for 100% self-hosted sovereignty, zero data egress, and $0.00 token cost on standard CPU.
* Choose **TypeSafe Jev** for instant cloud-managed scale with zero infrastructure setup.
