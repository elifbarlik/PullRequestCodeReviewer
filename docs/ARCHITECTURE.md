# SecPR-TR Architecture

**Baseline branch:** `feat/sprint-4-launch-hardening`  
**Baseline commit:** `35bd64ad8522ad9d14d22a3eb9b3a35e05b8f6e8`  
**Captured:** 2026-09-28  
**Purpose:** document the current system before launch-hardening changes. This document describes the code as it exists at the baseline commit; it does not define future architecture.

## 1. System overview

SecPR-TR is a FastAPI application that receives GitHub App webhooks, analyzes pull requests with Semgrep and Gemini, posts the result back to GitHub, and records operational/security metadata in PostgreSQL when `DATABASE_URL` is configured.

```text
GitHub User
   |
   | Install GitHub App
   v
GitHub App
   |
   | pull_request / installation webhooks
   v
FastAPI on Fly.io
   |
   +--> GitHub API
   |
   +--> Semgrep
   |
   +--> Gemini
   |
   +--> PostgreSQL / Neon (optional at runtime)
   |
   v
GitHub PR review/comment

Browser
   |
   +--> /
   +--> /dashboard
             |
             v
        static HTML/JS/CSS
```

## 2. Request lifecycle

### Pull request event

1. GitHub sends `POST /webhook`.
2. The application reads the raw body and validates `X-Hub-Signature-256` with `GITHUB_WEBHOOK_SECRET`.
3. `X-GitHub-Delivery` is checked against a process-local LRU of recent deliveries.
4. For `pull_request.opened` and `pull_request.synchronize`, the analysis is scheduled with FastAPI `BackgroundTasks` and the webhook returns immediately.
5. The review job ensures the installation exists in the database when DB access is enabled.
6. A `GitHubAppClient` obtains installation-scoped GitHub API access and loads PR diff/details/files.
7. Semgrep scans supported file types, but findings are filtered to lines actually added/changed in the PR.
8. The short-summary LLM stage and Semgrep scan run concurrently.
9. Gemini produces the detailed review/security explanation using the diff and Semgrep result.
10. Inline GitHub review comments are created when a finding can be mapped to an added line; otherwise findings fall back to the summary comment.
11. Usage and finding metadata are recorded when the database is enabled.

### Installation lifecycle

- `installation.created` -> installation row upsert.
- `installation.deleted` -> installation soft-delete.
- `installation_repositories` -> repository changes are logged.

## 3. GitHub App authentication

The current implementation uses two distinct security mechanisms:

- **Webhook authentication:** HMAC SHA-256 via `GITHUB_WEBHOOK_SECRET`.
- **GitHub API authentication:** GitHub App JWT followed by an installation access token.

Admin settings endpoints use `ADMIN_SECRET` in the `X-Admin-Token` header.

The GitHub client is installation-scoped so PR operations are performed with the relevant installation credentials.

## 4. Webhook flow and reliability baseline

Current webhook behavior:

- Signature validation is mandatory.
- Unsupported events/actions are ignored.
- `pull_request.opened` and `pull_request.synchronize` are accepted.
- Recent delivery IDs are tracked in process memory using `OrderedDict`.
- Long-running PR work uses FastAPI `BackgroundTasks`.

Current reliability limitation captured for later hardening:

```text
process restart
   |
   +--> delivery LRU is lost
   +--> queued BackgroundTask work can be lost
```

This is intentionally a Phase 0 observation, not a Phase 0 code change.

## 5. Security analysis pipeline

### Semgrep

Semgrep is the deterministic detection layer.

Current defaults include:

- `p/default`
- `p/python`
- `p/security-audit`
- `p/secrets`

Installation settings can select from an allow-list of supported `p/...` configs.

Current scan boundaries include:

- supported source extensions only;
- maximum of **60** scannable files per PR;
- files larger than **1 MB** are skipped by the Semgrep command;
- small PRs use a 45s timeout;
- larger scans use a 120s timeout;
- findings are retained only when they intersect changed/added diff lines.

### Gemini

Gemini is used for summary and explanatory review output. The architecture intentionally separates:

```text
Detection      = Semgrep
Explanation    = Gemini
```

The current code also has a bounded, process-local LLM response cache with TTL/LRU controls and a global output-token ceiling.

