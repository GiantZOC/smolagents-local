"""
Gate-aware orchestrator for preventing premature finalization.

Hybrid implementation that tries Path A (memory injection) first,
with automatic fallback to Path B (physical blocking) if injection fails.
"""

from typing import Dict, Any, List, Set, Optional
from dataclasses import dataclass
from agent_runtime.state import AgentState
from agent_runtime.tool_registry import (
    DISCOVERY_TOOLS,
    SEARCH_TOOLS,
    READ_TOOLS,
    PATCH_TOOLS,
    VERIFY_TOOLS,
    PROGRESS_TOOLS,
)


@dataclass
class GateStatus:
    """Track status of all gates."""
    understanding: bool = False
    change: bool = False
    verification: bool = False
    readiness: bool = False  # Composite: all others passed
    
    # Supporting evidence
    files_read: int = 0
    search_used: bool = False
    patches_proposed: int = 0
    verify_tool_used: bool = False
    no_progress_yet: bool = True
    steps_taken: int = 0
    
    def all_passed(self) -> bool:
        """Check if all core gates satisfied."""
        return all([
            self.understanding,
            self.change,
            self.verification,
        ])
    
    def to_dict(self) -> Dict[str, Any]:
        """Export for logging/tracing."""
        return {
            "understanding": self.understanding,
            "change": self.change,
            "verification": self.verification,
            "readiness": self.readiness,
            "all_passed": self.all_passed(),
            "evidence": {
                "files_read": self.files_read,
                "search_used": self.search_used,
                "patches_proposed": self.patches_proposed,
                "verify_tool_used": self.verify_tool_used,
                "no_progress_yet": self.no_progress_yet,
                "steps_taken": self.steps_taken,
            }
        }


