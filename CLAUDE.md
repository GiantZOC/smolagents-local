# smolagent ReAct Implementation for Low-Power LLMs

## Project Goal

Build a production-ready coding agent using smolagents primitives, optimized for local low-power models (7B-14B params). **All enforcement in Python, not prompts.**

## Core Architecture Principles

1. **Keep smolagents loop** - Instrument it via `InstrumentedTool`, don't replace it
2. **Python enforcement only** - Validation, approval, safety live in code, never in prompts
3. **Recovery hints, not auto-retry** - Return suggestions, let model choose
4. **Phoenix observability** - Every tool/sandbox op traced with spans

## Tech Stack

- **smolagents** 0.3.0+ (ToolCallingAgent with native loop)
- **LiteLLM** (Ollama integration for local models)
- **OpenTelemetry + Phoenix** (tracing/observability)
- **Docker** (sandbox for patch validation)
- Python 3.10+

## Implementation Order

**DO NOT start coding until you understand this sequence:**

1. **Foundation first** (no LLM): validation.py → state.py → approval.py
2. **Tools second** (no LLM): files, search, git, shell, patch
3. **Instrumentation third**: InstrumentedTool wrapper + Phoenix setup
4. **Integration last**: prompts + run.py with real Ollama

**Run tests after each phase.** Don't move forward until current phase tests pass.

## Critical Implementation Rules

### InstrumentedTool Wrapper
```python
# MUST use object.__setattr__ to avoid metadata mutation
object.__setattr__(self, 'name', tool.name)
object.__setattr__(self, 'inputs', copy.deepcopy(tool.inputs))
```

### Truncation
```python
# MUST return (str, bool) tuple to track actual truncation
def truncate_output(text, ...) -> Tuple[str, bool]:
    return (text, was_truncated)
```

### Phoenix Setup
```python
# MUST set global provider or spans go nowhere
trace.set_tracer_provider(tracer_provider)
```

### Span Naming
```python
# Use tool_wrapped.<name> to avoid collision with SmolagentsInstrumentor
with tracer.start_as_current_span(f"tool_wrapped.{self.name}"):
```

## Key Files & Their Purpose

| File | Purpose | Test Before Moving On |
|------|---------|----------------------|
| `tools/validation.py` | Input validators, returns tuples | Path traversal blocked? |
| `state.py` | AgentState with loop detection | Counter increments? |
| `approval.py` | ApprovalStore for patches/commands | is_approved() works? |
| `instrumentation.py` | InstrumentedTool wrapper | Spans created? Metadata not shared? |
| `tools/patch.py` | propose_patch_unified + apply | Sandbox validation works? |
| `policy.py` | CommandPolicy (ALLOW/APPROVE/DENY) | rm -rf denied? pytest allowed? |
| `sandbox.py` | Docker with repo mounted at /workspace | git apply --check works? |
| `run.py` | Agent builder + CLI | 2-step task completes? |

## Commands

```bash
# Build sandbox
docker build -t smolagent-sandbox:latest -f docker/Dockerfile.sandbox .

# Run tests (after each phase)
pytest tests/test_validation.py -v  # Phase 1
pytest tests/test_tools.py -v       # Phase 2
pytest tests/test_instrumentation.py -v  # Phase 4
pytest tests/test_agent_smoke.py -v # Phase 5 - MUST PASS

# Run agent
python -m agent_runtime.run "List Python files in this repo"

# Check Phoenix traces
# Visit http://localhost:6006/projects/
```

## Code Style

- **Validation**: Raise `ValidationError`, caught in InstrumentedTool
- **Error schema**: `{"error": "TYPE", "message": "...", "tool": "...", "context": {...}}`
- **Recovery hints**: Add `"recovery_suggestion"` to errors (not auto-execute)
- **Prompts**: Ultra-minimal (Qwen-style), ~50 tokens max

## Critical Anti-Patterns

❌ **NEVER** rely on prompts for safety ("Don't run rm -rf")  
✅ **ALWAYS** enforce in CommandPolicy.validate_command()

❌ **NEVER** auto-execute recovery actions  
✅ **ALWAYS** return recovery_suggestion for model to choose

❌ **NEVER** mutate tool metadata directly  
✅ **ALWAYS** use object.__setattr__() + deepcopy

❌ **NEVER** forget trace.set_tracer_provider()  
✅ **ALWAYS** set global provider in setup_phoenix_telemetry()

## Testing Checklist

Before claiming phase complete:

- [ ] Unit tests pass for that phase
- [ ] No shared references (test with `is not`)
- [ ] Error schema consistent across all tools
- [ ] Phoenix spans appear with correct attributes
- [ ] Smoke test passes (Phase 5 only)

## Success Criteria

Implementation is done when:

1. `pytest tests/test_agent_smoke.py -v` passes (all green)
2. Agent completes 5-step task without crashes
3. Phoenix shows `tool_wrapped.*` spans with attributes
4. Dangerous commands blocked (try `rm -rf /`)
5. Approval gates work (try `pip install numpy`)
6. Recovery hints appear in errors (try nonexistent file)

## Key Design Files

Detailed plans in:
- `new_agent_plan_fixed.md` - Full implementation spec with all fixes applied
- `IMPLEMENTATION_FIXES.md` - Critical bug fixes and why they matter
- `REMAINING_FIXES.md` - Edge case hardening (smoke tests, loop detection, etc.)

## When to Ask for Help

- smolagents API unclear (e.g., step_callbacks signature)
- Ollama connection errors (is it running?)
- Phoenix shows no spans (tracer provider issue?)
- Tests fail for unclear reason (might be upstream bug)

## Notes

- Model temperature: 0.1 (deterministic tool calls)
- Max tokens: 1024 (prevent rambling)
- Default model: qwen2.5-coder:14b (or 7b for testing)
- Max steps: 25 (prevent loops)
