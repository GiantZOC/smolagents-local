# Critical Implementation Fixes
## Issues to address before implementing the plan

---

## 1. InstrumentedTool Metadata Mutation (HIGH PRIORITY)

### Problem
Currently setting instance attributes after initialization may break Tool base class assumptions:
```python
self.name = tool.name  # BAD - may conflict with class attributes
self.inputs = tool.inputs  # BAD - shared mutation risk
```

### Fix
```python
class InstrumentedTool(Tool):
    """Wrapper that instruments any Tool."""
    
    # Class-level attributes (Tool expects these)
    name = ""
    description = ""
    inputs = {}
    output_type = "any"
    
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
        
        # Copy tool metadata to class-level attributes (avoid mutation)
        # Set at instance level, not class level
        object.__setattr__(self, 'name', tool.name)
        object.__setattr__(self, 'description', tool.description)
        object.__setattr__(self, 'output_type', tool.output_type)
        
        # DEEP COPY inputs to avoid shared mutation
        import copy
        object.__setattr__(self, 'inputs', copy.deepcopy(tool.inputs))
```

**Why this matters**: Tool schemas may be read once at agent init. Mutation after initialization causes silent failures.

---

## 2. Truncation Flag is Misleading (HIGH PRIORITY)

### Problem
Current code sets `truncated=True` whenever certain keys exist, even if nothing was truncated:
```python
if any(key in result for key in ["lines", "text", "stdout_tail"]):
    result["truncated"] = True  # WRONG - may not be truncated!
```

This poisons traces and debugging.

### Fix
```python
# agent_runtime/tools/validation.py

def truncate_output(text: str, max_chars: int = 5000, max_lines: int = 200) -> tuple[str, bool]:
    """
    Truncate text output to prevent context overflow.
    
    Args:
        text: Text to truncate
        max_chars: Maximum characters
        max_lines: Maximum lines
        
    Returns:
        (truncated_text, was_truncated) tuple
    """
    if not text:
        return ("", False)
    
    original_len = len(text)
    lines = text.splitlines()
    original_line_count = len(lines)
    was_truncated = False
    
    # Truncate by lines first
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = "\n".join(lines)
        truncated += f"\n\n... (truncated: {original_line_count - max_lines} more lines)"
        text = truncated
        was_truncated = True
    
    # Then truncate by chars
    if len(text) > max_chars:
        text = text[:max_chars]
        text += f"\n\n... (truncated: {original_len - max_chars} more characters)"
        was_truncated = True
    
    return (text, was_truncated)
```

Update InstrumentedTool:
```python
def _truncate_result(self, result: Any) -> Any:
    """Truncate large outputs."""
    if isinstance(result, dict):
        # Track if anything was actually truncated
        any_truncated = False
        
        # Truncate string values
        for key in ["lines", "text", "stdout_tail", "stderr_tail", "diff"]:
            if key in result and isinstance(result[key], str):
                truncated_text, was_truncated = truncate_output(
                    result[key], max_chars=3000, max_lines=150
                )
                result[key] = truncated_text
                any_truncated = any_truncated or was_truncated
        
        # Only set flag if something was actually truncated
        if any_truncated:
            result["truncated"] = True
    
    # ... rest of truncation logic
    
    return result
```

---

## 3. Command Validation Needs Policy (MEDIUM PRIORITY)

### Problem
Current validation is too generic:
- `pytest -q` should run without approval
- `pip install` might require approval
- `rm -rf` should be blocked outright

