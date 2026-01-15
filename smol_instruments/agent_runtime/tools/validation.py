"""Input validation and output truncation helpers.

FIXED: Returns tuples to track actual truncation.
"""

from pathlib import Path
from typing import Optional, Tuple

from agent_runtime.config import Config


class ValidationError(Exception):
    """Raised when tool input validation fails."""
    pass


def validate_path(path: str, allow_absolute: bool = False) -> str:
    """
    Validate file path for safety.
    
    Args:
        path: Path to validate
        allow_absolute: Whether to allow absolute paths
        
    Returns:
        Validated path string
        
    Raises:
        ValidationError: If path is invalid or unsafe
    """
    if not path or not path.strip():
        raise ValidationError("Path cannot be empty")
    
    path = path.strip()
    
    # Check for path traversal
    if ".." in path:
        raise ValidationError("Path traversal not allowed (..)")
    
    # Check for absolute paths if not allowed
    if not allow_absolute and Path(path).is_absolute():
        raise ValidationError("Absolute paths not allowed")
    
    # Check for suspicious patterns
    suspicious = ["|", ";", "&", "$", "`", "\n", "\r"]
    if any(char in path for char in suspicious):
        raise ValidationError("Path contains suspicious characters")
    
    return path


def validate_line_range(start: int, end: int, max_range: Optional[int] = None) -> Tuple[int, int]:
    """
    Validate line range for file reading.
    
    Args:
        start: Start line (1-indexed)
        end: End line (1-indexed)
        max_range: Maximum allowed range (defaults to Config.VALIDATION_MAX_LINE_RANGE)
        
    Returns:
        (start, end) tuple
        
    Raises:
        ValidationError: If range is invalid
    """
    if max_range is None:
        max_range = Config.VALIDATION_MAX_LINE_RANGE
    
    if start < 1:
        raise ValidationError(f"Start line must be >= 1, got {start}")
    
    if end < start:
        raise ValidationError(f"End line ({end}) must be >= start line ({start})")
    
    if end - start + 1 > max_range:
        raise ValidationError(f"Line range too large: {end - start + 1} > {max_range}")
    
    return (start, end)


def truncate_output(text: str, max_chars: Optional[int] = None, max_lines: Optional[int] = None) -> Tuple[str, bool]:
    """
    Truncate text output to prevent context overflow.
    
    FIXED: Returns (text, was_truncated) tuple to track actual truncation.
    
    Args:
        text: Text to truncate
        max_chars: Maximum characters (defaults to Config.VALIDATION_MAX_CHARS)
        max_lines: Maximum lines (defaults to Config.VALIDATION_MAX_LINES)
        
    Returns:
        (truncated_text, was_truncated) tuple
    """
    if max_chars is None:
        max_chars = Config.VALIDATION_MAX_CHARS
    if max_lines is None:
        max_lines = Config.VALIDATION_MAX_LINES
    
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
