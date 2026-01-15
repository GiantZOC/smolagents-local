# Smolagent ReAct Implementation Plan (Final)
## Designed for Low-Power LLMs in Mostly Local Environments

**Version**: 3.0 - High-leverage Phoenix-first architecture

---

## Core Design Principles (Enforced Throughout)

1. **Keep smolagents loop** - Don't rewrite what works; instrument it instead
2. **InstrumentedTool wrapper** - Single highest-leverage move (validation + tracing + truncation)
3. **Externalize enforcement** - Approvals, validation, errors live in Python, not prompts
4. **Minimize LLM reasoning** - Recovery hints, not automatic retries
5. **Phoenix-first observability** - Trace every tool, sandbox op, approval gate
6. **Repo-mounted sandbox** - Real validation with git apply --check

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ smolagents ToolCallingAgent (keeps native loop)             │
│   ├─ model.step (each LLM call)                             │
│   └─ InstrumentedTool wrapper (wraps ALL tools)             │
│        ├─ Phoenix span: tool.<name>                          │
│        ├─ validate inputs (path, ranges, commands)           │
│        ├─ call real tool                                     │
│        ├─ truncate outputs                                   │
│        ├─ normalize errors + recovery hints                  │
│        ├─ record into AgentState                             │
│        └─ end span with metrics                              │
└─────────────────────────────────────────────────────────────┘

Mutating tools check ApprovalStore internally:
  - propose_patch: creates proposal, returns patch_id
  - apply_patch: checks is_approved(patch_id)
    → if not: return {"error": "APPROVAL_REQUIRED", ...}
    → if yes: apply in sandbox, then repo

Retry Policy returns recovery_suggestion (not auto-execute):
  - Tool errors include "recovery_suggestion" field
  - Model sees suggestion, can choose to follow it
  - Phoenix traces error → suggestion → action causally
```

---

## Repository Structure

```
smolagent_react_scaffold/
  pyproject.toml
  README.md
  docker/
    Dockerfile.sandbox   # Slim Python + git image for patching
  
  agent_runtime/
    __init__.py
    run.py               # Agent orchestration + CLI
    prompt.py            # System prompts (model-specific variants)
    policy.py            # Recovery hint generation
    state.py             # Agent state tracking
    sandbox.py           # Repo-mounted Docker sandbox
    instrumentation.py   # InstrumentedTool wrapper + Phoenix setup
    approval.py          # ApprovalStore + approval gate
    
    tools/
      __init__.py
      repo.py            # Repo info, list files
      search.py          # Ripgrep search
      files.py           # Read file, read snippet
      patch.py           # Propose/Show/Apply patches (with approval checks)
      shell.py           # Run commands, run tests
      validation.py      # Input validation helpers
  
  tests/
    __init__.py
    test_instrumentation.py  # InstrumentedTool tests
    test_tools.py            # Tool determinism tests
    test_policy.py           # Recovery hints tests
    test_sandbox.py          # Sandbox execution tests
    test_approval.py         # Approval gate tests
```

---

## Implementation Details

### 1. InstrumentedTool Wrapper (`agent_runtime/instrumentation.py`)

**The single highest-leverage component.**

```python
# agent_runtime/instrumentation.py

"""
InstrumentedTool wrapper - wraps ALL tools with:
- Input validation
- Phoenix tracing
- Output truncation
- Error normalization + recovery hints
- State recording
"""

import time
import hashlib
import json
from typing import Any, Dict, Optional
from smolagents import Tool
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from agent_runtime.tools.validation import (
    validate_path,
    validate_line_range,
    validate_command,
    truncate_output,
    ValidationError
)
from agent_runtime.policy import RecoveryHintGenerator
from agent_runtime.state import AgentState


tracer = trace.get_tracer(__name__)


