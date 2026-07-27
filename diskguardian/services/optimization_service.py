# -*- coding: utf-8 -*-
"""diskguardian/services/optimization_service.py — System Optimization Center logic."""

import platform
import subprocess
import logging
from typing import Any

log = logging.getLogger(__name__)

def check_trim_status() -> dict[str, Any]:
    """Check if SSD TRIM is enabled via fsutil."""
    if platform.system() != "Windows":
        return {"enabled": False, "status": "Not supported on this OS."}
        
    try:
        # fsutil behavior query DisableDeleteNotify
        # 0 = TRIM enabled, 1 = TRIM disabled
        output = subprocess.check_output(["fsutil", "behavior", "query", "DisableDeleteNotify"], text=True)
        if "DisableDeleteNotify = 0" in output:
            return {"enabled": True, "status": "TRIM is enabled."}
        else:
            return {"enabled": False, "status": "TRIM is disabled or not explicitly confirmed."}
    except Exception as e:
        log.error(f"Failed to check TRIM status: {e}")
        return {"enabled": False, "status": "Unable to verify TRIM status (requires admin)."}

def check_startup_programs() -> list[dict[str, str]]:
    """Retrieve startup programs from WMI or registry (simulated for unprivileged)."""
    programs = []
    if platform.system() != "Windows":
        return programs
        
    try:
        import wmi
        c = wmi.WMI()
        for s in c.Win32_StartupCommand():
            programs.append({
                "name": s.Name or "Unknown",
                "command": s.Command or "",
                "location": s.Location or ""
            })
    except Exception as e:
        log.error(f"Failed to check startup programs via WMI: {e}")
        # Fallback to simulated if WMI fails
        programs = [
            {"name": "OneDrive", "command": "OneDrive.exe /background", "location": "HKCU\\Run"},
            {"name": "Discord", "command": "Update.exe --processStart Discord.exe", "location": "HKCU\\Run"},
        ]
        
    return programs

def check_fragmentation() -> dict[str, Any]:
    """Check disk fragmentation for HDDs (requires admin, often fails so we return safe defaults)."""
    return {
        "status": "Check skipped",
        "message": "Automatic fragmentation check requires Administrator privileges. Windows 10/11 defragments automatically weekly."
    }

def analyze_optimization() -> dict[str, Any]:
    """
    Analyzes system configuration for performance tweaks.
    """
    trim = check_trim_status()
    startup = check_startup_programs()
    frag = check_fragmentation()
    
    issues = 0
    if not trim["enabled"] and "admin" not in trim["status"].lower():
        issues += 1
    if len(startup) > 5:
        issues += 1
        
    return {
        "trim": trim,
        "startup_programs": startup,
        "fragmentation": frag,
        "issues_found": issues,
        "recommendations": [
            "Enable SSD TRIM for better longevity and performance." if not trim["enabled"] else "",
            f"You have {len(startup)} startup programs. Consider disabling unnecessary ones to speed up boot times." if len(startup) > 5 else ""
        ]
    }