### Fix
```python
# agent_runtime/policy.py

from enum import Enum
from typing import Optional

class CommandAction(Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class CommandPolicy:
    """
    Policy for command execution.
    
    Classifies commands as:
    - ALLOW: Execute without approval
    - REQUIRE_APPROVAL: Pause for user approval
    - DENY: Block outright
    """
    
    # Commands that are always safe
    SAFE_PREFIXES = [
        "pytest",
        "python -m pytest",
        "npm test",
        "pnpm test",
        "cargo test",
        "go test",
        "rg ",
        "grep ",
        "find ",
        "ls",
        "cat",
        "head",
        "tail",
        "git status",
        "git diff",
        "git log",
    ]
    
    # Commands that require approval
    RISKY_PREFIXES = [
        "pip install",
        "npm install",
        "pnpm install",
        "cargo build",
        "make",
        "git push",
        "git commit",
    ]
    
    # Commands that are always denied
    DANGEROUS_PATTERNS = [
        "rm -rf",
        "rm -fr",
        "dd if=",
        "mkfs",
        ":(){ :|:& };:",  # Fork bomb
        "> /dev/",
        "curl | sh",
        "wget | sh",
    ]
    
    @classmethod
    def classify_command(cls, cmd: str) -> CommandAction:
        """
        Classify command into ALLOW / REQUIRE_APPROVAL / DENY.
        
        Args:
            cmd: Command to classify
            
        Returns:
            CommandAction enum
        """
        cmd_lower = cmd.lower().strip()
        
        # Check dangerous patterns first
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.lower() in cmd_lower:
                return CommandAction.DENY
        
        # Check safe prefixes
        for prefix in cls.SAFE_PREFIXES:
            if cmd_lower.startswith(prefix.lower()):
                return CommandAction.ALLOW
        
        # Check risky prefixes
        for prefix in cls.RISKY_PREFIXES:
            if cmd_lower.startswith(prefix.lower()):
                return CommandAction.REQUIRE_APPROVAL
        
        # Default: require approval for unknown commands
        return CommandAction.REQUIRE_APPROVAL
    
    @classmethod
    def validate_command(cls, cmd: str) -> Optional[str]:
        """
        Validate command and return error message if denied.
        
        Args:
            cmd: Command to validate
            
        Returns:
            Error message if denied, None if allowed/requires approval
        """
        action = cls.classify_command(cmd)
        
        if action == CommandAction.DENY:
            return f"Command is blocked by policy (dangerous operation): {cmd}"
        
        return None
```

Update RunCmdTool:
```python
# agent_runtime/tools/shell.py

from agent_runtime.policy import CommandPolicy, CommandAction
from agent_runtime.approval import get_approval_store

class RunCmdTool(Tool):
    name = "run_cmd"
    description = "Run a shell command in repo root. Some commands require approval."
    inputs = {
        "cmd": {"type": "string", "description": "shell command to run"},
        "timeout": {"type": "integer", "description": "timeout seconds"},
    }
    output_type = "object"

    def forward(self, cmd: str, timeout: int = 60):
        # Validate command
        error = CommandPolicy.validate_command(cmd)
        if error:
            return {
                "error": "COMMAND_DENIED",
                "cmd": cmd,
                "message": error
            }
        
        # Check if approval required
        action = CommandPolicy.classify_command(cmd)
        
        if action == CommandAction.REQUIRE_APPROVAL:
            # Check if approved (similar to patch approval)
            approval_store = get_approval_store()
            
            # Create a simple approval proposal for commands
            cmd_id = f"cmd_{hashlib.sha256(cmd.encode()).hexdigest()[:10]}"
            
            if not approval_store.is_command_approved(cmd_id):
                return {
                    "error": "APPROVAL_REQUIRED",
                    "cmd": cmd,
                    "cmd_id": cmd_id,
                    "message": "This command requires user approval before execution.",
                    "blocked.approval_required": True,
                    "approval.kind": "command"
                }
        
        # Execute command
        root = RepoInfoTool().forward()["root"]
        proc = subprocess.Popen(
            cmd, 
            cwd=root, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {
                "error": "CMD_TIMEOUT",
                "cmd": cmd,
                "timeout": timeout
            }
        
        return {
            "cmd": cmd,
            "exit": proc.returncode,
            "stdout_tail": (out or "")[-5000:],
            "stderr_tail": (err or "")[-5000:],
        }
```

---

## 4. ProposePatchTool Fights Truncation (HIGH PRIORITY)

### Problem
Read tools deliberately truncate, but `propose_patch` requires full `original_content` + `new_content`.

This forces the model to:
- Guess original content
- Reconstruct full new content
- Create patches that don't apply

### Fix: Add Unified Diff Tool