class InstrumentedTool(Tool):
    """
    Wrapper that instruments any Tool with:
    - Input validation
    - Phoenix span per call
    - Output truncation
    - Error normalization
    - Recovery hints
    - State tracking
    """
    
    def __init__(self, tool: Tool, state: AgentState, validation_config: Optional[Dict] = None):
        """
        Args:
            tool: The actual tool to wrap
            state: AgentState instance for recording
            validation_config: Optional validation rules per tool
        """
        self.tool = tool
        self.state = state
        self.validation_config = validation_config or {}
        
        # Copy tool metadata
        self.name = tool.name
        self.description = tool.description
        self.inputs = tool.inputs
        self.output_type = tool.output_type
    
    def _validate_inputs(self, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Validate inputs based on tool type.
        
        Returns:
            Error dict if validation fails, None if valid
        """
        try:
            # Path validation for file tools
            if "path" in kwargs:
                validate_path(kwargs["path"])
            
            # Line range validation
            if "start_line" in kwargs and "end_line" in kwargs:
                validate_line_range(kwargs["start_line"], kwargs["end_line"])
            
            # Command validation for shell tools
            if "cmd" in kwargs or "test_cmd" in kwargs:
                cmd = kwargs.get("cmd") or kwargs.get("test_cmd")
                allowed_prefixes = self.validation_config.get("allowed_cmd_prefixes")
                validate_command(cmd, allowed_prefixes)
            
            return None  # Valid
        
        except ValidationError as e:
            return {
                "error": "VALIDATION_FAILED",
                "message": str(e),
                "tool": self.name,
                "arguments": kwargs
            }
    
    def _compute_args_hash(self, kwargs: Dict) -> str:
        """Compute stable hash of arguments for tracing."""
        # Sort keys for stability
        sorted_args = json.dumps(kwargs, sort_keys=True)
        return hashlib.sha256(sorted_args.encode()).hexdigest()[:8]
    
    def _normalize_error(self, result: Any) -> Dict[str, Any]:
        """
        Ensure errors follow schema: {"error": "TYPE", ...}
        Add recovery hints.
        """
        if not isinstance(result, dict):
            return result
        
        if "error" not in result:
            return result
        
        # Add recovery suggestion
        error_type = result["error"]
        hint = RecoveryHintGenerator.generate_hint(error_type, result)
        
        if hint:
            result["recovery_suggestion"] = hint
        
        return result
    
    def _truncate_result(self, result: Any) -> Any:
        """Truncate large outputs."""
        if isinstance(result, dict):
            # Truncate string values
            for key in ["lines", "text", "stdout_tail", "stderr_tail", "diff"]:
                if key in result and isinstance(result[key], str):
                    result[key] = truncate_output(result[key], max_chars=3000, max_lines=150)
            
            # Add truncation indicator
            if any(key in result for key in ["lines", "text", "stdout_tail"]):
                result["truncated"] = True
        
        elif isinstance(result, list):
            # Truncate array results
            max_items = 100
            if len(result) > max_items:
                result = result[:max_items]
                result.append({"message": f"Truncated to {max_items} items"})
        
        elif isinstance(result, str):
            result = truncate_output(result)
        
        return result
    
    def forward(self, **kwargs):
        """
        Execute tool with full instrumentation.
        
        Sequence:
        1. Validate inputs
        2. Start Phoenix span
        3. Call real tool
        4. Truncate outputs
        5. Normalize errors + add hints
        6. Record to state
        7. End span with metrics
        """
        args_hash = self._compute_args_hash(kwargs)
        
        # Start Phoenix span
        with tracer.start_as_current_span(f"tool.{self.name}") as span:
            start_time = time.time()
            
            # Set span attributes
            span.set_attribute("tool.name", self.name)
            span.set_attribute("tool.args.hash", args_hash)
            span.set_attribute("tool.args.size", len(json.dumps(kwargs)))
            
            # 1. Validate inputs
            validation_error = self._validate_inputs(**kwargs)
            if validation_error:
                span.set_status(Status(StatusCode.ERROR, "Validation failed"))
                span.set_attribute("result.error_type", "VALIDATION_FAILED")
                
                # Record to state
                self.state.add_step(self.name, kwargs, validation_error)
                
                return validation_error
            
            # 2. Call real tool
            try:
                result = self.tool.forward(**kwargs)
            except Exception as e:
                error_result = {
                    "error": "TOOL_EXCEPTION",
                    "tool": self.name,
                    "message": str(e),
                    "type": type(e).__name__
                }
                
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute("result.error_type", "TOOL_EXCEPTION")
                
                # Record to state
                self.state.add_step(self.name, kwargs, error_result)
                
                return error_result
            
            # 3. Truncate outputs
            result = self._truncate_result(result)
            
            # 4. Normalize errors + add recovery hints
            result = self._normalize_error(result)
            
            # 5. Record metrics
            duration_ms = (time.time() - start_time) * 1000
            
            if isinstance(result, dict):
                is_error = "error" in result
                
                span.set_attribute("result.ok", not is_error)
                if is_error:
                    span.set_status(Status(StatusCode.ERROR, result.get("error")))
                    span.set_attribute("result.error_type", result.get("error"))
                    
                    # Track if recovery hint was added
                    if "recovery_suggestion" in result:
                        span.set_attribute("policy.suggested_next_tool", 
                                         result["recovery_suggestion"]["tool_call"]["name"])
                
                # Output size metrics
                if "lines" in result:
                    span.set_attribute("output.lines", result.get("lines", "").count("\n"))
                if any(k in result for k in ["lines", "text", "stdout_tail", "diff"]):
                    output_str = str(result.get("lines") or result.get("text") or 
                                   result.get("stdout_tail") or result.get("diff") or "")
                    span.set_attribute("output.chars", len(output_str))
                    span.set_attribute("output.truncated", result.get("truncated", False))
            
            elif isinstance(result, list):
                span.set_attribute("result.ok", True)
                span.set_attribute("output.items", len(result))
            
            span.set_attribute("duration_ms", duration_ms)
            
            # 6. Record to state
            self.state.add_step(self.name, kwargs, result)
            
            return result


def wrap_tools_with_instrumentation(tools: list[Tool], state: AgentState, 
                                    validation_config: Optional[Dict] = None) -> list[InstrumentedTool]:
    """
    Wrap all tools with InstrumentedTool.
    
    Args:
        tools: List of Tool instances
        state: AgentState for recording
        validation_config: Optional per-tool validation rules
        
    Returns:
        List of InstrumentedTool instances
    """
    return [InstrumentedTool(tool, state, validation_config) for tool in tools]
```

---

### 2. ApprovalStore for Enforcement (`agent_runtime/approval.py`)

**Enforce approvals inside mutating tools, not in prompts.**

```python
# agent_runtime/approval.py

"""
ApprovalStore - tracks which patches/commands have been approved.

Tools check this store BEFORE executing mutating operations.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Callable
from opentelemetry import trace


tracer = trace.get_tracer(__name__)


@dataclass
class PatchProposal:
    """Artifact representing a proposed code change."""
    patch_id: str
    base_ref: str  # File path
    diff: str
    summary: str


@dataclass
class Approval:
    """User's decision on a proposal."""
    approved: bool
    feedback: Optional[str] = None


class ApprovalStore:
    """
    Central store for tracking approvals.
    
    Mutating tools check this before executing.
    """
    
    def __init__(self, approval_callback: Optional[Callable] = None):
        """
        Args:
            approval_callback: Function(PatchProposal) -> Approval
        """
        self.proposals: Dict[str, PatchProposal] = {}
        self.approvals: Dict[str, Approval] = {}
        self.approval_callback = approval_callback or self._console_approval
    
    def add_proposal(self, proposal: PatchProposal):
        """Store a new proposal."""
        self.proposals[proposal.patch_id] = proposal
    
    def is_approved(self, patch_id: str) -> bool:
        """Check if a patch has been approved."""
        approval = self.approvals.get(patch_id)
        return approval is not None and approval.approved
    
    def get_approval_feedback(self, patch_id: str) -> Optional[str]:
        """Get rejection feedback if available."""
        approval = self.approvals.get(patch_id)
        if approval and not approval.approved:
            return approval.feedback
        return None
    
    def request_approval(self, patch_id: str) -> Approval:
        """
        Request user approval for a patch.
        
        Creates Phoenix span: approval.wait
        
        Returns:
            Approval decision
        """
        proposal = self.proposals.get(patch_id)
        if not proposal:
            return Approval(approved=False, feedback=f"Patch {patch_id} not found")
        
        # Create Phoenix span for approval wait
        with tracer.start_as_current_span("approval.wait") as span:
            span.set_attribute("approval.kind", "patch")
            span.set_attribute("approval.patch_id", patch_id)
            span.set_attribute("approval.file", proposal.base_ref)
            
            # Request approval from user
            approval = self.approval_callback(proposal)
            
            # Record decision
            self.approvals[patch_id] = approval
            
            span.set_attribute("approval.granted", approval.approved)
            if approval.feedback:
                span.set_attribute("approval.feedback", approval.feedback[:200])
        
        return approval
    
    def _console_approval(self, proposal: PatchProposal) -> Approval:
        """Default console-based approval."""
        print("\n" + "=" * 70)
        print("🔧 PATCH APPROVAL REQUEST")
        print("=" * 70)
        print(f"Patch ID: {proposal.patch_id}")
        print(f"File: {proposal.base_ref}")
        print(f"Summary: {proposal.summary}")
        print("\nDiff:")
        print(proposal.diff)
        print("=" * 70)
        
        while True:
            choice = input("\nApprove? [y/n/feedback]: ").strip().lower()
            if choice == 'y':
                return Approval(approved=True)
            elif choice == 'n':
                return Approval(approved=False)
            else:
                return Approval(approved=False, feedback=choice)


# Global approval store (injected into tools)
_approval_store: Optional[ApprovalStore] = None


def set_approval_store(store: ApprovalStore):
    """Set global approval store."""
    global _approval_store
    _approval_store = store


def get_approval_store() -> ApprovalStore:
    """Get global approval store."""
    if _approval_store is None:
        raise RuntimeError("ApprovalStore not initialized. Call set_approval_store() first.")
    return _approval_store
```

---

### 3. Recovery Hint Generator (`agent_runtime/policy.py`)

**Return suggestions, not automatic execution.**

```python
# agent_runtime/policy.py

"""
Recovery hint generator.

Instead of auto-executing next tool, return a structured hint
that the model can choose to follow.
"""

from typing import Dict, Any, Optional


class RecoveryHintGenerator:
    """
    Generates recovery suggestions for tool errors.
    
    These are hints returned WITH the error, not automatic retries.
    Small models can "accept the hint" as their next action.
    """
    
    HINT_RULES: Dict[str, callable] = {
        "FILE_NOT_FOUND": lambda ctx: {
            "tool_call": {
                "name": "list_files",
                "arguments": {
                    "glob": f"**/{ctx.get('path', '').split('/')[-1]}",
                    "limit": 50
                }
            },
            "rationale": "Search for the file by name across the repository"
        },
        
        "NOT_FOUND_IN_FILE": lambda ctx: {
            "tool_call": {
                "name": "read_file",
                "arguments": {
                    "path": ctx.get('path'),
                    "start_line": 1,
                    "end_line": 200
                }
            },
            "rationale": "Read more of the file to find the content"
        },
        
        "INVALID_LINE_RANGE": lambda ctx: {
            "tool_call": {
                "name": "read_file",
                "arguments": {
                    "path": ctx.get('path'),
                    "start_line": 1,
                    "end_line": 200
                }
            },
            "rationale": "Use valid line range starting from 1"
        },
        
        "RG_FAILED": lambda ctx: {
            "tool_call": {
                "name": "list_files",
                "arguments": {
                    "glob": ctx.get('glob', '**/*'),
                    "limit": 100
                }
            },
            "rationale": "List files instead to explore the directory structure"
        },
        
        "PATCH_APPLY_FAILED": lambda ctx: {
            "tool_call": {
                "name": "show_patch",
                "arguments": {
                    "patch_id": ctx.get('patch_id')
                }
            },
            "rationale": "Review the patch to understand why it failed"
        },
        
        "APPROVAL_REQUIRED": lambda ctx: {
            # No automatic recovery - user must approve
            "message": "Waiting for user approval. Patch will be applied once approved.",
            "no_retry": True
        },
        
        "VALIDATION_FAILED": lambda ctx: {
            "message": f"Fix the validation error: {ctx.get('message')}",
            "no_retry": True
        },
    }
    
    @classmethod
    def generate_hint(cls, error_type: str, error_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate recovery hint for an error.
        
        Args:
            error_type: Error type string
            error_context: Full error dict with context
            
        Returns:
            Recovery hint dict or None
        """
        if error_type not in cls.HINT_RULES:
            return None
        
        hint = cls.HINT_RULES[error_type](error_context)
        
        # Don't return hints for no-retry cases
        if hint.get("no_retry"):
            return None
        
        return hint


class StepLimiter:
    """
    Tracks agent steps and enforces limits.
    
    Prevents infinite loops with small models.
    """
    
    def __init__(self, max_steps: int = 25):
        self.max_steps = max_steps
        self.steps_taken = 0
    
    def can_continue(self) -> bool:
        """Check if agent can take another step."""
        return self.steps_taken < self.max_steps
    
    def record_step(self):
        """Record that a step was taken."""
        self.steps_taken += 1
    
    def reset(self):
        """Reset counter for new task."""
        self.steps_taken = 0
```

---

### 4. Repo-Mounted Sandbox (`agent_runtime/sandbox.py`)

**Mount the repo so git apply --check actually works.**

```python
# agent_runtime/sandbox.py

"""
Repo-mounted Docker sandbox for patch validation.

Key change: mounts actual repo at /workspace so git operations work.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from opentelemetry import trace


tracer = trace.get_tracer(__name__)


class DockerSandbox:
    """
    Isolated Docker container with repo mounted.
    
    Features:
    - Repo mounted at /workspace
    - git available for patch validation
    - Phoenix tracing for sandbox operations
    """
    
    def __init__(self, 
                 repo_root: str,
                 image: str = "smolagent-sandbox:latest",
                 enable_phoenix: bool = True):
        """
        Args:
            repo_root: Absolute path to repo root
            image: Docker image (must have git + python)
            enable_phoenix: Whether to pass Phoenix endpoint
        """
        self.repo_root = Path(repo_root).resolve()
        self.image = image
        self.enable_phoenix = enable_phoenix
        self.container_id: Optional[str] = None
        self._setup_container()
    
    def _setup_container(self):
        """Create and start container with repo mounted."""
        with tracer.start_as_current_span("sandbox.setup") as span:
            # Build docker run command
            cmd = [
                "docker", "run", "-d",
                "--rm",  # Auto-remove on exit
                "-v", f"{self.repo_root}:/workspace",  # Mount repo
                "-w", "/workspace",
            ]
            
            # Add Phoenix endpoint if enabled
            if self.enable_phoenix:
                cmd.extend(["-e", "PHOENIX_ENDPOINT=http://host.docker.internal:6006/v1/traces"])
            
            # Add image and keep-alive command
            cmd.extend([self.image, "tail", "-f", "/dev/null"])
            
            # Start container
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                span.set_attribute("error", True)
                raise RuntimeError(f"Failed to start container: {result.stderr}")
            
            self.container_id = result.stdout.strip()
            span.set_attribute("container_id", self.container_id)
    
    def run_code(self, code: str, timeout: int = 60) -> str:
        """
        Execute Python code in sandbox.
        
        Args:
            code: Python code to execute
            timeout: Timeout in seconds
            
        Returns:
            Combined stdout/stderr output
        """
        with tracer.start_as_current_span("sandbox.run_code") as span:
            if not self.container_id:
                raise RuntimeError("Container not initialized")
            
            span.set_attribute("code.size", len(code))
            
            # Write code to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            try:
                # Copy code to container
                subprocess.run(
                    ["docker", "cp", temp_path, f"{self.container_id}:/tmp/exec.py"],
                    check=True,
                    capture_output=True
                )
                
                # Execute in container
                result = subprocess.run(
                    ["docker", "exec", self.container_id, "python", "/tmp/exec.py"],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                # Combine output
                output = result.stdout
                if result.stderr:
                    output += f"\n{result.stderr}"
                
                span.set_attribute("returncode", result.returncode)
                span.set_attribute("output.size", len(output))
                
                return output
            
            finally:
                Path(temp_path).unlink(missing_ok=True)
    
    def validate_patch(self, patch_content: str) -> Tuple[bool, str]:
        """
        Validate patch with git apply --check.
        
        This is the key operation that requires repo mounting.
        
        Args:
            patch_content: Unified diff content
            
        Returns:
            (success, message) tuple
        """
        with tracer.start_as_current_span("sandbox.validate_patch") as span:
            if not self.container_id:
                raise RuntimeError("Container not initialized")
            
            span.set_attribute("dry_run", True)
            span.set_attribute("patch.size", len(patch_content))
            
            # Write patch to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                f.write(patch_content)
                temp_path = f.name
            
            try:
                # Copy patch to container
                subprocess.run(
                    ["docker", "cp", temp_path, f"{self.container_id}:/tmp/apply.patch"],
                    check=True,
                    capture_output=True
                )
                
                # Validate with git apply --check
                result = subprocess.run(
                    ["docker", "exec", self.container_id, 
                     "git", "apply", "--check", "--whitespace=nowarn", "/tmp/apply.patch"],
                    capture_output=True,
                    text=True
                )
                
                span.set_attribute("returncode", result.returncode)
                
                if result.returncode == 0:
                    span.set_attribute("valid", True)
                    return (True, "Patch is valid")
                else:
                    span.set_attribute("valid", False)
                    span.set_attribute("stderr_tail", result.stderr[:500])
                    return (False, result.stderr)
            
            finally:
                Path(temp_path).unlink(missing_ok=True)
    
    def cleanup(self):
        """Stop and remove container."""
        with tracer.start_as_current_span("sandbox.cleanup"):
            if self.container_id:
                subprocess.run(
                    ["docker", "stop", self.container_id],
                    capture_output=True
                )
                self.container_id = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
```

---

### 5. Updated Patch Tools with Approval Enforcement

```python
# agent_runtime/tools/patch.py

"""
Patch tools with approval enforcement.

Key change: apply_patch checks ApprovalStore.is_approved() BEFORE applying.
"""

import uuid
from pathlib import Path
from smolagents import Tool
from agent_runtime.tools.repo import RepoInfoTool
from agent_runtime.approval import PatchProposal, get_approval_store
from agent_runtime.sandbox import DockerSandbox
import difflib
import subprocess


class ProposePatchTool(Tool):
    name = "propose_patch"
    description = """Create a patch proposal (unified diff).
    
    This creates a patch that will be shown to the user for approval.
    After approval, use apply_patch to apply it.
    
    Returns: {patch_id, intent, file_path, diff_preview}"""
    
    inputs = {
        "intent": {"type": "string", "description": "short description of what the patch should do"},
        "file_path": {"type": "string", "description": "repo-relative path to file being modified"},
        "original_content": {"type": "string", "description": "current file content"},
        "new_content": {"type": "string", "description": "proposed new content"},
    }
    output_type = "object"

    def forward(self, intent: str, file_path: str, original_content: str, new_content: str):
        # Generate patch ID
        patch_id = f"patch_{uuid.uuid4().hex[:10]}"
        
        # Create unified diff
        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        )
        
        diff_text = ''.join(diff)
        
        # Create proposal
        proposal = PatchProposal(
            patch_id=patch_id,
            base_ref=file_path,
            diff=diff_text,
            summary=intent
        )
        
        # Store in approval store
        approval_store = get_approval_store()
        approval_store.add_proposal(proposal)
        
        # Automatically request approval (creates Phoenix span)
        approval = approval_store.request_approval(patch_id)
        
        return {
            "patch_id": patch_id,
            "intent": intent,
            "file_path": file_path,
            "diff_preview": diff_text[:500] + ("..." if len(diff_text) > 500 else ""),
            "approved": approval.approved,
            "feedback": approval.feedback,
            "message": "Patch created and approval requested. Use apply_patch to apply." if approval.approved 
                      else f"Patch rejected. Feedback: {approval.feedback or 'None'}"
        }


class ShowPatchTool(Tool):
    name = "show_patch"
    description = "Show a previously proposed patch by id."
    inputs = {
        "patch_id": {"type": "string", "description": "patch id"}
    }
    output_type = "object"

    def forward(self, patch_id: str):
        approval_store = get_approval_store()
        proposal = approval_store.proposals.get(patch_id)
        
        if not proposal:
            return {"error": "PATCH_NOT_FOUND", "patch_id": patch_id}
        
        # Check approval status
        is_approved = approval_store.is_approved(patch_id)
        feedback = approval_store.get_approval_feedback(patch_id)
        
        return {
            "patch_id": patch_id,
            "intent": proposal.summary,
            "file_path": proposal.base_ref,
            "diff": proposal.diff,
            "approved": is_approved,
            "feedback": feedback
        }


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = """Apply a previously proposed patch by id.
    
    IMPORTANT: This only works if the patch has been approved.
    If not approved, returns APPROVAL_REQUIRED error.
    
    Validates patch in sandbox before applying to repo.
    
    Returns: {ok, patch_id, intent} on success or {error, ...} on failure"""
    
    inputs = {
        "patch_id": {"type": "string", "description": "patch id to apply"}
    }
    output_type = "object"

    def forward(self, patch_id: str):
        approval_store = get_approval_store()
        
        # Get proposal
        proposal = approval_store.proposals.get(patch_id)
        if not proposal:
            return {
                "error": "PATCH_NOT_FOUND",
                "patch_id": patch_id,
                "message": "Patch not found. Use propose_patch to create it."
            }
        
        # ENFORCEMENT: Check if approved
        if not approval_store.is_approved(patch_id):
            feedback = approval_store.get_approval_feedback(patch_id)
            return {
                "error": "APPROVAL_REQUIRED",
                "patch_id": patch_id,
                "message": "Patch has not been approved by user.",
                "feedback": feedback,
                "blocked.approval_required": True,
                "approval.kind": "patch"
            }
        
        # Get repo root
        root = RepoInfoTool().forward()["root"]
        
        # Validate in sandbox (creates Phoenix span)
        with DockerSandbox(repo_root=root, enable_phoenix=True) as sandbox:
            valid, message = sandbox.validate_patch(proposal.diff)
            
            if not valid:
                return {
                    "error": "PATCH_APPLY_FAILED",
                    "patch_id": patch_id,
                    "message": f"Patch validation failed: {message}",
                    "suggestion": "File may have changed since proposal. Create a new patch."
                }
        
        # Apply to actual repository
        tmp = Path(root) / f".{patch_id}.diff"
        tmp.write_text(proposal.diff)
        
        try:
            # Use git apply
            cmd = ["git", "apply", "--whitespace=nowarn", str(tmp)]
            
            proc = subprocess.Popen(
                cmd,
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            out, err = proc.communicate()
            
            if proc.returncode != 0:
                return {
                    "error": "PATCH_APPLY_FAILED",
                    "patch_id": patch_id,
                    "stdout": out[-1000:],
                    "stderr": err[-1000:],
                    "message": "Patch command failed. See stdout/stderr for details."
                }
            
            # Success - clean up
            approval_store.proposals.pop(patch_id, None)
            approval_store.approvals.pop(patch_id, None)
            
            return {
                "ok": True,
                "patch_id": patch_id,
                "intent": proposal.summary,
                "file_path": proposal.base_ref,
                "message": f"Patch {patch_id} applied successfully to {proposal.base_ref}"
            }
        
        finally:
            tmp.unlink(missing_ok=True)
```

---

### 6. Phoenix Setup (`agent_runtime/instrumentation.py` - continued)

```python
# agent_runtime/instrumentation.py (Phoenix setup section)

"""Phoenix telemetry setup."""

from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def setup_phoenix_telemetry(endpoint: str = "http://localhost:6006/v1/traces"):
    """
    Setup Phoenix telemetry for smolagents.
    
    Creates spans:
    - agent.run (root)
    - model.step (each LLM call)
    - tool.<name> (via InstrumentedTool)
    - sandbox.<op> (via DockerSandbox)
    - approval.wait (via ApprovalStore)
    
    Args:
        endpoint: Phoenix OTLP endpoint
    """
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint))
    )
    
    # Instrument smolagents
    SmolagentsInstrumentor().instrument(tracer_provider=tracer_provider)
    
    print(f"✓ Phoenix telemetry enabled: {endpoint}")
