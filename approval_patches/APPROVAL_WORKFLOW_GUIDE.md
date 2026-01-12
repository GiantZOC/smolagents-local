# Human-in-the-Loop Approval Workflow Guide

## Overview

The patching system implements a **human-in-the-loop approval workflow** where patches are reviewed and approved by a human before being applied. This ensures safety and oversight for all code changes.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Code Patching Agent                        │
│  (Creates proposals, requests approval, waits for decision)  │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              SQLite Database (artifacts.db)                  │
│                                                              │
│  • patch_proposals - Proposed changes with diffs            │
│  • approval_requests - Safety evaluations and status        │
│  • PENDING → APPROVED/REJECTED → APPLIED                    │
└─────────────────┬───────────────────────────────────────────┘
                  ▲
                  │
┌─────────────────┴───────────────────────────────────────────┐
│                    Approval UI (CLI)                         │
│  (Polls DB, shows diff + safety eval, user decides)         │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Principles**:
1. **Database as single source of truth** - All state persisted
2. **Process isolation** - Agent and UI are separate processes
3. **No direct communication** - Agent and UI communicate via database only
4. **Polling architecture** - UI polls database for new requests
5. **Human always in control** - No auto-approval, human reviews every patch

## Workflow Steps

### 1. Agent Creates Proposal

```python
# Agent tool call
proposal_id = create_patch_proposal(
    artifact_id="proj_abc123",
    base_version_id="v_def456",
    requirements="Add error handling to login function"
)
```

**What happens**:
- Diff generated (currently placeholder, future: LLM-generated)
- Stored in `patch_proposals` table
- Diff hash computed for integrity

### 2. Agent Requests Approval

```python
# Agent tool call
result = request_patch_approval(proposal_id)
```

**What happens**:
- Patch applied to temp workspace (dry-run)
- Safety checks run:
  - AST analysis for dangerous capabilities
  - Syntax validation with py_compile
  - Capability delta (before/after comparison)
- Evaluation stored in database
- Approval request created with status=PENDING

### 3. Agent Waits for Human Decision

```python
# Agent tool call - THIS BLOCKS!
approval_result = wait_for_approval(
    proposal_id=proposal_id,
    timeout_seconds=300
)
```

**What happens**:
- Agent polls database every 2 seconds
- Shows status to user:
  ```
  ⏳ WAITING FOR HUMAN APPROVAL
  ══════════════════════════════════════════════════════════
  
  📋 A patch approval request is pending in the database.
  
     To review and approve/reject, open ANOTHER terminal and run:
     python3 approval_ui.py
  
     Polling database every 2 seconds (timeout: 300s)...
  ══════════════════════════════════════════════════════════
  ```
- Agent is **blocked** until decision received or timeout

### 4. Human Reviews in Approval UI

**User runs in separate terminal**:
```bash
python3 approval_ui.py
```

**UI shows**:
```
══════════════════════════════════════════════════════════
📋 PENDING APPROVAL REQUESTS (1)
══════════════════════════════════════════════════════════

1. Request ID: 8bd39be7bc8b8991
   Proposal ID: 3ab5bfc62f923490
   Artifact: proj_abc123
   Requirements: Add error handling to login function
   Created: 2025-01-11T14:23:45

══════════════════════════════════════════════════════════
🔍 APPROVAL REQUEST DETAILS
══════════════════════════════════════════════════════════

Request ID: 8bd39be7bc8b8991
Status: PENDING
Created: 2025-01-11T14:23:45

📝 Patch Proposal:
   Proposal ID: 3ab5bfc62f923490
   Artifact ID: proj_abc123
   Base Version: v_def456
   Requirements: Add error handling to login function
   Diff Hash: a3f7b2c1

──────────────────────────────────────────────────────────
📄 UNIFIED DIFF:
──────────────────────────────────────────────────────────
--- login.py
+++ login.py
@@ -5,6 +5,10 @@
 def authenticate(username, password):
     """Authenticate user credentials"""
+    try:
+        validate_credentials(username, password)
+    except ValidationError as e:
+        logger.error(f"Authentication failed: {e}")
+        raise
     return check_credentials(username, password)
──────────────────────────────────────────────────────────

🔒 Safety Evaluation:
   Safe: ✅ YES
   Syntax Valid: ✅ YES

   ✅ No issues, warnings, or capability changes detected

══════════════════════════════════════════════════════════

Decision (approve/reject/skip/quit):
```

