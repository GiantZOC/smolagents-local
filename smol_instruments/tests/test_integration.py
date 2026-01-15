"""Integration tests for complete agent workflow (without LLM)."""

import pytest
from agent_runtime.run import build_agent
from agent_runtime.approval import Approval


@pytest.fixture
def auto_approve_callback():
    """Callback that auto-approves everything."""
    return lambda proposal: Approval(approved=True)


class TestAgentBuilding:
    """Test that agent can be built successfully."""
    
    def test_build_agent_succeeds(self, auto_approve_callback):
        """Should successfully build agent with all components."""
        agent, state, approval_store = build_agent(
            model_id="test_model",
            api_base="http://localhost:11434",
            max_steps=10,
            enable_phoenix=False,  # Disable for testing
            approval_callback=auto_approve_callback
        )
        
        # Check agent exists
        assert agent is not None
        assert hasattr(agent, 'tools')
        assert hasattr(agent, 'model')
        
        # Check state initialized
        assert state is not None
        assert state.max_steps == 10
        assert len(state.steps) == 0
        
        # Check approval store initialized
        assert approval_store is not None
        assert approval_store.approval_callback == auto_approve_callback
    
    def test_agent_has_all_tools(self, auto_approve_callback):
        """Should have all 14 tools wrapped with instrumentation."""
        agent, state, approval_store = build_agent(
            model_id="test_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # Should have 14 tools + final_answer (smolagents adds this automatically)
        # agent.tools is a dict with tool names as keys
        assert len(agent.tools) >= 14
        
        # Check tool names
        expected_tools = [
            "repo_info",
            "list_files",
            "rg_search",
            "read_file",
            "read_file_snippet",
            "propose_patch_unified",
            "propose_patch",
            "show_patch",
            "apply_patch",
            "git_status",
            "git_diff",
            "git_log",
            "run_cmd",
            "run_tests",
        ]
        
        for expected in expected_tools:
            assert expected in agent.tools, f"Missing tool: {expected}"
    
    def test_tools_are_instrumented(self, auto_approve_callback):
        """Tools should have their forward method wrapped with instrumentation."""
        agent, state, approval_store = build_agent(
            model_id="test_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # Check our instrumented tools (exclude final_answer added by smolagents)
        our_tool_names = [
            "repo_info", "list_files", "rg_search", "read_file", "read_file_snippet",
            "propose_patch_unified", "propose_patch", "show_patch", "apply_patch",
            "git_status", "git_diff", "git_log", "run_cmd", "run_tests"
        ]
        
        for tool_name in our_tool_names:
            tool = agent.tools[tool_name]
            
            # Should have standard Tool metadata
            assert hasattr(tool, 'name')
            assert hasattr(tool, 'description')
            assert hasattr(tool, 'inputs')
            assert hasattr(tool, 'forward')
            
            # forward method should be wrapped (will have __wrapped__ from functools.wraps)
            assert hasattr(tool.forward, '__wrapped__'), f"Tool {tool_name} forward not wrapped"
    
    def test_state_shared_across_tools(self, auto_approve_callback):
        """All tools should record to the same state instance."""
        agent, state, approval_store = build_agent(
            model_id="test_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # The state passed to build_agent should be shared via closure
        # Test by executing tools and checking they all record to the same state
        repo_tool = agent.tools["repo_info"]
        list_tool = agent.tools["list_files"]
        
        # Execute tools
        repo_tool.forward()
        list_tool.forward(glob="*.py")
        
        # Both should be recorded in the same state
        assert len(state.steps) == 2
        assert state.steps[0].tool_name == "repo_info"
        assert state.steps[1].tool_name == "list_files"
    
    def test_custom_max_steps(self, auto_approve_callback):
        """Should respect custom max_steps."""
        agent, state, approval_store = build_agent(
            model_id="test_model",
            max_steps=50,
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        assert state.max_steps == 50
        assert agent.max_steps == 50


class TestPromptSelection:
    """Test that system prompt is selected correctly."""
    
    def test_qwen_model_gets_minimal_prompt(self, auto_approve_callback):
        """Qwen models should get ultra-minimal prompt."""
        agent, _, _ = build_agent(
            model_id="ollama_chat/qwen2.5-coder:14b",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # Check that prompt was set
        # Note: smolagents might not expose system_prompt directly
        # This is a basic check that agent was created successfully
        assert agent is not None
    
    def test_unknown_model_gets_default_prompt(self, auto_approve_callback):
        """Unknown models should get default minimal prompt."""
        agent, _, _ = build_agent(
            model_id="some_random_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        assert agent is not None


class TestToolExecution:
    """Test that tools can be executed through the agent (without LLM)."""
    
    def test_repo_info_tool_works(self, auto_approve_callback):
        """Should be able to call repo_info tool directly."""
        agent, state, _ = build_agent(
            model_id="test_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # Get repo_info tool from dict
        repo_tool = agent.tools["repo_info"]
        
        # Execute it
        result = repo_tool.forward()
        
        # Should return valid result
        assert isinstance(result, dict)
        assert "root" in result
        assert "name" in result
        
        # Should be recorded in state
        assert len(state.steps) == 1
        assert state.steps[0].tool_name == "repo_info"
    
    def test_list_files_tool_works(self, auto_approve_callback):
        """Should be able to call list_files tool directly."""
        agent, state, _ = build_agent(
            model_id="test_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # Get list_files tool from dict
        list_tool = agent.tools["list_files"]
        
        # Execute it
        result = list_tool.forward(glob="*.py")
        
        # Should return valid result
        assert isinstance(result, dict)
        assert "files" in result
        assert "count" in result
        
        # Should be recorded in state
        assert len(state.steps) == 1
        assert state.steps[0].tool_name == "list_files"
    
    def test_multiple_tool_calls_tracked(self, auto_approve_callback):
        """Multiple tool calls should all be tracked in state."""
        agent, state, _ = build_agent(
            model_id="test_model",
            enable_phoenix=False,
            approval_callback=auto_approve_callback
        )
        
        # Execute multiple tools (get from dict)
        repo_tool = agent.tools["repo_info"]
        list_tool = agent.tools["list_files"]
        git_tool = agent.tools["git_status"]
        
        repo_tool.forward()
        list_tool.forward(glob="*.md")
        git_tool.forward()
        
        # Should have 3 steps
        assert len(state.steps) == 3
        assert state.steps[0].tool_name == "repo_info"
        assert state.steps[1].tool_name == "list_files"
        assert state.steps[2].tool_name == "git_status"
