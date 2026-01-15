"""
Sandbox for validating patches before applying to repo.

NOTE: This is a simplified version that uses git apply --check
without Docker. Full Docker sandbox can be added later.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Tuple
from opentelemetry import trace


tracer = trace.get_tracer(__name__)


class SimpleSandbox:
    """
    Simple sandbox that validates patches using git apply --check.
    
    This is a lightweight alternative to Docker for basic patch validation.
    """
    
    def __init__(self, repo_root: str, enable_phoenix: bool = False):
        """
        Args:
            repo_root: Path to git repository
            enable_phoenix: Whether to create Phoenix spans
        """
        self.repo_root = Path(repo_root)
        self.enable_phoenix = enable_phoenix
    
    def validate_patch(self, diff: str) -> Tuple[bool, str]:
        """
        Validate that a patch can be applied cleanly.
        
        Args:
            diff: Unified diff content
            
        Returns:
            (is_valid, message) tuple
        """
        if self.enable_phoenix:
            with tracer.start_as_current_span("sandbox.validate_patch") as span:
                span.set_attribute("sandbox.type", "simple")
                span.set_attribute("patch.size", len(diff))
                
                result = self._do_validate(diff)
                
                span.set_attribute("validation.ok", result[0])
                if not result[0]:
                    span.set_attribute("validation.error", result[1][:200])
                
                return result
        else:
            return self._do_validate(diff)
    
    def _do_validate(self, diff: str) -> Tuple[bool, str]:
        """Perform actual validation."""
        # Write diff to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.diff', delete=False) as f:
            f.write(diff)
            temp_path = f.name
        
        try:
            # Use git apply --check to validate
            proc = subprocess.run(
                ["git", "apply", "--check", temp_path],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            
            if proc.returncode == 0:
                return (True, "Patch applies cleanly")
            else:
                return (False, f"Patch does not apply: {proc.stderr}")
        
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


# Alias for compatibility with plan
DockerSandbox = SimpleSandbox