```

---

### 7. Agent Runtime with InstrumentedTool Integration

```python
# agent_runtime/run.py

"""
Agent runtime with InstrumentedTool wrapper.

Key changes:
- Wrap all tools with InstrumentedTool
- Initialize ApprovalStore
- Setup Phoenix telemetry
- Keep smolagents native loop
"""

import argparse
import logging
from smolagents import ToolCallingAgent, LiteLLMModel, PromptTemplates

from agent_runtime.prompt import get_system_prompt
from agent_runtime.state import AgentState
from agent_runtime.approval import ApprovalStore, set_approval_store
from agent_runtime.instrumentation import (
    wrap_tools_with_instrumentation,
    setup_phoenix_telemetry
)

# Import raw tools
from agent_runtime.tools.repo import RepoInfoTool, ListFilesTool
from agent_runtime.tools.search import RipgrepSearchTool
from agent_runtime.tools.files import ReadFileTool, ReadFileSnippetTool
from agent_runtime.tools.patch import ProposePatchTool, ShowPatchTool, ApplyPatchTool
from agent_runtime.tools.shell import RunCmdTool, RunTestsTool


logger = logging.getLogger(__name__)


def build_agent(model_id: str, api_base: str, max_steps: int, 
                enable_phoenix: bool = True) -> tuple[ToolCallingAgent, AgentState]:
    """
    Build agent with instrumented tools.
    
    Returns:
        (agent, state) tuple
    """
    # Setup Phoenix if enabled
    if enable_phoenix:
        setup_phoenix_telemetry()
    
    # Create model
    model = LiteLLMModel(
        model_id=model_id,
        api_base=api_base,
        temperature=0.1,
        max_tokens=1024,
    )
    
    # Create raw tools
    raw_tools = [
        RepoInfoTool(),
        ListFilesTool(),
        RipgrepSearchTool(),
        ReadFileTool(),
        ReadFileSnippetTool(),
        ProposePatchTool(),
        ShowPatchTool(),
        ApplyPatchTool(),
        RunCmdTool(),
        RunTestsTool(),
    ]
    
    # Create state
    state = AgentState(task="")  # Will be set in run()
    
    # Wrap tools with instrumentation
    instrumented_tools = wrap_tools_with_instrumentation(raw_tools, state)
    
    # Get system prompt
    system_prompt = get_system_prompt(model_id)
    prompt_templates = PromptTemplates(system_prompt=system_prompt)
    
    # Build agent with instrumented tools
    agent = ToolCallingAgent(
        tools=instrumented_tools,
        model=model,
        prompt_templates=prompt_templates,
        add_base_tools=False,
        max_steps=max_steps,
    )
    
    logger.info(f"Agent built with {len(instrumented_tools)} instrumented tools")
    return agent, state


