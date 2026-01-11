"""
Updated version of ollama_sandbox_test.py with Phoenix telemetry integration.

This is a drop-in replacement that adds telemetry to your existing sandbox workflow.

How it works:
    1. You run this script on your HOST machine
    2. sandbox_manager.py creates an isolated Docker container
    3. Phoenix instrumentation is automatically injected
    4. Agent runs in the sandbox and sends traces to Phoenix
    5. Sandbox is cleaned up after execution

Usage:
    # Start Phoenix:
    docker-compose up -d
    
    # Run this script from your HOST machine:
    python ollama_sandbox_phoenix_test.py
    
    # View traces:
    http://localhost:6006/projects/
"""

from sandbox_manager import DockerSandbox

# Create sandbox with Phoenix telemetry enabled
sandbox = DockerSandbox(enable_phoenix=True)

try:
    # Define the agent code to run in the sandbox
    agent_code = """
from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://host.docker.internal:11434",  # Access host Ollama from container
    api_key="",
    num_ctx=8192,
)

with CodeAgent(
    tools=[],
    model=model,
    add_base_tools=True,
    executor_type="local",  # Use local executor since we're already in a sandbox
    name="fibonacci_calculator",
    description="Agent that calculates Fibonacci numbers",
) as agent:
    result = agent.run(
        "Could you give me the 118th number in the Fibonacci sequence?",
    )
    print(result)
"""

    # Run the code in the sandbox
    print("Starting agent execution in Docker sandbox with Phoenix telemetry...")
    print("=" * 70)
    output = sandbox.run_code(agent_code)
    print("\n=== Output from sandbox ===")
    print(output)
    print("=" * 70)
    print("\n✅ Agent execution completed!")
    print("📊 View detailed traces at: http://localhost:6006/projects/")
    print("\nYou can see:")
    print("  - Agent reasoning steps")
    print("  - Code generation and execution")
    print("  - Tool calls and results")
    print("  - Timing and performance metrics")

finally:
    # Clean up the sandbox
    print("\nCleaning up sandbox...")
    sandbox.cleanup()
    print("Done!")
