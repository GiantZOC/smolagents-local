#!/usr/bin/env python3
"""
Demonstration of the approval UI workflow.

This script:
1. Creates a patch proposal
2. Requests approval (creates pending request in DB)
3. Tells user to run approval_ui.py to review and approve
4. Polls for approval decision
5. Applies the approved patch

Run in two terminals:
  Terminal 1: python3 test_approval_ui.py
  Terminal 2: python3 approval_ui.py
"""

import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from artifact_store import ArtifactStore
from patch_applier import PatchApplier
from safety_checker import ContextAwareSafetyChecker
from approval_workflow import ApprovalStateMachine, PatchLifecycle, ApprovalStatus


def wait_for_approval(workflow, proposal_id, timeout=300):
    """
    Wait for user to approve/reject via approval UI.
    Polls database every 2 seconds.
    """
    print(f"\n⏳ Waiting for approval decision...")
    print(f"   (Polling database every 2 seconds, timeout: {timeout}s)")
    print(f"   Run this in another terminal: python3 approval_ui.py\n")
    
    elapsed = 0
    while elapsed < timeout:
        approval_req = workflow.get_approval_by_proposal(proposal_id)
        
        if not approval_req:
            print("❌ No approval request found")
            return None
        
        status = approval_req.status
        
        if status == ApprovalStatus.APPROVED:
            print(f"\n✅ Patch APPROVED!")
            if approval_req.decision_reason:
                print(f"   Reason: {approval_req.decision_reason}")
            return True
        
        elif status == ApprovalStatus.REJECTED:
            print(f"\n❌ Patch REJECTED")
            if approval_req.decision_reason:
                print(f"   Reason: {approval_req.decision_reason}")
            return False
        
        # Still pending
        print(f"   [{elapsed:3d}s] Status: {status.value} ...", end='\r')
        time.sleep(2)
        elapsed += 2
    
    print(f"\n\n⏱️  Timeout waiting for approval decision")
    return None


def main():
    print("=" * 70)
    print("🔒 APPROVAL UI DEMONSTRATION")
    print("=" * 70)
    
    # Initialize components
    print("\n1️⃣  Initializing components...")
    artifact_store = ArtifactStore(db_path="demo_artifacts.db", blob_dir="demo_blobs")
    patch_applier = PatchApplier(artifact_store)
    safety_checker = ContextAwareSafetyChecker(artifact_store, patch_applier)
    approval_workflow = ApprovalStateMachine(db_path="demo_artifacts.db")
    patch_lifecycle = PatchLifecycle(artifact_store, patch_applier, safety_checker, approval_workflow)
    print("   ✅ Components initialized")
    
    # Create workspace artifact
    print("\n2️⃣  Creating workspace artifact...")
    workspace_path = str(Path(__file__).parent / "test_workspace")
    artifact_id, version_id = artifact_store.create_workspace_artifact(
        name="demo_fibonacci",
        workspace_path=workspace_path,
        commit_message="Initial version"
    )
    print(f"   ✅ Artifact created: {artifact_id}")
    print(f"   ✅ Version created: {version_id}")
    
    # Create patch proposal
    print("\n3️⃣  Creating patch proposal...")
    diff_content = """--- utils.py
+++ utils.py
@@ -1,6 +1,11 @@
 \"\"\"
 Utility functions
 \"\"\"
+import logging
+
+# Initialize logger
+logger = logging.getLogger(__name__)
+
 
 def greet(name):
     \"\"\"Simple greeting function\"\"\"
@@ -8,5 +13,6 @@ def greet(name):
 
 
 def add(a, b):
     \"\"\"Add two numbers\"\"\"
+    logger.debug(f"Adding {a} + {b}")
     return a + b
"""
    
    proposal_id = patch_lifecycle.propose_patch(
        artifact_id=artifact_id,
        base_version_id=version_id,
        diff_content=diff_content,
        requirements="Add logging to utils module"
    )
    print(f"   ✅ Proposal created: {proposal_id}")
    
    # Request approval
    print("\n4️⃣  Requesting approval (with safety checks)...")
    success, request_id, error = patch_lifecycle.request_approval(proposal_id)
    
    if not success:
        print(f"   ❌ Approval request failed: {error}")
        return False
    
    print(f"   ✅ Approval request created: {request_id}")
    
    # Show approval request details
    approval_req = approval_workflow.get_approval_request(request_id)
    if approval_req:
        safety_eval = approval_req.safety_evaluation
        print(f"\n   🔍 Safety Check Results:")
        print(f"      - Safe: {safety_eval.get('safe', False)}")
        print(f"      - Syntax valid: {safety_eval.get('syntax_valid', False)}")
        print(f"      - Issues: {len(safety_eval.get('issues', []))}")
        print(f"      - Warnings: {len(safety_eval.get('warnings', []))}")
        
        cap_delta = safety_eval.get('capability_delta', {})
        added = cap_delta.get('added', [])
        if added:
            print(f"      - New capabilities: {len(added)}")
            for cap in added[:3]:
                print(f"        + {cap['capability']}")
    
    print(f"\n{'='*70}")
    print(f"🚨 USER ACTION REQUIRED")
    print(f"{'='*70}")
    print(f"\n📋 A patch approval is waiting for your review!")
    print(f"\n   Request ID: {request_id}")
    print(f"\n   To review and approve/reject, run in ANOTHER terminal:")
    print(f"   \033[1;32mpython3 approval_ui.py --db demo_artifacts.db\033[0m")
    print(f"\n   Or review this specific request:")
    print(f"   \033[1;32mpython3 approval_ui.py --db demo_artifacts.db --review {request_id}\033[0m")
    print(f"\n{'='*70}")
    
    # Wait for approval
    approved = wait_for_approval(approval_workflow, proposal_id, timeout=300)
    
    if approved is None:
        print("\n⚠️  No decision received within timeout")
        return False
    
    if not approved:
        print("\n❌ Cannot proceed - patch was rejected")
        return False
    
    # Apply approved patch
    print("\n5️⃣  Applying approved patch...")
    success, new_version_id, error = patch_lifecycle.apply_approved_patch(proposal_id)
    
    if not success:
        print(f"   ❌ Apply failed: {error}")
        return False
    
    print(f"   ✅ Patch applied successfully!")
    print(f"   📦 New version: {new_version_id}")
    
    # Get new version info
    new_version = artifact_store.get_version(new_version_id)
    print(f"   📁 Files: {len(new_version.manifest)}")
    print(f"   📝 Commit: {new_version.commit_message}")
    
    print("\n" + "=" * 70)
    print("✅ WORKFLOW COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("\nThe patch was reviewed by a human, approved, and applied.")
    print("This demonstrates the complete approval workflow with user interaction.")
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