## 6. Database architecture

The runtime database layer is optional at startup:

- `DATABASE_URL` missing -> DB is disabled;
- `DATABASE_URL` present -> SQLAlchemy/PostgreSQL is enabled;
- application startup calls Alembic upgrade to `head`.

Baseline schema currently contains:

- `installations`
- `usage_logs`
- `findings`
- `settings`

The current schema does **not** yet contain the future launch-plan entities `repositories`, `review_runs`, or `webhook_deliveries`.

Repository functions keep database failures from blocking the primary review/comment path.

## 7. Web application

Current browser-facing routes:

- `GET /` -> `static/index.html`
- `GET /dashboard` -> `static/dashboard.html`
- `/static/*` -> static asset mount

Current API-facing operational routes include:

- `GET /health`
- `GET /stats`
- `POST /local-review`
- `GET /installations/{installation_id}/settings`
- `PUT /installations/{installation_id}/settings`
- `POST /webhook`

The dashboard is a static frontend in this baseline and is not yet a user-authenticated, installation-scoped SaaS dashboard.

## 8. Deployment

Current deployment target:

- Fly.io app: `pr-reviewer-quiet-fire-1218`
- Primary region: `fra`
- Internal HTTP port: `8000`
- Minimum running machines: `1`
- VM: 2 GB memory, 2 shared CPUs

The Dockerfile uses a multi-stage Python 3.11 image and installs Semgrep in the builder environment. Semgrep rule packs are warmed during image build.

**Baseline deployment gap:** the baseline Dockerfile copies `app/` but does not copy `static/` or the Alembic files into the runtime image. This is carried forward as a known Phase 1 hardening item.

## 9. Configuration

Important environment variables at baseline:

```text
GEMINI_API_KEY
GITHUB_APP_ID
GITHUB_APP_PRIVATE_KEY
GITHUB_APP_PRIVATE_KEY_PATH
GITHUB_WEBHOOK_SECRET
DATABASE_URL
POSTGRES_PASSWORD
ADMIN_SECRET

LLM_CACHE_ENABLED
LLM_CACHE_TTL_SECONDS
LLM_CACHE_MAX_ENTRIES
LLM_MAX_OUTPUT_TOKENS
GEMINI_MODEL
```

Secrets are expected to be provided through environment configuration rather than repository source files.

## 10. Failure scenarios already handled

- Invalid/missing webhook signature -> request rejected.
- Missing admin secret -> settings endpoints unavailable.
- Missing database configuration -> application continues without DB.
- Database migration failure -> startup logs the failure and the service continues without DB.
- Semgrep unavailable/error -> analysis records a distinguishable non-success Semgrep state rather than pretending the scan was clean.
- Inline review API failure -> summary-comment fallback is attempted.
- Missing/invalid scan configuration -> validated against the allow-list and defaults are restored.
- Large diff -> diff truncation is applied before LLM analysis.

## 11. Known baseline gaps

The following are intentionally documented for later phases:

1. Webhook deduplication is process-local rather than persistent.
2. PR review execution uses `BackgroundTasks`, so queued work is not durable across process restarts.
3. Review lifecycle is not persisted as a dedicated `review_runs` entity.
4. Repository membership is not modeled as a dedicated `repositories` entity.
5. Database isolation is not yet enforced through an authenticated user -> installation authorization layer.
6. Dashboard routes are not yet authenticated/tenant-scoped.
7. `/health` reports version `0.3.0` while the FastAPI application is version `0.5.0`.
8. Baseline Docker runtime image omits `static/` and Alembic files.
9. PR file retrieval and maximum review size need explicit pagination/size hardening.
10. Public product documentation/README is incomplete at this baseline snapshot.

## 12. Future architecture guardrails

For the launch-hardening work, changes should preserve these principles:

- Keep FastAPI + Fly.io + PostgreSQL/Neon as the simple deployment model.
- Keep Semgrep as the deterministic detection layer.
- Keep Gemini as an explanation/summary layer rather than the sole vulnerability detector.
- Scope persisted data by GitHub installation.
- Prefer additive Alembic migrations.
- Avoid introducing Kafka, Kubernetes, microservice decomposition, or a distributed cache unless a later measured requirement justifies it.
