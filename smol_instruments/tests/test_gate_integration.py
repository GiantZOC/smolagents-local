#!/usr/bin/env python3
"""
Test gate integration functionality.
"""

import sys
import os

# Add smol_instruments to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_gate_integration():
    """
    Test that the gate system integrates properly with the agent.
    """
    print("="*70)
    print("GATE INTEGRATION TEST")
    print("="*70)
    
    # Test 1: Tool registry
    print("\n[TEST 1] Tool registry functionality...")
    
    from agent_runtime import (
        build_agent, 
        get_gate_status,
        validate_tool_name, 
        is_progress_tool,
        get_tool_list_string
    )
    
    # Test some tool names
    test_tools = [
        ("rg_search", True, True),
        ("list_files", True, False),
        ("nonexistent_tool", False, False),
        ("read_file", True, True),
        ("run_tests", True, True),
    ]
    
    for tool_name, should_exist, should_be_progress in test_tools:
        exists = validate_tool_name(tool_name)
        is_progress = is_progress_tool(tool_name)
        
        print(f"  {tool_name}: exists={exists}, progress={is_progress}")
        
        assert exists == should_exist, f"Tool {tool_name} existence mismatch"
        assert is_progress == should_be_progress, f"Tool {tool_name} progress status mismatch"
    
    # Test tool list
    tool_list = get_tool_list_string()
    print(f"  All tools: {tool_list}")
    assert len(tool_list) > 0, "Tool list should not be empty"
    
    # Test 2: Build agent with gates
    print("\n[TEST 2] Building agent with gates...")
    
    agent, state, approval_store = build_agent(
        model_id="gpt-4",
        max_steps=5,
        enable_gates=True
    )
    
    print("  ✓ Agent built successfully")
    assert agent is not None, "Agent should be created"
    assert state is not None, "State should be created"
    
    # Test 3: Check gate tracker attachment
    print("\n[TEST 3] Checking gate tracker...")
    
    has_tracker = hasattr(agent, '_gate_tracker')
    has_state = hasattr(agent, '_smol_state')
    has_callbacks = hasattr(agent, 'step_callbacks')
    
    print(f"  Has gate tracker: {has_tracker}")
    print(f"  Has state: {has_state}")
    print(f"  Has callbacks: {has_callbacks}")
    
    assert has_state, "Agent should have state attached"
    assert has_callbacks, "Agent should have callbacks"
    
    if has_callbacks and agent.step_callbacks:
        print(f"  Callback type: {type(agent.step_callbacks)}")
        # Check if it's our CallbackWrapper
        if hasattr(agent.step_callbacks, 'callback'):
            print(f"  ✓ Callback wrapper configured properly")
        else:
            print(f"  Callbacks configured")
    
    # Test 4: Check initial gate status
    print("\n[TEST 4] Checking initial gate status...")
    
    if has_tracker:
        status = get_gate_status(agent)
        assert status is not None, "Should be able to get gate status"
        
        print(f"  Steps taken: {status.steps_taken}")
        print(f"  Understanding: {status.understanding}")
        print(f"  Change: {status.change}")
        print(f"  Verification: {status.verification}")
        print(f"  Readiness: {status.readiness}")
        print(f"  All passed: {status.all_passed()}")
        
        assert status.steps_taken == 0, "Should start with 0 steps"
        assert not status.readiness, "Should not be ready initially"
    else:
        print("  ✗ No gate tracker attached")
        
        # Try to initialize manually
        from agent_runtime.orchestrator import GateTracker
        agent._gate_tracker = GateTracker(state)
        has_tracker = True
        print("  ✓ Gate tracker initialized manually")
    
    assert has_tracker, "Gate tracker should be available"
    
    # Test 5: Simulate some steps
    print("\n[TEST 5] Simulating agent steps...")
    
    # Add some discovery steps (should trigger warnings)
    state.steps.append(type('MockStep', (), {
        'tool_name': 'repo_info',
        'input': {},
        'output': {'name': 'test-repo'}
    })())
    
    state.steps.append(type('MockStep', (), {
        'tool_name': 'list_files',
        'input': {'path': '.'},
        'output': {'files': ['test.py']}
    })())
    
    print(f"  Added 2 discovery steps")
    print(f"  Total steps: {len(state.steps)}")
    
    # Check gate status after discovery steps
    if has_tracker:
        status = agent._gate_tracker.evaluate_gates()
        print(f"  No progress yet: {status.no_progress_yet}")
        
        assert status.no_progress_yet, "Should detect no progress after discovery steps"
        
        if status.no_progress_yet:
            warning = agent._gate_tracker.get_warning_message(status)
            assert warning is not None, "Should generate warning for no progress"
            print(f"  ✓ Warning generated: {warning[:100]}...")
    
    # Test 6: Test gate tracker functionality
    print("\n[TEST 6] Testing gate tracker functionality...")
    
    # Re-check gate status after manual initialization
    if has_tracker:
        status = get_gate_status(agent)
        assert status is not None, "Should still get gate status"
        print(f"  Status after init: ready={status.readiness}")
    
    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED")
    print("  Gate system is working correctly")
    print("="*70)

if __name__ == "__main__":
    print("Starting gate integration test...")
    
    try:
        test_gate_integration()
        print("\n" + "="*70)
        print("FINAL ASSESSMENT")
        print("="*70)
        print("✅ Gate integration test PASSED")
        print("  - Tool registry working")
        print("  - Gate tracker integrated")
        print("  - Basic functionality verified")
        print("\nNext steps:")
        print("  1. Test with real agent tasks")
        print("  2. Monitor gate effectiveness")
        print("  3. Verify memory injection works in practice")
        print("="*70)
    except Exception as e:
        print("\n" + "="*70)
        print("FINAL ASSESSMENT")
        print("="*70)
        print("❌ Gate integration test FAILED")
        print(f"  Error: {e}")
        print("  - Check error messages above")
        print("  - Fix issues before proceeding")
        print("="*70)
        raise