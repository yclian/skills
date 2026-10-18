---
name: yclian-engineering
description: "Core software engineering, coding, testing, git workflow, resilience, and architecture standards grounded by YC Lian. Use when writing or refactoring code, designing tests (Dual-Boundary / Reality-and-Oracle Verification), making git commits or preparing PRs (Conventional Commits, Jira refs, squashing granular commits by category), structuring modules/packages, building resilient cloud/serverless integrations, or writing architecture docs (ARCH.md, DATAFLOW.md, ADRs) and implementation plans."
---

# Engineering Standards & Principles (`yclian-engineering`)

## Why This Exists: Engineering for the Agentic Era

Most software engineering conventions (the test pyramid, heavy mocking frameworks, premature package abstractions, sprawling dependency trees) were invented for an era when **human typing was the bottleneck**.

We no longer live in that era. Autonomous coding agents made code generation fast and cheap, which inverted the economics and failure modes of software engineering:
1. **Tautology Risk (Why We Reject Mocked Unit Tests)**: When an agent writes both the implementation and a white-box mocked unit test, it writes a **tautology**—mirroring its own hallucinated assumptions about external APIs and passing 100% while failing in production. Verification only works if **Ingress is anchored in captured reality** (`test/fixtures/`, `&xml=t`, `.fromprod.xml`) and **Egress is certified by an independent Oracle + universal Invariants**.
2. **Closed-Loop Autonomy (The Fix Loop)**: A reality-and-oracle boundary suite is not a post-hoc checklist—it is an **un-gameable cybernetic environment** that an agent can iterate against autonomously (red → green fix loop) while human attention moves to the highest-leverage points: **Specs, Oracles, and adversarial Probes**.
3. **Inspection Over Magic (Thin Abstractions & Zero-Dep)**: Agents reason reliably over 50 lines of explicit, dependency-free code with injected seams (`deps = { store, clock, cipher, fetch }`), and poorly over opaque framework magic or third-party packages whose APIs drift across training cutoffs.
4. **Session & Harness Continuity (Repo-First Memory & Clean History)**: Agents run across multiple harnesses (Claude, Gemini/Antigravity) and machines, and produce dozens of micro-edits per hour. Specs and plans must live in git (`./docs/specs/`, `./docs/plans/`, `DATAFLOW.md`), and noisy agent WIP commits must be squashed into clean logical categories before review.

---

## 1. Git Commit & History Discipline (Always-On)

Apply these three rules on every commit and branch across all repositories and agent harnesses:

