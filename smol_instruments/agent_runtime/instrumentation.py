"""
InstrumentedTool wrapper - wraps tools by replacing their forward method.

FIXED: Preserve original forward() signature to pass smolagents validation.
"""

import time
import hashlib
import json
import functools
import inspect
from typing import Any, Dict, Optional, List
from smolagents import Tool
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from agent_runtime.config import Config
from agent_runtime.tools.validation import (
    validate_path,
    validate_line_range,
    truncate_output,
    ValidationError
)
from agent_runtime.policy import RecoveryHintGenerator, CommandPolicy
from agent_runtime.state import AgentState


tracer = trace.get_tracer(__name__)


def wrap_tools_with_instrumentation(tools: List[Tool], state: AgentState, 
                                    validation_config: Optional[Dict] = None) -> List[Tool]:
    """
    Wrap all tools with instrumentation by replacing their forward() methods.
    
    This approach preserves the Tool class structure and signatures that smolagents expects
    while adding instrumentation logic.
    
    Args:
        tools: List of Tool instances
        state: AgentState for recording
        validation_config: Optional per-tool validation rules
        
    Returns:
        List of instrumented Tool instances (same instances, modified)
    """
    for tool in tools:
        _instrument_tool(tool, state, validation_config or {})
    
    return tools


def _instrument_tool(tool: Tool, state: AgentState, validation_config: Dict):
    """
    Instrument a single tool by wrapping its forward method.
    
    Preserves the original signature so smolagents validation passes.
    
    Args:
        tool: Tool instance to instrument
        state: AgentState for recording
        validation_config: Validation config
    """
    # Store original forward method
    original_forward = tool.forward
    original_sig = inspect.signature(original_forward)
    
    # Create instrumented wrapper that preserves signature
    @functools.wraps(original_forward)
    def instrumented_forward(*args, **kwargs):
        """Instrumented forward with validation, tracing, truncation."""
        
        # Bind arguments to get clean kwargs dict
        bound_args = original_sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        call_kwargs = bound_args.arguments
        
        args_hash = _compute_args_hash(call_kwargs)
        
        with tracer.start_as_current_span(f"tool_wrapped.{tool.name}") as span:
            start_time = time.time()
            
            # Set comprehensive span attributes
            span.set_attribute("tool.name", tool.name)
            span.set_attribute("tool.args.hash", args_hash)
            span.set_attribute("tool.args.size", len(json.dumps(call_kwargs, default=str)))
            span.set_attribute("tool.args.details", json.dumps(call_kwargs, default=str))
            
            # Add tool-specific attributes for better filtering
            if tool.name in ["read_file", "read_file_snippet"]:
                span.set_attribute("tool.type", "file_read")
                if "path" in call_kwargs:
                    span.set_attribute("file.path", call_kwargs["path"])
            
            elif tool.name in ["rg_search"]:
                span.set_attribute("tool.type", "search")
                if "pattern" in call_kwargs:
                    span.set_attribute("search.pattern", call_kwargs["pattern"])
            
            elif tool.name in ["propose_patch_unified", "propose_patch"]:
                span.set_attribute("tool.type", "patch")
            
            elif tool.name in ["run_tests", "run_cmd"]:
                span.set_attribute("tool.type", "execution")
            
            else:
                span.set_attribute("tool.type", "other")
            
            # 1. Validate inputs
            validation_error = _validate_inputs(tool.name, call_kwargs)
            if validation_error:
                span.set_status(Status(StatusCode.ERROR, "Validation failed"))
                span.set_attribute("result.error_type", validation_error.get("error"))
                
                # Add recovery hint
                validation_error = _normalize_error(validation_error)
                
                # Record to state
                state.add_step(tool.name, call_kwargs, validation_error)
                
                return validation_error
            
            # 2. Call original tool
            try:
                result = original_forward(*args, **kwargs)
            except Exception as e:
                error_result = {
                    "error": "TOOL_EXCEPTION",
                    "tool": tool.name,
                    "message": str(e),
                    "type": type(e).__name__
                }
                
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute("result.error_type", "TOOL_EXCEPTION")
                
                # Record to state
                state.add_step(tool.name, call_kwargs, error_result)
                
                return error_result
            
            # 3. Truncate outputs
            result = _truncate_result(result)
            
            # 4. Normalize errors + add recovery hints
            result = _normalize_error(result)
            
            # 5. Record metrics
            duration_ms = (time.time() - start_time) * 1000
            
            if isinstance(result, dict):
                is_error = "error" in result
                
                span.set_attribute("result.ok", not is_error)
                if is_error:
                    span.set_status(Status(StatusCode.ERROR, result.get("error")))
                    span.set_attribute("result.error_type", result.get("error"))
                    
                    if "recovery_suggestion" in result:
                        hint = result["recovery_suggestion"]
                        if isinstance(hint, dict) and "tool_call" in hint:
                            span.set_attribute("policy.suggested_next_tool", 
                                             hint["tool_call"]["name"])
                
                # Output size metrics
                if any(k in result for k in ["lines", "text", "stdout_tail", "diff"]):
                    output_str = str(result.get("lines") or result.get("text") or 
                                   result.get("stdout_tail") or result.get("diff") or "")
                    span.set_attribute("output.chars", len(output_str))
                    span.set_attribute("output.truncated", result.get("truncated", False))
            
            elif isinstance(result, list):
                span.set_attribute("result.ok", True)
                span.set_attribute("output.items", len(result))
            
            span.set_attribute("duration_ms", duration_ms)
            
            # 6. Record to state
            state.add_step(tool.name, call_kwargs, result)
            
            # Add output details to span for traceability
            if isinstance(result, dict):
                if "lines" in result:
                    span.set_attribute("output.lines", len(result["lines"]))
                    span.set_attribute("output.first_line", result["lines"][0] if result["lines"] else "")
                    # Add lines as span events for full visibility
                    for i, line in enumerate(result["lines"][:5]):  # First 5 lines
                        span.add_event(f"output.line_{i}", {"content": line})
                elif "text" in result:
                    span.set_attribute("output.text.length", len(result["text"]))
                    span.set_attribute("output.text.preview", result["text"][:200] if result["text"] else "")
                    # Add full text as span event
                    span.add_event("output.full_text", {"content": result["text"]})
                elif "stdout_tail" in result:
                    span.set_attribute("output.stdout.preview", result["stdout_tail"][:200] if result["stdout_tail"] else "")
                    span.add_event("output.stdout", {"content": result["stdout_tail"]})
                elif "diff" in result:
                    span.set_attribute("output.diff.preview", result["diff"][:200] if result["diff"] else "")
                    span.add_event("output.diff", {"content": result["diff"]})
                elif "error" in result:
                    span.set_attribute("output.error", result["error"])
                    span.set_attribute("output.error_message", result.get("message", ""))
                    span.add_event("output.error_details", {"error": result["error"], "message": result.get("message", "")})
            
            return result
    
    # Replace the forward method (signature is preserved by @functools.wraps)
    tool.forward = instrumented_forward


