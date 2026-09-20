---
name: laya-system-one
license: MIT
description: >
  Set up, operate, and build with Laya: a local, non-autoregressive "System 1"
  decision engine powered by ModernBERT-large (395M). Delivers typed judgments
  (Choice, Noul, Score) in ~35ms on standard CPU (~842 MB RAM, $0.00 token cost).
  Use when setting up Laya locally on a home server, Mini-PC, or workstation,
  writing zero-token classification/routing pipelines, diagnosing shell/LLM
  error traces, or connecting Laya to Claude Code, Antigravity CLI, and LiteLLM.
---

# Laya: Local System 1 Decision Engine

**Laya** brings Daniel Kahneman's **"System 1" (fast, intuitive reflex)** into your AI stack and agent workflows. 

While traditional Large Language Models (Gemini Pro, Claude 3.7, Qwen 35B) are **System 2**—slow, expensive, autoregressive token generators designed for human prose—modern software workflows mostly need **fast, typed semantic judgments**:
- *Is this email an invoice?* (`Noul` -> `0.94`)
- *Which of these 4 error categories caused this crash?* (`Choice` -> `PERMISSION_AUTH_DENIED`)
- *How urgent is this production alert?* (`Score` -> `2.78` on a 1–3 ladder)
- *Classify 200 incoming notifications without burning $5 in cloud tokens.*

Laya evaluates state in a **single forward pass** on standard CPU in **~35ms**, consuming **~842 MB RAM** at FP16. Code owns the workflow; Laya provides the programmable common sense.

### Origins, Context & Acknowledgements
This skill and architectural pattern are inspired by **TypeSafe AI's Jev** (the flagship System 1 decision model pioneered by Diogo Almeida, Erik Gafni, and Sasha Sheng; see their canonical skill at [typesafe-ai/skills](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md)) and Daniel Kahneman's dual-process cognitive framework (*Thinking, Fast and Slow*). 

With TypeSafe dropping Jev's waitlist and offering a $5 trial credit, System 1 decision heads are rapidly becoming the standard interface for agent routing. **Laya** serves as the self-hosted, open-weights complement for environments demanding full local sovereignty and true zero-token economics:

| Dimension | **Laya** (This Skill) | **Jev** (TypeSafe AI) |
| :--- | :--- | :--- |
| **Hosting & Economics** | 100% Self-Hosted ($0.00 token cost forever on CPU) | Managed Cloud API ($5 trial credit, no waitlist; metered per request) |
| **Underlying Weights** | Open weights: ModernBERT-large (395M) | Proprietary hosted decision model |
| **Data Privacy** | Zero telemetry / Zero cloud egress | Hosted API endpoint |
| **Inference Latency** | ~25–45ms (Local socket / IPC) | ~100–300ms (Network round-trip) |
| **Semantic Primitives** | `Choice`, `Noul`, `Score` | `Choice`, `Noul`, `Score` |

Both paradigms share the exact same machine-native primitives. Choose **Jev** for instant cloud-managed scale with zero infrastructure setup; choose **Laya** for air-gapped workflows, sensitive trace diagnosis, and zero-cost local CPU execution.

---

## 1. Quickstart: 1-Command Local Setup

You can run Laya on any Linux server, Intel/AMD Mini-PC, Raspberry Pi 5, or Windows WSL2 instance.

### Step 1: Run the automated installer
From the root of this skill:
```bash
bash scripts/install_laya.sh
```

Or run manually step-by-step:
```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Setup venv with CPU PyTorch
mkdir -p /srv/laya && cd /srv/laya
uv venv --python 3.10 venv
./venv/bin/uv pip install --index-url https://download.pytorch.org/whl/cpu torch>=2.1.0
./venv/bin/uv pip install laya>=0.3.4 transformers>=4.40.0 fastapi>=0.110.0 uvicorn[standard] mcp>=1.2.0

# 3. Deploy server & pre-load weights
cp scripts/server.py /srv/laya/server.py
./venv/bin/python3 -c "import laya; laya.load('convaiinnovations/laya', device='cpu')"

# 4. Start daemon
./venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8500
```

### Step 2: Verify Health
```bash
curl http://127.0.0.1:8500/health
# {"status":"healthy","model":"convaiinnovations/laya","backbone":"ModernBERT-large (395M)","device":"cpu","ready":true}
```

