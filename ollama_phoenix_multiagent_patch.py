"""
Multi-Agent Orchestration with Plan Approval and Code Patching

Architecture:
    Orchestrator (CodeAgent with Planning)
        ├── Web Search Agent (searches internet)
        └── Code Patching Agent (proposes and applies patches in sandbox)

    Approval Gates:
        1. Plan Approval - User approves/modifies execution plans
        2. Patch Approval - User approves/rejects code patches

    HOST: Orchestrator, web search, patch proposals, LLM inference
    SANDBOX: Code execution and patch application

This implements:
    - Multi-agent collaboration
    - Plan customization and user approval
    - Code patch proposal and approval workflow
    - Sandboxed code execution and patching
    - Full Phoenix observability

Usage:
    # Start Phoenix:
    docker-compose up -d

    # Run on host:
    python ollama_phoenix_multiagent_patch.py

    # View traces:
    http://localhost:6006/projects/
"""

import warnings
# Suppress Pydantic serialization warnings from LiteLLM/Phoenix interaction
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")

from smolagents import (
    CodeAgent,
    ToolCallingAgent,
    LiteLLMModel,
    PlanningStep,
    ActionStep,
    Tool,
    tool,
    DuckDuckGoSearchTool,
)
from sandbox_manager import DockerSandbox
from patch_tools import ProposePatchTool, ApplyPatchTool, ApprovalGate, PatchProposal
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
import re
import requests
from markdownify import markdownify
from requests.exceptions import RequestException
import sys
import os


# ============================================================================
# Phoenix Setup (Host-side telemetry)
# ============================================================================

def setup_phoenix_host():
    """Set up Phoenix telemetry on the host"""
    endpoint = "http://localhost:6006/v1/traces"
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint)))
    SmolagentsInstrumentor().instrument(tracer_provider=tracer_provider)
    print("✓ Phoenix telemetry enabled on host")


# ============================================================================
# Plan Approval Gate (runs on HOST)
# ============================================================================

def display_plan(plan_content):
    """Display the plan in a formatted way"""
    print("\n" + "=" * 60)
    print("📋 EXECUTION PLAN CREATED")
    print("=" * 60)
    print(plan_content)
    print("=" * 60)


def get_user_plan_choice():
    """Get user's choice for plan approval"""
    while True:
        choice = input("\nPlan Options:\n1. Approve plan\n2. Modify plan\n3. Cancel\nYour choice (1-3): ").strip()
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

    # Remove the last two empty lines
    modified_plan = "\n".join(lines[:-2])
    return modified_plan if modified_plan.strip() else original_plan


def interrupt_after_plan(memory_step, agent):
    """
    Step callback that interrupts the agent after a planning step is created.
    This runs on the HOST for interactive plan approval.
    """
    if isinstance(memory_step, PlanningStep):
        print("\n🛑 Agent paused after plan creation...")

        # Display the created plan
        display_plan(memory_step.plan)

        # Get user choice
        choice = get_user_plan_choice()

        if choice == 1:  # Approve plan
            print("✅ Plan approved! Continuing execution...")
            return

        elif choice == 2:  # Modify plan
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
# Patch Approval Gate (runs on HOST)
# ============================================================================

def patch_approval_callback(patch: PatchProposal):
    """
    Interactive patch approval with formatted display.
    Shows patch details and gets user decision.
    """
    print("\n" + "=" * 70)
    print("🔧 CODE PATCH PROPOSAL")
    print("=" * 70)
    print(patch)
    print("=" * 70)

    while True:
        choice = input("\nPatch Options:\n1. Approve patch\n2. Reject with feedback\n3. Reject without feedback\nYour choice (1-3): ").strip()

        if choice == "1":
            from patch_tools import Approval
            return Approval(approved=True, patch_id=patch.patch_id)

        elif choice == "2":
            feedback = input("\nEnter feedback for the agent: ").strip()
            from patch_tools import Approval
            return Approval(approved=False, feedback=feedback, patch_id=patch.patch_id)

        elif choice == "3":
            from patch_tools import Approval
            return Approval(approved=False, patch_id=patch.patch_id)

        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


# ============================================================================
# Step Hierarchy Tracker
# ============================================================================

