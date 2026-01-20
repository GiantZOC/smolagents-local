"""
Canonical tool name registry.

CRITICAL: Use these constants everywhere. No hardcoded strings.
"""

from typing import Set, FrozenSet

# Discovery tools (do not count as progress)
DISCOVERY_TOOLS: FrozenSet[str] = frozenset({
    "repo_info",
    "list_files",
    "git_status",
    "git_diff",
    "git_log",
})

# Progress tools (satisfy gates)
SEARCH_TOOLS: FrozenSet[str] = frozenset({
    "rg_search",
})

READ_TOOLS: FrozenSet[str] = frozenset({
    "read_file",
    "read_file_snippet",
})

PATCH_TOOLS: FrozenSet[str] = frozenset({
    "propose_patch_unified",
    "propose_patch",
})

VERIFY_TOOLS: FrozenSet[str] = frozenset({
    "run_tests",
    "run_cmd",
})

OTHER_TOOLS: FrozenSet[str] = frozenset({
    "show_patch",
    "apply_patch",
})

# Aggregate sets
PROGRESS_TOOLS: FrozenSet[str] = SEARCH_TOOLS | READ_TOOLS | PATCH_TOOLS | VERIFY_TOOLS
ALL_TOOLS: FrozenSet[str] = DISCOVERY_TOOLS | PROGRESS_TOOLS | OTHER_TOOLS


def validate_tool_name(name: str) -> bool:
    """Check if tool name is registered."""
    return name in ALL_TOOLS


def is_progress_tool(name: str) -> bool:
    """Check if tool counts as progress."""
    return name in PROGRESS_TOOLS


def get_tool_list_string() -> str:
    """Get comma-separated tool list for prompts."""
    return ", ".join(sorted(ALL_TOOLS))


def get_discovery_tools_string() -> str:
    """Get comma-separated discovery tool list."""
    return ", ".join(sorted(DISCOVERY_TOOLS))


def get_progress_tools_string() -> str:
    """Get comma-separated progress tool list."""
    return ", ".join(sorted(PROGRESS_TOOLS))