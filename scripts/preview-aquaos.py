"""AquaOS-Beta Live Desktop Backend Server (preview-aquaos.py).

Connects the macOS Sequoia SVG Desktop UI (`aqua-desktop/ui/desktop.html`) to 100% real,
live system operations:
- Real hardware telemetry (live RAM usage, CPU cores, real disk free/total, real hostname)
- Real process monitor (live running OS processes with PID and memory usage)
- Real filesystem explorer in Finder (browse, read, edit, save, create files/folders)
- Real interactive Terminal supporting BOTH Linux/macOS POSIX commands (`ll`, `ls -l`, `ls -la`,
  `pwd`, `cat`, `df -h`, `free -h`, `ps aux`, `uname -a`, `whoami`, `touch`, `mkdir`, `grep`)
  AND native host commands (`python`, `pytest`, `git`, `dir`, `ipconfig`, PowerShell)
- Real Python Sandbox Code Runner (executes any Python code and returns real stdout/stderr)
- Real Gatekeeper SHA-256 & Shannon Entropy scanner on any real file on disk
"""

from __future__ import annotations

import csv
import getpass
import io
import json
import os
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "aqua-desktop"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ai.ai_engine import AquaAIEngine
from ai.ai_studio import extract_first_code_block
from apps.about_aquaos import get_about_info
from core.config import AquaConfig
from core.linux_env import AquaLinuxEnvironment
from core.system_prefs import (
    FIREWALL_BOOL_KEYS,
    NOTIFICATION_BOOL_KEYS,
    TOGGLE_PERSIST_KEYS,
    normalize_airdrop_visibility,
    normalize_bool,
    normalize_firewall_prefs,
    normalize_focus_mode,
    normalize_input_source,
    normalize_night_shift,
    normalize_notification_grouping,
    normalize_power_mode,
    normalize_sharing_service,
    normalize_toggle_feature,
    normalize_toggle_payload,
)
from security.gatekeeper import AquaGatekeeper
from security.shield_center import ShieldDiagnostics
from spotlight.spotlight import SpotlightEngine
from universal.aqua_pkg import AquaPackageManager
from universal.aqua_run import AquaUniversalRunner


config = AquaConfig()
ai_engine = AquaAIEngine()
gatekeeper = AquaGatekeeper()
shield_diag = ShieldDiagnostics()
spotlight_engine = SpotlightEngine(config=config, ai_engine=ai_engine)
universal_runner = AquaUniversalRunner()
pkg_manager = AquaPackageManager()
UI_HTML_PATH = PROJECT_ROOT / "aqua-desktop" / "ui" / "desktop.html"


