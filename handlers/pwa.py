"""check_pwa: web-app manifest validation, service-worker state, installability."""
import asyncio
import json
from urllib.parse import urljoin, urlparse

from runtime import get_tester, session_manager
from sessions import real_page

from .registry import tool

_INSTALL_DISPLAYS = ("standalone", "fullscreen", "minimal-ui")

# Recorded by an init script in url mode (must be installed before the page
# scripts run; sessions opened earlier can't observe it).
_BIP_INIT = """() => {
    window.__periscope_bip = false;
    window.addEventListener('beforeinstallprompt', () => { window.__periscope_bip = true; });
}"""


def _icon_sizes(icon: dict) -> list[int]:
    out = []
    for token in str(icon.get("sizes") or "").split():
        if token.lower() == "any":
            out.append(10_000)
            continue
        try:
            w, h = token.lower().split("x")
            out.append(min(int(w), int(h)))
        except ValueError:
            continue
    return out


def validate_manifest(manifest: dict, manifest_url: str) -> list[str]:
    """Installability-oriented manifest problems, in plain language."""
    problems = []
    if not (manifest.get("name") or "").strip():
        problems.append("missing 'name' (shown on the home screen / install dialog)")
    if not (manifest.get("short_name") or "").strip():
        problems.append("missing 'short_name' (used where the full name doesn't fit)")
    icons = manifest.get("icons") or []
    sizes = [s for i in icons if isinstance(i, dict) for s in _icon_sizes(i)]
    if not any(s >= 192 for s in sizes):
        problems.append("no icon of at least 192x192 (Chrome requires one for install)")
    if not any(s >= 512 for s in sizes):
        problems.append("no icon of at least 512x512 (splash screen / store listing)")
    if any(isinstance(i, dict) and (i.get("purpose") or "") == "maskable any" for i in icons):
        problems.append("icon purpose 'maskable any' — use separate icons for maskable and any")
    display = manifest.get("display") or "browser"
    if display not in _INSTALL_DISPLAYS:
        problems.append(f"'display' is '{display}' — installable apps need standalone, fullscreen or minimal-ui")
    start_url = manifest.get("start_url")
    if not start_url:
        problems.append("missing 'start_url'")
    else:
        scope = manifest.get("scope") or urljoin(manifest_url, "./")
        abs_start = urljoin(manifest_url, start_url)
        abs_scope = urljoin(manifest_url, scope)
        if not abs_start.startswith(abs_scope):
            problems.append(f"start_url '{start_url}' is outside the manifest scope '{scope}'")
    if not manifest.get("theme_color"):
        problems.append("missing 'theme_color' (title bar / splash colour)")
    if not manifest.get("background_color"):
        problems.append("missing 'background_color' (splash screen background)")
    return problems


async def _manifest_section(page) -> dict:
    href = await page.evaluate(
        "() => { const l = document.querySelector('link[rel~=\"manifest\"]'); return l ? l.href : null; }")
    if not href:
        return {"found": False, "url": None, "problems": ["no <link rel=\"manifest\"> on the page"]}
    try:
        resp = await real_page(page).context.request.get(href, timeout=10000)
        text = await resp.text()
        status = resp.status
    except Exception as e:
        return {"found": False, "url": href, "problems": [f"manifest fetch failed: {e}"]}
    if status >= 400:
        return {"found": False, "url": href, "status": status,
                "problems": [f"manifest returns HTTP {status}"]}
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as e:
        return {"found": True, "url": href, "status": status, "valid_json": False,
                "problems": [f"manifest is not valid JSON: {e}"]}
    icons = [{"src": i.get("src"), "sizes": i.get("sizes"), "type": i.get("type"),
              "purpose": i.get("purpose")} for i in (manifest.get("icons") or []) if isinstance(i, dict)]
    return {
        "found": True, "url": href, "status": status, "valid_json": True,
        "name": manifest.get("name"), "short_name": manifest.get("short_name"),
        "start_url": manifest.get("start_url"), "scope": manifest.get("scope"),
        "display": manifest.get("display"), "theme_color": manifest.get("theme_color"),
        "background_color": manifest.get("background_color"), "icons": icons,
        "problems": validate_manifest(manifest, href),
    }


