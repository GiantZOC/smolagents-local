conda create -n smolagents
conda activate smolagents

pip install smolagents
pip install "smolagents[toolkit]"
pip install "smolagents[mcp]"
pip install "smolagents[docker]"
pip install "smolagents[telemetry]"
pip install "smolagents[gradio]"
pip install 'smolagents[litellm]'

docker exec ollama ollama list

docker compose build ollama --no-cache
docker compose up -d ollama


# Check if ollama container can see the GPU
docker compose exec ollama ls -la /dev/dri

# Check Ollama logs for GPU initialization
docker compose logs ollama | grep -i gpu
docker compose logs ollama | grep -i amd

# Check Ollama's detected compute devices
docker compose exec ollama ollama ps
docker logs ollama 2>&1 | grep -iE "(gpu|amd|vulkan|rocm|vram|device|radeon)" | tail -40 

docker ps
docker stop [name]
