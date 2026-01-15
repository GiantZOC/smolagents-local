# Ollama Standalone - Makefile
# Simple management commands for Ollama Docker setup

.PHONY: help setup start stop restart logs health install-models list-models clean clean-all shell build

# Default models to install
# qwen2.5-coder:14b-instruct-q8_0
DEFAULT_MODELS := llama3.2:3b nomic-embed-text:latest

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
BLUE := \033[0;34m
NC := \033[0m

# Helper function
define print_status
	@echo "$(GREEN)[INFO]$(NC) $(1)"
endef

.DEFAULT_GOAL := help

## Display help
help:
	@echo "============================================"
	@echo "Ollama Standalone - Management Commands"
	@echo "============================================"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  make setup           - Complete setup (build, start, install models)"
	@echo "  make health          - Check Ollama health"
	@echo "  make logs            - View logs"
	@echo ""
	@echo "🐳 Service Management:"
	@echo "  make build           - Build Ollama container"
	@echo "  make start           - Start Ollama"
	@echo "  make stop            - Stop Ollama"
	@echo "  make restart         - Restart Ollama"
	@echo "  make status          - Show container status"
	@echo ""
	@echo "📦 Model Management:"
	@echo "  make install-models  - Install default models"
	@echo "  make list-models     - List installed models"
	@echo "  make pull MODEL=name - Pull specific model"
	@echo ""
	@echo "🔧 Utilities:"
	@echo "  make shell           - Access Ollama container shell"
	@echo "  make logs            - View container logs"
	@echo "  make health          - Check health status"
	@echo ""
	@echo "🧹 Cleanup:"
	@echo "  make clean           - Remove containers"
	@echo "  make clean-all       - Remove containers and volumes"
	@echo ""
	@echo "🌐 Access:"
	@echo "  API: http://localhost:11434"
	@echo "  Health: http://localhost:11434/api/tags"

## Complete setup
setup: build start wait-healthy install-models
	$(call print_status,"✅ Setup complete! Ollama is ready.")
	@echo ""
	@echo "Access Ollama at: http://localhost:11434"
	@echo "Run 'make list-models' to see installed models"

## Build Ollama container
build:
	$(call print_status,"Building Ollama container...")
	@docker compose build

## Start Ollama
start:
	$(call print_status,"Starting Ollama...")
	@docker compose up -d ollama
	$(call print_status,"Ollama started!")

## Start with Redis
start-with-redis:
	$(call print_status,"Starting Ollama with Redis...")
	@docker compose --profile with-redis up -d
	$(call print_status,"Ollama and Redis started!")

## Stop Ollama
stop:
	$(call print_status,"Stopping Ollama...")
	@docker compose down
	$(call print_status,"Ollama stopped!")

## Restart Ollama
restart: stop start

## Show status
status:
	$(call print_status,"Container status:")
	@docker compose ps

## View logs
logs:
	$(call print_status,"Ollama logs (Ctrl+C to exit):")
	@docker compose logs -f ollama

## Check health
health:
	$(call print_status,"Checking Ollama health...")
	@echo "🔍 Health Check"
	@echo "==============="
	@if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then \
		echo "✅ Ollama API: Available"; \
		echo "📊 Response:"; \
		curl -s http://localhost:11434/api/tags | head -20; \
	else \
		echo "❌ Ollama API: Not available"; \
		echo "Run 'make logs' to check for errors"; \
	fi

## Wait for healthy status
wait-healthy:
	$(call print_status,"Waiting for Ollama to be healthy...")
	@timeout=60; \
	while [ $$timeout -gt 0 ]; do \
		if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then \
			echo "$(GREEN)✅ Ollama is healthy!$(NC)"; \
			exit 0; \
		fi; \
		echo "Waiting... ($$timeout seconds remaining)"; \
		sleep 2; \
		timeout=$$((timeout - 2)); \
	done; \
	echo "$(RED)❌ Timeout waiting for Ollama$(NC)"; \
	exit 1

## Install default models
install-models: wait-healthy
	$(call print_status,"Installing default models...")
	@for model in $(DEFAULT_MODELS); do \
		echo "📦 Installing $$model..."; \
		docker exec ollama ollama pull $$model || echo "Failed to install $$model"; \
	done
	$(call print_status,"Model installation complete!")

## List installed models
list-models:
	$(call print_status,"Installed models:")
	@docker exec ollama ollama list

## Pull specific model
pull:
	@if [ -z "$(MODEL)" ]; then \
		echo "$(RED)Error: MODEL not specified$(NC)"; \
		echo "Usage: make pull MODEL=llama3.2:3b"; \
		exit 1; \
	fi
	$(call print_status,"Pulling model: $(MODEL)")
	@docker exec ollama ollama pull $(MODEL)

## Remove specific model
remove:
	@if [ -z "$(MODEL)" ]; then \
		echo "$(RED)Error: MODEL not specified$(NC)"; \
		echo "Usage: make remove MODEL=llama3.2:3b"; \
		exit 1; \
	fi
	$(call print_status,"Removing model: $(MODEL)")
	@docker exec ollama ollama rm $(MODEL)

## Access shell
shell:
	$(call print_status,"Accessing Ollama container shell...")
	@docker exec -it ollama /bin/bash

## Test API
test:
	$(call print_status,"Testing Ollama API...")
	@echo "📡 API Test"
	@echo "==========="
	@echo "Available models:"
	@curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || echo "No models found"
	@echo ""
	@echo "Testing generation (if models are installed)..."
	@curl -s http://localhost:11434/api/generate -d '{"model":"llama3.2:3b","prompt":"Say hello","stream":false}' | head -20 || echo "Generation test failed"

## Clean containers
clean:
	$(call print_status,"Removing containers...")
	@docker compose down
	$(call print_status,"Containers removed!")

## Clean containers and volumes
clean-all:
	$(call print_status,"⚠️  Warning: This will delete all models and data!")
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
		echo "$(GREEN)Cleanup complete!$(NC)"; \
	else \
		echo "Cancelled."; \
	fi

## Show disk usage
disk-usage:
	$(call print_status,"Ollama disk usage:")
	@docker exec ollama du -sh /root/.ollama 2>/dev/null || echo "Container not running"
	@echo ""
	$(call print_status,"Docker volume size:")
	@docker system df -v | grep ollama || echo "No Ollama volumes found"

## Backup models
backup:
	$(call print_status,"Creating backup of Ollama models...")
	@mkdir -p backups
	@docker run --rm \
		-v ollama-standalone_ollama_data:/data \
		-v $(PWD)/backups:/backup \
		ubuntu tar czf /backup/ollama_backup_$(shell date +%Y%m%d_%H%M%S).tar.gz /data
	$(call print_status,"Backup created in ./backups/")

## Restore models from backup
restore:
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)Error: BACKUP not specified$(NC)"; \
		echo "Usage: make restore BACKUP=backups/ollama_backup_20240101_120000.tar.gz"; \
		ls -la backups/ 2>/dev/null || echo "No backups found"; \
		exit 1; \
	fi
	$(call print_status,"Restoring from backup: $(BACKUP)")
	@docker run --rm \
		-v ollama-standalone_ollama_data:/data \
		-v $(PWD)/backups:/backup \
		ubuntu tar xzf /backup/$(notdir $(BACKUP)) -C /
	$(call print_status,"Restore complete! Restart Ollama to load models.")

## Show info
info:
	@echo "🔧 Ollama Configuration"
	@echo "======================="
	@echo "Container: ollama"
	@echo "Port: 11434"
	@echo "Volume: ollama-standalone_ollama_data"
	@echo "Network: ollama-standalone_ollama-net"
	@echo ""
	@echo "📁 Files:"
	@echo "  Config: docker-compose.yml"
	@echo "  Dockerfile: Dockerfile"
	@echo "  Logs: ./logs/"
	@echo ""
	@echo "🌐 Endpoints:"
	@echo "  Health: http://localhost:11434/api/tags"
	@echo "  Generate: http://localhost:11434/api/generate"
	@echo "  Chat: http://localhost:11434/api/chat"
	@echo ""
	@echo "📦 Installed Models:"
	@docker exec ollama ollama list 2>/dev/null || echo "  Container not running"
