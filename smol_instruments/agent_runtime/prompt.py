"""
System prompts with minimal reasoning instructions.

FIXED: Made Qwen-style (ultra-minimal) the default for all low-power models.
"""

# ============================================================================
# ULTRA-MINIMAL PROMPT (DEFAULT for all low-power models)
# ============================================================================

DEFAULT_SYSTEM_PROMPT = r"""Tool agent. One action per turn.

FORMAT:
{"tool_call": {"name": "<tool>", "arguments": {...}}}
OR
{"final": "<answer>"}

RECOVERY: If error has "recovery_suggestion", use that tool call next.

PATCH: propose_patch_unified (creates diff from what you read) -> apply_patch

TOOLS: repo_info, list_files, rg_search, read_file, read_file_snippet, 
       propose_patch_unified, propose_patch, show_patch, apply_patch,
       git_status, git_diff, git_log, run_cmd, run_tests
"""

# ============================================================================
# SLIGHTLY MORE DETAILED (for 14B+ models if needed)
# ============================================================================

DETAILED_SYSTEM_PROMPT = r"""You are a local-tool agent.

FORMAT (choose one per turn):
{"tool_call": {"name": "<tool>", "arguments": {...}}}
OR
{"final": "<answer>"}

RULES:
- Use tools for all repo operations
- When error has "recovery_suggestion", use that tool call
- Create patches: propose_patch_unified (from diff) -> apply_patch

ERROR RECOVERY:
If tool returns:
{
  "error": "FILE_NOT_FOUND",
  "recovery_suggestion": {
    "tool_call": {"name": "list_files", "arguments": {...}},
    "rationale": "..."
  }
}

Use the suggested tool call as your next action.

TOOLS: repo_info, list_files, rg_search, read_file, read_file_snippet, 
       propose_patch_unified, propose_patch, show_patch, apply_patch,
       git_status, git_diff, git_log, run_cmd, run_tests
"""

# ============================================================================
# Prompt Selection
# ============================================================================

PROMPT_VARIANTS = {
    # Use ultra-minimal for all low-power models
    "qwen": DEFAULT_SYSTEM_PROMPT,
    "qwen2.5-coder": DEFAULT_SYSTEM_PROMPT,
    "deepseek": DEFAULT_SYSTEM_PROMPT,
    "llama": DEFAULT_SYSTEM_PROMPT,
    "phi": DEFAULT_SYSTEM_PROMPT,
    "codellama": DEFAULT_SYSTEM_PROMPT,
    
    # Only use detailed for 14B+ if explicitly needed
    "detailed": DETAILED_SYSTEM_PROMPT,
    
    # Fallback
    "default": DEFAULT_SYSTEM_PROMPT,
}

def get_system_prompt(model_id: str) -> str:
    """Select prompt based on model ID."""
    model_lower = model_id.lower()
    
    # Check for explicit matches first
    for key, prompt in PROMPT_VARIANTS.items():
        if key in model_lower:
            return prompt
    
    # Default to ultra-minimal
    return DEFAULT_SYSTEM_PROMPT
