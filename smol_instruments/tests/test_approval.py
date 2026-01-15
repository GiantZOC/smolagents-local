"""Tests for approval store."""

import pytest
from agent_runtime.approval import (
    ApprovalStore,
    PatchProposal,
    Approval,
    set_approval_store,
    get_approval_store
)


class TestApprovalStore:
    """Test approval store functionality."""
    
    def test_initialization(self):
        """ApprovalStore should initialize empty."""
        store = ApprovalStore()
        
        assert len(store.proposals) == 0
        assert len(store.approvals) == 0
        assert len(store.approved_commands) == 0
    
    def test_add_proposal(self):
        """Adding proposals should store them."""
        store = ApprovalStore()
        
        proposal = PatchProposal(
            patch_id="patch_123",
            base_ref="foo.py",
            diff="diff content",
            summary="Fix bug"
        )
        
        store.add_proposal(proposal)
        
        assert "patch_123" in store.proposals
        assert store.proposals["patch_123"] == proposal
    
    def test_is_approved_false_by_default(self):
        """Patches should not be approved by default."""
        store = ApprovalStore()
        
        assert store.is_approved("patch_123") is False
    
    def test_is_approved_after_approval(self):
        """is_approved should return True after approval."""
        store = ApprovalStore()
        
        store.approvals["patch_123"] = Approval(approved=True)
        
        assert store.is_approved("patch_123") is True
    
    def test_is_approved_false_after_rejection(self):
        """is_approved should return False after rejection."""
        store = ApprovalStore()
        
        store.approvals["patch_123"] = Approval(approved=False, feedback="Not good")
        
        assert store.is_approved("patch_123") is False
    
    def test_get_approval_feedback(self):
        """Rejection feedback should be retrievable."""
        store = ApprovalStore()
        
        store.approvals["patch_123"] = Approval(approved=False, feedback="Needs work")
        
        feedback = store.get_approval_feedback("patch_123")
        assert feedback == "Needs work"
    
    def test_get_approval_feedback_none_for_approved(self):
        """Approved patches should have no rejection feedback."""
        store = ApprovalStore()
        
        store.approvals["patch_123"] = Approval(approved=True)
        
        feedback = store.get_approval_feedback("patch_123")
        assert feedback is None
    
    def test_is_command_approved(self):
        """Command approval tracking should work."""
        store = ApprovalStore()
        
        assert store.is_command_approved("cmd_abc") is False
        
        store.approve_command("cmd_abc")
        
        assert store.is_command_approved("cmd_abc") is True
    
    def test_approve_command(self):
        """approve_command should add to approved set."""
        store = ApprovalStore()
        
        store.approve_command("cmd_123")
        store.approve_command("cmd_456")
        
        assert "cmd_123" in store.approved_commands
        assert "cmd_456" in store.approved_commands
    
    def test_custom_approval_callback(self):
        """Custom approval callback should be used."""
        auto_approve = lambda proposal: Approval(approved=True)
        
        store = ApprovalStore(approval_callback=auto_approve)
        
        proposal = PatchProposal("patch_123", "foo.py", "diff", "Fix")
        store.add_proposal(proposal)
        
        approval = store.request_approval("patch_123")
        
        assert approval.approved is True
    
    def test_request_approval_missing_patch(self):
        """Requesting approval for missing patch should fail."""
        store = ApprovalStore()
        
        approval = store.request_approval("nonexistent")
        
        assert approval.approved is False
        assert "not found" in approval.feedback.lower()


class TestGlobalApprovalStore:
    """Test global approval store getters/setters."""
    
    def test_set_and_get_approval_store(self):
        """Global approval store should be settable and gettable."""
        store = ApprovalStore()
        set_approval_store(store)
        
        retrieved = get_approval_store()
        
        assert retrieved is store
    
    def test_get_approval_store_not_initialized(self):
        """Getting uninitialized store should raise."""
        # Reset global state
        import agent_runtime.approval as approval_module
        approval_module._approval_store = None
        
        with pytest.raises(RuntimeError, match="not initialized"):
            get_approval_store()
