"""
Laya Fast Non-Autoregressive Decision Service & MCP Gateway
Runs on CPU (port 8500), exposed via Tailscale or local network.
Endpoints:
- /health: Service health and model status
- /decide: Direct JSON decision API
- /v1/chat/completions: OpenAI-compatible API for LiteLLM
- /mcp: Model Context Protocol (MCP) streamable HTTP endpoint
"""

import os
import json
import time
import datetime
import logging
import contextlib
from collections import Counter, deque
from threading import Lock
from typing import Any, Dict, List, Optional, Union
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import laya
import torch
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

# Limit intra-op CPU threads to prevent CPU thrashing
torch.set_num_threads(int(os.getenv("LAYA_NUM_THREADS", "4")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("laya-service")

# Initialize MCP Server
mcp = MCPServer("laya")

# Global Laya agent
agent: Optional[laya.Agent] = None

# Stats and Observability Tracking
stats_lock = Lock()
STATS: Dict[str, Any] = {
    "start_time": time.time(),
    "total_decisions": 0,
    "total_latency_ms": 0.0,
    "by_tool": Counter(),
    "by_choice": Counter(),
    "by_tier": Counter(),
    "recent_decisions": deque(maxlen=50)
}

def get_confidence_tier(confidence: Optional[float]) -> str:
    """Map calibrated confidence score to routing tier."""
    if confidence is None:
        return "unscored"
    if confidence >= 0.75:
        return "high_local"
    elif confidence >= 0.50:
        return "mid_cheap_rag"
    elif confidence >= 0.25:
        return "low_deep_reasoning"
    else:
        return "bad_human_escalation"

def record_decision(
    tool: str,
    input_text: Union[str, Any],
    choice: Any,
    confidence: Optional[float],
    latency_ms: float
):
    """Update running metrics in-memory and write structured decision log to journald."""
    tier = get_confidence_tier(confidence)
    with stats_lock:
        STATS["total_decisions"] += 1
        STATS["total_latency_ms"] += latency_ms
        STATS["by_tool"][tool] += 1
        STATS["by_choice"][str(choice)] += 1
        STATS["by_tier"][tier] += 1
        
        # Keep ring buffer of last 50 decisions
        STATS["recent_decisions"].append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tool": tool,
            "choice": choice,
            "confidence": round(confidence, 4) if confidence is not None else None,
            "tier": tier,
            "latency_ms": round(latency_ms, 2),
            "input": str(input_text)[:120]
        })
    
    # Structured one-line log for journalctl / tailscale observability
    conf_str = f"conf={confidence:.2f}" if confidence is not None else "conf=None"
    tier_str = f"tier={tier}"
    clean_inp = str(input_text).replace("\n", " ")[:90]
    logger.info(f"⚡ [{tool}] choice='{choice}' {conf_str} {tier_str} latency={latency_ms:.1f}ms | input='{clean_inp}'")

def _scrub(text: Any) -> Any:
    """Strip [MASK] or special syntax to avoid injection into ModernBERT's MLM heads."""
    if isinstance(text, str):
        return text.replace("[MASK]", " ").replace("<mask>", " ")
    return text

# MCP Tool: laya_classify
@mcp.tool()
def laya_classify(
    text: str,
    options: List[str],
    instructions: str = "Classify the text into exactly one category."
) -> Dict[str, Any]:
    """Classify text into a simple list of candidate labels in 35ms.
    Returns the predicted choice, calibrated confidence score, and probability distribution.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    q = {
        "category": {
            "type": "choice",
            "instructions": instructions,
            "criteria": {opt: opt for opt in options}
        }
    }
    t0 = time.time()
    res = agent.predict(_scrub(text), q)
    latency_ms = (time.time() - t0) * 1000
    ans = res.get("answers", {}).get("category", {})
    choice = ans.get("choice")
    conf = ans.get("confidence")
    record_decision("laya_classify", text, choice, conf, latency_ms)
    return {
        "choice": choice,
        "confidence": conf,
        "probabilities": ans.get("probabilities", {})
    }

# MCP Tool: laya_decide
@mcp.tool()
def laya_decide(
    text: str,
    options: Dict[str, str],
    instructions: str = "Select the best matching option based on the criteria."
) -> Dict[str, Any]:
    """Semantic routing and decision making over detailed candidate options.
    Options is a dictionary mapping option_key -> description/criteria.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    q = {
        "decision": {
            "type": "choice",
            "instructions": instructions,
            "criteria": options
        }
    }
    t0 = time.time()
    res = agent.predict(_scrub(text), q)
    latency_ms = (time.time() - t0) * 1000
    ans = res.get("answers", {}).get("decision", {})
    choice = ans.get("choice")
    conf = ans.get("confidence")
    record_decision("laya_decide", text, choice, conf, latency_ms)
    return {
        "choice": choice,
        "confidence": conf,
        "probabilities": ans.get("probabilities", {})
    }

