"""
Patch tools with approval enforcement.

FIXED: Added propose_patch_unified to work with truncated content.
"""

import uuid
import difflib
import subprocess
from pathlib import Path
from smolagents import Tool
from agent_runtime.tools.repo import RepoInfoTool
from agent_runtime.approval import PatchProposal, get_approval_store
from agent_runtime.sandbox import SimpleSandbox


# ============================================================================
# FIXED: New propose_patch_unified tool (preferred for truncated content)
# ============================================================================

class ProposePatchUnifiedTool(Tool):
    name = "propose_patch_unified"
    description = """Create a patch proposal from a unified diff.
    
    Use this when you have read portions of a file and want to propose changes.
    Provide the unified diff directly (starting with --- a/path, +++ b/path).
    
    This is PREFERRED over propose_patch when working with large files.
    
    Returns: {patch_id, intent, approved, feedback}"""
    
    inputs = {
        "intent": {"type": "string", "description": "short description of what the patch does"},
        "unified_diff": {"type": "string", "description": "unified diff content (--- a/... +++ b/... @@ ...)"},
    }
    output_type = "object"
    
    def forward(self, intent: str, unified_diff: str):
        # Generate patch ID
        patch_id = f"patch_{uuid.uuid4().hex[:10]}"
        
        # Extract file path from diff
        # Format: --- a/path/to/file.py or --- path/to/file.py
        lines = unified_diff.splitlines()
        file_path = None
        for line in lines:
            if line.startswith("--- a/"):
                file_path = line[6:]
                break
            elif line.startswith("--- "):
                # Handle git diff without a/ prefix
                file_path = line[4:].split()[0]  # First token after ---
                break
        
        if not file_path:
            return {
                "error": "INVALID_DIFF",
                "message": "Could not extract file path from diff. Expected '--- a/path' or '--- path' format."
            }
        
        # Create proposal
        proposal = PatchProposal(
            patch_id=patch_id,
            base_ref=file_path,
            diff=unified_diff,
            summary=intent
        )
        
        # Store and request approval
        approval_store = get_approval_store()
        approval_store.add_proposal(proposal)
        approval = approval_store.request_approval(patch_id)
        
        return {
            "patch_id": patch_id,
            "intent": intent,
            "file_path": file_path,
            "diff_preview": unified_diff[:500] + ("..." if len(unified_diff) > 500 else ""),
            "approved": approval.approved,
            "feedback": approval.feedback,
            "message": "Patch created and approved. Use apply_patch to apply." if approval.approved 
                      else f"Patch rejected. Feedback: {approval.feedback or 'None'}"
        }


# ============================================================================
# Original propose_patch tool (kept for backward compatibility)
# ============================================================================

class ProposePatchTool(Tool):
    name = "propose_patch"
    description = """Create a patch proposal (unified diff).
    
    Requires full file content. For large files, prefer propose_patch_unified.
    
    Returns: {patch_id, intent, file_path, diff_preview}"""
    
    inputs = {
        "intent": {"type": "string", "description": "short description of what the patch should do"},
        "file_path": {"type": "string", "description": "repo-relative path to file being modified"},
        "original_content": {"type": "string", "description": "current file content"},
        "new_content": {"type": "string", "description": "proposed new content"},
    }
    output_type = "object"

    def forward(self, intent: str, file_path: str, original_content: str, new_content: str):
        # Generate patch ID
        patch_id = f"patch_{uuid.uuid4().hex[:10]}"
        
        # Create unified diff
        original_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        )
        
        diff_text = ''.join(diff)
        
        # Create proposal
        proposal = PatchProposal(
            patch_id=patch_id,
            base_ref=file_path,
            diff=diff_text,
            summary=intent
        )
        
        # Store in approval store
        approval_store = get_approval_store()
        approval_store.add_proposal(proposal)
        
        # Automatically request approval (creates Phoenix span)
        approval = approval_store.request_approval(patch_id)
        
        return {
            "patch_id": patch_id,
            "intent": intent,
            "file_path": file_path,
            "diff_preview": diff_text[:500] + ("..." if len(diff_text) > 500 else ""),
            "approved": approval.approved,
            "feedback": approval.feedback,
            "message": "Patch created and approved. Use apply_patch to apply." if approval.approved 
                      else f"Patch rejected. Feedback: {approval.feedback or 'None'}"
        }