1. **Conventional Commits**:
   - Format: `<type>(<scope>): <imperative summary>` (lowercase type, no trailing period, $\le 72$ chars).
   - Allowed types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`.
2. **Issue Key Reference (`refs:` / `Refs:`)**:
   - Whenever a Jira or issue key applies, append `refs: JIRA-123` or `Refs: JIRA-123` at the end of the last line (or as the commit footer trailer).
   - Multiple tickets: `refs: PROJ-123, PROJ-456`.
   - Examples:
     - Single-line: `feat(auth): enforce PKCE S256 on token exchange refs: JIRA-123`
     - Multi-line: place `Refs: JIRA-123` at the end of the final line of the commit body.
3. **Squash Granular Commits by Logical Category**:
   - Never leave noisy, granular WIP commits (`fix typo`, `try again`, `lint`, `address review`) that obscure what changed since the branch diverged.
   - Before pushing or opening/merging a PR, **squash and group commits into a small number of cohesive commits organized by logical category** (e.g., one `feat(...)` commit for the core change, one `test(...)` commit for the verification suite, one `docs(...)` commit for specs/runbooks—or a single squashed commit for a focused change).
4. **Worktree Isolation (`.worktrees/`) & Branch Naming**:
   - Branch format: `type/lowercase-no-dash-key-slug` (e.g., `feat/proj123-plans-overview`, `fix/jira456-module-load`).
   - Develop non-trivial changes inside an isolated git worktree (`.worktrees/<name>`) rather than dirtying the primary checkout.

---

## 2. Dual-Boundary (Reality-and-Oracle) Verification

> **Tagline**: *True-up the ingress boundary against captured reality; verify the core as pure transforms; certify the egress boundary with ranked oracles and universal invariants.*

Agents made black-box harnesses cheap and white-box mocked unit tests dangerous (an agent writing both code and mocked unit tests writes a tautology). We replace the traditional test pyramid with a **three-layer verification architecture**:

```text
+-----------------------------------------------------------------------+
| 1. INGRESS BOUNDARY: Captured Reality (`test/fixtures/` & True-Up)    |
|    Real API recordings ({ok,err}.json), DB/SQL row dumps, platform    |
|    object exports (&xml=t, .fromprod.xml), contrastive pairs,         |
|    and PLANTED_* sentinels. Never hand-written mocks of guesses.      |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| 2. DOMAIN CORE: Pure Transforms (Fast Localiser — Milliseconds)       |
|    Parsers, ciphers, scorers, key encoders, decision rules peeled     |
|    away from hostile runtimes. Verified via TDD + property-based      |
|    tests (fast-check / Hypothesis) + published vectors.               |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| 3. EGRESS BOUNDARY: Scenarios, Ranked Oracles & Invariant Sweep       |
|    Drive the real entry point (app.fetch, CLI, handler) over real     |
|    local engines. Certified by a Rank 1–5 Oracle and swept on every   |
|    scenario by a single `afterEach` Invariant Suite.                  |
+-----------------------------------------------------------------------+
```

### Core Verification Rules
- **Two test tiers survive; integration & glue unit tests are dropped**:
  1. **Boundary Scenarios (Merge Gate)** — drive the real system boundary over real local engines.
  2. **Pure-Transform Tests (Localiser)** — keep TDD and property tests strictly for pure functions. Never unit-test orchestration glue.
- **Never mock `src/`**: Internal module mocking (`vi.mock("../../src/...")`) is forbidden. Inject explicit seams (`deps = { store, clock, cipher, fetch }`) instead. Fake **only** at the third-party network edge using recorded fixtures.
- **Every scenario traces to a Scenario Table (`name · boundary · fixture/generator · oracle · assertions`)** reviewed before code, and every acceptance criterion requires a **Rank 1–5 Oracle**:
  1. **Planted truth** (generator knobs or `PLANTED_*` sentinels).
  2. **Independent recomputation / Naive model** (e.g., an in-test `Map` or SQL/pandas over raw input).
  3. **Legacy parity** (verbatim old code in `test/legacy_ref/` run on the same input).
  4. **Recorded reality / Spec contract** (captured `{ok,err}.json` responses, contrastive before/after XML/JSON dumps, RFC rules).
  5. **Published vectors / Hand-computed examples** (e.g., RFC 7636 PKCE vector).
  - *Rank 6 (Invariants)* and *Rank 7 (Goldens / Phase 0 Characterisation)* are **guards**, never standalone certification.
- **Reviewer Probes**: A reviewer writes adversarial probes from the spec without reading the implementation first; probes that find defects are promoted into permanent scenarios.

👉 **Load [`references/dual-boundary-verification.md`](./references/dual-boundary-verification.md)** for the complete classification matrix, scenario-when-no-plan protocol, and the **4 copy-pasteable thin `test/support/` implementations** (`TestClock`, `planted.ts`, `recordingFetch` + `afterEach` invariant sweep, and `runStoreSuite` model checking).

---

## 3. Language, Modularity & Packaging

1. **JS-First & ESM-First**:
   - Default to pure JavaScript on greenfield projects (*"JavaScript is beautifully typeless — runtime guides development"*); adopt TypeScript when already established in the target repo.
   - Always use `"type": "module"`, explicit `.js` extensions on relative imports, and named exports/imports for grep-ability.
2. **Zero-Dependency & YAGNI (Rule of Three)**:
   - Never `npm install` what takes 5–10 lines of vanilla JS (`fetch`, `crypto`, `Intl`, `URLSearchParams`).
   - Do not abstract until **3 concrete implementations** exist (*"copy-paste beats the wrong abstraction"*).
3. **3-Tier Packaging Progression**:
   - **Tier 1 (1–2 consumers)**: Vendored copy per service; share the **contract** (schema/interface doc), not the code.
   - **Tier 2 (3+ services in one monorepo)**: Shared workspace package (`packages/<name>/`).
   - **Tier 3 (Cross-repo consumers)**: Published versioned package.
   - **Injectable I/O Seam**: Shared modules must accept logger, SDK clients, clock, and project/database IDs as injected parameters—never hardcode globals.
4. **OS-Safe File Naming vs. Language Export Naming**:
   - **Files & directories** (OS concern): `kebab-case.js` to prevent silent case-insensitive git drift across Windows/macOS vs. Linux.
   - **Exports** (language concern): `camelCase` functions/vars, `PascalCase` classes/components, `UPPER_SNAKE_CASE` constants.
   - **Directory layout**: Group by domain responsibility (`src/oauth/`, `src/store/`), not technical layer (`controllers/`, `helpers/`).

👉 **Load [`references/coding-and-packaging.md`](./references/coding-and-packaging.md)** for code examples and packaging graduation triggers.

---

## 4. Resilience, State & Production Safety

1. **Explicit Dry-Run Gate**:
   - Every write-capable script, sync job, or mutation CLI must accept an explicit `dryRun` flag/parameter that logs the exact intended mutation without executing it. Never infer dry-run from ambient runtime metadata.
2. **Idempotent Upsert Over Blind-Create**:
   - Webhooks, queues, and Map/Reduce or batch jobs run at-least-once and re-run after partial failure. Always look up by a stable external/idempotency key and upsert rather than blind-creating.
3. **Error Classification & Bounded Retries (Never Busy-Wait)**:
   - Classify errors before retrying: `4xx` (except `429`) is permanent—fail fast and do not retry; `429`, `5xx`, and network timeouts are transient.
   - Never use CPU spin-loops (`while (Date.now() < ...)`). In runtimes without non-blocking sleep, use bounded immediate retries (2–3 attempts) and delegate temporal backoff to the scheduler + idempotent design.
4. **Multi-Instance State Persistence**:
   - Serverless and container runtimes scale horizontally without sticky sessions. Never store user-mutable config or session state solely in process memory (`this.state`); persist to a backing store, hydrate on boot, and read-through on admin/settings views. Treat in-memory state strictly as a bounded cache with a documented staleness window.
5. **Secret Shell vs. Value Separation + Safe Fingerprinting**:
   - Declare secret shells/containers and IAM bindings in IaC (Terraform), never pass secret values through Terraform variables, state files, or source code.
   - When diagnosing silent 401/webhook auth failures, log `{ length, sha256Prefix8 }` on the receiver—never the raw secret.
6. **Log at the Failure Site + Redact Copy Only**:
   - Log `ERROR` with full context at the exact `catch` site; end-of-job summaries are recaps at `WARN`. Never log actual failures at `INFO`/`AUDIT` (silent failure trap).
   - Redact PII on a *shallow copy* passed to the logger—never mutate the live payload in flight.

👉 **Load [`references/resilience-and-state.md`](./references/resilience-and-state.md)** for patterns and production post-mortem traps.

---

## 5. Architecture, Planning & Review Discipline

1. **3-Artifact Architecture Standard**:
   - `ARCH.md` — C4 System Context & Container diagrams (the *What* and trust boundaries).
   - `DATAFLOW.md` — High-density Mermaid `graph TB` with `subgraph` boundaries + a mandatory **Logic Q&A** section capturing edge cases, retries, and failure modes (the *How*).
   - `docs/adr/XXXX-title.md` — ADRs recording context, trade-offs, and graduation triggers (the *Why*). Reserve formal methods (TLA+) for genuine multi-hop concurrency/liveness or at-least-once idempotency surfaces; use property-based tests for data transformations.
2. **Repo-First Specs & Plans (No Ephemeral Brain Lock-In)**:
   - Never leave specs, plans, or scenario tables trapped in ephemeral AI session directories (`.gemini/.../brain/`) or tool-locked folders (`docs/superpowers/`).
   - Commit them to the repository under `./docs/specs/YYYY-MM-DD-<topic>-design.md` and `./docs/plans/YYYY-MM-DD-<topic>.md`.
3. **Two-Axis Code Review + Probes**:
   - Confirm scope before fan-out. Review along **Standards + Spec Adherence** in sequence: `contracts/schemas → logic → edge cases → naming → tests/oracles`.
   - For deployed services, verify the *running revision / deployed artifact* (`file:import`, `object:import`, Cloud Run revision), never just local git.

👉 **Load [`references/architecture-and-review.md`](./references/architecture-and-review.md)** for templates and review checklists, and **[`references/web-and-cloud-mechanics.md`](./references/web-and-cloud-mechanics.md)** for CSS grid/layer rules, Cloud Run + Terraform 4-step bootstrap, and Windows/MSYS path conversion guards.