# MCP Tool: laya_noul
@mcp.tool()
def laya_noul(
    text: str,
    condition: str
) -> Dict[str, Any]:
    """Calibrated probability evaluation (0.0 to 1.0) of whether a condition is TRUE.
    Native implementation of Kahneman's fast intuitive true/false check.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    q = {
        "condition": {
            "type": "noul",
            "instructions": condition
        }
    }
    t0 = time.time()
    res = agent.predict(_scrub(text), q)
    latency_ms = (time.time() - t0) * 1000
    ans = res.get("answers", {}).get("condition", {})
    prob = ans.get("noul", 0.0)
    conf = ans.get("confidence")
    passes = (prob >= 0.80)
    choice = f"YES ({prob:.2f})" if passes else f"NO ({prob:.2f})"
    record_decision("laya_noul", f"{condition} | {text}", choice, conf, latency_ms)
    return {
        "yes_probability": prob,
        "confidence": conf,
        "passes_threshold_80": passes
    }

# MCP Tool: laya_score
@mcp.tool()
def laya_score(
    text: str,
    levels: Dict[str, str],
    instructions: str = "Score the position along this ordered dimension."
) -> Dict[str, Any]:
    """Score text across ordered semantic levels (e.g. {"1": "Low", "2": "Medium", "3": "High"}).
    Returns expected probability-weighted score and the distribution across levels.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    q = {
        "metric": {
            "type": "score",
            "instructions": instructions,
            "criteria": levels
        }
    }
    t0 = time.time()
    res = agent.predict(_scrub(text), q)
    latency_ms = (time.time() - t0) * 1000
    ans = res.get("answers", {}).get("metric", {})
    score = ans.get("score")
    conf = ans.get("confidence")
    record_decision("laya_score", f"{instructions} | {text}", f"score={score}", conf, latency_ms)
    return {
        "expected_score": score,
        "confidence": conf,
        "probabilities": ans.get("probabilities", {}),
        "legend": ans.get("legend", {})
    }

