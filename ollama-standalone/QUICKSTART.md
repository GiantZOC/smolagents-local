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
4. ✅ Installed default models (llama3.2:3b, nomic-embed-text)

## 🧪 Try It Out

### Using curl

```bash
# Simple question
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2:3b",
  "prompt": "Why is the sky blue?",
  "stream": false
}'
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.2:3b",
        "prompt": "Explain Docker in one sentence",
        "stream": False
    }
)

print(response.json()["response"])
```

### Using Node.js

```javascript
const axios = require('axios');

axios.post('http://localhost:11434/api/generate', {
  model: 'llama3.2:3b',
  prompt: 'What is AI?',
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
# Small & fast (2GB)
make pull MODEL=llama3.2:3b

# Better quality (4GB)
make pull MODEL=mistral:7b

# Code generation (4GB)
make pull MODEL=codellama:7b

# Embeddings (274MB)
make pull MODEL=nomic-embed-text
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

1. **Keep models loaded**: Set `OLLAMA_KEEP_ALIVE=24h` for faster responses
2. **Use smaller models**: llama3.2:3b is 4x faster than 8b models
3. **Enable streaming**: Better user experience for long responses
4. **Monitor resources**: Use `make disk-usage` to check space
5. **Backup models**: Use `make backup` before major changes

## 🎉 You're Ready!

Ollama is now running and ready for your AI projects. Happy building!

Need help? Check the [README.md](README.md) or [open an issue](https://github.com/ollama/ollama/issues).
