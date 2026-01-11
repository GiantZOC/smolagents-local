"""
Example of using DockerSandbox with Phoenix telemetry integration.

This demonstrates the enhanced sandbox_manager.py that automatically:
1. Sets up Phoenix instrumentation in sandboxed containers
2. Connects sandbox containers to the Phoenix network
3. Traces all agent activities

Architecture:
    Host Machine (runs this script)
         │
         ├─> Creates sandbox containers (via sandbox_manager.py)
         │
    ┌────▼─────────────────┐       ┌──────────────────┐
    │ Agent Sandbox        │──────>│ Phoenix Server   │
    │ (isolated container) │ Trace │ (docker-compose) │
    └──────────────────────┘       └──────────────────┘

Usage:
    # 1. Start Phoenix:
    docker-compose up -d
    
    # 2. Run this script from your HOST machine:
    python phoenix_sandbox_example.py
    
    # 3. View traces at: http://localhost:6006/projects/
"""

from sandbox_manager import DockerSandbox

# Example 1: Basic usage with Phoenix enabled (default)
print("=" * 70)
print("Example 1: Running agent in sandbox WITH Phoenix telemetry")
print("=" * 70)
print("\nℹ️  This script runs on your HOST machine")
print("   It creates a SANDBOX container to run your agent code")
print("   The sandbox automatically sends traces to Phoenix\n")

sandbox = DockerSandbox(enable_phoenix=True)

try:
    agent_code = """
from smolagents import CodeAgent, LiteLLMModel

# Note: When using Phoenix-enabled sandbox, we access Ollama via host gateway
# The sandbox is on the smolagents-network, so we use host.docker.internal
model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://host.docker.internal:11434",
    api_key="",
    num_ctx=8192,
)

agent = CodeAgent(
    tools=[],
    model=model,
    add_base_tools=True,
    name="fibonacci_agent",
)

result = agent.run(
    "Calculate the 20th Fibonacci number",
)
print(f"\\nAgent result: {result}")
"""

    print("\n🔧 Creating sandbox with Phoenix integration...")
    output = sandbox.run_code(agent_code)
    print("\n📤 Sandbox output:")
    print(output)
    print("\n✅ Success! Check Phoenix UI at http://localhost:6006/projects/")

finally:
    print("\n🧹 Cleaning up sandbox...")
    sandbox.cleanup()


# Example 2: Running without Phoenix (for comparison)
print("\n\n" + "=" * 70)
print("Example 2: Running agent in sandbox WITHOUT Phoenix telemetry")
print("=" * 70)

sandbox_no_phoenix = DockerSandbox(enable_phoenix=False)

try:
    # Same code, but simpler - no Phoenix overhead
    simple_code = """
from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://localhost:11434",  # Direct access via host network
    api_key="",
    num_ctx=8192,
)

agent = CodeAgent(
    tools=[],
    model=model,
    add_base_tools=True,
)

result = agent.run("What is 2 + 2?")
print(f"\\nAgent result: {result}")
"""

    print("\n🔧 Creating sandbox WITHOUT Phoenix...")
    output = sandbox_no_phoenix.run_code(simple_code)
    print("\n📤 Sandbox output:")
    print(output)
    print("\n✅ Done! No traces sent to Phoenix.")

finally:
    print("\n🧹 Cleaning up sandbox...")
    sandbox_no_phoenix.cleanup()


# Example 3: Per-run Phoenix control
print("\n\n" + "=" * 70)
print("Example 3: Dynamic Phoenix control per execution")
print("=" * 70)

sandbox_dynamic = DockerSandbox(enable_phoenix=True)

try:
    test_code = """
from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://host.docker.internal:11434",
    api_key="",
    num_ctx=8192,
)

agent = CodeAgent(tools=[], model=model, add_base_tools=True)
result = agent.run("What is the capital of France?")
print(f"Result: {result}")
"""

    print("\n🔧 Run 1: WITH Phoenix (override default)...")
    output1 = sandbox_dynamic.run_code(test_code, setup_phoenix=True)
    print("✓ Traced in Phoenix")
    
    print("\n🔧 Run 2: WITHOUT Phoenix (override default)...")
    output2 = sandbox_dynamic.run_code(test_code, setup_phoenix=False)
    print("✓ Not traced")

finally:
    sandbox_dynamic.cleanup()


print("\n" + "=" * 70)
print("🎉 All examples completed!")
print("=" * 70)
print("\n📊 Phoenix Dashboard: http://localhost:6006/projects/")
print("   You should see traces from Examples 1 and 3 (first run)")
print("\n💡 Tips:")
print("   - Each sandbox creates a fresh, isolated container")
print("   - Phoenix automatically captures all agent steps")
print("   - Sandboxes are cleaned up after execution")
print("   - Security constraints prevent privilege escalation")
