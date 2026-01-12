"""
Code Patching Agent with Approval Workflow

This agent implements PATCHING_ARCHITECTURE_V3:
- DB-backed approval workflow (no in-memory state)
- All-or-nothing patch application
- Deterministic file manifests with SHA256 hashes
- Workspace-first architecture
- Post-apply tests (py_compile minimum)
- Full Phoenix telemetry

Usage:
    # Start Phoenix:
    docker-compose up -d
    
    # Run the patching agent:
    python code_patching_agent.py
    
    # View traces:
    http://localhost:6006/projects/
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from smolagents import CodeAgent, LiteLLMModel, PlanningStep, ActionStep, tool
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


# ============================================================================
# Phoenix Setup
# ============================================================================

def setup_phoenix_host():
    """Set up Phoenix telemetry on the host"""
    endpoint = "http://localhost:6006/v1/traces"
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint)))
    SmolagentsInstrumentor().instrument(tracer_provider=tracer_provider)
    print("✓ Phoenix telemetry enabled")


# ============================================================================
# Patching System Components (Implementing V3 Architecture)
# ============================================================================

from artifact_store import ArtifactStore
from patch_applier import PatchApplier
from safety_checker import ContextAwareSafetyChecker
from approval_workflow import ApprovalStateMachine, PatchLifecycle
from approval_helper import wait_for_user_approval, check_approval_result
from wait_for_approval_tool import wait_for_approval, set_approval_workflow

# Initialize V3 components
artifact_store = ArtifactStore(db_path="artifacts.db", blob_dir="artifact_blobs")
patch_applier = PatchApplier(artifact_store)
safety_checker = ContextAwareSafetyChecker(artifact_store, patch_applier)
approval_workflow = ApprovalStateMachine(db_path="artifacts.db")
patch_lifecycle = PatchLifecycle(artifact_store, patch_applier, safety_checker, approval_workflow)

# Set global workflow for wait_for_approval tool
set_approval_workflow(approval_workflow)

@tool
def create_workspace_artifact(name: str, workspace_path: str) -> str:
    """
    Create a new workspace artifact from a directory.
    
    This creates an initial version (v1) with a complete file manifest.
    Each file is content-addressed with SHA256 hashes.
    
    Args:
        name: Human-readable name for the artifact
        workspace_path: Path to the workspace directory to snapshot
    
    Returns:
        artifact_id that can be used to reference this artifact
    
    Example:
        artifact_id = create_workspace_artifact("my_project", "/workspace/current/my_project")
    """
    try:
        print(f"🆕 Creating workspace artifact: {name}")
        print(f"   From: {workspace_path}")
        
        artifact_id, version_id = artifact_store.create_workspace_artifact(
            name=name,
            workspace_path=workspace_path,
            commit_message="Initial version"
        )
        
        # Get version info
        version = artifact_store.get_version(version_id)
        file_count = len(version.manifest) if version else 0
        
        return (f"✅ Created artifact '{name}'\n"
                f"   Artifact ID: {artifact_id}\n"
                f"   Initial Version ID: {version_id}\n"
                f"   Files: {file_count}\n"
                f"   Status: Ready for patching")
    except Exception as e:
        return f"❌ Error creating artifact: {str(e)}"


@tool
def create_patch_proposal(artifact_id: str, base_version_id: str, 
                          requirements: str) -> str:
    """
    Generate a patch proposal for an artifact.
    
    This generates a unified diff that describes changes to implement the requirements.
    The diff is validated and stored with a SHA256 hash for integrity.
    
    CRITICAL: base_version_id must be pinned to prevent drift.
    
    Args:
        artifact_id: Target artifact to patch
        base_version_id: Specific version to patch from (e.g., "v_abc123...")
        requirements: Description of what changes to make
    
    Returns:
        proposal_id for the approval workflow
    
    Example:
        proposal_id = create_patch_proposal(
            "my_project_abc123", 
            "v_def456",
            "Add error handling to the login function"
        )
    """
    try:
        print(f"📝 Creating patch proposal")
        print(f"   Artifact: {artifact_id}")
        print(f"   Base version: {base_version_id}")
        print(f"   Requirements: {requirements}")
        
        # NOTE: For now, this creates a placeholder diff
        # In production, this would use an LLM to generate the actual diff
        # based on the requirements and the current code
        diff_content = f"""--- placeholder.py
+++ placeholder.py
@@ -1,1 +1,2 @@
 # Placeholder for: {requirements}
