"""
Hybrid Agentic RAG with Sandboxed Execution

Architecture:
    HOST: RAG retrieval, planning, approval, LLM inference, Phoenix telemetry
    SANDBOX: Code execution only (when agent generates Python code)

This implements:
    - Agentic RAG with custom retriever tool
    - Plan customization and user approval
    - Sandboxed code execution for safety
    - Full Phoenix observability

Usage:
    # Start Phoenix:
    docker-compose up -d
    
    # Run on host:
    python ollama_phoenix_rag_hybrid.py
    
    # View traces:
    http://localhost:6006/projects/
"""

from smolagents import CodeAgent, LiteLLMModel, PlanningStep, Tool
from sandbox_manager import DockerSandbox
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
import datasets
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
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
    Custom tool for semantic retrieval from knowledge base.
    This runs on the HOST (fast, no sandbox overhead).
    """
    name = "retriever"
    description = "Uses semantic search to retrieve the parts of transformers documentation that could be most relevant to answer your query."
    inputs = {
        "query": {
            "type": "string",
            "description": "The query to perform. This should be semantically close to your target documents. Use the affirmative form rather than a question.",
        }
    }
    output_type = "string"

    def __init__(self, docs, **kwargs):
        super().__init__(**kwargs)
        # Initialize the retriever with our processed documents
        print("  Initializing BM25 retriever...")
        self.retriever = BM25Retriever.from_documents(
            docs, k=10  # Return top 10 most relevant documents
        )
        print(f"  ✓ Retriever ready with {len(docs)} document chunks")

    def forward(self, query: str) -> str:
        """Execute the retrieval based on the provided query."""
        assert isinstance(query, str), "Your search query must be a string"

        print(f"\n🔍 Retrieving documents for query: '{query[:100]}...'")
        
        # Retrieve relevant documents
        docs = self.retriever.invoke(query)

        # Format the retrieved documents for readability
        result = "\nRetrieved documents:\n" + "".join(
            [
                f"\n\n===== Document {str(i)} =====\n" + doc.page_content
                for i, doc in enumerate(docs)
            ]
        )
        
        print(f"✓ Retrieved {len(docs)} documents")
        return result


def prepare_knowledge_base():
    """
    Prepare the knowledge base from HuggingFace documentation.
    This runs on the HOST (one-time setup).
    """
    print("\n📚 Preparing knowledge base...")
    
    # Load the Hugging Face documentation dataset
    print("  Loading HuggingFace documentation dataset...")
    knowledge_base = datasets.load_dataset("m-ric/huggingface_doc", split="train")
    
    # Filter to include only Transformers documentation
    print("  Filtering for Transformers docs...")
    knowledge_base = knowledge_base.filter(
        lambda row: row["source"].startswith("huggingface/transformers")
    )
    print(f"  ✓ Found {len(knowledge_base)} documents")
    
    # Convert dataset entries to Document objects with metadata
    print("  Converting to Document objects...")
    source_docs = [
        Document(
            page_content=doc["text"],
            metadata={"source": doc["source"].split("/")[1]}
        )
        for doc in knowledge_base
    ]
    
    # Split documents into smaller chunks for better retrieval
    print("  Splitting documents into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,  # Characters per chunk
        chunk_overlap=50,  # Overlap between chunks to maintain context
        add_start_index=True,
        strip_whitespace=True,
        separators=["\n\n", "\n", ".", " ", ""],  # Priority order for splitting
    )
    docs_processed = text_splitter.split_documents(source_docs)
    
    print(f"✓ Knowledge base prepared with {len(docs_processed)} document chunks")
    return docs_processed


# ============================================================================
# Sandboxed Python Execution
# ============================================================================

class SandboxedPythonExecutor:
    """
    Custom executor that runs Python code in isolated Docker sandbox.
    """
    
    def __init__(self):
        self.sandbox = None
        self.execution_count = 0
    
    def execute(self, code: str) -> str:
        """Execute Python code in a fresh sandbox container."""
        self.execution_count += 1
        print(f"\n🔒 Executing code in isolated sandbox (execution #{self.execution_count})...")
        
        # Create fresh sandbox for this execution
        self.sandbox = DockerSandbox(enable_phoenix=True)
        
        try:
            result = self.sandbox.run_code(code)
            print("✓ Sandbox execution completed")
            return result if result else ""
            
        except Exception as e:
            error_msg = f"Sandbox execution failed: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
            
        finally:
            if self.sandbox:
                self.sandbox.cleanup()
                self.sandbox = None
    
    def __del__(self):
        """Ensure cleanup on object destruction"""
        if self.sandbox:
            self.sandbox.cleanup()


# ============================================================================
# Main Execution
# ============================================================================

def main():
    print("=" * 70)
    print("🚀 HYBRID AGENTIC RAG: Host Retrieval + Sandboxed Execution")
    print("=" * 70)
    
    # Setup Phoenix telemetry on host
    setup_phoenix_host()
    
    # Prepare knowledge base (on HOST)
    docs_processed = prepare_knowledge_base()
    
    # Create retriever tool (runs on HOST)
    print("\n🔧 Creating retriever tool...")
    retriever_tool = RetrieverTool(docs_processed)
    
    # Create LLM model (runs on HOST, connects to local Ollama)
    print("\n🧠 Initializing LLM model (host-side)...")
    model = LiteLLMModel(
        model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
        api_base="http://localhost:11434",
        api_key="",
        num_ctx=8192,
    )
    
    # Create sandboxed executor
    executor = SandboxedPythonExecutor()
    
    # Create agent with RAG + planning + approval (runs on HOST)
    print("🤖 Creating agentic RAG agent...")
    agent = CodeAgent(
        tools=[retriever_tool],  # RAG retrieval tool
        model=model,
        add_base_tools=True,  # Includes Python interpreter (we'll override)
        planning_interval=3,  # Create plan every 3 steps
        step_callbacks={PlanningStep: interrupt_after_plan},
        max_steps=10,
        verbosity_level=2,  # Show detailed reasoning
        name="rag_agent",
        description="Agent with RAG retrieval and sandboxed code execution",
    )
    
    # Define task - something that requires both retrieval and computation
    task = """Using the Transformers documentation, find out how to use the pipeline() 
    function for text classification. Then write a Python code example that demonstrates 
    using it with a sample text. Explain what each parameter does."""
    
    print("\n" + "=" * 70)
    print("📋 TASK:")
    print(task)
    print("=" * 70)
    
    try:
        print("\n🎯 Starting agent execution...")
        print("   - Retrieval happens on HOST (fast)")
        print("   - Planning happens on HOST (interactive)")
        print("   - Code execution happens in SANDBOX (safe)")
        print()
        
        # Run agent
        result = agent.run(task)
        
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
            print("\n🛑 Agent execution was cancelled by user.")
            if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps'):
                print(f"\n📚 Current memory contains {len(agent.memory.steps)} steps")
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
    print("  ✓ RAG retrieval queries and results")
    print("  ✓ Agent reasoning and planning")
    print("  ✓ User approval decisions")
    print("  ✓ Sandboxed code executions")
    print("  ✓ End-to-end RAG workflow")
    print("=" * 70)


if __name__ == "__main__":
    main()
