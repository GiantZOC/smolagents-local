"""
Plan Customization with Phoenix Telemetry in Docker Sandbox

This script combines:
1. Docker sandbox isolation from ollama_sandbox_phoenix_test.py
2. Plan customization/approval workflow from smolagents examples
3. Phoenix telemetry for observability

How it works:
    1. Agent runs in isolated Docker container
    2. After creating a plan, execution pauses for user approval
    3. User can approve, modify, or cancel the plan
    4. All interactions are traced to Phoenix
    5. Sandbox is cleaned up after execution

Usage:
    # Start Phoenix:
    docker-compose up -d
    
    # Run this script from your HOST machine:
    python ollama_sandbox_phoenix_plan_test.py
    
    # View traces with plan customization details:
    http://localhost:6006/projects/
"""

from sandbox_manager import DockerSandbox

# Create sandbox with Phoenix telemetry enabled
sandbox = DockerSandbox(enable_phoenix=True)

try:
    # Define the agent code to run in the sandbox
    # This includes plan customization callbacks
    agent_code = """
from smolagents import CodeAgent, LiteLLMModel, PlanningStep


def display_plan(plan_content):
    '''Display the plan in a formatted way'''
    print("\\n" + "=" * 60)
    print("🤖 AGENT PLAN CREATED")
    print("=" * 60)
    print(plan_content)
    print("=" * 60)


def get_user_choice():
    '''Get user's choice for plan approval'''
    while True:
        choice = input("\\nChoose an option:\\n1. Approve plan\\n2. Modify plan\\n3. Cancel\\nYour choice (1-3): ").strip()
        if choice in ["1", "2", "3"]:
            return int(choice)
        print("Invalid choice. Please enter 1, 2, or 3.")


def get_modified_plan(original_plan):
    '''Allow user to modify the plan'''
    print("\\n" + "-" * 40)
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
    modified_plan = "\\n".join(lines[:-2])
    return modified_plan if modified_plan.strip() else original_plan


def interrupt_after_plan(memory_step, agent):
    '''
    Step callback that interrupts the agent after a planning step is created.
    This allows for user interaction to review and potentially modify the plan.
    '''
    if isinstance(memory_step, PlanningStep):
        print("\\n🛑 Agent interrupted after plan creation...")

        # Display the created plan
        display_plan(memory_step.plan)

        # Get user choice
        choice = get_user_choice()

        if choice == 1:  # Approve plan
            print("✅ Plan approved! Continuing execution...")
            # Don't interrupt - let the agent continue
            return

        elif choice == 2:  # Modify plan
            # Get modified plan from user
            modified_plan = get_modified_plan(memory_step.plan)

            # Update the plan in the memory step
            memory_step.plan = modified_plan

            print("\\nPlan updated!")
            display_plan(modified_plan)
            print("✅ Continuing with modified plan...")
            # Don't interrupt - let the agent continue with modified plan
            return

        elif choice == 3:  # Cancel
            print("❌ Execution cancelled by user.")
            agent.interrupt()
            return


# Create the LLM model pointing to host Ollama
model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://host.docker.internal:11434",  # Access host Ollama from container
    api_key="",
    num_ctx=8192,
)

# Create agent with planning enabled and step callback
agent = CodeAgent(
    tools=[],
    model=model,
    add_base_tools=True,
    executor_type="local",  # Use local executor since we're already in a sandbox
    planning_interval=3,  # Create a plan every 3 steps
    step_callbacks={PlanningStep: interrupt_after_plan},
    max_steps=15,
    verbosity_level=1,  # Show agent thoughts
    name="planning_agent",
    description="Agent that creates plans and requests user approval before execution",
)

# Define a task that will benefit from planning
task = \"\"\"Create a Python function that calculates the factorial of a number using recursion,
then use it to calculate the factorial of 10. After that, create an iterative version
and compare which one is more efficient for large numbers.\"\"\"

try:
    print("\\n" + "=" * 60)
    print("🚀 Starting Plan Customization Example in Sandbox")
    print("=" * 60)
    print(f"\\n📋 Task: {task}")
    print("\\n🤖 Agent starting execution...")

    # Run the agent - will pause when plan is created
    result = agent.run(task)

    # If we get here, the plan was approved and execution completed
    print("\\n" + "=" * 60)
    print("✅ Task completed successfully!")
    print("=" * 60)
    print("\\n📄 Final Result:")
    print("-" * 60)
    print(result)
    print("-" * 60)

except Exception as e:
    error_msg = str(e)
    if "interrupted" in error_msg.lower():
        print("\\n🛑 Agent execution was cancelled by user.")
        print("\\n💡 Note: To resume execution later, you could call:")
        print("   agent.run(task, reset=False)  # This preserves the agent's memory")
        
        # Show current memory state
        print(f"\\n📚 Current memory contains {len(agent.memory.steps)} steps:")
        for i, step in enumerate(agent.memory.steps):
            step_type = type(step).__name__
            print(f"  {i + 1}. {step_type}")
    else:
        print(f"\\n❌ An error occurred: {e}")
        raise
"""

    # Run the code in the sandbox
    print("Starting agent execution in Docker sandbox with Phoenix telemetry...")
    print("This agent will pause when it creates a plan and ask for your approval.")
    print("=" * 70)
    
    output = sandbox.run_code(agent_code)
    
    print("\n=== Output from sandbox ===")
    print(output)
    print("=" * 70)
    
    print("\n✅ Agent execution completed!")
    print("📊 View detailed traces at: http://localhost:6006/projects/")
    print("\nYou can see:")
    print("  - Agent reasoning steps")
    print("  - Plan creation and modifications")
    print("  - User approval interactions")
    print("  - Code generation and execution")
    print("  - Tool calls and results")
    print("  - Timing and performance metrics")

finally:
    # Clean up the sandbox
    print("\nCleaning up sandbox...")
    sandbox.cleanup()
    print("Done!")