### 5. Human Decides

**User types**: `approve`

```
Approval reason (optional): Looks good, adds proper error handling
✅ Patch APPROVED
```

**What happens**:
- Decision written to database
- `approval_requests` table updated:
  - `status` = "approved"
  - `decision_at` = current timestamp
  - `decision_reason` = user's reason
- Database commit completes

### 6. Agent Receives Decision

**Agent's wait_for_approval() detects change**:
```python
# Polling loop detects status change
approval_req = workflow.get_approval_by_proposal(proposal_id)
if approval_req.status == ApprovalStatus.APPROVED:
    return True, reason
```

**Agent output**:
```
✅ PATCH APPROVED!
   Reason: Looks good, adds proper error handling
```

### 7. Agent Applies Patch

```python
# Agent tool call
new_version = apply_approved_patch(proposal_id)
```

**What happens**:
- Verifies approval exists and is approved
- Checks base version hasn't drifted
- Applies patch with git apply (all-or-nothing)
- Creates new version with file manifest
- Runs post-apply tests (py_compile)
- Marks approval request as "applied"

## Complete Example Session

### Terminal 1 (Agent)

```bash
$ python3 code_patching_agent.py

🚀 CODE PATCHING AGENT (PATCHING_ARCHITECTURE_V3)

👤 Task: Add error handling to the login function in my_project

📋 PLANNING STEP #1
Plan:
1. Get current version of my_project
2. Create patch proposal for error handling
3. Request approval and wait for user
4. Apply if approved

⚡ Action #1 [patching_agent]: get_version_info
📦 Version ID: v_def456
   Files: 5
   ...

⚡ Action #2 [patching_agent]: create_patch_proposal
✅ Created patch proposal
   Proposal ID: prop_xyz789
   ...

⚡ Action #3 [patching_agent]: request_patch_approval
✅ Approval request created
   Request ID: req_abc123
   ✅ No safety issues found

⚡ Action #4 [patching_agent]: wait_for_approval

⏳ WAITING FOR HUMAN APPROVAL
══════════════════════════════════════════════════════════

📋 A patch approval request is pending in the database.

   To review and approve/reject, open ANOTHER terminal and run:
   python3 approval_ui.py

   Polling database every 2 seconds (timeout: 300s)...

══════════════════════════════════════════════════════════

   [  0s] Waiting for decision...
   [  2s] Waiting for decision...
   [  4s] Waiting for decision...
   [  6s] Waiting for decision...

✅ PATCH APPROVED!
   Reason: Looks good, adds proper error handling

⚡ Action #5 [patching_agent]: apply_approved_patch
✅ Patch applied successfully!
   New Version ID: v_ghi012
   ...

✅ TASK COMPLETED
```

### Terminal 2 (Approval UI)

```bash
$ python3 approval_ui.py

🔒 PATCH APPROVAL UI

Commands:
  approve (a) - Approve the patch
  reject (r)  - Reject the patch
  skip (s)    - Skip to next request
  quit (q)    - Exit

══════════════════════════════════════════════════════════
📋 PENDING APPROVAL REQUESTS (1)
══════════════════════════════════════════════════════════

1. Request ID: req_abc123
   Proposal ID: prop_xyz789
   Artifact: my_project
   Requirements: Add error handling to login function
   Created: 2025-01-11T14:23:45

[Shows full details, diff, safety evaluation...]

Decision (approve/reject/skip/quit): approve
Approval reason (optional): Looks good, adds proper error handling
✅ Patch APPROVED

⏳ Waiting for new approval requests...
   (Checking every 5 seconds, Ctrl+C to exit)

^C
👋 Exiting approval UI
```