```python
# agent_runtime/tools/patch.py

class ProposePatchUnifiedTool(Tool):
    name = "propose_patch_unified"
    description = """Create a patch proposal from a unified diff.
    
    Use this when you have read portions of a file and want to propose changes.
    Provide the unified diff directly (starting with --- a/path, +++ b/path).
    
    This is preferred over propose_patch when working with truncated file content.
    
    Returns: {patch_id, intent, approved, feedback}"""
    
    inputs = {
        "intent": {"type": "string", "description": "short description of what the patch does"},
        "unified_diff": {"type": "string", "description": "unified diff content (--- a/... +++ b/... @@ ...)"},
    }
    output_type = "object"
    
    def forward(self, intent: str, unified_diff: str):
        # Generate patch ID
        patch_id = f"patch_{uuid.uuid4().hex[:10]}"
        
        # Extract file path from diff
        # Format: --- a/path/to/file.py
        lines = unified_diff.splitlines()
        file_path = None
        for line in lines:
            if line.startswith("--- a/"):
                file_path = line[6:]
                break
            elif line.startswith("--- "):
                file_path = line[4:]
                break
        
        if not file_path:
            return {
                "error": "INVALID_DIFF",
                "message": "Could not extract file path from diff. Expected '--- a/path' format."
            }
        
        # Create proposal
        proposal = PatchProposal(
            patch_id=patch_id,
            base_ref=file_path,
            diff=unified_diff,
            summary=intent
        )
        
        # Store and request approval
        approval_store = get_approval_store()
        approval_store.add_proposal(proposal)
        approval = approval_store.request_approval(patch_id)
        
        return {
            "patch_id": patch_id,
            "intent": intent,
            "file_path": file_path,
            "diff_preview": unified_diff[:500] + ("..." if len(unified_diff) > 500 else ""),
            "approved": approval.approved,
            "feedback": approval.feedback,
            "message": "Patch created and approval requested." if approval.approved 
                      else f"Patch rejected. Feedback: {approval.feedback or 'None'}"
        }
```

Update system prompt to encourage using `propose_patch_unified`:
```python
DEFAULT_SYSTEM_PROMPT = r"""
...

PATCH WORKFLOW:
1. Read file portions with read_file or read_file_snippet
2. Create unified diff based on what you read
3. Call propose_patch_unified with the diff
4. If approved, call apply_patch with the patch_id

PREFER propose_patch_unified over propose_patch when working with large files.

...
"""
```

---

## 5. Approval Auto-Request in propose_patch (MEDIUM PRIORITY)

### Problem
Currently `propose_patch` immediately requests approval, which:
- Creates repeated interruptions
- Makes the tool hard to test/batch
- Couples proposal creation to approval flow

### Fix: Separate Concerns

**Option A: Keep current behavior but mark it clearly**
```python
def forward(self, intent: str, file_path: str, original_content: str, new_content: str):
    # ... create proposal ...
    
    # Store in approval store
    approval_store = get_approval_store()
    approval_store.add_proposal(proposal)
    
    # AUTO-REQUEST approval (mark this clearly in span)
    with tracer.start_as_current_span("approval.wait") as span:
        span.set_attribute("approval.requested_by", "propose_patch")
        span.set_attribute("approval.auto_requested", True)
        
        approval = approval_store.request_approval(patch_id)
    
    # ... return result ...
```

**Option B: Separate proposal from approval (recommended for flexibility)**
```python
class ProposePatchTool(Tool):
    # ... same as before but DON'T request approval ...
    
    def forward(self, intent: str, file_path: str, original_content: str, new_content: str):
        # ... create proposal ...
        
        approval_store = get_approval_store()
        approval_store.add_proposal(proposal)
        
        # Just store - don't request approval yet
        return {
            "patch_id": patch_id,
            "intent": intent,
            "file_path": file_path,
            "diff_preview": diff_text[:500],
            "status": "proposed",
            "message": f"Patch {patch_id} created. Use request_approval or show_patch to review."
        }


class RequestPatchApprovalTool(Tool):
    name = "request_patch_approval"
    description = "Request user approval for a proposed patch."
    inputs = {
        "patch_id": {"type": "string", "description": "patch id to request approval for"}
    }
    output_type = "object"
    
    def forward(self, patch_id: str):
        approval_store = get_approval_store()
        
        if patch_id not in approval_store.proposals:
            return {"error": "PATCH_NOT_FOUND", "patch_id": patch_id}
        
        approval = approval_store.request_approval(patch_id)
        
        return {
            "patch_id": patch_id,
            "approved": approval.approved,
            "feedback": approval.feedback
        }
```

For CLI-first workflow, **Option A is workable**. Just add the span attribute to trace clearly.

---

