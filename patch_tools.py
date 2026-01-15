"""
Patch Workflow Tools

Three-part implementation:
1. ProposePatchTool - Agents call this to generate patch proposals
2. Approval gate - Orchestrator pauses for human approval
3. ApplyPatchTool - Mechanical patch application

Usage:
    # Agent generates patch
    patch = propose_patch_tool(file_path, original, new_content, summary)
    
    # Orchestrator shows patch and waits for approval
    approval = await orchestrator.request_approval(patch)
    
    # If approved, apply mechanically
    if approval.approved:
        result = apply_patch_tool(patch)
"""

from dataclasses import dataclass, asdict
from typing import Optional, Any
import subprocess
import tempfile
import os
import difflib


@dataclass
class PatchProposal:
    """Artifact representing a proposed code change."""
    base_ref: str  # File path or reference
    diff: str  # Unified diff format
    summary: str  # Human-readable description
    patch_id: str  # Unique identifier for tracking
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    
    def __str__(self) -> str:
        return f"""
╔══════════════════════════════════════════════════════════╗
║ PATCH PROPOSAL: {self.patch_id}
╚══════════════════════════════════════════════════════════╝

File: {self.base_ref}

Summary: {self.summary}

Diff:
{self.diff}
"""


@dataclass
class Approval:
    """User's decision on a patch proposal."""
    approved: bool
    feedback: Optional[str] = None
    patch_id: str = ""


@dataclass
class ApplyResult:
    """Result of applying a patch."""
    success: bool
    files_changed: list[str]
    error: Optional[str] = None
    patch_id: str = ""


class ProposePatchTool:
    """
    Tool for agents to generate patch proposals.
    
    Agent calls this with original content and new content.
    Returns a PatchProposal artifact that gets sent to the approval gate.
    """
    
    name = "propose_patch"
    description = """Generate a patch proposal for code changes.
    
    Args:
        base_ref: File path being modified
        original_content: Current file content
        new_content: Proposed new content
        summary: Clear description of what changes and why
        
    Returns:
        PatchProposal artifact with unified diff
    """
    
    def __init__(self):
        self._patch_counter = 0
    
    def _generate_patch_id(self) -> str:
        """Generate unique patch ID."""
        self._patch_counter += 1
        return f"patch_{self._patch_counter:04d}"
    
    def _create_unified_diff(self, base_ref: str, original: str, new: str) -> str:
        """Generate unified diff between original and new content."""
        original_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{base_ref}",
            tofile=f"b/{base_ref}",
            lineterm=''
        )
        
        return ''.join(diff)
    
    def __call__(self, base_ref: str, original_content: str, 
                 new_content: str, summary: str) -> PatchProposal:
        """
        Generate a patch proposal.
        
        Args:
            base_ref: File path being modified
            original_content: Current file content
            new_content: Proposed new content
            summary: Description of changes
            
        Returns:
            PatchProposal artifact
        """
        patch_id = self._generate_patch_id()
        diff = self._create_unified_diff(base_ref, original_content, new_content)
        
        proposal = PatchProposal(
            base_ref=base_ref,
            diff=diff,
            summary=summary,
            patch_id=patch_id
        )
        
        return proposal


