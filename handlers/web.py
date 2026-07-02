"""Web search and fetch tools."""
import asyncio
import json
import os
import time

import config
import interactions
from crawler import Crawler
from runtime import auth_handler, get_tester, project_manager, session_manager
from sessions import real_page

from .registry import tool


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
        import httpx
        from bs4 import BeautifulSoup
        url = args["url"]
        max_length = int(args.get("max_length", 50000))
        raw_html = args.get("raw_html", False)
        verify_ssl = args.get("verify_ssl", True)
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, verify=verify_ssl) as client:
            response = await client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        # Don't decode-and-soup binary responses (PDFs, images) into garbage
        main_type = content_type.split(";")[0].strip().lower()
        if main_type and not (main_type.startswith("text/")
                              or main_type in ("application/json", "application/xml",
                                               "application/xhtml+xml", "application/javascript")
                              or main_type.endswith("+json") or main_type.endswith("+xml")):
            return {
                "success": False,
                "url": str(response.url),
                "error": f"Unsupported content type '{content_type}' — web_fetch handles text content only",
                "content_type": content_type,
                "content_length": len(response.content),
            }
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if raw_html:
            content = html[:max_length]
        else:
            for tag in soup(["script", "style", "img", "svg", "picture", "video", "audio", "canvas", "iframe", "source", "noscript"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)[:max_length]
        return {
            "url": str(response.url),
            "title": title,
            "content": content,
            "length": len(content),
            "content_type": content_type,
        }
