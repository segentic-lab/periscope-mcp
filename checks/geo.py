"""GEO (Generative Engine Optimization) / agentic-search checks.

Covers what AI crawlers, answer engines, and in-browser agents need:
- robots.txt access for AI crawlers (GPTBot, ClaudeBot, PerplexityBot, ...)
- llms.txt presence and basic format compliance
- WebMCP integration (document.modelContext tools + declarative form annotations)
- JSON-LD presence (the structured data answer engines consume)

Shared robots.txt helpers live here and are reused by the SEO check.
"""
from urllib.parse import urlparse
from playwright.async_api import Page

# Crawlers used by AI products for training/search/answers.
AI_CRAWLERS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "ClaudeBot", "Claude-Web", "anthropic-ai",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot-Extended",
    "CCBot", "Bytespider", "Amazonbot", "meta-externalagent",
    "cohere-ai", "DuckAssistBot",
]

# Classic search engine crawlers (used by the SEO check).
SEARCH_CRAWLERS = ["Googlebot", "Bingbot", "DuckDuckBot", "Slurp", "Baiduspider", "YandexBot"]

# (origin, path) -> body text or None. Robots/llms files change rarely;
# one fetch per origin per server process is enough.
_origin_file_cache: dict = {}


def _owner(page):
    """Frame (iframe session) -> owning Page."""
    return page if hasattr(page, "context") else page.page


async def fetch_origin_file(page, path: str):
    """Fetch text of an origin-root file (e.g. /robots.txt), cached per origin.

    Returns (text_or_None, origin_or_None). origin is None for non-http pages
    (file://, about:), meaning the check doesn't apply.
    """
    p = _owner(page)
    parts = urlparse(p.url)
    if parts.scheme not in ("http", "https"):
        return None, None
    origin = f"{parts.scheme}://{parts.netloc}"
    key = (origin, path)
    if key not in _origin_file_cache:
        try:
            resp = await p.context.request.get(origin + path, timeout=5000)
            _origin_file_cache[key] = await resp.text() if resp.status == 200 else None
        except Exception:
            _origin_file_cache[key] = None
    return _origin_file_cache[key], origin


def parse_robots(text: str) -> list:
    """Minimal robots.txt parser: [(set_of_agents, disallow_paths, allow_paths)]."""
    groups = []
    agents, disallow, allow = set(), [], []
    has_rules = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            if has_rules:
                groups.append((agents, disallow, allow))
                agents, disallow, allow = set(), [], []
                has_rules = False
            agents.add(val.lower())
        elif key == "disallow":
            disallow.append(val)
            has_rules = True
        elif key == "allow":
            allow.append(val)
            has_rules = True
    if agents:
        groups.append((agents, disallow, allow))
    return groups


def is_blocked(groups: list, user_agent: str) -> bool:
    """True if robots.txt fully blocks this user agent (Disallow: / applies).

    Per-robots.txt semantics, a specific user-agent group overrides the
    wildcard group entirely.
    """
    ua = user_agent.lower()
    matching = [g for g in groups if ua in g[0]]
    if not matching:
        matching = [g for g in groups if "*" in g[0]]
    for _, disallow, allow in matching:
        if any(d == "/" for d in disallow) and not any(a == "/" for a in allow):
            return True
    return False


