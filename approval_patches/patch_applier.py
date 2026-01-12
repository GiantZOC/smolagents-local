"""
PatchApplier V3: Git-based patch application with all-or-nothing semantics
"""
import subprocess
import tempfile
import shutil
import re
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FileChange:
    """Single file modification from patch"""
    repo_relative_path: str
    change_type: str  # 'modified', 'added', 'deleted'
    hunks_applied: int


@dataclass
class ApplyResult:
    """Result of patch application with all-or-nothing semantics"""
    success: bool
    files_changed: List[FileChange]
    hunks_total: int
    error_message: Optional[str] = None
    # No temp_dir - returns manifest directly
    resulting_manifest: Optional[List] = None


class PatchApplier:
    """
    Applies unified diffs using git apply with workspace-first semantics.
    All-or-nothing: Either entire patch applies cleanly or nothing changes.
    """
    
    def __init__(self, artifact_store):
        """
        Args:
            artifact_store: ArtifactStore instance for content retrieval
        """
        self.artifact_store = artifact_store
    
    def _validate_diff_paths(self, diff_content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that diff uses repo-relative paths (no a/ b/ prefixes allowed).
        Returns (valid, error_message)
        """
        lines = diff_content.split('\n')
        for line in lines:
            if line.startswith('--- ') or line.startswith('+++ '):
                path = line[4:].strip()
                
                # Check for a/ b/ prefixes
                if path.startswith('a/') or path.startswith('b/'):
                    return False, f"Diff contains a/ or b/ prefix: {line}. Use repo-relative paths."
                
                # Check for absolute paths
                if path.startswith('/') and path != '/dev/null':
                    return False, f"Diff contains absolute path: {line}. Use repo-relative paths."
        
        return True, None
    
    def _count_hunks(self, diff_content: str) -> int:
        """Count number of hunks in unified diff"""
        return len(re.findall(r'^@@', diff_content, re.MULTILINE))
    
    def _compute_file_changes(self, diff_content: str) -> List[FileChange]:
        """
        Parse diff to compute file changes.
        Returns list of FileChange objects.
        """
        changes: List[FileChange] = []
        current_file = None
        current_hunks = 0
        
        lines = diff_content.split('\n')
        for i, line in enumerate(lines):
            # New file header
            if line.startswith('--- '):
                # Save previous file if exists
                if current_file:
                    changes.append(FileChange(
                        repo_relative_path=current_file,
                        change_type='modified',  # Will refine below
                        hunks_applied=current_hunks
                    ))
                
                # Parse new file
                old_file = line[4:].strip()
                
                # Look ahead for +++ line
                if i + 1 < len(lines):
                    new_line = lines[i + 1]
                    if new_line.startswith('+++ '):
                        new_file = new_line[4:].strip()
                        
                        # Determine change type
                        if old_file == '/dev/null':
                            change_type = 'added'
                            current_file = new_file
                        elif new_file == '/dev/null':
                            change_type = 'deleted'
                            current_file = old_file
                        else:
                            change_type = 'modified'
                            current_file = new_file
                        
                        current_hunks = 0
            
            # Count hunks for current file
            elif line.startswith('@@'):
                current_hunks += 1
        
        # Save last file
        if current_file:
            changes.append(FileChange(
                repo_relative_path=current_file,
                change_type='modified',
                hunks_applied=current_hunks
            ))
        
        return changes
    
    def apply_to_workspace(
        self,
        base_version_id: str,
        diff_content: str,
        workspace_mode: bool = True
    ) -> ApplyResult:
        """
        Apply unified diff to base version with all-or-nothing semantics.
        
        Args:
            base_version_id: Version to apply patch to
            diff_content: Unified diff content
            workspace_mode: If True, treat as multi-file workspace diff
        
        Returns:
            ApplyResult with success status and resulting manifest
        """
        # Validate diff format
        valid, error = self._validate_diff_paths(diff_content)
        if not valid:
            return ApplyResult(
                success=False,
                files_changed=[],
                hunks_total=0,
                error_message=error
            )
        
        # Get base version
        base_version = self.artifact_store.get_version(base_version_id)
        if not base_version:
            return ApplyResult(
                success=False,
                files_changed=[],
                hunks_total=0,
                error_message=f"Base version not found: {base_version_id}"
            )
        
        # Count hunks
        hunks_total = self._count_hunks(diff_content)
        
        # Create temporary workspace
        temp_workspace = tempfile.mkdtemp(prefix="patch_apply_")
        try:
            # Export base version to temp workspace
            success = self.artifact_store.export_version_to_workspace(
                base_version_id, 
                temp_workspace
            )
            if not success:
                return ApplyResult(
                    success=False,
                    files_changed=[],
                    hunks_total=hunks_total,
                    error_message="Failed to export base version"
                )
            
            # Write diff to temp file
            diff_file = Path(temp_workspace) / ".patch.diff"
            diff_file.write_text(diff_content)
            
            # Try to apply with git apply (dry-run first)
            try:
                # Dry run
                subprocess.run(
                    ["git", "apply", "--check", "--verbose", str(diff_file)],
                    cwd=temp_workspace,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                # Actual apply
                subprocess.run(
                    ["git", "apply", "--verbose", str(diff_file)],
                    cwd=temp_workspace,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                return ApplyResult(
                    success=False,
                    files_changed=[],
                    hunks_total=hunks_total,
                    error_message=f"Patch application failed:\n{e.stderr}"
                )
            
            # Compute file changes
            file_changes = self._compute_file_changes(diff_content)
            
            # Build resulting manifest
            resulting_manifest = self.artifact_store._build_file_manifest(temp_workspace)
            
            return ApplyResult(
                success=True,
                files_changed=file_changes,
                hunks_total=hunks_total,
                resulting_manifest=resulting_manifest
            )
        
        finally:
            # Clean up temp workspace
            shutil.rmtree(temp_workspace, ignore_errors=True)
    
    def apply_and_create_version(
        self,
        artifact_id: str,
        base_version_id: str,
        diff_content: str,
        commit_message: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Apply patch and create new version if successful.
        
        Returns:
            (success, version_id, error_message)
        """
        # Apply patch
        result = self.apply_to_workspace(base_version_id, diff_content)
        
        if not result.success:
            return False, None, result.error_message
        
        # Create new version with resulting manifest
        version_id = self.artifact_store._create_version_with_manifest(
            artifact_id=artifact_id,
            base_version_id=base_version_id,
            commit_message=commit_message,
            manifest=result.resulting_manifest
        )
        
        return True, version_id, None
