"""
ApprovalStateMachine V3: Fully DB-backed approval workflow
"""
import sqlite3
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class ApprovalStatus(Enum):
    """Approval request states"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


@dataclass
class PatchProposal:
    """Patch proposal with metadata"""
    proposal_id: str
    artifact_id: str
    base_version_id: str
    diff_content: str
    requirements: str
    created_at: str
    diff_hash: str


@dataclass
class ApprovalRequest:
    """Approval request with safety evaluation"""
    request_id: str
    proposal_id: str
    status: ApprovalStatus
    created_at: str
    evaluation_hash: str
    safety_evaluation: Dict
    decision_at: Optional[str] = None
    decision_reason: Optional[str] = None


class ApprovalStateMachine:
    """
    Fully DB-backed approval workflow.
    Zero in-memory state - everything persisted.
    """
    
    def __init__(self, db_path: str = "artifacts.db"):
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get DB connection with FK enforcement"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize approval workflow tables"""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS patch_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    base_version_id TEXT NOT NULL,
                    diff_content TEXT NOT NULL,
                    diff_hash TEXT NOT NULL,
                    requirements TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id),
                    FOREIGN KEY (base_version_id) REFERENCES versions(version_id)
                );
                
                CREATE TABLE IF NOT EXISTS approval_requests (
                    request_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    evaluation_hash TEXT NOT NULL,
                    safety_evaluation TEXT NOT NULL,
                    decision_at TEXT,
                    decision_reason TEXT,
                    FOREIGN KEY (proposal_id) REFERENCES patch_proposals(proposal_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_approval_status 
                ON approval_requests(status);
                
                CREATE INDEX IF NOT EXISTS idx_proposal_artifact 
                ON patch_proposals(artifact_id);
            """)
            conn.commit()
        finally:
            conn.close()
    
    def create_patch_proposal(
        self,
        artifact_id: str,
        base_version_id: str,
        diff_content: str,
        requirements: str
    ) -> str:
        """
        Create patch proposal.
        Returns proposal_id.
        """
        # Compute diff hash
        diff_hash = hashlib.sha256(diff_content.encode()).hexdigest()[:16]
        
        # Generate proposal ID
        proposal_id = hashlib.sha256(
            f"{artifact_id}:{base_version_id}:{diff_hash}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        conn = self._get_connection()
        try:
            conn.execute(
                """INSERT INTO patch_proposals 
                   (proposal_id, artifact_id, base_version_id, diff_content, 
                    diff_hash, requirements, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (proposal_id, artifact_id, base_version_id, diff_content,
                 diff_hash, requirements, datetime.utcnow().isoformat())
            )
            conn.commit()
        finally:
            conn.close()
        
        return proposal_id
    
    def get_patch_proposal(self, proposal_id: str) -> Optional[PatchProposal]:
        """Get patch proposal by ID"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM patch_proposals WHERE proposal_id = ?""",
                (proposal_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            return PatchProposal(
                proposal_id=row['proposal_id'],
                artifact_id=row['artifact_id'],
                base_version_id=row['base_version_id'],
                diff_content=row['diff_content'],
                requirements=row['requirements'],
                created_at=row['created_at'],
                diff_hash=row['diff_hash']
            )
        finally:
            conn.close()
    
    def create_approval_request(
        self,
        proposal_id: str,
        safety_evaluation: Dict
    ) -> str:
        """
        Create approval request from proposal and safety evaluation.
        Returns request_id.
        """
        # Generate request ID
        request_id = hashlib.sha256(
            f"{proposal_id}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Get evaluation hash from safety evaluation
        evaluation_hash = safety_evaluation.get('evaluation_hash', 'unknown')
        
        conn = self._get_connection()
        try:
            conn.execute(
                """INSERT INTO approval_requests 
                   (request_id, proposal_id, status, created_at, 
                    evaluation_hash, safety_evaluation)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (request_id, proposal_id, ApprovalStatus.PENDING.value,
                 datetime.utcnow().isoformat(), evaluation_hash,
                 json.dumps(safety_evaluation))
            )
            conn.commit()
        finally:
            conn.close()
        
        return request_id
    
    def get_approval_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get approval request by ID"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM approval_requests WHERE request_id = ?""",
                (request_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            return ApprovalRequest(
                request_id=row['request_id'],
                proposal_id=row['proposal_id'],
                status=ApprovalStatus(row['status']),
                created_at=row['created_at'],
                evaluation_hash=row['evaluation_hash'],
                safety_evaluation=json.loads(row['safety_evaluation']),
                decision_at=row['decision_at'],
                decision_reason=row['decision_reason']
            )
        finally:
            conn.close()
    
    def list_pending_requests(self) -> List[Dict]:
        """List all pending approval requests (DB query)"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT r.*, p.artifact_id, p.base_version_id, p.requirements
                   FROM approval_requests r
                   JOIN patch_proposals p ON r.proposal_id = p.proposal_id
                   WHERE r.status = ?
                   ORDER BY r.created_at ASC""",
                (ApprovalStatus.PENDING.value,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def list_requests_by_status(self, status: ApprovalStatus) -> List[Dict]:
        """List approval requests by status"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT r.*, p.artifact_id, p.base_version_id
                   FROM approval_requests r
                   JOIN patch_proposals p ON r.proposal_id = p.proposal_id
                   WHERE r.status = ?
                   ORDER BY r.created_at DESC""",
                (status.value,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def submit_decision(
        self,
        request_id: str,
        approved: bool,
        reason: Optional[str] = None
    ) -> bool:
        """
        Submit approval decision.
        Returns success status.
        """
        # Check request exists and is pending
        request = self.get_approval_request(request_id)
        if not request:
            return False
        
        if request.status != ApprovalStatus.PENDING:
            return False
        
        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        
        conn = self._get_connection()
        try:
            conn.execute(
                """UPDATE approval_requests
                   SET status = ?, decision_at = ?, decision_reason = ?
                   WHERE request_id = ?""",
                (new_status.value, datetime.utcnow().isoformat(), reason, request_id)
            )
            conn.commit()
        finally:
            conn.close()
        
        return True
    
    def mark_applied(self, request_id: str, version_id: str) -> bool:
        """
        Mark approval request as applied after patch application.
        Returns success status.
        """
        request = self.get_approval_request(request_id)
        if not request:
            return False
        
        if request.status != ApprovalStatus.APPROVED:
            return False
        
        conn = self._get_connection()
        try:
            conn.execute(
                """UPDATE approval_requests
                   SET status = ?
                   WHERE request_id = ?""",
                (ApprovalStatus.APPLIED.value, request_id)
            )
            conn.commit()
        finally:
            conn.close()
        
        return True
    
    def get_approval_by_proposal(self, proposal_id: str) -> Optional[ApprovalRequest]:
        """Get most recent approval request for a proposal"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM approval_requests 
                   WHERE proposal_id = ?
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (proposal_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            return ApprovalRequest(
                request_id=row['request_id'],
                proposal_id=row['proposal_id'],
                status=ApprovalStatus(row['status']),
                created_at=row['created_at'],
                evaluation_hash=row['evaluation_hash'],
                safety_evaluation=json.loads(row['safety_evaluation']),
                decision_at=row['decision_at'],
                decision_reason=row['decision_reason']
            )
        finally:
            conn.close()


class PatchLifecycle:
    """
    High-level API for complete patch lifecycle.
    Orchestrates proposal → evaluation → approval → application.
    """
    
    def __init__(
        self,
        artifact_store,
        patch_applier,
        safety_checker,
        approval_workflow
    ):
        self.artifact_store = artifact_store
        self.patch_applier = patch_applier
        self.safety_checker = safety_checker
        self.approval_workflow = approval_workflow
    
    def propose_patch(
        self,
        artifact_id: str,
        base_version_id: str,
        diff_content: str,
        requirements: str
    ) -> str:
        """
        Create patch proposal.
        Returns proposal_id.
        """
        return self.approval_workflow.create_patch_proposal(
            artifact_id, base_version_id, diff_content, requirements
        )
    
    def request_approval(self, proposal_id: str) -> tuple[bool, str, Optional[str]]:
        """
        Evaluate patch and create approval request.
        Returns (success, request_id, error_message)
        """
        # Get proposal
        proposal = self.approval_workflow.get_patch_proposal(proposal_id)
        if not proposal:
            return False, "", "Proposal not found"
        
        # Apply patch to get resulting manifest
        apply_result = self.patch_applier.apply_to_workspace(
            proposal.base_version_id,
            proposal.diff_content
        )
        
        if not apply_result.success:
            return False, "", f"Patch does not apply cleanly: {apply_result.error_message}"
        
        # Evaluate safety
        safety_eval = self.safety_checker.evaluate_patch(
            proposal.base_version_id,
            proposal.diff_content,
            apply_result.resulting_manifest
        )
        
        # Create approval request
        request_id = self.approval_workflow.create_approval_request(
            proposal_id,
            {
                'safe': safety_eval.safe,
                'issues': safety_eval.issues,
                'warnings': safety_eval.warnings,
                'syntax_valid': safety_eval.syntax_valid,
                'evaluation_hash': safety_eval.evaluation_hash,
                'capability_delta': {
                    'added': [asdict(d) for d in safety_eval.capability_delta.added],
                    'removed': [asdict(d) for d in safety_eval.capability_delta.removed],
                }
            }
        )
        
        return True, request_id, None
    
    def apply_approved_patch(self, proposal_id: str) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Apply an approved patch and create new version.
        Returns (success, version_id, error_message)
        """
        # Get approval request
        approval = self.approval_workflow.get_approval_by_proposal(proposal_id)
        if not approval:
            return False, None, "No approval request found"
        
        if approval.status != ApprovalStatus.APPROVED:
            return False, None, f"Patch not approved (status: {approval.status.value})"
        
        # Get proposal
        proposal = self.approval_workflow.get_patch_proposal(proposal_id)
        if not proposal:
            return False, None, "Proposal not found"
        
        # Apply patch and create version
        success, version_id, error = self.patch_applier.apply_and_create_version(
            proposal.artifact_id,
            proposal.base_version_id,
            proposal.diff_content,
            proposal.requirements
        )
        
        if success:
            # Mark as applied
            self.approval_workflow.mark_applied(approval.request_id, version_id)
        
        return success, version_id, error
