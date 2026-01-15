"""Tests for tool instrumentation wrapper."""

import pytest
import copy
from smolagents import Tool

from agent_runtime.instrumentation import wrap_tools_with_instrumentation
from agent_runtime.state import AgentState
from agent_runtime.approval import ApprovalStore, set_approval_store, Approval


# Mock tool for testing
class MockTool(Tool):
    name = "mock_tool"
    description = "A mock tool for testing"
    inputs = {
        "value": {"type": "string", "description": "test value"}
    }
    output_type = "object"
    
    def forward(self, value: str):
        return {"result": value}


class MockErrorTool(Tool):
    name = "error_tool"
    description = "A tool that returns errors"
    inputs = {
        "error_type": {"type": "string", "description": "type of error to return"}
    }
    output_type = "object"
    
    def forward(self, error_type: str):
        return {
            "error": error_type,
            "message": f"Simulated {error_type} error"
        }


class MockExceptionTool(Tool):
    name = "exception_tool"
    description = "A tool that raises exceptions"
    inputs = {}
    output_type = "object"
    
    def forward(self):
        raise ValueError("Simulated exception")


@pytest.fixture
def state():
    """Create agent state for testing."""
    return AgentState(task="Test task", max_steps=10)


@pytest.fixture
def approval_store():
    """Create approval store for testing."""
    auto_approve = lambda proposal: Approval(approved=True)
    store = ApprovalStore(approval_callback=auto_approve)
    set_approval_store(store)
    return store


class TestInstrumentedToolMetadata:
    """Test that instrumentation preserves tool metadata."""
    
    def test_preserves_tool_metadata(self, state):
        """Should preserve original tool metadata after wrapping."""
        tool = MockTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        assert wrapped.name == "mock_tool"
        assert wrapped.description == "A mock tool for testing"
        assert wrapped.output_type == "object"
    
    def test_preserves_forward_signature(self, state):
        """Should preserve forward method signature."""
        tool = MockTool()
        original_forward = tool.forward
        
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        # forward method should be wrapped
        assert hasattr(wrapped.forward, '__wrapped__')
        
        # Should still be callable with same signature
        result = wrapped.forward(value="test")
        assert isinstance(result, dict)
    
    def test_tool_instance_is_same(self, state):
        """Wrapping should modify tool in-place, not create new instance."""
        tool = MockTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        # Should be the same instance
        assert wrapped is tool


class TestInstrumentedToolValidation:
    """Test input validation in wrapped tools."""
    
    def test_validates_paths(self, state):
        """Should validate path inputs."""
        class PathTool(Tool):
            name = "path_tool"
            description = "Tool with path"
            inputs = {"path": {"type": "string", "description": "file path"}}
            output_type = "object"
            
            def forward(self, path: str):
                return {"path": path}
        
        tool = PathTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        # Valid path should work
        result = wrapped.forward(path="src/main.py")
        assert "error" not in result
        
        # Invalid path should fail
        result = wrapped.forward(path="../etc/passwd")
        assert result["error"] == "VALIDATION_FAILED"
        assert "Path traversal" in result["message"]
    
    def test_validates_line_ranges(self, state):
        """Should validate line range inputs."""
        class RangeTool(Tool):
            name = "range_tool"
            description = "Tool with line range"
            inputs = {
                "start_line": {"type": "integer", "description": "start"},
                "end_line": {"type": "integer", "description": "end"}
            }
            output_type = "object"
            
            def forward(self, start_line: int, end_line: int):
                return {"start": start_line, "end": end_line}
        
        tool = RangeTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        # Valid range should work
        result = wrapped.forward(start_line=1, end_line=10)
        assert "error" not in result
        
        # Invalid range should fail
        result = wrapped.forward(start_line=0, end_line=10)
        assert result["error"] == "VALIDATION_FAILED"
        assert "Start line must be >= 1" in result["message"]
    
    def test_validates_commands(self, state, approval_store):
        """Should validate dangerous commands."""
        class CmdTool(Tool):
            name = "cmd_tool"
            description = "Tool with command"
            inputs = {"cmd": {"type": "string", "description": "command"}}
            output_type = "object"
            
            def forward(self, cmd: str):
                return {"cmd": cmd}
        
        tool = CmdTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        # Safe command should work
        result = wrapped.forward(cmd="pytest")
        assert "error" not in result
        
        # Dangerous command should be denied
        result = wrapped.forward(cmd="rm -rf /")
        assert result["error"] == "COMMAND_DENIED"
        assert "blocked by policy" in result["message"]


class TestInstrumentedToolExecution:
    """Test tool execution with instrumentation."""
    
    def test_successful_execution(self, state):
        """Should execute tool and record to state."""
        tool = MockTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward(value="test")
        
        assert result == {"result": "test"}
        assert len(state.steps) == 1
        assert state.steps[0].tool_name == "mock_tool"
        assert state.steps[0].error is False
    
    def test_error_result_recorded(self, state):
        """Should record error results to state."""
        tool = MockErrorTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward(error_type="FILE_NOT_FOUND")
        
        assert result["error"] == "FILE_NOT_FOUND"
        assert len(state.steps) == 1
        assert state.steps[0].error is True
    
    def test_exception_handling(self, state):
        """Should catch exceptions and return error dict."""
        tool = MockExceptionTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward()
        
        assert result["error"] == "TOOL_EXCEPTION"
        assert "Simulated exception" in result["message"]
        assert result["type"] == "ValueError"
        assert len(state.steps) == 1
        assert state.steps[0].error is True


