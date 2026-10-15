# Laya 0.4.7 Upgrade, Customization Audit & Empirical Eval Plan

> **For Agentic Workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task once Arwen (`arwen.dikdik-dojo.ts.net`) is back online from maintenance. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Arwen System 1 Decision Engine (`svc:laya`, `:8500`) to upstream [`laya==0.4.7`](https://github.com/NandhaKishorM/laya), close the Imlad Decision #17 zero-persistence logging gap (`record_decision`), fix the `laya_score` rubric serialization bug, adopt `0.4.7` vectorized batching (`agent.predict_batch`), reconcile `laya.service` host-binding drift, and establish a repeatable upgrade smoke-test harness.

**Architecture:** We maintain a strict **Adapter / Facade boundary**: upstream `laya` is installed unmodified from PyPI into `/srv/laya/venv`, while all Imlad fleet customizations (StreamableHTTP MCP on `/mcp`, `LayaTriageGate` REST `/decide`, LiteLLM OpenAI shim `/v1/chat/completions`, 4-tier confidence telemetry `/stats`, and metadata-only `journald` logging) live exclusively in [`scripts/server.py`](../../scripts/server.py) (deployed to `/srv/laya/server.py` and mirrored to `yclian/machines:arwen/laya/server.py`).

**Tech Stack:** Python 3.12 (`uv` venv at `/srv/laya/venv`), `laya==0.4.7` (`transformers>=4.48.0`, `torch>=2.0.0`, `safetensors>=0.4.0`), `mcp>=2.2.0` (FastMCP StreamableHTTP), `fastapi>=0.110.0`, `uvicorn`, `systemd` (`laya.service`), Tailscale Serve (`https://laya.dikdik-dojo.ts.net/mcp`).

**Cross-References:**
- Skill Architecture & Docs: [`ARCH.md`](../../ARCH.md), [`SKILL.md`](../../SKILL.md), [`README.md`](../../README.md), [`references/harness-control-retrospective.md`](../../references/harness-control-retrospective.md)
- Fleet Architecture & Dataflow (`yclian/machines`): `ARCH.laya.md`, `DATAFLOW.laya.md`, `FLEETS.md`, `arwen/laya/server.py`
- Obsidian Architecture & Eval Note: `Commitments/Building/2026-07 Imlad/2026-09-21 System 1 Decision Engine (Laya) Architecture & Eval.md`
- Governance Decisions: `Commitments/Building/2026-07 Imlad/2026-07 Imlad.md` (Decisions #16, #16 Amendment, #17)

---

## Part 1: Customization Audit & 0.4.7 Compatibility Matrix

### 1.1 Did We Customize Upstream `laya`?
**No changes were made inside the upstream `laya` Python package.** Instead, all fleet customizations live in our **633-line service wrapper** ([`scripts/server.py`](../../scripts/server.py) / `arwen/laya/server.py`) and systemd unit ([`scripts/install_laya.sh`](../../scripts/install_laya.sh) / `arwen/laya/laya.service`):

| Layer | Component | Upstream `laya 0.4.7` Built-In | Our Fleet Customization (`scripts/server.py`) | Why We Keep Our Wrapper |
| :--- | :--- | :--- | :--- | :--- |
| **Core Model & Inference** | `laya.load()` / `agent.predict()` | `laya.load("convaiinnovations/laya", device="cpu")`, `predict()`, `predict_batch()` | Calls `laya.load("convaiinnovations/laya", device="cpu")` directly; pins `torch.set_num_threads(4)` | 100% compatible with `0.4.7`. Can now upgrade `laya_classify` from Python loop to `agent.predict_batch()`. |
| **MCP Transport** | `laya.mcp` (`laya-mcp-server`) | **stdio-only** (`mcp.run()`) with 5 tools (`laya_decide`, `laya_batch`, `laya_evaluate`, `laya_shortlist`, `laya_capabilities`) | **StreamableHTTP (`/mcp`)** mounted into FastAPI with `TransportSecuritySettings(enable_dns_rebinding_protection=False)` for Tailscale Serve (`https://laya.dikdik-dojo.ts.net/mcp`) | Remote fleet machines (Aili, Suzu, Adara) connect over Tailscale HTTPS `/mcp`, which upstream stdio MCP does not serve. |
| **Domain MCP Tools** | MCP tool surface | Generic primitives + tournament shortlist | 8 fleet-tailored tools: `laya_classify`, `laya_decide`, `laya_noul`, `laya_score`, `laya_eval`, `laya_triage_error` (with 35-line tail slice & prescriptive `action_map`), `laya_triage_git`, `laya_is_safe` | Preserves global `user_global` rule contracts (`laya_classify`, `laya_decide`, `laya_triage_error`). |
| **REST `/decide`** | `laya.serve` (`POST /v1/systemone`) | Expects `{"state": ..., "questions": {...}}` on `/v1/systemone` | Custom `POST /decide` accepting `{text, options, instruction}` and returning `{decision, confidence, tier, action, latency_ms}` | Required by `arwen/financial_signals.py` (`LayaTriageGate`, lines 989–1038) calling `http://127.0.0.1:8500/decide`. |
| **LiteLLM OpenAI Shim** | None | Not present upstream | Custom `POST /v1/chat/completions` & `GET /v1/models` parsing JSON or natural-language `[Option A, Option B]` prompts into Laya `choice` calls | Required by `arwen/litellm/config.yaml` (`laya-decision` and `laya` routes on `:4000`). |
| **Telemetry & Escalation Tiers** | None | Raw confidence float only | `GET /stats` & `POST /stats/reset` tracking 4-tier escalation (`high_local >=0.75`, `mid_cheap_rag 0.50-0.74`, `low_deep_reasoning 0.25-0.49`, `bad_human_escalation <0.25`) | Powers empirical hit-rate auditing and `/stats` monitoring. |
| **Prompt/Token Hardening** | Built-in in `0.4.7` (`common.py`) | `0.4.7` now sanitizes `tok.mask_token` in `build_sequence`/`build_head` and locks fast tokenizer via `_TOKENIZE_LOCK` | `_scrub()` strips `[MASK]` before calling `agent.predict()` | Safe defense-in-depth; zero conflict. |

### 1.2 New Capabilities & Gotchas in Upstream `laya 0.4.7`
1. **Dependencies bumped (`pyproject.toml`)**:
   - `transformers>=4.48.0` (required for ModernBERT / mmBERT support; our old `install_laya.sh` only specified `>=4.40.0`).
   - `mcp>=2.2.0` (when using `laya[mcp]`).
2. **Multi-Checkpoint Bundle (`convaiinnovations/laya`)**:
   - Upstream repo now ships three checkpoints:
     - `english` (root of `convaiinnovations/laya`): ModernBERT-large, 421M params, 512 context.
     - `typed-decisions` (`subfolder="typed-decisions"`): ModernBERT-large fine-tuned on typed workflow decisions, 421M params, **1024 context** (0.766 benchmark score vs 0.362 base on 2,000 typed decisions).
     - `multilingual` (`subfolder="multilingual"`): mmBERT-base, 322M params, up to 8192 context.
   - `laya.load("convaiinnovations/laya", device="cpu")` in `0.4.7` uses `allow_patterns` so it only downloads root files (~1.6 GB) instead of pulling the entire multi-checkpoint repo unless `subfolder=` is requested.
   - **Important `Router` gotcha**: Since `0.4.0`, `laya.Router()` defaults to `default="multilingual"` for short ambiguous ASCII strings unless `Router(default="english")` or `LAYA_DEFAULT_MODEL=english` is set. Setting `LAYA_DEFAULT_MODEL=english` in `laya.service` avoids accidental multilingual routing.
3. **Vectorized `agent.predict_batch(states, questions, batch_size=8, sort_by_length=True)`**:
   - Tokenizes question headers once per batch, sorts states by token length to minimize padding waste, and runs batched forward passes (1.4x–2.6x faster than our current `for item in items:` loop in `laya_classify`).
4. **Latent Bug Discovered in Our `laya_score` (`scripts/server.py` lines 250–258)**:
   - Upstream `laya/common.py` line 152 renders `score` criteria via:
     `["level %d: %s" % (i, render_criterion(c)) for i, c in enumerate(crit)]`
   - Our `laya_score` in `server.py` passed `crit` as a `dict` (`{"0": "trivial...", "1": "low...", ...}`). In Python, `enumerate(dict)` iterates over the **keys** (`"0"`, `"1"`, ...), silently discarding the rubric descriptions!
   - **Fix**: Convert `crit` in `laya_score` to an ordered `list[str]` of rubric descriptions (`["trivial, cosmetic, or negligible", ...]`) before passing to `agent.predict()`.
5. **Imlad Decision #17 Compliance Gap (`record_decision` in `scripts/server.py` lines 79 & 88)**:
   - Currently logs `input='{input_summary[:80]}'` to stdout (`journald`) and stores `input_summary[:80]` in `STATS["recent_decisions"]`.
   - Per **Imlad Decision #17 (Stateless-Transit Exemption)**, `record_decision()` must log **metadata only** (`input_len=len(input_summary)`), ensuring zero ServiceRocket work snippets ever touch Arwen's disk or memory ring buffer.
6. **Host Binding Drift (`arwen/laya/laya.service` vs `arwen/litellm/config.yaml`)**:
   - `arwen/laya/laya.service` in `yclian/machines` specifies `--host 127.0.0.1 --port 8500`, whereas `arwen/litellm/config.yaml` calls `http://100.78.131.8:8500/v1` and `scripts/install_laya.sh` uses `--host 0.0.0.0 --port 8500`.
   - **Fix**: Standardize `laya.service` to `--host 0.0.0.0 --port 8500` (protected by Arwen's UFW `tailscale0`-only firewall rule) so loopback (`127.0.0.1:8500`), Tailscale IP (`100.78.131.8:8500`), and `tailscale serve` (`https://laya.dikdik-dojo.ts.net`) all work deterministically.

---

## Part 2: How We Guarantee Future Upgrades Are Always Doable

1. **Strict Adapter Boundary (Zero Upstream Monkey-Patching)**
   - Never fork or edit site-packages inside `/srv/laya/venv`.
   - Consume only Upstream's stable public Python API: `laya.__version__`, `laya.load()`, `agent.predict()`, and `agent.predict_batch()`.
2. **Pinned Manifest (`scripts/requirements.txt` & `arwen/laya/requirements.txt`)**
   - Version-control `requirements.txt` alongside `server.py`.
   - Every upgrade is a deterministic `uv pip install -r /srv/laya/requirements.txt` with a 1-command rollback (`uv pip install laya==<previous_version>`).
3. **Canonical Source & Skill Sync**
   - Keep `yclian/skills:laya-system-one/scripts/server.py` and `yclian/machines:arwen/laya/server.py` byte-identical.
4. **Pre-Restart Contract & Redaction Smoke Test (`scripts/test_laya_contracts.py`)**
   - Before `systemctl restart laya` is declared healthy, run a deterministic contract test that verifies:
     1. `choice`, `noul`, `score` (list criteria), and `predict_batch` against `laya 0.4.7`.
     2. `POST /decide` payload schema required by `arwen/financial_signals.py` (`LayaTriageGate`).
     3. `POST /v1/chat/completions` OpenAI schema required by LiteLLM (`:4000`).
     4. `record_decision()` redaction invariant (asserts raw input strings never appear in stdout logs or `/stats`).

---

## Part 3: Step-by-Step Implementation Plan

### File Map
- **Create:** `laya-system-one/scripts/requirements.txt` (and mirror to `yclian/machines:arwen/laya/requirements.txt`) — Pinned dependency manifest for `/srv/laya/venv` (`laya==0.4.7`, `transformers>=4.48.0`, etc.).
- **Modify:** `laya-system-one/scripts/server.py` (and mirror to `yclian/machines:arwen/laya/server.py`) — Redact `input_summary` in `record_decision()` (Decision #17), fix `laya_score` list rubric bug, switch `laya_classify` to `agent.predict_batch()`, expose `laya_version` in `/health` and `/stats`, and support `LAYA_MODEL_SUBFOLDER` (for optional `typed-decisions` evaluation).
- **Modify:** `laya-system-one/scripts/install_laya.sh` (and `yclian/machines:arwen/laya/laya.service`) — Pin `laya==0.4.7`, `transformers>=4.48.0`, `mcp>=2.2.0`, align `--host 0.0.0.0 --port 8500`, and set `Environment="LAYA_DEFAULT_MODEL=english"`.
- **Create:** `laya-system-one/scripts/test_laya_contracts.py` (and mirror to `yclian/machines:arwen/laya/test_laya_contracts.py`) — Offline + live contract and Decision #17 zero-persistence test suite.

---

### Task 1: Add Pinned `requirements.txt` & Update Installer / Systemd Unit

**Files:**
- Create: `laya-system-one/scripts/requirements.txt`
- Modify: `laya-system-one/scripts/install_laya.sh`
- Modify (`yclian/machines`): `arwen/laya/laya.service`

- [ ] **Step 1: Create `laya-system-one/scripts/requirements.txt`**

```txt
# Arwen System 1 Decision Engine (svc:laya) pinned dependencies
laya==0.4.7
torch>=2.0.0
transformers>=4.48.0
safetensors>=0.4.0
huggingface-hub>=0.20.0
numpy>=1.20.0
fastapi>=0.110.0
uvicorn>=0.29.0
mcp>=2.2.0
pydantic>=2.6.0
```

- [ ] **Step 2: Update `laya-system-one/scripts/install_laya.sh` & `arwen/laya/laya.service` to fix host drift and pin default model**

Ensure `laya.service` has:

```ini
Environment="HF_HOME=/srv/laya/.cache/huggingface"
Environment="OMP_NUM_THREADS=4"
Environment="MKL_NUM_THREADS=4"
Environment="LAYA_DEFAULT_MODEL=english"
ExecStart=/srv/laya/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8500 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
```

---

### Task 2: Upgrade `scripts/server.py` (Decision #17 Redaction, `0.4.7` Batching, `laya_score` Fix)

**Files:**
- Modify: `laya-system-one/scripts/server.py`
- Mirror (`yclian/machines`): `arwen/laya/server.py`

- [ ] **Step 1: Expose `laya.__version__` and optional `LAYA_MODEL_SUBFOLDER` during model load**

In `scripts/server.py` (lines 28–38), update model initialization:

```python
MODEL_ID = os.environ.get("LAYA_MODEL", "convaiinnovations/laya")
MODEL_SUBFOLDER = os.environ.get("LAYA_MODEL_SUBFOLDER", "").strip() or None
LAYA_VERSION = getattr(laya, "__version__", "unknown")

t0 = time.time()
print(f"[laya] Loading model {MODEL_ID} (subfolder={MODEL_SUBFOLDER}, laya={LAYA_VERSION}) on CPU...")
if MODEL_SUBFOLDER:
    agent = laya.load(MODEL_ID, subfolder=MODEL_SUBFOLDER, device="cpu")
else:
    agent = laya.load(MODEL_ID, device="cpu")
print(f"[laya] Model loaded in {time.time() - t0:.2f}s")
```

- [ ] **Step 2: Enforce Imlad Decision #17 Zero-Persistence Logging in `record_decision()`**

In `scripts/server.py` (lines 58–91), replace `input_summary` persistence with `input_len` metadata only:

```python
def record_decision(
    tool_name: str,
    input_summary: str,
    decision: Any,
    confidence: float,
    latency_ms: float,
):
    STATS["total_requests"] += 1
    tier = classify_tier(confidence)
    STATS["tiers"][tier] += 1
    STATS["by_tool"][tool_name] = STATS["by_tool"].get(tool_name, 0) + 1
    input_len = len(input_summary) if input_summary else 0

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": tool_name,
        "tier": tier,
        "confidence": round(confidence, 4),
        "decision": decision,
        "latency_ms": round(latency_ms, 1),
        "input_len": input_len,
    }
    STATS["recent_decisions"].append(entry)
    if len(STATS["recent_decisions"]) > 50:
        STATS["recent_decisions"] = STATS["recent_decisions"][-50:]

    print(
        f"[laya-audit] tool={tool_name} tier={tier} conf={confidence:.3f} "
        f"decision={decision} latency={latency_ms:.1f}ms input_len={input_len}"
    )
    return tier
```

- [ ] **Step 3: Fix `laya_score` rubric serialization for `laya 0.4.7`**

In `scripts/server.py` (lines 240–272), normalize `rubric` to an ordered `list[str]` so `laya/common.py:render_options` (`enumerate(crit)`) renders full rubric descriptions instead of dict keys:

```python
    default_rubric = [
        "trivial, cosmetic, or negligible",
        "low priority or minor impact",
        "moderate importance, standard priority",
        "high priority, important or urgent",
        "critical, severe, blocking, or maximum priority",
    ]
    if rubric is None:
        crit = default_rubric
    elif isinstance(rubric, dict):
        crit = [
            str(v)
            for _, v in sorted(
                rubric.items(),
                key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else str(kv[0]),
            )
        ]
    else:
        crit = [str(item) for item in rubric]
```

*(Also update `laya_score` signature to `rubric: Optional[Union[Dict[str, str], List[str]]] = None`.)*

- [ ] **Step 4: Upgrade `laya_classify` to use `0.4.7` vectorized `agent.predict_batch()`**

In `scripts/server.py` (lines 305–361), replace the sequential `for idx, item in enumerate(items):` loop with `agent.predict_batch`:

```python
    t0 = time.time()
    crit = {c: c for c in categories}
    questions = {
        "category": {
            "type": "choice",
            "instruction": _scrub(instruction),
            "criteria": crit,
        }
    }
    scrubbed_items = [_scrub(item) for item in items]
    if hasattr(agent, "predict_batch") and len(scrubbed_items) > 1:
        batch_preds = agent.predict_batch(scrubbed_items, questions)
    else:
        batch_preds = [agent.predict(s, questions) for s in scrubbed_items]

    total_ms = (time.time() - t0) * 1000
    per_item_ms = total_ms / max(len(items), 1)
    results = []
    tier_counts = {"high_local": 0, "mid_cheap_rag": 0, "low_deep_reasoning": 0, "bad_human_escalation": 0}

    for idx, (item, res) in enumerate(zip(items, batch_preds)):
        out = res["category"]
        conf = float(out["confidence"])
        tier = record_decision("laya_classify", item, out["answer"], conf, per_item_ms)
        tier_counts[tier] += 1
        results.append({
            "index": idx,
            "input_len": len(item),
            "category": out["answer"],
            "confidence": round(conf, 4),
            "tier": tier,
            "action": recommended_action(tier),
            "probs": {k: round(float(v), 4) for k, v in out["probs"].items()},
        })
```

- [ ] **Step 5: Include `laya_version` and `model_subfolder` in `/health` and `/stats`**

In `scripts/server.py` (`health()` at line 500):

```python
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_ID,
        "subfolder": MODEL_SUBFOLDER,
        "laya_version": LAYA_VERSION,
        "device": "cpu",
    }
```

---

### Task 3: Add Contract & Decision #17 Zero-Persistence Test Suite

**Files:**
- Create: `laya-system-one/scripts/test_laya_contracts.py`

- [ ] **Step 1: Write `laya-system-one/scripts/test_laya_contracts.py`**

```python
"""Contract and Imlad Decision #17 zero-persistence tests for Arwen svc:laya."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch


class TestLayaServerContracts(unittest.TestCase):
    def test_record_decision_redacts_payload(self):
        """Imlad Decision #17: raw input text must NEVER appear in stdout or STATS."""
        with patch("laya.load") as mock_load:
            mock_load.return_value = MagicMock()
            import server

            server.STATS["recent_decisions"].clear()
            secret_payload = "CONFIDENTIAL_SERVICEROCKET_TICKET_SR-99999_SECRET_PAYLOAD"
            buf = io.StringIO()
            with redirect_stdout(buf):
                tier = server.record_decision(
                    tool_name="laya_decide",
                    input_summary=secret_payload,
                    decision="urgent",
                    confidence=0.88,
                    latency_ms=12.3,
                )

            stdout_log = buf.getvalue()
            self.assertEqual(tier, "high_local")
            self.assertNotIn(secret_payload, stdout_log)
            self.assertNotIn("SR-99999", stdout_log)
            self.assertIn(f"input_len={len(secret_payload)}", stdout_log)

            last_entry = server.STATS["recent_decisions"][-1]
            self.assertNotIn("input_preview", last_entry)
            self.assertEqual(last_entry["input_len"], len(secret_payload))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the unit test**

Run: `python -m unittest laya-system-one/scripts/test_laya_contracts.py`
Expected: `OK (1 test)`

---

### Task 4: Execute Live Upgrade on Arwen (Once Maintenance Completes Tomorrow)

- [ ] **Step 1: Verify Arwen reachability and snapshot current state**

```bash
ssh yclian@arwen.dikdik-dojo.ts.net "systemctl status laya --no-pager && /srv/laya/venv/bin/python -c 'import laya; print(getattr(laya, \"__version__\", \"pre-version\"))'"
```

- [ ] **Step 2: Copy updated `requirements.txt`, `server.py`, `test_laya_contracts.py`, and `laya.service` to Arwen**

```bash
scp laya-system-one/scripts/requirements.txt laya-system-one/scripts/server.py laya-system-one/scripts/test_laya_contracts.py yclian@arwen.dikdik-dojo.ts.net:/srv/laya/
```

- [ ] **Step 3: Upgrade `/srv/laya/venv` to `laya==0.4.7` and warm checkpoint cache**

```bash
ssh yclian@arwen.dikdik-dojo.ts.net "
  export PATH=\$HOME/.local/bin:\$PATH
  uv pip install --python /srv/laya/venv/bin/python --upgrade -r /srv/laya/requirements.txt
  HF_HOME=/srv/laya/.cache/huggingface /srv/laya/venv/bin/python -c '
import laya
print(\"Installed laya version:\", laya.__version__)
agent = laya.load(\"convaiinnovations/laya\", device=\"cpu\")
res = agent.predict(\"System check\", {\"ok\": {\"type\": \"noul\", \"instruction\": \"Is this a system check?\"}})
print(\"Warmup prediction:\", res)
'
"
```

- [ ] **Step 4: Run contract test on Arwen and restart `laya.service`**

```bash
ssh yclian@arwen.dikdik-dojo.ts.net "
  cd /srv/laya && /srv/laya/venv/bin/python -m unittest test_laya_contracts.py &&
  sudo systemctl daemon-reload &&
  sudo systemctl restart laya &&
  sleep 3 &&
  systemctl is-active laya
"
```

- [ ] **Step 5: Run 4-Point Fleet Smoke Verification**

1. **Health & Version Check**:
   ```bash
   curl -s http://arwen.dikdik-dojo.ts.net:8500/health | jq .
   ```
   Expected: `{"status": "ok", "model": "convaiinnovations/laya", "subfolder": null, "laya_version": "0.4.7", "device": "cpu"}`
2. **REST `/decide` Contract (`financial_signals.py` `LayaTriageGate`)**:
   ```bash
   curl -s -X POST http://arwen.dikdik-dojo.ts.net:8500/decide \
     -H "Content-Type: application/json" \
     -d '{"text":"Headline: Fed holds rates steady; Source: Reuters","options":{"actionable_catalyst":"Material macro catalyst","routine_noise":"Routine commentary"},"instruction":"Classify whether this macro headline is an actionable portfolio catalyst or routine market noise."}' | jq .
   ```
3. **LiteLLM `:4000` OpenAI Shim (`laya-decision`)**:
   ```bash
   ssh yclian@arwen.dikdik-dojo.ts.net "curl -s -X POST http://127.0.0.1:4000/v1/chat/completions -H 'Content-Type: application/json' -H 'Authorization: Bearer '\"\$LITELLM_MASTER_KEY\" -d '{\"model\":\"laya-decision\",\"messages\":[{\"role\":\"user\",\"content\":\"{\\\"text\\\":\\\"margin utilization at 92%\\\",\\\"options\\\":[\\\"normal\\\",\\\"breach\\\"]}\"}]}'"
   ```
4. **Decision #17 `journald` Zero-Payload Audit**:
   ```bash
   ssh yclian@arwen.dikdik-dojo.ts.net "journalctl -u laya -n 10 --no-pager"
   ```
   Expected: `[laya-audit] tool=rest_decide tier=... input_len=46` (zero raw input text).

- [ ] **Step 6: Sync `yclian/machines:arwen/laya/server.py`**

Copy the verified `laya-system-one/scripts/server.py` and `requirements.txt` to `yclian/machines:arwen/laya/` and commit both repositories cleanly.

---

### Task 5: Empirical Evaluation Harness (`0.4.7` Base vs `typed-decisions` vs `Plumb-4B`)

As documented in `2026-09-21 System 1 Decision Engine (Laya) Architecture & Eval.md`, upstream `0.4.7` includes the `convaiinnovations/laya` `subfolder="typed-decisions"` checkpoint (1024-token context, 0.766 vs 0.362 accuracy on structured workflow routing).

- [ ] **Step 1: Curate 30–50 labeled fleet test cases in `laya-system-one/evals/fleet_eval_cases.jsonl`** across:
  - `financial_signals.py` macro headlines (`actionable_catalyst` vs `routine_noise`)
  - `gmail-drift-miner` sender/subject pairs (`tier1_human`, `transactional_receipt`, `newsletter_promo`)
  - Python/bash traceback snippets (`transient_network_retry`, `auth_or_permission_denied`, `syntax_or_type_bug`, `missing_dependency_or_file`)
- [ ] **Step 2: Benchmark 3 checkpoints side-by-side on Arwen CPU**:
  1. `laya.load("convaiinnovations/laya", device="cpu")` (Base English 512-ctx)
  2. `laya.load("convaiinnovations/laya", subfolder="typed-decisions", device="cpu")` (Typed-Decisions 1024-ctx)
  3. Local Ollama `qwen3.5:2b` / `Plumb-4B` via `:11434`
- [ ] **Step 3: Record results in `2026-09-21 System 1 Decision Engine (Laya) Architecture & Eval.md` §7** and set `LAYA_MODEL_SUBFOLDER=typed-decisions` in `laya.service` if `typed-decisions` wins on calibration and F1.

---

## Part 4: Fleet Utilization Refresher & Recommendations

Per [`ARCH.md`](../../ARCH.md), [`references/harness-control-retrospective.md`](../../references/harness-control-retrospective.md), and Imlad Decisions #16 & #17:

### 1) Interactive Coding Agents (Antigravity, Claude Code, OpenCode on Aili / Suzu)
- **What NOT to do (Decision #16 Amendment — Teknium's Law)**:
  - **Do NOT** put Laya inside mandatory per-turn `PreToolUse` / `PostToolUse` harness hooks that mutate system prompts or prune tool schemas mid-session. Prompt cache reads give a **90% discount** (`$0.50/MTok` vs `$5.00/MTok` on Opus); breaking the KV cache prefix costs dollars to save pennies.
- **Where Interactive Agents SHOULD use Laya (`https://laya.dikdik-dojo.ts.net/mcp`)**:
  1. **In-Turn Bulk Sorting (`laya_classify`)**: Categorizing **20–100 items in a single turn** (e.g., sorting 60 git commits by domain, classifying 50 Jira issues/PRs, or triaging a batch of unfiled Obsidian notes). With `0.4.7`'s `predict_batch`, 50 items classify in <300ms for `$0.00` without bloating the frontier LLM's output token budget.
  2. **Traceback & Dirty-Worktree Triage (`laya_triage_error`, `laya_triage_git`)**: Passing raw 200-line stack traces or `git status --short` + `git diff --stat` to get an immediate `tier` + prescriptive action (`transient_network_retry` vs `syntax_or_type_bug`) before burning reasoning tokens.
  3. **Authoring Pipeline Code**: Using the `laya-system-one` skill so coding agents write `LayaTriageGate` / REST calls into new automation scripts rather than wiring expensive LLM API calls for binary/enum gates.

### 2) Hermes Tasks & Telegram Bots (Arwen & Adara `:8642`)
Autonomous cron jobs and headless loops have **no warm multi-turn KV cache to protect**, making them Laya's highest-ROI surface:
- **Live Today on Arwen**:
  - **`daily-macro-radar` (`arwen/financial_signals.py`)**: `LayaTriageGate` calls `http://127.0.0.1:8500/decide` on every scraped macro/sentiment headline (`actionable_catalyst` vs `routine_noise`). If `tier == "high_local"` and `decision == "routine_noise"`, it drops the item before downstream scoring.
- **High-Leverage Next Integrations for Hermes Crons & Bots**:
  1. **Telegram Bot Ingress Router (Arwen & Adara)**: Before waking up a full Hermes LLM session on an incoming Telegram message or forwarded link, call `POST /decide` (`~15ms`) to classify intent into `[margin_fx_check, portfolio_query, calendar_tbd, social_dispatch_pitch, obsidian_clip, general_chat]` and dispatch deterministic scripts directly when `confidence >= 0.75`.
  2. **`people-refill-radar` (Arwen Mon 09:05)**: Use `laya_classify` (or `laya_eval` combining `choice` + `noul`) on scraped calendar events and Expense IQ dining descriptors to filter genuine social/1:1 gatherings from solo meals, flights, or internal recurring blocks before fuzzy-matching `People I met since 2025.md`.
  3. **`calendar-tbd-recommender` (Arwen Mon 09:00)**: Use `laya_decide` on event titles/attendees to infer meal vibe (`business_quiet`, `casual_catchup`, `celebration_wine`, `quick_coffee`) before querying your personal taste graph.
  4. **`weekly-social-dispatch` (Adara Tue/Fri)**: Pre-score harvested git commit messages and work-week artifacts via `laya_score` (0–4 editorial signal rubric) over Tailscale (`http://arwen.dikdik-dojo.ts.net:8500/decide`) so the pitch generator only reads level 3–4 commits.

### 3) Other Fleet Possibilities
1. **Gmail Gateway Pipelines (`gmail-drift-miner` & `gmail-forward-watchdog`)**:
   - Feed Catch-All sender + subject + snippet batches into `laya_classify` with categories `["human_vip_correspondence", "transactional_receipt_or_alert", "marketing_or_newsletter_drift", "security_or_otp"]`. High-confidence `marketing_or_newsletter_drift` items immediately become candidate Terraform diffs for `filters.auto.tfvars.json`, while `human_vip_correspondence` triggers priority backfill in `gmail-forward-watchdog`.
2. **Oxana / Imlad Ask (`:8765` on Arwen) & "Clip & Compile" Gate**:
   - **Query Router**: Classify incoming search queries (`exact_keyword_lookup` -> FTS5 only, `conceptual_synthesis` -> Hybrid Vector + Reranker, `temporal_journal_recap` -> Date-scoped filter) in 12ms before touching `bge-reranker-v2-m3`.
   - **Vault Deduplication Gate**: When clipping a new article into `Clippings/`, run `laya_noul` + `laya_score` against the top-3 existing wiki articles to decide `["skip_duplicate", "append_new_angle", "compile_new_concept"]` before calling an LLM compiler.
3. **Perplexity -> Oxana Sync (`perplexity-oxana-sync`, Arwen 04:15)**:
   - Score scraped Perplexity threads (`0–4` durability rubric via `laya_score`) to automatically drop ephemeral throwaway lookups (e.g., quick syntax checks, flight lookups) before staging markdown notes into the Obsidian inbox.
4. **LiteLLM Reflex Model (`laya-decision` on `:4000`)**:
   - Any external tool, n8n/webhook, or OpenAI-SDK client on the Tailnet can point at `http://arwen.dikdik-dojo.ts.net:4000/v1` with `model="laya-decision"` and get structured JSON classification + confidence tiering through the standard OpenAI Chat Completions format.
