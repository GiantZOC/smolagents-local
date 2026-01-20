# Setup Guide for smol-instruments

## 🐍 Python Package Setup

### Installation Options

#### Option 1: Install in Development Mode (Recommended)

```bash
# From the project root directory
pip install -e .

# This makes the package importable from anywhere
python -c "import agent_runtime; print('✅ Package installed')"
```

#### Option 2: Add to Python Path Temporarily

```bash
# From the project root directory
export PYTHONPATH=$(pwd):$PYTHONPATH
python -c "import agent_runtime; print('✅ Package accessible')"
```

#### Option 3: Run from Project Root

```bash
# From the project root directory
python -m smol_instruments.tests.test_logging_verification
```

## 🧪 Running Tests

### Using pytest (Recommended)

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
pytest smol_instruments/tests/ -v

# Run specific test
pytest smol_instruments/tests/test_logging_verification.py -v

# Run with more detail
pytest smol_instruments/tests/test_logging_verification.py -v -s
```

### Running Tests Directly

```bash
# From project root
python smol_instruments/tests/test_logging_verification.py

# From anywhere (if installed)
python -m smol_instruments.tests.test_logging_verification
```

## 🔧 Common Issues & Fixes

### Issue: "No module named agent_runtime"

**Cause:** Package not installed or Python path not set.

**Solutions:**
1. Install in development mode: `pip install -e .`
2. Run from project root: `cd /path/to/smol-instruments`
3. Set PYTHONPATH: `export PYTHONPATH=/path/to/smol-instruments:$PYTHONPATH`

### Issue: "No module named agent_runtime.run"

**Cause:** Trying to import from wrong location.

**Solutions:**
1. Use proper import: `from agent_runtime import run_task`
2. Run from project root or install package
3. Check your import statements

### Issue: Tests not discovered by pytest

**Cause:** Missing `__init__.py` or wrong directory structure.

**Solutions:**
1. Ensure `smol_instruments/tests/__init__.py` exists
2. Run pytest from project root
3. Use explicit path: `pytest smol_instruments/tests/`

## 📁 Project Structure

```
smol-instruments/
├── smol_instruments/
│   ├── __init__.py          # Main package
│   ├── agent_runtime/       # Runtime components
│   └── tests/               # Test suite
│       ├── __init__.py      # Tests package
│       ├── test_*.py        # Test files
│       └── ...
├── pyproject.toml          # Build configuration
└── SETUP_GUIDE.md          # This file
```

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Run tests
pytest smol_instruments/tests/ -v

# 3. Use the package
python -c "
from agent_runtime import run_task
result = run_task('List files', enable_phoenix=True)
print('Task completed!')
"
```

## 🎯 Verification

Check that everything is working:

```bash
# Test imports
python -c "from agent_runtime import build_agent; print('✅ Imports work')"

# Test package structure
python -c "import smol_instruments; print('✅ Package structure OK')"

# Test pytest discovery
pytest --collect-only smol_instruments/tests/
```

## 📊 Troubleshooting

### Check Python Environment

```bash
which python
python --version
pip list | grep smol
```

### Check Package Installation

```bash
pip show smol-instruments
python -c "import sys; print(sys.path)"
```

### Verify Test Discovery

```bash
pytest --collect-only smol_instruments/tests/test_logging_verification.py
```

## 📖 Best Practices

1. **Always run from project root** when developing
2. **Use `pip install -e .`** for development
3. **Run pytest explicitly** with paths
4. **Check imports** match package structure
5. **Verify PYTHONPATH** if having import issues

The package is now properly set up with clean imports and proper Python packaging. Use the methods above to run tests and verify everything is working correctly.