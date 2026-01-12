"""
Tool for waiting for human approval via the approval UI.

This is a separate tool that the agent can call after requesting approval.
"""

from smolagents import tool
from approval_workflow import ApprovalStateMachine
from approval_helper import wait_for_user_approval


# Global approval workflow (initialized in main agent)
_approval_workflow = None


def set_approval_workflow(workflow: ApprovalStateMachine):
    """Set the global approval workflow instance"""
    global _approval_workflow
    _approval_workflow = workflow


@tool
def wait_for_approval(proposal_id: str, timeout_seconds: int = 300) -> str:
    """
    Wait for human to approve/reject a patch via the approval UI.
    
    This tool blocks and polls the database for the approval decision.
    The user reviews the patch using approval_ui.py in another terminal.
    
    IMPORTANT: This tool will wait up to timeout_seconds for a decision.
    Make sure to inform the user to run: python3 approval_ui.py
    
    Args:
        proposal_id: The proposal to wait for approval on
        timeout_seconds: Maximum seconds to wait (default: 300 = 5 minutes)
    
    Returns:
        Status message indicating approved/rejected/timeout
    
    Example:
        # After requesting approval
        result = wait_for_approval("prop_abc123", timeout_seconds=180)
    """
    if not _approval_workflow:
        return "❌ Error: Approval workflow not initialized"
    
    try:
        approved, reason = wait_for_user_approval(
            _approval_workflow,
            proposal_id,
            timeout=timeout_seconds,
            poll_interval=2
        )
        
        if approved is True:
            return f"✅ APPROVED\nReason: {reason}\nReady to apply patch!"
        elif approved is False:
            return f"❌ REJECTED\nReason: {reason}\nCannot apply patch."
        else:
            return f"⏱️  TIMEOUT\nNo decision received within {timeout_seconds} seconds.\n{reason}"
    
    except Exception as e:
        import traceback
        return f"❌ Error waiting for approval: {str(e)}\n{traceback.format_exc()}"
