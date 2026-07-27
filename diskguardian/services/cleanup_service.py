# -*- coding: utf-8 -*-
"""diskguardian/services/cleanup_service.py — Disk Cleanup Advisor logic."""

import os
import glob
from pathlib import Path

def get_dir_size(path: str) -> int:
    """Calculate total size of a directory in bytes."""
    total_size = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
    except Exception:
        pass
    return total_size

def find_large_files(start_path: str, min_size_mb: int = 500, max_files: int = 10) -> list[dict]:
    """Find files larger than min_size_mb in a given path."""
    large_files = []
    min_size_bytes = min_size_mb * 1024 * 1024
    
    try:
        # We only search the user's home directory to avoid hanging on entire C: drive
        for dirpath, _, filenames in os.walk(start_path):
            # Skip hidden dirs or AppData to speed up search
            if "AppData" in dirpath or "\\." in dirpath:
                continue
                
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    if not os.path.islink(fp):
                        size = os.path.getsize(fp)
                        if size > min_size_bytes:
                            large_files.append({"path": fp, "size_bytes": size})
                except Exception:
                    pass
    except Exception:
        pass

    # Sort descending by size
    large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    return large_files[:max_files]

def analyze_cleanup() -> dict:
    """
    Analyzes common storage hogs and returns recommendations.
    Does NOT delete any files.
    """
    user_home = os.path.expanduser("~")
    temp_dir = os.environ.get("TEMP", os.path.join(user_home, "AppData", "Local", "Temp"))
    downloads_dir = os.path.join(user_home, "Downloads")
    
    temp_size = get_dir_size(temp_dir)
    downloads_size = get_dir_size(downloads_dir)
    
    # Simple heuristic for Recycle Bin in Windows
    recycle_bin_size = 0
    recycle_path = "C:\\$Recycle.Bin"
    if os.path.exists(recycle_path):
        recycle_bin_size = get_dir_size(recycle_path)

    large_files = find_large_files(user_home, min_size_mb=500, max_files=10)
    
    total_reclaimable = temp_size + recycle_bin_size
    
    return {
        "temp_files": {
            "path": temp_dir,
            "size_bytes": temp_size,
            "recommendation": "Safe to delete temporary files." if temp_size > 500 * 1024 * 1024 else "No action needed.",
            "is_issue": temp_size > 500 * 1024 * 1024
        },
        "downloads": {
            "path": downloads_dir,
            "size_bytes": downloads_size,
            "recommendation": "Review old downloaded files." if downloads_size > 1024 * 1024 * 1024 else "No action needed.",
            "is_issue": downloads_size > 5 * 1024 * 1024 * 1024
        },
        "recycle_bin": {
            "path": recycle_path,
            "size_bytes": recycle_bin_size,
            "recommendation": "Empty recycle bin." if recycle_bin_size > 500 * 1024 * 1024 else "No action needed.",
            "is_issue": recycle_bin_size > 500 * 1024 * 1024
        },
        "large_files": large_files,
        "total_reclaimable_bytes": total_reclaimable
    }
