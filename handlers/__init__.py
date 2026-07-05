"""Tool handlers, grouped by category. Importing the submodules registers them."""
from . import advanced, agent_speed, analysis, auth, discovery, interactive, projects, report, session_tools, static_testing, system, web  # noqa: F401 — populates the registry
from .registry import HANDLERS

__all__ = ["HANDLERS"]
