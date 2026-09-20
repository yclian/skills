# Architecture: Non-Autoregressive "System 1" Decision Engine

This document specifies the technical architecture, internal mechanics, hardware accounting, and integration topologies for **Laya**—a local, non-autoregressive "System 1" decision engine.

---

## 1. Conceptual Framework: System 1 vs. System 2

Daniel Kahneman's dual-process cognitive framework (*Thinking, Fast and Slow*) distinguishes between two modes of thought:

```mermaid
flowchart LR
    subgraph S1["System 1: Fast & Intuitive (Laya)"]
        direction TB
        A1["Non-Autoregressive ModernBERT (395M)"]
        A2["Single Forward Pass (~35ms on CPU)"]
        A3["Zero KV-Cache Overhead (0 MB)"]
        A4["Typed Judgments & Probabilities ($0.00 cost)"]
        A1 --> A2 --> A3 --> A4
    end

    subgraph S2["System 2: Slow & Deliberative (Frontier LLMs)"]
        direction TB
        B1["Autoregressive Transformers (7B – 70B+)"]
        B2["Sequential Token-by-Token Loop (2–15s)"]
        B3["O(N) KV-Cache Memory Scaling (2–16 GB VRAM)"]
        B4["Freeform Prose & Reasoning Explanations ($$$)"]
        B1 --> B2 --> B3 --> B4
    end
```

Traditional software architectures frequently waste System 2 capacity on problems that only require System 1 judgment:
* *Classifying an incoming email as an invoice vs. newsletter.*
* *Routing a user prompt to a fast agent vs. a deep planner.*
* *Triaging a shell traceback to identify the failing component.*
* *Scoring the severity of a production metric anomaly.*

Laya offloads these semantic classification and routing tasks to a local CPU microservice, reserving System 2 models for multi-step reasoning, architectural synthesis, and code generation.

---

## 2. System Topology & Deployment Architecture

Laya operates as an always-on background daemon exposing three interface contracts:
1. **Model Context Protocol (MCP)**: FastMCP Streamable HTTP (`/mcp`) for direct integration into interactive agent loops (Claude Code, Antigravity CLI).
2. **OpenAI Chat Completions (`/v1/chat/completions`)**: Emulates an OpenAI-compatible completion endpoint for gateway routers (LiteLLM, OpenCode).
3. **Direct JSON REST API (`/decide`, `/health`)**: Low-latency endpoints for cron pipelines, shell scripts, and webhook listeners.

```mermaid
flowchart TD
    subgraph Clients["Clients & Agents"]
        CC["Claude Code\n(HTTP MCP)"]
        AGY["Antigravity CLI\n(Native Tool MCP)"]
        CRON["Automated Daemons\n(Cron / Webhooks / Scripts)"]
        OPC["Agent Frameworks\n(LiteLLM / OpenCode)"]
    end

    subgraph Host["Host Machine (Local Server / Workstation / WSL2)"]
        subgraph Gateway["Gateway / Proxy (Optional)"]
            LL["LiteLLM Router (:4000)"]
        end

        subgraph LayaService["Laya Microservice (:8500)"]
            API["FastAPI / Uvicorn Shim"]
            MCP_SVR["FastMCP Session Manager (/mcp)"]
            OAI_SVR["OpenAI Schema Shim (/v1)"]
            REST_SVR["Direct JSON API (/decide)"]
            
            ENGINE["Laya Runtime (ModernBERT-large 395M)\nResident Footprint: ~842 MB RAM\nSingle Forward Pass: ~35ms CPU"]
        end
    end

    subgraph CloudFallbacks["Upstream Fallback Tier"]
        JEV["Cloud Jev (TypeSafe API)\n(Free System 1 Fallback)"]
        FLASH["Gemini 3.8 Flash / Claude Haiku\n(Fast LLM Fallback)"]
    end

    %% Client Ingress
    CC -->|"POST /mcp"| MCP_SVR
    AGY -->|"POST /mcp"| MCP_SVR
    CRON -->|"POST /decide"| REST_SVR
    OPC -->|"POST /v1/chat/completions"| LL

    %% Gateway Routing
    LL -->|"model: laya-decision\n(localhost:8500/v1)"| OAI_SVR
    LL -.->|"fallback if offline"| JEV
    LL -.->|"fallback if offline"| FLASH

    %% Server Internal Flow
    MCP_SVR --> ENGINE
    OAI_SVR --> ENGINE
    REST_SVR --> ENGINE
```

