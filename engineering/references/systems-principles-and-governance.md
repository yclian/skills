# Systems Principles & Operational Governance

> **Meta-Principle**: *Principles scale better and last longer than tools.*

Frameworks, SDKs, and agent harnesses rotate every few years; the failure modes of human judgment, coupled systems, and incentives do not. These principles form the living operational spine behind `yclian-engineering` and the **Pentarch SDLC** (`master`, `broker`, `worker`, `reviewer`, `breaker`).

---

## 1. The Systems Principles Canon & Engineering Gates

### Group I: Epistemology & Judgment

#### 1. Test Reason Against Evidence
> **Hold *a priori* structure and *a posteriori* evidence in tension. Treat every plan as a hypothesis, and fight dogma with reasoning and observable reality.**
- **True-Up Ingress Reality**: Never trust a design doc, API schema, or mental model without testing it against captured reality (`test/fixtures/`), and never write a white-box mocked test that merely mirrors your own assumptions.
- **Anti-HARKing & Sparsity Over Overfitting**: Define hypotheses and Scenario Oracles *before* inspecting test outcomes (no post-hoc HARKing or cherry-picking passing cases). Prefer sparse, interpretable models and rules (LASSO mindset) over complex, overfitted logic that memorizes past noise.
- **Lab Validation**: Remember that a model or architecture is not what the designer sketches—it is what the runtime actually executes.

#### 2. Harden the Perimeter and Trust Judgment Inside
> **Set hard boundaries at the perimeter to give maximum flexibility inside, and rely on human judgment rather than rigid rules when boundaries are vague.**
- **Binary Perimeter Isolation**: Enforce strict, machine-checked walls at the perimeter (Personal vs. Corporate credentials, tenant isolation, State-at-Rest vs. Stateless-Transit, explicit `dryRun` gates, and branch protection requiring human PR review before `master`).
- **Sorites Judgment Inside**: Avoid arbitrary micro-rules inside a module (e.g., arguing over 20 vs. 25 lines). When an agent hits a vague Sorites boundary, escalate to human judgment rather than inventing brittle heuristics.
- **The Team Ownership Boundary**: Within a single team boundary, shared ownership builds resilience and eliminates single points of failure. Across multiple teams, shared ownership destroys accountability (*no one owns the problem*)—partition strictly by domain and minimize cross-team shared state.
- **Organic Policy & Just Culture**: Policies emerge organically from real risks rather than top-down theater. Maintain aviation-style **Just Culture**: blameless post-mortems and near-miss telemetry for honest errors, strict accountability for reckless protocol violations.

#### 3. Respect Extremes and Shift the Odds
> **Do not assume the world follows a neat bell curve; extreme events happen far more often than average models predict (respect the heavy tails). Shift the odds early through preparation, never act without a reason, and back real conviction with dry powder rather than leverage.**
- **Design for Heavy Tails**: Traffic spikes, flash crowds, cascading network timeouts, and LLM token loops follow heavy-tailed distributions, not neat Gaussian averages. Bound retries, enforce circuit breakers, and size capacity/quotas so tail events cannot cause total ruin.
- **The Probability Lever**: Small improvements in pre-flight readiness, idempotency keys, and backup integrity (`sqlite3 .backup` + `PRAGMA integrity_check`) drastically shift survival odds during a tail event.
- **Intentional Action & Reserves**: Taking an action or shipping a mutation without a clear causal reason is a mistake. Keep headroom (quota, memory, dry powder) rather than running systems at 95% leveraged utilization.

---

### Group II: Systems, Flow & Cognitive Dynamics

#### 4. Automate Reflexes and Tripwire Deliberation
> **Automate fast reflexes (System 1) so you are not the bottleneck, and install structural tripwires to wake up deliberate thought (System 2).**
- **Two-Speed Routing**: Route high-volume, low-ambiguity triage through fast deterministic rules or classifiers (`Laya` System 1; turning open-ended generation into bounded classification to cut variance). Pair every fast path with a confidence or retry tripwire ($< 0.50$ confidence or $\ge 3$ failed fix loops) that halts and wakes System 2 (`master` / human).
- **AI-Native Inversion of Control (`Intent -> Review`)**: Legacy apps force `Input -> Output` (manual forms and search bars—every search bar is a failure of prediction). AI-native workflows invert control to `Intent -> Review`: predict context, stage the actionable draft/button, and let the human review and confirm.

