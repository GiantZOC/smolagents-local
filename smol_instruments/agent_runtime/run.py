"""
Agent runtime with InstrumentedTool wrapper.

Integrates all components:
- Tools with instrumentation
- State tracking
- Approval gates
- Phoenix telemetry
- LiteLLM/Ollama for local models
"""

import logging
import warnings
from typing import Optional

from smolagents import ToolCallingAgent, LiteLLMModel, PromptTemplates

# Suppress Pydantic serialization warnings from LiteLLM/Ollama responses
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')

from agent_runtime.config import Config
from agent_runtime.prompt import get_system_prompt
from agent_runtime.state import AgentState
from agent_runtime.approval import ApprovalStore, set_approval_store
from agent_runtime.instrumentation import (
    wrap_tools_with_instrumentation,
    setup_phoenix_telemetry
)

# Import raw tools
from agent_runtime.tools.repo import RepoInfoTool, ListFilesTool
from agent_runtime.tools.search import RipgrepSearchTool
from agent_runtime.tools.files import ReadFileTool, ReadFileSnippetTool
from agent_runtime.tools.patch import (
    ProposePatchUnifiedTool,
    ProposePatchTool,
    ShowPatchTool,
    ApplyPatchTool
)
from agent_runtime.tools.shell import RunCmdTool, RunTestsTool
from agent_runtime.tools.git import GitStatusTool, GitDiffTool, GitLogTool


logger = logging.getLogger(__name__)


def build_agent(
    model_id: Optional[str] = None,
    api_base: Optional[str] = None,
    max_steps: Optional[int] = None,
    enable_phoenix: Optional[bool] = None,
    approval_callback: Optional[callable] = None
) -> tuple:
    """
    Build agent with instrumented tools.
    
    Args:
        model_id: LiteLLM model ID (defaults to Config.MODEL_ID)
        api_base: API base URL (defaults to Config.MODEL_API_BASE)
        max_steps: Maximum steps for agent (defaults to Config.AGENT_MAX_STEPS)
        enable_phoenix: Whether to enable Phoenix telemetry (defaults to Config.PHOENIX_ENABLED)
        approval_callback: Optional custom approval callback
        
    Returns:
        (agent, state, approval_store) tuple
    """
    # Use config defaults if not provided
    if model_id is None:
        model_id = Config.MODEL_ID
    if api_base is None:
        api_base = Config.MODEL_API_BASE
    if max_steps is None:
        max_steps = Config.AGENT_MAX_STEPS
    if enable_phoenix is None:
        enable_phoenix = Config.PHOENIX_ENABLED
    
    # Setup Phoenix if enabled
    if enable_phoenix:
        try:
            setup_phoenix_telemetry()
        except Exception as e:
            logger.warning(f"Failed to setup Phoenix telemetry: {e}")
            logger.info("Continuing without Phoenix telemetry")
    
    # Create model
    model = LiteLLMModel(
        model_id=model_id,
        api_base=api_base,
        temperature=Config.MODEL_TEMPERATURE,
        max_tokens=Config.MODEL_MAX_TOKENS,
    )
    
    # Create raw tools
    raw_tools = [
        RepoInfoTool(),
        ListFilesTool(),
        RipgrepSearchTool(),
        ReadFileTool(),
        ReadFileSnippetTool(),
        ProposePatchUnifiedTool(),
        ProposePatchTool(),
        ShowPatchTool(),
        ApplyPatchTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitLogTool(),
        RunCmdTool(),
        RunTestsTool(),
    ]
    
    # Create state
    state = AgentState(task="", max_steps=max_steps)
    
    # Initialize ApprovalStore
    approval_store = ApprovalStore(approval_callback=approval_callback)
    set_approval_store(approval_store)
    
    # Wrap tools with instrumentation
    instrumented_tools = wrap_tools_with_instrumentation(raw_tools, state)
    
    # Build agent (use default prompt templates for now)
    # TODO: Customize prompts via PromptTemplates with all required templates
    agent = ToolCallingAgent(
        tools=instrumented_tools,
        model=model,
        add_base_tools=False,
        max_steps=max_steps,
    )
    
    print(f"✓ Agent built with {len(instrumented_tools)} instrumented tools")
    print(f"✓ Model: {model_id}")
    print(f"✓ Max steps: {max_steps}")
    
    return agent, state, approval_store


