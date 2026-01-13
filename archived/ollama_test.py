# !pip install 'smolagents[litellm]'
from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0", # This model is a bit weak for agentic behaviours though
    api_base="http://localhost:11434", # replace with 127.0.0.1:11434 or remote open-ai compatible server if necessary
    api_key="", # replace with API key if necessary
    num_ctx=8192, # ollama default is 2048 which will fail horribly. 8192 works for easy tasks, more is better. Check https://huggingface.co/spaces/NyxKrage/LLM-Model-VRAM-Calculator to calculate how much VRAM this will need for the selected model.
)

with CodeAgent(
    tools=[],
    model=model,
    add_base_tools=True,
    executor_type="docker",
    # executor_kwargs={
    #     "host": "127.0.0.1",
    #     "port": 9005,  # pick any free port: 8889, 8890, 9000, etc.
    # },
) as agent:
    agent.run(
        "Could you give me the 118th number in the Fibonacci sequence?",
    )