def main():
    parser = argparse.ArgumentParser(
        description="Smolagent ReAct with InstrumentedTool wrapper"
    )
    parser.add_argument("task", nargs="?", help="Task to run")
    parser.add_argument("--model-id", default="ollama_chat/qwen2.5-coder:14b")
    parser.add_argument("--api-base", default="http://localhost:11434")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--no-phoenix", action="store_true", help="Disable Phoenix")
    
    args = parser.parse_args()
    
    # Get task
    if args.task:
        task = args.task
    else:
        print("Enter task:")
        task = input()
    
    if not task.strip():
        print("Error: No task provided")
        return 1
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize ApprovalStore (uses console approval by default)
    approval_store = ApprovalStore()
    set_approval_store(approval_store)
    
    # Build agent
    print(f"Building agent with model: {args.model_id}")
    agent, state = build_agent(
        args.model_id, 
        args.api_base, 
        args.max_steps,
        enable_phoenix=not args.no_phoenix
    )
    
    # Set task in state
    state.task = task
    
    # Run task
    print(f"\nRunning task: {task}\n")
    print("=" * 70)
    
    try:
        result = agent.run(task)
        
        print("\n" + "=" * 70)
        print("RESULT:")
        print("=" * 70)
        print(result)
        print()
        
        # Print state summary
        print("\n" + "-" * 70)
        print("STATE SUMMARY:")
        print("-" * 70)
        print(state.summary())
        print()
        
        if not args.no_phoenix:
            print("\n📊 View traces at: http://localhost:6006/projects/")
        
        return 0
    
    except Exception as e:
        print(f"\nError: {e}")
        logger.exception("Task failed")
        return 1


