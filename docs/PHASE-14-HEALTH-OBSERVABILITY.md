# Phase 14 — Health & Observability

## Goal
Keep operational visibility useful without leaking cross-tenant usage data.

## Delivered
- /metrics now requires an authenticated GitHub user.
- Operational and cost metrics are scoped to the user's installation IDs.
- Empty installation scope returns zero metrics.
- Existing /health remains suitable for infrastructure health checks and does not expose secrets.
- Sentry/structured logging remain the server-side error/diagnostic channels.

## Security invariant
Product usage metrics follow the same isolation boundary as dashboard data.

## Out of scope
External monitoring vendor configuration and Marketplace submission.