---

## 2. The Three System 1 Primitives

Laya structures all judgments into three machine-native primitives:

### Primitive A: `Choice` (Mutually Exclusive Categorization)
Selects exactly one option from a defined set. Returns the selected key, calibrated confidence, and full probability distribution.
```python
query = {
    "category": {
        "type": "choice",
        "instructions": "Classify incoming notification",
        "criteria": {
            "BILLING": "Invoices, payment receipts, subscription renewals",
            "ALERT": "Security warnings, node disconnects, quota alerts",
            "NOISE": "Newsletters, marketing promotions, digests"
        }
    }
}
```

### Primitive B: `Noul` (Condition / Probability of Yes)
Unlike binary Booleans (true/false), `Noul` returns a **calibrated continuous probability** from `0.0` to `1.0`. This allows code to set application-specific risk thresholds.
```python
query = {
    "is_deductible": {
        "type": "noul",
        "instructions": "Is this transaction a tax-deductible business expense?"
    }
}
# Output: {"yes_probability": 0.892, "confidence": 0.892}
```
* Threshold recipe in code:
  * `p > 0.90`: Auto-approve in database.
  * `0.60 <= p <= 0.90`: Queue for 1-click human confirmation.
  * `p < 0.60`: Mark as personal.

### Primitive C: `Score` (Ordered Semantic Ladders)
LLMs struggle with arbitrary numeric scores (e.g. "Rate from 1 to 10"). Laya instead evaluates probability distributions across **concrete, ordered semantic levels** to compute an expected mathematical position.
```python
query = {
    "incident_severity": {
        "type": "score",
        "instructions": "Score the severity of this production incident",
        "criteria": {
            "1": "Routine notification or log noise, zero customer impact",
            "2": "Elevated latency or non-critical worker retrying",
            "3": "SLA breached or partial degradation of core flow",
            "4": "Complete site outage, data loss risk, or security breach"
        }
    }
}
# Output: {"expected_score": 2.84, "probabilities": {"1": 0.05, "2": 0.15, "3": 0.70, "4": 0.10}}
```

---

## 3. The Power Move: Multi-Question Parallel State Evaluation (`Eval`)

Never call an LLM sequentially for multiple checks. Pass the state **once**, and send multiple questions simultaneously. ModernBERT evaluates all questions in a **single forward pass in ~40ms**:

```bash
curl -X POST http://127.0.0.1:8500/decide \
  -H "Content-Type: application/json" \
  -d '{
    "text": "AWS Invoice #9821 for $320.00 is due on Oct 1st.",
    "query": {
      "is_invoice": {"type": "noul", "instructions": "Is this a billing receipt?"},
      "urgency":    {"type": "score", "instructions": "Rate urgency", "criteria": {"1": "FYI", "2": "Needs payment"}},
      "bucket":     {"type": "choice", "criteria": {"CLOUD": "Hosting", "SAAS": "Software", "PERSONAL": "Personal"}}
    }
  }'
```

---

## 4. Architectural Recipes to Steal

### Recipe 1: "Select Instead of Generate" (Zero Hallucination)
LLMs hallucinate when asked to copy numbers or dates from messy documents.
1. Run simple code (e.g. regex) to find all candidate matches (e.g. all 3 monetary amounts in an invoice).
2. Ask Laya: `"Which candidate represents the final balance due net of tax?"` with candidates as `Choice` criteria.
3. Code extracts the exact substring from source text. **Zero hallucination guaranteed.**

### Recipe 2: "Verify and Escalate" (Extraction Cascades)
Don't send everything to Claude 3.7 or Gemini Pro.
1. Run input through Laya (`~35ms`, `$0.00`).
2. If `confidence >= 0.92`: Execute deterministic action in code.
3. If `confidence < 0.92`: Escalate to Gemini Pro with context and Laya's initial suspicion.

### Recipe 3: Automated Execution Error Triage & Fast Repair
When a local LLM or script produces a syntax blowout or tool failure, call `laya_triage_error`:
- In 35ms, it classifies the defect (`SYNTAX_FORMAT_ERROR`, `PERMISSION_AUTH_DENIED`, `MISSING_DEPENDENCY`).
- Directly prescribes the repair (e.g. regex fence stripping vs credential reload) before re-running.

---