async def check_geo(page: Page, response=None) -> list[dict]:
    """
    Run GEO / agentic-search checks on a page.
    Returns list of issues found (type: "geo").
    """
    issues = []

    # --- llms.txt: the Markdown site guide LLMs read ------------------------
    llms, origin = await fetch_origin_file(page, "/llms.txt")
    if origin is not None:
        if llms is None:
            issues.append({
                "type": "geo",
                "severity": "info",
                "message": "No llms.txt found — a Markdown site guide at /llms.txt helps "
                           "LLMs understand and cite your content",
            })
        elif not any(line.strip().startswith("# ") for line in llms.splitlines()):
            issues.append({
                "type": "geo",
                "severity": "warning",
                "message": "llms.txt exists but is not compliant: it must be Markdown "
                           "with at least one H1 heading ('# ...')",
            })

    # --- robots.txt: AI crawler access --------------------------------------
    robots, origin = await fetch_origin_file(page, "/robots.txt")
    if origin is not None and robots is not None:
        groups = parse_robots(robots)
        blocked = [ua for ua in AI_CRAWLERS if is_blocked(groups, ua)]
        if blocked:
            issues.append({
                "type": "geo",
                "severity": "warning",
                "message": f"robots.txt blocks {len(blocked)} AI crawlers — content won't "
                           f"appear in those AI search/answer products",
                "details": blocked,
            })

    # --- WebMCP: in-browser agent tools -------------------------------------
    # Site-side signals are always checkable (declarative form annotations);
    # tool enumeration additionally needs a browser exposing modelContext
    # (origin trial / flag), so treat its absence as "not assessable".
    webmcp = await page.evaluate("""() => {
        const mc = (typeof document !== 'undefined' && document.modelContext)
                || (typeof navigator !== 'undefined' && navigator.modelContext) || null;
        const forms = Array.from(document.querySelectorAll('form'));
        const annotated = forms.filter(f => f.hasAttribute('toolname'));
        return {
            apiAvailable: !!mc,
            canEnumerate: !!(mc && mc.getTools),
            formsTotal: forms.length,
            formsAnnotated: annotated.length,
            annotatedProblems: annotated
                .filter(f => !(f.getAttribute('toolname') || '').trim()
                          || !(f.getAttribute('tooldescription') || '').trim())
                .map(f => f.getAttribute('toolname') || '(empty toolname)'),
        };
    }""")

    if webmcp["annotatedProblems"]:
        issues.append({
            "type": "geo",
            "severity": "warning",
            "message": f"{len(webmcp['annotatedProblems'])} declarative WebMCP forms missing "
                       f"toolname/tooldescription — agents can't understand them",
            "details": webmcp["annotatedProblems"][:5],
        })
    if webmcp["formsAnnotated"] and webmcp["formsAnnotated"] < webmcp["formsTotal"]:
        issues.append({
            "type": "geo",
            "severity": "info",
            "message": f"WebMCP form coverage: {webmcp['formsAnnotated']} of "
                       f"{webmcp['formsTotal']} forms have tool annotations",
        })

    if webmcp["canEnumerate"]:
        tools = await page.evaluate("""async () => {
            const mc = document.modelContext || navigator.modelContext;
            try {
                const tools = await mc.getTools();
                return tools.map(t => {
                    let schemaOk = true;
                    try {
                        if (typeof t.inputSchema === 'string') JSON.parse(t.inputSchema);
                    } catch { schemaOk = false; }
                    return { name: t.name || '', description: t.description || '', schemaOk };
                });
            } catch { return null; }
        }""")
        if tools is not None:
            invalid = [
                t["name"] or "(unnamed)" for t in tools
                if not t["schemaOk"] or not t["name"] or len(t["name"]) > 30
                or not t["description"] or len(t["description"]) > 500
            ]
            if invalid:
                issues.append({
                    "type": "geo",
                    "severity": "warning",
                    "message": f"{len(invalid)} WebMCP tools have invalid schemas or "
                               f"out-of-budget names/descriptions (name ≤30, description ≤500)",
                    "details": invalid[:5],
                })
            if not tools and webmcp["formsTotal"] > 0:
                issues.append({
                    "type": "geo",
                    "severity": "info",
                    "message": "WebMCP API is available but no tools are registered",
                })
    elif webmcp["formsTotal"] > 0 and webmcp["formsAnnotated"] == 0:
        issues.append({
            "type": "geo",
            "severity": "info",
            "message": f"No WebMCP integration detected — page has {webmcp['formsTotal']} "
                       f"form(s) that agents could use as tools (optional, progressive enhancement)",
        })

    # --- JSON-LD: the structured data answer engines consume ----------------
    jsonld_count = await page.evaluate(
        """() => document.querySelectorAll('script[type="application/ld+json"]').length"""
    )
    if jsonld_count == 0:
        issues.append({
            "type": "geo",
            "severity": "info",
            "message": "No JSON-LD structured data — AI answer engines rely on it to "
                       "understand and accurately cite content",
        })

    return issues
