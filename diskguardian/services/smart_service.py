# -*- coding: utf-8 -*-
"""diskguardian/services/smart_service.py
SMART data reader: tries WMI → pySMART → graceful simulated fallback.
All three paths produce the same output schema.
"""

import random
import datetime
from typing import Any

# ── Try WMI (Windows, no admin needed for basic info) ────────────────────────
try:
    import wmi as _wmi
    _WMI = _wmi.WMI()
    _HAS_WMI = True
except Exception:
    _HAS_WMI = False

# ── Try pySMART (needs smartmontools installed) ───────────────────────────────
try:
    from pySMART import DeviceList as _DeviceList
    _HAS_SMART = True
except Exception:
    _HAS_SMART = False


def _health_label(pct: float) -> str:
    if pct >= 90: return "Excellent"
    if pct >= 70: return "Good"
    if pct >= 50: return "Warning"
    return "Critical"


def _risk_label(score: float) -> str:
    if score >= 80: return "low"
    if score >= 60: return "medium"
    if score >= 40: return "high"
    return "critical"


def _simulated_smart(drive_path: str = "C:") -> dict[str, Any]:
    """Generate realistic-looking simulated SMART data when hardware access fails."""
    seed = sum(ord(c) for c in drive_path)
    rng  = random.Random(seed)

    hours  = rng.randint(500, 25000)
    realloc = rng.randint(0, 5)
    pending = rng.randint(0, 3)
    temp    = rng.randint(28, 48)
    health  = max(60, 100 - realloc * 8 - pending * 5 - max(0, temp - 40) * 2)

    # Determine SSD vs HDD
    is_ssd = drive_path.upper() in ("C:", "D:") or rng.random() > 0.4
    drive_type = "SSD" if is_ssd else "HDD"

    wear = max(50, 100 - int(hours / 300)) if is_ssd else None

    model_pool = {
        "SSD": ["Samsung 870 EVO 500GB", "Crucial MX500 1TB", "WD Blue SN570 500GB NVMe",
                 "Kingston A400 480GB", "Seagate BarraCuda Q1 SSD"],
        "HDD": ["WDC WD10EZEX 1TB", "Seagate ST2000DM008 2TB", "Toshiba DT01ACA200 2TB",
                 "WDC WD40EFRX 4TB", "Seagate IronWolf 4TB"],
    }
    model   = rng.choice(model_pool[drive_type])
    serial  = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=12))
    firmware= f"{'F' if is_ssd else 'M'}{rng.randint(100,999)}"

    attributes = {
        "01": {"name": "Raw Read Error Rate",    "value": rng.randint(60, 100), "raw": rng.randint(0, 50)},
        "05": {"name": "Reallocated Sectors",    "value": 100 - realloc*5, "raw": realloc,   "flag": "⚠️" if realloc else "✅"},
        "09": {"name": "Power-On Hours",         "value": 100, "raw": hours},
        "0C": {"name": "Power Cycle Count",      "value": 100, "raw": rng.randint(100, 2000)},
        "B8": {"name": "End-to-End Error",       "value": rng.randint(90, 100), "raw": 0},
        "BB": {"name": "Uncorrectable Errors",   "value": rng.randint(90, 100), "raw": 0},
        "BC": {"name": "Command Timeout",        "value": rng.randint(95, 100), "raw": rng.randint(0, 10)},
        "BE": {"name": "Airflow Temperature",    "value": 100 - temp, "raw": temp},
        "C0": {"name": "Unsafe Shutdowns",       "value": 100, "raw": rng.randint(0, 50)},
        "C2": {"name": "Temperature Celsius",    "value": 100 - temp, "raw": temp},
        "C5": {"name": "Pending Sectors",        "value": 100 - pending*10, "raw": pending, "flag": "⚠️" if pending else "✅"},
        "C6": {"name": "Uncorrectable Sectors",  "value": 100, "raw": 0},
        "C7": {"name": "CRC Error Count",        "value": rng.randint(90, 100), "raw": rng.randint(0, 5)},
        "F0": {"name": "Head Flying Hours",      "value": 100, "raw": hours} if not is_ssd
              else {"name": "Total Writes",      "value": 100, "raw": rng.randint(1, 50)},  # TB written
    }
    if is_ssd and wear is not None:
        attributes["E1"] = {"name": "Load Cycle Count",  "value": 100, "raw": rng.randint(0, 5000)}
        attributes["E8"] = {"name": "SSD Wear Leveling", "value": wear, "raw": 100 - wear, "flag": "⚠️" if wear < 70 else "✅"}
        attributes["F1"] = {"name": "Total LBAs Written", "value": 100, "raw": rng.randint(100, 20000)}

    return {
        "source":          "simulated",
        "drive_path":      drive_path,
        "model":           model,
        "serial":          serial,
        "firmware":        firmware,
        "drive_type":      drive_type,
        "interface":       "NVMe" if "NVMe" in model else ("SATA III" if is_ssd else "SATA III"),
        "capacity_gb":     rng.choice([256, 500, 512, 1000, 2000, 4000]),
        "health_pct":      health,
        "health_label":    _health_label(health),
        "risk_level":      _risk_label(health),
        "temperature":     temp,
        "power_on_hours":  hours,
        "wear_level":      wear,
        "reallocated_sectors": realloc,
        "pending_sectors":     pending,
        "attributes":      attributes,
        "test_passed":     health > 70,
    }