if __name__ == "__main__":
    exit(main())
```

---

### 8. Dockerfile for Sandbox

```dockerfile
# docker/Dockerfile.sandbox

FROM python:3.10-slim

# Install git and other essentials
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python packages commonly needed for code execution
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    requests

WORKDIR /workspace

CMD ["/bin/bash"]
```

Build with:
```bash
docker build -t smolagent-sandbox:latest -f docker/Dockerfile.sandbox .
```

---

### 9. Updated System Prompts with Recovery Hints

```python
# agent_runtime/prompt.py

"""System prompts with recovery hint guidance."""

DEFAULT_SYSTEM_PROMPT = r"""
You are a low-power local-tool agent.

Core constraints:
- Keep reasoning shallow. Do NOT write long plans.
- Do NOT reveal chain-of-thought.
- Every step must be EITHER a tool call OR a final answer.

TOOL CALL FORMAT:
{
  "tool_call": {
    "name": "<tool_name>",
    "arguments": { ... }
  }
}

FINAL ANSWER FORMAT:
{
  "final": "<your answer>"
}

Rules:
- Use tools for all repo operations (search, read, patch, run).
- Prefer SEARCH then targeted READ.
- When a tool returns an error with "recovery_suggestion", you can follow that suggestion for your next action.
- Patch workflow: propose_patch (user approval happens automatically) -> apply_patch
- All outputs are truncated. Be specific in queries.

ERROR HANDLING:
When a tool fails, check if "recovery_suggestion" is provided. Example:

{
  "error": "FILE_NOT_FOUND",
  "path": "foo.py",
  "recovery_suggestion": {
    "tool_call": {
      "name": "list_files",
      "arguments": {"glob": "**/foo.py", "limit": 50}
    },
    "rationale": "Search for the file by name"
  }
}

You can use the suggested tool call as your next action.

TOOLS: repo_info, list_files, rg_search, read_file, read_file_snippet, propose_patch, show_patch, apply_patch, run_cmd, run_tests
"""

