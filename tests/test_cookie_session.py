"""Cookie domain and SSO redirect regression checks for GUAP MCP."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from mcp_guap import auth, guap_client, session_cookies


class CookieSessionTest(unittest.TestCase):
    def test_sso_redirect_refreshes_and_persists_both_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.json"
            path.write_text(json.dumps({"cookies": [
                {"name": "KEYCLOAK_SESSION", "value": "sso-old", "domain": "sso.guap.ru",
                 "path": "/realms/master/", "expires": -1, "secure": True},
                {"name": "PHPSESSID", "value": "old", "domain": "pro.guap.ru",
                 "path": "/", "expires": 1, "secure": True},
            ]}), encoding="utf-8")
            seen = []

            def respond(request):
                seen.append((str(request.url), request.headers.get("cookie", "")))
                if request.url.path == "/inside/profile" and len(seen) == 1:
                    return httpx.Response(302, headers={"location": "https://sso.guap.ru/realms/master/protocol/openid-connect/auth"})
                if request.url.host == "sso.guap.ru":
                    return httpx.Response(302, headers={
                        "location": "https://pro.guap.ru/oauth/callback",
                        "set-cookie": "KEYCLOAK_SESSION=sso-new; Path=/realms/master/; Secure; HttpOnly",
                    })
                if request.url.path == "/oauth/callback":
                    return httpx.Response(302, headers={
                        "location": "/inside/profile",
                        "set-cookie": "PHPSESSID=new; Path=/; Secure; HttpOnly",
                    })
                return httpx.Response(200, text="profile")

            session = session_cookies.load(path)
            with guap_client._make_client(session, transport=httpx.MockTransport(respond)) as client:
                self.assertEqual(client.get("/inside/profile").status_code, 200)
            self.assertEqual(len(seen), 4)
            self.assertNotIn("KEYCLOAK_SESSION", seen[0][1])
            self.assertIn("KEYCLOAK_SESSION=sso-old", seen[1][1])
            self.assertNotIn("PHPSESSID", seen[1][1])
            self.assertIn("PHPSESSID=new", seen[3][1])
            restored = session_cookies.load(path)
            self.assertEqual(restored.cookies.get("PHPSESSID", domain="pro.guap.ru"), "new")
            self.assertEqual(restored.cookies.get("KEYCLOAK_SESSION", domain="sso.guap.ru", path="/realms/master/"), "sso-new")
            self.assertNotIn("cookie_string", json.loads(path.read_text(encoding="utf-8")))
            with guap_client._make_client(restored, transport=httpx.MockTransport(respond)) as client:
                self.assertEqual(client.get("/inside/profile").status_code, 200)
            self.assertEqual(len(seen), 5)
            self.assertIn("PHPSESSID=new", seen[4][1])
            self.assertNotIn("KEYCLOAK_SESSION", seen[4][1])

    def test_auth_check_persists_cookie_from_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.json"
            path.write_text(json.dumps({"cookies": [{
                "name": "KEYCLOAK_SESSION", "value": "active", "domain": "sso.guap.ru",
                "path": "/realms/master/", "expires": -1, "secure": True,
            }]}), encoding="utf-8")
            session = session_cookies.load(path)

            def respond(request):
                if request.url.host == "sso.guap.ru":
                    self.assertIn("KEYCLOAK_SESSION=active", request.headers.get("cookie", ""))
                    return httpx.Response(302, headers={"location": "https://pro.guap.ru/inside/profile",
                                                        "set-cookie": "KEYCLOAK_SESSION=renewed; Path=/realms/master/; Secure"})
                if "PHPSESSID=fresh" in request.headers.get("cookie", ""):
                    return httpx.Response(200, text="profile")
                return httpx.Response(302, headers={"location": "https://sso.guap.ru/realms/master/auth",
                                                    "set-cookie": "PHPSESSID=fresh; Path=/; Secure"})

            original_client = httpx.AsyncClient
            with patch.object(auth.session_cookies, "configured", return_value=session), \
                 patch.object(httpx, "AsyncClient", side_effect=lambda **kw: original_client(
                     transport=httpx.MockTransport(respond), **kw)):
                result = asyncio.run(auth.check_auth())
            self.assertTrue(result["valid"])
            restored = session_cookies.load(path)
            self.assertEqual(restored.cookies.get("PHPSESSID", domain="pro.guap.ru"), "fresh")
            self.assertEqual(restored.cookies.get("KEYCLOAK_SESSION", domain="sso.guap.ru",
                                                  path="/realms/master/"), "renewed")


if __name__ == "__main__":
    unittest.main()
