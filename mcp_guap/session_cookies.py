"""Persistent, domain-aware GUAP and SSO cookies for HTTPX."""

import json
import os
import tempfile
from dataclasses import dataclass
from http.cookiejar import Cookie
from pathlib import Path

import httpx


DEFAULT_PATH = Path(__file__).parent / "cookie.json"


def _allowed(domain: str) -> bool:
    domain = domain.lstrip(".").lower()
    return domain == "guap.ru" or domain.endswith(".guap.ru")


def _cookie(record: dict) -> Cookie:
    domain = record["domain"]
    path = record.get("path") or "/"
    expires = record.get("expires", record.get("expiry"))
    if expires is not None and expires <= 0:
        expires = None
    return Cookie(
        version=0, name=record["name"], value=record["value"],
        port=None, port_specified=False, domain=domain,
        domain_specified=domain.startswith("."), domain_initial_dot=domain.startswith("."),
        path=path, path_specified=True, secure=bool(record.get("secure", False)),
        expires=int(expires) if expires is not None else None, discard=expires is None,
        comment=None, comment_url=None,
        rest={"HttpOnly": record.get("httpOnly", False), "SameSite": record.get("sameSite")},
        rfc2109=False,
    )


def _records(cookies: httpx.Cookies) -> list[dict]:
    return [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
         "expires": c.expires if c.expires is not None else -1,
         "secure": c.secure, "httpOnly": "HttpOnly" in c._rest and c._rest["HttpOnly"] is not False,
         "sameSite": c._rest.get("SameSite")}
        for c in cookies.jar if _allowed(c.domain)
    ]


@dataclass
class SessionCookies:
    cookies: httpx.Cookies
    path: Path | None = None

    def save(self, cookies: httpx.Cookies) -> None:
        if self.path is None:
            return
        data = {"url": "https://pro.guap.ru", "cookies": _records(cookies)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".guap-cookies-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False, indent=2)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def from_header(value: str) -> SessionCookies:
    cookies = httpx.Cookies()
    for item in value.split(";"):
        if "=" in item:
            name, val = item.strip().split("=", 1)
            if name:
                cookies.set(name, val, domain="pro.guap.ru", path="/")
    return SessionCookies(cookies)


def load(path: Path | None = None) -> SessionCookies | None:
    if path is None:
        path = next((p for p in (DEFAULT_PATH, DEFAULT_PATH.parent.parent / "cookie.json") if p.exists()), None)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return from_header(path.read_text(encoding="utf-8").strip())
    cookies = httpx.Cookies()
    for record in data.get("cookies", []):
        if _allowed(record.get("domain", "")):
            cookies.jar.set_cookie(_cookie(record))
    if not cookies.jar and data.get("cookie_string"):
        cookies = from_header(data["cookie_string"]).cookies
    return SessionCookies(cookies, path)


def configured() -> SessionCookies | None:
    override = os.environ.get("GUAP_COOKIE", "").strip()
    return from_header(override) if override else load()
