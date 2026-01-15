"""Tests for tools - determinism and error handling."""

import pytest
import tempfile
import os
from pathlib import Path

from agent_runtime.tools.repo import RepoInfoTool, ListFilesTool
from agent_runtime.tools.files import ReadFileTool, ReadFileSnippetTool
from agent_runtime.tools.git import GitStatusTool, GitDiffTool, GitLogTool
from agent_runtime.approval import ApprovalStore, Approval, set_approval_store


@pytest.fixture
def test_repo(tmp_path):
    """Create a temporary git repo for testing."""
    # Create temp repo
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    
    # Initialize git
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
    
    # Create test files
    (repo_dir / "README.md").write_text("# Test Repo\n")
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (repo_dir / "src" / "utils.py").write_text("def helper():\n    pass\n")
    
    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
    
    # Change to repo directory for tests
    original_cwd = os.getcwd()
    os.chdir(repo_dir)
    
    yield repo_dir
    
    # Restore original directory
    os.chdir(original_cwd)


@pytest.fixture
def approval_store():
    """Create approval store with auto-approve callback for testing."""
    auto_approve = lambda proposal: Approval(approved=True)
    store = ApprovalStore(approval_callback=auto_approve)
    set_approval_store(store)
    return store


class TestRepoInfoTool:
    """Test RepoInfoTool."""
    
    def test_finds_git_repo(self, test_repo):
        """Should find git repository root."""
        tool = RepoInfoTool()
        result = tool.forward()
        
        assert "root" in result
        assert "name" in result
        assert result["is_git"] is True
        assert result["name"] == "test_repo"
    
    def test_deterministic(self, test_repo):
        """Tool should return same result on multiple calls."""
        tool = RepoInfoTool()
        
        result1 = tool.forward()
        result2 = tool.forward()
        
        assert result1 == result2


class TestListFilesTool:
    """Test ListFilesTool."""
    
    def test_list_all_python_files(self, test_repo):
        """Should list all Python files."""
        tool = ListFilesTool()
        result = tool.forward(glob="**/*.py")
        
        assert "files" in result
        assert "count" in result
        assert result["count"] == 2
        assert "src/main.py" in result["files"]
        assert "src/utils.py" in result["files"]
    
    def test_list_markdown_files(self, test_repo):
        """Should list markdown files."""
        tool = ListFilesTool()
        result = tool.forward(glob="*.md")
        
        assert result["count"] == 1
        assert "README.md" in result["files"]
    
    def test_limit_results(self, test_repo):
        """Should respect limit parameter."""
        tool = ListFilesTool()
        result = tool.forward(glob="**/*", limit=1)
        
        assert result["count"] == 1
        assert result.get("truncated") is True
        assert "total_matches" in result
    
    def test_no_matches(self, test_repo):
        """Should handle no matches gracefully."""
        tool = ListFilesTool()
        result = tool.forward(glob="**/*.nonexistent")
        
        assert result["count"] == 0
        assert result["files"] == []
    
    def test_deterministic(self, test_repo):
        """Tool should return consistent results."""
        tool = ListFilesTool()
        
        result1 = tool.forward(glob="**/*.py")
        result2 = tool.forward(glob="**/*.py")
        
        assert result1["files"] == result2["files"]


class TestReadFileTool:
    """Test ReadFileTool."""
    
    def test_read_full_file(self, test_repo):
        """Should read full file content."""
        tool = ReadFileTool()
        result = tool.forward(path="README.md")
        
        assert "lines" in result
        assert "# Test Repo" in result["lines"]
        assert result["total_lines"] == 1
        assert result["path"] == "README.md"
    
    def test_read_with_line_range(self, test_repo):
        """Should read specific line range."""
        tool = ReadFileTool()
        result = tool.forward(path="src/main.py", start_line=1, end_line=1)
        
        assert "def main():" in result["lines"]
        assert result["start"] == 1
        assert result["end"] == 1
    
    def test_file_not_found(self, test_repo):
        """Should return error for non-existent file."""
        tool = ReadFileTool()
        result = tool.forward(path="nonexistent.txt")
        
        assert "error" in result
        assert result["error"] == "FILE_NOT_FOUND"
        assert "nonexistent.txt" in result["message"]
    
    def test_invalid_line_range(self, test_repo):
        """Should handle invalid line range."""
        tool = ReadFileTool()
        result = tool.forward(path="README.md", start_line=10, end_line=5)
        
        assert "error" in result
        assert result["error"] == "INVALID_LINE_RANGE"
    
    def test_range_beyond_file_end(self, test_repo):
        """Should auto-adjust range if beyond file end."""
        tool = ReadFileTool()
        result = tool.forward(path="README.md", start_line=1, end_line=1000)
        
        # Should succeed and adjust to actual file length
        assert "lines" in result
        assert result["end"] == 1  # Actual file length
    
    def test_deterministic(self, test_repo):
        """Tool should return consistent results."""
        tool = ReadFileTool()
        
        result1 = tool.forward(path="README.md")
        result2 = tool.forward(path="README.md")
        
        assert result1["lines"] == result2["lines"]


