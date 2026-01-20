# Custom Ollama Dockerfile with health check support and GPU drivers
# Based on official Ollama image with additional utilities
FROM ollama/ollama:latest

# Install curl for health checks and AMD GPU support packages
# Also includes debugging utilities
RUN apt-get update --allow-unauthenticated && \
    apt-get install -y --allow-unauthenticated \
    curl \
    mesa-vulkan-drivers \
    libvulkan1 \
    vulkan-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Optional: Pre-load models during build
# Uncomment the following block to pre-load models (increases image size)
# This is useful for air-gapped deployments or faster startup times
#
# RUN /bin/ollama serve & \
#     sleep 5 && \
#     /bin/ollama pull qwen2.5-coder:14b-instruct && \
#     /bin/ollama pull nomic-embed-text:latest && \
#     pkill ollama

# Keep the original entrypoint and command
ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]

# Health check is defined in docker-compose.yml
# This allows for easier customization without rebuilding the image
