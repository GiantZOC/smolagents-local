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
import time
import hashlib
import functools
from typing import Optional

from smolagents import ToolCallingAgent, LiteLLMModel, PromptTemplates

# Suppress Pydantic serialization warnings from LiteLLM/Ollama responses
warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')

from agent_runtime.config import Config
from agent_runtime.state import AgentState
from agent_runtime.approval import ApprovalStore, set_approval_store
from agent_runtime.instrumentation import (
    wrap_tools_with_instrumentation,
    setup_phoenix_telemetry
)
from .orchestrator import gate_aware_step_callback
from .tool_registry import get_tool_list_string

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
    approval_callback: Optional[callable] = None,
    enable_gates: bool = True
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
    
    # Add LLM call tracing
    from opentelemetry import trace
    original_run = agent.run
    
    # Debug: Check if tracing is properly set up
    current_tracer = trace.get_tracer_provider()
    if current_tracer is None or not hasattr(current_tracer, '_span_processors'):
        print("⚠️  Warning: OpenTelemetry tracer provider not properly configured")
        print("   Phoenix traces may not be exported")
    
    @functools.wraps(original_run)
    def traced_run(task):
        """Wrap agent.run to trace LLM calls."""
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span("llm_agent_run") as span:
            span.set_attribute("agent.task", task)
            span.set_attribute("agent.max_steps", max_steps)
            span.set_attribute("agent.tools_count", len(instrumented_tools))
            
            # Track LLM calls by wrapping the model
            if hasattr(model, '_make_call'):
                original_make_call = model._make_call
                
                @functools.wraps(original_make_call)
                def traced_make_call(*args, **kwargs):
                    with tracer.start_as_current_span("llm_call") as llm_span:
                        llm_span.set_attribute("llm.model", getattr(model, "model_id", "unknown"))
                        
                        # Capture prompt if available
                        if len(args) > 0:
                            prompt = args[0] if isinstance(args[0], str) else str(args[0])
                            llm_span.set_attribute("llm.prompt.length", len(prompt))
                            llm_span.set_attribute("llm.prompt.hash", hashlib.sha256(prompt.encode()).hexdigest()[:8])
                        
                        # Make the actual LLM call
                        start_time = time.time()
                        try:
                            result = original_make_call(*args, **kwargs)
                            duration_ms = (time.time() - start_time) * 1000
                            llm_span.set_attribute("llm.duration_ms", duration_ms)
                            
                            # Capture response
                            if isinstance(result, dict) and "choices" in result:
                                completion = result["choices"][0]["message"]["content"] if "message" in result["choices"][0] else ""
                                llm_span.set_attribute("llm.completion.length", len(completion))
                                llm_span.set_attribute("llm.completion.hash", hashlib.sha256(completion.encode()).hexdigest()[:8])
                                llm_span.set_attribute("llm.completion.preview", completion[:200] if completion else "")
                                
                                # Add full completion to span events for detailed analysis
                                if completion:
                                    llm_span.add_event("llm_completion", {
                                        "content": completion,
                                        "token_count": len(completion.split())
                                    })
                            
                            return result
                        except Exception as e:
                            llm_span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                            llm_span.set_attribute("llm.error", str(e))
                            raise
                
                model._make_call = traced_make_call
            
            # Call the original run method
            return original_run(task)
    
    agent.run = traced_run
    
    # Attach state and initialize gate tracking
    agent._smol_state = state
    
    if enable_gates:
        # Initialize gate tracker immediately
        from .orchestrator import GateTracker
        agent._gate_tracker = GateTracker(state)
        
        # Create a callback wrapper that smolagents expects
        class CallbackWrapper:
            def __init__(self, callback_func):
                self.callback_func = callback_func
            
            def callback(self, step, agent):
                return self.callback_func(step, agent)
        
        # Set up step callbacks properly
        agent.step_callbacks = CallbackWrapper(gate_aware_step_callback)
        
        print("✓ Gate enforcement enabled (Path A - memory injection)")
    
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
