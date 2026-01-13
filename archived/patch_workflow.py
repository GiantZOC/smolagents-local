"""
Minimal Code Patch Workflow

A simple, artifact-based approach to LLM-generated code patches with human approval.

Flow:
1. Read current file(s) 
2. LLM generates unified diff against base
3. Store patch as artifact (PatchProposal)
4. Show patch to user (diff + summary)
5. If approved → apply patch and run smoke test
6. If rejected → incorporate feedback and regenerate
"""

from dataclasses import dataclass
from typing import Optional
import subprocess
import tempfile
import os


@dataclass
class PatchProposal:
    """Artifact representing a proposed code change."""
    base_ref: str  # File path or commit hash the diff is against
    diff: str  # Unified diff format
    summary: str  # Human-readable description of changes
    
    def __str__(self) -> str:
        return f"Patch for {self.base_ref}\n\n{self.summary}\n\n{self.diff}"


@dataclass
class Approval:
    """User's decision on a patch proposal."""
    approved: bool
    feedback: Optional[str] = None


@dataclass
class ApplyResult:
    """Result of applying a patch."""
    success: bool
    files_changed: list[str]
    error: Optional[str] = None


class PatchWorkflow:
    """Minimal patch workflow orchestrator."""
    
    def create_patch(self, base_ref: str, original_content: str, 
                     new_content: str, summary: str) -> PatchProposal:
        """
        Generate a unified diff between original and new content.
        
        Args:
            base_ref: File path or reference
            original_content: Original file content
            new_content: Modified file content  
            summary: Description of changes
            
        Returns:
            PatchProposal with unified diff
        """
        # Create temp files for diff generation
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.orig') as f_orig:
            f_orig.write(original_content)
            orig_path = f_orig.name
            
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.new') as f_new:
            f_new.write(new_content)
            new_path = f_new.name
        
        try:
            # Generate unified diff
            result = subprocess.run(
                ['diff', '-u', orig_path, new_path],
                capture_output=True,
                text=True
            )
            
            # diff returns 1 when files differ (not an error)
            diff_output = result.stdout
            
            # Replace temp filenames with actual reference
            lines = diff_output.split('\n')
            if len(lines) >= 2:
                lines[0] = f'--- a/{base_ref}'
                lines[1] = f'+++ b/{base_ref}'
            diff_output = '\n'.join(lines)
            
            return PatchProposal(
                base_ref=base_ref,
                diff=diff_output,
                summary=summary
            )
        finally:
            os.unlink(orig_path)
            os.unlink(new_path)
    
    def apply_patch(self, patch: PatchProposal, dry_run: bool = False) -> ApplyResult:
        """
        Apply a patch to the filesystem.
        
        Args:
            patch: PatchProposal to apply
            dry_run: If True, check if patch would apply without actually applying
            
        Returns:
            ApplyResult with success status and files changed
        """
        # Write patch to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.patch') as f:
            f.write(patch.diff)
            patch_file = f.name
        
        try:
            # Build patch command
            cmd = ['patch', '-p1']
            if dry_run:
                cmd.append('--dry-run')
            
            # Apply patch
            result = subprocess.run(
                cmd,
                stdin=open(patch_file),
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return ApplyResult(
                    success=True,
                    files_changed=[patch.base_ref]
                )
            else:
                return ApplyResult(
                    success=False,
                    files_changed=[],
                    error=result.stderr
                )
        finally:
            os.unlink(patch_file)
    
    def run_smoke_test(self, command: str) -> tuple[bool, str]:
        """
        Run a smoke test command after applying patch.
        
        Args:
            command: Shell command to run (e.g., "pytest tests/")
            
        Returns:
            (success, output) tuple
        """
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        
        return (result.returncode == 0, result.stdout + result.stderr)


# Example usage
if __name__ == "__main__":
    workflow = PatchWorkflow()
    
    # Step 1: Read current file
    file_path = "example.py"
    original = """def hello():
    print("Hello")
"""
    
    # Step 2: LLM generates new content (simulated)
    modified = """def hello(name="World"):
    print(f"Hello, {name}!")
"""
    
    # Step 3: Create patch proposal
    patch = workflow.create_patch(
        base_ref=file_path,
        original_content=original,
        new_content=modified,
        summary="Add name parameter to hello() function with default value"
    )
    
    # Step 4: Show patch to user
    print("=" * 60)
    print("PATCH PROPOSAL")
    print("=" * 60)
    print(patch)
    print("=" * 60)
    
    # Step 5a: Check if patch would apply
    result = workflow.apply_patch(patch, dry_run=True)
    if not result.success:
        print(f"Patch would not apply cleanly: {result.error}")
    
    # Step 5b: Get approval (simulated)
    approval = Approval(approved=True)
    
    if approval.approved:
        # Apply patch
        result = workflow.apply_patch(patch)
        if result.success:
            print(f"\nPatch applied successfully to: {', '.join(result.files_changed)}")
            
            # Optional: Run smoke test
            # test_success, output = workflow.run_smoke_test("python -m pytest")
        else:
            print(f"\nFailed to apply patch: {result.error}")
    else:
        print(f"\nPatch rejected. Feedback: {approval.feedback}")
        # Loop back to step 2 with feedback
