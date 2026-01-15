# Smol Instruments - Production Coding Agent

A production-ready coding agent built with smolagents, optimized for local low-power LLMs (7B-14B params) with comprehensive observability via Phoenix.

## Features

✅ **Python-enforced safety** - All validation, approval, and policy enforcement in code, not prompts  
✅ **14 instrumented tools** - Repo info, file operations, git, search, patch management, shell commands  
✅ **State tracking** - Full execution history with loop detection  
✅ **Approval gates** - Requires human approval for patches and risky commands  
✅ **Phoenix observability** - OpenTelemetry tracing for every tool and operation  
✅ **Recovery hints** - Intelligent suggestions when tools fail  
✅ **Environment-based config** - All settings via `.env` file  
✅ **119 passing tests** - Comprehensive test coverage

## Quick Start

### 1. Configuration

Copy the example config and customize:

```bash
cp .env.example .env
```

Edit `.env` to set your model and preferences:

```bash
# LLM Model Settings
MODEL_ID=ollama_chat/qwen2.5-coder:14b
MODEL_API_BASE=http://localhost:11434
MODEL_TEMPERATURE=0.1
MODEL_MAX_TOKENS=1024

# Agent Settings
AGENT_MAX_STEPS=25

# Phoenix Telemetry
PHOENIX_ENABLED=true
PHOENIX_ENDPOINT=http://localhost:6006/v1/traces
```

### 2. Install Dependencies

```bash
# From the smol_instruments directory
pip install smolagents litellm opentelemetry-sdk opentelemetry-exporter-otlp
```

### 3. Start Phoenix (Optional)

If you want observability traces:

```bash
docker-compose up phoenix  # or run Phoenix separately
```

### 4. Run the Agent

**Interactive mode:**
```bash
python -m agent_runtime.run
```

**Single task mode:**
```bash
python -m agent_runtime.run "List all Python files in this repo"
```

## Configuration Reference

All settings can be customized via environment variables in `.env`:

| Category | Setting | Default | Description |
|----------|---------|---------|-------------|
| **Model** | `MODEL_ID` | `ollama_chat/qwen2.5-coder:14b` | LiteLLM model identifier |
| | `MODEL_API_BASE` | `http://localhost:11434` | Ollama API endpoint |
| | `MODEL_TEMPERATURE` | `0.1` | Sampling temperature |
| | `MODEL_MAX_TOKENS` | `1024` | Max tokens per response |
| **Agent** | `AGENT_MAX_STEPS` | `25` | Max steps before stopping |
| **Phoenix** | `PHOENIX_ENABLED` | `true` | Enable telemetry |
| | `PHOENIX_ENDPOINT` | `http://localhost:6006/v1/traces` | OTLP endpoint |
| **Validation** | `VALIDATION_MAX_CHARS` | `5000` | Max chars for output |
| | `VALIDATION_MAX_LINES` | `200` | Max lines for output |
| | `VALIDATION_MAX_LINE_RANGE` | `1000` | Max line range for reads |
| **Truncation** | `TRUNCATION_MAX_CHARS` | `3000` | Truncate tool output at |
| | `TRUNCATION_MAX_LINES` | `150` | Truncate output lines at |
| | `TRUNCATION_MAX_LIST_ITEMS` | `100` | Truncate lists at |
| **Logging** | `LOG_LEVEL` | `INFO` | Python log level |
| | `SUPPRESS_WARNINGS` | `true` | Suppress Pydantic warnings |

## Architecture

### Components

```
agent_runtime/
├── config.py              # Environment-based configuration
├── run.py                 # CLI and agent builder
├── instrumentation.py     # Tool wrapper with tracing
├── state.py              # Execution state tracking
├── approval.py           # Human approval gates
├── policy.py             # Command policy & recovery hints
├── prompt.py             # Minimal prompts for Qwen
├── sandbox.py            # Patch validation sandbox
└── tools/
    ├── validation.py     # Input/output validators
    ├── repo.py          # Repository info & file listing
    ├── search.py        # Ripgrep code search
    ├── files.py         # File reading operations
    ├── git.py           # Git status/diff/log
    ├── patch.py         # Unified diff management
    └── shell.py         # Command execution
```

### Key Design Patterns

1. **Signature-preserving instrumentation**: Tools are wrapped by replacing their `forward()` method while preserving the original signature for smolagents validation

2. **Config-first**: All hardcoded values replaced with `Config.SETTING_NAME` lookups

3. **Python enforcement**: Safety policies enforced in code:
   - Path traversal blocked in validators
   - Dangerous commands denied by `CommandPolicy`
   - Line range limits checked before file reads

4. **Recovery hints**: Tools return structured errors with `recovery_suggestion` fields containing next-step recommendations

## Available Tools

| Tool | Purpose | Approval Required |
|------|---------|-------------------|
| `repo_info` | Get repo root and basic info | No |
| `list_files` | List files by glob pattern | No |
| `rg_search` | Search code with ripgrep | No |
| `read_file` | Read full file or line range | No |
| `read_file_snippet` | Find pattern and read context | No |
| `git_status` | Show git working tree status | No |
| `git_diff` | Show unstaged changes | No |
| `git_log` | Show recent commits | No |
| `propose_patch_unified` | Create unified diff patch | Yes (for apply) |
| `propose_patch` | Create simple patch | Yes (for apply) |
| `show_patch` | Display proposed patch | No |
| `apply_patch` | Apply patch to files | Yes |
| `run_cmd` | Execute shell command | Policy-based |
| `run_tests` | Run test commands | Policy-based |

## Command Policy

Shell commands are classified into three categories:

- **ALLOW**: Safe commands that run without approval (e.g., `pytest`, `ls`, `cat`)
- **REQUIRE_APPROVAL**: Risky commands needing approval (e.g., `pip install`, `git push`)
- **DENY**: Dangerous commands blocked entirely (e.g., `rm -rf`, `curl | sh`)

Edit `agent_runtime/policy.py` to customize the policy.

## Testing

Run the test suite:

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_tools.py -v

# With coverage
pytest tests/ --cov=agent_runtime --cov-report=html
```

**Test Coverage**: 119 tests covering all modules

## Observability

When `PHOENIX_ENABLED=true`, every tool call creates OpenTelemetry spans with:

- Tool name and arguments hash
- Input/output sizes
- Error types and recovery hints
- Execution duration
- Truncation flags

View traces at: http://localhost:6006/projects/

## Development

See `../CLAUDE.md` for detailed implementation guidelines and architecture decisions.

### Adding New Tools

1. Create tool class inheriting from `smolagents.Tool`
2. Define `inputs` dict with type and description
3. Implement `forward()` method with proper signature
4. Return dict (success) or dict with `"error"` key (failure)
5. Add to `raw_tools` list in `run.py`
6. Write unit tests in `tests/test_tools.py`

The instrumentation wrapper automatically adds:
- Input validation
- Output truncation
- Error normalization
- State recording
- Phoenix tracing

## Troubleshooting

**Ollama connection errors**: Ensure Ollama is running and the model is pulled:
```bash
ollama pull qwen2.5-coder:14b
ollama serve
```

**Pydantic warnings**: Set `SUPPRESS_WARNINGS=true` in `.env`

**Phoenix not showing traces**: Check that Phoenix is running and `PHOENIX_ENDPOINT` is correct

**Tests failing**: Ensure you're in the `smol_instruments` directory when running pytest

## License

See parent repository license.