class TestReadFileSnippetTool:
    """Test ReadFileSnippetTool."""
    
    def test_find_pattern(self, test_repo):
        """Should find pattern and return snippet."""
        tool = ReadFileSnippetTool()
        result = tool.forward(path="src/main.py", pattern="def main")
        
        assert "lines" in result
        assert "def main" in result["lines"]
        assert result["match_line"] == 1
        assert result["pattern"] == "def main"
    
    def test_pattern_not_found(self, test_repo):
        """Should return error if pattern not found."""
        tool = ReadFileSnippetTool()
        result = tool.forward(path="src/main.py", pattern="nonexistent_function")
        
        assert "error" in result
        assert result["error"] == "NOT_FOUND_IN_FILE"
    
    def test_context_lines(self, test_repo):
        """Should include context lines around match."""
        tool = ReadFileSnippetTool()
        result = tool.forward(path="src/main.py", pattern="print", context_lines=1)
        
        assert "lines" in result
        assert "def main" in result["lines"]  # Context before
        assert "print" in result["lines"]  # Matched line
    
    def test_file_not_found(self, test_repo):
        """Should return error for non-existent file."""
        tool = ReadFileSnippetTool()
        result = tool.forward(path="nonexistent.py", pattern="test")
        
        assert "error" in result
        assert result["error"] == "FILE_NOT_FOUND"


class TestGitTools:
    """Test git tools."""
    
    def test_git_status_clean(self, test_repo):
        """Should show clean status."""
        tool = GitStatusTool()
        result = tool.forward()
        
        assert "modified" in result
        assert "staged" in result
        assert "untracked" in result
        assert result["total_changes"] == 0
    
    def test_git_status_with_changes(self, test_repo):
        """Should detect modified files."""
        # Modify a file
        (test_repo / "README.md").write_text("# Modified\n")
        
        tool = GitStatusTool()
        result = tool.forward()
        
        assert "README.md" in result["modified"]
        assert result["total_changes"] > 0
    
    def test_git_diff_no_changes(self, test_repo):
        """Should show empty diff for clean repo."""
        tool = GitDiffTool()
        result = tool.forward()
        
        assert "diff" in result
        assert result["diff"] == "" or len(result["diff"]) == 0
    
    def test_git_diff_with_changes(self, test_repo):
        """Should show diff for changes."""
        # Modify a file
        (test_repo / "README.md").write_text("# Modified\n")
        
        tool = GitDiffTool()
        result = tool.forward()
        
        assert "diff" in result
        assert len(result["diff"]) > 0
        assert "Modified" in result["diff"] or "Test Repo" in result["diff"]
    
    def test_git_log(self, test_repo):
        """Should show commit history."""
        tool = GitLogTool()
        result = tool.forward(limit=5)
        
        assert "commits" in result
        assert result["count"] >= 1
        assert len(result["commits"]) >= 1
        assert "Initial commit" in result["commits"][0]["message"]
    
    def test_git_tools_deterministic_on_clean_repo(self, test_repo):
        """Git tools should be deterministic on clean repo."""
        status_tool = GitStatusTool()
        diff_tool = GitDiffTool()
        
        status1 = status_tool.forward()
        status2 = status_tool.forward()
        
        diff1 = diff_tool.forward()
        diff2 = diff_tool.forward()
        
        assert status1 == status2
        assert diff1 == diff2


class TestToolErrorHandling:
    """Test error handling across all tools."""
    
    def test_tools_return_dicts(self, test_repo):
        """All tools should return dict results."""
        tools = [
            (RepoInfoTool(), {}),
            (ListFilesTool(), {"glob": "*.py"}),
            (ReadFileTool(), {"path": "README.md"}),
            (GitStatusTool(), {}),
        ]
        
        for tool, args in tools:
            result = tool.forward(**args)
            assert isinstance(result, dict), f"{tool.name} should return dict"
    
    def test_error_results_have_error_key(self, test_repo):
        """Error results should have 'error' key."""
        # Test file not found
        read_tool = ReadFileTool()
        result = read_tool.forward(path="nonexistent.txt")
        
        assert "error" in result
        assert isinstance(result["error"], str)
        assert "message" in result
