# !pip install 'smolagents[litellm]'
from sandbox_manager import DockerSandbox

# Create sandbox instance
sandbox = DockerSandbox()

try:
    # Define the agent code to run in the sandbox
    agent_code = """
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://localhost:11434",  # Use localhost since we're using host network mode
    api_key="",
    num_ctx=8192,
)

with CodeAgent(
    tools=[],
    model=model,
    add_base_tools=True,
    executor_type="local",  # Use local executor since we're already in a sandbox
) as agent:
    result = agent.run(
        "Could you give me the 118th number in the Fibonacci sequence?",
    )
    print(result)
"""

    # Run the code in the sandbox
    print("Starting agent execution in Docker sandbox...")
    output = sandbox.run_code(agent_code)
    print("\n=== Output from sandbox ===")
    print(output)

finally:
    # Clean up the sandbox
    print("\nCleaning up sandbox...")
    sandbox.cleanup()
    print("Done!")
