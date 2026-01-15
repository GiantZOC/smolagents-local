"""Code search tools using ripgrep."""

import subprocess
from smolagents import Tool
from agent_runtime.tools.repo import RepoInfoTool
from agent_runtime.tools.validation import truncate_output


class RipgrepSearchTool(Tool):
    name = "rg_search"
    description = """Search code using ripgrep (fast regex search).
    
    Examples:
    - pattern="def main", glob="**/*.py"
    - pattern="class.*Component", glob="**/*.tsx"
    - pattern="TODO", glob="*"
    
    Returns: {matches: [{file, line, text}], count: N}"""
    
    inputs = {
        "pattern": {"type": "string", "description": "regex pattern to search for"},
        "glob": {"type": "string", "description": "glob pattern to filter files (e.g. **/*.py)", "nullable": True},
        "limit": {"type": "integer", "description": "max matches to return (default: 50)", "nullable": True}
    }
    output_type = "object"
    
    def forward(self, pattern: str, glob: str = "*", limit: int = 50):
        """Search code using ripgrep."""
        root = RepoInfoTool().forward()["root"]
        
        # Build ripgrep command
        cmd = [
            "rg",
            "--json",  # JSON output for easy parsing
            "--max-count", str(limit),
            "--glob", glob,
            pattern
        ]
        
        try:
            proc = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse JSON output
            import json
            matches = []
            
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                
                try:
                    entry = json.loads(line)
                    
                    # Only process match entries
                    if entry.get("type") == "match":
                        data = entry.get("data", {})
                        path = data.get("path", {}).get("text", "")
                        line_num = data.get("line_number", 0)
                        
                        # Extract matched text
                        lines_data = data.get("lines", {})
                        text = lines_data.get("text", "") if lines_data else ""
                        
                        matches.append({
                            "file": path,
                            "line": line_num,
                            "text": text.strip()
                        })
                except json.JSONDecodeError:
                    continue
            
            if not matches and proc.returncode != 0:
                # No matches found or error
                return {
                    "error": "RG_FAILED" if proc.returncode > 1 else "NO_MATCHES",
                    "pattern": pattern,
                    "glob": glob,
                    "stderr": proc.stderr[:500] if proc.stderr else "No matches found"
                }
            
            return {
                "matches": matches[:limit],
                "count": len(matches),
                "pattern": pattern,
                "glob": glob
            }
        
        except subprocess.TimeoutExpired:
            return {
                "error": "RG_TIMEOUT",
                "pattern": pattern,
                "message": "Search timed out after 30s"
            }
        except FileNotFoundError:
            return {
                "error": "RG_NOT_FOUND",
                "message": "ripgrep (rg) not found. Please install ripgrep."
            }
        except Exception as e:
            return {
                "error": "RG_FAILED",
                "pattern": pattern,
                "message": str(e)
            }
