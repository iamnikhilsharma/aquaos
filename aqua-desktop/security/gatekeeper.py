"""Aqua Gatekeeper & Heuristic Malware Scanner (aqua-gatekeeper).

Provides macOS Gatekeeper-style binary verification, static & heuristic malware scanning
(detecting ELF/PE/Mach-O anomalies, packed high-entropy payloads, crypto-miners, LD_PRELOAD
hijacking, and destructive shell commands), quarantine enforcement, and SHA-256 trust management.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class ScanReport:
    """Result of scanning a binary, package, or script with Aqua Gatekeeper."""

    file_path: str
    sha256: str
    file_format: str  # "ELF" | "PE_EXE" | "MACH_O" | "SCRIPT" | "ARCHIVE" | "DATA"
    entropy: float
    risk_level: str  # "CLEAN" | "LOW" | "SUSPICIOUS" | "MALICIOUS"
    risk_score: int  # 0 - 100
    findings: List[str] = field(default_factory=list)
    is_trusted: bool = False
    is_quarantined: bool = False
    recommended_action: str = "RUN_SANDBOXED"  # "ALLOW" | "RUN_SANDBOXED" | "BLOCK"


class AquaGatekeeper:
    """Static/heuristic malware scanner and trust database for AquaOS."""

    MALICIOUS_SIGNATURES: List[tuple[bytes, str, int]] = [
        (b"stratum+tcp://", "Cryptocurrency miner pool protocol (stratum+tcp)", 75),
        (b"xmrig", "XMRig cryptocurrency miner signature", 80),
        (b"LD_PRELOAD=", "Dynamic linker preload injection (LD_PRELOAD)", 45),
        (b"/etc/shadow", "Attempt to access system password hashes (/etc/shadow)", 65),
        (b"rm -rf / --no-preserve-root", "Destructive root filesystem wipe command", 95),
        (b"mkfs.ext", "Raw block device formatting command inside script/binary", 70),
        (b"curl ", "Network download invocation", 15),
        (b"| sh", "Piped remote shell execution pattern", 65),
        (b"| bash", "Piped remote bash execution pattern", 65),
        (b"base64 -d", "Obfuscated base64 payload decoding", 35),
        (b"/dev/tcp/", "Bash raw socket reverse shell pattern (/dev/tcp/)", 85),
        (b"nc -e /bin/", "Netcat reverse shell payload", 90),
        (b"VirtualAllocEx", "Windows PE remote process memory injection API", 55),
        (b"CreateRemoteThread", "Windows PE remote thread injection API", 60),
        (b"UPX!", "UPX packed executable header", 25),
    ]

    def __init__(self, trust_db_path: Optional[Path] = None) -> None:
        if trust_db_path is None:
            config_dir = Path(os.environ.get("AQUAOS_CONFIG_DIR", Path.home() / ".config" / "aquaos"))
            self.trust_db_path = config_dir / "trusted_apps.json"
        else:
            self.trust_db_path = Path(trust_db_path)
        self._trusted_hashes: Dict[str, Dict[str, str]] = {}
        self._load_trust_db()

    def _load_trust_db(self) -> None:
        if self.trust_db_path.exists():
            try:
                self._trusted_hashes = json.loads(self.trust_db_path.read_text(encoding="utf-8"))
            except Exception:
                self._trusted_hashes = {}

    def _save_trust_db(self) -> None:
        try:
            self.trust_db_path.parent.mkdir(parents=True, exist_ok=True)
            self.trust_db_path.write_text(json.dumps(self._trusted_hashes, indent=2), encoding="utf-8")
        except OSError:
            pass

    def trust_file(self, path: Path, note: str = "User approved via Gatekeeper") -> str:
        """Add a file's SHA-256 digest to the Gatekeeper trusted database."""
        digest = self.compute_sha256(path)
        self._trusted_hashes[digest] = {
            "path": str(path),
            "name": path.name,
            "note": note,
        }
        self._save_trust_db()
        return digest

    def revoke_trust(self, sha256_digest: str) -> None:
        """Remove a SHA-256 digest from the trusted database."""
        if sha256_digest in self._trusted_hashes:
            del self._trusted_hashes[sha256_digest]
            self._save_trust_db()

    @staticmethod
    def compute_sha256(path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def calculate_shannon_entropy(data: bytes) -> float:
        """Compute Shannon entropy (0.0 to 8.0 bits/byte) to detect encrypted/packed malware."""
        if not data:
            return 0.0
        counts = Counter(data)
        total = len(data)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log2(p)
        return round(entropy, 3)

    @staticmethod
    def detect_binary_format(header: bytes, suffix: str = "") -> str:
        """Identify binary format from magic bytes."""
        if header.startswith(b"\x7fELF"):
            return "ELF"
        if header.startswith(b"MZ"):
            return "PE_EXE"
        if header[:4] in (
            b"\xfe\xed\xfa\xce",
            b"\xfe\xed\xfa\xcf",
            b"\xce\xfa\xed\xfe",
            b"\xcf\xfa\xed\xfe",
            b"\xca\xfe\xba\xbe",
        ):
            return "MACH_O"
        if header.startswith(b"#!"):
            return "SCRIPT"
        if suffix.lower() in (".sh", ".py", ".pl", ".rb", ".ps1", ".bat"):
            return "SCRIPT"
        if suffix.lower() in (".dmg", ".iso", ".deb", ".rpm", ".apk", ".zip", ".tar", ".zst"):
            return "ARCHIVE"
        return "DATA"

    def scan_file(self, path: Path) -> ScanReport:
        """Perform static, signature, and entropy heuristic analysis on a target file."""
        path = Path(path)
        if not path.exists() or not path.is_file():
            return ScanReport(
                file_path=str(path),
                sha256="",
                file_format="UNKNOWN",
                entropy=0.0,
                risk_level="CLEAN",
                risk_score=0,
                findings=["File does not exist or is a directory"],
                recommended_action="RUN_SANDBOXED",
            )

        sha256 = self.compute_sha256(path)
        is_trusted = sha256 in self._trusted_hashes

        # Read up to first 2 MB for fast static analysis
        with path.open("rb") as f:
            sample = f.read(2 * 1024 * 1024)

        file_format = self.detect_binary_format(sample[:16], path.suffix)
        entropy = self.calculate_shannon_entropy(sample[:65536])

        findings: List[str] = []
        risk_score = 0

        for pattern, description, weight in self.MALICIOUS_SIGNATURES:
            if pattern in sample:
                findings.append(description)
                risk_score += weight

        if entropy >= 7.65 and file_format in ("ELF", "PE_EXE", "MACH_O"):
            findings.append(f"High payload entropy ({entropy} bits/byte) suggests packed or encrypted binary")
            risk_score += 30

        if file_format == "PE_EXE":
            findings.append("Foreign Windows PE executable (.exe/.msi) — requires Wine Sandbox")
            risk_score = max(risk_score, 15)

        risk_score = min(100, risk_score)
        if is_trusted and risk_score < 70:
            risk_level = "CLEAN"
            recommended = "ALLOW"
        elif risk_score >= 70:
            risk_level = "MALICIOUS"
            recommended = "BLOCK"
        elif risk_score >= 35:
            risk_level = "SUSPICIOUS"
            recommended = "RUN_SANDBOXED"
        elif risk_score > 0:
            risk_level = "LOW"
            recommended = "RUN_SANDBOXED"
        else:
            risk_level = "CLEAN"
            recommended = "ALLOW" if is_trusted else "RUN_SANDBOXED"

        return ScanReport(
            file_path=str(path),
            sha256=sha256,
            file_format=file_format,
            entropy=entropy,
            risk_level=risk_level,
            risk_score=risk_score,
            findings=findings,
            is_trusted=is_trusted,
            is_quarantined=(risk_level in ("SUSPICIOUS", "MALICIOUS")),
            recommended_action=recommended,
        )

    def rea_deep_inspect(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Perform deep binary reverse engineering, section analysis, entropy mapping, and REA integration."""
        target = Path(path)
        if not target.exists() or not target.is_file():
            return {
                "error": f"Target binary not found: {target}",
                "file_name": target.name,
                "file_path": str(target),
                "file_size": 0,
                "file_format": "UNKNOWN",
                "risk_level": "UNKNOWN",
            }

        scan_rep = self.scan_file(target)
        raw_bytes = target.read_bytes()
        file_size = len(raw_bytes)

        # Hashes
        md5_hash = hashlib.md5(raw_bytes).hexdigest()
        sha1_hash = hashlib.sha1(raw_bytes).hexdigest()
        sha256_hash = scan_rep.sha256

        # 32-segment entropy ribbon for interactive visualization
        block_count = 32
        block_size = max(1, file_size // block_count)
        entropy_ribbon: List[Dict[str, Any]] = []
        for i in range(block_count):
            start = i * block_size
            end = min(file_size, (i + 1) * block_size if i < block_count - 1 else file_size)
            chunk = raw_bytes[start:end]
            ent = self.calculate_shannon_entropy(chunk)
            entropy_ribbon.append({
                "block": i,
                "offset_start": start,
                "offset_end": end,
                "entropy": ent,
                "classification": "PACKED_ENCRYPTED" if ent >= 7.5 else "CODE_EXEC" if ent >= 5.5 else "DATA_RESOURCES",
            })

        # Format-specific deep parsing
        sections: List[Dict[str, Any]] = []
        architecture = "Unknown"
        mitigations: Dict[str, bool] = {
            "dynamic_base_aslr": False,
            "nx_dep_compatible": False,
            "high_entropy_va": False,
            "guard_cf": False,
            "code_signed": False,
        }
        rea_evidence: Optional[Dict[str, Any]] = None
        rea_status = "native_analyzer"

        if raw_bytes.startswith(b"MZ") and len(raw_bytes) >= 0x40:
            file_format = "PE_EXE"
            e_lfanew = struct.unpack_from("<I", raw_bytes, 0x3C)[0]
            if e_lfanew + 24 < file_size and raw_bytes[e_lfanew:e_lfanew+4] == b"PE\x00\x00":
                machine, num_sections, timedatestamp, _, _, size_opt_hdr, characteristics = struct.unpack_from(
                    "<HHIIIHH", raw_bytes, e_lfanew + 4
                )
                arch_map = {0x014C: "i386 (32-bit)", 0x8664: "AMD64 (x86_64)", 0xAA64: "ARM64"}
                architecture = arch_map.get(machine, f"PE 0x{machine:04X}")

                opt_offset = e_lfanew + 24
                if size_opt_hdr >= 68:
                    opt_magic = struct.unpack_from("<H", raw_bytes, opt_offset)[0]
                    is_64 = (opt_magic == 0x20B)
                    dll_char_offset = opt_offset + 70
                    if dll_char_offset + 2 <= file_size:
                        dll_char = struct.unpack_from("<H", raw_bytes, dll_char_offset)[0]
                        mitigations["dynamic_base_aslr"] = bool(dll_char & 0x0040)
                        mitigations["nx_dep_compatible"] = bool(dll_char & 0x0100)
                        mitigations["high_entropy_va"] = bool(dll_char & 0x0020)
                        mitigations["guard_cf"] = bool(dll_char & 0x4000)

                sec_offset = opt_offset + size_opt_hdr
                for s_idx in range(min(num_sections, 32)):
                    s_off = sec_offset + s_idx * 40
                    if s_off + 40 <= file_size:
                        s_name_raw = raw_bytes[s_off:s_off+8].split(b"\x00")[0]
                        s_name = s_name_raw.decode("ascii", errors="replace")
                        v_size, v_addr, raw_size, raw_ptr = struct.unpack_from("<IIII", raw_bytes, s_off + 8)
                        charact = struct.unpack_from("<I", raw_bytes, s_off + 36)[0]
                        sec_slice = raw_bytes[raw_ptr:raw_ptr + min(raw_size, file_size - raw_ptr)] if raw_ptr < file_size else b""
                        sec_ent = self.calculate_shannon_entropy(sec_slice)
                        perms = ("R" if charact & 0x40000000 else "") + ("W" if charact & 0x80000000 else "") + ("X" if charact & 0x20000000 else "")
                        sections.append({
                            "name": s_name,
                            "virtual_address": f"0x{v_addr:08X}",
                            "virtual_size": v_size,
                            "raw_size": raw_size,
                            "entropy": sec_ent,
                            "permissions": perms or "R",
                        })

            # Check if REA CLI is installed and can provide authoritative PE Evidence
            try:
                npm_cache = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
                rea_script = None
                if npm_cache.exists():
                    matches = list(npm_cache.glob("*/node_modules/rea-agents/scripts/rea.mjs"))
                    if matches:
                        rea_script = matches[-1]

                if rea_script and rea_script.exists():
                    cmd = ["node", str(rea_script), "inspect-pe-resources", str(target), "--format", "json"]
                else:
                    cmd = ["cmd.exe", "/c", "npx.cmd", "-y", "rea-agents@6.7.0", "inspect-pe-resources", str(target), "--format", "json"]

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                if proc.returncode == 0 and proc.stdout:
                    rea_evidence = json.loads(proc.stdout)
                    rea_status = "rea_mcp_aligned"
            except Exception:
                pass

        elif raw_bytes.startswith(b"\x7fELF") and len(raw_bytes) >= 64:
            file_format = "ELF"
            ei_class = raw_bytes[4]
            architecture = "x86_64" if ei_class == 2 else "x86 (32-bit)"
            mitigations["nx_dep_compatible"] = True
            mitigations["dynamic_base_aslr"] = (raw_bytes[16] == 3)  # ET_DYN (PIE)

        elif raw_bytes.startswith(b"\x00asm"):
            file_format = "WASM"
            architecture = "WebAssembly (v1)"

        elif raw_bytes.startswith(b"SQLite format 3\x00"):
            file_format = "SQLITE"
            architecture = "SQLite DB v3"

        elif raw_bytes.startswith(b"#!") or target.suffix.lower() in (".sh", ".py", ".pl", ".rb"):
            file_format = "SCRIPT"
            architecture = "Interpreted Script"

        else:
            file_format = scan_rep.file_format
            architecture = "Generic Binary / Data"

        # String extraction & Indicators of Compromise (IoC)
        text_sample = raw_bytes[:500000].decode("ascii", errors="ignore")
        ascii_strings = [m.group(0).decode("ascii", errors="replace") for m in re.finditer(b"[\x20-\x7e]{4,}", raw_bytes[:500000])]
        urls = list(dict.fromkeys(re.findall(r"https?://[a-zA-Z0-9\.\-_~:/?#\[\]@!$&'()*+,;=%]+", text_sample)))[:15]
        ips = list(dict.fromkeys(re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", text_sample)))[:15]
        suspicious_keywords = [
            "VirtualAlloc", "CreateRemoteThread", "LoadLibrary", "GetProcAddress",
            "socket", "connect", "execve", "fork", "system", "ptrace", "chmod", "setuid",
            "LD_PRELOAD", "/bin/sh", "/bin/bash", "cmd.exe", "powershell.exe", "xmrig", "stratum",
        ]
        found_suspicious = list({s for s in ascii_strings if any(k.lower() in s.lower() for k in suspicious_keywords)})[:25]

        return {
            "file_name": target.name,
            "file_path": str(target),
            "file_size": file_size,
            "file_format": file_format,
            "architecture": architecture,
            "md5": md5_hash,
            "sha1": sha1_hash,
            "sha256": sha256_hash,
            "overall_entropy": scan_rep.entropy,
            "risk_level": scan_rep.risk_level,
            "risk_score": scan_rep.risk_score,
            "findings": scan_rep.findings,
            "is_trusted": scan_rep.is_trusted,
            "is_quarantined": scan_rep.is_quarantined,
            "recommended_action": scan_rep.recommended_action,
            "mitigations": mitigations,
            "sections": sections,
            "entropy_ribbon": entropy_ribbon,
            "urls": urls,
            "ips": ips,
            "suspicious_apis": found_suspicious,
            "rea_status": rea_status,
            "rea_evidence": rea_evidence,
        }

    def search_binary_strings(self, path: Union[str, Path], query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """Extract and search printable ASCII/Unicode strings from a binary."""
        target = Path(path)
        if not target.exists() or not target.is_file():
            return []

        raw_bytes = target.read_bytes()[:1000000]
        results: List[Dict[str, Any]] = []
        q_low = query.strip().lower()

        for m in re.finditer(b"[\x20-\x7e]{4,}", raw_bytes):
            val = m.group(0).decode("ascii", errors="replace")
            if not q_low or q_low in val.lower():
                results.append({
                    "offset": m.start(),
                    "offset_hex": f"0x{m.start():08X}",
                    "length": len(val),
                    "value": val,
                })
                if len(results) >= limit:
                    break
        return results