class TestInstrumentedToolTruncation:
    """Test output truncation."""
    
    def test_truncates_large_output(self, state):
        """Should truncate large text outputs."""
        class LargeOutputTool(Tool):
            name = "large_tool"
            description = "Returns large output"
            inputs = {}
            output_type = "object"
            
            def forward(self):
                # Create large output
                large_text = "x" * 10000
                return {"lines": large_text}
        
        tool = LargeOutputTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward()
        
        # Should be truncated
        assert len(result["lines"]) < 10000
        assert result.get("truncated") is True
        assert "truncated:" in result["lines"]
    
    def test_no_truncation_flag_for_small_output(self, state):
        """Should not set truncated flag for small output."""
        tool = MockTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward(value="small")
        
        # Should not have truncated flag
        assert result.get("truncated") is not True
    
    def test_truncates_list_results(self, state):
        """Should truncate large list results."""
        class ListTool(Tool):
            name = "list_tool"
            description = "Returns list"
            inputs = {}
            output_type = "object"
            
            def forward(self):
                return [{"item": i} for i in range(200)]
        
        tool = ListTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward()
        
        # Should be truncated to 100 items + message
        assert len(result) <= 101


class TestInstrumentedToolRecoveryHints:
    """Test recovery hint generation."""
    
    def test_adds_recovery_hint_for_file_not_found(self, state):
        """Should add recovery hint for FILE_NOT_FOUND."""
        tool = MockErrorTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward(error_type="FILE_NOT_FOUND")
        
        assert "recovery_suggestion" in result
        assert result["recovery_suggestion"]["tool_call"]["name"] == "list_files"
    
    def test_no_hint_for_approval_required(self, state):
        """Should not add hint for APPROVAL_REQUIRED (no_retry)."""
        tool = MockErrorTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward(error_type="APPROVAL_REQUIRED")
        
        # Should not have recovery_suggestion (no_retry case)
        assert "recovery_suggestion" not in result
    
    def test_no_hint_for_unknown_error(self, state):
        """Should not add hint for unknown error types."""
        tool = MockErrorTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result = wrapped.forward(error_type="UNKNOWN_ERROR_TYPE")
        
        assert "recovery_suggestion" not in result


class TestWrapToolsFunction:
    """Test wrap_tools_with_instrumentation function."""
    
    def test_wraps_all_tools(self, state):
        """Should wrap all tools in list."""
        tools = [MockTool(), MockErrorTool()]
        
        wrapped = wrap_tools_with_instrumentation(tools, state)
        
        assert len(wrapped) == 2
        # Should still be Tool instances
        assert all(isinstance(t, Tool) for t in wrapped)
        # Should have wrapped forward methods
        assert all(hasattr(t.forward, '__wrapped__') for t in wrapped)
    
    def test_preserves_tool_names(self, state):
        """Should preserve names of wrapped tools."""
        tools = [MockTool(), MockErrorTool()]
        
        wrapped = wrap_tools_with_instrumentation(tools, state)
        
        names = [t.name for t in wrapped]
        assert "mock_tool" in names
        assert "error_tool" in names
    
    def test_all_share_same_state(self, state):
        """All wrapped tools should share the same state instance."""
        tools = [MockTool(), MockErrorTool()]
        
        wrapped = wrap_tools_with_instrumentation(tools, state)
        
        # Execute both tools
        wrapped[0].forward(value="test1")
        wrapped[1].forward(error_type="TEST_ERROR")
        
        # State should have both steps
        assert len(state.steps) == 2


class TestInstrumentedToolDeterminism:
    """Test that instrumentation doesn't break determinism."""
    
    def test_same_input_same_output(self, state):
        """Same input should produce same output."""
        tool = MockTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        result1 = wrapped.forward(value="test")
        
        # Reset state for second call
        state.steps.clear()
        
        result2 = wrapped.forward(value="test")
        
        assert result1 == result2
    
    def test_state_recording_consistent(self, state):
        """State recording should be consistent."""
        tool = MockTool()
        [wrapped] = wrap_tools_with_instrumentation([tool], state)
        
        wrapped.forward(value="test1")
        wrapped.forward(value="test2")
        wrapped.forward(value="test3")
        
        assert len(state.steps) == 3
        assert state.steps[0].tool_name == "mock_tool"
        assert state.steps[1].tool_name == "mock_tool"
        assert state.steps[2].tool_name == "mock_tool"
        
        # Check arguments were recorded
        assert state.steps[0].arguments == {"value": "test1"}
        assert state.steps[1].arguments == {"value": "test2"}
        assert state.steps[2].arguments == {"value": "test3"}
