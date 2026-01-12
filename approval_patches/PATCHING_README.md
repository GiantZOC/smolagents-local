# Code Patching System (PATCHING_ARCHITECTURE_V3)

A production-ready code patching system with approval workflows, safety checking, and version control.

## 🚀 Quick Start

### 1. Run the Test

```bash
python3 test_patching_workflow.py
```

This tests the complete workflow:
- Creating workspace artifacts
- Generating patch proposals
- Running safety checks
- Approval workflow
- Patch application
- Version export

### 2. Run the Agent with Approval UI

The agent requires human approval via the approval UI. Run in TWO terminals:

**Terminal 1 - Agent:**
```bash
# Start Phoenix telemetry (optional)
docker-compose up -d

# Run the interactive patching agent
python3 code_patching_agent.py
```

**Terminal 2 - Approval UI:**
```bash
# Run the approval UI to review and approve patches
python3 approval_ui.py
```

The agent will create patch proposals and wait for you to approve them via the UI.

## 📁 Files

### Core Implementation

- **artifact_store.py** - Version control and content-addressed storage
- **patch_applier.py** - Git-based patch application with all-or-nothing semantics
- **safety_checker.py** - AST-based capability detection and safety analysis
- **approval_workflow.py** - DB-backed approval state machine and lifecycle management

### Agent & Tools

- **code_patching_agent.py** - Smolagent with 8 patching tools integrated with Phoenix
- **test_patching_workflow.py** - End-to-end test script
- **test_workspace/** - Example workspace for testing

### Documentation

- **PATCHING_ARCHITECTURE_V3.md** - Complete architecture specification
- **PATCHING_IMPLEMENTATION_SUMMARY.md** - Implementation details and test results
- **PATCHING_README.md** - This file

## 🔧 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Code Patching Agent                      │
│  (Interactive smolagent with plan approval & telemetry)     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      PatchLifecycle                          │
│         (High-level orchestration of workflow)              │
└─────────────────────────────────────────────────────────────┘
           │                   │                    │
           ▼                   ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  ArtifactStore  │  │  PatchApplier   │  │ SafetyChecker   │
│                 │  │                 │  │                 │
│ - Versions      │  │ - Git apply     │  │ - AST analysis  │
│ - Manifests     │  │ - Validation    │  │ - Capabilities  │
│ - Blob storage  │  │ - File changes  │  │ - Syntax check  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
           │                                        │
           ▼                                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  SQLite Database (artifacts.db)              │
│                                                              │
│  Tables: artifacts, versions, file_manifests,               │
│          patch_proposals, approval_requests                 │
└─────────────────────────────────────────────────────────────┘
```

## 🔑 Key Features

### 1. Workspace-First Architecture
Every version is a complete workspace snapshot with deterministic file manifests.

### 2. All-or-Nothing Semantics
Patches either apply completely or not at all. No partial application.

### 3. Context-Aware Safety
AST analysis on resulting code, not just diff fragments. Capability delta tracking.

### 4. Fully DB-Backed
Zero in-memory state. All workflow state persisted in SQLite.

### 5. Content-Addressed Storage
Files stored by SHA256 hash with automatic deduplication.

## 🛠️ Tools Available

The agent provides 9 tools:

1. **create_workspace_artifact** - Snapshot a workspace directory
2. **create_patch_proposal** - Generate patch with requirements
3. **request_patch_approval** - Trigger safety checks and create approval request
4. **wait_for_approval** - Wait for HUMAN approval via approval UI (REQUIRED!)
5. **check_approval_status** - Query approval decision
6. **apply_approved_patch** - Apply approved patch atomically
7. **list_pending_approvals** - List all pending requests
8. **get_version_info** - Get version metadata and file manifest
9. **export_version_to_workspace** - Reconstruct workspace from version

## 📊 Workflow States

```
Patch Proposal → Safety Evaluation → Approval Request → Decision → Application
     (draft)         (evaluate)         (pending)      (approved)   (applied)
                                            ↓
                                        (rejected)
```

## 🔒 Safety Checks

The safety checker detects:
- **Dangerous capabilities**: eval, exec, pickle
- **Risky operations**: subprocess, network, socket
- **File operations**: read, write
- **Syntax errors**: py_compile on all Python files
- **Capability deltas**: What changed between versions

## 📝 Example Usage

### Create an artifact from workspace

```python
from artifact_store import ArtifactStore

store = ArtifactStore()
artifact_id, version_id = store.create_workspace_artifact(
    name="my_project",
    workspace_path="/path/to/workspace"
)
```

### Create and approve a patch

```python
from approval_workflow import PatchLifecycle
from approval_helper import wait_for_user_approval

lifecycle = PatchLifecycle(store, applier, checker, workflow)

# Create proposal
proposal_id = lifecycle.propose_patch(
    artifact_id=artifact_id,
    base_version_id=version_id,
    diff_content=unified_diff,
    requirements="Add error handling"
)

# Request approval (runs safety checks)
success, request_id, error = lifecycle.request_approval(proposal_id)

# Wait for HUMAN approval via UI
# User reviews in approval_ui.py
approved, reason = wait_for_user_approval(workflow, proposal_id, timeout=300)

if approved:
    # Apply
    success, new_version, error = lifecycle.apply_approved_patch(proposal_id)
```

### Or approve via the Approval UI

```bash
# In terminal 1: Your code creates proposal and waits
# In terminal 2: Run the approval UI
python3 approval_ui.py

# The UI shows:
# - Full diff
# - Safety evaluation
# - Capability changes
# User decides: approve/reject
```

## 🧪 Testing

The test suite (`test_patching_workflow.py`) covers:

✅ Component initialization  
✅ Workspace artifact creation  
✅ Patch proposal creation  
✅ Safety evaluation  
✅ Approval workflow  
✅ Patch application  
✅ Version listing  
✅ Version export  

All tests passing!

## 📚 Documentation

- See **PATCHING_ARCHITECTURE_V3.md** for complete architecture details
- See **PATCHING_IMPLEMENTATION_SUMMARY.md** for implementation notes
- See code docstrings for API details

## 🚧 Future Enhancements

- [ ] Rebase workflow for base version drift
- [ ] CLI approval UI that polls database
- [ ] LLM-generated diffs (currently placeholder)
- [ ] Capability-based auto-approval rules
- [ ] Diff visualization
- [ ] Export as tarball
- [ ] Rollback support

## 📞 Integration

The patching system integrates with:
- **Smolagents** - Agent framework
- **Phoenix** - Telemetry and observability
- **Ollama** - LLM for code generation
- **SQLite** - Persistence layer
- **Git** - Patch application (`git apply`)

## ⚡ Performance

- Content-addressed storage with deduplication
- Two-level directory structure for blob storage
- SQLite with proper indexing
- Minimal memory usage (no in-memory caching)

## 🔐 Security

- AST-based capability detection
- Syntax validation before application
- Approval workflow for dangerous changes
- Integrity hashes throughout
- All-or-nothing semantics prevent corruption
