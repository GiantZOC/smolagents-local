"""File reading tools."""

from pathlib import Path
from smolagents import Tool
from agent_runtime.tools.repo import RepoInfoTool
from agent_runtime.tools.validation import truncate_output


class ReadFileTool(Tool):
    name = "read_file"
    description = """Read file content with optional line range.
    
    Args:
        path: Repo-relative file path
        start_line: Starting line (1-indexed, default: 1)
        end_line: Ending line (1-indexed, default: 200)
    
    Returns: {lines, total_lines, start, end}"""
    
    inputs = {
        "path": {"type": "string", "description": "repo-relative path to file"},
        "start_line": {"type": "integer", "description": "start line (1-indexed, default: 1)", "nullable": True},
        "end_line": {"type": "integer", "description": "end line (1-indexed, default: 200)", "nullable": True}
    }
    output_type = "object"
    
    def forward(self, path: str, start_line: int = 1, end_line: int = 200):
        """Read file content."""
        root = RepoInfoTool().forward()["root"]
        file_path = Path(root) / path
        
        # Check file exists
        if not file_path.exists():
            return {
                "error": "FILE_NOT_FOUND",
                "path": path,
                "message": f"File not found: {path}"
            }
        
        if not file_path.is_file():
            return {
                "error": "NOT_A_FILE",
                "path": path,
                "message": f"Path is not a file: {path}"
            }
        
        try:
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            total_lines = len(all_lines)
            
            # Validate range
            if start_line < 1:
                start_line = 1
            if end_line > total_lines:
                end_line = total_lines
            if start_line > end_line:
                return {
                    "error": "INVALID_LINE_RANGE",
                    "path": path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "total_lines": total_lines,
                    "message": f"Invalid range: {start_line}-{end_line} (file has {total_lines} lines)"
                }
            
            # Extract lines (convert to 0-indexed)
            selected_lines = all_lines[start_line - 1:end_line]
            content = "".join(selected_lines)
            
            # Truncate if needed
            truncated_content, was_truncated = truncate_output(content, max_chars=5000, max_lines=200)
            
            result = {
                "lines": truncated_content,
                "total_lines": total_lines,
                "start": start_line,
                "end": end_line,
                "path": path
            }
            
            if was_truncated:
                result["truncated"] = True
            
            return result
        
        except UnicodeDecodeError:
            return {
                "error": "BINARY_FILE",
                "path": path,
                "message": "File appears to be binary (not UTF-8 text)"
            }
        except Exception as e:
            return {
                "error": "READ_FAILED",
                "path": path,
                "message": str(e)
            }


class ReadFileSnippetTool(Tool):
    name = "read_file_snippet"
    description = """Read a specific snippet from a file by searching for a pattern.
    
    Useful when you know what code you're looking for but not the exact line numbers.
    
    Args:
        path: Repo-relative file path
        pattern: Text pattern to search for
        context_lines: Lines of context before/after match (default: 5)
    
    Returns: {lines, match_line, start, end}"""
    
    inputs = {
        "path": {"type": "string", "description": "repo-relative path to file"},
        "pattern": {"type": "string", "description": "text pattern to find"},
        "context_lines": {"type": "integer", "description": "context lines before/after (default: 5)", "nullable": True}
    }
    output_type = "object"
    
    def forward(self, path: str, pattern: str, context_lines: int = 5):
        """Read snippet around a pattern match."""
        root = RepoInfoTool().forward()["root"]
        file_path = Path(root) / path
        
        # Check file exists
        if not file_path.exists():
            return {
                "error": "FILE_NOT_FOUND",
                "path": path,
                "message": f"File not found: {path}"
            }
        
        try:
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            # Find pattern
            match_index = None
            for i, line in enumerate(all_lines):
                if pattern in line:
                    match_index = i
                    break
            
            if match_index is None:
                return {
                    "error": "NOT_FOUND_IN_FILE",
                    "path": path,
                    "pattern": pattern,
                    "message": f"Pattern not found in file: {pattern}"
                }
            
            # Calculate range
            total_lines = len(all_lines)
            start = max(0, match_index - context_lines)
            end = min(total_lines, match_index + context_lines + 1)
            
            # Extract snippet
            snippet_lines = all_lines[start:end]
            content = "".join(snippet_lines)
            
            # Truncate if needed
            truncated_content, was_truncated = truncate_output(content, max_chars=3000, max_lines=100)
            
            result = {
                "lines": truncated_content,
                "match_line": match_index + 1,  # 1-indexed for user
                "start": start + 1,
                "end": end,
                "total_lines": total_lines,
                "path": path,
                "pattern": pattern
            }
            
            if was_truncated:
                result["truncated"] = True
            
            return result
        
        except UnicodeDecodeError:
            return {
                "error": "BINARY_FILE",
                "path": path,
                "message": "File appears to be binary (not UTF-8 text)"
            }
        except Exception as e:
            return {
                "error": "READ_FAILED",
                "path": path,
                "message": str(e)
            }