class GateTracker:
    """
    Track gate status and generate warnings.
    
    Features:
    - Understanding gate: (search OR patch) AND read (less strict)
    - Verification gate: tool usage only, not commands_run dependency
    - Escalating warnings for persistent no-progress
    - Designed to persist on agent
    """
    
    # Hard escalation threshold
    MAX_NO_PROGRESS_STEPS = 6
    
    def __init__(self, state: AgentState):
        self.state = state
        self.warnings_issued: List[str] = []
        self.last_warning_step: int = 0
        self.injection_working: Optional[bool] = None
    
    def evaluate_gates(self) -> GateStatus:
        """
        Evaluate all gates based on current state.
        """
        status = GateStatus()
        status.steps_taken = len(self.state.steps)
        
        # Gather tool usage evidence
        tools_used = [s.tool_name for s in self.state.steps]
        tools_set = set(tools_used)
        
        did_search = bool(SEARCH_TOOLS & tools_set)
        did_read = bool(READ_TOOLS & tools_set)
        did_patch = bool(PATCH_TOOLS & tools_set)
        did_verify = bool(VERIFY_TOOLS & tools_set)
        
        # Progress detection
        progress_used = PROGRESS_TOOLS & tools_set
        no_progress_yet = (
            len(progress_used) == 0 and 
            len(tools_used) >= 2
        )
        
        # Update status evidence
        status.files_read = len(self.state.files_read)
        status.search_used = did_search
        status.patches_proposed = len(self.state.patches_proposed)
        status.verify_tool_used = did_verify
        status.no_progress_yet = no_progress_yet
        
        # Gate 1: Understanding (search OR patch, less strict)
        # Rationale: "apply this patch" tasks don't need search
        status.understanding = (
            did_read and 
            (did_search or did_patch) and
            status.files_read >= 1
        )
        
        # Gate 2: Change (patch proposed)
        status.change = did_patch and status.patches_proposed > 0
        
        # Gate 3: Verification (tool usage only)
        # Don't depend on commands_run which may not be wired
        status.verification = did_verify
        
        # Gate 4: Readiness (composite)
        status.readiness = (
            status.understanding and 
            status.change and 
            status.verification
        )
        
        return status
    
    def get_warning_message(self, status: GateStatus) -> Optional[str]:
        """
        Generate warning message if gates not satisfied.
        
        Features:
        - Escalating warnings
        - Includes next concrete action
        - Task-specific suggestions
        """
        # CRITICAL: Hard escalation if stuck in no-progress
        if status.no_progress_yet:
            if status.steps_taken >= self.MAX_NO_PROGRESS_STEPS:
                # Hard escalation
                warning_key = "no_progress_escalated"
                if warning_key not in self.warnings_issued:
                    self.warnings_issued.append(warning_key)
                    self.last_warning_step = status.steps_taken
                    
                    # Extract task hint from state if available
                    task_hint = ""
                    if hasattr(self.state, 'task') and self.state.task:
                        # Suggest a search pattern based on task
                        task_lower = self.state.task.lower()
                        if "tracing" in task_lower or "phoenix" in task_lower:
                            task_hint = "\nSuggested: rg_search(pattern='phoenix|trace|span')"
                        elif "test" in task_lower:
                            task_hint = "\nSuggested: rg_search(pattern='test.*')"
                        elif "bug" in task_lower or "error" in task_lower:
                            task_hint = "\nSuggested: rg_search(pattern='error|exception')"
                    
                    return (
                        f"🚫 CRITICAL (step {status.steps_taken}): You are stuck.\n"
                        "\n"
                        "You MUST use a progress tool NOW:\n"
                        "  • rg_search - search for relevant code\n"
                        "  • read_file - examine a specific file\n"
                        "  • propose_patch_unified - create a patch\n"
                        "  • run_tests - verify changes\n"
                        f"{task_hint}\n"
                        "\n"
                        "DO NOT call discovery tools again (repo_info, list_files)."
                    )
            
            # Initial warning
            warning_key = "no_progress"
            if warning_key not in self.warnings_issued:
                self.warnings_issued.append(warning_key)
                self.last_warning_step = status.steps_taken
                return (
                    "⚠ WARNING: You have not made progress yet.\n"
                    "\n"
                    "Next, you must:\n"
                    "1. Use 'rg_search' to find relevant code\n"
                    "2. Use 'read_file' to examine files\n"
                    "3. Use 'propose_patch_unified' to create changes\n"
                    "4. Use 'run_tests' or 'run_cmd' to verify\n"
                    "\n"
                    "Do not finalize yet."
                )
        
        # Progressive warnings for incomplete gates (after 5 steps)
        if status.steps_taken >= 5 and not status.all_passed():
            # Throttle: warn every 3 steps
            if status.steps_taken - self.last_warning_step < 3:
                return None
            
            missing = []
            
            if not status.understanding:
                if not status.search_used and status.patches_proposed == 0:
                    missing.append("search code OR start patch (use 'rg_search' or 'propose_patch_unified')")
                if status.files_read == 0:
                    missing.append("read files (use 'read_file')")
            
            if not status.change:
                missing.append("propose patch (use 'propose_patch_unified')")
            
            if not status.verification:
                missing.append("verify (use 'run_tests' or 'run_cmd')")
            
            if missing:
                warning_key = f"step_{status.steps_taken // 3}"
                if warning_key not in self.warnings_issued:
                    self.warnings_issued.append(warning_key)
                    self.last_warning_step = status.steps_taken
                    
                    return (
                        f"⚠ WARNING (step {status.steps_taken}): Task incomplete.\n"
                        "\n"
                        "Still need to:\n" +
                        "\n".join(f"  - {item}" for item in missing) +
                        "\n\n"
                        "Continue working. DO NOT finalize."
                    )
        
        # All gates passed
        return None


def try_inject_warning(agent, warning_message: str) -> bool:
    """
    Try to inject warning into agent memory (Path A).
    Returns True if injection successful, False otherwise.
    """
    try:
        # Strategy 1: Direct memory injection
        if hasattr(agent, 'memory') and isinstance(agent.memory, list):
            agent.memory.append({
                "role": "system",
                "content": warning_message
            })
            return True
        
        # Strategy 2: Try logs if memory not available
        elif hasattr(agent, 'logs') and isinstance(agent.logs, list):
            agent.logs.append({
                "role": "system",
                "content": warning_message
            })
            return True
        
        return False
        
    except Exception as e:
        # Log the error but don't crash
        print(f"Warning injection failed: {e}")
        return False


