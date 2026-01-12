"""
Helper functions for integrating approval UI with the patching agent.

This provides utilities for the agent to wait for human approval via the UI.
"""

import time
from typing import Optional, Tuple
from approval_workflow import ApprovalStateMachine, ApprovalStatus


def wait_for_user_approval(
    approval_workflow: ApprovalStateMachine,
    proposal_id: str,
    timeout: int = 300,
    poll_interval: int = 2
) -> Tuple[Optional[bool], Optional[str]]:
    """
    Wait for user to approve/reject via approval UI.
    
    This polls the database for the approval decision.
    The user reviews and decides using approval_ui.py in another terminal.
    
    Args:
        approval_workflow: ApprovalStateMachine instance
        proposal_id: Proposal ID to wait for
        timeout: Maximum seconds to wait (default: 300 = 5 minutes)
        poll_interval: Seconds between database polls (default: 2)
    
    Returns:
        (approved, reason) tuple:
        - approved: True if approved, False if rejected, None if timeout/error
        - reason: Decision reason from user
    
    Example:
        approved, reason = wait_for_user_approval(workflow, proposal_id)
        if approved:
            # Apply patch
        elif approved is False:
            # Handle rejection
        else:
            # Handle timeout
    """
    print(f"\n{'='*70}")
    print(f"⏳ WAITING FOR HUMAN APPROVAL")
    print(f"{'='*70}")
    print(f"\n📋 A patch approval request is pending in the database.")
    print(f"\n   To review and approve/reject, open ANOTHER terminal and run:")
    print(f"   \033[1;32mpython3 approval_ui.py\033[0m")
    print(f"\n   The approval UI will show:")
    print(f"   - Full diff of changes")
    print(f"   - Safety evaluation results")
    print(f"   - Capability changes detected")
    print(f"\n   Polling database every {poll_interval} seconds (timeout: {timeout}s)...")
    print(f"{'='*70}\n")
    
    elapsed = 0
    last_status = None
    
    while elapsed < timeout:
        # Query database for approval decision
        approval_req = approval_workflow.get_approval_by_proposal(proposal_id)
        
        if not approval_req:
            print("❌ No approval request found in database")
            return None, "Request not found"
        
        status = approval_req.status
        
        # Show status updates
        if status != last_status:
            if status == ApprovalStatus.PENDING:
                print(f"📊 Status: {status.value.upper()} - waiting for user decision...")
            last_status = status
        
        # Check for decision
        if status == ApprovalStatus.APPROVED:
            print(f"\n✅ PATCH APPROVED!")
            if approval_req.decision_reason:
                print(f"   Reason: {approval_req.decision_reason}")
            print()
            return True, approval_req.decision_reason
        
        elif status == ApprovalStatus.REJECTED:
            print(f"\n❌ PATCH REJECTED")
            if approval_req.decision_reason:
                print(f"   Reason: {approval_req.decision_reason}")
            print()
            return False, approval_req.decision_reason
        
        # Still pending - show progress
        print(f"   [{elapsed:3d}s] Waiting for decision...", end='\r')
        
        time.sleep(poll_interval)
        elapsed += poll_interval
    
    print(f"\n\n⏱️  TIMEOUT: No approval decision received within {timeout} seconds")
    return None, "Timeout waiting for approval"


def check_approval_result(
    approval_workflow: ApprovalStateMachine,
    proposal_id: str
) -> Tuple[Optional[bool], str]:
    """
    Check current approval status without waiting.
    
    Args:
        approval_workflow: ApprovalStateMachine instance
        proposal_id: Proposal ID to check
    
    Returns:
        (approved, status_message) tuple
    """
    approval_req = approval_workflow.get_approval_by_proposal(proposal_id)
    
    if not approval_req:
        return None, "No approval request found"
    
    status = approval_req.status
    
    if status == ApprovalStatus.APPROVED:
        msg = "✅ APPROVED"
        if approval_req.decision_reason:
            msg += f" - {approval_req.decision_reason}"
        return True, msg
    
    elif status == ApprovalStatus.REJECTED:
        msg = "❌ REJECTED"
        if approval_req.decision_reason:
            msg += f" - {approval_req.decision_reason}"
        return False, msg
    
    elif status == ApprovalStatus.PENDING:
        return None, "⏳ PENDING - awaiting user decision"
    
    elif status == ApprovalStatus.APPLIED:
        return True, "✅ APPLIED - patch has been applied"
    
    return None, f"Unknown status: {status.value}"