---

## 3. Internal Model Mechanics: Non-Autoregressive Heads

Unlike generative LLMs that predict the next token $\Pr(w_t \mid w_{<t})$ in an iterative loop, Laya processes input text in a **single bidirectional forward pass** over a ModernBERT backbone, extracting dense token representations that feed dedicated classification heads:

```mermaid
flowchart TD
    Input["Input State + Questions\n(Text, JSON state, criteria definitions)"] --> Tokenizer["ModernBERT Tokenizer\n(Subword BPE, up to 512 tokens)"]
    Tokenizer --> Transformer["ModernBERT-Large 395M Encoder\n(28 Layers, 1024 Hidden Dim, 16 Heads)"]
    
    Transformer --> MaskRep["Extract Contextual Embeddings"]

    MaskRep --> ChoiceHead["Choice Projection Head"]
    MaskRep --> NoulHead["Noul Projection Head"]
    MaskRep --> ScoreHead["Score Projection Head"]

    ChoiceHead --> SoftmaxChoice["Softmax over Criteria\n-> Selected Option + Calibrated Confidence"]
    NoulHead --> SigmoidNoul["Sigmoid Activation\n-> Continuous Probability of Yes (0.0 to 1.0)"]
    ScoreHead --> SoftmaxScore["Softmax over Ordered Levels\n-> Expected Value Sum(p_i * level_i)"]
```

### The Three Native Primitives

| Primitive | Output Schema | Mathematical Activation | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **`Choice`** | `{"choice": str, "confidence": float, "probabilities": dict}` | $\text{Softmax}(z_{\text{criteria}})$ | Mutually exclusive categorical routing (e.g. `[AUTH, DB, NETWORK]`). |
| **`Noul`** | `{"yes_probability": float, "confidence": float}` | $\sigma(z_{\text{affirmative}})$ | Continuous probability of a condition holding true without competing alternatives. |
| **`Score`** | `{"expected_score": float, "probabilities": dict, "legend": dict}` | $\sum_{i=1}^K i \cdot \Pr(\text{level}_i)$ | Position on an ordered semantic ladder (e.g. Incident Severity `1` to `4`). |

---

## 4. Hardware Resource Footprint & Accounting

Because Laya does not perform autoregressive generation, its computational profile differs fundamentally from generative LLMs:

| Metric | Local Generative LLM (Qwen 35B / Llama 70B) | Small Generative SLM (Qwen 7B / Phi-3) | Laya System 1 (ModernBERT 395M) |
| :--- | :--- | :--- | :--- |
| **Parameters** | 35B – 70B | 3.8B – 7B | **395M** (+ 26M decision transformer head) |
| **Precision** | 4-bit / 8-bit quantized | 4-bit / 8-bit quantized | **FP16 Native** (Unquantized) |
| **Resident RAM (Disk/RAM)** | 20 GB – 42 GB | 4.5 GB – 8 GB | **~842 MB** (Fits comfortably on any device) |
| **Peak Inference Memory** | Model Size + KV Cache ($O(N)$) | Model Size + KV Cache ($O(N)$) | **~1.8 GB RSS** ($O(1)$ constant overhead) |
| **KV-Cache Allocation** | 2 GB – 12 GB VRAM | 500 MB – 2 GB VRAM | **0 MB** (Non-autoregressive, stateless) |
| **Hardware Requirement** | Dedicated GPU (16GB–48GB VRAM) | Mid-range GPU or slow CPU | **Standard x86/ARM CPU** (0 GPU required) |
| **Single Forward Pass Latency** | 3,000 – 15,000 ms (serial streaming) | 800 – 3,000 ms | **~25 – 45 ms** |
| **Thermal / Power Impact** | 100W – 350W sustained | 45W – 100W sustained | **2W – 10W** (Brief single-core burst) |

---

## 5. Architectural Dataflows

### Dataflow A: Ingress Reflex Router (Fast Path)

