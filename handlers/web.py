"""Web search and fetch tools."""
import asyncio
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import config
import interactions
from crawler import Crawler
from runtime import auth_handler, get_tester, project_manager, session_manager
from sessions import real_page

from .registry import tool

_STRIP_TAGS = ["script", "style", "img", "svg", "picture", "video", "audio",
               "canvas", "iframe", "source", "noscript"]


def _bs4_flat(soup) -> str:
    """Legacy flat-text extraction: strip media/script, dump all visible text.
    Keeps boilerplate (nav/footer) — used only when readable=False or as a
    never-empty fallback when readability extraction yields nothing."""
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _tidy_markdown(md: str) -> str:
    """Clean trafilatura markdown: drop per-line indent, empty headings, and
    collapse blank-line runs (artifacts from widget/table wrappers)."""
    md = re.sub(r"(?m)^[ \t]+", "", md)
    md = re.sub(r"(?m)^#+\s*$\n?", "", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def extract_readable(html: str, url: str, fmt: str = "markdown") -> tuple[str, str]:
    """Readable extraction of `html` → (content, method) for fmt=markdown|text.
    Falls back to a flat bs4 text dump so it is never empty. Shared by web_fetch
    and crawl_project's save-markdown pass."""
    from bs4 import BeautifulSoup
    import trafilatura
    out_fmt = "markdown" if fmt == "markdown" else "txt"
    extracted = trafilatura.extract(
        html, url=url, output_format=out_fmt, include_links=True,
        include_tables=True, include_formatting=(fmt == "markdown"), favor_recall=True)
    if extracted:
        return (_tidy_markdown(extracted) if fmt == "markdown" else extracted.strip()), "trafilatura"
    return _bs4_flat(BeautifulSoup(html, "html.parser")), "bs4-fallback"


@tool("web_search")
async def handle_web_search(args: dict) -> dict:
        from ddgs import DDGS
        query = args["query"]
        max_results = int(args.get("max_results", 10))
        # DDGS().text is synchronous network I/O — run it off the event loop
        # so a slow search doesn't stall every other tool call.
        results = await asyncio.to_thread(lambda: list(DDGS().text(query, max_results=max_results)))
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
        return {
            "query": query,
            "results": formatted,
            "count": len(formatted),
        }


@tool("web_fetch")
async def handle_web_fetch(args: dict) -> dict:
        from bs4 import BeautifulSoup
        url = args["url"]
        max_length = int(args.get("max_length", 50000))
        verify_ssl = args.get("verify_ssl", True)
        # Output: markdown (default, readable) | text | html. raw_html=true is a
        # back-compat alias for html.
        fmt = (args.get("format") or ("html" if args.get("raw_html") else "markdown")).lower()
        if fmt not in ("markdown", "text", "html"):
            return {"success": False, "url": url,
                    "error": f"Unknown format '{fmt}' — use markdown|text|html"}
        readable = args.get("readable", True)
        render = args.get("render", False)
        project = args.get("project")
        contains = args.get("contains")
        contains_mode = (args.get("contains_mode") or "any").lower()

        # --- get the HTML: rendered (JS run in headless Chromium) or static ---
        content_type = "text/html"
        if render:
            # The one reading path host WebFetch can't match: run all JS first,
            # and (with project) read pages behind a login.
            t = await get_tester()
            try:
                page, cleanup = await t.open_page(project, url)
            except Exception as e:
                return {"success": False, "url": url, "rendered": True,
                        "error": f"Headless render failed to load the page: {e}"}
            try:
                html = await page.content()
                final_url = real_page(page).url
                title = await page.title()
            finally:
                await cleanup()
        else:
            import httpx
            headers = {"User-Agent": "Mozilla/5.0 (compatible; PeriscopeBot/1.0; "
                                     "+https://github.com/segentic-lab/periscope-mcp)"}
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=30.0,
                                             verify=verify_ssl, headers=headers) as client:
                    response = await client.get(url)
                    response.raise_for_status()
            except httpx.HTTPStatusError as e:
                return {"success": False, "url": url, "status_code": e.response.status_code,
                        "error": f"HTTP {e.response.status_code} for {url}"}
            except Exception as e:
                return {"success": False, "url": url, "error": str(e)}
            content_type = response.headers.get("content-type", "")
            # Don't decode-and-soup binary responses (PDFs, images) into garbage.
            main_type = content_type.split(";")[0].strip().lower()
            if main_type and not (main_type.startswith("text/")
                                  or main_type in ("application/json", "application/xml",
                                                   "application/xhtml+xml", "application/javascript")
                                  or main_type.endswith("+json") or main_type.endswith("+xml")):
                return {
                    "success": False, "url": str(response.url),
                    "error": f"Unsupported content type '{content_type}' — web_fetch handles text only",
                    "content_type": content_type, "content_length": len(response.content),
                }
            html = response.text
            final_url = str(response.url)
            title = ""

        soup = BeautifulSoup(html, "html.parser")
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

        # --- extract to the requested shape ---
        if fmt == "html":
            content, extraction = html, "raw-html"
        elif readable:
            content, extraction = extract_readable(html, final_url, fmt)
        else:
            content, extraction = _bs4_flat(soup), "bs4-flat"

        result = {
            "url": final_url, "title": title, "format": fmt, "readable": readable,
            "rendered": bool(render), "content_type": content_type, "extraction": extraction,
        }

        # --- conditional fetch: only surface content if it contains the term(s) ---
        if contains is not None:
            terms = [t for t in (contains if isinstance(contains, list) else [contains]) if t]
            # Match against the FULL visible text, NOT the readable-extracted
            # output — otherwise a term living in stripped nav/footer/boilerplate
            # (or, in reading mode, anything trafilatura dropped) would be a false
            # miss. The output stays readable; only the haystack is the whole page.
            hay = _bs4_flat(BeautifulSoup(html, "html.parser")).lower()
            present = [t for t in terms if t.lower() in hay]
            matched = (len(present) == len(terms)) if contains_mode == "all" else bool(present)
            result.update({"matched": matched, "matched_terms": present,
                           "searched_terms": terms, "match_scope": "full_text"})
            if not matched:
                result.update({
                    "content_omitted": True, "length": len(content),
                    "note": f"Page does not contain the required term(s) ({contains_mode}) — "
                            "content omitted to save tokens.",
                })
                return result

        # --- optional save of the FULL artifact (before truncation) ---
        save = args.get("save") or args.get("save_path")
        if save:
            ext = {"markdown": "md", "text": "txt", "html": "html"}[fmt]
            path = args.get("save_path")
            if not path or path is True:
                fetch_dir = os.path.join(config.DATA_DIR, "fetches")
                os.makedirs(fetch_dir, exist_ok=True)
                host = (urlparse(final_url).netloc or "page").replace(":", "_")
                path = os.path.join(fetch_dir, f"{host}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")
            else:
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            result["saved_path"] = path
            result["saved_length"] = len(content)

        full_len = len(content)
        result["content"] = content[:max_length]
        result["length"] = min(full_len, max_length)
        if full_len > max_length:
            result["truncated"] = True
        return result
