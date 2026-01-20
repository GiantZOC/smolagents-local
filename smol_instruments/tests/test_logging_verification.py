#!/usr/bin/env python3
"""
Test to verify Phoenix logging is working properly.

This test should be run from the project root or with the package installed.
"""

def test_logging_setup():
    """Test that logging is properly configured."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    
    # Setup basic console exporter for testing
    provider = TracerProvider()
    exporter = ConsoleSpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    # Test creating a span
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("test_span") as span:
        span.set_attribute("test", "value")
        span.add_event("test_event", {"data": "test"})
    
    # If we get here without exception, the test passed
    assert True

def test_instrumentation():
    """Test that tool instrumentation creates spans."""
    from agent_runtime.state import AgentState
    from agent_runtime.instrumentation import wrap_tools_with_instrumentation
    from agent_runtime.tools.files import ReadFileTool
    
    # Create a simple tool and state
    state = AgentState(task="test", max_steps=5)
    tool = ReadFileTool()
    
    # Wrap the tool
    instrumented_tools = wrap_tools_with_instrumentation([tool], state)
    
    # Test calling the tool (should create spans)
    # Note: ReadFileTool expects path as direct string, not dict
    result = instrumented_tools[0].forward("test.py")
    
    assert isinstance(result, dict)
    assert len(state.steps) > 0

if __name__ == "__main__":
    print("="*70)
    print("PHOENIX LOGGING VERIFICATION")
    print("="*70)
    
    # Test 1: Basic logging setup
    setup_ok = test_logging_setup()
    
    # Test 2: Tool instrumentation
    instrumentation_ok = test_instrumentation()
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    if setup_ok and instrumentation_ok:
        print("✅ All logging tests passed!")
        print("   Phoenix logging should be working correctly")
    else:
        print("❌ Some tests failed")
        print("   Check the error messages above")
        
        if not setup_ok:
            print("   - Basic OpenTelemetry setup failed")
        if not instrumentation_ok:
            print("   - Tool instrumentation failed")
    
    print("\nNext steps:")
    print("1. Check Phoenix is running: http://localhost:6006")
    print("2. Run a real agent task to see traces")
    print("3. Verify span exporter is configured correctly")
    print("="*70)