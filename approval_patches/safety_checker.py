"""
ContextAwareSafetyChecker V3: AST-based analysis with capability delta
"""
import ast
import re
import tempfile
import shutil
import py_compile
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class Capability(Enum):
    """Security-relevant capabilities"""
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    NETWORK_REQUEST = "network_request"
    SUBPROCESS = "subprocess"
    EVAL_EXEC = "eval_exec"
    IMPORT_DYNAMIC = "import_dynamic"
    PICKLE = "pickle"
    SOCKET = "socket"


@dataclass
class CapabilityDetection:
    """Single capability detection with location"""
    capability: Capability
    file_path: str
    line_number: int
    code_snippet: str


@dataclass
class CapabilityDelta:
    """Change in capabilities between versions"""
    added: List[CapabilityDetection] = field(default_factory=list)
    removed: List[CapabilityDetection] = field(default_factory=list)
    unchanged: List[CapabilityDetection] = field(default_factory=list)


@dataclass
class SafetyEvaluation:
    """Complete safety evaluation result"""
    safe: bool
    issues: List[str]
    warnings: List[str]
    capability_delta: CapabilityDelta
    syntax_valid: bool
    evaluation_hash: str  # Hash of evaluation for deduplication


class ASTCapabilityVisitor(ast.NodeVisitor):
    """AST visitor that detects security-relevant capabilities"""
    
    def __init__(self, file_path: str, source_lines: List[str]):
        self.file_path = file_path
        self.source_lines = source_lines
        self.detections: List[CapabilityDetection] = []
    
    def _add_detection(self, node: ast.AST, capability: Capability):
        """Add capability detection with code context"""
        line_num = node.lineno if hasattr(node, 'lineno') else 0
        snippet = self.source_lines[line_num - 1] if 0 < line_num <= len(self.source_lines) else ""
        
        self.detections.append(CapabilityDetection(
            capability=capability,
            file_path=self.file_path,
            line_number=line_num,
            code_snippet=snippet.strip()
        ))
    
    def visit_Call(self, node: ast.Call):
        """Detect function calls that indicate capabilities"""
        # Get function name
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        if func_name:
            # Eval/exec detection
            if func_name in ('eval', 'exec', 'compile'):
                self._add_detection(node, Capability.EVAL_EXEC)
            
            # Subprocess detection
            elif func_name in ('system', 'popen', 'spawn', 'run', 'call', 'check_output'):
                self._add_detection(node, Capability.SUBPROCESS)
            
            # Network detection
            elif func_name in ('urlopen', 'request', 'get', 'post', 'connect'):
                self._add_detection(node, Capability.NETWORK_REQUEST)
            
            # Pickle detection
            elif func_name in ('loads', 'load', 'dumps', 'dump') and self._is_pickle_context(node):
                self._add_detection(node, Capability.PICKLE)
        
        self.generic_visit(node)
    
    def visit_Import(self, node: ast.Import):
        """Detect imports of security-relevant modules"""
        for alias in node.names:
            if alias.name in ('subprocess', 'os'):
                self._add_detection(node, Capability.SUBPROCESS)
            elif alias.name in ('socket', 'socketserver'):
                self._add_detection(node, Capability.SOCKET)
            elif alias.name in ('pickle', 'dill', 'shelve'):
                self._add_detection(node, Capability.PICKLE)
            elif alias.name in ('urllib', 'urllib2', 'urllib3', 'requests', 'httpx'):
                self._add_detection(node, Capability.NETWORK_REQUEST)
        
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Detect from X import Y patterns"""
        if node.module:
            if node.module in ('subprocess', 'os'):
                self._add_detection(node, Capability.SUBPROCESS)
            elif node.module in ('socket', 'socketserver'):
                self._add_detection(node, Capability.SOCKET)
            elif node.module.startswith('urllib') or node.module in ('requests', 'httpx'):
                self._add_detection(node, Capability.NETWORK_REQUEST)
        
        self.generic_visit(node)
    
    def visit_With(self, node: ast.With):
        """Detect file operations in with statements"""
        for item in node.items:
            if isinstance(item.context_expr, ast.Call):
                if isinstance(item.context_expr.func, ast.Name):
                    if item.context_expr.func.id == 'open':
                        # Check mode argument
                        if len(item.context_expr.args) > 1:
                            mode_arg = item.context_expr.args[1]
                            if isinstance(mode_arg, ast.Constant):
                                mode = mode_arg.value
                                if 'w' in mode or 'a' in mode or '+' in mode:
                                    self._add_detection(node, Capability.FILESYSTEM_WRITE)
                                else:
                                    self._add_detection(node, Capability.FILESYSTEM_READ)
                        else:
                            self._add_detection(node, Capability.FILESYSTEM_READ)
        
        self.generic_visit(node)
    
    def _is_pickle_context(self, node: ast.Call) -> bool:
        """Check if function call is in pickle module context"""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return node.func.value.id in ('pickle', 'dill', 'shelve')
        return False


class ContextAwareSafetyChecker:
    """
    Safety checker that analyzes resulting code (not just diff).
    Computes capability delta between base and patched versions.
    """
    
    def __init__(self, artifact_store, patch_applier):
        self.artifact_store = artifact_store
        self.patch_applier = patch_applier
    
    def _detect_capabilities_in_file(
        self, 
        file_path: str, 
        content: bytes
    ) -> List[CapabilityDetection]:
        """Detect capabilities in single Python file via AST"""
        try:
            source = content.decode('utf-8')
            source_lines = source.split('\n')
            tree = ast.parse(source, filename=file_path)
            
            visitor = ASTCapabilityVisitor(file_path, source_lines)
            visitor.visit(tree)
            
            return visitor.detections
        except Exception as e:
            # Not valid Python or parsing failed
            return []
    
    def _detect_capabilities_in_manifest(
        self, 
        manifest: List
    ) -> List[CapabilityDetection]:
        """Detect capabilities across all files in manifest"""
        all_detections = []
        
        for entry in manifest:
            # Only analyze Python files
            if not entry.repo_relative_path.endswith('.py'):
                continue
            
            # Get file content from blob store
            try:
                content = self.artifact_store._get_blob(entry.content_hash)
                detections = self._detect_capabilities_in_file(
                    entry.repo_relative_path,
                    content
                )
                all_detections.extend(detections)
            except Exception:
                continue
        
        return all_detections
    
    def _compute_capability_delta(
        self,
        base_capabilities: List[CapabilityDetection],
        patched_capabilities: List[CapabilityDetection]
    ) -> CapabilityDelta:
        """Compute delta between base and patched capability sets"""
        # Create hashable keys for comparison
        def detection_key(d: CapabilityDetection) -> Tuple:
            return (d.capability, d.file_path, d.line_number)
        
        base_set = {detection_key(d): d for d in base_capabilities}
        patched_set = {detection_key(d): d for d in patched_capabilities}
        
        added = [patched_set[k] for k in patched_set.keys() - base_set.keys()]
        removed = [base_set[k] for k in base_set.keys() - patched_set.keys()]
        unchanged = [base_set[k] for k in base_set.keys() & patched_set.keys()]
        
        return CapabilityDelta(added=added, removed=removed, unchanged=unchanged)
    
    def _validate_syntax(self, manifest: List) -> Tuple[bool, List[str]]:
        """
        Validate Python syntax for all .py files in manifest.
        Returns (all_valid, error_messages)
        """
        errors = []
        
        # Create temp directory for syntax checking
        temp_dir = tempfile.mkdtemp(prefix="syntax_check_")
        try:
            for entry in manifest:
                if not entry.repo_relative_path.endswith('.py'):
                    continue
                
                # Write file to temp directory
                file_path = Path(temp_dir) / entry.repo_relative_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                try:
                    content = self.artifact_store._get_blob(entry.content_hash)
                    file_path.write_bytes(content)
                    
                    # Try to compile
                    py_compile.compile(str(file_path), doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"{entry.repo_relative_path}: {e.msg}")
                except Exception as e:
                    errors.append(f"{entry.repo_relative_path}: {str(e)}")
            
            return len(errors) == 0, errors
        
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def evaluate_patch(
        self,
        base_version_id: str,
        diff_content: str,
        patched_manifest: List
    ) -> SafetyEvaluation:
        """
        Evaluate safety of patched version.
        
        Args:
            base_version_id: Base version for comparison
            diff_content: The patch being evaluated
            patched_manifest: Resulting manifest after patch application
        
        Returns:
            SafetyEvaluation with issues, warnings, and capability delta
        """
        issues = []
        warnings = []
        
        # Validate syntax of resulting code
        syntax_valid, syntax_errors = self._validate_syntax(patched_manifest)
        if not syntax_valid:
            issues.extend([f"Syntax error: {e}" for e in syntax_errors])
        
        # Get base version capabilities
        base_version = self.artifact_store.get_version(base_version_id)
        base_capabilities = self._detect_capabilities_in_manifest(base_version.manifest)
        
        # Get patched version capabilities
        patched_capabilities = self._detect_capabilities_in_manifest(patched_manifest)
        
        # Compute delta
        capability_delta = self._compute_capability_delta(
            base_capabilities,
            patched_capabilities
        )
        
        # Check for dangerous new capabilities
        for detection in capability_delta.added:
            if detection.capability in (Capability.EVAL_EXEC, Capability.PICKLE):
                issues.append(
                    f"Adds dangerous capability {detection.capability.value} "
                    f"in {detection.file_path}:{detection.line_number}"
                )
            elif detection.capability in (Capability.SUBPROCESS, Capability.NETWORK_REQUEST):
                warnings.append(
                    f"Adds {detection.capability.value} capability "
                    f"in {detection.file_path}:{detection.line_number}"
                )
        
        # Compute evaluation hash for deduplication
        import hashlib
        eval_data = f"{base_version_id}:{diff_content}:{len(patched_manifest)}"
        evaluation_hash = hashlib.sha256(eval_data.encode()).hexdigest()[:16]
        
        return SafetyEvaluation(
            safe=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            capability_delta=capability_delta,
            syntax_valid=syntax_valid,
            evaluation_hash=evaluation_hash
        )
