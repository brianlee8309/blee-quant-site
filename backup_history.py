"""
backup_history.py
-----------------
Creates a timestamped backup of Algorithm185History.html before any overwrite.
Keeps the last MAX_BACKUPS copies; older ones are deleted automatically.

Usage (standalone):
    python backup_history.py

Usage (imported):
    from backup_history import backup_before_write
    backup_before_write()          # call before writing Algorithm185History.html
"""

import os, shutil, glob, datetime

HTML_FILE  = os.path.join(os.path.dirname(__file__), "Algorithm185History.html")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
MAX_BACKUPS = 7          # keep one week of daily backups


def backup_before_write(html_file=HTML_FILE, backup_dir=BACKUP_DIR, max_backups=MAX_BACKUPS):
    """
    Copy html_file → backups/Algorithm185History_YYYYMMDD_HHMMSS.html
    Then prune so only the newest max_backups files remain.
    Returns the backup path on success, None if source didn't exist.
    """
    if not os.path.exists(html_file):
        print(f"[backup] Source not found: {html_file}")
        return None

    os.makedirs(backup_dir, exist_ok=True)

    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"Algorithm185History_{ts}.html"
    dest = os.path.join(backup_dir, name)

    shutil.copy2(html_file, dest)
    size = os.path.getsize(dest)
    print(f"[backup] Saved → {dest}  ({size:,} bytes)")

    # Prune oldest backups beyond max_backups
    pattern = os.path.join(backup_dir, "Algorithm185History_*.html")
    existing = sorted(glob.glob(pattern))          # sorted oldest→newest
    while len(existing) > max_backups:
        oldest = existing.pop(0)
        os.remove(oldest)
        print(f"[backup] Pruned old backup: {os.path.basename(oldest)}")

    return dest


if __name__ == "__main__":
    result = backup_before_write()
    if result:
        print("[backup] Done.")
    else:
        print("[backup] Nothing to back up.")
