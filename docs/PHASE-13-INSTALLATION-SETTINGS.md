# Phase 13 — Installation Settings UX

## Goal
Make installation-level Semgrep/review settings manageable by the authenticated GitHub user.

## Delivered
- Settings GET/PUT now require the GitHub user session.
- A user may access only installation IDs present in their signed session.
- Cross-installation access returns 404.
- Dashboard exposes the user's installation IDs and basic settings controls.
- Existing ruleset validation remains enforced before persistence.
- Reset-to-default ruleset remains available.

## Security invariant
current_user → allowed installation IDs → settings read/write

No admin secret is required for a normal user to manage an installation they can access.

## Out of scope
Marketplace submission and billing.
