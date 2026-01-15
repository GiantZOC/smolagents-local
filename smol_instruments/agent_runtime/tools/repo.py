"""Repository information tools."""

import os
from pathlib import Path
from smolagents import Tool
import glob as glob_module


class RepoInfoTool(Tool):
    name = "repo_info"
    description = "Get repository root path and basic info."
    inputs = {}
    output_type = "object"
    
    def forward(self):
        """Get repository root and basic information."""
        # Find git root by walking up from current directory
        current = Path.cwd()
        
        while current != current.parent:
            if (current / ".git").exists():
                return {
                    "root": str(current),
                    "name": current.name,
                    "is_git": True
                }
            current = current.parent
        
        # Not a git repo, use current directory
        cwd = Path.cwd()
        return {
            "root": str(cwd),
            "name": cwd.name,
            "is_git": False
        }


class ListFilesTool(Tool):
    name = "list_files"
    description = """List files matching glob pattern.
    
    Examples:
    - "**/*.py" - all Python files
    - "src/**/*.ts" - TypeScript files in src/
    - "*.md" - markdown files in root
    
    Returns: {files: [...], count: N}"""
    
    inputs = {
        "glob": {"type": "string", "description": "glob pattern (e.g. **/*.py)"},
        "limit": {"type": "integer", "description": "max files to return (default: 100)", "nullable": True}
    }
    output_type = "object"
    
    def forward(self, glob: str, limit: int = 100):
        """List files matching glob pattern."""
        root = RepoInfoTool().forward()["root"]
        
        try:
            # Use glob to find matching files
            pattern = os.path.join(root, glob)
            matches = glob_module.glob(pattern, recursive=True)
            
            # Filter to only files (not directories)
            files = [
                os.path.relpath(f, root)
                for f in matches
                if os.path.isfile(f)
            ]
            
            # Sort by path
            files.sort()
            
            # Apply limit
            if len(files) > limit:
                truncated = files[:limit]
                return {
                    "files": truncated,
                    "count": len(truncated),
                    "total_matches": len(files),
                    "truncated": True,
                    "message": f"Showing {limit} of {len(files)} matches"
                }
            
            return {
                "files": files,
                "count": len(files),
                "truncated": False
            }
        
        except Exception as e:
            return {
                "error": "GLOB_FAILED",
                "glob": glob,
                "message": str(e)
            }
