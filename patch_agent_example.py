"""
Example: Agent using patch workflow

Shows how an agent integrates with the patch tools:
1. Agent calls ProposePatchTool during its work
2. Agent execution pauses at approval gate
3. User approves/rejects
4. Agent resumes and applies (or regenerates)
"""

from patch_tools import ProposePatchTool, ApplyPatchTool, ApprovalGate, PatchProposal


class CodeRefactoringAgent:
    """
    Example agent that proposes code changes using the patch workflow.
    """
    
    def __init__(self, propose_tool: ProposePatchTool, apply_tool: ApplyPatchTool):
        self.propose_tool = propose_tool
        self.apply_tool = apply_tool
    
    def refactor_function(self, file_path: str, original_code: str, 
                         user_request: str) -> PatchProposal:
        """
        Agent's internal logic to generate a refactored version.
        
        In reality, this would call an LLM to generate the new code.
        """
        # Simulate LLM generating new code based on request
        if "add error handling" in user_request.lower():
            new_code = original_code.replace(
                "def process(data):",
                "def process(data):\n    if not data:\n        raise ValueError('Data cannot be empty')"
            )
            summary = "Add error handling for empty data"
        else:
            new_code = original_code + "\n# Refactored"
            summary = "Generic refactoring"
        
        # Agent calls propose tool to create patch
        patch = self.propose_tool(
            base_ref=file_path,
            original_content=original_code,
            new_content=new_code,
            summary=summary
        )
        
        return patch
    
    def apply_approved_patch(self, patch: PatchProposal) -> bool:
        """
        Agent applies the patch after approval.
        
        Returns True if successful, False otherwise.
        """
        # First validate patch would apply cleanly
        result = self.apply_tool(patch, dry_run=True)
        if not result.success:
            print(f"Warning: Patch validation failed: {result.error}")
            return False
        
        # Apply for real
        result = self.apply_tool(patch)
        return result.success


class PatchOrchestrator:
    """
    Orchestrator that manages the agent and approval workflow.
    
    This is where the pause/resume magic happens.
    """
    
    def __init__(self, approval_callback=None):
        # Initialize tools
        self.propose_tool = ProposePatchTool()
        self.apply_tool = ApplyPatchTool()
        self.approval_gate = ApprovalGate(approval_callback)
        
        # Create agent with tools
        self.agent = CodeRefactoringAgent(self.propose_tool, self.apply_tool)
    
    def run_agent_with_approval(self, file_path: str, original_code: str, 
                                user_request: str, max_iterations: int = 3):
        """
        Run agent with approval loop.
        
        Agent generates patch → pause for approval → resume and apply/regenerate
        """
        iteration = 0
        feedback = None
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n{'='*60}")
            print(f"Iteration {iteration}: Agent generating patch...")
            print(f"{'='*60}\n")
            
            # Agent generates patch
            if feedback:
                print(f"Incorporating feedback: {feedback}\n")
                # In reality, pass feedback to LLM for regeneration
            
            patch = self.agent.refactor_function(file_path, original_code, user_request)
            
            # Orchestrator pauses for approval
            print(f"Patch {patch.patch_id} created. Requesting approval...\n")
            approval = self.approval_gate.request_approval(patch)
            
            # Resume based on approval
            if approval.approved:
                print(f"\n{'='*60}")
                print("Approval granted. Agent resuming...")
                print(f"{'='*60}\n")
                
                success = self.agent.apply_approved_patch(patch)
                
                if success:
                    print(f"✓ Patch {patch.patch_id} applied successfully!")
                    print(f"  Files modified: {patch.base_ref}")
                    return True
                else:
                    print(f"✗ Failed to apply patch {patch.patch_id}")
                    return False
            else:
                print(f"\n{'='*60}")
                print("Patch rejected.")
                print(f"{'='*60}\n")
                
                if approval.feedback:
                    feedback = approval.feedback
                    print(f"Agent will regenerate with feedback: {feedback}\n")
                    # Loop continues with feedback
                else:
                    print("No feedback provided. Stopping.")
                    return False
        
        print(f"Max iterations ({max_iterations}) reached. Stopping.")
        return False


# Example usage
if __name__ == "__main__":
    # Example code to refactor
    original_code = """def process(data):
    result = []
    for item in data:
        result.append(item * 2)
    return result
"""
    
    # Create orchestrator
    orchestrator = PatchOrchestrator()
    
    # Run agent with approval workflow
    print("Starting patch workflow example...")
    print("Agent will propose changes that require your approval.\n")
    
    success = orchestrator.run_agent_with_approval(
        file_path="processor.py",
        original_code=original_code,
        user_request="Add error handling for empty data"
    )
    
    if success:
        print("\n✓ Workflow completed successfully!")
    else:
        print("\n✗ Workflow did not complete.")


"""
Example session output:

============================================================
Iteration 1: Agent generating patch...
============================================================

Patch patch_0001 created. Requesting approval...

╔══════════════════════════════════════════════════════════╗
║ PATCH PROPOSAL: patch_0001
╚══════════════════════════════════════════════════════════╝

File: processor.py

Summary: Add error handling for empty data

Diff:
--- a/processor.py
+++ b/processor.py
@@ -1,4 +1,6 @@
 def process(data):
+    if not data:
+        raise ValueError('Data cannot be empty')
     result = []
     for item in data:
         result.append(item * 2)

============================================================
Approve this patch? [y/n/feedback]: y

============================================================
Approval granted. Agent resuming...
============================================================

✓ Patch patch_0001 applied successfully!
  Files modified: processor.py

✓ Workflow completed successfully!
"""