+# This would be a real unified diff in production
"""
        
        proposal_id = patch_lifecycle.propose_patch(
            artifact_id=artifact_id,
            base_version_id=base_version_id,
            diff_content=diff_content,
            requirements=requirements
        )
        
        return (f"✅ Created patch proposal\n"
                f"   Proposal ID: {proposal_id}\n"
                f"   Requirements: {requirements}\n"
                f"   Status: Ready for approval request\n"
                f"   Next: Use request_patch_approval('{proposal_id}')")
    except Exception as e:
        return f"❌ Error creating proposal: {str(e)}"


@tool
def request_patch_approval(proposal_id: str) -> str:
    """
    Request approval for a patch proposal.
    
    This triggers:
    1. Apply check (dry-run with git apply --check)
    2. Safety scan (AST analysis, capability delta)
    3. Evaluation persisted to database
    4. Approval request created (pending in DB)
    
    The request can be auto-approved if it passes strict safety rules,
    or it waits for user approval via the UI.
    
    Args:
        proposal_id: The proposal to request approval for
    
    Returns:
        Status message with request_id or auto-approval result
    
    Example:
        status = request_patch_approval("prop_abc123")
    """
    try:
        print(f"🔍 Requesting approval for: {proposal_id}")
        print(f"   Running safety checks...")
        
        success, request_id, error = patch_lifecycle.request_approval(proposal_id)
        
        if not success:
            return f"❌ Failed to create approval request: {error}"
        
        # Get the approval request to show safety evaluation
        approval_req = approval_workflow.get_approval_request(request_id)
        if approval_req:
            safety_eval = approval_req.safety_evaluation
            issues = safety_eval.get('issues', [])
            warnings = safety_eval.get('warnings', [])
            
            status_msg = "✅ Approval request created\n"
            status_msg += f"   Request ID: {request_id}\n"
            status_msg += f"   Status: {approval_req.status.value}\n"
            
            if issues:
                status_msg += f"\n⚠️  Safety Issues ({len(issues)}):\n"
                for issue in issues[:3]:  # Show first 3
                    status_msg += f"   - {issue}\n"
            
            if warnings:
                status_msg += f"\n⚡ Warnings ({len(warnings)}):\n"
                for warning in warnings[:3]:  # Show first 3
                    status_msg += f"   - {warning}\n"
            
            if not issues:
                status_msg += "\n✅ No safety issues found\n"
            
            status_msg += f"\nNext: Use check_approval_status('{proposal_id}') to check decision"
            return status_msg
        
        return f"✅ Approval request created: {request_id}"
    except Exception as e:
        import traceback
        return f"❌ Error requesting approval: {str(e)}\n{traceback.format_exc()}"


@tool
def check_approval_status(proposal_id: str) -> str:
    """
    Check if a patch proposal has been approved.
    
    This queries the database for the decision.
    Returns pending/approved/rejected status.
    
    Args:
        proposal_id: The proposal to check
    
    Returns:
        Status: pending, approved, or rejected (with feedback if available)
    
    Example:
        status = check_approval_status("prop_abc123")
    """
    try:
        print(f"📊 Checking approval status: {proposal_id}")
        
        approval_req = approval_workflow.get_approval_by_proposal(proposal_id)
        
        if not approval_req:
            return f"❌ No approval request found for proposal: {proposal_id}"
        
        status_msg = f"Status: {approval_req.status.value.upper()}\n"
        status_msg += f"Request ID: {approval_req.request_id}\n"
        status_msg += f"Created: {approval_req.created_at}\n"
        
        if approval_req.decision_at:
            status_msg += f"Decided: {approval_req.decision_at}\n"
        
        if approval_req.decision_reason:
            status_msg += f"Reason: {approval_req.decision_reason}\n"
        
        if approval_req.status.value == "approved":
            status_msg += f"\n✅ APPROVED - Ready to apply\n"
            status_msg += f"Next: Use apply_approved_patch('{proposal_id}')"
        elif approval_req.status.value == "rejected":
            status_msg += "\n❌ REJECTED - Cannot apply"
        elif approval_req.status.value == "pending":
            status_msg += "\n⏳ PENDING - Awaiting decision"
        elif approval_req.status.value == "applied":
            status_msg += "\n✅ APPLIED - Patch has been applied"
        
        return status_msg
    except Exception as e:
        return f"❌ Error checking approval status: {str(e)}"


@tool
def apply_approved_patch(proposal_id: str) -> str:
    """
    Apply an approved patch to create a new version.
    
    This performs:
    1. Verify approval exists and is approved=TRUE
    2. Check base version hasn't drifted
    3. Apply patch with all-or-nothing semantics (git apply)
    4. Create new version with deterministic file manifest
    5. Run post-apply tests (py_compile minimum)
    6. Record application in database
    
    Args:
        proposal_id: The approved proposal to apply
    
    Returns:
        new_version_id or error message
    
    Example:
        new_version = apply_approved_patch("prop_abc123")
    """
    try:
        print(f"✅ Applying approved patch: {proposal_id}")
        print(f"   Verifying approval...")
        print(f"   Checking for base drift...")
        print(f"   Applying with git apply...")
        print(f"   Running post-apply tests...")
        
        success, version_id, error = patch_lifecycle.apply_approved_patch(proposal_id)
        
        if not success:
            return f"❌ Failed to apply patch: {error}"
        
        # Get the new version info
        version = artifact_store.get_version(version_id)
        if version:
            file_count = len(version.manifest)
            return (f"✅ Patch applied successfully!\n"
                    f"   New Version ID: {version_id}\n"
                    f"   Files: {file_count}\n"
                    f"   Base Version: {version.base_version_id}\n"
                    f"   Commit Message: {version.commit_message}\n"
                    f"   Status: Applied and tested\n"
                    f"\nNext: Use get_version_info('{version_id}') for details")
        
        return f"✅ Patch applied successfully! New version: {version_id}"
    except Exception as e:
        import traceback
        return f"❌ Error applying patch: {str(e)}\n{traceback.format_exc()}"


@tool
def list_pending_approvals() -> str:
    """
    List all pending approval requests.
    
    This queries the database for approval_requests with status='pending'.
    Returns a formatted list with proposal details.
    
    Returns:
        List of pending approvals with request_id, proposal_id, and metadata
    
    Example:
        pending = list_pending_approvals()
    """
    try:
        print(f"📋 Listing pending approval requests...")
        
        pending_requests = approval_workflow.list_pending_requests()
        
        if not pending_requests:
            return "✅ No pending approval requests"
        
        result = f"📋 Pending Approval Requests ({len(pending_requests)}):\n\n"
        
        for i, req in enumerate(pending_requests, 1):
            result += f"{i}. Request ID: {req['request_id']}\n"
            result += f"   Proposal ID: {req['proposal_id']}\n"
            result += f"   Artifact: {req['artifact_id']}\n"
            result += f"   Base Version: {req['base_version_id']}\n"
            result += f"   Requirements: {req['requirements']}\n"
            result += f"   Created: {req['created_at']}\n"
            result += "\n"
        
        return result
    except Exception as e:
        return f"❌ Error listing approvals: {str(e)}"


@tool
def get_version_info(version_id: str) -> str:
    """
    Get detailed information about a specific version.
    
    Returns:
    - Version metadata (version_number, created_at, parent)
    - File manifest (all files with content hashes)
    - Total file count and size
    
    Args:
        version_id: The version to inspect
    
    Returns:
        Formatted version information
    
    Example:
        info = get_version_info("v_abc123")
    """
    try:
        print(f"ℹ️  Getting version info: {version_id}")
        
        version = artifact_store.get_version(version_id)
        
        if not version:
            return f"❌ Version not found: {version_id}"
        
        total_size = sum(entry.file_size for entry in version.manifest)
        
        result = f"📦 Version Information\n\n"
        result += f"Version ID: {version.version_id}\n"
        result += f"Artifact ID: {version.artifact_id}\n"
        result += f"Created: {version.created_at}\n"
        result += f"Base Version: {version.base_version_id or 'None (initial)'}\n"
        result += f"Commit Message: {version.commit_message}\n"
        result += f"\n📁 File Manifest ({len(version.manifest)} files, {total_size} bytes):\n\n"
        
        # Show first 10 files
        for i, entry in enumerate(version.manifest[:10], 1):
            result += f"{i}. {entry.repo_relative_path}\n"
            result += f"   Hash: {entry.content_hash[:16]}...\n"
            result += f"   Size: {entry.file_size} bytes\n"
        
        if len(version.manifest) > 10:
            result += f"\n... and {len(version.manifest) - 10} more files\n"
        
        return result
    except Exception as e:
        return f"❌ Error getting version info: {str(e)}"


@tool
def export_version_to_workspace(version_id: str, target_path: str) -> str:
    """
    Export a version to a filesystem workspace.
    
    This reconstructs the full workspace tree from the file manifest.
    Each file is retrieved from content-addressed blob storage.
    
    Args:
        version_id: The version to export
        target_path: Where to write the workspace
    
    Returns:
        Success message or error
    
    Example:
        export_version_to_workspace("v_abc123", "/tmp/export")
    """
    try:
        print(f"📦 Exporting version: {version_id}")
        print(f"   To: {target_path}")
        
        success = artifact_store.export_version_to_workspace(version_id, target_path)
        
        if not success:
            return f"❌ Failed to export version: {version_id}"
        
        # Get version info for summary
        version = artifact_store.get_version(version_id)
        if version:
            return (f"✅ Version exported successfully\n"
                    f"   Version: {version_id}\n"
                    f"   Location: {target_path}\n"
                    f"   Files: {len(version.manifest)}\n"
                    f"   Commit: {version.commit_message}")
        
        return f"✅ Version exported to {target_path}"
    except Exception as e:
        import traceback
        return f"❌ Error exporting version: {str(e)}\n{traceback.format_exc()}"


# ============================================================================
# Plan Customization Callbacks
# ============================================================================

def display_plan(plan_content):
    """Display the plan in a formatted way"""
    print("\n" + "=" * 70)
    print("📋 AGENT PLAN CREATED")
    print("=" * 70)
    print(plan_content)
    print("=" * 70)


def get_user_choice():
    """Get user's choice for plan approval"""
    while True:
        choice = input("\nChoose an option:\n1. Approve plan\n2. Modify plan\n3. Cancel\nYour choice (1-3): ").strip()
        if choice in ["1", "2", "3"]:
            return int(choice)
        print("Invalid choice. Please enter 1, 2, or 3.")