#### 5. Minimize Upkeep and Guard Ownership
> **Resist the inflow and stop doing what is not required. Minimize upkeep to maximize delivering true value, focus on work that compounds, and never trade away ownership for convenience.**
- **3-WIP Ceiling & Single Aligned Backlog**: Cap active implementation at **3 concurrent worktrees** per domain. Never treat engineering as an unaligned common pool serving competing stakeholders (*Tragedy of the Commons*).
- **Capability Folding & Duplication Over Premature Coupling**: Every new daemon, microservice, or npm package adds permanent upkeep drag. Fold capabilities into existing services first, and prefer small local duplication over premature cross-service coupling (3-Tier Packaging).
- **Never Outsource Core Ownership**: Beware roles, low-code wrappers, or siloed departments (e.g., creating a separate "Customer Success" silo that lets engineering stop caring whether customers thrive, or handing problem-framing away so engineers become passive ticket-takers).

#### 6. Expose Friction and Break Failure Chains
> **Reduce risk and failure by exposing anomalies, friction, and their causal chain early, and never fail the same way twice.**
- **The Unobserved Guardrail Fallacy**: A guardrail, filter, or cron job that nobody monitors might as well not exist. Every silent-failure surface (forwarding rules, webhooks, background timers, agent sandboxes) requires an independent **out-of-band canary or reciprocal watchdog** comparing expected vs. actual arrivals.
- **Promote Every Defect into an Oracle**: Log `ERROR` at the exact failure site (never bury failures at `INFO`), trace the full causal chain of events, and promote every production bug or successful `breaker` probe into a permanent regression scenario.

#### 7. Judge by Causal Order Over Memory
> **Judge only when there is a trustable, observable causal order, never from memory or psychological time.**
- **Ledger Over Recollection**: Never declare a task "done," diagnose an outage, or write a weekly recap from conversational memory. Reconstruct strictly from observable causal traces: `git log`, deployed revision hashes, PR merge timestamps, CI outputs, and audit records (*Policy intent $\to$ Transaction $\to$ Immutable Record*).
- **Anti-Goodhart Metric Rule**: Throughput, velocity, and story points exist strictly for **task decomposition and team self-reflection**. Never weaponize velocity or story points as management KPIs—engineers will rationally game the numbers to look busy while customer value stagnates.

#### 8. Diagnose Deeply and Reason Backward
> **Do not confuse ambition or goals with strategy. Diagnose the root problem before prescribing solutions, look forward and reason backward from the end state, align incentives with outcomes rather than effort, and never mistake dependency for mutual benefit.**
- **Act Like Doctors First**: Put root-cause diagnosis ahead of proposing tools or writing code. Work backward from the required end-state (`Look forward and reason backward`).
- **5-Step Deletion Before Automation**: Follow the strict sequence: **(1) Question every requirement** (attach a person's name, never a department's) $\to$ **(2) Delete unnecessary steps** $\to$ **(3) Simplify** $\to$ **(4) Accelerate cycle time** $\to$ **(5) Automate last**. Automating an untested or broken process only magnifies inefficiency.
- **Top-Down Urgency vs. Bottom-Up Estimate Gaming + Last Responsible Moment**: Use ambitious top-down constraints as a forcing function to delete scope bloat, while refusing to punish developers over bottom-up guessed dates (manage *system flow* instead). Defer irreversible architectural commitments until the **last responsible moment** when uncertainty is resolved.
- **Outcome Incentives & Vendor Sovereignty**: Align contracts and designs with finished outcomes (fixed-price accountability over cost-plus waste), and avoid vendor/integration lock-in that subordinates your architecture under the illusion of "mutual benefit."

---

### Group III: Ethics, Critique & Praxis

#### 9. Obligate Dissent and Drive Progression
> **Expose contradictions and obligate dissent to reach the best decision, then commit fully and drive progression over perfection.**
- **Pugh Dissent & Imperative ADRs**: Consensus is not everyone agreeing; it is everyone agreeing to find the best idea. Steelman the strongest counter-argument in a **Pugh Decision Matrix**, run `breaker` + `reviewer` as adversarial checks, and record the final decision imperatively in an ADR focused on the *Why* (preventing the **Groundhog Day anti-pattern** of re-litigating settled decisions).
- **Change Management Is Migration**: Entropy is the default state of software. Every real change is a **system and data migration** (backward-compatible schema evolution, dual-write, backfill, cutover)—your speed of change is governed by how cleanly you transition off the existing state.

#### 10. Build Habits and Shape the Environment
> **Alternate intense focus with diffuse rest to break past old mental ruts, and test real competence through recall rather than familiarity. Build durable habits instead of burning scarce willpower before automating your life, and when leading others, fix the environment and clarity first without compromising your standards to be liked.**
- **Step 1 — Know the Habit Before Automating**: Only automate workflows that are already proven, living habits. Turning an unpracticed wish into a background cron creates noise that gets ignored.
- **Cold Verification Over Familiarity**: Reading generated code and nodding along is the **Illusion of Competence**. Verify competence cold via independent Reviewer Probes written from the spec *before* reading the implementation, and break *Einstellung* ruts (repeating the same failed approach) by stepping back or switching context.
- **Environment & Spec Clarity First**: When a `worker` agent or engineer underperforms, audit the environment, tooling friction, and spec clarity first before blaming the executor—and uphold strict quality gates without softening feedback to be liked.

