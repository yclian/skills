# Architecture, Planning & Code Review Discipline

## 1. The 3-Artifact Architecture Standard

Every non-trivial system or integration maintains three living documents in the repository—each answering a distinct question:

| Artifact | Question | Format & Mandatory Contents |
|----------|----------|-----------------------------|
| **`ARCH.md`** | **What** are the system boundaries and trust zones? | **C4 Model** (System Context + Container diagrams in Mermaid) plus a concise component responsibility table. |
| **`DATAFLOW.md`** | **How** does data move, transform, and fail? | High-density Mermaid `graph TB` using `subgraph` blocks for system boundaries, followed by a mandatory **Logic Q&A** section answering non-obvious operational questions (idempotency keys, retry behavior, partial-failure recovery, negative overrides). |
| **`docs/adr/XXXX-title.md`** | **Why** did we choose this design, and when do we outgrow it? | Context, Decision, Consequences, and explicit **Graduation Triggers** (e.g., *"When consumer count reaches 3, graduate from Tier 1 vendored copy to Tier 2 workspace package"*). |

### Where Formal Methods (TLA+) Fit vs. Property Tests
- **Do not apply formal methods (TLA+ / Lean) to I/O-bound integration glue**: Glue bugs are boundary-shape and field-mapping bugs—solve them with **Dual-Boundary (Reality-and-Oracle) Verification**.
- **Use TLA+ selectively at design time** only when a subsystem has genuine **multi-hop delivery safety/liveness** invariants (*"every privileged event produces at least one alert and zero silent drops"*) or **uncontrolled concurrent/at-least-once state transitions**.
- **Use Property-Based Testing (`fast-check` / `Hypothesis`)** for complex pure data transformations, ciphers, and stateful store models—buying ~90% of proof confidence at ~5% of the effort.

---

## 2. Repo-First Specs & Plans (No Brain-Only Lock-In)

1. **Commit Specs and Plans to the Repo**:
   - Never leave design specs, discovery notes, or implementation plans trapped inside ephemeral AI session folders (`.gemini/.../brain/`, `.claude/plans/`).
   - Never use tool-specific vendor folder names like `docs/superpowers/`.
   - Use clean, tool-agnostic repository paths:
     - **Design Specs**: `./docs/specs/YYYY-MM-DD-<topic>-design.md`
     - **Implementation Plans**: `./docs/plans/YYYY-MM-DD-<topic>.md`
2. **Sync Plan Deviations Back Before Merge**:
   - Implementation always uncovers edge cases not anticipated in the initial plan. Before opening or merging a PR, update the spec/plan doc with a brief **Deviations from Plan** note so the committed document reflects reality, not an obsolete draft.

---

## 3. Two-Axis Code Review + Reviewer Probes

When reviewing a branch, PR, or deployed service:

### Step 0: Confirm Scope & True-Up Against Deployed Reality
- Confirm the branch diff (`git diff main...HEAD`) and check that granular WIP commits have been squashed into logical categories.
- **If reviewing a deployed service or brownfield integration**: Do not trust local git alone. Check whether the live deployed artifact (Cloud Run revision, File Cabinet script, production config XML) has drifted from git.

### Step 1: Walk the Two-Axis Review Sequence
Evaluate every change along **Axis 1 (Engineering Standards)** and **Axis 2 (Spec Adherence)** in this exact five-step order:

1. **Contracts & Schemas**: Do boundary inputs/outputs, store interfaces, and config schemas match captured reality (`test/fixtures/`) and the spec? Are dependencies injected via seams rather than hardcoded globals?
2. **Core Logic**: Is decision logic peeled out of hostile runtimes into pure transforms? Are mutations guarded by explicit `dryRun` and idempotent upsert?
3. **Edge Cases & Failure Modes**: Are errors classified (`4xx` fail-fast vs. `429`/`5xx` bounded retry)? Are `ERROR` logs emitted at the failure site without leaking secrets or mutating live payloads? Does state survive across multiple instances?
4. **Naming & Structure**: Are files `kebab-case`, exports idiomatic (`camelCase` / `PascalCase` / `UPPER_SNAKE_CASE`), and directories grouped by domain?
5. **Tests, Oracles & Invariants**: Does every acceptance criterion trace to a **Rank 1–5 Oracle**? Is `src/` free of internal module mocks? Does the `afterEach` invariant suite run across all boundary scenarios?

### Step 2: Author Adversarial Reviewer Probes
- Write **probes** from the spec *without* trusting the implementation's happy path: Unicode/long strings, pagination boundaries (100+ items), concurrent token refreshes, spoofed proxy headers (`X-Forwarded-For`), cold-start mid-flow, missing optional claims.
- Any probe that exposes a defect is promoted into a permanent scenario in the test suite.