```mermaid
sequenceDiagram
    autonumber
    actor Caller as Client / Cron / CLI
    participant LL as Gateway Router (LiteLLM)
    participant Laya as Laya Engine (:8500)
    participant Cloud as Frontier Cloud (Gemini / Claude)

    Caller->>LL: POST /v1/chat/completions (model="laya-decision")
    LL->>Laya: Evaluate prompt intent & complexity
    Note over Laya: ModernBERT single forward pass (~35ms CPU)
    alt Simple Intent / Triage / Noise Drop
        Laya-->>LL: Typed JSON Choice { "choice": "FAST_DECISION", "confidence": 0.96 }
        LL-->>Caller: Instant Structured JSON (0 tokens generated, $0.00 cost)
    else Complex Synthesis / Deep Architecture Demanded
        Laya-->>LL: Typed JSON Choice { "choice": "ESCALATE_SYSTEM_2", "confidence": 0.94 }
        LL->>Cloud: Dispatch prompt to Gemini Pro / Claude 3.7
        Cloud-->>LL: Stream reasoning and code tokens
        LL-->>Caller: Deliver final generative response
    end
```

### Dataflow B: Execution Error Triage & Fast Recovery

```mermaid
flowchart TD
    Exec["Tool Execution / Command Run"] --> Result{"Execution Success?"}
    
    Result -->|"Success (Exit Code 0)"| Continue["Continue Agent Loop"]
    
    Result -->|"Error Traceback / Crash"| LayaTriage["Laya Error Triage Engine (:8500)\nSingle forward pass (~35ms)"]
    
    LayaTriage --> Defect{"Classified Failure Mode"}
    
    Defect -->|"SYNTAX_FORMAT_ERROR\n(Mangled JSON, markdown fence bleed)"| RegexRepair["FAST REPAIR:\nDeterministic regex fence stripper"]
    Defect -->|"PERMISSION_AUTH_DENIED\n(401/403, missing token)"| AuthCheck["AUTH CHECK:\nVerify credential file and reload env"]
    Defect -->|"MISSING_DEPENDENCY\n(ModuleNotFoundError, command not found)"| InstallPkg["PROVISION:\nInvoke package manager (uv/pip/npm)"]
    Defect -->|"TIMEOUT_OR_NETWORK\n(Socket timeout, 502/504 gateway)"| ExponentialRetry["RETRY:\nExecute backoff retry"]
    Defect -->|"LOGIC_OR_ASSERTION\n(AssertionError, invariant breach)"| EscalateModel["ESCALATE:\nInvolve Claude/Gemini for semantic refactor"]

    RegexRepair --> Continue
    AuthCheck --> Exec
    InstallPkg --> Exec
    ExponentialRetry --> Exec
    EscalateModel --> Continue
```

---

## 6. The Prompt Cache Preservation Principle (Teknium's Law)

A critical architectural consideration when integrating System 1 models into agentic loops is **Prompt Cache Preservation**:

```mermaid
flowchart TD
    subgraph WRONG["Anti-Pattern: Mutating Active Transcript"]
        direction TB
        T1["User Turn 1 -> Assistant Turn 1 -> User Turn 2"]
        MUTATE["Laya compacts / rewrites prior history"]
        T2["Altered Message Prefix"]
        FAIL["Frontier Model KV-Cache Invalidation!\nFull Price Paid on Every Turn ($$$)"]
        T1 --> MUTATE --> T2 --> FAIL
    end

    subgraph RIGHT["Correct Pattern: Out-of-Band Auxiliary Reflexes"]
        direction TB
        U1["User Turn 1 -> Assistant Turn 1 -> User Turn 2 (Stable Prefix)"]
        TOOL["Agent invokes tool: laya_triage_error(...)"]
        APPEND["Tool result appends to LEAF of transcript"]
        PASS["KV-Cache 90% Discount Maintained! (<10% cost)"]
        U1 --> TOOL --> APPEND --> PASS
    end
```

### Core Rule
* **Never use Laya to rewrite, compress, or alter existing chat history turns.** Changing even a single token in the conversation prefix breaks the KV cache of upstream frontier models (Anthropic, Google).
* **Always use Laya out-of-band**: inside tool calls, pre-ingress filters, post-egress validators, or standalone cron scripts. Because tool call responses append strictly to the *end* of the prompt, the entire preceding KV cache remains warm and valid.
