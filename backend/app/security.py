"""Access code check and a simple per-IP rate limit (Redis fixed window)."""
import hmac
import time

from fastapi import Depends, Header, HTTPException, Request

from .config import get_settings


def require_access(x_access_code: str | None = Header(default=None, alias="X-Access-Code"),
                   authorization: str | None = Header(default=None)):
    codes = get_settings().access_code_list
    if not codes:
        return  # open mode for local development
    supplied = x_access_code or (authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None)
    if not supplied or not any(hmac.compare_digest(supplied, c) for c in codes):
        raise HTTPException(status_code=401, detail="A valid access code is required (header X-Access-Code).")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def rate_limit(bucket: str, limit: int, window_s: int = 60):
    def dep(request: Request):
        try:
            from redis import Redis
            r = Redis.from_url(get_settings().redis_url, socket_timeout=1)
            key = f"docintel:rl:{bucket}:{client_ip(request)}:{int(time.time() // window_s)}"
            n = r.incr(key)
            if n == 1:
                r.expire(key, window_s + 5)
        except Exception:
            return
        if n > limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    return Depends(dep)