## Rejection Flow

If user rejects:

```
Decision (approve/reject/skip/quit): reject
Rejection reason (required): Uses deprecated API, needs update
❌ Patch REJECTED
```

Agent receives:
```
❌ PATCH REJECTED
   Reason: Uses deprecated API, needs update
```

Agent stops and does NOT apply patch.

## Timeout Flow

If no decision within timeout:

Agent shows:
```
⏱️  TIMEOUT: No approval decision received within 300 seconds
```

Patch is NOT applied. Request remains in PENDING state.

## CLI Approval UI Features

### Interactive Mode (Default)
```bash
python3 approval_ui.py
```
- Polls database every 5 seconds
- Shows next pending request
- User approves/rejects/skips
- Continuous loop until quit

### List Mode
```bash
python3 approval_ui.py --list
```
- Shows all pending requests
- Exits immediately
- Useful for checking queue

### Review Mode
```bash
python3 approval_ui.py --review req_abc123
```
- Reviews specific request by ID
- Shows full details
- Prompts for decision
- Exits after decision

### Custom Database
```bash
python3 approval_ui.py --db /path/to/custom.db
```
- Uses different database file
- Useful for testing or multiple projects

## Safety Information Displayed

The approval UI shows:

### 1. Diff
Full unified diff showing exact changes

### 2. Safety Verdict
- ✅ Safe or ❌ Unsafe
- Syntax validation results

### 3. Issues
Blocking safety issues:
- eval/exec usage
- pickle loads
- Dangerous operations

### 4. Warnings
Non-blocking concerns:
- Subprocess usage
- Network requests
- File operations

### 5. Capability Delta
Changes in security-relevant capabilities:
```
🔧 Capability Changes:
   ➕ Added (2):
      + subprocess in utils.py:45
      + network_request in api.py:23
   ➖ Removed (0):
```

## Best Practices

### For Operators

1. **Always review diffs carefully** - Don't just approve blindly
2. **Check capability changes** - New subprocess/network is risky
3. **Provide reasons** - Document why you approved/rejected
4. **Use reject for bad patches** - Don't skip, reject with reason
5. **Keep UI running** - Start it before running agent tasks

### For Developers

1. **Clear requirements** - Write descriptive patch requirements
2. **Test safety** - Ensure patches will pass safety checks
3. **Reasonable timeouts** - Default 300s, adjust if needed
4. **Handle rejections** - Check result, don't assume approval
5. **Inform users** - Tell them to run approval_ui.py

## Troubleshooting

### Agent hangs waiting for approval
- Check if approval_ui.py is running
- Verify same database file (artifacts.db)
- Check pending requests: `python3 approval_ui.py --list`

### UI shows no pending requests
- Verify agent created request successfully
- Check database: `sqlite3 artifacts.db "SELECT * FROM approval_requests"`
- Ensure same database file

### Timeout before I can review
- Increase timeout: `wait_for_approval(proposal_id, timeout_seconds=600)`
- Start UI before running agent
- Use `check_approval_status()` to verify request exists

### Patch applied without approval
- This should NEVER happen! File a bug report if it does
- All patches require explicit human approval

## Security Guarantees

1. **No auto-approval** - Human must explicitly approve every patch
2. **Safety checks always run** - Cannot bypass evaluation
3. **Audit trail** - All decisions logged with timestamps and reasons
4. **All-or-nothing** - Patches apply completely or not at all
5. **Capability tracking** - New dangerous capabilities flagged

## Summary

The approval workflow ensures **human oversight** for all code changes while maintaining a clean, database-backed architecture. The agent and UI communicate solely through the database, making the system:

- ✅ **Safe** - Humans review every change
- ✅ **Auditable** - All decisions logged
- ✅ **Reliable** - DB-backed, no state loss
- ✅ **Flexible** - UI can run anywhere, anytime
- ✅ **Transparent** - Full diff and safety info shown

This implements true human-in-the-loop AI code patching!