QWEN_SYSTEM_PROMPT = r"""Tool agent. One action per turn.

FORMAT:
{"tool_call": {"name": "<tool>", "arguments": {...}}}
OR
{"final": "<answer>"}

ERRORS: If tool returns "recovery_suggestion", use it as next action.

PATCH: propose_patch (approval automatic) -> apply_patch

TOOLS: repo_info, list_files, rg_search, read_file, read_file_snippet, propose_patch, show_patch, apply_patch, run_cmd, run_tests
"""

# ... (rest of prompt variants)

PROMPT_VARIANTS = {
    "qwen": QWEN_SYSTEM_PROMPT,
    "qwen2.5-coder": QWEN_SYSTEM_PROMPT,
    "deepseek": QWEN_SYSTEM_PROMPT,
    "default": DEFAULT_SYSTEM_PROMPT,
}

def get_system_prompt(model_id: str) -> str:
    """Select prompt based on model ID."""
    model_lower = model_id.lower()
    for key, prompt in PROMPT_VARIANTS.items():
        if key in model_lower:
            return prompt
    return DEFAULT_SYSTEM_PROMPT
```

---

## Phoenix Tracing Structure

### Span Hierarchy

```
agent.run (root span from smolagents)
├─ model.step (each LLM call)
│  └─ attributes: prompt.tokens, response.type, response.json_valid
├─ tool.<name> (from InstrumentedTool)
│  ├─ attributes:
│  │  ├─ tool.name
│  │  ├─ tool.args.hash
│  │  ├─ tool.args.size
│  │  ├─ result.ok
│  │  ├─ result.error_type (if error)
│  │  ├─ output.chars
│  │  ├─ output.lines
│  │  ├─ output.truncated
│  │  ├─ policy.suggested_next_tool (if recovery hint)
│  │  └─ duration_ms
│  └─ child spans:
│     ├─ sandbox.validate_patch (if patch tool)
│     │  ├─ attributes: dry_run, patch.size, valid, returncode
│     │  └─ duration_ms
│     └─ approval.wait (if mutating tool)
│        ├─ attributes:
│        │  ├─ approval.kind = "patch"
│        │  ├─ approval.patch_id
│        │  ├─ approval.file
│        │  ├─ approval.granted
│        │  └─ approval.feedback (if rejected)
│        └─ duration_ms
└─ ... (more steps)
```

### Key Attributes for Debugging

**Tool spans:**
- `tool.name` - Which tool was called
- `result.ok` - Success/failure
- `result.error_type` - Type of error (FILE_NOT_FOUND, etc.)
- `policy.suggested_next_tool` - Recovery hint provided
- `output.truncated` - Whether output was truncated

**Approval spans:**
- `approval.granted` - Whether user approved
- `approval.feedback` - Rejection reason
- `blocked.approval_required` - Tool blocked on approval

**Sandbox spans:**
- `valid` - Whether patch validated
- `dry_run` - Validation vs actual apply
- `returncode` - Git command exit code

---

## Testing Strategy

```python
# tests/test_instrumentation.py

