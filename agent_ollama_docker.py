import os
from smolagents import CodeAgent, OpenAIModel

# Point smolagents at Ollama's OpenAI-compatible endpoint.
# Typical local Ollama base URL is http://localhost:11434/v1
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")

# Use whatever model name you already have pulled in Ollama, e.g.:
#   llama3.1:8b-instruct, qwen2.5-coder:14b, mistral, etc.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct-q8_0")


# Ollama usually doesn't require an API key for local usage; keep it blank.
model = OpenAIModel(
    model_id=OLLAMA_MODEL,
    api_base=OLLAMA_API_BASE,
    api_key=os.getenv("OLLAMA_API_KEY", ""),  # safe default
)

# CodeAgent will have the LLM write Python code;
# executor_type="docker" runs that code in a Docker sandbox.
agent = CodeAgent(
    tools=[],                 # keep it minimal; add tools later
    model=model,
    add_base_tools=True,      # handy defaults (optional)
    executor_type="docker",   # key part: sandbox code execution
)

result = agent.run(
    "Write Python code to compute the first 25 prime numbers, "
    "then print them and also print their sum."
)

print("\n=== FINAL ANSWER ===")
print(result)
