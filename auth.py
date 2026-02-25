from playwright.async_api import Page, BrowserContext
from projects import Project, FormLogin, BasicAuth, CookieAuth


class AuthHandler:
    """Handles authentication for projects."""

    async def login(self, context: BrowserContext, project: Project) -> dict:
        """
        Perform login based on project auth settings.
        Returns dict with status and message.
        """
        if not project.auth or not project.auth.method:
            return {"success": False, "error": "No authentication configured"}

        if project.auth.method == "form":
            return await self._form_login(context, project.auth.form_login)
        elif project.auth.method == "basic":
            return await self._basic_auth(context, project.auth.basic_auth)
        elif project.auth.method == "cookies":
            return await self._cookie_auth(context, project.auth.cookie_auth)
        else:
            return {"success": False, "error": f"Unknown auth method: {project.auth.method}"}

    async def _form_login(self, context: BrowserContext, form: FormLogin) -> dict:
        """Perform form-based login."""
        page = await context.new_page()
        try:
            # Navigate to login page
            await page.goto(form.login_url, wait_until="networkidle")
            login_url = page.url
            debug = {"login_url": login_url}

            # Try each username selector individually
            username_field = None
            for selector in form.username_selector.split(", "):
                selector = selector.strip()
                loc = page.locator(selector)
                if await loc.count() > 0:
                    username_field = loc.first
                    debug["username_selector_matched"] = selector
                    break

            if not username_field:
                # Fallback: find any visible text/email input
                username_field = page.locator(
                    "input[type='email'], input[type='text']"
                ).first
                debug["username_selector_matched"] = "fallback (email/text input)"

            await username_field.wait_for(state="visible", timeout=10000)
            await username_field.click()
            await username_field.fill(form.username)

            # Try each password selector individually
            password_field = None
            for selector in form.password_selector.split(", "):
                selector = selector.strip()
                loc = page.locator(selector)
                if await loc.count() > 0:
                    password_field = loc.first
                    debug["password_selector_matched"] = selector
                    break

            if not password_field:
                password_field = page.locator("input[type='password']").first
                debug["password_selector_matched"] = "fallback (password input)"

            await password_field.click()
            await password_field.fill(form.password)

            # Try each submit selector individually
            submit_button = None
            for selector in form.submit_selector.split(", "):
                selector = selector.strip()
                loc = page.locator(selector)
                if await loc.count() > 0:
                    submit_button = loc.first
                    debug["submit_selector_matched"] = selector
                    break

            if not submit_button:
                submit_button = page.locator("button, input[type='submit']").first
                debug["submit_selector_matched"] = "fallback (any button)"

            # Click submit and wait for navigation or network response
            try:
                async with page.expect_navigation(timeout=10000, wait_until="networkidle"):
                    await submit_button.click()
            except Exception:
                # SPA might not trigger navigation event, wait for network to settle
                import asyncio
                await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle")

            current_url = page.url
            debug["final_url"] = current_url

            # Take a debug screenshot
            import os
            import config
            debug_path = os.path.join(config.SCREENSHOT_DIR, "_login_debug.png")
            await page.screenshot(path=debug_path)
            debug["debug_screenshot"] = debug_path

            # Check if URL changed (success)
            if current_url != login_url and "/login" not in current_url:
                return {
                    "success": True,
                    "message": f"Login successful, redirected to {current_url}",
                    "debug": debug
                }

            # Check for error messages on page
            error_selectors = [
                ".error", ".alert-danger", ".login-error",
                "[class*='error']", "[class*='invalid']",
                ".text-danger", ".text-red", "[role='alert']"
            ]
            for selector in error_selectors:
                loc = page.locator(selector)
                if await loc.count() > 0:
                    text = await loc.first.text_content()
                    if text and text.strip():
                        return {
                            "success": False,
                            "error": f"Login failed: {text.strip()}",
                            "debug": debug
                        }

            # Check if the page content changed (SPA login might stay on same URL)
            has_login_form = await page.locator(
                "input[type='password']"
            ).count() > 0
            if not has_login_form:
                return {
                    "success": True,
                    "message": "Login appears successful (password field gone)",
                    "debug": debug
                }

            return {
                "success": False,
                "error": "Login may have failed - still on login page",
                "debug": debug
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await page.close()

    async def _basic_auth(self, context: BrowserContext, auth: BasicAuth) -> dict:
        """Set up HTTP Basic Auth."""
        try:
            await context.set_extra_http_headers({
                "Authorization": self._make_basic_auth_header(auth.username, auth.password)
            })
            return {
                "success": True,
                "message": "HTTP Basic Auth configured"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _make_basic_auth_header(self, username: str, password: str) -> str:
        """Create Basic Auth header value."""
        import base64
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _cookie_auth(self, context: BrowserContext, auth: CookieAuth) -> dict:
        """Inject cookies for authentication."""
        try:
            await context.add_cookies(auth.cookies)
            return {
                "success": True,
                "message": f"Injected {len(auth.cookies)} cookies"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
