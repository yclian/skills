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
import logging
import contextlib
from typing import Any, Dict, List, Optional, Union
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import laya
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("laya-service")

# Initialize MCP Server
mcp = MCPServer("laya")

# Global Laya agent
agent: Optional[laya.Agent] = None

# MCP Tool: laya_classify
@mcp.tool()
def laya_classify(
    items: List[str],
    categories: Dict[str, str],
    instructions: str = "Classify each item into the best matching category."
) -> List[Dict[str, Any]]:
    """Ultra-fast (~35ms) non-autoregressive classifier powered by ModernBERT.
    Use this tool FIRST for bulk triage, categorization, and sorting tasks
    (emails, commit messages, log lines, candidates) without burning LLM tokens.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    results = []
    for item in items:
        q = {
            "cat": {
                "type": "choice",
                "instructions": instructions,
                "criteria": categories
            }
        }
        res = agent.predict(item, q)
        ans = res.get("answers", {}).get("cat", {})
        results.append({
            "item": item,
            "category": ans.get("choice"),
            "confidence": ans.get("confidence"),
            "probabilities": ans.get("probabilities", {})
        })
    return results

# MCP Tool: laya_decide
@mcp.tool()
def laya_decide(
    text: str,
    options: Dict[str, str],
    instructions: str = "Select the optimal choice for this input."
) -> Dict[str, Any]:
    """Execute a single calibrated decision across an input text in ~35ms.
    Returns typed choice, calibrated confidence score, and probability distribution.
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
    res = agent.predict(text, q)
    ans = res.get("answers", {}).get("decision", {})
    return {
        "choice": ans.get("choice"),
        "confidence": ans.get("confidence"),
        "probabilities": ans.get("probabilities", {})
    }

# MCP Tool: laya_noul
@mcp.tool()
def laya_noul(
    text: str,
    condition: str
) -> Dict[str, Any]:
    """Evaluate a yes/no condition using calibrated probability (0.0 to 1.0).
    Ideal for binary gates, compliance checks, or trigger filters without competing options.
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    q = {
        "condition": {
            "type": "noul",
            "instructions": condition
        }
    }
    res = agent.predict(text, q)
    ans = res.get("answers", {}).get("condition", {})
    return {
        "yes_probability": ans.get("noul"),
        "confidence": ans.get("confidence"),
        "passes_threshold_80": (ans.get("noul", 0.0) >= 0.80)
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
    res = agent.predict(text, q)
    ans = res.get("answers", {}).get("metric", {})
    return {
        "expected_score": ans.get("score"),
        "confidence": ans.get("confidence"),
        "probabilities": ans.get("probabilities", {}),
        "legend": ans.get("legend", {})
    }

# MCP Tool: laya_eval (Multi-Question Parallel State Evaluation)
@mcp.tool()
def laya_eval(
    state: Union[str, Dict[str, Any]],
    questions: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Evaluate multiple independent System 1 questions (choice, noul, score)
    over a single shared state in one parallel forward pass (~40ms total).
    """
    if agent is None:
        raise RuntimeError("Laya model not ready")
    
    res = agent.predict(state, questions)
    return {
        "answers": res.get("answers", {}),
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
    input_text = f"Context: {context}\nError:\n{error_traceback}" if context else error_traceback
    res = agent.predict(input_text, q)
    ans = res.get("answers", {}).get("defect", {})
    defect_type = ans.get("choice", "LOGIC_OR_ASSERTION")
    
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "model": "convaiinnovations/laya",
        "backbone": "ModernBERT-large (395M)",
        "device": "cpu",
        "ready": agent is not None
    }

class DirectDecideRequest(BaseModel):
    text: Union[str, dict, list]
    options: Optional[Dict[str, str]] = None
    instructions: Optional[str] = "Select the best matching option."
    query: Optional[Dict[str, Any]] = None

@app.post("/decide")
def direct_decide(req: DirectDecideRequest):
    if agent is None:
        raise HTTPException(status_code=503, detail="Laya agent loading")
    t0 = time.time()
    if req.query:
        q = req.query
    else:
        q = {
            "decision": {
                "type": "choice",
                "instructions": req.instructions,
                "criteria": req.options or {}
            }
        }
    res = agent.predict(req.text, q)
    latency_ms = (time.time() - t0) * 1000
    return {
        "answers": res.get("answers", {}),
        "latency_ms": round(latency_ms, 2)
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if agent is None:
        raise HTTPException(status_code=503, detail="Laya agent loading")
    
    body = await request.json()
    messages = body.get("messages", [])
    model_name = body.get("model", "laya-decision")
    
    user_text = ""
    system_text = ""
    for m in messages:
        if m.get("role") == "system":
            system_text = m.get("content", "")
        elif m.get("role") == "user":
            user_text = m.get("content", "")
            
    full_text = f"Context: {system_text}\nPrompt: {user_text}" if system_text else user_text
    
    q = {
        "routing": {
            "type": "choice",
            "instructions": "Classify the prompt for optimal model routing.",
            "criteria": {
                "FAST_DECISION": "Simple intent, classification, triage, formatting, short enum",
                "ESCALATE_SYSTEM_2": "Complex coding, multi-file edits, architecture, deep reasoning",
                "DROP_NOISE": "Automated alert noise, marketing drift, irrelevant background event"
            }
        }
    }
    
    t0 = time.time()
    res = agent.predict(full_text, q)
    latency_ms = (time.time() - t0) * 1000
    ans = res.get("answers", {}).get("routing", {})
    
    out_payload = json.dumps({
        "choice": ans.get("choice", "FAST_DECISION"),
        "confidence": ans.get("confidence", 1.0),
        "latency_ms": round(latency_ms, 2),
        "probabilities": ans.get("probabilities", {})
    })
    
    return {
        "id": f"chatcmpl-laya-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": out_payload
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(full_text.split()),
            "completion_tokens": len(out_payload.split()),
            "total_tokens": len(full_text.split()) + len(out_payload.split())
        }
    }

# Mount MCP streamable HTTP application at root
sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
mcp_app = mcp.streamable_http_app(transport_security=sec)
app.mount("", mcp_app)
