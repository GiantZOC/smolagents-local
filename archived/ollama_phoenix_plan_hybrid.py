"""
Hybrid Plan Customization with Sandboxed Execution

Architecture:
    HOST: Planning, approval, LLM inference, Phoenix aggregation
    SANDBOX: Code execution only (when agent generates Python code)

This gives you:
    - Fast, interactive planning and approval on the host
    - Isolated execution of untrusted generated code
    - Minimal container overhead (only when executing)
    - Full Phoenix telemetry across both layers

Usage:
    # Start Phoenix:
    docker-compose up -d
    
    # Run on host:
    python ollama_phoenix_plan_hybrid.py
    
    # View traces:
    http://localhost:6006/projects/
"""

from smolagents import CodeAgent, LiteLLMModel, PlanningStep, tool
from sandbox_manager import DockerSandbox
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
import sys


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
# Plan Customization Callbacks (runs on HOST)
# ============================================================================

def display_plan(plan_content):
    """Display the plan in a formatted way"""
    print("\n" + "=" * 60)
    print("🤖 AGENT PLAN CREATED")
    print("=" * 60)
    print(plan_content)
    print("=" * 60)


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

    # Remove the last two empty lines
    modified_plan = "\n".join(lines[:-2])
    return modified_plan if modified_plan.strip() else original_plan


def interrupt_after_plan(memory_step, agent):
    """
    Step callback that interrupts the agent after a planning step is created.
    This runs on the HOST for interactive approval.
    """
    if isinstance(memory_step, PlanningStep):
        print("\n🛑 Agent interrupted after plan creation...")

        # Display the created plan
        display_plan(memory_step.plan)

        # Get user choice
        choice = get_user_choice()

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
# Sandboxed Python Execution Tool
# ============================================================================

class SandboxedPythonExecutor:
    """
    Custom executor that runs Python code in isolated Docker sandbox.
    This replaces the default local Python executor for security.
    """
    
    def __init__(self):
        self.sandbox = None
        self.execution_count = 0
    
    def execute(self, code: str) -> str:
        """
        Execute Python code in a fresh sandbox container.
        
        Args:
            code: Python code to execute
            
        Returns:
            Output from code execution
        """
        self.execution_count += 1
        print(f"\n🔒 Executing code in isolated sandbox (execution #{self.execution_count})...")
        
        # Create fresh sandbox for this execution
        self.sandbox = DockerSandbox(enable_phoenix=True)
        
        try:
            # Run code in sandbox
            result = self.sandbox.run_code(code)
            print("✓ Sandbox execution completed")
            return result if result else ""
            
        except Exception as e:
            error_msg = f"Sandbox execution failed: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
            
        finally:
            # Always cleanup sandbox after execution
            if self.sandbox:
                self.sandbox.cleanup()
                self.sandbox = None
    
    def __del__(self):
        """Ensure cleanup on object destruction"""
        if self.sandbox:
            self.sandbox.cleanup()


# Create sandboxed Python execution tool
@tool
def python_interpreter_sandboxed(code: str) -> str:
    """
    Executes Python code in an isolated Docker sandbox and returns the output.
    This is safer than running code directly on the host.
    
    Args:
        code: Python code to execute
        
    Returns:
        Output from the code execution
    """
    executor = SandboxedPythonExecutor()
    return executor.execute(code)


# ============================================================================
# Main Execution
# ============================================================================

def main():
    print("=" * 70)
    print("🚀 HYBRID AGENT: Host Planning + Sandboxed Execution")
    print("=" * 70)
    
    # Setup Phoenix telemetry on host
    setup_phoenix_host()
    
    # Create LLM model (runs on HOST, connects to local Ollama)
    print("\n🧠 Initializing LLM model (host-side)...")
    model = LiteLLMModel(
        model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
        api_base="http://localhost:11434",  # Direct host access
        api_key="",
        num_ctx=8192,
    )
    
    # Create sandboxed executor
    executor = SandboxedPythonExecutor()
    
    # Create agent with planning + approval (runs on HOST)
    # But Python execution delegated to sandbox
    print("🤖 Creating agent with host-side planning and sandboxed execution...")
    agent = CodeAgent(
        tools=[],  # We'll override Python execution
        model=model,
        add_base_tools=True,
        planning_interval=3,  # Create plan every 3 steps
        step_callbacks={PlanningStep: interrupt_after_plan},  # HOST callback
        max_steps=15,
        verbosity_level=1,
        name="hybrid_agent",
        description="Agent with host planning and sandboxed code execution",
    )
    
    # Override the Python interpreter with sandboxed version
    # Find and replace the python_interpreter tool
    for i, tool_obj in enumerate(agent.tools):
        if hasattr(tool_obj, 'name') and 'python' in tool_obj.name.lower():
            agent.tools[i] = python_interpreter_sandboxed
            print(f"✓ Replaced '{tool_obj.name}' with sandboxed version")
            break
    
    # Define task
    task = """Write a Python function that generates the first N prime numbers,
    then use it to find the first 20 primes. After that, calculate the sum
    of those primes and determine if that sum is also prime."""
    
    print("\n" + "=" * 70)
    print("📋 TASK:")
    print(task)
    print("=" * 70)
    
    try:
        print("\n🎯 Starting agent execution...")
        print("   - Planning happens on HOST (fast, interactive)")
        print("   - Code execution happens in SANDBOX (safe, isolated)")
        print()
        
        # Run agent
        # Planning/approval runs on host
        # When agent calls python_interpreter, it spawns sandbox
        result = agent.run(task)
        
        print("\n" + "=" * 70)
        print("✅ TASK COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\n📄 Final Result:")
        print("-" * 70)
        print(result)
        print("-" * 70)
        
        print(f"\n📊 Sandboxed executions: {executor.execution_count}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
        
    except Exception as e:
        error_msg = str(e)
        if "interrupted" in error_msg.lower():
            print("\n🛑 Agent execution was cancelled by user.")
            print("\n💡 Agent memory state preserved. Could resume with:")
            print("   agent.run(task, reset=False)")
            
            if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps'):
                print(f"\n📚 Current memory contains {len(agent.memory.steps)} steps")
        else:
            print(f"\n❌ Error occurred: {e}")
            raise
    
    finally:
        # Cleanup
        if executor.sandbox:
            print("\n🧹 Cleaning up sandbox...")
            executor.sandbox.cleanup()
    
    print("\n" + "=" * 70)
    print("📊 View detailed traces at: http://localhost:6006/projects/")
    print("\nTrace shows:")
    print("  ✓ Host-side planning and reasoning")
    print("  ✓ User approval decisions")
    print("  ✓ Sandboxed code executions")
    print("  ✓ End-to-end timing and flow")
    print("=" * 70)


if __name__ == "__main__":
    main()
