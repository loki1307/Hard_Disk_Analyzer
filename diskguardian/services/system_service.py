# -*- coding: utf-8 -*-
"""diskguardian/services/system_service.py
Real-time system metrics via psutil with graceful fallbacks.
"""

import time
import platform
from typing import Any

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ── Persistent I/O counter baseline for speed calculation ────────────────────
_last_io   = None
_last_time = None
_last_net  = None


def _fmt_bytes(b: float) -> str:
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def get_cpu_info() -> dict[str, Any]:
    """Return CPU usage, frequency, core/thread count, temperature."""
    if not _PSUTIL:
        return {"percent": 0, "cores": 4, "threads": 8, "freq_mhz": 3000, "temperature": None}

    freq = psutil.cpu_freq()
    temps = {}
    try:
        sensors = psutil.sensors_temperatures()
        for name, entries in (sensors or {}).items():
            for e in entries:
                if e.current > 0:
                    temps[name] = round(e.current, 1)
                    break
    except (AttributeError, NotImplementedError):
        pass

    temp = next(iter(temps.values()), None)

    return {
        "percent":      psutil.cpu_percent(interval=None),
        "per_core":     psutil.cpu_percent(percpu=True),
        "cores":        psutil.cpu_count(logical=False) or 1,
        "threads":      psutil.cpu_count(logical=True)  or 1,
        "freq_mhz":     round(freq.current) if freq else 0,
        "freq_max_mhz": round(freq.max)     if freq else 0,
        "temperature":  temp,
        "name":         platform.processor() or "Unknown CPU",
    }


def get_ram_info() -> dict[str, Any]:
    """Return RAM usage statistics."""
    if not _PSUTIL:
        return {"total_gb": 8, "used_gb": 4, "free_gb": 4, "percent": 50}

    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "total_gb":   round(vm.total   / 1e9, 2),
        "used_gb":    round(vm.used    / 1e9, 2),
        "free_gb":    round(vm.available / 1e9, 2),
        "percent":    vm.percent,
        "swap_gb":    round(sw.total / 1e9, 2),
        "swap_used":  round(sw.used  / 1e9, 2),
        "swap_pct":   sw.percent,
    }


def get_disk_list() -> list[dict[str, Any]]:
    """Return all detected drives with usage stats."""
    if not _PSUTIL:
        return [{
            "device": "C:", "mountpoint": "C:\\", "fstype": "NTFS",
            "total_gb": 512, "used_gb": 256, "free_gb": 256,
            "percent": 50, "drive_type": "SSD",
        }]

    drives = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue

        # Detect drive type (best-effort on Windows via path)
        dtype = "HDD"
        try:
            import ctypes
            drive_type_num = ctypes.windll.kernel32.GetDriveTypeW(part.device)
            if drive_type_num == 2:
                dtype = "Removable"
            elif drive_type_num == 5:
                dtype = "CD-ROM"
            elif drive_type_num == 4:
                dtype = "Network"
            else:
                # Try WMI to distinguish SSD vs HDD
                try:
                    import wmi as _wmi
                    w = _wmi.WMI()
                    for disk in w.Win32_DiskDrive():
                        model = (disk.Model or "").upper()
                        if any(k in model for k in ("SSD", "NVME", "M.2", "SOLID")):
                            dtype = "SSD"
                            break
                except Exception:
                    pass
        except Exception:
            pass

        # Normalise device path: remove trailing backslash for consistency
        dev = part.device.rstrip("\\")

        drives.append({
            "device":     dev,
            "mountpoint": part.mountpoint,
            "fstype":     part.fstype or "Unknown",
            "total_gb":   round(usage.total / 1e9, 2),
            "used_gb":    round(usage.used  / 1e9, 2),
            "free_gb":    round(usage.free  / 1e9, 2),
            "percent":    usage.percent,
            "drive_type": dtype,
        })
    return drives


def get_disk_io_speeds() -> dict[str, float]:
    """Return current disk read/write speeds in MB/s."""
    global _last_io, _last_time
    if not _PSUTIL:
        return {"read_mbps": 0.0, "write_mbps": 0.0}

    now = time.monotonic()
    io  = psutil.disk_io_counters()

    if _last_io is None or _last_time is None:
        _last_io   = io
        _last_time = now
        return {"read_mbps": 0.0, "write_mbps": 0.0, "read_iops": 0, "write_iops": 0}

    dt = now - _last_time or 0.001
    read_mbps  = (io.read_bytes  - _last_io.read_bytes)  / dt / 1e6
    write_mbps = (io.write_bytes - _last_io.write_bytes) / dt / 1e6
    
    read_iops = (io.read_count - _last_io.read_count) / dt
    write_iops = (io.write_count - _last_io.write_count) / dt

    _last_io   = io
    _last_time = now
    return {
        "read_mbps": round(read_mbps, 2), 
        "write_mbps": round(write_mbps, 2),
        "read_iops": round(read_iops),
        "write_iops": round(write_iops)
    }


def get_network_info() -> dict[str, float]:
    """Return current network sent/received MB/s."""
    global _last_net
    if not _PSUTIL:
        return {"sent_mbps": 0.0, "recv_mbps": 0.0}

    now = time.monotonic()
    net = psutil.net_io_counters()

    if _last_net is None:
        _last_net = (net, now)
        return {"sent_mbps": 0.0, "recv_mbps": 0.0}

    prev, prev_time = _last_net
    dt = now - prev_time or 0.001
    sent_mbps = (net.bytes_sent - prev.bytes_sent) / dt / 1e6
    recv_mbps = (net.bytes_recv - prev.bytes_recv) / dt / 1e6
    _last_net = (net, now)
    return {"sent_mbps": round(sent_mbps, 3), "recv_mbps": round(recv_mbps, 3)}


def get_full_snapshot() -> dict[str, Any]:
    """Single call returning all live metrics for dashboard polling."""
    cpu  = get_cpu_info()
    ram  = get_ram_info()
    io   = get_disk_io_speeds()
    net  = get_network_info()
    return {
        "cpu":     cpu,
        "ram":     ram,
        "disk_io": io,
        "network": net,
        "timestamp": time.time(),
    }
