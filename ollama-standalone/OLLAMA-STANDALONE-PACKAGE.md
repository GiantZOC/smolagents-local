# Ollama Docker Standalone Package

This package provides a production-ready Ollama setup that can be integrated into any project.

## 📦 Package Contents

```
ollama-standalone/
├── docker-compose.yml          # Standalone Ollama service
├── Dockerfile                  # Custom Ollama with health checks
├── Makefile                    # Management commands
├── .env.example               # Configuration template
├── configs/
│   └── redis.conf             # Optional Redis config
└── README.md                  # This file
```

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# 1. Copy package to your project
cp -r ollama-standalone/ /path/to/your/project/

# 2. Navigate to directory
cd /path/to/your/project/ollama-standalone/

# 3. Start Ollama
docker compose up -d

# 4. Install models
docker exec ollama ollama pull llama3.2:3b
```

### Option 2: Makefile Commands

```bash
# Full setup (creates network, volumes, starts service)
make setup

# Install default models
make install-models

# Check health
make health

# View logs
make logs

# Stop service
make stop
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Key variables:
- `OLLAMA_PORT` - API port (default: 11434)
- `OLLAMA_KEEP_ALIVE` - Model keep-alive time (default: 24h)
- `OLLAMA_NUM_PARALLEL` - Parallel requests (default: 3)
- `OLLAMA_MAX_LOADED_MODELS` - Max models in memory (default: 2)
- `OLLAMA_VULKAN` - Enable Vulkan for AMD GPUs (default: 1)

### Resource Limits

Adjust in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: "8"
      memory: 16G
    reservations:
      cpus: "2"
      memory: 4G
```

## 🔧 Features

### 1. Custom Health Checks
- Built-in curl for reliable health monitoring
- Automatic health check every 30s
- 40s startup grace period

### 2. AMD GPU Support
- Pre-configured Vulkan drivers
- Device passthrough for `/dev/dri`
- Optimized for AMD Radeon GPUs

### 3. Pre-loaded Models (Optional)
Uncomment in Dockerfile to pre-load models during build:
```dockerfile
RUN /bin/ollama serve & \
    sleep 5 && \
    /bin/ollama pull llama3.2:3b && \
    pkill ollama
```

### 4. Persistent Storage
- Models stored in named volume `ollama_data`
- Survives container restarts
- Easy backup and migration

## 📊 Access Points

After startup, Ollama is available at:
- **API**: http://localhost:11434
- **Health Check**: http://localhost:11434/api/tags
- **Models List**: `docker exec ollama ollama list`

## 🔗 Integration Examples

### With Existing Docker Compose

Add to your existing `docker-compose.yml`:

```yaml
services:
  ollama:
    build:
      context: ./ollama-standalone
      dockerfile: Dockerfile
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    devices:
      - /dev/dri:/dev/dri
    environment:
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_KEEP_ALIVE=24h
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  ollama_data:
```

### Python Client

```python
import requests

# Check health
response = requests.get("http://localhost:11434/api/tags")
print(f"Ollama status: {response.status_code}")

# Generate completion
import ollama

response = ollama.chat(
    model='llama3.2:3b',
    messages=[{'role': 'user', 'content': 'Hello!'}]
)
print(response['message']['content'])
```

### Node.js Client

```javascript
const axios = require('axios');

// Generate completion
async function generate() {
  const response = await axios.post('http://localhost:11434/api/generate', {
    model: 'llama3.2:3b',
    prompt: 'Hello!',
    stream: false
  });
  console.log(response.data.response);
}

generate();
```

## 🛠️ Makefile Commands

```bash
make setup              # Complete setup
make start              # Start Ollama
make stop               # Stop Ollama
make restart            # Restart Ollama
make logs               # View logs
make health             # Check health
make install-models     # Install default models
make list-models        # List installed models
make clean              # Remove container
make clean-all          # Remove container and volumes
make shell              # Access container shell
```

## 📋 Recommended Models

### Small (< 4GB)
- `llama3.2:3b` - Fast general purpose (2GB)
- `mistral:7b` - High quality 7B model (4GB)
- `nomic-embed-text` - Text embeddings (274MB)

### Medium (4-8GB)
- `llama3.1:8b` - Balanced performance (4.7GB)
- `ministral-3:3b` - Mistral's small model (3GB)

### Large (> 8GB)
- `qwen2.5-coder:14b-instruct-q8_0` - Code generation (14GB)

## 🔒 Security Notes

1. **Network Isolation**: By default, Ollama listens on all interfaces (0.0.0.0)
   - For production, bind to localhost only: `127.0.0.1:11434:11434`
   - Or use a reverse proxy with authentication

2. **Resource Limits**: Always set appropriate CPU/memory limits

3. **Volume Permissions**: Ensure proper file permissions for volume mounts

## 🐛 Troubleshooting

### Ollama won't start
```bash
# Check logs
make logs

# Check Docker daemon
docker info

# Rebuild container
make clean
make start
```

### GPU not detected
```bash
# Verify device access
ls -la /dev/dri

# Check Vulkan support
docker exec ollama vulkaninfo
```

### Models not loading
```bash
# Check disk space
df -h

# Verify volume
docker volume inspect ollama_data

# Manually pull model
docker exec ollama ollama pull llama3.2:3b
```

### Health check failing
```bash
# Test curl inside container
docker exec ollama curl http://localhost:11434/api/tags

# Check if service is running
docker exec ollama ps aux | grep ollama
```

## 📦 Backup and Migration

### Backup Models
```bash
# Create backup
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/ollama_backup.tar.gz /data

# Restore backup
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/ollama_backup.tar.gz -C /
```

### Migration to Another Host
```bash
# Export volume
docker volume inspect ollama_data
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/ollama_data.tar.gz -C /data .

# On new host
docker volume create ollama_data
docker run --rm -v ollama_data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/ollama_data.tar.gz -C /data
```

## 🔄 Updates

### Update Ollama
```bash
# Pull latest image
docker pull ollama/ollama:latest

# Rebuild custom image
make clean
make start
```

### Update Models
```bash
# Update a model
docker exec ollama ollama pull llama3.2:3b

# Remove old model versions
docker exec ollama ollama rm old-model:version
```

## 📞 Support

For issues related to:
- **Ollama**: https://github.com/ollama/ollama/issues
- **This package**: Check the troubleshooting section above

## 📄 License

This package configuration is provided as-is for use in your projects.
Ollama itself is licensed under the MIT License.
