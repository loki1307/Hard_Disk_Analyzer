# -*- coding: utf-8 -*-
"""diskguardian/services/ai_service.py
Rule-based AI engine — no external API needed.
Calculates health scores, predicts risk, and responds to natural language.
"""

from __future__ import annotations
import re
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
#  Health Score Calculator
# ─────────────────────────────────────────────────────────────────────────────
def calculate_health_score(smart: dict, system: dict | None = None) -> dict[str, Any]:
    """
    Produces a 0-100 composite health score from SMART + system metrics.
    Returns score, grade, contributing factors, and maintenance checklist.
    """
    score = 100.0
    factors = []
    checklist = []

    # ── SMART factors ─────────────────────────────────────────────────────────
    realloc = smart.get("reallocated_sectors", 0) or 0
    pending = smart.get("pending_sectors",     0) or 0
    temp    = smart.get("temperature",         35) or 35
    hours   = smart.get("power_on_hours",       0) or 0
    wear    = smart.get("wear_level",          100) or 100
    smart_h = smart.get("health_pct",          100) or 100

    if realloc > 0:
        deduct = min(25, realloc * 8)
        score -= deduct
        factors.append({"name": "Reallocated Sectors", "impact": -deduct, "detail": f"{realloc} sector(s) remapped"})
        checklist.append("🔴 Back up your data immediately — reallocated sectors indicate physical drive damage.")

    if pending > 0:
        deduct = min(15, pending * 5)
        score -= deduct
        factors.append({"name": "Pending Sectors", "impact": -deduct, "detail": f"{pending} sector(s) waiting reallocation"})
        checklist.append("🟡 Run a full surface scan to resolve pending sectors.")

    if temp > 55:
        deduct = min(20, (temp - 55) * 3)
        score -= deduct
        factors.append({"name": "High Temperature", "impact": -deduct, "detail": f"{temp}°C — critically hot"})
        checklist.append(f"🔴 Drive temperature is {temp}°C. Improve airflow or replace thermal paste.")
    elif temp > 45:
        deduct = min(10, (temp - 45) * 2)
        score -= deduct
        factors.append({"name": "Elevated Temperature", "impact": -deduct, "detail": f"{temp}°C — above optimal"})
        checklist.append(f"🟡 Drive temperature ({temp}°C) is elevated. Check case cooling.")

    if hours > 50000:
        deduct = 15
        score -= deduct
        factors.append({"name": "Very High Drive Age", "impact": -deduct, "detail": f"{hours:,} hours"})
        checklist.append(f"🔴 Drive has {hours:,} power-on hours. Consider replacing soon.")
    elif hours > 30000:
        deduct = 8
        score -= deduct
        factors.append({"name": "High Drive Age", "impact": -deduct, "detail": f"{hours:,} hours"})
        checklist.append(f"🟡 Drive age ({hours:,} hrs) is high. Plan a replacement.")

    if wear < 20:
        deduct = 20
        score -= deduct
        factors.append({"name": "Critical SSD Wear", "impact": -deduct, "detail": f"{wear}% remaining"})
        checklist.append("🔴 SSD wear level critical. Replace drive and restore from backup.")
    elif wear < 50:
        deduct = 10
        score -= deduct
        factors.append({"name": "SSD Wear", "impact": -deduct, "detail": f"{wear}% remaining"})
        checklist.append(f"🟡 SSD wear level is {wear}%. Monitor closely and plan replacement.")

    # ── System factors ────────────────────────────────────────────────────────
    if system:
        cpu_pct = system.get("cpu", {}).get("percent", 0) or 0
        ram_pct = system.get("ram", {}).get("percent", 0) or 0

        if cpu_pct > 90:
            score -= 5
            factors.append({"name": "CPU Overload", "impact": -5, "detail": f"{cpu_pct}% usage"})
        if ram_pct > 90:
            score -= 5
            factors.append({"name": "RAM Pressure", "impact": -5, "detail": f"{ram_pct}% usage"})
            checklist.append("🟡 RAM is nearly full. Close background apps or add more RAM.")

    score = max(0.0, min(100.0, score))

    # ── Maintenance defaults ──────────────────────────────────────────────────
    if not any("TRIM" in c for c in checklist) and smart.get("drive_type") == "SSD":
        checklist.append("✅ Enable TRIM to maintain SSD performance (Settings > TRIM).")
    if not any("backup" in c.lower() for c in checklist):
        checklist.append("✅ Schedule regular backups to protect your data.")
    if hours > 0 and hours % 8760 < 720:
        checklist.append("✅ Consider running a full diagnostic — it has been approximately a year of use.")

    # ── Grade ─────────────────────────────────────────────────────────────────
    if score >= 90:   grade, color = "Excellent", "success"
    elif score >= 75: grade, color = "Good",      "info"
    elif score >= 55: grade, color = "Warning",   "warning"
    else:             grade, color = "Critical",  "danger"

    return {
        "score":     round(score, 1),
        "grade":     grade,
        "color":     color,
        "factors":   factors,
        "checklist": checklist,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Risk Prediction
# ─────────────────────────────────────────────────────────────────────────────
def predict_risk(smart: dict, scan_history: list[dict] | None = None) -> dict[str, Any]:
    """
    Predict drive failure likelihood based on SMART values + scan trend.
    Returns risk level, confidence, and explanation.
    """
    health = smart.get("health_pct",       100) or 100
    realloc = smart.get("reallocated_sectors", 0) or 0
    pending = smart.get("pending_sectors",     0) or 0
    temp    = smart.get("temperature",         35) or 35
    hours   = smart.get("power_on_hours",       0) or 0
    wear    = smart.get("wear_level",          100) or 100
    risk_score: float = 0.0  # 0-100

    risk_score += min(40, realloc * 15)
    risk_score += min(20, pending * 8)
    risk_score += max(0, temp - 45) * 3
    risk_score += max(0, hours - 30000) / 5000 * 5
    risk_score += max(0, 50 - wear) / 5

    # Trend: if last 3 scans show declining health
    if scan_history and len(scan_history) >= 2:
        recent = [s.get("health_score", 100) for s in scan_history[-3:]]
        if len(recent) >= 2 and recent[-1] < recent[0]:
            decline = recent[0] - recent[-1]
            risk_score += min(20, decline * 2)

    risk_score = min(100, risk_score)

    if risk_score < 20:   level, label, color = "low",      "Low Risk",      "success"
    elif risk_score < 45: level, label, color = "medium",   "Medium Risk",   "warning"
    elif risk_score < 70: level, label, color = "high",     "High Risk",     "danger"
    else:                 level, label, color = "critical", "Critical Risk", "danger"

    explanations = []
    if realloc:    explanations.append(f"{realloc} reallocated sector(s) — physical damage detected.")
    if pending:    explanations.append(f"{pending} pending sector(s) awaiting reallocation.")
    if temp > 45:  explanations.append(f"Temperature {temp}°C accelerates drive wear.")
    if hours > 30000: explanations.append(f"{hours:,} power-on hours indicates an aging drive.")
    if wear < 50:  explanations.append(f"SSD wear level at {wear}% — nearing end of write endurance.")
    if not explanations: explanations.append("Drive shows no significant warning signs.")

    return {
        "risk_score": round(risk_score, 1),
        "risk_level": level,
        "label":      label,
        "color":      color,
        "confidence": "Estimated — based on available SMART diagnostics",
        "explanations": explanations,
        "disclaimer": (
            "⚠️ This prediction is an estimate based on available diagnostic data. "
            "It is NOT a guarantee. Always maintain regular backups regardless of drive health."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  AI Chat Engine
# ─────────────────────────────────────────────────────────────────────────────
_TOPICS = [
    (r"health|condition|status|how (is|my) (drive|disk|ssd|hdd)",
     "health_response"),
    (r"(slow|speed|performance|benchmark|fast|read|write)",
     "performance_response"),
    (r"(temperature|hot|heat|cool|thermal)",
     "temperature_response"),
    (r"(fail|failur|dying|replace|dead|broken|bad|crash)",
     "failure_response"),
    (r"(partition|format|resize|space|storage|full|free)",
     "partition_response"),
    (r"(trim|ssd|nvm|wear|lifespan|life span|endurance)",
     "ssd_response"),
    (r"(defrag|defragment|fragment|hdd)",
     "defrag_response"),
    (r"(backup|restore|recovery|safe)",
     "backup_response"),
    (r"(firmware|update|version)",
     "firmware_response"),
    (r"(error|smart|reallocat|sector|pending|crc)",
     "smart_error_response"),
    (r"(windows 11|upgrade|os)",
     "os_upgrade_response"),
    (r"(cleanup|clean|space|free|delete|temp|large files|what is consuming)",
     "cleanup_advisor_response"),
    (r"(startup|slow boot|boot|trim|fragment)",
     "optimization_response"),
]


def _health_response(smart: dict, health: dict, q: str) -> str:
    score = health.get("score", 100)
    grade = health.get("grade", "Unknown")
    h_pct = smart.get("health_pct", 100)
    temp  = smart.get("temperature", 35)
    hours = smart.get("power_on_hours", 0)
    return (
        f"**Drive Health Summary**\n\n"
        f"Your drive is currently rated **{grade}** with a health score of **{score}/100**.\n\n"
        f"- Raw SMART health: **{h_pct}%**\n"
        f"- Current temperature: **{temp}°C**\n"
        f"- Total operating hours: **{hours:,} hrs**\n\n"
        + ("✅ Your drive is in great condition. Keep monitoring regularly." if score >= 80
           else "⚠️ Your drive shows some concerns. Review the checklist below for recommended actions.")
    )


def _performance_response(smart: dict, health: dict, q: str) -> str:
    dtype = smart.get("drive_type", "HDD")
    score = health.get("score", 100)
    return (
        f"**Drive Performance Analysis**\n\n"
        f"Your drive is a **{dtype}**. "
        + (f"SSDs deliver superior speed compared to HDDs. "
           f"If performance feels slow, consider:\n"
           f"- Running the **Speed Benchmark** tool in the sidebar\n"
           f"- Checking if TRIM is enabled (SSD optimisation)\n"
           f"- Ensuring the drive is not over **85% full** (performance drops significantly past this point)"
           if dtype == "SSD" else
           f"HDDs can slow down due to fragmentation. "
           f"Consider running a defragmentation scan.\n"
           f"For a major speed upgrade, replacing your HDD with an SSD is the single best improvement you can make.")
        + f"\n\nCurrent health score: **{score}/100**."
    )


def _temperature_response(smart: dict, health: dict, q: str) -> str:
    temp = smart.get("temperature", 35)
    if temp >= 55:
        status = f"🔴 **Critical** ({temp}°C) — drives above 55°C have significantly higher failure rates."
        advice = "Immediately check case airflow. Consider adding a cooling fan or reducing drive load."
    elif temp >= 45:
        status = f"🟡 **Elevated** ({temp}°C) — optimal range is 25–45°C."
        advice = "Check that cables are not blocking airflow. Clean dust from case vents."
    else:
        status = f"✅ **Normal** ({temp}°C) — within optimal range."
        advice = "Temperature is healthy. No action required."
    return f"**Temperature Analysis**\n\nCurrent drive temperature: {status}\n\n{advice}"


def _failure_response(smart: dict, health: dict, q: str) -> str:
    risk = predict_risk(smart)
    level = risk["risk_level"]
    score = health.get("score", 100)
    expl  = "\n".join(f"- {e}" for e in risk["explanations"])
    return (
        f"**Failure Risk Assessment**\n\n"
        f"Risk Level: **{risk['label']}** (score: {risk['risk_score']}/100)\n\n"
        f"Key findings:\n{expl}\n\n"
        f"_{risk['disclaimer']}_"
    )


def _partition_response(smart: dict, health: dict, q: str) -> str:
    return (
        "**Partition Safety Advisor**\n\n"
        "Before resizing or creating partitions:\n"
        "1. 📦 **Create a full backup first** — partition operations can be destructive\n"
        "2. 🔋 Ensure your laptop is plugged in or your PC has UPS\n"
        "3. 💾 Keep at least **15% free space** on system partitions for best performance\n"
        "4. 🔍 Run a disk error check (`chkdsk /f`) before resizing\n\n"
        "Use Windows Disk Management or a tool like MiniTool Partition Wizard for safe resizing."
    )


def _ssd_response(smart: dict, health: dict, q: str) -> str:
    wear = smart.get("wear_level", 100)
    return (
        f"**SSD Health & Lifespan Tips**\n\n"
        f"Current SSD wear level: **{wear}%** remaining\n\n"
        f"To maximise SSD lifespan:\n"
        f"- ✅ **Enable TRIM** — keeps SSD performance optimal\n"
        f"- 🚫 **Avoid filling above 85%** — SSDs slow down significantly when nearly full\n"
        f"- 🌡️ **Keep temperature below 45°C**\n"
        f"- 💾 Reduce unnecessary writes (avoid pagefile on SSD if possible)\n"
        f"- 🔋 Avoid sudden power cuts (use UPS or laptop battery)\n\n"
        + ("⚠️ Wear level below 50% — begin planning a replacement." if wear < 50
           else "✅ SSD wear level is healthy.")
    )


def _defrag_response(smart: dict, health: dict, q: str) -> str:
    dtype = smart.get("drive_type", "HDD")
    if dtype == "SSD":
        return (
            "**Important: Do NOT defragment an SSD!**\n\n"
            "Defragmentation causes unnecessary write cycles on SSDs, reducing their lifespan. "
            "Windows automatically runs **TRIM** on SSDs which performs the equivalent optimisation.\n\n"
            "✅ TRIM is the correct maintenance operation for SSDs."
        )
    return (
        "**HDD Defragmentation**\n\n"
        "Defragmentation is beneficial for HDDs as it reorganises file fragments, reducing seek time.\n\n"
        "- Windows runs automatic defragmentation on a schedule\n"
        "- Manual defrag: Start → Defragment and Optimise Drives\n"
        "- Best time: after freeing up significant storage space\n"
        "- Avoid defragging when drive is above 95% full"
    )


def _backup_response(smart: dict, health: dict, q: str) -> str:
    score = health.get("score", 100)
    urgency = "🔴 **Urgently recommended**" if score < 60 else ("🟡 **Recommended soon**" if score < 80 else "✅ **Good practice**")
    return (
        f"**Backup Recommendation**\n\n"
        f"{urgency} — Health score: {score}/100\n\n"
        f"Backup options:\n"
        f"- **Windows Backup** (built-in) — File History + System Image\n"
        f"- **Cloud**: Google Drive, OneDrive, Backblaze\n"
        f"- **External Drive**: full image backup with Macrium Reflect (free)\n\n"
        f"🔑 Follow the **3-2-1 rule**: 3 copies, 2 media types, 1 off-site."
    )


def _firmware_response(smart: dict, health: dict, q: str) -> str:
    fw = smart.get("firmware", "Unknown")
    model = smart.get("model", "your drive")
    return (
        f"**Firmware Information**\n\n"
        f"Current firmware: **{fw}** for {model}\n\n"
        f"To check for firmware updates:\n"
        f"1. Visit your manufacturer's website (Samsung, Seagate, WD, Crucial)\n"
        f"2. Search for your model: **{model}**\n"
        f"3. Download and run their official firmware update tool\n\n"
        f"⚠️ Always back up before applying a firmware update."
    )


def _smart_error_response(smart: dict, health: dict, q: str) -> str:
    realloc = smart.get("reallocated_sectors", 0) or 0
    pending = smart.get("pending_sectors", 0) or 0
    if realloc or pending:
        return (
            f"**SMART Error Analysis**\n\n"
            f"- Reallocated sectors: **{realloc}** {'⚠️' if realloc else '✅'}\n"
            f"- Pending sectors: **{pending}** {'⚠️' if pending else '✅'}\n\n"
            + ("🔴 Non-zero reallocated or pending sectors indicate **physical drive damage**. "
               "Back up your data immediately and plan drive replacement." if realloc or pending
               else "✅ No SMART errors detected.")
        )
    return (
        "All monitored attributes are within normal thresholds. "
        "Continue monitoring regularly for early detection of issues."
    )


def _os_upgrade_response(smart: dict, health: dict, q: str, **kwargs) -> str:
    sys = kwargs.get("system")
    if not sys:
        return "I need more system data to confirm Windows 11 compatibility. Try running a full scan first."
    cpu = sys.get("cpu", {})
    ram = sys.get("ram", {})
    
    # Very basic Windows 11 check heuristics based on psutil data
    ram_ok = ram.get("total_gb", 0) >= 4.0
    cpu_cores_ok = cpu.get("cores", 0) >= 2
    cpu_freq_ok = cpu.get("freq_max_mhz", 0) >= 1000
    
    status = "✅ Your system appears to meet the basic hardware requirements for Windows 11 (≥4GB RAM, ≥2 Cores, ≥1GHz)." if (ram_ok and cpu_cores_ok and cpu_freq_ok) else "❌ Your system may NOT meet the Windows 11 minimum requirements."
    
    return (
        f"**Windows 11 Upgrade Check**\n\n"
        f"{status}\n\n"
        f"**Detected Specs:**\n"
        f"- RAM: {ram.get('total_gb', 0)} GB (Requires 4 GB)\n"
        f"- CPU: {cpu.get('name', 'Unknown')} with {cpu.get('cores', 0)} Cores (Requires 2 Cores)\n\n"
        f"⚠️ Note: Microsoft also requires a TPM 2.0 module and Secure Boot, which I cannot verify without administrator privileges. Download the official 'PC Health Check' app from Microsoft to be 100% sure."
    )


def _cleanup_advisor_response(smart: dict, health: dict, q: str, **kwargs) -> str:
    cln = kwargs.get("cleanup")
    if not cln:
        return "I need to analyze your storage first. Please visit the **Cleanup Advisor** tab to scan your drives."
        
    total_mb = cln.get('total_reclaimable_bytes', 0) / (1024*1024)
    return (
        f"**Storage Cleanup Analysis**\n\n"
        f"Based on your recent scan, I found **{total_mb:.1f} MB** of easily reclaimable space.\n\n"
        f"I recommend:\n"
        f"1. Checking the Temp folder (Current size: {cln.get('temp_files', {}).get('size_bytes', 0)/(1024*1024):.1f} MB)\n"
        f"2. Emptying the Recycle Bin (Current size: {cln.get('recycle_bin', {}).get('size_bytes', 0)/(1024*1024):.1f} MB)\n"
        f"3. Reviewing your Downloads folder\n\n"
        f"Go to the **Cleanup Advisor** tab to view your largest files in detail."
    )


def _optimization_response(smart: dict, health: dict, q: str, **kwargs) -> str:
    opt = kwargs.get("opt")
    if not opt:
        return "Please run a scan in the **System Optimization Center** first."
        
    startup_cnt = len(opt.get("startup_programs", []))
    trim = opt.get("trim", {}).get("enabled", False)
    
    return (
        f"**System Optimization Status**\n\n"
        f"Boot Performance: You have **{startup_cnt}** programs starting automatically with Windows. "
        + ("Consider disabling some to speed up boot times." if startup_cnt > 5 else "Your boot configuration looks lean.")
        + f"\n\nSSD TRIM Status: **{'Enabled ✅' if trim else 'Disabled or Unknown ⚠️'}**\n"
        f"If you have an SSD, TRIM is critical for maintaining performance and longevity. "
        f"Visit the **Optimization** tab for a detailed breakdown."
    )


def _default_response(smart: dict, health: dict, q: str) -> str:
    return (
        "I'm your AI Disk Guardian assistant. I can help you with:\n\n"
        "- 🔍 **Drive health** — ask *'How is my drive health?'*\n"
        "- 🌡️ **Temperature** — ask *'Is my drive too hot?'*\n"
        "- ⚡ **Performance** — ask *'Why is my drive slow?'*\n"
        "- ⚠️ **Failure risk** — ask *'Is my drive going to fail?'*\n"
        "- 💾 **Backup advice** — ask *'Should I back up?'*\n"
        "- 🔧 **Maintenance** — ask *'How do I improve SSD lifespan?'*\n\n"
        "Try asking me any of those questions!"
    )


_HANDLERS = {
    "health_response":     _health_response,
    "performance_response": _performance_response,
    "temperature_response": _temperature_response,
    "failure_response":    _failure_response,
    "partition_response":  _partition_response,
    "ssd_response":        _ssd_response,
    "defrag_response":     _defrag_response,
    "backup_response":     _backup_response,
    "firmware_response":   _firmware_response,
    "smart_error_response": _smart_error_response,
    "os_upgrade_response": _os_upgrade_response,
    "cleanup_advisor_response": _cleanup_advisor_response,
    "optimization_response": _optimization_response,
}


def ai_chat(question: str, smart: dict, health: dict | None = None, **kwargs) -> str:
    """
    Main entry point for AI chat. Matches question to topic, returns markdown response.
    """
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        return "AI Assistant is currently unavailable. Please configure OPENAI_API_KEY."

    if health is None:
        health = calculate_health_score(smart)

    q = question.lower().strip()

    for pattern, handler_name in _TOPICS:
        if re.search(pattern, q):
            handler = _HANDLERS.get(handler_name, _default_response)
            # Pass kwargs (system, cleanup, opt) so handlers can use them
            if handler_name in ["os_upgrade_response", "cleanup_advisor_response", "optimization_response"]:
                return handler(smart, health, q, **kwargs)
            else:
                return handler(smart, health, q)

    return _default_response(smart, health, q)


def generate_maintenance_checklist(smart: dict, system: dict | None = None) -> list[str]:
    """Generate personalised maintenance checklist after a scan."""
    health = calculate_health_score(smart, system)
    return health.get("checklist", [])
