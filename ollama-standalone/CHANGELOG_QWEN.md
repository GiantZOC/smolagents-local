# Ollama Standalone - Qwen 2.5 Coder Update

## Summary

Updated ollama-standalone to default to `qwen2.5-coder:14b-instruct` with recommended 16k context variant creation.

## Changes Made

### 1. Default Model Update
- **Changed from**: `llama3.2:3b` → **To**: `qwen2.5-coder:14b-instruct`
- More capable coding model optimized for development tasks
- Model size: ~8.5GB vs 2GB (better quality for coding)

### 2. New Modelfile for Context Variants
- **Created**: `Modelfile.16k`
  ```dockerfile
  FROM qwen2.5-coder:14b-instruct
  PARAMETER num_ctx 16384
  ```
- Doubles context window from 8,192 to 16,384 tokens
- Better for understanding longer code files

### 3. New Makefile Targets

#### `make create-16k-variant`
- Creates `qwen2.5-coder:14b-instruct-16k` with 16,384 token context
- **Strongly recommended** for production use
- No additional download required (builds from base model)

#### `make create-32k-variant`
- Creates `qwen2.5-coder:14b-instruct-32k` with 32,768 token context
- For very large files or complex refactoring tasks
- Uses more memory

### 4. Updated Documentation
- **Makefile help**: Shows new variant creation commands
- **QUICKSTART.md**: 
  - Updated all examples to use qwen2.5-coder
  - Added section on creating 16k variant
  - Updated code examples to be coding-focused
  - Revised pro tips to recommend 16k variant
- **Dockerfile comments**: Updated pre-load example

### 5. Updated Commands
- `make test`: Now tests with qwen2.5-coder and coding prompt
- `make setup`: Shows recommendation to create 16k variant after completion
- `make install-models`: Installs qwen2.5-coder:14b-instruct by default

## Usage

### Quick Start (Recommended Workflow)
```bash
# 1. Setup with new default model
make setup

# 2. Create 16k context variant (strongly recommended!)
make create-16k-variant

# 3. Verify installation
make list-models

# Expected output:
# - qwen2.5-coder:14b-instruct
# - qwen2.5-coder:14b-instruct-16k
# - nomic-embed-text:latest
```

### Using the Models

#### Standard model (8k context)
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:14b-instruct",
  "prompt": "Write a Python function...",
  "stream": false
}'
```

#### 16k variant (recommended)
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:14b-instruct-16k",
  "prompt": "Refactor this large codebase...",
  "stream": false
}'
```

## Why Qwen 2.5 Coder?

### Advantages over llama3.2:3b
1. **Specialized for coding**: Fine-tuned on code datasets
2. **Better instruction following**: More reliable tool/function calls
3. **Larger context**: 8k default (vs 2k), 16k/32k variants available
4. **Better code understanding**: 14B params vs 3B
5. **Multi-language support**: Strong across Python, JS, Go, Rust, etc.

### Performance Characteristics
- **Model size**: ~8.5GB (vs 2GB for llama3.2:3b)
- **Memory usage**: ~10-12GB RAM (16GB recommended)
- **Speed**: Slower than 3B models but much better quality
- **Context**: 8k default, 16k/32k with variants

## Migration Notes

### For Existing Users
1. Old models are NOT removed automatically
2. Can keep both models installed
3. Update your application's model references:
   - Old: `llama3.2:3b`
   - New: `qwen2.5-coder:14b-instruct` or `qwen2.5-coder:14b-instruct-16k`

### Disk Space
- Qwen model: ~8.5GB
- 16k variant: ~100MB additional (shares base model weights)
- 32k variant: ~100MB additional (shares base model weights)
- Total with variants: ~8.7GB

### Memory Requirements
- **Minimum**: 10GB RAM
- **Recommended**: 16GB RAM
- **With 16k variant**: 16GB RAM recommended
- **With 32k variant**: 24GB+ RAM recommended

## Testing

```bash
# Test basic functionality
make test

# Test 16k variant
docker exec ollama ollama run qwen2.5-coder:14b-instruct-16k "Write a FastAPI app"

# Check installed models
make list-models
```

## Rollback (if needed)

To revert to llama3.2:3b:

```bash
# 1. Edit Makefile
sed -i 's/qwen2.5-coder:14b-instruct/llama3.2:3b/g' Makefile

# 2. Clean and reinstall
make clean
make setup
```

## Files Modified

1. `Dockerfile` - Updated pre-load example comment
2. `Makefile` - New targets, updated defaults, updated help
3. `QUICKSTART.md` - Comprehensive documentation updates
4. `Modelfile.16k` - **NEW**: 16k context variant configuration

## Configuration Updates (.env)

No `.env` changes required. The model choice is in Makefile's `DEFAULT_MODELS` variable.

To use a different model permanently:
```bash
# Edit Makefile
DEFAULT_MODELS := your-preferred-model
```

Or override per installation:
```bash
DEFAULT_MODELS="mistral:7b" make install-models
```

## Support

- **Model documentation**: https://ollama.ai/library/qwen2.5-coder
- **Context limits**: 8k default, 16k/32k variants available
- **Issues**: Check `make logs` for errors
- **Performance**: Use `make disk-usage` to monitor resources