"""Test InstrumentedTool wrapper."""

import pytest
from agent_runtime.instrumentation import InstrumentedTool
from agent_runtime.state import AgentState
from agent_runtime.tools.files import ReadFileTool


def test_instrumented_tool_validation():
    """InstrumentedTool should validate inputs."""
    state = AgentState(task="test")
    tool = ReadFileTool()
    instrumented = InstrumentedTool(tool, state)
    
    # Should catch path traversal
    result = instrumented.forward(path="../../../etc/passwd")
    assert "error" in result
    assert result["error"] == "VALIDATION_FAILED"


def test_instrumented_tool_truncation():
    """InstrumentedTool should truncate large outputs."""
    state = AgentState(task="test")
    tool = ReadFileTool()
    instrumented = InstrumentedTool(tool, state)
    
    # Read a large file (if it exists)
    result = instrumented.forward(path="README.md", start_line=1, end_line=1000)
    
    if "lines" in result:
        # Should be truncated
        assert len(result["lines"]) <= 3000 or result.get("truncated")


def test_instrumented_tool_recovery_hints():
    """InstrumentedTool should add recovery hints to errors."""
    state = AgentState(task="test")
    tool = ReadFileTool()
    instrumented = InstrumentedTool(tool, state)
    
    # Trigger FILE_NOT_FOUND
    result = instrumented.forward(path="nonexistent.py")
    
    assert "error" in result
    assert result["error"] == "FILE_NOT_FOUND"
    assert "recovery_suggestion" in result
    assert result["recovery_suggestion"]["tool_call"]["name"] == "list_files"
