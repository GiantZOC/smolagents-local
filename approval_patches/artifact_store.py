"""
ArtifactStore V3: Fully DB-backed, workspace-first architecture
"""
import sqlite3
import hashlib
import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class FileManifestEntry:
    """Represents a single file in a workspace snapshot"""
    repo_relative_path: str
    content_hash: str  # SHA256
    file_size: int


@dataclass
class Version:
    """Version metadata with file manifest"""
    version_id: str
    artifact_id: str
    created_at: str
    base_version_id: Optional[str]
    commit_message: str
    manifest: List[FileManifestEntry]


class ArtifactStore:
    """
    Database-backed artifact storage with content-addressed blobs.
    Every version is a workspace snapshot with deterministic file manifest.
    """
    
    def __init__(self, db_path: str = "artifacts.db", blob_dir: str = "artifact_blobs"):
        self.db_path = db_path
        self.blob_dir = Path(blob_dir)
        self.blob_dir.mkdir(exist_ok=True)
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get DB connection with FK enforcement"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT
                );
                
                CREATE TABLE IF NOT EXISTS versions (
                    version_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    base_version_id TEXT,
                    commit_message TEXT,
                    FOREIGN KEY (artifact_id) REFERENCES artifacts(artifact_id),
                    FOREIGN KEY (base_version_id) REFERENCES versions(version_id)
                );
                
                CREATE TABLE IF NOT EXISTS file_manifests (
                    manifest_id TEXT PRIMARY KEY,
                    version_id TEXT NOT NULL,
                    repo_relative_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    FOREIGN KEY (version_id) REFERENCES versions(version_id),
                    UNIQUE(version_id, repo_relative_path)
                );
                
                CREATE INDEX IF NOT EXISTS idx_version_artifact 
                ON versions(artifact_id);
                
                CREATE INDEX IF NOT EXISTS idx_manifest_version 
                ON file_manifests(version_id);
            """)
            conn.commit()
        finally:
            conn.close()
    
    def _compute_file_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content"""
        return hashlib.sha256(content).hexdigest()
    
    def _store_blob(self, content: bytes, content_hash: str) -> str:
        """Store content-addressed blob, return path"""
        # Two-level directory structure: blobs/ab/cdef...
        dir_path = self.blob_dir / content_hash[:2]
        dir_path.mkdir(exist_ok=True)
        blob_path = dir_path / content_hash[2:]
        
        # Only write if doesn't exist (content-addressed = dedup)
        if not blob_path.exists():
            blob_path.write_bytes(content)
        
        return str(blob_path)
    
    def _get_blob(self, content_hash: str) -> bytes:
        """Retrieve blob by content hash"""
        blob_path = self.blob_dir / content_hash[:2] / content_hash[2:]
        if not blob_path.exists():
            raise FileNotFoundError(f"Blob not found: {content_hash}")
        return blob_path.read_bytes()
    
    def _build_file_manifest(self, workspace_path: str) -> List[FileManifestEntry]:
        """
        Build deterministic file manifest from workspace.
        Walks directory tree and computes hashes.
        """
        workspace = Path(workspace_path).resolve()
        if not workspace.is_dir():
            raise ValueError(f"Workspace path is not a directory: {workspace_path}")
        
        manifest: List[FileManifestEntry] = []
        
        # Walk all files in workspace
        for root, dirs, files in os.walk(workspace):
            # Skip hidden directories and common ignore patterns
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for file in files:
                # Skip hidden files and bytecode
                if file.startswith('.') or file.endswith('.pyc'):
                    continue
                
                file_path = Path(root) / file
                
                # Compute repo-relative path
                try:
                    relative_path = file_path.relative_to(workspace)
                except ValueError:
                    continue  # Skip files outside workspace
                
                # Read content and compute hash
                try:
                    content = file_path.read_bytes()
                    content_hash = self._compute_file_hash(content)
                    file_size = len(content)
                    
                    # Store blob
                    self._store_blob(content, content_hash)
                    
                    # Add to manifest
                    manifest.append(FileManifestEntry(
                        repo_relative_path=str(relative_path),
                        content_hash=content_hash,
                        file_size=file_size
                    ))
                except Exception as e:
                    print(f"Warning: Failed to process {file_path}: {e}")
                    continue
        
        # Sort for deterministic ordering
        manifest.sort(key=lambda e: e.repo_relative_path)
        return manifest
    
    def create_artifact(self, name: str, metadata: Optional[Dict] = None) -> str:
        """Create a new artifact container"""
        artifact_id = hashlib.sha256(f"{name}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
        
        conn = self._get_connection()
        try:
            conn.execute(
                """INSERT INTO artifacts (artifact_id, name, created_at, metadata)
                   VALUES (?, ?, ?, ?)""",
                (artifact_id, name, datetime.utcnow().isoformat(), 
                 json.dumps(metadata) if metadata else None)
            )
            conn.commit()
        finally:
            conn.close()
        
        return artifact_id
    
    def create_workspace_artifact(
        self, 
        name: str, 
        workspace_path: str,
        commit_message: str = "Initial version",
        metadata: Optional[Dict] = None
    ) -> Tuple[str, str]:
        """
        Create artifact from workspace directory.
        Returns (artifact_id, version_id)
        """
        # Create artifact
        artifact_id = self.create_artifact(name, metadata)
        
        # Build file manifest
        manifest = self._build_file_manifest(workspace_path)
        
        # Create initial version
        version_id = self._create_version_with_manifest(
            artifact_id=artifact_id,
            base_version_id=None,
            commit_message=commit_message,
            manifest=manifest
        )
        
        return artifact_id, version_id
    
    def _create_version_with_manifest(
        self,
        artifact_id: str,
        manifest: List[FileManifestEntry],
        commit_message: str,
        base_version_id: Optional[str] = None
    ) -> str:
        """Create version with file manifest (internal)"""
        # Compute deterministic version_id from manifest
        manifest_data = json.dumps(
            [asdict(e) for e in manifest],
            sort_keys=True
        )
        version_id = hashlib.sha256(
            f"{artifact_id}:{manifest_data}".encode()
        ).hexdigest()[:16]
        
        conn = self._get_connection()
        try:
            # Insert version (artifact must exist due to FK)
            conn.execute(
                """INSERT INTO versions (version_id, artifact_id, created_at, 
                   base_version_id, commit_message)
                   VALUES (?, ?, ?, ?, ?)""",
                (version_id, artifact_id, datetime.utcnow().isoformat(),
                 base_version_id, commit_message)
            )
            
            # Insert manifest entries
            for entry in manifest:
                manifest_id = hashlib.sha256(
                    f"{version_id}:{entry.repo_relative_path}".encode()
                ).hexdigest()[:16]
                
                conn.execute(
                    """INSERT INTO file_manifests 
                       (manifest_id, version_id, repo_relative_path, content_hash, file_size)
                       VALUES (?, ?, ?, ?, ?)""",
                    (manifest_id, version_id, entry.repo_relative_path, 
                     entry.content_hash, entry.file_size)
                )
            
            conn.commit()
        finally:
            conn.close()
        
        return version_id
    
    def get_version(self, version_id: str) -> Optional[Version]:
        """Get version metadata with manifest"""
        conn = self._get_connection()
        try:
            # Get version metadata
            cursor = conn.execute(
                """SELECT * FROM versions WHERE version_id = ?""",
                (version_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get manifest entries
            manifest_cursor = conn.execute(
                """SELECT repo_relative_path, content_hash, file_size
                   FROM file_manifests
                   WHERE version_id = ?
                   ORDER BY repo_relative_path""",
                (version_id,)
            )
            
            manifest = [
                FileManifestEntry(
                    repo_relative_path=m['repo_relative_path'],
                    content_hash=m['content_hash'],
                    file_size=m['file_size']
                )
                for m in manifest_cursor.fetchall()
            ]
            
            return Version(
                version_id=row['version_id'],
                artifact_id=row['artifact_id'],
                created_at=row['created_at'],
                base_version_id=row['base_version_id'],
                commit_message=row['commit_message'],
                manifest=manifest
            )
        finally:
            conn.close()
    
    def get_version_content(self, version_id: str, repo_relative_path: str) -> Optional[bytes]:
        """Get specific file content from version"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT content_hash FROM file_manifests
                   WHERE version_id = ? AND repo_relative_path = ?""",
                (version_id, repo_relative_path)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            return self._get_blob(row['content_hash'])
        finally:
            conn.close()
    
    def export_version_to_workspace(self, version_id: str, target_path: str) -> bool:
        """
        Export version to filesystem workspace.
        Reconstructs all files from manifest.
        """
        version = self.get_version(version_id)
        if not version:
            return False
        
        target = Path(target_path)
        target.mkdir(parents=True, exist_ok=True)
        
        # Reconstruct all files
        for entry in version.manifest:
            file_path = target / entry.repo_relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get content from blob store
            content = self._get_blob(entry.content_hash)
            
            # Verify hash
            if self._compute_file_hash(content) != entry.content_hash:
                raise ValueError(f"Content hash mismatch for {entry.repo_relative_path}")
            
            # Write file
            file_path.write_bytes(content)
        
        return True
    
    def list_versions(self, artifact_id: str) -> List[Dict]:
        """List all versions for an artifact"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT version_id, created_at, commit_message, base_version_id
                   FROM versions
                   WHERE artifact_id = ?
                   ORDER BY created_at DESC""",
                (artifact_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_artifact(self, artifact_id: str) -> Optional[Dict]:
        """Get artifact metadata"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT * FROM artifacts WHERE artifact_id = ?""",
                (artifact_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            result = dict(row)
            if result['metadata']:
                result['metadata'] = json.loads(result['metadata'])
            return result
        finally:
            conn.close()
