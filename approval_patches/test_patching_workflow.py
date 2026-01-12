#!/usr/bin/env python3
"""
Test script for PATCHING_ARCHITECTURE_V3 workflow
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from artifact_store import ArtifactStore
from patch_applier import PatchApplier
from safety_checker import ContextAwareSafetyChecker
from approval_workflow import ApprovalStateMachine, PatchLifecycle


def test_workflow():
    """Test complete patching workflow"""
    
    print("=" * 70)
    print("🧪 TESTING PATCHING_ARCHITECTURE_V3 WORKFLOW")
    print("=" * 70)
    
    # Initialize components
    print("\n1️⃣  Initializing components...")
    artifact_store = ArtifactStore(db_path="test_artifacts.db", blob_dir="test_blobs")
    patch_applier = PatchApplier(artifact_store)
    safety_checker = ContextAwareSafetyChecker(artifact_store, patch_applier)
    approval_workflow = ApprovalStateMachine(db_path="test_artifacts.db")
    patch_lifecycle = PatchLifecycle(artifact_store, patch_applier, safety_checker, approval_workflow)
    print("   ✅ Components initialized")
    
    # Create workspace artifact
    print("\n2️⃣  Creating workspace artifact...")
    workspace_path = str(Path(__file__).parent / "test_workspace")
    artifact_id, version_id = artifact_store.create_workspace_artifact(
        name="test_fibonacci",
        workspace_path=workspace_path,
        commit_message="Initial version"
    )
    print(f"   ✅ Artifact created: {artifact_id}")
    print(f"   ✅ Version created: {version_id}")
    
    # Get version info
    version = artifact_store.get_version(version_id)
    print(f"   📁 Files: {len(version.manifest)}")
    for entry in version.manifest:
        print(f"      - {entry.repo_relative_path} ({entry.file_size} bytes)")
    
    # Create patch proposal
    print("\n3️⃣  Creating patch proposal...")
    diff_content = """--- fibonacci.py
+++ fibonacci.py
@@ -1,6 +1,8 @@
 \"\"\"
 Simple fibonacci implementation for testing patch workflow
 \"\"\"
+from typing import Dict
+
 
 def fibonacci(n):
     \"\"\"Calculate the nth fibonacci number\"\"\"
"""
    
    proposal_id = patch_lifecycle.propose_patch(
        artifact_id=artifact_id,
        base_version_id=version_id,
        diff_content=diff_content,
        requirements="Add typing imports"
    )
    print(f"   ✅ Proposal created: {proposal_id}")
    
    # Request approval
    print("\n4️⃣  Requesting approval (with safety checks)...")
    success, request_id, error = patch_lifecycle.request_approval(proposal_id)
    
    if not success:
        print(f"   ❌ Approval request failed: {error}")
        return False
    
    print(f"   ✅ Approval request created: {request_id}")
    
    # Get approval request to see safety evaluation
    approval_req = approval_workflow.get_approval_request(request_id)
    if approval_req:
        safety_eval = approval_req.safety_evaluation
        print(f"   🔍 Safety check:")
        print(f"      - Safe: {safety_eval.get('safe', False)}")
        print(f"      - Syntax valid: {safety_eval.get('syntax_valid', False)}")
        print(f"      - Issues: {len(safety_eval.get('issues', []))}")
        print(f"      - Warnings: {len(safety_eval.get('warnings', []))}")
    
    # Simulate approval decision
    print("\n5️⃣  Submitting approval decision...")
    approval_workflow.submit_decision(request_id, approved=True, reason="Test approval")
    print(f"   ✅ Patch approved")
    
    # Apply approved patch
    print("\n6️⃣  Applying approved patch...")
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
    
    # List versions
    print("\n7️⃣  Listing all versions...")
    versions = artifact_store.list_versions(artifact_id)
    print(f"   📚 Total versions: {len(versions)}")
    for v in versions:
        print(f"      - {v['version_id']}: {v['commit_message']}")
    
    # Export new version
    print("\n8️⃣  Exporting new version...")
    export_path = str(Path(__file__).parent / "test_export")
    artifact_store.export_version_to_workspace(new_version_id, export_path)
    print(f"   ✅ Exported to: {export_path}")
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    
    return True


if __name__ == "__main__":
    try:
        success = test_workflow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
