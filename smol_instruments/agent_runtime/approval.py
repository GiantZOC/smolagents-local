"""
ApprovalStore - tracks which patches/commands have been approved.

FIXED: Added command approval support.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Callable, Set
from opentelemetry import trace


tracer = trace.get_tracer(__name__)


@dataclass
class PatchProposal:
    """Artifact representing a proposed code change."""
    patch_id: str
    base_ref: str  # File path
    diff: str
    summary: str


@dataclass
class Approval:
    """User's decision on a proposal."""
    approved: bool
    feedback: Optional[str] = None


class ApprovalStore:
    """
    Central store for tracking approvals.
    
    FIXED: Added command approval tracking.
    """
    
    def __init__(self, approval_callback: Optional[Callable] = None):
        """
        Args:
            approval_callback: Function(PatchProposal) -> Approval
        """
        self.proposals: Dict[str, PatchProposal] = {}
        self.approvals: Dict[str, Approval] = {}
        self.approved_commands: Set[str] = set()  # FIXED: Track approved commands
        self.approval_callback = approval_callback or self._console_approval
    
    def add_proposal(self, proposal: PatchProposal):
        """Store a new proposal."""
        self.proposals[proposal.patch_id] = proposal
    
    def is_approved(self, patch_id: str) -> bool:
        """Check if a patch has been approved."""
        approval = self.approvals.get(patch_id)
        return approval is not None and approval.approved
    
    def get_approval_feedback(self, patch_id: str) -> Optional[str]:
        """Get rejection feedback if available."""
        approval = self.approvals.get(patch_id)
        if approval and not approval.approved:
            return approval.feedback
        return None
    
    def is_command_approved(self, cmd_id: str) -> bool:
        """FIXED: Check if a command has been approved."""
        return cmd_id in self.approved_commands
    
    def approve_command(self, cmd_id: str):
        """FIXED: Mark a command as approved."""
        self.approved_commands.add(cmd_id)
    
    def request_approval(self, patch_id: str) -> Approval:
        """
        Request user approval for a patch.
        
        Creates Phoenix span: approval.wait
        
        Returns:
            Approval decision
        """
        proposal = self.proposals.get(patch_id)
        if not proposal:
            return Approval(approved=False, feedback=f"Patch {patch_id} not found")
        
        # Create Phoenix span for approval wait
        with tracer.start_as_current_span("approval.wait") as span:
            span.set_attribute("approval.kind", "patch")
            span.set_attribute("approval.patch_id", patch_id)
            span.set_attribute("approval.file", proposal.base_ref)
            span.set_attribute("approval.requested_by", "propose_patch_unified")  # FIXED: Track source
            
            # Request approval from user
            approval = self.approval_callback(proposal)
            
            # Record decision
            self.approvals[patch_id] = approval
            
            span.set_attribute("approval.granted", approval.approved)
            if approval.feedback:
                span.set_attribute("approval.feedback", approval.feedback[:200])
        
        return approval
    
    def _console_approval(self, proposal: PatchProposal) -> Approval:
        """Default console-based approval."""
        print("\n" + "=" * 70)
        print("🔧 PATCH APPROVAL REQUEST")
        print("=" * 70)
        print(f"Patch ID: {proposal.patch_id}")
        print(f"File: {proposal.base_ref}")
        print(f"Summary: {proposal.summary}")
        print("\nDiff:")
        print(proposal.diff)
        print("=" * 70)
        
        while True:
            choice = input("\nApprove? [y/n/feedback]: ").strip().lower()
            if choice == 'y':
                return Approval(approved=True)
            elif choice == 'n':
                return Approval(approved=False)
            else:
                return Approval(approved=False, feedback=choice)


# Global approval store (injected into tools)
_approval_store: Optional[ApprovalStore] = None


def set_approval_store(store: ApprovalStore):
    """Set global approval store."""
    global _approval_store
    _approval_store = store


def get_approval_store() -> ApprovalStore:
    """Get global approval store."""
    if _approval_store is None:
        raise RuntimeError("ApprovalStore not initialized. Call set_approval_store() first.")
    return _approval_store
