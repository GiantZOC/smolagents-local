# Ollama Docker Standalone Package

A production-ready, portable Ollama setup that can be integrated into any project. This package provides a fully-configured Docker setup with health checks, GPU support, and easy management commands.

## 🚀 Quick Start

### 1. Copy to Your Project

```bash
# Option A: Copy the entire directory
cp -r ollama-standalone/ /path/to/your/project/

# Option B: Clone just this setup
git clone <repo> --depth 1
cd ollama-standalone/
```

### 2. Configure (Optional)

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 3. Start Ollama

```bash
# Complete setup with models
make setup

# Or just start the service
docker compose up -d
```

### 4. Verify

```bash
# Check health
make health

# List models
make list-models
```

## 📦 What's Included

```
ollama-standalone/
├── docker-compose.yml     # Service configuration
├── Dockerfile             # Custom Ollama image
├── Makefile              # Management commands
├── .env.example          # Configuration template
├── configs/
│   └── redis.conf        # Optional Redis config
└── README.md             # This file
```

## 🎯 Features

### ✅ Production Ready
- Health checks with automatic recovery
- Resource limits and reservations
- Persistent storage with named volumes
- Automatic restarts on failure

### 🎮 AMD GPU Support
- Pre-configured Vulkan drivers
- Device passthrough for `/dev/dri`
- Optimized for AMD Radeon GPUs

### 🔧 Easy Management
- Simple Makefile commands
- Docker Compose integration
- Backup and restore utilities
- Model management helpers

### 📊 Optional Components
- Redis caching (use `--profile with-redis`)
- Custom configurations
- Logging directory

## 📖 Usage

### Basic Commands

```bash
# Start Ollama
make start

# Stop Ollama
make stop

# Restart Ollama
make restart

# View logs
make logs

# Check health
make health
```

### Model Management

```bash
# Install default models (llama3.2:3b, nomic-embed-text)
make install-models

# List installed models
make list-models

# Pull specific model
make pull MODEL=mistral:7b

# Remove model
make remove MODEL=mistral:7b
```

### Advanced Commands

```bash
# Access container shell
make shell

# Test API
make test

# Show disk usage
make disk-usage

# Backup models
make backup

# Restore from backup
make restore BACKUP=backups/ollama_backup_20240101_120000.tar.gz

# Show configuration
make info
```

## ⚙️ Configuration

### Environment Variables

Edit `.env` file:

```bash
# Ports
OLLAMA_PORT=11434
REDIS_PORT=6379

# Ollama Settings
OLLAMA_KEEP_ALIVE=24h          # How long to keep models in memory
OLLAMA_NUM_PARALLEL=3          # Number of parallel requests
OLLAMA_MAX_LOADED_MODELS=2     # Max models in memory
OLLAMA_VULKAN=1                # Enable Vulkan (AMD GPU)
OLLAMA_DEBUG=0                 # Debug logging

# Resource Limits
OLLAMA_CPU_LIMIT=8             # Max CPU cores
OLLAMA_MEMORY_LIMIT=16G        # Max memory
OLLAMA_CPU_RESERVATION=2       # Reserved CPU cores
OLLAMA_MEMORY_RESERVATION=4G   # Reserved memory
```

### Resource Tuning

For different hardware configurations:

**Low-end (8GB RAM, 4 cores):**
```env
OLLAMA_CPU_LIMIT=4
OLLAMA_MEMORY_LIMIT=6G
OLLAMA_CPU_RESERVATION=1
OLLAMA_MEMORY_RESERVATION=2G
OLLAMA_MAX_LOADED_MODELS=1
```

**Mid-range (16GB RAM, 8 cores):**
```env
OLLAMA_CPU_LIMIT=8
OLLAMA_MEMORY_LIMIT=12G
OLLAMA_CPU_RESERVATION=2
OLLAMA_MEMORY_RESERVATION=4G
OLLAMA_MAX_LOADED_MODELS=2
```

**High-end (32GB+ RAM, 16+ cores):**
```env
OLLAMA_CPU_LIMIT=16
OLLAMA_MEMORY_LIMIT=24G
OLLAMA_CPU_RESERVATION=4
OLLAMA_MEMORY_RESERVATION=8G
OLLAMA_MAX_LOADED_MODELS=3
```

## 🔗 Integration Examples

### Python

```python
import requests

# Simple API call
response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.2:3b",
        "prompt": "Why is the sky blue?",
        "stream": False
    }
)
print(response.json()["response"])

# Using official Ollama Python library
import ollama

response = ollama.chat(
    model='llama3.2:3b',
    messages=[
        {'role': 'user', 'content': 'Hello!'}
    ]
)
print(response['message']['content'])
```

### Node.js

```javascript
const axios = require('axios');

async function generate(prompt) {
  const response = await axios.post('http://localhost:11434/api/generate', {
    model: 'llama3.2:3b',
    prompt: prompt,
    stream: false
  });
  
  console.log(response.data.response);
}

generate('What is Docker?');
```