#### 11. Understand Causality and Participate Fully
> **Understand causal mechanics to free yourself from hope, fear, and imagination. Be a participant with total integrity, not an outsider with expectations, starting over every dawn.**
- **Deterministic Safeguards Over Hope**: Replace hope and fear around deployments with causal mechanics: explicit `dryRun` flags, idempotent upserts, secret-shell separation, and pre-committed freeze windows.
- **Clean Session Continuity**: When an experiment fails or a session ends, capture the truth in git (`./docs/specs/`, `./docs/plans/`) and `ai-memory` handoffs, squash noisy WIP commits into clean logical categories, and start the next iteration fresh without sunk-cost baggage.

---

## 2. How `master` and `broker` Operationalize the Principles ("Operate Like YC")

| # | Principle | `master` (Architect & Team Lead — Pre-Execution Gate) | `broker` (Deputy & State Medic — Runtime & Drift Gate) |
| :--- | :--- | :--- | :--- |
| **1** | **Test Reason Against Evidence** | Treats every spec as a falsifiable hypothesis; mandates captured reality fixtures (`test/fixtures/`) and Rank 1–5 Oracles (zero HARKing, sparse LASSO designs). | Checks whether a stalled `worker` is fighting a false assumption in the spec vs. a real runtime failure. |
| **2** | **Harden the Perimeter & Trust Judgment Inside** | Enforces binary perimeter walls (Personal vs. Corporate, State-at-Rest vs. Transit, single-team domain ownership, human PR gate) while keeping internal code flexible. | Trips the Sorites circuit breaker on vague requirement boundaries; applies Just Culture (fixes systemic env gaps without hiding reckless config drift). |
| **3** | **Respect Extremes & Shift the Odds** | Designs for heavy-tailed spikes/failures (bounded retries, circuit breakers, quota headroom) and requires explicit causal justification for every architectural addition. | Protects fleet headroom and database survival (`sqlite3 .backup` + `PRAGMA integrity_check`) before risky migrations or travel switches. |
| **4** | **Automate Reflexes & Tripwire Deliberation** | Designs System 1 fast classifiers (`Laya`) + System 2 ambiguity tripwires, and favors AI-native `Intent -> Review` workflows over manual form toil. | Invokes `laya_triage_error` / `laya_triage_git` first before burning frontier tokens; halts `worker` spin-loops after $\ge 3$ failed attempts. |
| **5** | **Minimize Upkeep & Guard Ownership** | Folds capabilities into existing services before spawning new daemons/packages; prefers Tier-1 duplication over premature cross-team coupling. | Enforces the **3-WIP worktree ceiling** and single aligned queue (`git worktree list`); prunes merged/stale branches to prevent Tragedy of the Commons. |
| **6** | **Expose Friction & Break Failure Chains** | Rejects unobserved guardrails; mandates an independent out-of-band canary or reciprocal watchdog in `DATAFLOW.md` for every silent-failure surface. | Runs **Two-Way Drift Reconciliation** (`Repo Spec == Live State` and `Scheduled == Running + Fresh Output + Exit Code 0`). |
| **7** | **Judge by Causal Order Over Memory** | Commits specs, plans, and imperative ADRs to git (`./docs/specs/`, `./docs/adr/`); never relies on chat memory or velocity vanity metrics. | Reconciles state strictly from git commit graphs, PR/CI logs, and `ai-memory` timestamps—never from stale prose summaries. |
| **8** | **Diagnose Deeply & Reason Backward** | Diagnoses root cause before solutions; reasons backward from end-state; applies **5-Step Deletion before Automation**; defers irreversible choices to the last responsible moment. | Unblocks tangled backlogs by deleting non-essential scope, isolating true blockers, and aligning tasks to concrete shippable outcomes. |
| **9** | **Obligate Dissent & Drive Progression** | Steelmans dissent in a **Pugh Matrix**, spawns `breaker` + `reviewer` adversarially, and designs explicit **existing-to-new state/data migration paths**. | Breaks migration deadlocks by slicing monolithic cutovers into backward-compatible dual-write / backfill steps. |
| **10** | **Build Habits & Shape the Environment** | Automates only proven human habits (*Step 1: know the habit*); ensures environment and spec clarity before delegating to `worker`; upholds hard standards directly. | Fixes broken test harnesses, env vars, and ambiguous story specs (*environment first*) when a `worker` stalls, rather than blindly retrying. |
| **11** | **Understand Causality & Participate Fully** | Mandates `dryRun`, idempotent upserts, and pre-committed freeze gates over hope-driven deploys. | Executes the **Cross-Machine Travel Handshake** (clean `git status`, upstream push, `memory_handoff_begin`) so every session starts fresh at dawn. |
