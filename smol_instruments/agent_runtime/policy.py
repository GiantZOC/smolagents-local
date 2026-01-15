"""
Recovery hint generator and command policy.

Recovery hints are suggestions, not automatic retries.
Command policy enforces safety without relying on prompts.
"""

from typing import Dict, Any, Optional
from enum import Enum
import re


# ============================================================================
# Command Policy (NEW - enforces safety in Python, not prompts)
# ============================================================================

class CommandAction(Enum):
    """Classification for command execution."""
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class CommandPolicy:
    """
    Policy for command execution enforced in Python.
    
    Classifies commands as:
    - ALLOW: Execute without approval (safe, read-only)
    - REQUIRE_APPROVAL: Pause for user approval (risky)
    - DENY: Block outright (dangerous)
    """
    
    # Commands that are always safe (read-only, local)
    SAFE_PREFIXES = [
        "pytest",
        "python -m pytest",
        "npm test",
        "pnpm test",
        "yarn test",
        "cargo test",
        "go test",
        "rg ",
        "grep ",
        "find ",
        "ls",
        "cat ",
        "head ",
        "tail ",
        "git status",
        "git diff",
        "git log",
        "git show",
        "which ",
        "whereis ",
    ]
    
    # Commands that require approval (mutating, but not destructive)
    RISKY_PREFIXES = [
        "pip install",
        "npm install",
        "pnpm install",
        "yarn install",
        "cargo build",
        "make",
        "git push",
        "git commit",
        "git pull",
        "docker build",
        "docker run",
    ]
    
    # Commands that are always denied (destructive, dangerous)
    # Some are simple strings, some are regex patterns
    DANGEROUS_PATTERNS = [
        "rm -rf",
        "rm -fr",
        "dd if=",
        "mkfs",
        ":(){ :|:& };:",  # Fork bomb
        "> /dev/",
        r"curl\s+.*\|\s*(sh|bash)",  # curl ... | sh/bash (regex)
        r"wget\s+.*\|\s*(sh|bash)",  # wget ... | sh/bash (regex)
        "chmod 777",
        "chown -R",
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
        
        # Check dangerous patterns first (supports both literal strings and regex)
        for pattern in cls.DANGEROUS_PATTERNS:
            # Try as regex first
            try:
                if re.search(pattern.lower(), cmd_lower):
                    return CommandAction.DENY
            except re.error:
                # If not valid regex, treat as literal string
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


# ============================================================================
# Recovery Hint Generator
# ============================================================================

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
            "message": "Waiting for user approval.",
            "no_retry": True
        },
        
        "COMMAND_DENIED": lambda ctx: {
            "message": f"Command blocked by safety policy: {ctx.get('message')}",
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
