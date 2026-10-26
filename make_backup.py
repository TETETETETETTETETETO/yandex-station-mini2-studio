"""
Automatic Project Backup & Rollback Utility
"""

import os
import zipfile
import datetime

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUPS_DIR = os.path.join(PROJ_DIR, "backups")

def create_backup(tag=""):
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{tag}" if tag else ""
    zip_name = f"backup_{now_str}{suffix}.zip"
    zip_path = os.path.join(BACKUPS_DIR, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(PROJ_DIR):
            if any(p in root for p in [".git", "backups", "__pycache__"]):
                continue
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, PROJ_DIR)
                z.write(full, rel)

    size_kb = os.path.getsize(zip_path) // 1024
    print(f"[+] Backup saved: backups/{zip_name} ({size_kb} KB)")
    return zip_path

if __name__ == "__main__":
    import sys
    tag = sys.argv[1] if len(sys.argv) > 1 else "manual"
    create_backup(tag)
