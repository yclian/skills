# Resilience, State & Production Safety

Battle-tested rules from production incidents across serverless functions, background batch jobs, and enterprise integrations.

---

## 1. Mutation Safety: Explicit Dry-Run & Idempotent Upsert

### A. Explicit Dry-Run Gate
Every write-capable script, batch processor, or operational CLI must accept an explicit `dryRun` parameter/flag (`--dry-run`, `DRY_RUN=true`, or script parameter):
- **Never infer dry-run from ambient runtime metadata** (for example, checking whether a deployment status is `TESTING` when the platform only executes `SCHEDULED` deployments—which turns the live branch into dead code).
- In `dryRun` mode, execute the full read, classification, and payload-construction pipeline, then log the exact would-be mutation payload at `INFO`/`AUDIT` and skip the external write.
- Ship new scheduled jobs with `dryRun = true` by default until discovery and threshold tuning are verified against live data.

### B. Upsert Over Blind-Create (At-Least-Once Idempotency)
Background jobs, webhooks, Map/Reduce stages, and queue consumers operate under **at-least-once delivery**: they *will* re-run on timeout, crash, or manual retry.
- **Never blind-create** a record or side effect assuming the job only runs once.
- Always derive or require a **stable external/idempotency key** (`externalId`, `dedupeSignature`, or deterministic hash) and perform a lookup-then-update (or atomic upsert).
- Advance watermarks/cursors **only** when the stage completes with zero unhandled item errors, so failed items are retried on the next window rather than silently dropped.

---

## 2. Error Classification & Bounded Retries

### A. Classify Before Retrying
Not all failures deserve a retry:
- **Permanent (`4xx` except `429`, validation/schema errors, missing permissions)**: Do **not** retry. Log `ERROR` at the failure site with full request context and fail fast.
- **Transient (`429 Too Many Requests`, `502`/`503`/`504`, network socket resets)**: Eligible for bounded retry.

### B. Never Busy-Wait (No CPU Spin-Loops)
- **Forbidden**: `while (Date.now() < start + delayMs) {}`. Spin-waiting burns CPU quota, starves event loops, and triggers platform governance kills.
- **In standard async runtimes**: Use non-blocking timer backoff with jitter (`await new Promise(r => setTimeout(r, delayMs))`).
- **In constrained runtimes without non-blocking sleep**: Perform at most **2–3 bounded immediate retries** for transient network blips, then let the item fail and rely on **idempotent upsert + the next scheduled run** for temporal backoff.

---

## 3. Multi-Instance State Persistence

Serverless platforms (Cloud Run, Cloud Functions, Lambda, Vercel) scale horizontally and replace instances at any time without session affinity.

- **Never store user-mutable settings or cross-request state solely in process memory** (`this.config = ...` or module-level `let`). Instance A will accept a POST update while Instance B continues serving stale memory to the user's next GET.
- **Required Pattern**:
  1. Persist all mutable state to an external backing store (Firestore, Postgres, KV, Secret Manager).
  2. Hydrate on cold start.
  3. **Read-through on admin/settings views** so operators always see committed truth.
  4. If in-memory caching is used on a hot path (e.g., KMS decrypted token cache), bound it with an explicit TTL/staleness window and document that window in the spec.

---

## 4. Secret Hygiene & Fingerprint Diagnostics

### A. Secret Shell vs. Secret Value Separation
- **In IaC (Terraform)**: Declare the **secret shell/container** (`google_secret_manager_secret`) and IAM bindings (`secretAccessor`), never the secret value (`google_secret_manager_secret_version` with sensitive variables).
- **Why**: Passing secret values through Terraform variables writes plaintext secrets into `terraform.tfstate`. Populate secret versions out-of-band via CLI (`gcloud secrets versions add ... --data-file=-`) or the console.

### B. Safe Fingerprint Logging for 401 Diagnosis
When debugging silent `401 Unauthorized` or webhook signature mismatches across services, **never log the raw secret**, and never log a bare `"401 unauthorized"` that leaves operators guessing whether the caller sent an unresolved placeholder, an empty string, or the wrong key.
- Log the **received length and a short SHA-256 prefix fingerprint** alongside the expected fingerprint:

```js
import { createHash } from "node:crypto";

function secretFingerprint(val = "") {
  const fp = val ? createHash("sha256").update(val).digest("hex").slice(0, 8) : "none";
  return { len: val.length, fp };
}
// Example log on 401:
// auth_failed: recv={len:32, fp:"a1b2c3d4"} exp={len:44, fp:"9f8e7d6c"}
```
- `recv.len === 32` (matching `{custsecret_...}` literal length) immediately diagnoses a platform secret-restriction failure without exposing any credential.

---

## 5. Logging Discipline & PII Redaction

1. **Log `ERROR` at the Failure Site**:
   - Always log `ERROR` inside the `catch` block where the failure occurs, including the entity key, endpoint, and stack/status.
   - End-of-job summaries are recaps (`WARN` or `INFO`); never swallow site errors into an `INFO`-only summary that looks green in log monitors.
2. **Redact a Shallow Copy, Never Live Data**:
   - When stripping PII or tokens before logging, clone the object first (`const safe = { ...payload, token: "[REDACTED]" }`). Mutating the live object in place corrupts downstream business logic.