```

---

## README Updates

```markdown
# Smolagent ReAct Scaffold

Phoenix-first ReAct agent for local low-power LLMs.

## Architecture Highlights

### InstrumentedTool Wrapper
Every tool is wrapped with `InstrumentedTool` which:
- Validates inputs (path traversal, line ranges, commands)
- Creates Phoenix span per call
- Truncates outputs to prevent context overflow
- Normalizes errors to `{"error": "TYPE", ...}` schema
- Adds recovery hints for common errors
- Records to AgentState

### Approval Enforcement
Mutating tools (apply_patch) check `ApprovalStore.is_approved()` BEFORE executing.
Returns `{"error": "APPROVAL_REQUIRED"}` if not approved.

### Recovery Hints (Not Auto-Retry)
Errors include `recovery_suggestion` field that the model can choose to follow:
```json
{
  "error": "FILE_NOT_FOUND",
  "path": "foo.py",
  "recovery_suggestion": {
    "tool_call": {
      "name": "list_files",
      "arguments": {"glob": "**/foo.py"}
    },
    "rationale": "Search for the file"
  }
}
```

### Repo-Mounted Sandbox
Docker sandbox mounts actual repo at `/workspace` so `git apply --check` works.

### Phoenix Tracing
Every operation traced:
- `agent.run` - Root span
- `model.step` - Each LLM call
- `tool.<name>` - Each tool execution
- `sandbox.validate_patch` - Patch validation
- `approval.wait` - User approval gates

View at: http://localhost:6006/projects/

## Usage

```bash
# Start Phoenix
docker-compose up -d

# Build sandbox image
docker build -t smolagent-sandbox:latest -f docker/Dockerfile.sandbox .

# Run agent
python -m agent_runtime.run "Find all TODO comments in Python files"
```

## Tracing Examples

### Successful Patch
```
agent.run
├─ model.step (plan)
├─ tool.propose_patch
│  └─ approval.wait (user approved)
├─ model.step (apply)
└─ tool.apply_patch
   └─ sandbox.validate_patch (valid=true)
```

### Failed Patch with Recovery
```
agent.run
├─ tool.read_file (error: FILE_NOT_FOUND)
│  └─ attributes: policy.suggested_next_tool=list_files
├─ model.step (follows hint)
└─ tool.list_files (finds file)
```
```

---

## Summary of High-Leverage Changes

### 1. InstrumentedTool Wrapper ✅
- **Single wrapper** for all tools
- Validates, traces, truncates, normalizes, records
- No custom loop needed

### 2. Approval Enforcement ✅
- `ApprovalStore.is_approved()` checked inside `apply_patch`
- Returns `APPROVAL_REQUIRED` error if not approved
- Phoenix spans show `blocked.approval_required`

### 3. Recovery Hints (Not Auto-Retry) ✅
- Errors include `recovery_suggestion` field
- Model can choose to follow or ignore
- Phoenix traces error → suggestion → action

### 4. Repo-Mounted Sandbox ✅
- Docker mounts repo at `/workspace`
- `git apply --check` actually works
- Phoenix spans for all sandbox ops

### 5. Phoenix-First Tracing ✅
- agent.run → model.step → tool.<name> → sandbox/approval
- Attributes optimized for debugging
- "Claude Code-level" observability

This architecture **maximizes leverage** by keeping smolagents' proven loop and instrumenting at the tool boundary. No custom step loop needed!