"""Tests for validation helpers."""

import pytest
from agent_runtime.tools.validation import (
    validate_path,
    validate_line_range,
    truncate_output,
    ValidationError
)


class TestValidatePath:
    """Test path validation."""
    
    def test_valid_relative_path(self):
        """Valid relative paths should pass."""
        assert validate_path("src/main.py") == "src/main.py"
        assert validate_path("README.md") == "README.md"
        assert validate_path("tests/test_foo.py") == "tests/test_foo.py"
    
    def test_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        with pytest.raises(ValidationError, match="Path traversal"):
            validate_path("../etc/passwd")
        
        with pytest.raises(ValidationError, match="Path traversal"):
            validate_path("foo/../../bar")
    
    def test_absolute_path_blocked_by_default(self):
        """Absolute paths should be blocked by default."""
        with pytest.raises(ValidationError, match="Absolute paths not allowed"):
            validate_path("/etc/passwd")
        
        with pytest.raises(ValidationError, match="Absolute paths not allowed"):
            validate_path("/home/user/file.txt")
    
    def test_absolute_path_allowed_when_enabled(self):
        """Absolute paths should be allowed when enabled."""
        path = validate_path("/home/user/file.txt", allow_absolute=True)
        assert path == "/home/user/file.txt"
    
    def test_suspicious_characters_blocked(self):
        """Paths with shell metacharacters should be blocked."""
        suspicious_chars = ["|", ";", "&", "$", "`"]
        
        for char in suspicious_chars:
            with pytest.raises(ValidationError, match="suspicious characters"):
                validate_path(f"file{char}name.txt")
    
    def test_empty_path_blocked(self):
        """Empty paths should be blocked."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_path("")
        
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_path("   ")
    
    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace should be trimmed."""
        assert validate_path("  src/main.py  ") == "src/main.py"


class TestValidateLineRange:
    """Test line range validation."""
    
    def test_valid_range(self):
        """Valid line ranges should pass."""
        assert validate_line_range(1, 10) == (1, 10)
        assert validate_line_range(5, 100) == (5, 100)
        assert validate_line_range(1, 1) == (1, 1)
    
    def test_start_less_than_one(self):
        """Start line < 1 should fail."""
        with pytest.raises(ValidationError, match="Start line must be >= 1"):
            validate_line_range(0, 10)
        
        with pytest.raises(ValidationError, match="Start line must be >= 1"):
            validate_line_range(-5, 10)
    
    def test_end_before_start(self):
        """End line before start should fail."""
        with pytest.raises(ValidationError, match="must be >= start line"):
            validate_line_range(10, 5)
    
    def test_range_too_large(self):
        """Range exceeding max should fail."""
        with pytest.raises(ValidationError, match="Line range too large"):
            validate_line_range(1, 1001, max_range=1000)
        
        with pytest.raises(ValidationError, match="Line range too large"):
            validate_line_range(5, 1005, max_range=1000)
    
    def test_custom_max_range(self):
        """Custom max_range should be respected."""
        # Should pass
        assert validate_line_range(1, 50, max_range=50) == (1, 50)
        
        # Should fail
        with pytest.raises(ValidationError):
            validate_line_range(1, 51, max_range=50)


class TestTruncateOutput:
    """Test output truncation."""
    
    def test_no_truncation_needed(self):
        """Short text should not be truncated."""
        text = "Hello, world!"
        result, was_truncated = truncate_output(text)
        
        assert result == text
        assert was_truncated is False
    
    def test_empty_text(self):
        """Empty text should return empty."""
        result, was_truncated = truncate_output("")
        assert result == ""
        assert was_truncated is False
    
    def test_truncate_by_lines(self):
        """Text exceeding max_lines should be truncated."""
        lines = ["line " + str(i) for i in range(300)]
        text = "\n".join(lines)
        
        result, was_truncated = truncate_output(text, max_lines=200)
        
        assert was_truncated is True
        assert "truncated: 100 more lines" in result
        assert result.count("\n") < 210  # 200 lines + truncation message
    
    def test_truncate_by_chars(self):
        """Text exceeding max_chars should be truncated."""
        text = "x" * 10000
        
        result, was_truncated = truncate_output(text, max_chars=5000)
        
        assert was_truncated is True
        assert len(result) < 5100  # Some buffer for truncation message
        assert "truncated:" in result
    
    def test_truncate_both_lines_and_chars(self):
        """Truncation should apply both limits."""
        # Create text with many lines AND many chars
        lines = ["x" * 50 for _ in range(300)]
        text = "\n".join(lines)
        
        result, was_truncated = truncate_output(text, max_chars=3000, max_lines=150)
        
        assert was_truncated is True
        assert "truncated" in result
    
    def test_custom_limits(self):
        """Custom limits should be respected."""
        text = "x" * 100
        
        # Should not truncate
        result, was_truncated = truncate_output(text, max_chars=200)
        assert was_truncated is False
        
        # Should truncate
        result, was_truncated = truncate_output(text, max_chars=50)
        assert was_truncated is True
    
    def test_returns_tuple(self):
        """Function must return (str, bool) tuple."""
        result = truncate_output("test")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], bool)
