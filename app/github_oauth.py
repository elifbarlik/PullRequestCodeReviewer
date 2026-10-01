"""GitHub App user authorization for the product dashboard.

The review worker continues to authenticate as the GitHub App installation.
This module only authenticates a human dashboard user and records the
installation IDs that GitHub reports the user can access.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Optional

import requests
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"
SESSION_COOKIE = "secpr_session"
STATE_COOKIE = "secpr_oauth_state"
SESSION_TTL_SECONDS = 3600
STATE_TTL_SECONDS = 600


def _secret() -> bytes:
    value = os.getenv("GITHUB_OAUTH_SESSION_SECRET", "").strip()
    if not value:
        raise RuntimeError("GITHUB_OAUTH_SESSION_SECRET yapılandırılmamış")
    return value.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: dict[str, Any]) -> str:
    raw = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _verify(value: str, required_exp: bool = True) -> Optional[dict[str, Any]]:
    try:
        raw, supplied = value.split(".", 1)
        expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(_unb64(raw))
        if required_exp and int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https"


def _client_id() -> str:
    value = os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()
    if not value:
        raise RuntimeError("GITHUB_OAUTH_CLIENT_ID yapılandırılmamış")
    return value


def _redirect_uri(request: Request) -> str:
    configured = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return str(request.base_url).rstrip("/") + "/auth/github/callback"


def start_login(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    state_value = _sign({"state": state, "exp": int(time.time()) + STATE_TTL_SECONDS})
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(request),
        "state": state,
        "allow_signup": "false",
    }
    from urllib.parse import urlencode
    response = RedirectResponse(GITHUB_AUTHORIZE_URL + "?" + urlencode(params), status_code=302)
    response.set_cookie(
        STATE_COOKIE, state_value, max_age=STATE_TTL_SECONDS, httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
    )
    return response


def _github_json(method: str, url: str, **kwargs) -> dict[str, Any]:
    headers = kwargs.pop("headers", {})
    headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    response = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    response.raise_for_status()
    return response.json()


def finish_login(request: Request, code: str, state: str) -> RedirectResponse:
    state_cookie = _verify(request.cookies.get(STATE_COOKIE, ""))
    if not state_cookie or not hmac.compare_digest(str(state_cookie.get("state", "")), state):
        raise HTTPException(status_code=400, detail="OAuth state doğrulaması başarısız")

    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    if not client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth secret yapılandırılmamış")

    token = _github_json(
        "POST",
        GITHUB_TOKEN_URL,
        json={
            "client_id": _client_id(),
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": _redirect_uri(request),
        },
    )
    access_token = token.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="GitHub OAuth access token alınamadı")

    auth_headers = {"Authorization": f"Bearer {access_token}"}
    user = _github_json("GET", f"{GITHUB_API}/user", headers=auth_headers)
    installations_response = _github_json(
        "GET", f"{GITHUB_API}/user/installations", headers=auth_headers
    )
    installation_ids = [
        int(item["id"]) for item in installations_response.get("installations", [])
        if str(item.get("id", "")).isdigit()
    ]

    # The access token is intentionally not persisted or placed in the cookie.
    # The dashboard session only contains the GitHub user identity and the
    # installation IDs returned by GitHub at login time.
    session = _sign({
        "sub": int(user["id"]),
        "login": str(user.get("login", ""))[:255],
        "installations": installation_ids[:500],
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    })
    response = RedirectResponse("/dashboard", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    response.set_cookie(
        SESSION_COOKIE, session, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=os.getenv("ENVIRONMENT", "production") != "local",
        samesite="lax",
    )
    return response


def current_user(request: Request) -> Optional[dict[str, Any]]:
    value = request.cookies.get(SESSION_COOKIE, "")
    if not value:
        return None
    return _verify(value)


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="GitHub ile giriş gerekli")
    return user


def logout() -> RedirectResponse:
    response = RedirectResponse("/dashboard", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response
