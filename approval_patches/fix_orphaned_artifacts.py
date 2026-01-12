#!/usr/bin/env python3
"""
Fix orphaned artifacts that don't have any versions.

This script identifies artifacts that have no associated versions and either:
1. Deletes them (if they're just test artifacts)
2. Prompts you to create an initial version if they should be kept
"""

import sqlite3
import sys
from pathlib import Path

def get_orphaned_artifacts(db_path="artifacts.db"):
    """Find artifacts with no versions"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT a.artifact_id, a.name, a.created_at
        FROM artifacts a
        LEFT JOIN versions v ON a.artifact_id = v.artifact_id
        WHERE v.version_id IS NULL
        ORDER BY a.created_at DESC
    """)
    
    orphans = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return orphans


def delete_orphaned_artifacts(db_path="artifacts.db"):
    """Delete all orphaned artifacts"""
    conn = sqlite3.connect(db_path)
    
    # First, find orphans
    cursor = conn.execute("""
        SELECT a.artifact_id
        FROM artifacts a
        LEFT JOIN versions v ON a.artifact_id = v.artifact_id
        WHERE v.version_id IS NULL
    """)
    
    orphan_ids = [row[0] for row in cursor.fetchall()]
    
    if not orphan_ids:
        print("✅ No orphaned artifacts found")
        conn.close()
        return 0
    
    # Delete them
    placeholders = ','.join('?' * len(orphan_ids))
    conn.execute(f"""
        DELETE FROM artifacts
        WHERE artifact_id IN ({placeholders})
    """, orphan_ids)
    
    conn.commit()
    deleted_count = len(orphan_ids)
    conn.close()
    
    return deleted_count


def main():
    db_path = "artifacts.db"
    
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    print("=" * 70)
    print("🔧 ORPHANED ARTIFACT CLEANUP")
    print("=" * 70)
    
    # Find orphaned artifacts
    orphans = get_orphaned_artifacts(db_path)
    
    if not orphans:
        print("\n✅ No orphaned artifacts found!")
        print("\nYour database is clean.")
        return
    
    print(f"\n⚠️  Found {len(orphans)} orphaned artifact(s):")
    print("\n" + "-" * 70)
    for i, orphan in enumerate(orphans, 1):
        print(f"{i}. Artifact ID: {orphan['artifact_id']}")
        print(f"   Name: {orphan['name']}")
        print(f"   Created: {orphan['created_at']}")
        print(f"   Problem: No versions associated with this artifact")
        print()
    
    print("-" * 70)
    print("\nThese artifacts cannot be used for patching because they have no base version.")
    print("\nOptions:")
    print("  1. Delete all orphaned artifacts (recommended)")
    print("  2. Keep them (you'll need to manually create versions)")
    print("  3. Cancel")
    
    while True:
        choice = input("\nYour choice (1-3): ").strip()
        
        if choice == "1":
            # Delete orphans
            deleted = delete_orphaned_artifacts(db_path)
            print(f"\n✅ Deleted {deleted} orphaned artifact(s)")
            print("\n💡 Next steps:")
            print("   - Create new workspace artifacts using create_workspace_artifact()")
            print("   - This will properly create both the artifact AND initial version")
            break
        
        elif choice == "2":
            print("\n⚠️  Keeping orphaned artifacts")
            print("\n💡 To make them usable, you must:")
            print("   1. Create a workspace directory with the code")
            print("   2. Manually call artifact_store._create_version_with_manifest()")
            print("   3. Or delete them and recreate with create_workspace_artifact()")
            break
        
        elif choice == "3":
            print("\n❌ Cancelled")
            break
        
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