class ApplyPatchTool:
    """
    Mechanical tool to apply an approved patch.
    
    This should only be called after approval gate passes.
    No business logic - just applies the patch to disk.
    """
    
    name = "apply_patch"
    description = """Apply an approved patch to the filesystem.
    
    Args:
        patch: PatchProposal to apply
        dry_run: If True, validate patch without applying
        
    Returns:
        ApplyResult with success status
    """
    
    def _write_patch_file(self, diff: str) -> str:
        """Write diff to temporary file for patch command."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.patch') as f:
            f.write(diff)
            return f.name
    
    def _apply_with_patch_command(self, patch_file: str, dry_run: bool) -> tuple[bool, str]:
        """Use system patch command to apply diff."""
        cmd = ['patch', '-p1']
        if dry_run:
            cmd.append('--dry-run')
        
        with open(patch_file, 'r') as f:
            result = subprocess.run(
                cmd,
                stdin=f,
                capture_output=True,
                text=True
            )
        
        return (result.returncode == 0, result.stderr if result.returncode != 0 else "")
    
    def __call__(self, patch: PatchProposal, dry_run: bool = False) -> ApplyResult:
        """
        Apply a patch to the filesystem.
        
        Args:
            patch: PatchProposal to apply
            dry_run: If True, validate without applying
            
        Returns:
            ApplyResult with success status and files changed
        """
        patch_file = self._write_patch_file(patch.diff)
        
        try:
            success, error = self._apply_with_patch_command(patch_file, dry_run)
            
            return ApplyResult(
                success=success,
                files_changed=[patch.base_ref] if success else [],
                error=error if not success else None,
                patch_id=patch.patch_id
            )
        finally:
            os.unlink(patch_file)


class ApprovalGate:
    """
    Orchestrator-level approval gate for patches.
    
    Pauses agent execution, shows patch to user, waits for approval.
    Resumes agent with approval decision.
    """
    
    def __init__(self, approval_callback=None):
        """
        Initialize approval gate.
        
        Args:
            approval_callback: Function(PatchProposal) -> Approval
                              If None, uses console input (for testing)
        """
        self.approval_callback = approval_callback or self._console_approval
        self.pending_patches = {}
    
    def _console_approval(self, patch: PatchProposal) -> Approval:
        """Default console-based approval for testing."""
        print(patch)
        print("\n" + "="*60)
        response = input("Approve this patch? [y/n/feedback]: ").strip().lower()
        
        if response == 'y':
            return Approval(approved=True, patch_id=patch.patch_id)
        elif response == 'n':
            return Approval(approved=False, patch_id=patch.patch_id)
        else:
            return Approval(approved=False, feedback=response, patch_id=patch.patch_id)
    
    def request_approval(self, patch: PatchProposal) -> Approval:
        """
        Request user approval for a patch.
        
        This pauses agent execution and shows the patch to the user.
        
        Args:
            patch: PatchProposal to approve
            
        Returns:
            Approval decision from user
        """
        # Store pending patch
        self.pending_patches[patch.patch_id] = patch
        
        # Request approval (blocks until user responds)
        approval = self.approval_callback(patch)
        
        # Clean up pending
        if approval.approved or approval.feedback:
            del self.pending_patches[patch.patch_id]
        
        return approval


# Example integration
if __name__ == "__main__":
    # Initialize tools
    propose_tool = ProposePatchTool()
    apply_tool = ApplyPatchTool()
    approval_gate = ApprovalGate()
    
    # Simulate agent workflow
    print("Agent generating patch proposal...\n")
    
    # Agent reads file and generates new content
    original = """def calculate(x, y):
    return x + y
"""
    
    new = """def calculate(x, y, operation='add'):
    if operation == 'add':
        return x + y
    elif operation == 'subtract':
        return x - y
    else:
        raise ValueError(f"Unknown operation: {operation}")
"""
    
    # Agent calls ProposePatchTool
    patch = propose_tool(
        base_ref="calculator.py",
        original_content=original,
        new_content=new,
        summary="Add operation parameter to support subtraction"
    )
    
    print(f"Patch proposal created: {patch.patch_id}")
    print("Sending to approval gate...\n")
    
    # Orchestrator requests approval
    approval = approval_gate.request_approval(patch)
    
    # Handle approval decision
    if approval.approved:
        print("\nApproval granted. Applying patch...")
        result = apply_tool(patch)
        
        if result.success:
            print(f"✓ Patch applied successfully to: {', '.join(result.files_changed)}")
        else:
            print(f"✗ Failed to apply patch: {result.error}")
    else:
        print(f"\nPatch rejected.")
        if approval.feedback:
            print(f"User feedback: {approval.feedback}")
            print("Agent should regenerate patch with feedback...")
