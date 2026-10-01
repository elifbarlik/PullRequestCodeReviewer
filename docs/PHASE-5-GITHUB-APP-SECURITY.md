# Phase 5 — GitHub App Security Audit

## Scope

This phase hardens only the GitHub App security boundary. It does not introduce a new service, queue, authentication provider, or database model.

## Authentication

- GitHub App authentication remains App JWT → installation access token.
- JWT lifetime remains bounded to 9 minutes with a 60-second clock-skew allowance.
- Installation access tokens remain cached until their refresh buffer is reached.
- The runtime now verifies that the token response exposes the minimum permissions required by the review engine:
  - Pull requests: write
  - Contents: read
  - Metadata: read
- A token that does not expose the required scope is rejected before it is used.

## Private key and token handling

- The private key is loaded only from GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH.
- The private key is never written to repository files by the application.
- Installation-token error logging no longer includes the upstream response body, preventing accidental propagation of sensitive response content into logs.
- The actual access token is not logged.

## Webhook security

The webhook now validates, before event routing:

1. HMAC SHA-256 signature.
2. Supported X-GitHub-Event value.
3. Non-empty, bounded X-GitHub-Delivery identifier.
4. Positive installation.id for installation-scoped events.

Supported events are explicitly limited to:

- ping
- pull_request
- installation
- installation_repositories

Unsupported events are rejected rather than entering the event-processing path.

Duplicate protection from the earlier phases remains in place through the persistent delivery claim.

## Permissions

The application runtime uses only:

- Pull requests: read/write — required to publish PR reviews.
- Contents: read — required to read changed file contents.
- Metadata: read — required by GitHub repository/app APIs.

No broader runtime permission is requested by the token creation call.

The GitHub App's configured permissions in GitHub Developer Settings must still be reviewed manually; source code cannot change the App's configured permission policy.

## Secrets

Expected production secrets/configuration remain environment/secret-manager values:

GITHUB_APP_ID, GITHUB_PRIVATE_KEY, GITHUB_PRIVATE_KEY_PATH, GITHUB_WEBHOOK_SECRET, GEMINI_API_KEY, DATABASE_URL, ADMIN_SECRET.

No secret value is committed as part of Phase 5.

## Test coverage

Phase 5 adds tests for:

- webhook event allow-list;
- delivery ID validation;
- installation ID validation;
- required token permission levels;
- rejection of insufficient token permissions;
- acceptance of the minimum required permission set;
- missing delivery/installation webhook metadata;
- unsupported webhook events;
- protection against logging the installation access token on token-scope failure.

## Exit criteria

Phase 5 is complete when the branch CI is green and the GitHub App configuration is manually checked to match the minimum permission set above.
