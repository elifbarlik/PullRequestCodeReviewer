"""GitHub App security policy and request validation for SecPR-TR.

Phase 5 scope:
- keep GitHub App JWT + installation-token authentication;
- scope installation tokens to the minimum permissions used by the app;
- validate webhook event, delivery ID, and installation identifiers;
- keep secrets out of logs and repository code.
"""

import re
from typing import Mapping, Optional

REQUIRED_INSTALLATION_PERMISSIONS = {
    "pull_requests": "write",
    "contents": "read",
    "metadata": "read",
}

SUPPORTED_WEBHOOK_EVENTS = frozenset(
    {"ping", "pull_request", "installation", "installation_repositories"}
)

_DELIVERY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")


def validate_webhook_event(event_type: str) -> str:
    value = (event_type or "").strip()
    if not value:
        raise ValueError("X-GitHub-Event header is required")
    if value not in SUPPORTED_WEBHOOK_EVENTS:
        raise ValueError(f"Unsupported GitHub webhook event: {value}")
    return value


def validate_delivery_id(delivery_id: str) -> str:
    value = (delivery_id or "").strip()
    if not _DELIVERY_ID_RE.fullmatch(value):
        raise ValueError("X-GitHub-Delivery header is missing or invalid")
    return value


def validate_installation_id(
    installation_id: Optional[object], *, required: bool = True
) -> Optional[int]:
    if installation_id is None:
        if required:
            raise ValueError("Webhook payload is missing installation.id")
        return None
    if isinstance(installation_id, bool):
        raise ValueError("installation.id must be a positive integer")
    try:
        value = int(installation_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("installation.id must be a positive integer") from exc
    if value <= 0:
        raise ValueError("installation.id must be a positive integer")
    return value


def validate_token_permissions(
    permissions: Optional[Mapping[str, str]],
) -> bool:
    if not permissions:
        return False
    return all(
        permissions.get(name) == level
        for name, level in REQUIRED_INSTALLATION_PERMISSIONS.items()
    )