def get_modified_plan(original_plan):
    """Allow user to modify the plan"""
    print("\n" + "-" * 40)
    print("MODIFY PLAN")
    print("-" * 40)
    print("Current plan:")
    print(original_plan)
    print("-" * 40)
    print("Enter your modified plan (press Enter twice to finish):")

    lines = []
    empty_line_count = 0

    while empty_line_count < 2:
        line = input()
        if line.strip() == "":
            empty_line_count += 1
        else:
            empty_line_count = 0
        lines.append(line)

    modified_plan = "\n".join(lines[:-2])
    return modified_plan if modified_plan.strip() else original_plan


def interrupt_after_plan(memory_step, agent):
    """Step callback that interrupts the agent after a planning step"""
    if isinstance(memory_step, PlanningStep):
        print("\n🛑 Agent interrupted after plan creation...")
        display_plan(memory_step.plan)

        choice = get_user_choice()

        if choice == 1:  # Approve
            print("✅ Plan approved! Continuing execution...")
            return
        elif choice == 2:  # Modify
            modified_plan = get_modified_plan(memory_step.plan)
            memory_step.plan = modified_plan
            print("\nPlan updated!")
            display_plan(modified_plan)
            print("✅ Continuing with modified plan...")
            return
        elif choice == 3:  # Cancel
            print("❌ Execution cancelled by user.")
            agent.interrupt()
            return


