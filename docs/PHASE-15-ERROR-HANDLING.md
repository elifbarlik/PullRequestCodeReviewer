# Phase 15 — Error Handling

## Goal
Give API failures a stable, safe response contract while preserving server-side diagnostics.

## Delivered
- Request correlation ID via X-Request-ID.
- Generated request IDs when callers do not provide one.
- Unexpected exceptions return HTTP 500 with a generic message.
- Internal exception text, stack traces and secrets are not returned to clients.
- Server logs retain the exception with the correlation ID for investigation.

## Client contract
Unexpected failures use: {"detail":"Internal server error","request_id":"..."}

## Security invariant
Sensitive implementation details stay in server logs; API clients receive only the safe error contract.
