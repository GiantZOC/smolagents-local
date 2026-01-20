"""
ApprovalStore - tracks which patches/commands have been approved.

Unified approval system for both patches and commands.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Callable
from opentelemetry import trace


tracer = trace.get_tracer(__name__)


@dataclass
class ApprovalRequest:
    """Unified approval request for patches or commands."""
    request_id: str
    kind: str  # "patch" or "command"
    summary: str
    details: str  # diff for patches, full command for commands
    source_file: Optional[str] = None  # For patches


@dataclass
class Approval:
    """User's decision on a request."""
    approved: bool
    feedback: Optional[str] = None


# Legacy alias for backward compatibility
PatchProposal = ApprovalRequest


class ApprovalStore:
    """
    Central store for tracking approvals (patches and commands).
    """
    
    def __init__(self, approval_callback: Optional[Callable[[ApprovalRequest], Approval]] = None):
        """
        Args:
            approval_callback: Function(ApprovalRequest) -> Approval
        """
        self.requests: Dict[str, ApprovalRequest] = {}
        self.approvals: Dict[str, Approval] = {}
        self.approval_callback = approval_callback or self._console_approval
    
    # Legacy property for backward compatibility
    @property
    def proposals(self) -> Dict[str, ApprovalRequest]:
        return self.requests
    
    @property
    def approved_commands(self):
        """Legacy: return set of approved command IDs."""
        return {k for k, v in self.approvals.items() if k.startswith("cmd_") and v.approved}
    
    def add_proposal(self, proposal: ApprovalRequest):
        """Store a new approval request (legacy name for patches)."""
        self.requests[proposal.request_id] = proposal
    
    def add_request(self, request: ApprovalRequest):
        """Store a new approval request."""
        self.requests[request.request_id] = request
    
    def is_approved(self, request_id: str) -> bool:
        """Check if a request has been approved."""
        approval = self.approvals.get(request_id)
        return approval is not None and approval.approved
    
    # Legacy alias
    def is_command_approved(self, cmd_id: str) -> bool:
        return self.is_approved(cmd_id)
    
    # Legacy alias
    def approve_command(self, cmd_id: str):
        self.approvals[cmd_id] = Approval(approved=True)
    
    def get_approval_feedback(self, request_id: str) -> Optional[str]:
        """Get rejection feedback if available."""
        approval = self.approvals.get(request_id)
        if approval and not approval.approved:
            return approval.feedback
        return None
    
    def request_approval(self, request_id: str, cmd: Optional[str] = None) -> Approval:
        """
        Request user approval.
        
        Args:
            request_id: ID of the request (patch_id or cmd_id)
            cmd: For commands not pre-registered, the command string
            
        Creates Phoenix span: approval.wait
        
        Returns:
            Approval decision
        """
        request = self.requests.get(request_id)
        
        # Auto-create request for commands passed directly
        if not request and cmd is not None:
            request = ApprovalRequest(
                request_id=request_id,
                kind="command",
                summary=f"Execute command",
                details=cmd,
            )
            self.requests[request_id] = request
        
        if not request:
            return Approval(approved=False, feedback=f"Request {request_id} not found")
        
        # Create Phoenix span for approval wait
        with tracer.start_as_current_span("approval.wait") as span:
            span.set_attribute("approval.kind", request.kind)
            span.set_attribute("approval.request_id", request_id)
            if request.source_file:
                span.set_attribute("approval.file", request.source_file)
            
            # Request approval from user
            approval = self.approval_callback(request)
            
            # Record decision
            self.approvals[request_id] = approval
            
            span.set_attribute("approval.granted", approval.approved)
            if approval.feedback:
                span.set_attribute("approval.feedback", approval.feedback[:200])
        
        return approval
    
    def _console_approval(self, request: ApprovalRequest) -> Approval:
        """Default console-based approval for any request type."""
        print("\n" + "=" * 70)
        if request.kind == "command":
            print("⚠️  COMMAND APPROVAL REQUEST")
        else:
            print("🔧 PATCH APPROVAL REQUEST")
        print("=" * 70)
        print(f"ID: {request.request_id}")
        print(f"Summary: {request.summary}")
        if request.source_file:
            print(f"File: {request.source_file}")
        print(f"\n{request.kind.title()}:")
        print(request.details)
        print("=" * 70)
        
        while True:
            choice = input("\nApprove? [y/n/feedback]: ").strip().lower()
            if choice == 'y':
                return Approval(approved=True)
            elif choice == 'n':
                return Approval(approved=False)
            elif choice:
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
