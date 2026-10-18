# Coding, Modularity & Packaging Standards

Grounded in runtime simplicity, zero unnecessary dependencies, explicit dependency seams, and OS-safe file naming.

---

## 1. Language & Module Philosophy

### A. JavaScript-First & ESM-First
- **Pure JavaScript by default on greenfield work**: JavaScript is dynamically guided by the runtime—avoid ceremony and build-step tax when plain JS + JSDoc (`@param`, `@returns`) expresses the contract clearly.
- **Respect established TypeScript**: When working in an existing TypeScript repository, follow its conventions without fighting the toolchain.
- **ESM-First (`"type": "module"`)**:
  - Use standard `import` / `export` syntax everywhere (unless constrained by a legacy platform such as SuiteScript 2.x AMD `define([...])`).
  - Always include explicit file extensions in relative imports (`import { parseRow } from "./parse-row.js"`).
  - Prefer **named exports and named imports** over default exports so symbols remain grep-able across the entire codebase.

### B. Zero-Dependency & YAGNI (Rule of Three)
- **Zero-Dependency Default**: Before running `npm install`, check if native platform APIs (`fetch`, `crypto.subtle` / `node:crypto`, `URL`, `Intl`, `fs/promises`) or 5–10 lines of plain code solve the problem. Every third-party package is a supply-chain and maintenance liability.
- **Rule of Three (YAGNI)**: Do not extract a generic helper, base class, or config-driven framework until **three concrete implementations** exist. Copy-pasting twice is cheaper and safer than Premature Abstraction.

---

## 2. The 3-Tier Packaging Progression

When sharing logic across services or cloud functions, escalate packaging complexity **only** when consumer count and synchronization pain justify it:

| Tier | Trigger (Consumer Count) | Mechanism | What Is Shared |
|------|--------------------------|-----------|----------------|
| **Tier 1: Vendored Copy** | **1–2 consumers** | Copy the single file into each service's `lib/` directory. | Share the **Contract** (JSON schema, storage layout, or ADR), not a package build pipeline. |
| **Tier 2: In-Repo Workspace Package** | **3+ consumers in the same monorepo** | Extract to `packages/<name>/` (or `common/<name>/`) wired via npm/pnpm workspaces or local path imports. | Single source of truth inside the repo, tested once. |
| **Tier 3: Published Versioned Package** | **Cross-repo consumers** | Publish to a package registry with semver and automated release notes. | Versioned artifact with strict backward-compatibility guarantees. |

### Mandatory Rule for Shared Units: Injectable I/O Seam
Any module intended for reuse (even at Tier 1) **must never hardcode ambient globals, singletons, or environment variables**:
- Inject dependencies explicitly via an options/deps object: `{ store, clock, cipher, fetch, logger, projectId }`.
- This keeps the module portable across runtimes (Node, Deno, Cloud Run, edge workers) and allows **Dual-Boundary Verification** without module mocking (`vi.mock`).

```js
// GOOD: Explicit dependency seam — zero module mocks needed in tests
export function createSyncHandler({ store, fetchFn = globalThis.fetch, clock = Date.now, logger = console }) {
  return async function handleSync(payload) {
    const startedAt = clock();
    // ...
  };
}
```

---

## 3. Naming & Directory Structure

Separate **operating-system concerns** (file paths) from **language concerns** (exported identifiers):

### A. File & Directory Naming (OS Concern)
- **Always use `kebab-case.js`** for files and directories (e.g., `firestore-key.js`, `rate-limiter.js`, `parse-script-object.js`).
- **Why**: Windows and macOS default to case-insensitive filesystems while Linux (CI and production containers) is case-sensitive. Renaming ` userProfile.js` to `UserProfile.js` causes silent git drift that passes locally and crashes in Linux containers. All-lowercase `kebab-case` eliminates casing bugs permanently.

### B. Export & Symbol Naming (Language Concern)
- **Functions & variables**: `camelCase` (`resolveTravelBooking`, `clientIp`)
- **Classes, Types & UI Components**: `PascalCase` (`StaticCipher`, `DenoKvStore`, `TestClock`)
- **Module-level Constants & Planted Sentinels**: `UPPER_SNAKE_CASE` (`PLANTED_KEY_MATERIAL`, `SECURITY_HEADERS`)

### C. Group by Domain Responsibility, Not Technical Layer
- Organize directories by **what the feature does** (`src/oauth/`, `src/store/`, `src/crypto/`), not by generic technical role (`src/controllers/`, `src/helpers/`, `src/utils/`).
- A reader should know what a system does from `ls src/` alone.