### curl

```bash
# Simple generation
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2:3b",
  "prompt": "Hello!"
}'

# Chat format
curl http://localhost:11434/api/chat -d '{
  "model": "llama3.2:3b",
  "messages": [
    {"role": "user", "content": "Why is the ocean salty?"}
  ]
}'

# Streaming
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2:3b",
  "prompt": "Tell me a story",
  "stream": true
}'
```

### Docker Compose Integration

Add to your existing `docker-compose.yml`:

```yaml
services:
  # Your existing services...
  
  ollama:
    build:
      context: ./ollama-standalone
      dockerfile: Dockerfile
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
    restart: unless-stopped
    
  your-app:
    depends_on:
      - ollama
    environment:
      - OLLAMA_URL=http://ollama:11434

volumes:
  ollama_data:
```

## 🔒 Security

### Network Security

For production, restrict network access:

```yaml
# In docker-compose.yml
ports:
  - "127.0.0.1:11434:11434"  # Localhost only
```

Or use a reverse proxy:

```nginx
# Nginx example
location /ollama/ {
    proxy_pass http://127.0.0.1:11434/;
    # Add authentication, rate limiting, etc.
}
```

### Resource Limits

Always set appropriate limits to prevent resource exhaustion:

```yaml
deploy:
  resources:
    limits:
      cpus: "8"
      memory: 16G
```

## 📊 Recommended Models

### Small Models (< 4GB RAM)
- **llama3.2:3b** - Fast, general purpose (2GB)
- **phi3:mini** - Microsoft's 3.8B model (2GB)
- **tinyllama** - Very small, fast (637MB)

### Medium Models (4-8GB RAM)
- **llama3.1:8b** - Balanced performance (4.7GB)
- **mistral:7b** - High quality (4GB)
- **gemma:7b** - Google's model (5GB)

### Large Models (16GB+ RAM)
- **llama3.1:70b** - Best quality (40GB)
- **mixtral:8x7b** - Mixture of experts (26GB)
- **qwen2.5-coder:14b** - Code generation (9GB)

### Specialized Models
- **nomic-embed-text** - Text embeddings (274MB)
- **llava** - Vision + language (4.7GB)
- **codellama:7b** - Code generation (3.8GB)

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check logs
make logs

# Verify Docker is running
docker info

# Check port conflicts
lsof -i :11434

# Rebuild from scratch
make clean-all
make setup
```

### GPU Not Detected

```bash
# Verify GPU device
ls -la /dev/dri

# Test Vulkan support
docker exec ollama vulkaninfo

# Check Docker device passthrough
docker inspect ollama | grep -A 10 Devices
```

### Models Not Loading

```bash
# Check disk space
df -h

# Verify volume
docker volume inspect ollama-standalone_ollama_data

# Check container logs
make logs

# Try manual pull
docker exec ollama ollama pull llama3.2:3b
```

### Out of Memory

```bash
# Reduce loaded models
# Edit .env:
OLLAMA_MAX_LOADED_MODELS=1

# Lower memory limit
OLLAMA_MEMORY_LIMIT=8G

# Restart
make restart
```

### Health Check Failing

```bash
# Test manually
curl http://localhost:11434/api/tags

# Check if service is running
docker exec ollama ps aux | grep ollama

# Restart service
make restart
```

## 📦 Backup & Migration

### Create Backup

```bash
# Using Makefile
make backup

# Manual backup
docker run --rm \
  -v ollama-standalone_ollama_data:/data \
  -v $(pwd)/backups:/backup \
  ubuntu tar czf /backup/ollama_backup.tar.gz /data
```

### Restore Backup

```bash
# Using Makefile
make restore BACKUP=backups/ollama_backup_20240101_120000.tar.gz

# Manual restore
docker run --rm \
  -v ollama-standalone_ollama_data:/data \
  -v $(pwd)/backups:/backup \
  ubuntu tar xzf /backup/ollama_backup.tar.gz -C /
```

### Migrate to Another Server

```bash
# On source server
make backup

# Copy backup file to target server
scp backups/ollama_backup_*.tar.gz user@target:/path/to/ollama-standalone/backups/

# On target server
make restore BACKUP=backups/ollama_backup_*.tar.gz
make start
```

## 🔄 Updates

### Update Ollama

```bash
# Pull latest image
docker pull ollama/ollama:latest

# Rebuild
make clean
make build
make start
```

### Update Models

```bash
# Re-pull a model to get latest version
make pull MODEL=llama3.2:3b
```

## 📞 Support

- **Ollama Documentation**: https://ollama.ai/docs
- **Ollama GitHub**: https://github.com/ollama/ollama
- **Docker Documentation**: https://docs.docker.com

## 📄 License

This Docker configuration is provided as-is for use in your projects.
Ollama itself is licensed under the MIT License.

## 🙏 Credits

Based on the official Ollama Docker image with enhancements for:
- Health monitoring
- AMD GPU support  
- Easy management
- Production deployment