def run_task(
    task: str,
    model_id: Optional[str] = None,
    api_base: Optional[str] = None,
    max_steps: Optional[int] = None,
    enable_phoenix: Optional[bool] = None
):
    """
    Run agent on a task.
    
    Args:
        task: Task description
        model_id: LiteLLM model ID (defaults to Config.MODEL_ID)
        api_base: API base URL (defaults to Config.MODEL_API_BASE)
        max_steps: Maximum steps (defaults to Config.AGENT_MAX_STEPS)
        enable_phoenix: Whether to enable Phoenix telemetry (defaults to Config.PHOENIX_ENABLED)
    """
    # Setup logging
    logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), format='%(levelname)s: %(message)s')
    
    # Suppress verbose library logging
    if Config.SUPPRESS_WARNINGS:
        logging.getLogger('LiteLLM').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
    
    # Build agent
    print("Building agent...")
    agent, state, approval_store = build_agent(
        model_id=model_id,
        api_base=api_base,
        max_steps=max_steps,
        enable_phoenix=enable_phoenix
    )
    
    # Set task in state
    state.task = task
    
    # Run task
    print(f"\n{'='*70}")
    print(f"TASK: {task}")
    print(f"{'='*70}\n")
    
    result = agent.run(task)
    
    print(f"\n{'='*70}")
    print("RESULT:")
    print(f"{'='*70}")
    print(result)
    print()
    
    # Print state summary
    print(f"\n{'-'*70}")
    print("STATE SUMMARY:")
    print(f"{'-'*70}")
    print(state.summary(compact=False))
    print()
    
    if enable_phoenix:
        print("📊 View traces at: http://localhost:6006/projects/")
    
    return result, state


def interactive_cli():
    """Interactive CLI for running agent tasks."""
    import sys
    
    print("=" * 70)
    print("SMOL INSTRUMENTS - Coding Agent with Phoenix Observability")
    print("=" * 70)
    print()
    
    # Display configuration from Config
    Config.display()
    print()
    
    # Setup logging
    logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL), format='%(levelname)s: %(message)s')
    
    # Suppress verbose library logging
    if Config.SUPPRESS_WARNINGS:
        logging.getLogger('LiteLLM').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
    
    # Build agent once (uses Config defaults)
    print("Building agent...")
    agent, state, approval_store = build_agent()
    print()
    
    # Interactive loop
    while True:
        try:
            print("-" * 70)
            task = input("Enter task (or 'quit' to exit): ").strip()
            print()
            
            if not task:
                continue
            
            if task.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            # Reset state for new task
            state.steps.clear()
            state.task = task
            
            # Run task
            print(f"{'='*70}")
            print(f"TASK: {task}")
            print(f"{'='*70}\n")
            
            try:
                result = agent.run(task)
                
                print(f"\n{'='*70}")
                print("RESULT:")
                print(f"{'='*70}")
                print(result)
                print()
                
                # Print state summary
                print(f"\n{'-'*70}")
                print("STATE SUMMARY:")
                print(f"{'-'*70}")
                print(state.summary(compact=False))
                print()
                
            except Exception as e:
                print(f"\n❌ Error running task: {e}")
                import traceback
                traceback.print_exc()
                print()
        
        except KeyboardInterrupt:
            print("\n\nInterrupted. Type 'quit' to exit.")
            continue
        except EOFError:
            print("\nGoodbye!")
            break
    
    if Config.PHOENIX_ENABLED:
        print("\n📊 View traces at: http://localhost:6006/projects/")


if __name__ == "__main__":
    import sys
    
    # If task provided as argument, run once
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        run_task(task)
    else:
        # Otherwise start interactive CLI
        interactive_cli()