# ============================================================================
# Step Hierarchy Tracker
# ============================================================================

class StepTracker:
    """Tracks step hierarchy and provides formatted labels"""
    
    def __init__(self):
        self.step_counter = 0
        self.agent_step_counters = {}
    
    def format_step(self, memory_step, agent):
        """Format a step with hierarchical labels"""
        self.step_counter += 1
        agent_name = getattr(agent, 'name', 'patching_agent')
        
        if agent_name not in self.agent_step_counters:
            self.agent_step_counters[agent_name] = 0
        self.agent_step_counters[agent_name] += 1
        
        if isinstance(memory_step, PlanningStep):
            print(f"\n{'='*70}")
            print(f"📋 PLANNING STEP #{self.step_counter}")
            print(f"{'='*70}")
        elif isinstance(memory_step, ActionStep):
            if hasattr(memory_step, 'tool_calls') and memory_step.tool_calls:
                tool_call = memory_step.tool_calls[0]
                action_name = getattr(tool_call, 'name', 'unknown')
                print(f"\n⚡ Action #{self.step_counter} [{agent_name}]: {action_name}")


step_tracker = StepTracker()

def log_step_hierarchy(memory_step, agent):
    """Callback to log steps with proper hierarchy"""
    step_tracker.format_step(memory_step, agent)


