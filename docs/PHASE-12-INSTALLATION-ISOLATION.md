# Phase 12 — Installation Isolation

## Goal

Ensure dashboard and product statistics are scoped to the GitHub App installations visible to the authenticated GitHub user.

## Scope

- Dashboard summary, recent reviews and review detail already receive the authenticated session's installation IDs.
- `/stats` now requires an authenticated GitHub user and passes the user's installation IDs to the repository layer.
- `get_stats_summary()` accepts an explicit installation scope and applies it to installation and usage-log queries.
- Empty installation scope returns zeroed statistics rather than global data.
- Tests cover both authenticated access and cross-installation isolation.

## Security invariant

A dashboard/statistics query must never fall back to a global `SELECT * FROM ...` style read when a user has no matching installations.

The authenticated session is the source of the allowed installation IDs:

`current_user → installations → repository query`

## Out of scope

- Installation settings UX (Phase 13).
- Health/observability changes (Phase 14).
- General error-handling redesign (Phase 15).
- Marketplace submission.