# Helper functions

def _compute_args_hash(kwargs: Dict) -> str:
    """Compute stable hash of arguments for tracing."""
    sorted_args = json.dumps(kwargs, sort_keys=True, default=str)
    return hashlib.sha256(sorted_args.encode()).hexdigest()[:8]


def _validate_inputs(tool_name: str, kwargs: Dict) -> Optional[Dict[str, Any]]:
    """Validate inputs based on tool type."""
    try:
        # Path validation for file tools
        if "path" in kwargs:
            validate_path(kwargs["path"])
        
        # Line range validation
        if "start_line" in kwargs and "end_line" in kwargs:
            validate_line_range(kwargs["start_line"], kwargs["end_line"])
        
        # Command validation for shell tools
        if "cmd" in kwargs or "test_cmd" in kwargs:
            cmd = kwargs.get("cmd") or kwargs.get("test_cmd")
            
            # Check if command is dangerous (DENY)
            error = CommandPolicy.validate_command(cmd)
            if error:
                return {
                    "error": "COMMAND_DENIED",
                    "message": error,
                    "cmd": cmd
                }
        
        return None  # Valid
    
    except ValidationError as e:
        return {
            "error": "VALIDATION_FAILED",
            "message": str(e),
            "tool": tool_name,
            "arguments": kwargs
        }


def _normalize_error(result: Any) -> Dict[str, Any]:
    """Ensure errors follow schema and add recovery hints."""
    if not isinstance(result, dict):
        return result
    
    if "error" not in result:
        return result
    
    # Add recovery suggestion
    error_type = result["error"]
    hint = RecoveryHintGenerator.generate_hint(error_type, result)
    
    if hint:
        result["recovery_suggestion"] = hint
    
    return result


def _truncate_result(result: Any) -> Any:
    """Truncate large outputs."""
    if isinstance(result, dict):
        any_truncated = False
        
        # Truncate string values
        for key in ["lines", "text", "stdout_tail", "stderr_tail", "diff"]:
            if key in result and isinstance(result[key], str):
                truncated_text, was_truncated = truncate_output(
                    result[key], 
                    max_chars=Config.TRUNCATION_MAX_CHARS, 
                    max_lines=Config.TRUNCATION_MAX_LINES
                )
                result[key] = truncated_text
                any_truncated = any_truncated or was_truncated
        
        if any_truncated:
            result["truncated"] = True
    
    elif isinstance(result, list):
        max_items = Config.TRUNCATION_MAX_LIST_ITEMS
        if len(result) > max_items:
            result = result[:max_items]
            result.append({"message": f"Truncated to {max_items} items"})
    
    elif isinstance(result, str):
        truncated_text, was_truncated = truncate_output(result)
        result = truncated_text
    
    return result


# Phoenix Setup

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_phoenix_telemetry(endpoint: Optional[str] = None, use_batch: bool = True):
    """
    Setup Phoenix telemetry.
    
    Args:
        endpoint: Phoenix OTLP endpoint (defaults to Config.PHOENIX_ENDPOINT)
        use_batch: Whether to use BatchSpanProcessor
    """
    if endpoint is None:
        endpoint = Config.PHOENIX_ENDPOINT
    
    tracer_provider = TracerProvider()
    
    exporter = OTLPSpanExporter(endpoint)
    processor = BatchSpanProcessor(exporter) if use_batch else exporter
    
    tracer_provider.add_span_processor(processor)
    trace.set_tracer_provider(tracer_provider)
    
    print(f"✓ Phoenix telemetry enabled: {endpoint}")