## 6. Phoenix Setup Missing Global Provider (CRITICAL)

### Problem
```python
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(...))
# MISSING: trace.set_tracer_provider(tracer_provider)
```

Without setting global provider, spans may go nowhere.

### Fix
```python
# agent_runtime/instrumentation.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.smolagents import SmolagentsInstrumentor


def setup_phoenix_telemetry(endpoint: str = "http://localhost:6006/v1/traces",
                            use_batch: bool = True):
    """
    Setup Phoenix telemetry for smolagents.
    
    Args:
        endpoint: Phoenix OTLP endpoint
        use_batch: Whether to use BatchSpanProcessor (recommended for production)
    """
    # Create provider
    tracer_provider = TracerProvider()
    
    # Choose processor
    exporter = OTLPSpanExporter(endpoint)
    if use_batch:
        processor = BatchSpanProcessor(exporter)
    else:
        processor = SimpleSpanProcessor(exporter)
    
    tracer_provider.add_span_processor(processor)
    
    # SET GLOBAL PROVIDER (critical!)
    trace.set_tracer_provider(tracer_provider)
    
    # Instrument smolagents
    SmolagentsInstrumentor().instrument(tracer_provider=tracer_provider)
    
    print(f"✓ Phoenix telemetry enabled: {endpoint}")
    print(f"  Processor: {'Batch' if use_batch else 'Simple'}")
```

---

## 7. Instrumentation Duplication Risk (HIGH PRIORITY)

### Problem
Both `SmolagentsInstrumentor()` and `InstrumentedTool` create spans. Risk of duplicates.

### Investigation Steps
```python
# Test with minimal agent
agent, state = build_agent(...)
result = agent.run("simple test task")

# Check Phoenix for duplicate spans:
# - tool.search (from SmolagentsInstrumentor)
# - tool.search (from InstrumentedTool)
```

### Fix Options

**Option A: Keep both but rename wrapper spans**
```python
class InstrumentedTool(Tool):
    def forward(self, **kwargs):
        # Use different span name to avoid collision
        with tracer.start_as_current_span(f"tool_wrapped.{self.name}") as span:
            # ... instrumentation ...
            result = self.tool.forward(**kwargs)
```

**Option B: Disable smolagents tool instrumentation, keep only wrapper**
```python
def setup_phoenix_telemetry(...):
    # Instrument only agent.run + model.step, not tools
    SmolagentsInstrumentor().instrument(
        tracer_provider=tracer_provider,
        instrument_tools=False  # If this option exists
    )
```

**Option C: Use smolagents instrumentation, add attributes in callbacks**
```python
# Don't wrap tools; instead use smolagents callbacks to add attributes
def tool_callback(tool_name, args, result):
    span = trace.get_current_span()
    span.set_attribute("tool.validated", True)
    # ... add other attributes
```

**Recommendation**: Start with **Option A** (rename wrapper spans) for clarity, then check for duplicates.

---

## Minor but High-Value Adjustments

### A. Format Guard for JSON Outputs

```python
# agent_runtime/run.py or as a callback

def check_json_format(memory_step):
    """Step callback to check if model output is valid JSON."""
    if isinstance(memory_step, ActionStep):
        # Check if response is valid
        if hasattr(memory_step, 'tool_calls') and not memory_step.tool_calls:
            # Model may have output invalid JSON
            span = trace.get_current_span()
            span.set_attribute("response.json_valid", False)
            
            # Could trigger retry here if smolagents supports it
```

If smolagents doesn't handle this natively, you may need a retry wrapper.

### B. Move Step Counting to State

```python
# agent_runtime/state.py

@dataclass
class AgentState:
    task: str
    max_steps: int = 25  # Make this configurable
    steps: List[StepRecord] = field(default_factory=list)
    # ... rest ...
    
    @property
    def steps_remaining(self) -> int:
        return self.max_steps - len(self.steps)
    
    def summary(self) -> str:
        return f"""Task: {self.task}
Steps taken: {len(self.steps)}/{self.max_steps}
Steps remaining: {self.steps_remaining}
..."""
```

### C. Add Read-Only Git Tools

