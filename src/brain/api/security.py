"""Bearer-only authentication. No ambient cookies or test bypasses."""
import hmac
import os
from typing import Optional
from fastapi import Header, HTTPException


def configured_key():
    key = os.environ.get('BRAIN_API_KEY', '')
    if len(key) < 32 or key.startswith(('brain-secure-', 'change-me', 'replace-')):
        raise HTTPException(status_code=503, detail='Set a random BRAIN_API_KEY of at least 32 characters.')
    return key


def verify_brain_api_key(
    authorization: Optional[str] = Header(None),
    x_brain_api_key: Optional[str] = Header(None, alias='X-Brain-API-Key'),
    brain_token: Optional[str] = None,
) -> bool:
    expected = configured_key()
    token = x_brain_api_key if isinstance(x_brain_api_key, str) else ''
    if isinstance(authorization, str):
        parts = authorization.split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == 'bearer' else ''
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail='Invalid brain bearer token or authentication required.',
                            headers={'WWW-Authenticate': 'Bearer'})
    return True