# ============================================================================
# Main Agent
# ============================================================================

def main():
    print("=" * 70)
    print("🚀 CODE PATCHING AGENT (PATCHING_ARCHITECTURE_V3)")
    print("=" * 70)
    print("\nCapabilities:")
    print("  ✓ Workspace-first artifact management")
    print("  ✓ DB-backed approval workflow")
    print("  ✓ All-or-nothing patch application")
    print("  ✓ Deterministic file manifests with SHA256")
    print("  ✓ Post-apply tests (py_compile)")
    print("  ✓ Phoenix telemetry integration")
    print("=" * 70)
    
    # Setup Phoenix
    setup_phoenix_host()
    
    # Create LLM model
    print("\n🧠 Initializing LLM model...")
    model = LiteLLMModel(
        model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
        api_base="http://localhost:11434",
        api_key="",
        num_ctx=8192,
    )
    
    # Patching tools
    patching_tools = [
        create_workspace_artifact,
        create_patch_proposal,
        request_patch_approval,
        wait_for_approval,  # NEW: Wait for human approval via UI
        check_approval_status,
        apply_approved_patch,
        list_pending_approvals,
        get_version_info,
        export_version_to_workspace,
    ]
    
    # Custom instructions for concise planning
    planning_prompt = """You are a code patching agent that implements PATCHING_ARCHITECTURE_V3.

Your workflow for patching code:
1. Create or identify the workspace artifact
2. Get the current version (head_version_id)
3. Create a patch proposal with the base version pinned
4. Request approval (triggers safety checks)
5. **CRITICAL**: Call wait_for_approval() and tell user to run approval_ui.py
6. Once approved, apply the patch
7. Verify the new version

Keep plans SHORT (3-5 steps). Focus on what to do, not extensive analysis.

When creating patches:
- Always pin the base_version_id
- Describe requirements clearly
- **MUST call wait_for_approval() after requesting approval**
- Tell user: "Run python3 approval_ui.py in another terminal to review"
- Only apply after approval is confirmed
- Check for drift (base moved) before applying

IMPORTANT: Approval is NOT automatic. You must:
1. Call request_patch_approval() to create the request
2. Call wait_for_approval() to wait for HUMAN decision via approval UI
3. Only then call apply_approved_patch()"""

    # Create agent
    print("🤖 Creating patching agent...")
    agent = CodeAgent(
        tools=patching_tools,
        model=model,
        add_base_tools=True,
        planning_interval=5,
        step_callbacks={
            PlanningStep: interrupt_after_plan,
            ActionStep: log_step_hierarchy,
        },
        max_steps=20,
        verbosity_level=2,
        name="patching_agent",
        description="Agent that manages code artifacts and applies patches with approval workflow",
        instructions=planning_prompt,
    )
    print("  ✓ Patching Agent created")
    
    # Example tasks
    example_tasks = [
        """
        Create a workspace artifact from /workspace/current/fibonacci_example
        and show me the version information.
        """,
        
        """
        Create a patch proposal to add type hints to the fibonacci function.
        The artifact is 'fibonacci_example_abc123' and base version is 'v_def456'.
        Request approval and show me the status.
        """,
        
        """
        List all pending approval requests and show their details.
        """,
    ]
    
    # Interactive mode
    print("\n" + "=" * 70)
    print("📋 INTERACTIVE MODE")
    print("=" * 70)
    print("\nExample tasks you can ask:")
    for i, task in enumerate(example_tasks, 1):
        print(f"\n{i}. {task.strip()}")
    
    print("\n" + "-" * 70)
    print("Enter a task (or 'quit' to exit):")
    print("-" * 70)
    
    while True:
        try:
            task = input("\n👤 Task: ").strip()
            
            if task.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not task:
                continue
            
            print("\n" + "=" * 70)
            print("🎯 EXECUTING TASK")
            print("=" * 70)
            
            # Run agent
            result = agent.run(task)
            
            print("\n" + "=" * 70)
            print("✅ TASK COMPLETED")
            print("=" * 70)
            print(f"\n📄 Result:\n{result}")
            print("\n" + "=" * 70)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            if "interrupted" in str(e).lower():
                print("\n🛑 Task cancelled by user")
            else:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("📊 View traces at: http://localhost:6006/projects/")
    print("=" * 70)


if __name__ == "__main__":
    main()
