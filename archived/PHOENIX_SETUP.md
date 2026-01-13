# Phoenix Rise Integration with Smolagents

This project integrates [Phoenix by Arize AI](https://github.com/Arize-ai/phoenix) for telemetry and observability of smolagents runs.

## Architecture

```
┌─────────────────┐
│   Your Host     │  Runs sandbox_manager.py
│    Machine      │  
└────────┬────────┘
         │
         │ Creates sandbox containers
         │ (via Docker API)
         ▼
┌─────────────────┐         ┌─────────────────┐
│ Agent Sandbox   │────────▶│ Phoenix Server  │
│  (Container)    │ Traces  │  (Container)    │
│                 │         │                 │
│ - Runs agent    │         │ - Collects data │
│ - Phoenix SDK   │         │ - Shows UI      │
│ - Isolated      │         │                 │
└─────────────────┘         └─────────────────┘
         │
         │ Access Ollama
         ▼
┌─────────────────┐
│  Ollama (Host)  │
│  localhost:11434│
└─────────────────┘
```

**Components:**
1. **Your host machine**: Runs `sandbox_manager.py` which creates sandboxes
2. **Phoenix container**: Started by docker-compose, collects telemetry
3. **Agent sandbox containers**: Created dynamically by sandbox_manager.py, run your agents with Phoenix instrumentation
4. **Ollama**: Runs on your host, accessed by sandbox containers

## Prerequisites

- Docker and Docker Compose installed
- Ollama running on your host machine (for LLM inference)
- HF_TOKEN environment variable set (for Hugging Face access)

## Quick Start


### 2. Start Phoenix server

```bash
docker-compose up -d
```

This starts only the Phoenix server on port 6006.

### 3. Run your script from the host

The enhanced `sandbox_manager.py` now automatically:
- Creates sandboxed Docker containers for your agents
- Instruments them with Phoenix telemetry
- Connects them to the Phoenix network
- Cleans them up after execution

```bash
# Run from your host machine
python phoenix_sandbox_example.py
```

The sandbox_manager will:
1. Build the agent-sandbox image (first time only)
2. Create a container with security constraints
3. Connect it to the smolagents-network
4. Inject Phoenix instrumentation
5. Execute your agent code
6. Clean up the container

### 4. View traces in Phoenix UI

Open your browser to: http://localhost:6006/projects/

You'll see detailed traces showing:
- Agent steps and reasoning
- Tool calls and their results
- LLM model interactions
- Timing and performance metrics
- Multi-agent orchestration (if using managed agents)

## Using Phoenix in Your Own Scripts

### Option 1: Using sandbox_manager.py (Recommended for production)

```python
from sandbox_manager import DockerSandbox

# Create sandbox with Phoenix enabled (default)
sandbox = DockerSandbox(enable_phoenix=True)

try:
    agent_code = """
from smolagents import CodeAgent, LiteLLMModel

model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:14b-instruct-q8_0",
    api_base="http://host.docker.internal:11434",  # Access Ollama on host
    api_key="",
    num_ctx=8192,
)

agent = CodeAgent(tools=[], model=model, add_base_tools=True)
result = agent.run("Your task here")
print(result)
"""
    
    # Phoenix instrumentation is automatically added!
    output = sandbox.run_code(agent_code)
    print(output)
    
finally:
    sandbox.cleanup()
```

**Note**: Phoenix instrumentation is automatically injected by `sandbox_manager.py` - you don't need to add it to your agent code!

### Option 2: Direct execution (for development/debugging)

If you want to run agents directly without sandboxing:

```python
from phoenix.otel import register
from openinference.instrumentation.smolagents import SmolagentsInstrumentor

# Set up Phoenix instrumentation
register()
SmolagentsInstrumentor().instrument()

# Now run your agents normally - they'll be automatically traced!
```

## Docker Compose Configuration

The `docker-compose.yml` is minimal - it only runs Phoenix:

### Phoenix Service
- **Ports**: 6006 (UI), 4317 (OTLP gRPC), 4318 (OTLP HTTP)
- **Volume**: Persistent storage for traces
- **Health check**: Ensures Phoenix is ready
- **Network**: Creates `smolagents-network` for sandbox containers to join

### Sandbox Containers (created dynamically)

When you run `sandbox_manager.py`, it:
- Builds the `agent-sandbox` image from your Dockerfile
- Creates ephemeral containers with security constraints
- Connects them to the `smolagents-network`
- Runs your agent code in isolation
- Cleans up after execution

Security features:
- Runs as `nobody` user
- Memory limit: 512MB
- CPU quota: 50%
- Process limit: 100
- No new privileges
- All capabilities dropped

## Network Configuration

### With Phoenix (Bridge Network)

When Phoenix is enabled (`enable_phoenix=True`), sandboxes join the `smolagents-network`:

```python
# In your agent code, access Ollama via host gateway
model = LiteLLMModel(
    api_base="http://host.docker.internal:11434",  # Docker Desktop (Mac/Windows)
    # OR
    api_base="http://172.17.0.1:11434",  # Linux
)
```

### Without Phoenix (Host Network)

When Phoenix is disabled (`enable_phoenix=False`), sandboxes use host networking:

```python
# Direct localhost access
model = LiteLLMModel(
    api_base="http://localhost:11434",
)
```

### DockerSandbox Options

```python
# Default: Phoenix enabled, bridge network
sandbox = DockerSandbox()

# Disable Phoenix, use host network (faster, less isolation)
sandbox = DockerSandbox(enable_phoenix=False)

# Custom Phoenix endpoint
sandbox = DockerSandbox(
    enable_phoenix=True,
    phoenix_endpoint="http://phoenix:4317",
    network_name="smolagents_smolagents-network"
)
```

## Managing Services

```bash
# Start Phoenix
docker-compose up -d

# View Phoenix logs
docker-compose logs -f phoenix

# Stop Phoenix
docker-compose down

# Stop and remove volumes (deletes trace data)
docker-compose down -v

# Rebuild sandbox image after Dockerfile changes
docker build -t agent-sandbox .

# View running sandboxes
docker ps --filter ancestor=agent-sandbox

# Clean up stopped sandbox containers
docker container prune
```

## Troubleshooting

### Phoenix UI not accessible
- Check if Phoenix is running: `docker-compose ps`
- Check Phoenix logs: `docker-compose logs phoenix`
- Verify port 6006 is not in use: `lsof -i :6006`

### Traces not appearing
- Ensure `register()` and `SmolagentsInstrumentor().instrument()` are called before running agents
- Check smolagents logs: `docker-compose logs smolagents`
- Verify environment variable: `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:4317`

### Cannot connect to Ollama
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check the API base URL in your model configuration
- For Linux: Use `http://172.17.0.1:11434`
- For Docker Desktop (Mac/Windows): Use `http://host.docker.internal:11434`

### Permission errors in container
- The container runs as `nobody` user for security
- Ensure mounted files have appropriate permissions
- Check volume mounts in `docker-compose.yml`

## Phoenix Features

Phoenix provides:

- **Trace Inspection**: Detailed view of each agent step
- **Performance Metrics**: Latency, token usage, and throughput
- **Multi-Agent Tracking**: Visualize agent orchestration
- **Search & Filter**: Find specific runs or errors
- **Export**: Download traces for analysis

## Advanced Configuration

### Custom Phoenix Settings

Edit `docker-compose.yml` to add Phoenix environment variables:

```yaml
phoenix:
  environment:
    - PHOENIX_WORKING_DIR=/phoenix-data
    - PHOENIX_TELEMETRY_ENABLED=false  # Disable analytics
    - PHOENIX_PORT=6006
```

### Resource Limits

Adjust smolagents container limits in `docker-compose.yml`:

```yaml
smolagents:
  mem_limit: 1g        # Increase memory
  cpu_quota: 100000    # Increase CPU (100%)
  pids_limit: 200      # Increase process limit
```

## References

- [Phoenix Documentation](https://docs.arize.com/phoenix)
- [Phoenix GitHub](https://github.com/Arize-ai/phoenix)
- [Smolagents Documentation](https://huggingface.co/docs/smolagents)
- [OpenInference Instrumentation](https://github.com/Arize-ai/openinference)