## 5. Client Integrations

### A. Claude Code (`~/.claude.json`)
Connect Claude Code via HTTP MCP:
```bash
claude mcp add --transport http laya http://<YOUR_HOST>:8500/mcp
```
*(Or if using Tailscale HTTPS: `claude mcp add --transport http laya https://laya.<tailnet>.ts.net/mcp`)*

### B. Antigravity CLI (`mcp_config.json`)
Add to `~/.gemini/antigravity-cli/mcp_config.json`:
```json
{
  "mcpServers": {
    "laya": {
      "serverUrl": "http://<YOUR_HOST>:8500/mcp",
      "timeout": 10000
    }
  }
}
```

### C. LiteLLM Proxy Gateway (`config.yaml`)
Register Laya as an ultra-fast OpenAI-compatible completion model:
```yaml
model_list:
  - model_name: laya-decision
    litellm_params:
      model: openai/laya-decision
      api_base: http://<YOUR_HOST>:8500/v1
      api_key: "sk-noauth"
      timeout: 10

litellm_settings:
  fallbacks:
    - {"laya-decision": ["gemini-flash"]}
```

---

## 6. Verification Checklist

- [ ] `curl http://127.0.0.1:8500/health` returns `200 OK` with `ready: true`.
- [ ] `curl http://127.0.0.1:8500/mcp` returns HTTP 400 with `Missing session ID` (proves FastMCP is live).
- [ ] Claude Code: `claude mcp list` shows `laya - ✔ Connected`.
- [ ] Antigravity CLI: tools `laya_classify`, `laya_decide`, `laya_noul`, `laya_score`, `laya_eval` appear in tool registry.

---

## 7. Known Limitations & Architectural Mitigations

Recent open-source benchmarks and autonomous agent evaluations highlight three critical boundaries to keep in mind when engineering with Laya:

### 1. The 512-Token Context Window
* **The Constraint**: Laya's decision head operates optimally within a 512-token span. Dumping raw multi-page PDFs or giant 30k-token logs will cause truncation.
* **Mitigation (Extract First, Judge Second)**: Never feed raw documents into Laya. Use fast deterministic code (regex, string slices, or AST parsers) to extract candidate spans (e.g., the 10-line traceback snippet, the email header, the specific sentence in question). Pass *only* the focused span (~50–200 tokens) to Laya.
* **Dual-Tier Fallback**: For genuinely long documents that cannot be pre-sliced, route via LiteLLM to Cloud Jev or Gemini Flash.

### 2. Degradation on Large Option Sets (>20 Choices)
* **The Constraint**: While frontier cloud models maintain accuracy across large option sets, local 0.4B System 1 heads degrade when presented with 50+ competing options at once (diluting logit probability mass across overlapping embeddings).
* **Mitigation (Hierarchical Gating / Tree of Deciders)**: Never flatten 50 tools into a single prompt. Split decisions into a 2-tier tree:
  - *Tier 1 (Domain Gate)*: `[DATABASE, AUTH, NETWORK, APPLICATION]` -> 4 options (Laya accuracy >95%).
  - *Tier 2 (Tool Gate)*: 5 specific tools within the selected domain -> 5 options.
  Two 35ms passes take 70ms total and maintain near-perfect accuracy.
* **Mitigation (Orthogonal Noul Flags)**: If you have independent attributes, ask multiple parallel `Noul` questions instead of cramming combinations into one massive enum.

### 3. The Prompt Caching Destruction Trap (Teknium's Law)
* **The Trap**: If an agent uses a fast System 1 model to constantly "compact", rewrite, or mutate the active conversation history between turns, it alters the message prefix. When the agent next calls Claude 3.7 or Gemini Pro, the KV prompt cache is completely invalidated—destroying the 90% prompt-caching discount and driving token costs through the roof!
* **Mitigation (Out-of-Band Reflexes Only)**:
  - **NEVER** use Laya to rewrite or compress the ongoing conversation transcript.
  - **DO** use Laya for **out-of-band auxiliary execution**:
    - Pre-filtering incoming events/emails *before* they enter the agent loop.
    - Diagnosing error traces *inside a tool execution* (tool outputs append to the end of the transcript, preserving the cached conversation prefix).
    - Standalone batch pipelines and background workers (event routers, scrapers, data filtering pipelines).
