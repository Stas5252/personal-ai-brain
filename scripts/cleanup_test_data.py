#!/usr/bin/env python3
"""
Cleanup script: removes duplicate test data from the production database.

Run BEFORE going to production:
    python scripts/cleanup_test_data.py           # preview (dry-run)
    python scripts/cleanup_test_data.py --execute  # apply changes

Findings addressed:
 - 69 duplicate 'Анна Смирнова [LEAD]' test clients
 - 46 duplicate 'Fashion Campaign 2026 [PLANNING]' test projects
 - Other obvious test/seed entries

Safe: always shows a preview first, requires --execute flag to delete.
"""
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.brain.db import get_connection


def preview_duplicates(conn):
    """Show what would be cleaned up."""
    c = conn.cursor()
    print("\n=== DUPLICATE CLIENTS ===")
    c.execute("""
        SELECT name, status, COUNT(*) as cnt
        FROM clients
        GROUP BY name, status
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(f"  [{row['cnt']}x] {row['name']} ({row['status']})")
    else:
        print("  No duplicates found.")

    print("\n=== DUPLICATE PROJECTS ===")
    c.execute("""
        SELECT name, status, COUNT(*) as cnt
        FROM projects
        GROUP BY name, status
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(f"  [{row['cnt']}x] {row['name']} ({row['status']})")
    else:
        print("  No duplicates found.")

    print("\n=== SUSPICIOUS TEST ENTRIES ===")
    test_keywords = ['test', 'Test', 'тест', 'Тест', 'ТЕСТ', 'dummy', 'example',
                     'Anna Smirnova', 'Анна Смирнова', 'Fashion Campaign 2026']
    c.execute("SELECT id, name, status, created_at FROM clients ORDER BY created_at")
    test_clients = [r for r in c.fetchall()
                    if any(k.lower() in (r['name'] or '').lower() for k in test_keywords)]
    if test_clients:
        print(f"  Clients matching test keywords: {len(test_clients)}")
        for r in test_clients[:10]:
            print(f"    {r['id'][:8]}... | {r['name']} | {r['status']} | {r['created_at'][:10]}")
    else:
        print("  No test clients found.")

    c.execute("SELECT id, name, status FROM projects ORDER BY created_at")
    test_projects = [r for r in c.fetchall()
                     if any(k.lower() in (r['name'] or '').lower() for k in test_keywords)]
    if test_projects:
        print(f"  Projects matching test keywords: {len(test_projects)}")
        for r in test_projects[:10]:
            print(f"    {r['id'][:8]}... | {r['name']} | {r['status']}")
    else:
        print("  No test projects found.")


def cleanup(conn, dry_run: bool = True):
    """Remove duplicates and test entries."""
    c = conn.cursor()
    deleted_clients = 0
    deleted_projects = 0

    # 1. Remove duplicate clients (keep the oldest one per name+status group)
    c.execute("""
        SELECT name, status
        FROM clients
        GROUP BY name, status
        HAVING COUNT(*) > 1
    """)
    dup_groups = c.fetchall()
    for group in dup_groups:
        c.execute("""
            SELECT id FROM clients
            WHERE name = ? AND status = ?
            ORDER BY created_at ASC
        """, (group['name'], group['status']))
        ids = [r['id'] for r in c.fetchall()]
        to_delete = ids[1:]  # Keep the first (oldest)
        if to_delete:
            print(f"  {'[DRY-RUN] ' if dry_run else ''}Removing {len(to_delete)} duplicate clients: '{group['name']}'")
            if not dry_run:
                c.executemany("DELETE FROM clients WHERE id = ?", [(i,) for i in to_delete])
                deleted_clients += len(to_delete)

    # 2. Remove duplicate projects (keep the oldest one)
    c.execute("""
        SELECT name, status
        FROM projects
        GROUP BY name, status
        HAVING COUNT(*) > 1
    """)
    dup_proj_groups = c.fetchall()
    for group in dup_proj_groups:
        c.execute("""
            SELECT id FROM projects
            WHERE name = ? AND status = ?
            ORDER BY created_at ASC
        """, (group['name'], group['status']))
        ids = [r['id'] for r in c.fetchall()]
        to_delete = ids[1:]
        if to_delete:
            print(f"  {'[DRY-RUN] ' if dry_run else ''}Removing {len(to_delete)} duplicate projects: '{group['name']}'")
            if not dry_run:
                c.executemany("DELETE FROM projects WHERE id = ?", [(i,) for i in to_delete])
                deleted_projects += len(to_delete)

    # 3. Remove known test seed patterns (keep 1 example each)
    test_client_patterns = ['Анна Смирнова', 'Anna Smirnova', 'test_client', 'TestClient']
    test_project_patterns = ['Fashion Campaign 2026', 'test_project', 'TestProject']

    for pattern in test_client_patterns:
        c.execute("SELECT id, name FROM clients WHERE name LIKE ? ORDER BY created_at ASC",
                  (f'%{pattern}%',))
        candidates = c.fetchall()
        if len(candidates) > 1:
            to_delete = [r['id'] for r in candidates[1:]]  # Keep first one
            print(f"  {'[DRY-RUN] ' if dry_run else ''}Removing {len(to_delete)} test clients: '{pattern}'")
            if not dry_run:
                c.executemany("DELETE FROM clients WHERE id = ?", [(i,) for i in to_delete])
                deleted_clients += len(to_delete)

    for pattern in test_project_patterns:
        c.execute("SELECT id, name FROM projects WHERE name LIKE ? ORDER BY created_at ASC",
                  (f'%{pattern}%',))
        candidates = c.fetchall()
        if len(candidates) > 1:
            to_delete = [r['id'] for r in candidates[1:]]
            print(f"  {'[DRY-RUN] ' if dry_run else ''}Removing {len(to_delete)} test projects: '{pattern}'")
            if not dry_run:
                c.executemany("DELETE FROM projects WHERE id = ?", [(i,) for i in to_delete])
                deleted_projects += len(to_delete)

    if not dry_run:
        conn.commit()
        print(f"\n✅ Done! Removed {deleted_clients} clients, {deleted_projects} projects.")
    else:
        print("\n[DRY-RUN] No changes made. Run with --execute to apply.")


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup duplicate test data from production DB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cleanup_test_data.py           # preview only
  python scripts/cleanup_test_data.py --execute  # apply deletions
"""
    )
    parser.add_argument('--execute', action='store_true',
                        help='Actually delete data (default is dry-run preview)')
    parser.add_argument('--no-preview', action='store_true',
                        help='Skip the preview step')
    args = parser.parse_args()

    conn = get_connection()
    try:
        if not args.no_preview:
            preview_duplicates(conn)
            print()

        dry_run = not args.execute
        if dry_run:
            print("=== Running in DRY-RUN mode (use --execute to apply) ===")
        else:
            print("⚠️  EXECUTING deletions — this cannot be undone!")
            response = input("Continue? [y/N] ").strip().lower()
            if response != 'y':
                print("Aborted.")
                return

        cleanup(conn, dry_run=dry_run)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
