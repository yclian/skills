# Web UI, Cloud Run & Cross-Platform Mechanics

Hard-won mechanical rules for CSS layout, web rendering, GCP serverless + Terraform bootstrap, and Windows/POSIX shell interoperability.

---

## 1. Web UI & CSS Layout Mechanics

### A. Shrinkable Grid & Flex Columns (`minmax(0, 1fr)` + `min-width: 0`)
- In CSS Grid, `1fr` is shorthand for `minmax(auto, 1fr)`. A wide child (such as a `<table>` or `<pre>` block) pushes the `auto` minimum out to its content width, blowing out the viewport and breaking `position: fixed` toolbars.
- **Rule**: Always declare fluid main columns as `minmax(0, 1fr)` and add `min-width: 0` on flex/grid wrappers so wide content scrolls inside its own `.table-wrap { overflow-x: auto }` container:

```css
.app-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
}
.main-content {
  min-width: 0;
}
.table-wrap {
  overflow-x: auto;
  max-width: 100%;
}
```

### B. CSS `@layer` Cascade Precedence
- **Un-layered CSS always beats `@layer` CSS**, regardless of selector specificity or source order.
- If base desktop styles are placed outside `@layer` while mobile `@media` overrides sit inside `@layer utilities` (or vice versa), the responsive overrides will silently fail. Keep base rules and their `@media` overrides in the same layer tier.

### C. Cheap Initial Shell + Escape Before Format
- **Cheap Initial Render**: Render the page shell and primary navigation immediately; hydrate slow or per-user enrichments asynchronously (`fetch` + `Promise.allSettled`) so one slow upstream never blocks first paint or crashes sibling panels.
- **HTML-Escape Before Injecting Formatting Tags**: When rendering user text or lightweight Markdown, always escape raw HTML entities (`&`, `<`, `>`, `"`, `'`) **first** on the raw string before replacing markdown tokens with safe tags (`<strong>`, `<code>`).

---

## 2. GCP Serverless (Cloud Run) + Terraform 4-Step Bootstrap

A fresh `terraform apply` on a brand-new Cloud Run service fails if Cloud Run tries to pull a container image that hasn't been pushed yet, or mount a Secret Manager secret that has a shell but zero versions.

Execute first-time deployment in **four ordered phases**:

1. **Phase 1 — Foundation & Empty Shells (`terraform apply -target=...`)**:
   - Apply API enablement, Artifact Registry repository, Service Accounts, IAM bindings, and **empty Secret Manager secret shells** (`google_secret_manager_secret`).
2. **Phase 2 — Populate Secret Versions (Out-of-Band CLI)**:
   - Add secret values via `gcloud secrets versions add <secret-id> --data-file=-` so secrets never enter `terraform.tfstate`.
3. **Phase 3 — Build & Push Container Image**:
   - Build and push the image tagged with the git commit SHA (`gcloud builds submit` or `docker buildx build --push`) into the Artifact Registry created in Phase 1.
4. **Phase 4 — Full `terraform apply`**:
   - Deploy the Cloud Run service/job, Cloud Scheduler triggers, and alerting policies now that both secret versions and the container image exist.

---

## 3. Windows / Git-Bash (MSYS2) Path Conversion Guard

When running CLIs on Windows that accept leading-slash virtual paths (such as `suitecloud file:upload --paths "/SuiteScripts/..."`, `suitecloud object:import --destinationfolder "/Objects"`, or Docker/container volume paths):

- **The Trap**: Git-for-Windows Bash and MSYS2 automatically rewrite any bare POSIX argument starting with `/` into a local Windows path (`C:/Program Files/Git/SuiteScripts/...` or `C:\msys64\SuiteScripts\...`) *before* the CLI receives `argv`, causing validation failures.
- **The Rule**: Detect the shell environment first:
  - **PowerShell (`pwsh`)**: No path rewriting occurs—run the command directly.
  - **Git-for-Windows Bash**: Prefix with `MSYS_NO_PATHCONV=1`.
  - **MSYS2**: Prefix with `MSYS2_ARG_CONV_EXCL='*'`.
