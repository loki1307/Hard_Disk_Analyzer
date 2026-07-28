# -*- coding: utf-8 -*-
"""diskguardian/services/benchmark_service.py
Disk read/write benchmark using sequential and random I/O patterns.
"""

import os
import time
import tempfile
import random
import threading
from typing import Any

_running: dict[str, bool] = {}


def _seq_write(path: str, size_mb: int = 100) -> float:
    """Write `size_mb` MB sequentially, return MB/s."""
    data = b"\x00" * (1024 * 1024)  # 1 MB block
    start = time.perf_counter()
    with open(path, "wb") as f:
        for _ in range(size_mb):
            f.write(data)
        f.flush()
        os.fsync(f.fileno())
    elapsed = time.perf_counter() - start
    return round(size_mb / elapsed, 2) if elapsed > 0 else 0.0


def _seq_read(path: str) -> float:
    """Read file sequentially, return MB/s."""
    size_mb = os.path.getsize(path) / (1024 * 1024)
    start   = time.perf_counter()
    with open(path, "rb") as f:
        while f.read(1024 * 1024):
            pass
    elapsed = time.perf_counter() - start
    return round(size_mb / elapsed, 2) if elapsed > 0 else 0.0


def _rand_write(path: str, size_mb: int = 50, block_kb: int = 4) -> float:
    """Random write benchmark (4K blocks)."""
    block  = b"\x00" * (block_kb * 1024)
    total  = size_mb * 1024 // block_kb
    file_size = size_mb * 1024 * 1024
    start  = time.perf_counter()
    with open(path, "r+b") as f:
        for _ in range(min(total, 2000)):  # cap iterations
            pos = random.randint(0, max(0, file_size - block_kb * 1024))
            f.seek(pos)
            f.write(block)
    elapsed = time.perf_counter() - start
    written_mb = min(total, 2000) * block_kb / 1024
    return round(written_mb / elapsed, 2) if elapsed > 0 else 0.0


def _rand_read(path: str, block_kb: int = 4) -> float:
    """Random read benchmark (4K blocks)."""
    file_size = os.path.getsize(path)
    block_size = block_kb * 1024
    iterations = min(2000, file_size // block_size)
    start = time.perf_counter()
    with open(path, "rb") as f:
        for _ in range(iterations):
            pos = random.randint(0, max(0, file_size - block_size))
            f.seek(pos)
            f.read(block_size)
    elapsed = time.perf_counter() - start
    read_mb = iterations * block_kb / 1024
    return round(read_mb / elapsed, 2) if elapsed > 0 else 0.0


def run_benchmark(drive_path: str = "C:", size_mb: int = 100) -> dict[str, Any]:
    """
    Run sequential + random read/write benchmark on the given drive.
    Returns results dict with speeds in MB/s and an overall score.
    """
    mountpoint = drive_path.rstrip("\\") + "\\"
    try:
        tmp = tempfile.NamedTemporaryFile(
            dir=mountpoint, prefix="diskguardian_bench_",
            suffix=".tmp", delete=False
        )
        tmp_path = tmp.name
        tmp.close()
    except Exception as e:
        return {"error": str(e), "drive": drive_path}

    results: dict[str, Any] = {"drive": drive_path, "size_mb": size_mb}
    try:
        results["seq_write_mbps"] = _seq_write(tmp_path, size_mb)
        results["seq_read_mbps"]  = _seq_read(tmp_path)
        results["rand_write_mbps"] = _rand_write(tmp_path, size_mb)
        results["rand_read_mbps"]  = _rand_read(tmp_path)
    finally:
        try: os.unlink(tmp_path)
        except: pass

    # Overall performance score 0-100
    # Reference: NVMe SSD ~3000 seq read, SATA SSD ~550, HDD ~120
    ref_seq  = 550
    ref_rand = 100
    seq_score  = min(100, (results.get("seq_read_mbps",  0) / ref_seq)  * 100)
    rand_score = min(100, (results.get("rand_read_mbps", 0) / ref_rand) * 100)
    results["performance_score"] = round((seq_score * 0.6 + rand_score * 0.4), 1)

    if results["performance_score"] >= 80:   results["rating"] = "Excellent"
    elif results["performance_score"] >= 60: results["rating"] = "Good"
    elif results["performance_score"] >= 40: results["rating"] = "Average"
    else:                                     results["rating"] = "Slow"

    return results
