"""
Read-only git tools for deterministic repo operations.

NEW: Added git_status, git_diff, git_log tools.
"""

from smolagents import Tool
import subprocess
from agent_runtime.tools.repo import RepoInfoTool
from agent_runtime.tools.validation import truncate_output


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
            
            if status[0] in ['M', 'A', 'D', 'R']:
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
        "file_path": {"type": "string", "description": "optional file path to diff (empty for all)", "nullable": True},
        "staged": {"type": "boolean", "description": "whether to show staged changes (default: False)", "nullable": True}
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
        diff_truncated, was_truncated = truncate_output(diff, max_chars=5000, max_lines=200)
        
        result = {
            "diff": diff_truncated,
            "file_path": file_path or "all files",
            "staged": staged
        }
        
        if was_truncated:
            result["truncated"] = True
        
        return result


class GitLogTool(Tool):
    name = "git_log"
    description = "Get recent git commit history."
    inputs = {
        "limit": {"type": "integer", "description": "number of commits to show (default: 10)", "nullable": True},
        "file_path": {"type": "string", "description": "optional file path to show history for", "nullable": True}
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
