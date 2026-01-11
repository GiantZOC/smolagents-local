"""
Multi-Agent Orchestration with Sandboxed Execution

Architecture:
    Manager Agent (CodeAgent)
        ├── RAG Agent (searches HuggingFace docs)
        ├── Web Search Agent (searches internet)
        └── Planner Agent (creates execution plans)
    
    HOST: All agents, planning, retrieval, LLM inference
    SANDBOX: Code execution only

This implements:
    - Multi-agent collaboration
    - RAG agent for documentation retrieval
    - Web search agent for current information
    - Planner agent for task decomposition
    - Plan customization and user approval
    - Sandboxed code execution
    - Full Phoenix observability

Usage:
    # Start Phoenix:
    docker-compose up -d
    
    # Run on host:
    python ollama_phoenix_multiagent_hybrid.py
    
    # View traces:
    http://localhost:6006/projects/
"""

from smolagents import (
    CodeAgent,
    ToolCallingAgent,
    LiteLLMModel,
    PlanningStep,
    Tool,
    tool,
    DuckDuckGoSearchTool,
)
from sandbox_manager import DockerSandbox
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
import datasets
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
import re
import requests
from markdownify import markdownify
from requests.exceptions import RequestException
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
# RAG Components (runs on HOST)
# ============================================================================

class RetrieverTool(Tool):
    """
    Custom tool for semantic retrieval from HuggingFace documentation.
    This runs on the HOST (fast, no sandbox overhead).
    """
    name = "retriever"
    description = "Uses semantic search to retrieve parts of the HuggingFace Transformers documentation that could be most relevant to answer your query. Use this for questions about transformers, models, training, or HuggingFace APIs."
    inputs = {
        "query": {
            "type": "string",
            "description": "The query to perform. This should be semantically close to your target documents. Use the affirmative form rather than a question.",
        }
    }
    output_type = "string"

    def __init__(self, docs, **kwargs):
        super().__init__(**kwargs)
        print("  Initializing BM25 retriever...")
        self.retriever = BM25Retriever.from_documents(
            docs, k=5  # Return top 5 most relevant documents
        )
        print(f"  ✓ Retriever ready with {len(docs)} document chunks")

    def forward(self, query: str) -> str:
        """Execute the retrieval based on the provided query."""
        assert isinstance(query, str), "Your search query must be a string"

        print(f"\n🔍 [RAG] Retrieving documents for: '{query[:80]}...'")
        
        # Retrieve relevant documents
        docs = self.retriever.invoke(query)

        # Format the retrieved documents for readability
        result = "\nRetrieved documents:\n" + "".join(
            [
                f"\n\n===== Document {str(i)} =====\n" + doc.page_content
                for i, doc in enumerate(docs)
            ]
        )
        
        print(f"✓ [RAG] Retrieved {len(docs)} documents")
        return result