class StepTracker:
    """Tracks step hierarchy for better logging"""

    def __init__(self):
        self.step_counter = 0
        self.agent_step_counters = {}

    def format_step(self, memory_step, agent):
        """Format a step with hierarchical labels"""
        self.step_counter += 1

        agent_name = getattr(agent, 'name', 'orchestrator')

        if agent_name not in self.agent_step_counters:
            self.agent_step_counters[agent_name] = 0
        self.agent_step_counters[agent_name] += 1

        if isinstance(memory_step, PlanningStep):
            print(f"\n{'='*70}")
            print(f"📋 PLANNING STEP #{self.step_counter} [{agent_name}]")
            print(f"{'='*70}")

        elif isinstance(memory_step, ActionStep):
            if hasattr(memory_step, 'tool_calls') and memory_step.tool_calls:
                tool_call = memory_step.tool_calls[0]
                action_name = getattr(tool_call, 'name', 'unknown')
            else:
                action_name = "unknown"

            if any(name in action_name for name in ['web_search_agent', 'code_patch_agent']):
                print(f"\n{'─'*70}")
                print(f"🤖 DELEGATING TO: {action_name.upper()} (Step {self.step_counter})")
                print(f"{'─'*70}")
            else:
                print(f"\n⚡ Action #{self.step_counter} [{agent_name}]: {action_name}")


step_tracker = StepTracker()


def log_step_hierarchy(memory_step, agent):
    """Callback to log steps with proper hierarchy"""
    step_tracker.format_step(memory_step, agent)


# ============================================================================
# Web Tools (runs on HOST)
# ============================================================================

@tool
def visit_webpage(url: str) -> str:
    """
    Visits a webpage at the given URL and returns its content as a markdown string.

    Args:
        url: The URL of the webpage to visit.

    Returns:
        The content of the webpage converted to Markdown, or an error message if the request fails.
    """
    try:
        print(f"\n🌐 [WEB] Visiting webpage: {url}")

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        markdown_content = markdownify(response.text).strip()
        markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

        max_length = 5000
        if len(markdown_content) > max_length:
            markdown_content = markdown_content[:max_length] + "\n\n[Content truncated...]"

        print(f"✓ [WEB] Retrieved {len(markdown_content)} characters")
        return markdown_content

    except RequestException as e:
        return f"Error fetching the webpage: {str(e)}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"


# ============================================================================
# Sandboxed Code Execution with Patching
# ============================================================================

class SandboxedPatchExecutor:
    """
    Executor that runs code and applies patches in isolated Docker sandbox.
    Integrates with patch approval workflow.
    """

    def __init__(self, approval_gate: ApprovalGate):
        self.sandbox = None
        self.execution_count = 0
        self.patch_count = 0
        self.approval_gate = approval_gate
        self.propose_tool = ProposePatchTool()
        self.apply_tool = ApplyPatchTool()

    def execute_code(self, code: str) -> str:
        """Execute Python code in a fresh sandbox container."""
        self.execution_count += 1
        print(f"\n🔒 [SANDBOX] Executing code (execution #{self.execution_count})...")

        self.sandbox = DockerSandbox(enable_phoenix=True)

        try:
            result = self.sandbox.run_code(code)
            print("✓ [SANDBOX] Execution completed")
            return result if result else ""

        except Exception as e:
            error_msg = f"Sandbox execution failed: {str(e)}"
            print(f"❌ [SANDBOX] {error_msg}")
            return error_msg

        finally:
            if self.sandbox:
                self.sandbox.cleanup()
                self.sandbox = None

    def propose_patch(self, file_path: str, original_content: str,
                     new_content: str, summary: str) -> PatchProposal:
        """
        Create a patch proposal.
        Returns PatchProposal artifact for approval.
        """
        self.patch_count += 1
        print(f"\n📝 [PATCH] Creating patch proposal #{self.patch_count}...")

        patch = self.propose_tool(
            base_ref=file_path,
            original_content=original_content,
            new_content=new_content,
            summary=summary
        )

        print(f"✓ [PATCH] Proposal {patch.patch_id} created")
        return patch

    def apply_patch_with_approval(self, patch: PatchProposal) -> tuple[bool, str]:
        """
        Request approval and apply patch if approved.
        Returns (success, message) tuple.
        """
        print(f"\n🛑 [PATCH] Requesting approval for {patch.patch_id}...")

        # Request user approval
        approval = self.approval_gate.request_approval(patch)

        if approval.approved:
            print(f"\n✅ [PATCH] Patch {patch.patch_id} approved. Applying...")

            # Apply in sandbox
            self.sandbox = DockerSandbox(enable_phoenix=True)
            try:
                # First validate
                result = self.apply_tool(patch, dry_run=True)
                if not result.success:
                    msg = f"Patch validation failed: {result.error}"
                    print(f"❌ [PATCH] {msg}")
                    return (False, msg)

                # Apply for real
                result = self.apply_tool(patch)
                if result.success:
                    msg = f"Patch applied successfully to: {', '.join(result.files_changed)}"
                    print(f"✓ [PATCH] {msg}")
                    return (True, msg)
                else:
                    msg = f"Patch application failed: {result.error}"
                    print(f"❌ [PATCH] {msg}")
                    return (False, msg)

            finally:
                if self.sandbox:
                    self.sandbox.cleanup()
                    self.sandbox = None
        else:
            msg = f"Patch {patch.patch_id} rejected"
            if approval.feedback:
                msg += f". Feedback: {approval.feedback}"
            print(f"\n❌ [PATCH] {msg}")
            return (False, msg)

    def __del__(self):
        if self.sandbox:
            self.sandbox.cleanup()


