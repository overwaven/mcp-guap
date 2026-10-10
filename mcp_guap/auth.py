#!/usr/bin/env python3
"""Playwright-based authentication for GUAP.

This module provides browser automation to get session cookies from pro.guap.ru.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright

try:
    from . import session_cookies
except ImportError:
    import session_cookies

GUAP_URL = "https://pro.guap.ru"
SSO_AUTH_URL = "https://sso.guap.ru/realms/master/protocol/openid-connect/auth"


async def ensure_playwright_browsers() -> bool:
    """Ensure playwright browsers are installed. Install if needed.
    
    Returns:
        True if browsers are available/installed, False otherwise
    """
    import subprocess
    import sys
    
    # Check if chromium is available using async API
    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch()
                await browser.close()
                return True
            except Exception:
                pass
    except Exception:
        pass
    
    # Try to install
    print("🔧 Installing Playwright browsers (this may take 1-2 minutes)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print("✅ Playwright browsers installed successfully!")
            return True
        else:
            print(f"❌ Failed to install browsers: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error installing browsers: {e}")
        return False


async def authenticate_with_browser(
    save_path: Optional[Path] = None,
    timeout: int = 120,
    headless: bool = False,
) -> dict:
    """Authenticate via browser and extract session cookies.
    
    Args:
        save_path: Path to save cookies JSON file (default: cookie.json in package dir)
        timeout: Seconds to wait for user authentication
        headless: Run browser in headless mode (not recommended for auth)
    
    Returns:
        dict with 'success', 'cookies', 'save_path'
    """
    if save_path is None:
        save_path = Path(__file__).parent / "cookie.json"
    
    # Ensure browsers are installed
    if not await ensure_playwright_browsers():
        return {
            "success": False,
            "error": "Failed to install Playwright browsers. Please install manually: uvx playwright install chromium"
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("="*60)
        print("🔐 Авторизация в ГУАП")
        print("="*60)
        print(f"\nОткрываю {GUAP_URL}...")
        print("Пожалуйста, войдите в систему используя ваши учетные данные.")
        print(f"У вас есть {timeout} секунд на авторизацию.\n")
        
        # Открываем главную страницу
        await page.goto(GUAP_URL)
        
        # Кликаем на вход
        try:
            await page.click('text="Вход в личный кабинет"')
            print("✅ Перехожу на страницу авторизации...")
        except:
            print("⚠️  Не удалось найти кнопку входа, возможно уже на странице SSO")
        
        # Ждём пока URL изменится - это значит что авторизация прошла
        print("⏳ Ожидаю завершения авторизации...")
        print("   (URL должен измениться с sso.guap.ru на pro.guap.ru)")
        
        start_time = asyncio.get_event_loop().time()
        authenticated = False
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            current_url = page.url
            if "pro.guap.ru" in current_url and "sso.guap.ru" not in current_url:
                # Проверяем что мы на profile или другой внутренней странице
                if "/inside/" in current_url or current_url == GUAP_URL + "/":
                    authenticated = True
                    print(f"\n✅ Авторизация успешна!")
                    print(f"   Текущий URL: {current_url}")
                    break
            
            await asyncio.sleep(1)
        
        if not authenticated:
            await browser.close()
            return {
                "success": False,
                "error": f"Timeout: авторизация не завершена за {timeout} секунд",
            }
        
        # Получаем cookies
        cookies = await context.cookies()
        
        # Фильтруем только guap cookies
        guap_cookies = [c for c in cookies if session_cookies._allowed(c.get("domain", ""))]
        
        if not guap_cookies:
            await browser.close()
            return {
                "success": False,
                "error": "No cookies found for guap.ru domain",
            }
        
        # Preserve domain, path and expiry for subsequent GUAP and SSO requests.
        import httpx
        session = session_cookies.SessionCookies(httpx.Cookies(), save_path)
        for record in guap_cookies:
            session.cookies.jar.set_cookie(session_cookies._cookie(record))
        session.save(session.cookies)
        
        print(f"\n🍪 Сохранено {len(guap_cookies)} cookies:")
        for c in guap_cookies:
            print(f"   {c['name']}")
        
        print(f"\n💾 Cookies сохранены в: {save_path}")
        
        await browser.close()
        
        return {
            "success": True,
            "cookies": guap_cookies,
            "save_path": str(save_path),
        }


def get_saved_cookie(cookie_file: Optional[Path] = None) -> Optional[str]:
    """Legacy helper: return only cookies applicable to the GUAP profile URL."""
    session = session_cookies.load(cookie_file)
    if session is None:
        return None
    import httpx
    with httpx.Client(cookies=session.cookies) as client:
        return client.build_request("GET", GUAP_URL + "/inside/profile").headers.get("Cookie")


async def check_auth(cookie_string: Optional[str] = None) -> dict:
    """Check if current cookies are valid.
    
    Args:
        cookie_string: Cookie string to test. If None, loads from file.
    
    Returns:
        dict with 'valid' (bool) and 'user_info' if valid
    """
    import httpx
    
    session = session_cookies.from_header(cookie_string) if cookie_string is not None else session_cookies.configured()
    if session is None or not session.cookies.jar:
        return {"valid": False, "error": "No cookies provided or found"}
    
    try:
        async with httpx.AsyncClient(
            base_url=GUAP_URL,
            cookies=session.cookies,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            follow_redirects=True,
            timeout=30,
        ) as client:
            try:
                response = await client.get("/inside/profile")
            finally:
                session.save(client.cookies)
            
            # Проверяем что мы получили профиль, а не страницу логина
            if response.status_code == 200 and "login" not in response.text.lower():
                return {
                    "valid": True,
                    "status_code": response.status_code,
                    "url": str(response.url),
                }
            else:
                return {
                    "valid": False,
                    "status_code": response.status_code,
                    "error": "Invalid or expired cookies",
                }
                
    except Exception as e:
        return {"valid": False, "error": str(e)}


# CLI
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        # Check mode
        result = asyncio.run(check_auth())
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("valid") else 1)
    else:
        # Auth mode
        result = asyncio.run(authenticate_with_browser())
        if result.get("success"):
            print("\n✅ Авторизация успешно завершена!")
            print(f"Cookies saved to: {result['save_path']}")
        else:
            print(f"\n❌ Ошибка: {result.get('error')}")
            sys.exit(1)
