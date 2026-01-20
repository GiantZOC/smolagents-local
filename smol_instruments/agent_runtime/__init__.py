"""Agent runtime for smol_instruments - ReAct implementation for low-power LLMs."""

__version__ = "1.0.0"

# Expose key modules for easy importing
from .orchestrator import (
    GateTracker,
    GateStatus,
    gate_aware_step_callback,
    get_gate_status,
    try_inject_warning
)

from .tool_registry import (
    validate_tool_name,
    is_progress_tool,
    get_tool_list_string,
    get_discovery_tools_string,
    get_progress_tools_string,
    DISCOVERY_TOOLS,
    SEARCH_TOOLS,
    READ_TOOLS,
    PATCH_TOOLS,
    VERIFY_TOOLS,
    PROGRESS_TOOLS,
    ALL_TOOLS
)

# Re-export existing functionality
from .state import AgentState
from .config import Config
from .approval import ApprovalStore, set_approval_store
from .instrumentation import wrap_tools_with_instrumentation, setup_phoenix_telemetry
from .run import build_agent, run_task, interactive_cli
