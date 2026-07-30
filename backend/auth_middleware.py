"""
Clerk JWT verification for FastAPI.

Requires CLERK_JWKS_URL env var, found in Clerk dashboard:
  API Keys → Advanced → JWT Verification Key (JWKS URL)
  Format: https://<your-app>.clerk.accounts.dev/.well-known/jwks.json
"""

import os
from typing import Optional

from jwt import PyJWKClient, decode as jwt_decode, PyJWTError

_jwks_client: Optional[PyJWKClient] = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = os.getenv("CLERK_JWKS_URL", "")
        if not url:
            raise RuntimeError("CLERK_JWKS_URL is not set in environment")
        _jwks_client = PyJWKClient(url, cache_jwk_set=True, lifespan=600)
    return _jwks_client


def get_clerk_user_id(authorization_header: str) -> Optional[str]:
    """
    Verify a Clerk session JWT from the Authorization: Bearer <token> header.
    Returns the Clerk user ID (sub claim) on success, None on failure.
    """
    if not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header[7:].strip()
    if not token:
        return None
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt_decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload.get("sub")
    except (PyJWTError, Exception):
        return None