# ============================================================================
# Main Multi-Agent System with Patch Workflow
# ============================================================================

def main():
    print("=" * 70)
    print("🚀 MULTI-AGENT ORCHESTRATION WITH PATCHING")
    print("=" * 70)
    print("\nComponents:")
    print("  🎯 Orchestrator - Plans tasks with user approval")
    print("  🌐 Web Search Agent - Searches internet and visits pages")
    print("  🔧 Code Patching Agent - Proposes and applies code patches")
    print("\nApproval Gates:")
    print("  ✋ Plan Approval - User reviews execution plans")
    print("  ✋ Patch Approval - User reviews code patches")
    print("=" * 70)

    # Setup Phoenix telemetry
    setup_phoenix_host()

    # Create patch approval gate
    patch_approval_gate = ApprovalGate(approval_callback=patch_approval_callback)

    # Create sandboxed executor with patching
    executor = SandboxedPatchExecutor(patch_approval_gate)

    # Create shared LLM model
    print("\n🧠 Initializing LLM model...")
    model = LiteLLMModel(
        model_id="ollama_chat/llama3.2:3b",
        api_base="http://localhost:11434",
        api_key="",
        num_ctx=8192,
    )

    print("\n🔧 Creating specialized agents...")

    # ========================================================================
    # Web Search Agent - Searches internet and visits pages
    # ========================================================================
    web_search_agent = CodeAgent(
        tools=[DuckDuckGoSearchTool(), visit_webpage],
        model=model,
        max_steps=8,
        additional_authorized_imports=["requests", "json", "re"],
        name="web_search_agent",
        description="Searches the internet and visits web pages to find current information, news, and general knowledge.",
    )
    print("  ✓ Web Search Agent created")

    # ========================================================================
    # Code Patching Agent - Creates and applies patches in sandbox
    # ========================================================================

    @tool
    def python_interpreter_sandboxed(code: str) -> str:
        """
        Executes Python code in an isolated Docker sandbox and returns the output.
        Use this for running any Python code, calculations, data processing, or demonstrations.

        Args:
            code: Python code to execute

        Returns:
            Output from the code execution
        """
        result = executor.execute_code(code)

        if result and ("Traceback" in result or "Error" in result or "Exception" in result):
            error_context = f"\n{'='*60}\n⚠️  CODE EXECUTION FAILED\n{'='*60}\n{result}\n{'='*60}\n"
            error_context += "\n💡 Analyze the error and retry with corrected code.\n"
            return error_context

        return result

    @tool
    def propose_code_patch(file_path: str, original_content: str,
                          new_content: str, summary: str) -> str:
        """
        Propose a code patch for review and approval.

        Creates a patch proposal that will be shown to the user for approval.
        If approved, the patch will be applied. If rejected, you'll receive
        feedback to create an improved version.

        Args:
            file_path: Path to the file being modified
            original_content: Current file content
            new_content: Proposed new content
            summary: Clear description of what changes and why

        Returns:
            Success message if approved and applied, or feedback if rejected
        """
        # Create patch proposal
        patch = executor.propose_patch(file_path, original_content, new_content, summary)

        # Request approval and apply if approved
        success, message = executor.apply_patch_with_approval(patch)

        return message

    code_patch_agent = CodeAgent(
        tools=[python_interpreter_sandboxed, propose_code_patch],
        model=model,
        max_steps=15,
        additional_authorized_imports=["time", "numpy", "pandas", "json", "requests", "os"],
        name="code_patch_agent",
        description=(
            "Writes and executes Python code, and proposes code patches for files. "
            "All code runs in an isolated sandbox. Patches require user approval before being applied. "
            "Can iterate based on patch approval feedback."
        ),
    )
    print("  ✓ Code Patching Agent created")

    # ========================================================================
    # Orchestrator - Plans and coordinates agents with approval
    # ========================================================================
    print("\n🎯 Creating orchestrator...")

    # Wrap managed agents to ensure string outputs
    @tool
    def call_web_search_agent(task: str) -> str:
        """
        Searches the internet and visits web pages to find current information.

        Args:
            task: Detailed description of what to search for

        Returns:
            Search results as a string
        """
        result = web_search_agent.run(task)
        return str(result)

    @tool
    def call_code_patch_agent(task: str) -> str:
        """
        Writes and executes Python code, and proposes code patches for files.
        All code runs in an isolated sandbox. Patches require user approval.

        Args:
            task: Detailed description of what code to write or patch to create

        Returns:
            Result as a string
        """
        result = code_patch_agent.run(task)
        return str(result)

    orchestrator_prompt = """You are an orchestrator agent that coordinates specialized agents.

When creating plans:
- Keep plans MINIMAL and ACTION-ORIENTED
- Focus on WHAT to do, not extensive analysis
- Each step should be a clear action

CRITICAL: After the plan is approved, you MUST execute it step by step using CODE BLOCKS with <code></code> tags.

You have access to these tools to coordinate agents:
- call_web_search_agent(task): Searches the internet and visits web pages. Use this for finding information online.
- call_code_patch_agent(task): Writes code and proposes file patches. Use this for writing and executing code.

DO NOT call functions like wikipedia_search, web_search, web_search_agent, code_patch_agent or any other tools - they don't exist. You can ONLY call call_web_search_agent and call_code_patch_agent.

Example execution after plan approval:

Thought: I will search for the information requested.
<code>
results = call_web_search_agent(task="Search for Pokemon team building guides for classic mode")
print(results)
</code>

Thought: Now I will provide the final answer based on the results.
<code>
final_answer(results)
</code>

Remember:
1. ALWAYS use <code></code> tags around your Python code
2. ONLY call web_search_agent and code_patch_agent - no other tools exist
3. Never just describe actions - execute them with code blocks"""

    orchestrator = CodeAgent(
        tools=[call_web_search_agent, call_code_patch_agent],
        model=model,
        managed_agents=[],
        additional_authorized_imports=["time", "json"],
        planning_interval=5,
        step_callbacks={
            PlanningStep: interrupt_after_plan,
            ActionStep: log_step_hierarchy,
        },
        max_steps=20,
        verbosity_level=1,  # Use verbosity 1 to avoid serialization issues
        name="orchestrator",
        description="Plans complex tasks and orchestrates web search and code patching agents",
        instructions=orchestrator_prompt
    )
    print("  ✓ Orchestrator created")

    # Get task from user
    print("\n" + "=" * 70)
    print("📋 ENTER YOUR TASK")
    print("=" * 70)
    print("Describe what you want the orchestrator to do.")
    print("The orchestrator can coordinate:")
    print("  - Web search agent (search internet, visit pages)")
    print("  - Code patching agent (write code, propose patches)")
    print("\nEnter your task (press Enter twice to finish):")
    print("-" * 70)

    lines = []
    empty_line_count = 0

    while empty_line_count < 2:
        line = input()
        if line.strip() == "":
            empty_line_count += 1
        else:
            empty_line_count = 0
        lines.append(line)

    # Remove the last two empty lines
    task = "\n".join(lines[:-2])

    if not task.strip():
        print("\n❌ No task provided. Exiting.")
        return

    print("\n" + "=" * 70)
    print("📋 YOUR TASK:")
    print("=" * 70)
    print(task)
    print("=" * 70)

    try:
        print("\n🎯 Starting orchestration...")
        print("   - Orchestrator creates plans (requires approval)")
        print("   - Web search agent finds information")
        print("   - Code patch agent proposes patches (requires approval)")
        print()

        result = orchestrator.run(task)

        print("\n" + "=" * 70)
        print("✅ TASK COMPLETED")
        print("=" * 70)
        print("\n📄 Final Result:")
        print("-" * 70)
        print(result)
        print("-" * 70)

        print(f"\n📊 Statistics:")
        print(f"   - Code executions: {executor.execution_count}")
        print(f"   - Patch proposals: {executor.patch_count}")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)

    except Exception as e:
        error_msg = str(e)
        if "interrupted" in error_msg.lower():
            print("\n🛑 Execution was cancelled by user.")
        else:
            print(f"\n❌ Error occurred: {e}")
            raise

    finally:
        if executor.sandbox:
            print("\n🧹 Cleaning up sandbox...")
            executor.sandbox.cleanup()

    print("\n" + "=" * 70)
    print("📊 View detailed traces at: http://localhost:6006/projects/")
    print("\nTrace shows:")
    print("  ✓ Orchestrator planning with user approval")
    print("  ✓ Web search agent queries")
    print("  ✓ Code patch proposals and approvals")
    print("  ✓ Sandboxed code execution")
    print("  ✓ Complete multi-agent workflow")
    print("=" * 70)


if __name__ == "__main__":
    main()