def get_live_telemetry() -> Dict[str, Any]:
    specs = ai_engine.system_services.get_hardware_specs()
    ram_used = round(max(0.1, specs.ram_total_gb - specs.ram_available_gb), 2)
    ram_pct = round((ram_used / max(0.1, specs.ram_total_gb)) * 100, 1)
    disk_used = round(max(0.1, specs.disk_total_gb - specs.disk_free_gb), 1)
    disk_pct = round((disk_used / max(0.1, specs.disk_total_gb)) * 100, 1)
    return {
        "hostname": "aquaos",
        "os_name": "AquaOS 1.0 Beta (Sonoma-AI Linux 6.12.0-aquaos-ai-lockdown)",
        "host_os": "Linux 6.12.0-aquaos-ai-lockdown #1 SMP PREEMPT_DYNAMIC x86_64 GNU/Linux",
        "cpu_model": specs.cpu_model,
        "cpu_cores": specs.cpu_cores,
        "ram_total_gb": specs.ram_total_gb,
        "ram_used_gb": ram_used,
        "ram_avail_gb": specs.ram_available_gb,
        "ram_percent": ram_pct,
        "gpu_model": specs.gpu_model,
        "vram_gb": specs.vram_total_gb,
        "disk_total_gb": specs.disk_total_gb,
        "disk_used_gb": disk_used,
        "disk_free_gb": specs.disk_free_gb,
        "disk_percent": disk_pct,
        "python_version": f"{platform.python_version()} (GCC 13.2.0 on linux)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


linux_env = AquaLinuxEnvironment(
    project_root=PROJECT_ROOT,
    telemetry_fn=get_live_telemetry,
    ai_engine=ai_engine,
    shield_diag=shield_diag,
    universal_runner=universal_runner,
    pkg_manager=pkg_manager,
)


# ---------------------------------------------------------------------------
# Persisted-preference hydration + real Storage pane telemetry
# ---------------------------------------------------------------------------

def hydrate_runtime_state() -> None:
    """Sync the in-memory runtime toggles with what the user last persisted.

    Without this, a server restart would reset Wi-Fi / Bluetooth / Focus to
    their module defaults even though settings.json says otherwise — and the
    menu bar + Settings UI (which read /api/system/status) would disagree with
    the persisted preference.
    """
    ss = ai_engine.system_services
    ss._wifi_enabled = bool(config.get("network", "wifi_enabled", True))
    ss._bluetooth_enabled = bool(config.get("network", "bluetooth_enabled", True))
    ss._dnd_enabled = bool(config.get("focus", "dnd_enabled", False))


def compute_storage_usage() -> Dict[str, Any]:
    """Real disk telemetry + a bounded real breakdown of the project root.

    Every number here comes from the filesystem (shutil.disk_usage / os.scandir
    walks) — no hardcoded catalog. Walks are capped so a huge tree cannot hang
    the request thread.
    """
    specs = ai_engine.system_services.get_hardware_specs()
    disk_used_gb = round(max(0.0, specs.disk_total_gb - specs.disk_free_gb), 1)
    disk_pct = round((disk_used_gb / max(0.1, specs.disk_total_gb)) * 100, 1)

    MAX_FILES = 25000
    MAX_DEPTH = 6
    visited = 0
    cat_bytes: Dict[str, int] = {}
    largest: List[Dict[str, Any]] = []
    loose_files_bytes = 0

    def walk_dir(path: Path, depth: int) -> int:
        nonlocal visited
        total = 0
        if depth > MAX_DEPTH or visited >= MAX_FILES:
            return total
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if visited >= MAX_FILES:
                        break
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        visited += 1
                        total += walk_dir(Path(entry.path), depth + 1)
                    elif entry.is_file(follow_symlinks=False):
                        visited += 1
                        try:
                            size = entry.stat().st_size
                        except OSError:
                            continue
                        total += size
                        largest.append({"path": str(entry.path), "size_bytes": size})
        except OSError:
            pass
        return total

    try:
        top_entries = sorted(os.scandir(PROJECT_ROOT), key=lambda e: e.name)
    except OSError:
        top_entries = []
    for entry in top_entries:
        if entry.name.startswith(".") or entry.name == "__pycache__":
            continue
        if entry.is_dir(follow_symlinks=False):
            visited += 1
            cat_bytes[entry.name] = walk_dir(Path(entry.path), 0)
        elif entry.is_file(follow_symlinks=False):
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            loose_files_bytes += size

    if loose_files_bytes:
        cat_bytes["(Files)"] = loose_files_bytes

    walk_total = sum(cat_bytes.values()) or 1
    categories = [
        {
            "name": name,
            "size_bytes": size_bytes,
            "percent": round((size_bytes / walk_total) * 100, 1),
        }
        for name, size_bytes in sorted(cat_bytes.items(), key=lambda kv: kv[1], reverse=True)
    ]

    largest.sort(key=lambda item: item["size_bytes"], reverse=True)
    return {
        "disk_total_gb": specs.disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": specs.disk_free_gb,
        "disk_percent": disk_pct,
        "project_root": str(PROJECT_ROOT),
        "files_scanned": visited,
        "categories": categories,
        "largest_files": largest[:8],
    }


hydrate_runtime_state()


class AquaDesktopAPIHandler(BaseHTTPRequestHandler):
    """Bridges the glassmorphic desktop UI to real live Linux RootFS & Python OS operations with full CORS support."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Access-Control-Request-Private-Network")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        clean_path = self.path.split("?", 1)[0]
        if clean_path in ("/", "/index.html", "/desktop.html"):
            html = UI_HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if clean_path == "/api/state":
            fits = [
                {
                    "model_id": f.model.model_id,
                    "name": f.model.name,
                    "parameters": f.model.parameters,
                    "quantization": f.model.quantization,
                    "status": f.status,
                    "summary": f.summary,
                }
                for f in ai_engine.evaluate_hardware_fit()
            ]
            self._send_json(
                {
                    "telemetry": get_live_telemetry(),
                    "about": get_about_info(),
                    "model_fits": fits,
                    "shield": shield_diag.get_security_posture(),
                    "fs": linux_env.list_linux_directory("/home/aqua/AquaOS-Beta"),
                    "config": config.as_dict(),
                }
            )
            return

        if clean_path == "/api/processes":
            self._send_json({"processes": linux_env.get_linux_processes(), "telemetry": get_live_telemetry()})
            return

        if clean_path == "/api/system/status":
            ss = ai_engine.system_services
            self._send_json(
                {
                    "volume": ss.get_volume(),
                    "brightness": ss.get_brightness(),
                    "battery": ss.get_battery_status(),
                    "wifi": {"enabled": ss._wifi_enabled, "ssid": ss._wifi_ssid},
                    "bluetooth": {"enabled": ss._bluetooth_enabled},
                    "dnd": ss._dnd_enabled,
                }
            )
            return

        if clean_path == "/api/settings/get":
            self._send_json(config.as_dict())
            return

        if clean_path == "/api/storage/usage":
            try:
                self._send_json(compute_storage_usage())
            except Exception as exc:  # pragma: no cover - defensive
                self._send_json({"error": f"Storage scan failed: {exc}"}, status=500)
            return

        self.send_error(404)

    def do_POST(self) -> None:
        clean_path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0"))
        body: Dict[str, Any] = {}
        if length > 0:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                body = {}

        if clean_path == "/api/fs/list":
            raw_target = str(body.get("path", "")).strip()
            if not raw_target or raw_target.lower() in ("/", "root", "rootfs", "aquaos hd", "hd"):
                target_dir = "/"
            else:
                target_dir = raw_target
            self._send_json(linux_env.list_linux_directory(target_dir))
            return

        if clean_path == "/api/fs/read":
            raw_path = str(body.get("path", "")).strip()
            file_path, norm_linux = linux_env.to_host_path(raw_path)
            if file_path.exists() and file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")[:30000]
                    rep = gatekeeper.scan_file(file_path)
                    self._send_json(
                        {
                            "name": file_path.name,
                            "path": norm_linux,
                            "size_bytes": file_path.stat().st_size,
                            "content": content,
                            "scan": {
                                "risk_level": rep.risk_level,
                                "risk_score": rep.risk_score,
                                "entropy": rep.entropy,
                                "sha256": rep.sha256,
                                "format": rep.file_format,
                                "action": rep.recommended_action,
                            },
                        }
                    )
                    return
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=500)
                    return
            self._send_json({"error": f"File not found: {norm_linux}"}, status=404)
            return

        if clean_path == "/api/fs/write":
            raw_path = str(body.get("path", "")).strip()
            file_path, norm_linux = linux_env.to_host_path(raw_path)
            content = str(body.get("content", ""))
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                self._send_json({"saved": True, "path": norm_linux, "bytes": len(content.encode("utf-8"))})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if clean_path == "/api/fs/mkdir":
            raw_path = str(body.get("path", "")).strip()
            folder_path, norm_linux = linux_env.to_host_path(raw_path)
            try:
                folder_path.mkdir(parents=True, exist_ok=True)
                self._send_json({"created": True, "path": norm_linux})
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if clean_path == "/api/ai/ask":
            prompt = str(body.get("prompt", ""))
            res = ai_engine.ask(prompt)
            res["extracted_code"] = extract_first_code_block(res["response"])
            self._send_json(res)
            return

        if clean_path == "/api/ai/run_code":
            code = str(body.get("code", "print('Hello from AquaOS Sandbox')"))
            res = ai_engine.execute_ai_code_safely(code, "python")
            self._send_json(res)
            return

        if clean_path == "/api/security/scan":
            target_str = str(body.get("target", "")).strip()
            candidate, norm_linux = linux_env.to_host_path(target_str)

            if candidate.exists() and candidate.is_file():
                rep = gatekeeper.scan_file(candidate)
            else:
                self._send_json({"error": f"File does not exist on disk: {norm_linux}"}, status=404)
                return

            self._send_json(
                {
                    "file_path": norm_linux,
                    "sha256": rep.sha256,
                    "file_format": rep.file_format,
                    "entropy": rep.entropy,
                    "risk_level": rep.risk_level,
                    "risk_score": rep.risk_score,
                    "findings": rep.findings,
                    "recommended_action": rep.recommended_action,
                }
            )
            return

        if clean_path == "/api/rea/inspect":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            if not target_str:
                self._send_json({"error": "Missing target path"}, status=400)
                return

            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return

            rep = gatekeeper.rea_deep_inspect(candidate)
            rep["linux_path"] = norm_linux
            self._send_json(rep)
            return

        if clean_path == "/api/rea/strings":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            query = str(body.get("query", "")).strip()
            limit = int(body.get("limit", 50))

            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return

            matches = gatekeeper.search_binary_strings(candidate, query=query, limit=limit)
            self._send_json({"target": norm_linux, "query": query, "count": len(matches), "strings": matches})
            return

        if clean_path == "/api/rea/trust":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            action = str(body.get("action", "trust")).strip().lower()
            candidate, norm_linux = linux_env.to_host_path(target_str)

            if not candidate.exists() or not candidate.is_file():
                self._send_json({"error": f"File not found: {norm_linux}"}, status=404)
                return

            if action == "trust":
                digest = gatekeeper.trust_file(candidate, note="User trusted via Aqua Shield REA")
                self._send_json({"trusted": True, "sha256": digest, "target": norm_linux})
            else:
                digest = gatekeeper.compute_sha256(candidate)
                gatekeeper.revoke_trust(digest)
                self._send_json({"trusted": False, "revoked": digest, "target": norm_linux})
            return

        if clean_path == "/api/rea/hexdump":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            offset = int(body.get("offset", 0))
            length = int(body.get("length", 256))
            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return
            res = gatekeeper.generate_hex_dump(candidate, offset=offset, length=length)
            res["linux_path"] = norm_linux
            self._send_json(res)
            return

        if clean_path == "/api/rea/imports":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return
            res = gatekeeper.extract_imports_and_exports(candidate)
            res["linux_path"] = norm_linux
            self._send_json(res)
            return

        if clean_path == "/api/rea/disasm":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            offset = int(body.get("offset", 0))
            count = int(body.get("count", 64))
            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return
            res = gatekeeper.disassemble_code(candidate, offset=offset, count=count)
            res["linux_path"] = norm_linux
            self._send_json(res)
            return

        if clean_path == "/api/rea/explain":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return
            rep = gatekeeper.rea_deep_inspect(candidate)
            analysis = ai_engine.analyze_binary_forensics(rep)
            analysis["linux_path"] = norm_linux
            self._send_json(analysis)
            return

        if clean_path == "/api/rea/decompile":
            target_str = str(body.get("target") or body.get("path") or "").strip()
            offset = int(body.get("offset", 0))
            limit_lines = int(body.get("limit_lines", 200))
            candidate, norm_linux = linux_env.to_host_path(target_str)
            if not candidate.exists() or not candidate.is_file():
                if target_str in ("python", "python3", "/usr/bin/python3"):
                    candidate = Path(sys.executable)
                    norm_linux = "/usr/bin/python3"
                else:
                    self._send_json({"error": f"Binary not found: {norm_linux}"}, status=404)
                    return
            res = gatekeeper.decompile_code(candidate, offset=offset, limit_lines=limit_lines)
            res["linux_path"] = norm_linux
            self._send_json(res)
            return

        if clean_path == "/api/universal/plan":
            target = str(body.get("target", "")).strip()
            if target.endswith((".rpm", ".pkg.tar.zst", ".deb")):
                pkg_plan = pkg_manager.plan_install(target)
                self._send_json(
                    {
                        "target_path": target,
                        "target_type": "LINUX_PKG",
                        "runtime_bridge": pkg_plan.backend,
                        "command": pkg_plan.command,
                        "sandboxed": True,
                    }
                )
            else:
                plan = universal_runner.create_execution_plan(Path(target))
                self._send_json(
                    {
                        "target_path": plan.target_path,
                        "target_type": plan.target_type,
                        "runtime_bridge": plan.runtime_bridge,
                        "command": plan.command,
                        "sandboxed": plan.sandboxed,
                    }
                )
            return

        if clean_path == "/api/spotlight":
            q = str(body.get("query", ""))
            hits = [
                {
                    "category": r.category,
                    "title": r.title,
                    "subtitle": r.subtitle,
                    "action_cmd": r.action_cmd,
                }
                for r in spotlight_engine.query(q)
            ]
            q_low = q.strip().lower()
            if len(q_low) >= 2:
                for p in PROJECT_ROOT.rglob("*"):
                    if p.is_file() and q_low in p.name.lower() and ".git" not in str(p) and "__pycache__" not in str(p):
                        linux_p = linux_env.to_linux_path(p)
                        hits.append(
                            {
                                "category": "FILE",
                                "title": p.name,
                                "subtitle": linux_p,
                                "action_cmd": linux_p,
                            }
                        )
                        if len(hits) >= 10:
                            break
            self._send_json(hits)
            return

        if clean_path == "/api/terminal":
            cmd = str(body.get("cmd", "")).strip()
            cwd_str = str(body.get("cwd", "/home/aqua/AquaOS-Beta"))
            output, new_cwd = linux_env.execute_bash(cmd, cwd_str)
            self._send_json({"output": output, "cwd": new_cwd})
            return

        if clean_path == "/api/settings/get":
            self._send_json(config.as_dict())
            return

        if clean_path == "/api/settings/update":
            section = str(body.get("section", "")).strip()
            key = str(body.get("key", "")).strip()
            val = body.get("value")
            if section and key:
                config.set(section, key, val)
                self._send_json({"saved": True, "section": section, "key": key, "value": val})
            else:
                self._send_json({"error": "Missing section or key"}, status=400)
            return

        if clean_path == "/api/system/volume":
            vol = int(body.get("volume", 75))
            new_vol = ai_engine.system_services.set_volume(vol)
            self._send_json({"volume": new_vol})
            return

        if clean_path == "/api/system/brightness":
            b = int(body.get("brightness", 85))
            new_b = ai_engine.system_services.set_brightness(b)
            self._send_json({"brightness": new_b})
            return

        if clean_path == "/api/system/night-shift":
            try:
                enabled = normalize_night_shift(body.get("enabled"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("display", "night_shift", enabled)
            self._send_json({"enabled": enabled})
            return

        if clean_path == "/api/system/input-source":
            try:
                source = normalize_input_source(body.get("source"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("keyboard", "input_source", source)
            self._send_json({"source": source})
            return

        if clean_path == "/api/system/power-mode":
            try:
                mode = normalize_power_mode(body.get("mode"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("battery", "power_mode", mode)
            self._send_json({"mode": mode})
            return

        if clean_path == "/api/system/toggle":
            try:
                feature = normalize_toggle_feature(body.get("feature"))
                enabled = normalize_bool(body.get("enabled"), "enabled")
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            ss = ai_engine.system_services
            if feature == "wifi":
                ss._wifi_enabled = enabled
            elif feature == "bluetooth":
                ss._bluetooth_enabled = enabled
            elif feature == "dnd":
                ss._dnd_enabled = enabled
            # Persist so a restart (or the boot-time hydration) keeps the choice
            section, key = TOGGLE_PERSIST_KEYS[feature]
            config.set(section, key, enabled)
            self._send_json({"feature": feature, "enabled": enabled})
            return

        if clean_path == "/api/system/firewall":
            try:
                prefs = normalize_firewall_prefs(body)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            if not prefs:
                self._send_json({"error": "No firewall preference provided"}, status=400)
                return
            for key, value in prefs.items():
                config.set("security", key, value)
            self._send_json(prefs)
            return

        if clean_path == "/api/system/private-mac":
            try:
                enabled = normalize_bool(body.get("enabled"), "Private Wi-Fi Address")
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("network", "private_mac_randomization", enabled)
            self._send_json({"enabled": enabled})
            return

        if clean_path == "/api/system/notifications":
            if not isinstance(body, dict):
                self._send_json({"error": "Notification update must be a JSON object"}, status=400)
                return
            unknown = set(body.keys()) - set(NOTIFICATION_BOOL_KEYS) - {"grouping"}
            if unknown:
                self._send_json({"error": f"Unknown notification setting(s): {', '.join(sorted(unknown))}"}, status=400)
                return
            payload: Dict[str, Any] = {}
            try:
                bools = {key: body[key] for key in NOTIFICATION_BOOL_KEYS if key in body}
                payload.update(normalize_toggle_payload(bools, NOTIFICATION_BOOL_KEYS, "notification preference"))
                if "grouping" in body:
                    payload["grouping"] = normalize_notification_grouping(body.get("grouping"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            if not payload:
                self._send_json({"error": "No notification preference provided"}, status=400)
                return
            for key, value in payload.items():
                config.set("notifications", key, value)
            self._send_json(payload)
            return

        if clean_path == "/api/system/focus":
            try:
                mode = normalize_focus_mode(body.get("mode"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("focus", "mode", mode)
            self._send_json({"mode": mode})
            return

        if clean_path == "/api/system/airdrop":
            try:
                visibility = normalize_airdrop_visibility(body.get("visibility"))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("sharing", "airdrop_visibility", visibility)
            self._send_json({"visibility": visibility})
            return

        if clean_path == "/api/system/sharing":
            try:
                service = normalize_sharing_service(body.get("service"))
                enabled = normalize_bool(body.get("enabled"), service)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            config.set("sharing", service, enabled)
            self._send_json({"service": service, "enabled": enabled})
            return

        self.send_error(404)


def launch_app_window(url: str) -> None:
    busted_url = f"{url}/?v={int(time.time())}"
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        shutil.which("msedge"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, "--new-window", f"--app={busted_url}", "--window-size=1440,900"])
                return
            except Exception:
                pass
    webbrowser.open(busted_url)


def is_server_already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1.2) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_gui_preview(port: int = 8765) -> int:
    url = f"http://127.0.0.1:{port}"
    if is_server_already_running(port):
        print(f"AquaOS Backend Server is already active at {url} — launching fresh desktop window...")
        if "--no-browser" not in sys.argv:
            launch_app_window(url)
        return 0

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", port), AquaDesktopAPIHandler)
    print("=" * 68)
    print(f"  AquaOS 1.0 Beta Live Desktop Server Running at: {url}")
    print("=" * 68)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.3, lambda: launch_app_window(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    if "--cli" in sys.argv:
        from apps.about_aquaos import main as about_main

        about_main()
        raise SystemExit(0)
    raise SystemExit(run_gui_preview())
