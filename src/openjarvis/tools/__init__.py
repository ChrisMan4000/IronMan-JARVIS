# Modified for the IronMan J.A.R.V.I.S. project (see NOTICE). Original: https://github.com/open-jarvis/OpenJarvis (Apache-2.0)
"""Tools primitive — tool system with ABC interface and built-in tools."""

from __future__ import annotations

import importlib
import logging

from openjarvis.tools._stubs import BaseTool, ToolExecutor, ToolSpec

logger = logging.getLogger(__name__)

# Import built-in tools to trigger @ToolRegistry.register() decorators.
# Each is wrapped in try/except so the package loads even before the
# individual tool modules are created or if optional dependencies are missing.
_BUILTIN_TOOL_MODULES = (
    "calculator",
    "think",
    "retrieval",
    "llm_tool",
    "file_read",
    "web_search",
    "weather",
    "fx_macro",
    "code_interpreter",
    "code_interpreter_docker",
    "repl",
    "storage_tools",
    "mcp_adapter",
    "channel_tools",
    "http_request",
    "docker_shell_exec",
    "shell_exec",
    "memory_manage",
    "user_profile_manage",
    "skill_manage",
    "file_write",
    "apply_patch",
    "git_tool",
    "db_query",
    "pdf_tool",
    "image_tool",
    "audio_tool",
    "knowledge_tools",
    "text_to_speech",
    "digest_collect",
    "scan_chunks",
    "knowledge_sql",
    "apple_calendar",
    "knowledge_search",
    "browser",
    "browser_axtree",
    "proactive_tools",
    # IronMan J.A.R.V.I.S. tools
    "oracle_search",
    "hue_lights",
    "hue_set",
    "hue_light_list",
    "hue_all_set",
    "rss_news",
    "tado_heating",
    "oxxify_vent",
    "sonos_control",
    "hue_light",
)

for _name in _BUILTIN_TOOL_MODULES:
    try:
        importlib.import_module(f"openjarvis.tools.{_name}")
    except ImportError as _exc:
        logger.debug("Optional tool %s not loaded: %s", _name, _exc)

__all__ = ["BaseTool", "ToolExecutor", "ToolSpec"]
