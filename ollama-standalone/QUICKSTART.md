# Ollama Standalone - Quick Start Guide

Get Ollama running in under 5 minutes!

## 🎯 Prerequisites

- Docker installed and running
- 4GB+ available RAM (8GB+ recommended)
- 10GB+ free disk space

## ⚡ 60-Second Setup

```bash
# 1. Navigate to directory
cd ollama-standalone/

# 2. Start Ollama (one command does everything!)
make setup

# 3. Done! Test it:
make test
```

That's it! Ollama is now running at http://localhost:11434

## 📝 What Just Happened?

The `make setup` command did:
1. ✅ Built custom Ollama container with health checks
2. ✅ Started Ollama service
3. ✅ Waited for healthy status
4. ✅ Installed default models (qwen2.5-coder:14b-instruct, nomic-embed-text)

## 🔥 Recommended: Create 16k Context Variant

For better performance with longer code contexts:

```bash
make create-16k-variant
```

This creates `qwen2.5-coder:14b-instruct-16k` with 16,384 token context window (vs default 8,192)

## 🧪 Try It Out

### Using curl

```bash
# Simple code generation
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:14b-instruct",
  "prompt": "Write a Python function to calculate fibonacci",
  "stream": false
}'

# Use 16k variant for longer contexts
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:14b-instruct-16k",
  "prompt": "Refactor this code...",
  "stream": false
}'
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen2.5-coder:14b-instruct",
        "prompt": "Write a FastAPI endpoint for user authentication",
        "stream": False
    }
)

print(response.json()["response"])
```

### Using Node.js

```javascript
const axios = require('axios');

axios.post('http://localhost:11434/api/generate', {
  model: 'qwen2.5-coder:14b-instruct',
  prompt: 'Create a React component for a login form',
  stream: false
}).then(res => console.log(res.data.response));
```

## 🎮 Common Commands

```bash
# Check status
make health

# View logs
make logs

# List models
make list-models

# Install another model
make pull MODEL=mistral:7b

# Stop Ollama
make stop

# Start again
make start
```

## 🔧 Configure (Optional)

```bash
# 1. Create config file
cp .env.example .env

# 2. Edit settings
nano .env

# 3. Restart to apply
make restart
```

### Key Settings

```bash
OLLAMA_PORT=11434                # Change port
OLLAMA_KEEP_ALIVE=24h            # Keep models in memory
OLLAMA_MAX_LOADED_MODELS=2       # Number of models in memory
OLLAMA_MEMORY_LIMIT=16G          # Max memory usage
```

## 🚀 Next Steps

### Install More Models

```bash
# Default coding model (8.5GB) - already installed
# qwen2.5-coder:14b-instruct

# Create extended context variants
make create-16k-variant  # 16k context (recommended)
make create-32k-variant  # 32k context (for very long files)

# Alternative coding models
make pull MODEL=qwen2.5-coder:7b-instruct    # Smaller, faster (4.7GB)
make pull MODEL=codellama:13b                # Alternative (7GB)

# Embeddings (274MB) - already installed
# nomic-embed-text:latest

# Small general purpose models
make pull MODEL=llama3.2:3b    # Small & fast (2GB)
make pull MODEL=mistral:7b     # Better quality (4GB)
```

### Integrate with Your App

See [README.md](README.md#integration-examples) for integration examples with:
- Python
- Node.js
- curl
- Docker Compose

### Add Redis Caching (Optional)

```bash
# Start with Redis
docker compose --profile with-redis up -d

# Or update your command
make start-with-redis
```

## ❌ Troubleshooting

### Can't connect to Ollama?

```bash
# Check if running
docker ps | grep ollama

# Check logs
make logs

# Restart
make restart
```

### Out of memory?

```bash
# Edit .env file
echo "OLLAMA_MEMORY_LIMIT=8G" >> .env
echo "OLLAMA_MAX_LOADED_MODELS=1" >> .env

# Restart
make restart
```

### GPU not working?

```bash
# Check if GPU is available
ls -la /dev/dri

# Test inside container
docker exec ollama vulkaninfo
```

## 🧹 Clean Up

```bash
# Stop and remove containers
make clean

# Remove everything including models
make clean-all
```

## 📚 Learn More

- **Full Documentation**: See [README.md](README.md)
- **Ollama Docs**: https://ollama.ai/docs
- **Model Library**: https://ollama.ai/library
- **API Reference**: https://github.com/ollama/ollama/blob/main/docs/api.md

## 💡 Pro Tips

1. **Use 16k variant**: Run `make create-16k-variant` for better code understanding
2. **Keep models loaded**: Set `OLLAMA_KEEP_ALIVE=24h` for faster responses
3. **Smaller for speed**: qwen2.5-coder:7b-instruct is faster but less capable
4. **Enable streaming**: Better user experience for long responses
5. **Monitor resources**: Use `make disk-usage` to check space
6. **Backup models**: Use `make backup` before major changes

## 🎉 You're Ready!

Ollama is now running and ready for your AI projects. Happy building!

Need help? Check the [README.md](README.md) or [open an issue](https://github.com/ollama/ollama/issues).
