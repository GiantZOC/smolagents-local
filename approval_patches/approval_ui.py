#!/usr/bin/env python3
"""
Interactive CLI UI for approving patch proposals.

This runs as a separate process and polls the database for pending approval requests.
Users can review patches, see safety evaluations, and approve/reject them.
"""

import sys
import time
import json
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from approval_workflow import ApprovalStateMachine, ApprovalStatus
from artifact_store import ArtifactStore


class ApprovalUI:
    """Interactive CLI for patch approval"""
    
    def __init__(self, db_path: str = "artifacts.db"):
        self.approval_workflow = ApprovalStateMachine(db_path=db_path)
        self.artifact_store = ArtifactStore(db_path=db_path, blob_dir="artifact_blobs")
    
    def show_pending_approvals(self):
        """Display all pending approval requests"""
        pending = self.approval_workflow.list_pending_requests()
        
        if not pending:
            print("✅ No pending approval requests")
            return None
        
        print(f"\n{'='*70}")
        print(f"📋 PENDING APPROVAL REQUESTS ({len(pending)})")
        print(f"{'='*70}\n")
        
        for i, req in enumerate(pending, 1):
            print(f"{i}. Request ID: {req['request_id']}")
            print(f"   Proposal ID: {req['proposal_id']}")
            print(f"   Artifact: {req['artifact_id']}")
            print(f"   Requirements: {req['requirements']}")
            print(f"   Created: {req['created_at']}")
            print()
        
        return pending
    
    def show_approval_details(self, request_id: str):
        """Show detailed information about an approval request"""
        approval_req = self.approval_workflow.get_approval_request(request_id)
        
        if not approval_req:
            print(f"❌ Request not found: {request_id}")
            return None
        
        # Get proposal
        proposal = self.approval_workflow.get_patch_proposal(approval_req.proposal_id)
        
        print(f"\n{'='*70}")
        print(f"🔍 APPROVAL REQUEST DETAILS")
        print(f"{'='*70}\n")
        
        print(f"Request ID: {request_id}")
        print(f"Status: {approval_req.status.value.upper()}")
        print(f"Created: {approval_req.created_at}\n")
        
        if proposal:
            print(f"📝 Patch Proposal:")
            print(f"   Proposal ID: {proposal.proposal_id}")
            print(f"   Artifact ID: {proposal.artifact_id}")
            print(f"   Base Version: {proposal.base_version_id}")
            print(f"   Requirements: {proposal.requirements}")
            print(f"   Diff Hash: {proposal.diff_hash}")
            print()
            
            # Show diff
            print(f"{'─'*70}")
            print(f"📄 UNIFIED DIFF:")
            print(f"{'─'*70}")
            print(proposal.diff_content)
            print(f"{'─'*70}\n")
        
        # Show safety evaluation
        safety_eval = approval_req.safety_evaluation
        
        print(f"🔒 Safety Evaluation:")
        print(f"   Safe: {'✅ YES' if safety_eval.get('safe') else '❌ NO'}")
        print(f"   Syntax Valid: {'✅ YES' if safety_eval.get('syntax_valid') else '❌ NO'}")
        print()
        
        issues = safety_eval.get('issues', [])
        if issues:
            print(f"   ⚠️  SAFETY ISSUES ({len(issues)}):")
            for issue in issues:
                print(f"      - {issue}")
            print()
        
        warnings = safety_eval.get('warnings', [])
        if warnings:
            print(f"   ⚡ Warnings ({len(warnings)}):")
            for warning in warnings:
                print(f"      - {warning}")
            print()
        
        # Show capability delta
        cap_delta = safety_eval.get('capability_delta', {})
        added_caps = cap_delta.get('added', [])
        removed_caps = cap_delta.get('removed', [])
        
        if added_caps or removed_caps:
            print(f"   🔧 Capability Changes:")
            
            if added_caps:
                print(f"      ➕ Added ({len(added_caps)}):")
                for cap in added_caps[:5]:  # Show first 5
                    print(f"         - {cap['capability']} in {cap['file_path']}:{cap['line_number']}")
                if len(added_caps) > 5:
                    print(f"         ... and {len(added_caps) - 5} more")
                print()
            
            if removed_caps:
                print(f"      ➖ Removed ({len(removed_caps)}):")
                for cap in removed_caps[:5]:  # Show first 5
                    print(f"         - {cap['capability']} in {cap['file_path']}:{cap['line_number']}")
                if len(removed_caps) > 5:
                    print(f"         ... and {len(removed_caps) - 5} more")
                print()
        
        if not issues and not warnings and not added_caps and not removed_caps:
            print(f"   ✅ No issues, warnings, or capability changes detected\n")
        
        print(f"{'='*70}\n")
        
        return approval_req, proposal
    
    def prompt_decision(self, request_id: str) -> bool:
        """Prompt user for approval decision"""
        while True:
            choice = input("Decision (approve/reject/skip/quit): ").strip().lower()
            
            if choice == 'quit' or choice == 'q':
                return False
            
            if choice == 'skip' or choice == 's':
                print("⏭️  Skipped\n")
                return True
            
            if choice == 'approve' or choice == 'a':
                reason = input("Approval reason (optional): ").strip()
                if not reason:
                    reason = "Approved via UI"
                
                success = self.approval_workflow.submit_decision(
                    request_id, 
                    approved=True, 
                    reason=reason
                )
                
                if success:
                    print(f"✅ Patch APPROVED\n")
                else:
                    print(f"❌ Failed to approve\n")
                
                return True
            
            if choice == 'reject' or choice == 'r':
                reason = input("Rejection reason (required): ").strip()
                if not reason:
                    print("⚠️  Rejection reason is required")
                    continue
                
                success = self.approval_workflow.submit_decision(
                    request_id, 
                    approved=False, 
                    reason=reason
                )
                
                if success:
                    print(f"❌ Patch REJECTED\n")
                else:
                    print(f"❌ Failed to reject\n")
                
                return True
            
            print("Invalid choice. Use: approve, reject, skip, or quit")
    
    def interactive_mode(self):
        """Run interactive approval loop"""
        print(f"\n{'='*70}")
        print(f"🔒 PATCH APPROVAL UI")
        print(f"{'='*70}")
        print("\nCommands:")
        print("  approve (a) - Approve the patch")
        print("  reject (r)  - Reject the patch")
        print("  skip (s)    - Skip to next request")
        print("  quit (q)    - Exit")
        print(f"{'='*70}\n")
        
        while True:
            pending = self.show_pending_approvals()
            
            if not pending:
                print("\n⏳ Waiting for new approval requests...")
                print("   (Checking every 5 seconds, Ctrl+C to exit)\n")
                try:
                    time.sleep(5)
                    continue
                except KeyboardInterrupt:
                    print("\n\n👋 Exiting approval UI")
                    break
            
            # Show first pending request
            first_req = pending[0]
            request_id = first_req['request_id']
            
            # Show details
            result = self.show_approval_details(request_id)
            if not result:
                continue
            
            # Prompt for decision
            should_continue = self.prompt_decision(request_id)
            if not should_continue:
                print("\n👋 Exiting approval UI")
                break
    
    def review_mode(self):
        """Review a specific request by ID"""
        request_id = input("Enter request ID to review: ").strip()
        
        if not request_id:
            print("❌ No request ID provided")
            return
        
        result = self.show_approval_details(request_id)
        if not result:
            return
        
        self.prompt_decision(request_id)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive CLI for patch approval")
    parser.add_argument(
        '--db', 
        default='artifacts.db',
        help='Path to artifacts database (default: artifacts.db)'
    )
    parser.add_argument(
        '--review',
        metavar='REQUEST_ID',
        help='Review a specific request by ID'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List pending requests and exit'
    )
    
    args = parser.parse_args()
    
    ui = ApprovalUI(db_path=args.db)
    
    if args.list:
        # Just list pending requests
        ui.show_pending_approvals()
    elif args.review:
        # Review specific request
        ui.show_approval_details(args.review)
        ui.prompt_decision(args.review)
    else:
        # Interactive mode (poll for new requests)
        try:
            ui.interactive_mode()
        except KeyboardInterrupt:
            print("\n\n👋 Exiting approval UI")


if __name__ == "__main__":
    main()
