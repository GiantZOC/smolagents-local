"""
Shell command execution tools with CommandPolicy enforcement.

FIXED: Commands are classified as ALLOW/REQUIRE_APPROVAL/DENY in Python.
"""

import subprocess
import hashlib
from smolagents import Tool
from agent_runtime.tools.repo import RepoInfoTool
from agent_runtime.policy import CommandPolicy, CommandAction
from agent_runtime.approval import get_approval_store


class RunCmdTool(Tool):
    name = "run_cmd"
    description = """Run a shell command in repo root.
    
    Safe commands (pytest, git status, etc.) run immediately.
    Risky commands (pip install, etc.) require user approval.
    Dangerous commands (rm -rf, etc.) are blocked.
    
    Returns: {cmd, exit, stdout_tail, stderr_tail}"""
    
    inputs = {
        "cmd": {"type": "string", "description": "shell command to run"},
        "timeout": {"type": "integer", "description": "timeout seconds (default: 60)", "nullable": True},
    }
    output_type = "object"

    def forward(self, cmd: str, timeout: int = 60):
        # Validate command (checks for DENY)
        # Note: validate_command is already called in InstrumentedTool._validate_inputs
        # This is a defense-in-depth check
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
            # Check approval store and request approval if needed
            approval_store = get_approval_store()
            cmd_id = f"cmd_{hashlib.sha256(cmd.encode()).hexdigest()[:10]}"
            
            if not approval_store.is_approved(cmd_id):
                # Request approval from user (blocks until user responds)
                approval = approval_store.request_approval(cmd_id, cmd=cmd)
                
                if not approval.approved:
                    return {
                        "error": "APPROVAL_DENIED",
                        "cmd": cmd,
                        "cmd_id": cmd_id,
                        "message": "Command was not approved by user.",
                        "feedback": approval.feedback,
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
                "timeout": timeout,
                "message": f"Command timed out after {timeout}s"
            }
        
        return {
            "cmd": cmd,
            "exit": proc.returncode,
            "stdout_tail": (out or "")[-5000:],
            "stderr_tail": (err or "")[-5000:],
        }


class RunTestsTool(Tool):
    name = "run_tests"
    description = "Run tests with a provided command (defaults to pytest -q)."
    inputs = {
        "test_cmd": {"type": "string", "description": "test command to run (e.g. pytest -q, npm test)", "nullable": True},
        "timeout": {"type": "integer", "description": "timeout seconds (default: 300)", "nullable": True},
    }
    output_type = "object"

    def forward(self, test_cmd: str = "pytest -q", timeout: int = 300):
        # Test commands are usually ALLOW, so this typically runs immediately
        return RunCmdTool().forward(cmd=test_cmd, timeout=timeout)