def _wmi_smart(drive_path: str = "C:") -> dict[str, Any] | None:
    """Try to get basic drive info via WMI (no admin needed)."""
    if not _HAS_WMI:
        return None
    try:
        disks = _WMI.Win32_DiskDrive()
        for disk in disks:
            base = {
                "source":        "wmi",
                "drive_path":    drive_path,
                "model":         disk.Model or "Unknown",
                "serial":        (disk.SerialNumber or "").strip(),
                "firmware":      disk.FirmwareRevision or "",
                "drive_type":    "SSD" if any(k in (disk.Model or "").upper() for k in ("SSD","NVME","M.2")) else "HDD",
                "interface":     disk.InterfaceType or "SATA",
                "capacity_gb":   round(int(disk.Size or 0) / 1e9, 1) if disk.Size else 0,
            }
            # Fill missing SMART with simulated values
            sim = _simulated_smart(drive_path)
            return {**sim, **base, "source": "wmi+simulated"}
    except Exception:
        pass
    return None


import concurrent.futures

def get_smart_data(drive_path: str = "C:") -> dict[str, Any]:
    """Public interface: returns SMART data from best available source with timeout protection."""
    def _run_queries():
        # Try WMI first
        wmi_data = _wmi_smart(drive_path)
        if wmi_data:
            return wmi_data
        
        # Try pySMART
        if _HAS_SMART:
            try:
                dl = _DeviceList()
                for dev in dl.devices:
                    if dev and dev.name:
                        attrs = {}
                        for attr in (dev.attributes or []):
                            if attr:
                                attrs[attr.num] = {
                                    "name":  attr.name,
                                    "value": attr.value,
                                    "raw":   attr.raw,
                                }
                        health = 100 if dev.assessment == "PASS" else 50
                        return {
                            "source":        "pysmart",
                            "drive_path":    drive_path,
                            "model":         dev.model or "Unknown",
                            "serial":        dev.serial or "",
                            "firmware":      dev.firmware or "",
                            "drive_type":    "SSD" if dev.is_ssd else "HDD",
                            "interface":     dev.interface or "SATA",
                            "capacity_gb":   dev.capacity or 0,
                            "health_pct":    health,
                            "health_label":  _health_label(health),
                            "risk_level":    _risk_label(health),
                            "temperature":   dev.temperature or 35,
                            "power_on_hours": getattr(dev, "power_on", 0),
                            "attributes":    attrs,
                            "test_passed":   dev.assessment == "PASS",
                        }
            except Exception:
                pass
        return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_queries)
            result = future.result(timeout=5.0)
            if result:
                return result
    except Exception:
        pass

    # Final fallback — simulated
    return _simulated_smart(drive_path)




def get_all_drives_smart() -> list[dict[str, Any]]:
    """Return SMART data for all detected drives."""
    try:
        import psutil
        drives = [p.device for p in psutil.disk_partitions(all=False)]
    except Exception:
        drives = ["C:"]
    return [get_smart_data(d) for d in drives]