# MCP Tool: laya_eval (Multi-Question Parallel State Evaluation)
@mcp.tool()
def laya_eval(
    state: Union[str, Dict[str, Any]],
    questions: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate multiple questions against arbitrary state in ONE forward pass (~35ms).
    Matches the native system_one paradigm. Questions can mix choice, noul, and score.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    clean_state = _scrub(state) if isinstance(state, str) else state
    t0 = time.time()
    res = agent.predict(clean_state, questions)
    latency_ms = (time.time() - t0) * 1000
    answers = res.get("answers", {})
    record_decision("laya_eval", str(state), f"{len(questions)} questions", 1.0, latency_ms)
    return {
        "answers": answers,
        "usage": res.get("usage", {})
    }

# MCP Tool: laya_triage_error (Execution Error Triage)
@mcp.tool()
def laya_triage_error(
    error_traceback: str,
    context: Optional[str] = None
) -> Dict[str, Any]:
    """Triage a shell error, stack trace, or model blowout in 35ms.
    Categorizes the root failure and prescribes immediate recovery action.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    categories = {
        "SYNTAX_FORMAT_ERROR": "JSON parsing error, missing brackets, markdown fence bleed",
        "PERMISSION_AUTH_DENIED": "Permission denied, 401/403 HTTP, missing API token or credentials",
        "MISSING_DEPENDENCY": "ModuleNotFoundError, command not found, ENOENT, missing library/binary",
        "TIMEOUT_OR_NETWORK": "Connection refused, socket timeout, 502/504 gateway failure",
        "RESOURCE_EXHAUSTION": "Out of memory, VRAM CUDA OOM, disk space full, CPU rate limit",
        "LOGIC_OR_ASSERTION": "AssertionError, test failure, logic invariant breach"
    }
    
    q = {
        "defect": {
            "type": "choice",
            "instructions": "Identify the root operational failure mode from this error trace.",
            "criteria": categories
        }
    }
    # Take the tail of the traceback (where root exception and error message live)
    lines = error_traceback.strip().splitlines()
    tail_trace = "\n".join(lines[-35:]) if len(lines) > 35 else error_traceback
    clean_trace = _scrub(tail_trace)
    clean_context = _scrub(context) if context else None
    input_text = f"Context: {clean_context}\nError:\n{clean_trace}" if clean_context else clean_trace

    t0 = time.time()
    res = agent.predict(input_text, q)
    latency_ms = (time.time() - t0) * 1000
    ans = res.get("answers", {}).get("defect", {})
    defect_type = ans.get("choice", "LOGIC_OR_ASSERTION")
    conf = ans.get("confidence")
    record_decision("laya_triage_error", clean_trace[-60:], defect_type, conf, latency_ms)
    
    # Prescriptive recommendations
    action_map = {
        "SYNTAX_FORMAT_ERROR": "FAST_REPAIR: Apply deterministic regex to strip fences or balance braces.",
        "PERMISSION_AUTH_DENIED": "AUTH_CHECK: Verify bearer token or environment credential.",
        "MISSING_DEPENDENCY": "INSTALL: Run package manager (uv/pip/npm) to provision missing module.",
        "TIMEOUT_OR_NETWORK": "RETRY_EXPONENTIAL: Transient network failure; retry with backoff.",
        "RESOURCE_EXHAUSTION": "FALLBACK_CLOUD: Free local VRAM or shunt to cloud fallback.",
        "LOGIC_OR_ASSERTION": "ESCALATE_SYSTEM_2: Involve Gemini Pro or Claude for semantic refactor."
    }
    
    return {
        "defect_type": defect_type,
        "confidence": ans.get("confidence"),
        "prescribed_action": action_map.get(defect_type, "RETRY"),
        "probabilities": ans.get("probabilities", {})
    }

# MCP Tool: laya_triage_git (Git Commit / Diff Classification)
@mcp.tool()
def laya_triage_git(
    diff_or_message: str
) -> Dict[str, Any]:
    """Classify a git diff, staged status, or commit message into conventional change type and risk level in 35ms."""
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    categories = {
        "FEAT": "New user-facing functionality or capability",
        "FIX": "Bug fix, patch, or error resolution",
        "DOCS": "Documentation, comments, markdown, or README updates",
        "REFACTOR": "Internal code cleanup, restructuring, or renaming without behavior change",
        "CHORE": "Build, CI/CD, dependencies, tooling, or minor maintenance"
    }
    
    q = {
        "change_type": {
            "type": "choice",
            "instructions": "Determine the conventional commit change type.",
            "criteria": categories
        },
        "is_breaking_or_high_risk": {
            "type": "noul",
            "instructions": "Is this change high-risk, breaking, or destructive?"
        }
    }
    clean_input = _scrub(diff_or_message[:2000])
    t0 = time.time()
    res = agent.predict(clean_input, q)
    latency_ms = (time.time() - t0) * 1000
    
    ans_type = res.get("answers", {}).get("change_type", {})
    ans_risk = res.get("answers", {}).get("is_breaking_or_high_risk", {})
    
    c_type = ans_type.get("choice", "CHORE")
    conf = ans_type.get("confidence")
    risk_prob = ans_risk.get("noul", 0.0)
    
    record_decision("laya_triage_git", clean_input[:60], f"{c_type} (risk={risk_prob:.2f})", conf, latency_ms)
    
    return {
        "change_type": c_type,
        "confidence": conf,
        "high_risk_probability": risk_prob,
        "is_high_risk": risk_prob >= 0.70
    }

# MCP Tool: laya_is_safe (Command Safety Guardrail)
@mcp.tool()
def laya_is_safe(
    command: str,
    context: Optional[str] = None
) -> Dict[str, Any]:
    """Fast guardrail checking if a shell command, script, or SQL query is destructive or risky (drops tables, deletes files, force pushes)."""
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    q = {
        "is_destructive": {
            "type": "noul",
            "instructions": "Is this command or action destructive, deleting data, force pushing, dropping databases, or killing system processes?"
        }
    }
    clean_cmd = _scrub(f"{context or ''} | {command}" if context else command)
    t0 = time.time()
    res = agent.predict(clean_cmd, q)
    latency_ms = (time.time() - t0) * 1000
    
    ans = res.get("answers", {}).get("is_destructive", {})
    prob_destructive = ans.get("noul", 0.0)
    conf = ans.get("confidence")
    is_safe = prob_destructive < 0.35
    
    record_decision("laya_is_safe", clean_cmd[:60], "SAFE" if is_safe else f"RISKY ({prob_destructive:.2f})", conf, latency_ms)
    
    return {
        "is_safe": is_safe,
        "destructive_probability": prob_destructive,
        "confidence": conf,
        "verdict": "SAFE" if is_safe else "CONFIRMATION_REQUIRED"
    }

# Lifespan context manager for FastAPI
@contextlib.asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    global agent
    logger.info("Preloading Laya model (convaiinnovations/laya)...")
    t0 = time.time()
    agent = laya.load("convaiinnovations/laya", device="cpu")
    logger.info(f"Laya model loaded in {time.time() - t0:.2f}s")
    
    # Run MCP StreamableHTTP session manager
    async with mcp.session_manager.run():
        yield

# Main FastAPI App
app = FastAPI(title="Laya Decision Service", version="1.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP endpoint
app.mount("/mcp", mcp.streamable_http_app(transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)))

# REST Request Models
class DecideRequest(BaseModel):
    text: Optional[str] = None
    state: Optional[Union[str, Dict[str, Any]]] = None
    questions: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, str]] = None
    instructions: Optional[str] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.0
    max_tokens: Optional[int] = 100

@app.get("/health")
def health():
    uptime = time.time() - STATS["start_time"]
    return {
        "status": "healthy",
        "model": "convaiinnovations/laya",
        "backbone": "ModernBERT-large (395M)",
        "device": "cpu",
        "ready": agent is not None,
        "uptime_seconds": round(uptime, 1),
        "total_decisions": STATS["total_decisions"]
    }

@app.get("/stats")
def get_stats():
    """Live telemetry stats on total inferences, avg latency, and 4-tier routing summary."""
    with stats_lock:
        uptime = time.time() - STATS["start_time"]
        total = STATS["total_decisions"]
        avg_latency = (STATS["total_latency_ms"] / total) if total > 0 else 0.0
        
        tier_high = STATS["by_tier"]["high_local"]
        tier_mid = STATS["by_tier"]["mid_cheap_rag"]
        tier_low = STATS["by_tier"]["low_deep_reasoning"]
        tier_bad = STATS["by_tier"]["bad_human_escalation"]
        
        pct_high = f"{(tier_high / total * 100):.1f}%" if total > 0 else "0.0%"
        pct_mid = f"{(tier_mid / total * 100):.1f}%" if total > 0 else "0.0%"
        pct_low = f"{(tier_low / total * 100):.1f}%" if total > 0 else "0.0%"
        pct_bad = f"{(tier_bad / total * 100):.1f}%" if total > 0 else "0.0%"
        
        return {
            "uptime_seconds": round(uptime, 1),
            "total_decisions": total,
            "avg_latency_ms": round(avg_latency, 2),
            "routing_summary": {
                "system_1_resolved_pct": pct_high,
                "system_2_cheap_rag_pct": pct_mid,
                "system_2_deep_reasoning_pct": pct_low,
                "human_escalation_pct": pct_bad
            },
            "confidence_tiers": {
                "high_local": {
                    "threshold": ">= 0.75",
                    "action": "Local System 1 (ModernBERT CPU)",
                    "count": tier_high,
                    "percentage": pct_high
                },
                "mid_cheap_rag": {
                    "threshold": "0.50 - 0.74",
                    "action": "Fast Cloud / Speculative RAG (Flash / Qwen 35B)",
                    "count": tier_mid,
                    "percentage": pct_mid
                },
                "low_deep_reasoning": {
                    "threshold": "0.25 - 0.49",
                    "action": "Deep System 2 (Gemini Pro / Claude Sonnet)",
                    "count": tier_low,
                    "percentage": pct_low
                },
                "bad_human_escalation": {
                    "threshold": "< 0.25",
                    "action": "Human Escalation / Ambiguity Tripwire",
                    "count": tier_bad,
                    "percentage": pct_bad
                }
            },
            "by_tool": dict(STATS["by_tool"]),
            "by_choice": dict(STATS["by_choice"]),
            "recent_decisions": list(STATS["recent_decisions"])
        }

@app.post("/stats/reset")
def reset_stats():
    """Reset live telemetry counters."""
    with stats_lock:
        STATS["start_time"] = time.time()
        STATS["total_decisions"] = 0
        STATS["total_latency_ms"] = 0.0
        STATS["by_tool"].clear()
        STATS["by_choice"].clear()
        STATS["by_tier"].clear()
        STATS["recent_decisions"].clear()
    return {"status": "reset_successful"}

@app.post("/decide")
def decide(req: DecideRequest):
    """Direct REST decision endpoint compatible with both raw dict criteria and multi-question payloads."""
    if agent is None:
        raise HTTPException(status_code=503, detail="Laya model not ready")
    
    t0 = time.time()
    
    # If questions dict provided, run native multi-question predict
    if req.questions is not None:
        state_payload = req.state if req.state is not None else (req.text or "")
        clean_state = _scrub(state_payload) if isinstance(state_payload, str) else state_payload
        res = agent.predict(clean_state, req.questions)
        latency = (time.time() - t0) * 1000
        record_decision("rest_decide_multi", str(state_payload), f"{len(req.questions)} questions", 1.0, latency)
        return {
            "answers": res.get("answers", {}),
            "usage": res.get("usage", {}),
            "latency_ms": round(latency, 2)
        }
    
    # If options dict provided, formulate choice question
    if req.options is not None:
        text_payload = req.text if req.text is not None else str(req.state or "")
        q = {
            "decision": {
                "type": "choice",
                "instructions": req.instructions or "Select the best matching option.",
                "criteria": req.options
            }
        }
        res = agent.predict(_scrub(text_payload), q)
        latency = (time.time() - t0) * 1000
        ans = res.get("answers", {}).get("decision", {})
        choice = ans.get("choice")
        conf = ans.get("confidence")
        record_decision("rest_decide_choice", text_payload, choice, conf, latency)
        return {
            "answers": res.get("answers", {}),
            "usage": res.get("usage", {}),
            "latency_ms": round(latency, 2)
        }
    
    raise HTTPException(status_code=400, detail="Must provide either 'questions' or 'options'")

@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible chat completion endpoint so LiteLLM can route to Laya."""
    if agent is None:
        raise HTTPException(status_code=503, detail="Laya model not ready")
    
    user_msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    t0 = time.time()
    clean_user_msg = _scrub(user_msg)
    
    # Try parsing user_msg as JSON for structured questions
    parsed_json = None
    try:
        parsed_json = json.loads(clean_user_msg)
    except Exception:
        pass
    
    if isinstance(parsed_json, dict) and "questions" in parsed_json:
        state = parsed_json.get("state", "")
        questions = parsed_json["questions"]
        res = agent.predict(_scrub(state) if isinstance(state, str) else state, questions)
        content_out = json.dumps(res.get("answers", {}))
        conf = 1.0
        choice = f"{len(questions)} answers"
    else:
        # Default single-pass sentiment/intent classification
        q = {
            "intent": {
                "type": "choice",
                "instructions": "Classify the primary operational intent of the input.",
                "criteria": {
                    "QUERY": "User is asking a question or querying status",
                    "ACTION": "User is instructing execution or running a command",
                    "FEEDBACK": "User is providing evaluation, corrections, or comments",
                    "UNCLEAR": "Ambiguous, conversational filler, or undefined request"
                }
            }
        }
        res = agent.predict(clean_user_msg, q)
        ans = res.get("answers", {}).get("intent", {})
        choice = ans.get("choice", "QUERY")
        conf = ans.get("confidence")
        content_out = json.dumps({"intent": choice, "confidence": conf})
    
    latency = (time.time() - t0) * 1000
    record_decision("litellm_chat_completion", clean_user_msg, choice, conf, latency)
    
    return {
        "id": f"chatcmpl-laya-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content_out
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(clean_user_msg.split()),
            "completion_tokens": len(content_out.split()),
            "total_tokens": len(clean_user_msg.split()) + len(content_out.split())
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