```python
# agent_runtime/tools/git.py

from smolagents import Tool
import subprocess
from agent_runtime.tools.repo import RepoInfoTool


class GitStatusTool(Tool):
    name = "git_status"
    description = "Get git status (modified/staged/untracked files)."
    inputs = {}
    output_type = "object"
    
    def forward(self):
        root = RepoInfoTool().forward()["root"]
        
        # Run git status --porcelain
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True
        )
        
        if proc.returncode != 0:
            return {"error": "GIT_FAILED", "stderr": proc.stderr}
        
        # Parse porcelain output
        modified = []
        staged = []
        untracked = []
        
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            
            status = line[:2]
            path = line[3:]
            
            if status[0] in ['M', 'A', 'D']:
                staged.append(path)
            if status[1] in ['M', 'D']:
                modified.append(path)
            if status == '??':
                untracked.append(path)
        
        return {
            "modified": modified,
            "staged": staged,
            "untracked": untracked,
            "total_changes": len(modified) + len(staged) + len(untracked)
        }


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Get git diff (uncommitted changes). Optionally for specific file."
    inputs = {
        "file_path": {"type": "string", "description": "optional file path to diff (empty for all)"},
        "staged": {"type": "boolean", "description": "whether to show staged changes (default: False)"}
    }
    output_type = "object"
    
    def forward(self, file_path: str = "", staged: bool = False):
        root = RepoInfoTool().forward()["root"]
        
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")
        if file_path:
            cmd.append(file_path)
        
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True
        )
        
        if proc.returncode != 0:
            return {"error": "GIT_FAILED", "stderr": proc.stderr}
        
        diff = proc.stdout
        
        # Truncate if needed
        from agent_runtime.tools.validation import truncate_output
        diff_truncated, was_truncated = truncate_output(diff, max_chars=5000)
        
        return {
            "diff": diff_truncated,
            "truncated": was_truncated,
            "file_path": file_path or "all files",
            "staged": staged
        }


class GitLogTool(Tool):
    name = "git_log"
    description = "Get recent git commit history."
    inputs = {
        "limit": {"type": "integer", "description": "number of commits to show (default: 10)"},
        "file_path": {"type": "string", "description": "optional file path to show history for"}
    }
    output_type = "object"
    
    def forward(self, limit: int = 10, file_path: str = ""):
        root = RepoInfoTool().forward()["root"]
        
        cmd = ["git", "log", f"-{limit}", "--oneline"]
        if file_path:
            cmd.append(file_path)
        
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True
        )
        
        if proc.returncode != 0:
            return {"error": "GIT_FAILED", "stderr": proc.stderr}
        
        commits = []
        for line in proc.stdout.splitlines():
            if line.strip():
                parts = line.split(" ", 1)
                commits.append({
                    "hash": parts[0],
                    "message": parts[1] if len(parts) > 1 else ""
                })
        
        return {
            "commits": commits,
            "count": len(commits),
            "file_path": file_path or "all files"
        }
```

Add to agent build:
```python
from agent_runtime.tools.git import GitStatusTool, GitDiffTool, GitLogTool

raw_tools = [
    # ... existing tools ...
    GitStatusTool(),
    GitDiffTool(),
    GitLogTool(),
]
```

Update system prompt:
```python
TOOLS: repo_info, list_files, rg_search, read_file, read_file_snippet, 
       propose_patch_unified, show_patch, apply_patch, 
       git_status, git_diff, git_log,
       run_cmd, run_tests
```

---

## Summary of Fixes

### Critical (Must Fix Before Implementation)
1. ✅ InstrumentedTool metadata mutation → Use `object.__setattr__` + deep copy
2. ✅ Truncation flag misleading → Return `(text, bool)` from `truncate_output()`
3. ✅ Phoenix global provider → Call `trace.set_tracer_provider()`

### High Priority (Strongly Recommended)
4. ✅ Command policy → Add `CommandPolicy` with ALLOW/REQUIRE_APPROVAL/DENY
5. ✅ Patch tool fights truncation → Add `propose_patch_unified` tool
6. ✅ Instrumentation duplication → Rename wrapper spans or disable tool instrumentation

### Medium Priority (Quality of Life)
7. ✅ Approval auto-request → Add span attribute `approval.requested_by`
8. ✅ Format guard → Add JSON validation callback
9. ✅ Step counting → Move to AgentState with `max_steps` config
10. ✅ Git tools → Add `git_status`, `git_diff`, `git_log`

These fixes will make the implementation much more robust and production-ready.
