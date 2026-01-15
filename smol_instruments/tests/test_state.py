"""Tests for agent state tracking."""

import pytest
from agent_runtime.state import AgentState, StepRecord


class TestAgentState:
    """Test AgentState tracking."""
    
    def test_initialization(self):
        """State should initialize with defaults."""
        state = AgentState(task="Test task")
        
        assert state.task == "Test task"
        assert state.max_steps == 25
        assert len(state.steps) == 0
        assert len(state.patches_proposed) == 0
        assert len(state.files_read) == 0
    
    def test_custom_max_steps(self):
        """Custom max_steps should be respected."""
        state = AgentState(task="Test", max_steps=10)
        assert state.max_steps == 10
    
    def test_add_step(self):
        """Adding steps should update state."""
        state = AgentState(task="Test")
        
        state.add_step("read_file", {"path": "foo.py"}, {"lines": "content"})
        
        assert len(state.steps) == 1
        assert state.steps[0].tool_name == "read_file"
        assert state.steps[0].step_num == 1
        assert state.steps[0].error is False
    
    def test_add_error_step(self):
        """Error steps should be marked as such."""
        state = AgentState(task="Test")
        
        state.add_step("read_file", {"path": "missing.py"}, {"error": "FILE_NOT_FOUND"})
        
        assert len(state.steps) == 1
        assert state.steps[0].error is True
    
    def test_track_files_read(self):
        """Files read should be tracked."""
        state = AgentState(task="Test")
        
        state.add_step("read_file", {"path": "foo.py"}, {"lines": "content"})
        state.add_step("read_file_snippet", {"path": "bar.py"}, {"lines": "content"})
        
        assert "foo.py" in state.files_read
        assert "bar.py" in state.files_read
        assert len(state.files_read) == 2
    
    def test_track_patches_proposed(self):
        """Patches proposed should be tracked."""
        state = AgentState(task="Test")
        
        state.add_step("propose_patch_unified", {"intent": "fix"}, {"patch_id": "patch_123"})
        
        assert "patch_123" in state.patches_proposed
    
    def test_track_patches_applied(self):
        """Patches applied should be tracked."""
        state = AgentState(task="Test")
        
        result = {
            "ok": True,
            "patch_id": "patch_123",
            "files_changed": ["foo.py", "bar.py"]
        }
        state.add_step("apply_patch", {"patch_id": "patch_123"}, result)
        
        assert "patch_123" in state.patches_applied
        assert "foo.py" in state.files_modified
        assert "bar.py" in state.files_modified
    
    def test_track_commands_run(self):
        """Commands run should be tracked."""
        state = AgentState(task="Test")
        
        state.add_step("run_cmd", {"cmd": "pytest"}, {"exit": 0})
        state.add_step("run_tests", {"test_cmd": "npm test"}, {"exit": 0})
        
        assert "pytest" in state.commands_run
        assert "npm test" in state.commands_run
    
    def test_steps_remaining(self):
        """steps_remaining should be calculated correctly."""
        state = AgentState(task="Test", max_steps=10)
        
        assert state.steps_remaining == 10
        
        state.add_step("read_file", {}, {})
        assert state.steps_remaining == 9
        
        state.add_step("read_file", {}, {})
        assert state.steps_remaining == 8
    
    def test_max_steps_reached(self):
        """max_steps_reached should be accurate."""
        state = AgentState(task="Test", max_steps=3)
        
        assert state.max_steps_reached is False
        
        state.add_step("read_file", {}, {})
        state.add_step("read_file", {}, {})
        assert state.max_steps_reached is False
        
        state.add_step("read_file", {}, {})
        assert state.max_steps_reached is True
    
    def test_get_last_steps(self):
        """get_last_steps should return correct steps."""
        state = AgentState(task="Test")
        
        for i in range(10):
            state.add_step(f"tool_{i}", {}, {})
        
        last_3 = state.get_last_steps(3)
        assert len(last_3) == 3
        assert last_3[0].tool_name == "tool_7"
        assert last_3[1].tool_name == "tool_8"
        assert last_3[2].tool_name == "tool_9"
    
    def test_get_last_steps_fewer_than_n(self):
        """get_last_steps should handle fewer steps than requested."""
        state = AgentState(task="Test")
        
        state.add_step("tool_1", {}, {})
        state.add_step("tool_2", {}, {})
        
        last_5 = state.get_last_steps(5)
        assert len(last_5) == 2
    
    def test_summary_compact(self):
        """Compact summary should be minimal."""
        state = AgentState(task="Test task", max_steps=10)
        
        state.add_step("read_file", {}, {"lines": "content"})
        state.add_step("propose_patch_unified", {}, {"error": "VALIDATION_FAILED"})
        
        summary = state.summary(compact=True)
        
        assert "2/10" in summary
        assert "read_file" in summary
        assert "propose_patch_unified" in summary
        assert "✓" in summary  # Success marker
        assert "❌" in summary  # Error marker
    
    def test_summary_detailed(self):
        """Detailed summary should include more info."""
        state = AgentState(task="Test task", max_steps=10)
        
        state.add_step("read_file", {"path": "foo.py"}, {"lines": "content"})
        state.add_step("propose_patch_unified", {}, {"patch_id": "patch_123"})
        
        summary = state.summary(compact=False)
        
        assert "Test task" in summary
        assert "2/10" in summary
        assert "8 remaining" in summary
        assert "Files read: 1" in summary
        assert "Patches proposed: 1" in summary
    
    def test_to_dict(self):
        """to_dict should export full state."""
        state = AgentState(task="Test", max_steps=5)
        
        state.add_step("read_file", {"path": "foo.py"}, {"lines": "content"})
        
        exported = state.to_dict()
        
        assert exported["task"] == "Test"
        assert exported["max_steps"] == 5
        assert len(exported["steps"]) == 1
        assert exported["steps"][0]["tool"] == "read_file"
        assert "foo.py" in exported["files_read"]


class TestStepRecord:
    """Test StepRecord dataclass."""
    
    def test_to_dict(self):
        """StepRecord should serialize to dict."""
        from datetime import datetime
        
        step = StepRecord(
            step_num=1,
            tool_name="read_file",
            arguments={"path": "foo.py"},
            result={"lines": "content"},
            error=False
        )
        
        exported = step.to_dict()
        
        assert exported["step"] == 1
        assert exported["tool"] == "read_file"
        assert exported["args"] == {"path": "foo.py"}
        assert exported["error"] is False
        assert "timestamp" in exported
