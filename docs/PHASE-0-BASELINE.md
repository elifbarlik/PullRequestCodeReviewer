# Phase 0 — Launch Hardening Baseline

**Captured:** 2026-09-28  
**Baseline branch:** `feat/sprint-4-launch-hardening`  
**Parent branch:** `feat/sprint-3-dashboard-landing`  
**Baseline commit:** `35bd64ad8522ad9d14d22a3eb9b3a35e05b8f6e8`

## 0. Phase 0 objective

Freeze the current implementation, record the system boundaries and known limitations, and create a stable reference point before production-hardening changes.

The branch is intentionally based on the Sprint 3 dashboard/landing snapshot. Phase 0 does not modify application behavior.

## 1. Branch state

At baseline capture:

- `feat/sprint-3-dashboard-landing` -> `35bd64ad8522ad9d14d22a3eb9b3a35e05b8f6e8`
- `feat/sprint-4-launch-hardening` -> `35bd64ad8522ad9d14d22a3eb9b3a35e05b8f6e8`

This means the launch-hardening branch begins as a clean snapshot of the Sprint 3 branch.

The current `main` branch has subsequently moved ahead of this snapshot, so this document is the **starting-code baseline**, not a claim that `main` and the baseline branch are identical.

## 2. Component inventory

| Component | Baseline state |
|---|---|
| FastAPI | Present |
| GitHub App authentication | Present |
| Webhook HMAC verification | Present |
| Pull request event handling | Present |
| Semgrep scanner | Present |
| Gemini review/explanation | Present |
| PostgreSQL / Neon integration | Present, optional by configuration |
| Alembic | Present |
| Static landing page | Present |
| Static dashboard | Present |
| Rate limiting | Present for `/local-review` |
| LLM cache | Present, process-local |
| Admin authentication | Present for installation settings |
| Dedicated review lifecycle table | Not present |
| Dedicated repository entity | Not present |
| Persistent webhook delivery table | Not present |
| User-level dashboard authentication | Not present |

## 3. Current API surface

```text
GET  /health
GET  /stats
POST /local-review

GET  /installations/{id}/settings
PUT  /installations/{id}/settings

POST /webhook

GET  /
GET  /dashboard
GET  /static/*
```

## 4. Current data model

```text
installations
    |
    +--> usage_logs
             |
             +--> findings

settings
    |
    +--> installation_id
```

Current Alembic baseline migration is `0001_baseline_schema`.

## 5. Current review flow

```text
GitHub PR
   |
   v
POST /webhook
   |
   +--> signature verification
   |
   +--> delivery de-dup (process-local)
   |
   v
FastAPI BackgroundTasks
   |
   v
GitHub PR bundle
   |
   +------> Semgrep
   |
   +------> Gemini summary
              |
              v
         Gemini detail/security
              |
              v
     GitHub inline review/comment
              |
              v
       usage_logs / findings
```

## 6. Baseline limits and controls

- `/local-review`: 10 requests/hour per remote address.
- PR security scan: maximum 60 scannable files.
- Semgrep max target size: 1,000,000 bytes.
- Semgrep timeout: 45s for small scans, 120s for larger scans.
- LLM cache defaults: enabled, 300s TTL, 256 entries.
- LLM output ceiling: 2048 tokens unless configured lower/higher within the code's clamp.
- Webhook duplicate-memory capacity: 500 delivery IDs.

## 7. Baseline known gaps

### Production packaging
The baseline Dockerfile copies `app/` but not `static/` or the Alembic configuration/migrations. This is a known production-image gap to address in Phase 1.

### Health endpoint
The FastAPI application declares version `0.5.0`, while `/health` currently returns version `0.3.0`.

### Durable processing
Webhook de-duplication and LLM cache are process-local. PR analysis uses FastAPI `BackgroundTasks`.

### Persistence model
The current schema records installations, usage, findings, and settings, but there is no persisted `review_runs` lifecycle.

### Tenant isolation
The installation identifier exists in the data model, but the dashboard is not yet authenticated and there is no user-to-installation authorization layer.

### Large PR handling
There is a 60-file scan cap, but the launch plan still calls for explicit pagination and transparent partial-scan behavior.

## 8. Test/CI baseline

The repository contains:

- 11 test modules under `tests/`.
- Semgrep benchmark cases under `benchmarks/`.
- Benchmark runner: `scripts/run_benchmark.py`.
- Webhook helper: `scripts/test_webhook.py`.
- CI workflow: `.github/workflows/test.yml`.
- Deployment workflow: `.github/workflows/fly-deploy.yml`.

This environment could not execute a local clone because outbound GitHub DNS/network access was unavailable during baseline capture. Therefore, this Phase 0 record does **not** claim a fresh local test run.

Separately, the repository's current `main` branch has recent successful GitHub Actions runs for both **Tests** and **Fly Deploy**; those results are operational context for `main`, not a fresh test result for this frozen baseline branch.

## 9. Phase 0 exit criteria

- [x] Launch-hardening branch exists.
- [x] Branch starts from the Sprint 3 dashboard/landing snapshot.
- [x] Main system components documented.
- [x] Request lifecycle documented.
- [x] Configuration and deployment baseline recorded.
- [x] Known production/reliability gaps recorded.
- [x] No application behavior changed as part of Phase 0.
- [ ] Fresh runtime smoke tests — deferred to Phase 1.
- [ ] Docker image validation — deferred to Phase 1.
- [ ] Migration verification against production DB — deferred to Phase 1.

## 10. Next phase

Phase 1 starts with production packaging and runtime validation:

1. Copy `static/`, `alembic.ini`, and `alembic/` into the production image.
2. Validate Alembic startup/migration behavior.
3. Harden the health endpoint for production observability.
4. Add production smoke/integration checks.