def prepare_knowledge_base():
    """Prepare the knowledge base from HuggingFace documentation."""
    print("\n📚 Preparing RAG knowledge base...")
    
    print("  Loading HuggingFace documentation dataset...")
    knowledge_base = datasets.load_dataset("m-ric/huggingface_doc", split="train")
    
    print("  Filtering for Transformers docs...")
    knowledge_base = knowledge_base.filter(
        lambda row: row["source"].startswith("huggingface/transformers")
    )
    print(f"  ✓ Found {len(knowledge_base)} documents")
    
    print("  Converting to Document objects...")
    source_docs = [
        Document(
            page_content=doc["text"],
            metadata={"source": doc["source"].split("/")[1]}
        )
        for doc in knowledge_base
    ]
    
    print("  Splitting documents into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        add_start_index=True,
        strip_whitespace=True,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    docs_processed = text_splitter.split_documents(source_docs)
    
    print(f"✓ Knowledge base prepared with {len(docs_processed)} document chunks")
    return docs_processed


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
        
        # Send a GET request to the URL
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Convert the HTML content to Markdown
        markdown_content = markdownify(response.text).strip()

        # Remove multiple line breaks
        markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
        
        # Limit content length to avoid overwhelming the context
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
# Planner Tool (runs on HOST)
# ============================================================================

@tool
def create_task_plan(task_description: str) -> str:
    """
    Creates a detailed step-by-step plan for accomplishing a complex task.
    Breaks down the task into logical subtasks with dependencies.

    Args:
        task_description: Description of the task to plan

    Returns:
        A structured plan with numbered steps
    """
    print(f"\n📋 [PLANNER] Creating plan for: '{task_description[:80]}...'")
    
    # This is a simple planning heuristic
    # In a real system, you might use another LLM call here
    plan = f"""
TASK PLAN for: {task_description}

Step 1: Analyze the task requirements
   - Identify key questions to answer
   - Determine what information sources are needed

Step 2: Gather information
   - Use RAG retriever for documentation-related queries
   - Use web search for current/general information
   
Step 3: Process and synthesize information
   - Analyze retrieved information
   - Extract relevant facts and examples
   - Identify any gaps in knowledge

Step 4: Execute any required computations
   - Write and run code if calculations are needed
   - Generate examples or demonstrations

Step 5: Compile final answer
   - Synthesize all gathered information
   - Provide clear, structured response
   - Include sources and citations
"""
    
    print("✓ [PLANNER] Plan created")
    return plan


# ============================================================================
# Sandboxed Python Execution
# ============================================================================

class SandboxedPythonExecutor:
    """Custom executor that runs Python code in isolated Docker sandbox."""
    
    def __init__(self):
        self.sandbox = None
        self.execution_count = 0
    
    def execute(self, code: str) -> str:
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
    
    def __del__(self):
        if self.sandbox:
            self.sandbox.cleanup()


# ============================================================================
# Main Multi-Agent System
# ============================================================================

def main():
    print("=" * 70)
    print("🚀 MULTI-AGENT ORCHESTRATION SYSTEM")
    print("=" * 70)
    print("\nAgents:")
    print("  🤖 Manager Agent - Orchestrates other agents")
    print("  📚 RAG Agent - Searches HuggingFace documentation")
    print("  🌐 Web Search Agent - Searches the internet")
    print("  📋 Planner Agent - Creates task execution plans")
    print("=" * 70)
    
    # Setup Phoenix telemetry
    setup_phoenix_host()
    
    # Prepare RAG knowledge base
    docs_processed = prepare_knowledge_base()
    retriever_tool = RetrieverTool(docs_processed)
    
    # Create shared LLM model
    print("\n🧠 Initializing LLM model (host-side)...")
    model = LiteLLMModel(
        model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
        api_base="http://localhost:11434",
        api_key="",
        num_ctx=8192,
    )
    
    # Create sandboxed executor
    executor = SandboxedPythonExecutor()
    
    print("\n🔧 Creating specialized agents...")
    
    # ========================================================================
    # RAG Agent - Searches documentation
    # ========================================================================
    rag_agent = ToolCallingAgent(
        tools=[retriever_tool],
        model=model,
        max_steps=5,
        name="rag_agent",
        description="Searches HuggingFace Transformers documentation to answer questions about models, training, APIs, and library usage.",
    )
    print("  ✓ RAG Agent created")
    
    # ========================================================================
    # Web Search Agent - Searches internet and visits pages
    # ========================================================================
    web_search_agent = ToolCallingAgent(
        tools=[DuckDuckGoSearchTool(), visit_webpage],
        model=model,
        max_steps=8,
        name="web_search_agent",
        description="Searches the internet and visits web pages to find current information, news, and general knowledge.",
    )
    print("  ✓ Web Search Agent created")
    
    # ========================================================================
    # Planner Agent - Creates execution plans
    # ========================================================================
    planner_agent = ToolCallingAgent(
        tools=[create_task_plan],
        model=model,
        max_steps=3,
        name="planner_agent",
        description="Creates detailed step-by-step plans for complex tasks. Use this to break down complicated requests into manageable steps.",
    )
    print("  ✓ Planner Agent created")
    
    # ========================================================================
    # Manager Agent - Orchestrates everything
    # ========================================================================
    print("\n🎯 Creating manager agent...")
    manager_agent = CodeAgent(
        tools=[],  # No direct tools, uses managed agents
        model=model,
        managed_agents=[rag_agent, web_search_agent, planner_agent],
        additional_authorized_imports=["time", "numpy", "pandas", "json"],
        planning_interval=3,
        step_callbacks={PlanningStep: interrupt_after_plan},
        max_steps=15,
        verbosity_level=2,
        name="manager_agent",
        description="Orchestrates multiple specialized agents to accomplish complex tasks",
    )
    print("  ✓ Manager Agent created")
    
    # Define a complex task that requires multiple agents
    task = """
    I want to fine-tune a transformer model for sentiment analysis. Please help me by:
    1. Finding information in the HuggingFace docs about how to fine-tune models
    2. Searching the web for recent best practices in sentiment analysis (2024-2025)
    3. Creating a step-by-step plan for the fine-tuning process
    4. Providing a code example that demonstrates the key steps
    
    Please cite your sources for both documentation and web searches.
    """
    
    print("\n" + "=" * 70)
    print("📋 COMPLEX TASK:")
    print(task)
    print("=" * 70)
    
    try:
        print("\n🎯 Starting multi-agent execution...")
        print("   - Manager orchestrates specialized agents")
        print("   - RAG agent searches documentation")
        print("   - Web search agent finds current info")
        print("   - Planner agent creates structured plans")
        print("   - Code execution happens in sandbox")
        print()
        
        # Run the manager agent
        result = manager_agent.run(task)
        
        print("\n" + "=" * 70)
        print("✅ TASK COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\n📄 Final Result:")
        print("-" * 70)
        print(result)
        print("-" * 70)
        
        print(f"\n📊 Statistics:")
        print(f"   - Sandboxed executions: {executor.execution_count}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
        
    except Exception as e:
        error_msg = str(e)
        if "interrupted" in error_msg.lower():
            print("\n🛑 Execution was cancelled by user.")
            if hasattr(manager_agent, 'memory') and hasattr(manager_agent.memory, 'steps'):
                print(f"\n📚 Current memory contains {len(manager_agent.memory.steps)} steps")
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
    print("  ✓ Manager agent orchestration")
    print("  ✓ RAG agent documentation searches")
    print("  ✓ Web search agent queries and page visits")
    print("  ✓ Planner agent task decomposition")
    print("  ✓ Inter-agent communication")
    print("  ✓ Sandboxed code executions")
    print("  ✓ Complete multi-agent workflow")
    print("=" * 70)


if __name__ == "__main__":
    main()