class ShowPatchTool(Tool):
    name = "show_patch"
    description = "Show a previously proposed patch by id."
    inputs = {
        "patch_id": {"type": "string", "description": "patch id"}
    }
    output_type = "object"

    def forward(self, patch_id: str):
        approval_store = get_approval_store()
        proposal = approval_store.proposals.get(patch_id)
        
        if not proposal:
            return {"error": "PATCH_NOT_FOUND", "patch_id": patch_id}
        
        # Check approval status
        is_approved = approval_store.is_approved(patch_id)
        feedback = approval_store.get_approval_feedback(patch_id)
        
        return {
            "patch_id": patch_id,
            "intent": proposal.summary,
            "file_path": proposal.base_ref,
            "diff": proposal.diff,
            "approved": is_approved,
            "feedback": feedback
        }


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = """Apply a previously proposed patch by id.
    
    IMPORTANT: This only works if the patch has been approved.
    If not approved, returns APPROVAL_REQUIRED error.
    
    Note: Sandbox validation skipped in basic version. Use carefully.
    
    Returns: {ok, patch_id, intent} on success or {error, ...} on failure"""
    
    inputs = {
        "patch_id": {"type": "string", "description": "patch id to apply"}
    }
    output_type = "object"

    def forward(self, patch_id: str):
        approval_store = get_approval_store()
        
        # Get proposal
        proposal = approval_store.proposals.get(patch_id)
        if not proposal:
            return {
                "error": "PATCH_NOT_FOUND",
                "patch_id": patch_id,
                "message": "Patch not found. Use propose_patch_unified to create it."
            }
        
        # ENFORCEMENT: Check if approved
        if not approval_store.is_approved(patch_id):
            feedback = approval_store.get_approval_feedback(patch_id)
            return {
                "error": "APPROVAL_REQUIRED",
                "patch_id": patch_id,
                "message": "Patch has not been approved by user.",
                "feedback": feedback,
                "blocked.approval_required": True,
                "approval.kind": "patch"
            }
        
        # Get repo root
        root = RepoInfoTool().forward()["root"]
        
        # Validate in sandbox (creates Phoenix span if enabled)
        with SimpleSandbox(repo_root=root, enable_phoenix=True) as sandbox:
            valid, message = sandbox.validate_patch(proposal.diff)
            
            if not valid:
                return {
                    "error": "PATCH_APPLY_FAILED",
                    "patch_id": patch_id,
                    "message": f"Patch validation failed: {message}",
                    "suggestion": "File may have changed since proposal. Create a new patch."
                }
        
        # Apply to actual repository
        tmp = Path(root) / f".{patch_id}.diff"
        tmp.write_text(proposal.diff)
        
        try:
            
            # Apply the patch
            apply_proc = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(tmp)],
                cwd=root,
                capture_output=True,
                text=True
            )
            
            if apply_proc.returncode != 0:
                return {
                    "error": "PATCH_APPLY_FAILED",
                    "patch_id": patch_id,
                    "stdout": apply_proc.stdout[-1000:],
                    "stderr": apply_proc.stderr[-1000:],
                    "message": "Patch command failed. See stdout/stderr for details."
                }
            
            # Success - clean up
            approval_store.proposals.pop(patch_id, None)
            approval_store.approvals.pop(patch_id, None)
            
            return {
                "ok": True,
                "patch_id": patch_id,
                "intent": proposal.summary,
                "file_path": proposal.base_ref,
                "files_changed": [proposal.base_ref],
                "message": f"Patch {patch_id} applied successfully to {proposal.base_ref}"
            }
        
        finally:
            tmp.unlink(missing_ok=True)