async def _sw_section(page) -> dict:
    try:
        return await page.evaluate("""async () => {
            if (!('serviceWorker' in navigator)) return { supported: false, registered: false };
            const regs = await navigator.serviceWorker.getRegistrations();
            const r = regs[0];
            const w = r ? (r.active || r.waiting || r.installing) : null;
            return {
                supported: true,
                registered: regs.length > 0,
                count: regs.length,
                scope: r ? r.scope : null,
                script_url: w ? w.scriptURL : null,
                state: w ? w.state : null,
                controlling: !!navigator.serviceWorker.controller,
            };
        }""")
    except Exception as e:
        return {"supported": None, "registered": False, "error": str(e)[:200]}


async def _installability(page) -> dict:
    """CDP Page.getInstallabilityErrors — Chrome's own verdict, when exposed."""
    try:
        owner = real_page(page)
        cdp = await owner.context.new_cdp_session(owner)
        try:
            data = await cdp.send("Page.getInstallabilityErrors")
        finally:
            try:
                await cdp.detach()
            except Exception:
                pass
        # 'in-incognito' describes Periscope's own isolated automation context,
        # not the site — it is never a finding.
        errors = [e.get("errorId") for e in (data or {}).get("installabilityErrors", [])
                  if e.get("errorId") != "in-incognito"]
        return {"source": "cdp", "errors": errors, "installable": not errors}
    except Exception as e:
        return {"source": "unavailable", "errors": None, "installable": None,
                "note": f"Page.getInstallabilityErrors not available: {str(e)[:120]}"}


@tool("check_pwa")
async def handle_check_pwa(args: dict) -> dict:
        session_id = args.get("session_id")
        url = args.get("url")
        if not session_id and not url:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        cleanup = None
        bip = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        else:
            t = await get_tester()
            project = args.get("project")
            own_ctx = None
            if project:
                context = await t.get_context(project)
            else:
                own_ctx = await t.new_ephemeral_context()
                context = own_ctx
            page = await context.new_page()
            await page.add_init_script(f"({_BIP_INIT})()")
            from nav import resilient_goto
            try:
                await resilient_goto(page, url)
            except Exception as e:
                await page.close()
                if own_ctx:
                    await own_ctx.close()
                return {"success": False, "url": url,
                        "error": f"check_pwa could not load the page: {str(e).splitlines()[0][:200]}"}

            async def cleanup():
                await page.close()
                if own_ctx:
                    await own_ctx.close()

        try:
            # Give a freshly loaded page a beat to register its worker.
            try:
                await page.wait_for_function(
                    "() => !('serviceWorker' in navigator) || navigator.serviceWorker.getRegistrations().then(r => r.length > 0)",
                    timeout=3000)
            except Exception:
                pass
            manifest = await _manifest_section(page)
            sw = await _sw_section(page)
            install = await _installability(page)
            if not session_id:
                try:
                    await asyncio.sleep(0.5)
                    bip = bool(await page.evaluate("() => window.__periscope_bip === true"))
                except Exception:
                    bip = None

            issues = []
            # A site with neither a manifest nor a service worker isn't trying
            # to be a PWA: say so once, as information — not as three defects.
            is_pwa = bool(manifest["found"] or sw.get("registered"))
            if not is_pwa:
                issues.append({"type": "pwa", "severity": "info",
                               "message": "Not a PWA: no web app manifest and no service worker "
                                          "(nothing to fix unless the site should be installable)"})
            else:
                if not manifest["found"]:
                    issues.append({"type": "pwa", "severity": "error",
                                   "message": "No web app manifest — the page cannot be installed",
                                   "details": manifest.get("problems", [])})
                elif manifest.get("problems"):
                    issues.append({"type": "pwa", "severity": "warning",
                                   "message": f"{len(manifest['problems'])} manifest problem(s) affect installability",
                                   "details": manifest["problems"][:8]})
                if not sw.get("registered"):
                    issues.append({"type": "pwa", "severity": "warning",
                                   "message": "No service worker registered — no offline support (Chrome 108+ "
                                              "can still install the app from the manifest alone; other "
                                              "browsers and richer install UI still expect one)"})
                elif sw.get("state") and sw["state"] != "activated":
                    issues.append({"type": "pwa", "severity": "info",
                                   "message": f"Service worker is '{sw['state']}', not activated yet"})
                if install.get("errors"):
                    issues.append({"type": "pwa", "severity": "warning",
                                   "message": f"Chrome reports {len(install['errors'])} installability error(s)",
                                   "details": install["errors"][:8]})

            return {
                "success": True,
                "url": real_page(page).url,
                "is_pwa": is_pwa,
                "manifest": manifest,
                "service_worker": sw,
                "installability": install,
                "before_install_prompt_fired": bip,
                "issues": issues,
                "issue_count": len(issues),
            }
        finally:
            if cleanup:
                await cleanup()
