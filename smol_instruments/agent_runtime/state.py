"""
Agent state tracking with context injection for low-power models.

FIXED: Added max_steps configuration and summary injection.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Set
from datetime import datetime


@dataclass
class StepRecord:
    """Record of a single agent step."""
    step_num: int
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    error: bool
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_num,
            "tool": self.tool_name,
            "args": self.arguments,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AgentState:
    """
    Track agent progress across steps.
    
    FIXED: Added max_steps configuration and summary() injection method.
    """
    task: str
    max_steps: int = 25  # FIXED: Made configurable
    steps: List[StepRecord] = field(default_factory=list)
    patches_proposed: List[str] = field(default_factory=list)
    patches_applied: List[str] = field(default_factory=list)
    patches_rejected: List[str] = field(default_factory=list)
    files_read: Set[str] = field(default_factory=set)
    files_modified: Set[str] = field(default_factory=set)
    commands_run: List[str] = field(default_factory=list)
    
    @property
    def steps_remaining(self) -> int:
        """Calculate remaining steps."""
        return self.max_steps - len(self.steps)
    
    @property
    def max_steps_reached(self) -> bool:
        """Check if max steps reached."""
        return len(self.steps) >= self.max_steps
    
    def add_step(self, tool_name: str, arguments: Dict[str, Any], result: Any):
        """Record a tool execution step."""
        step = StepRecord(
            step_num=len(self.steps) + 1,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            error=isinstance(result, dict) and "error" in result
        )
        self.steps.append(step)
        
        # Track specific operations
        if tool_name == "read_file" or tool_name == "read_file_snippet":
            self.files_read.add(arguments.get("path", ""))
        elif tool_name == "propose_patch_unified" and isinstance(result, dict):
            patch_id = result.get("patch_id", "")
            if patch_id:
                self.patches_proposed.append(patch_id)
        elif tool_name == "apply_patch" and isinstance(result, dict):
            if result.get("ok"):
                patch_id = result.get("patch_id", "")
                self.patches_applied.append(patch_id)
                files = result.get("files_changed", [])
                self.files_modified.update(files)
        elif tool_name in ("run_cmd", "run_tests"):
            self.commands_run.append(arguments.get("cmd", arguments.get("test_cmd", "")))
    
    def get_last_steps(self, n: int = 3) -> List[StepRecord]:
        """Get the last N steps."""
        return self.steps[-n:] if len(self.steps) > n else self.steps
    
    def summary(self, compact: bool = True) -> str:
        """
        Provide concise summary for the model.
        
        FIXED: This should be injected into prompts to give context.
        
        Args:
            compact: If True, ultra-minimal format for small models
        """
        if compact:
            # Ultra-minimal for low-power models
            summary_lines = [
                f"Steps: {len(self.steps)}/{self.max_steps}",
            ]
            
            # Show last 2 steps only
            if self.steps:
                last_steps = self.get_last_steps(2)
                for step in last_steps:
                    status = "❌" if step.error else "✓"
                    summary_lines.append(f"{status} {step.tool_name}")
            
            return " | ".join(summary_lines)
        else:
            # More detailed for larger models
            summary_lines = [
                f"Task: {self.task}",
                f"Steps taken: {len(self.steps)}/{self.max_steps} ({self.steps_remaining} remaining)",
            ]
            
            if self.files_read:
                summary_lines.append(f"Files read: {len(self.files_read)}")
            
            if self.patches_proposed:
                summary_lines.append(f"Patches proposed: {len(self.patches_proposed)}")
            
            if self.patches_applied:
                summary_lines.append(f"Patches applied: {len(self.patches_applied)}")
            
            # Show last few steps
            if self.steps:
                last_steps = self.get_last_steps(3)
                summary_lines.append("\nRecent steps:")
                for step in last_steps:
                    status = "❌" if step.error else "✓"
                    summary_lines.append(f"  {status} {step.tool_name}")
            
            return "\n".join(summary_lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export full state as dict for logging."""
        return {
            "task": self.task,
            "max_steps": self.max_steps,
            "steps": [s.to_dict() for s in self.steps],
            "patches_proposed": self.patches_proposed,
            "patches_applied": self.patches_applied,
            "patches_rejected": self.patches_rejected,
            "files_read": list(self.files_read),
            "files_modified": list(self.files_modified),
            "commands_run": self.commands_run,
            "max_steps_reached": self.max_steps_reached,
        }
