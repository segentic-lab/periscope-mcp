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
        max_results = args.get("max_results", 10)
        results = DDGS().text(query, max_results=max_results)
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
        max_length = args.get("max_length", 50000)
        raw_html = args.get("raw_html", False)
        verify_ssl = args.get("verify_ssl", True)
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, verify=verify_ssl) as client:
            response = await client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "")
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