def gate_aware_step_callback(step, agent):
    """
    Step callback that injects gate warnings (Path A) or logs them (fallback).
    
    Args:
        step: MemoryStep from smolagents
        agent: MultiStepAgent instance
    """
    # Get or create persisted tracker
    if not hasattr(agent, '_gate_tracker'):
        state = getattr(agent, '_smol_state', None)
        if not state:
            return
        agent._gate_tracker = GateTracker(state)
    
    tracker = agent._gate_tracker
    status = tracker.evaluate_gates()
    
    # Get warning
    warning = tracker.get_warning_message(status)
    if not warning:
        return
    
    # Try injection (Path A)
    injected = try_inject_warning(agent, warning)
    
    # Console output (always)
    print(f"\n{'='*70}")
    if injected:
        print("✓ GATE WARNING INJECTED (model will see this):")
        tracker.injection_working = True
    else:
        print("⚠ GATE WARNING (NOT INJECTED - model cannot see):")
        tracker.injection_working = False
    print(f"{'='*70}")
    print(warning)
    print(f"{'='*70}\n")
    
    if not injected:
        print("⚠ Path A will not work - injection failed.")
        print("  Recommendation: Implement Path B (blocking).")
        print()


def get_gate_status(agent) -> Optional[GateStatus]:
    """Get current gate status for an agent."""
    if not hasattr(agent, '_gate_tracker'):
        return None
    return agent._gate_tracker.evaluate_gates()


def is_injection_working(agent) -> bool:
    """Check if memory injection is working for this agent."""
    tracker = getattr(agent, '_gate_tracker', None)
    if tracker and tracker.injection_working is not None:
        return tracker.injection_working
    return False


# Path B: Physical Blocking (Fallback)
# This would be implemented if injection consistently fails

class GatedToolCallingAgent:
    """
    Fallback implementation for Path B (physical blocking).
    
    This would subclass the actual ToolCallingAgent and override
    tool execution to block finalization when gates aren't passed.
    
    TODO: Implement once smolagents source is studied.
    """
    
    def __init__(self, base_agent, state):
        """
        Wrapper around base agent that enforces gates.
        
        Args:
            base_agent: The original ToolCallingAgent
            state: AgentState for gate tracking
        """
        self.base_agent = base_agent
        self.state = state
        self.gate_tracker = GateTracker(state)
        
        # Copy relevant attributes
        self.tools = base_agent.tools
        self.model = base_agent.model
        
    def run(self, task: str):
        """
        Override run method to enforce gates.
        """
        # Set task in state
        self.state.task = task
        
        # Start the agent loop
        return self._run_with_gates(task)
    
    def _run_with_gates(self, task: str):
        """
        Agent loop with gate enforcement.
        
        This is a simplified version - actual implementation would need
        to integrate with smolagents' native loop.
        """
        # TODO: Implement actual loop with gate checking
        # For now, just call the base agent
        return self.base_agent.run(task)
    
    def _check_gates_before_tool(self, tool_name: str):
        """
        Check if tool execution should be blocked.
        
        Returns True if tool should be blocked, False otherwise.
        """
        # Identify finalization tools
        # These are tools that would end the task without proper completion
        FINALIZATION_TOOLS = {
            # Add actual finalization tool names here
            # Example: "final_answer", "complete_task", etc.
        }
        
        if tool_name in FINALIZATION_TOOLS:
            status = self.gate_tracker.evaluate_gates()
            if not status.all_passed():
                # Block this tool execution
                return True
        
        return False
    
    def _get_blocking_response(self, status: GateStatus) -> dict:
        """
        Generate response when tool is blocked.
        """
        missing = []
        
        if not status.understanding:
            missing.append("understand the problem (search and read code)")
        if not status.change:
            missing.append("propose changes (create patches)")
        if not status.verification:
            missing.append("verify changes (run tests)")
        
        return {
            "error": "GATE_BLOCK",
            "message": f"Cannot finalize yet. Still need to: {', '.join(missing)}",
            "required_actions": missing,
            "gate_status": status.to_dict()
        }