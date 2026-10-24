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
            is_64 = (ei_class == 2)
            machine = struct.unpack_from("<H", raw_bytes, 18)[0]
            mach_map = {0x03: "x86 (32-bit)", 0x3E: "x86_64 (AMD64)", 0x28: "ARM", 0xB7: "AArch64 (ARM64)", 0xF3: "RISC-V"}
            architecture = mach_map.get(machine, "x86_64" if is_64 else "x86")
            mitigations["nx_dep_compatible"] = True
            mitigations["dynamic_base_aslr"] = (raw_bytes[16] == 3)  # ET_DYN (PIE)

            # Parse ELF Section Headers
            try:
                if is_64 and len(raw_bytes) >= 64:
                    e_shoff = struct.unpack_from("<Q", raw_bytes, 40)[0]
                    e_shentsize = struct.unpack_from("<H", raw_bytes, 58)[0]
                    e_shnum = struct.unpack_from("<H", raw_bytes, 60)[0]
                    e_shstrndx = struct.unpack_from("<H", raw_bytes, 62)[0]

                    if 0 < e_shoff < file_size and e_shnum > 0 and e_shstrndx < e_shnum:
                        strtab_sh_off = e_shoff + e_shstrndx * e_shentsize
                        if strtab_sh_off + 40 <= file_size:
                            strtab_offset = struct.unpack_from("<Q", raw_bytes, strtab_sh_off + 24)[0]
                            strtab_size = struct.unpack_from("<Q", raw_bytes, strtab_sh_off + 32)[0]
                            shstrtab = raw_bytes[strtab_offset:min(file_size, strtab_offset + strtab_size)] if strtab_offset < file_size else b""

                            for s_idx in range(min(e_shnum, 32)):
                                s_entry = e_shoff + s_idx * e_shentsize
                                if s_entry + 64 <= file_size:
                                    sh_name_idx = struct.unpack_from("<I", raw_bytes, s_entry)[0]
                                    sh_flags = struct.unpack_from("<Q", raw_bytes, s_entry + 8)[0]
                                    sh_addr = struct.unpack_from("<Q", raw_bytes, s_entry + 16)[0]
                                    sh_offset = struct.unpack_from("<Q", raw_bytes, s_entry + 24)[0]
                                    sh_size = struct.unpack_from("<Q", raw_bytes, s_entry + 32)[0]

                                    s_name = ""
                                    if shstrtab and sh_name_idx < len(shstrtab):
                                        null_term = shstrtab.find(b"\x00", sh_name_idx)
                                        s_name = shstrtab[sh_name_idx:null_term].decode("ascii", errors="replace") if null_term != -1 else ""

                                    if s_name:
                                        sec_slice = raw_bytes[sh_offset:sh_offset + min(sh_size, file_size - sh_offset)] if sh_offset < file_size else b""
                                        sec_ent = self.calculate_shannon_entropy(sec_slice) if sec_slice else 0.0
                                        perms = ("R" if sh_flags & 0x2 else "") + ("W" if sh_flags & 0x1 else "") + ("X" if sh_flags & 0x4 else "")
                                        sections.append({
                                            "name": s_name,
                                            "virtual_address": f"0x{sh_addr:08X}",
                                            "virtual_size": sh_size,
                                            "raw_size": sh_size,
                                            "entropy": sec_ent,
                                            "permissions": perms or "R",
                                        })
            except Exception:
                pass

        elif raw_bytes[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe") and len(raw_bytes) >= 32:
            file_format = "MACH_O"
            magic = raw_bytes[:4]
            is_fat = (magic == b"\xca\xfe\xba\xbe")
            is_64 = (magic in (b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"))

            if is_fat:
                architecture = "Universal Binary (FAT)"
            elif is_64:
                cputype = struct.unpack_from("<I", raw_bytes, 4)[0]
                arch_map = {0x01000007: "x86_64 (Intel Mac)", 0x0100000C: "ARM64 (Apple Silicon M1/M2/M3/M4)"}
                architecture = arch_map.get(cputype, "Mach-O 64-bit")
            else:
                architecture = "Mach-O 32-bit"

            mitigations["nx_dep_compatible"] = True
            mitigations["dynamic_base_aslr"] = True  # macOS PIE default

            # Parse Mach-O Load Commands
            try:
                if is_64 and not is_fat:
                    ncmds = struct.unpack_from("<I", raw_bytes, 16)[0]
                    cmd_offset = 32
                    for _ in range(min(ncmds, 32)):
                        if cmd_offset + 8 > file_size:
                            break
                        cmd = struct.unpack_from("<I", raw_bytes, cmd_offset)[0]
                        cmdsize = struct.unpack_from("<I", raw_bytes, cmd_offset + 4)[0]

                        # LC_SEGMENT_64 = 0x19
                        if cmd == 0x19 and cmd_offset + 72 <= file_size:
                            segname = raw_bytes[cmd_offset + 8:cmd_offset + 24].split(b"\x00")[0].decode("ascii", errors="replace")
                            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", raw_bytes, cmd_offset + 24)
                            nsects = struct.unpack_from("<I", raw_bytes, cmd_offset + 64)[0]

                            sec_cur = cmd_offset + 72
                            for _ in range(min(nsects, 16)):
                                if sec_cur + 80 <= file_size:
                                    secname = raw_bytes[sec_cur:sec_cur + 16].split(b"\x00")[0].decode("ascii", errors="replace")
                                    s_addr, s_size, s_off = struct.unpack_from("<QQI", raw_bytes, sec_cur + 32)
                                    sec_slice = raw_bytes[s_off:s_off + min(s_size, file_size - s_off)] if s_off < file_size else b""
                                    sec_ent = self.calculate_shannon_entropy(sec_slice) if sec_slice else 0.0
                                    perms = "RX" if "TEXT" in segname else ("RW" if "DATA" in segname else "R")
                                    sections.append({
                                        "name": f"{segname}.{secname}",
                                        "virtual_address": f"0x{s_addr:08X}",
                                        "virtual_size": s_size,
                                        "raw_size": s_size,
                                        "entropy": sec_ent,
                                        "permissions": perms,
                                    })
                                    sec_cur += 80

                        cmd_offset += cmdsize
            except Exception:
                pass

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

    def disassemble_code(self, path: Union[str, Path], offset: int = 0, count: int = 32) -> Dict[str, Any]:
        """Disassemble executable code or Python bytecode into readable assembly instructions."""
        target = Path(path)
        if not target.exists() or not target.is_file():
            return {"format": "UNKNOWN", "instructions": [], "error": "File not found"}

        raw_bytes = target.read_bytes()
        file_size = len(raw_bytes)

        # 1. Python bytecode disassembler (for .py and .pyc)
        if target.suffix.lower() == ".py":
            import dis
            try:
                code_obj = compile(raw_bytes.decode("utf-8", errors="replace"), target.name, "exec")
                instructions: List[Dict[str, Any]] = []
                for instr in dis.Bytecode(code_obj):
                    instructions.append({
                        "address": f"0x{instr.offset:04X}",
                        "bytes": f"{instr.opcode:02X}" + (f" {instr.arg:02X}" if instr.arg is not None else ""),
                        "mnemonic": instr.opname,
                        "operands": str(instr.argrepr or instr.argval or ""),
                        "comment": f"Line {instr.starts_line}" if instr.starts_line else "",
                    })
                    if len(instructions) >= count:
                        break
                return {
                    "format": "PYTHON_BYTECODE",
                    "target": target.name,
                    "instructions": instructions,
                    "total_instructions": len(instructions),
                }
            except Exception:
                pass

        # 2. Native x86_64 / ELF / PE disassembly
        entry_offset = offset
        is_pe = raw_bytes.startswith(b"MZ") and len(raw_bytes) >= 0x40
        is_elf = raw_bytes.startswith(b"\x7fELF") and len(raw_bytes) >= 32
        if is_pe and offset == 0:
            try:
                e_lfanew = struct.unpack_from("<I", raw_bytes, 0x3C)[0]
                if e_lfanew + 40 < file_size:
                    opt_offset = e_lfanew + 24
                    entry_rva = struct.unpack_from("<I", raw_bytes, opt_offset + 16)[0]
                    num_sections = struct.unpack_from("<H", raw_bytes, e_lfanew + 6)[0]
                    size_opt = struct.unpack_from("<H", raw_bytes, e_lfanew + 20)[0]
                    sec_base = opt_offset + size_opt
                    for s in range(min(num_sections, 16)):
                        s_off = sec_base + s * 40
                        if s_off + 40 <= file_size:
                            v_size, v_addr, raw_size, raw_ptr = struct.unpack_from("<IIII", raw_bytes, s_off + 8)
                            if v_addr <= entry_rva < v_addr + v_size:
                                entry_offset = raw_ptr + (entry_rva - v_addr)
                                break
            except Exception:
                entry_offset = 0
        elif is_elf and offset == 0:
            try:
                is_64 = raw_bytes[4] == 2
                e_entry = struct.unpack_from("<Q" if is_64 else "<I", raw_bytes, 24)[0]
                if 0 < e_entry < file_size:
                    entry_offset = e_entry
                elif e_entry >= 0x400000 and (e_entry - 0x400000) < file_size:
                    entry_offset = e_entry - 0x400000
            except Exception:
                entry_offset = 0

        code_slice = raw_bytes[entry_offset:min(file_size, entry_offset + 512)]
        instructions: List[Dict[str, Any]] = []
        idx = 0
        base_addr = 0x140001000 + entry_offset if is_pe else 0x401000 + entry_offset

        while idx < len(code_slice) and len(instructions) < count:
            addr = base_addr + idx
            addr_str = f"0x{addr:08X}"
            b0 = code_slice[idx]

            # Match common x86_64 instruction patterns
            if b0 == 0x55:
                instructions.append({"address": addr_str, "bytes": "55", "mnemonic": "push", "operands": "rbp", "comment": "Standard Prologue"})
                idx += 1
            elif b0 == 0x53:
                instructions.append({"address": addr_str, "bytes": "53", "mnemonic": "push", "operands": "rbx", "comment": ""})
                idx += 1
            elif b0 == 0x56:
                instructions.append({"address": addr_str, "bytes": "56", "mnemonic": "push", "operands": "rsi", "comment": ""})
                idx += 1
            elif b0 == 0x57:
                instructions.append({"address": addr_str, "bytes": "57", "mnemonic": "push", "operands": "rdi", "comment": ""})
                idx += 1
            elif b0 == 0x5D:
                instructions.append({"address": addr_str, "bytes": "5D", "mnemonic": "pop", "operands": "rbp", "comment": ""})
                idx += 1
            elif b0 == 0x5B:
                instructions.append({"address": addr_str, "bytes": "5B", "mnemonic": "pop", "operands": "rbx", "comment": ""})
                idx += 1
            elif b0 == 0xC3:
                instructions.append({"address": addr_str, "bytes": "C3", "mnemonic": "ret", "operands": "", "comment": "Return from procedure"})
                idx += 1
            elif b0 == 0x90:
                instructions.append({"address": addr_str, "bytes": "90", "mnemonic": "nop", "operands": "", "comment": "Alignment padding"})
                idx += 1
            elif b0 == 0xCC:
                instructions.append({"address": addr_str, "bytes": "CC", "mnemonic": "int3", "operands": "", "comment": "Debugger breakpoint"})
                idx += 1
            elif idx + 2 < len(code_slice) and code_slice[idx:idx+3] == b"\x48\x89\xe5":
                instructions.append({"address": addr_str, "bytes": "48 89 E5", "mnemonic": "mov", "operands": "rbp, rsp", "comment": "Frame pointer setup"})
                idx += 3
            elif idx + 3 < len(code_slice) and code_slice[idx:idx+3] == b"\x48\x83\xec":
                imm = code_slice[idx+3]
                instructions.append({"address": addr_str, "bytes": f"48 83 EC {imm:02X}", "mnemonic": "sub", "operands": f"rsp, 0x{imm:02X}", "comment": f"Allocate {imm} bytes stack frame"})
                idx += 4
            elif idx + 3 < len(code_slice) and code_slice[idx:idx+3] == b"\x48\x83\xc4":
                imm = code_slice[idx+3]
                instructions.append({"address": addr_str, "bytes": f"48 83 C4 {imm:02X}", "mnemonic": "add", "operands": f"rsp, 0x{imm:02X}", "comment": f"Deallocate stack frame"})
                idx += 4
            elif idx + 1 < len(code_slice) and code_slice[idx:idx+2] == b"\x31\xc0":
                instructions.append({"address": addr_str, "bytes": "31 C0", "mnemonic": "xor", "operands": "eax, eax", "comment": "Return code 0 (SUCCESS)"})
                idx += 2
            elif idx + 2 < len(code_slice) and code_slice[idx:idx+3] == b"\x48\x31\xc0":
                instructions.append({"address": addr_str, "bytes": "48 31 C0", "mnemonic": "xor", "operands": "rax, rax", "comment": "Zero rax"})
                idx += 3
            elif b0 == 0xE8 and idx + 4 < len(code_slice):
                rel = struct.unpack_from("<i", code_slice, idx + 1)[0]
                target_addr = addr + 5 + rel
                raw_hex = " ".join(f"{b:02X}" for b in code_slice[idx:idx+5])
                instructions.append({"address": addr_str, "bytes": raw_hex, "mnemonic": "call", "operands": f"0x{target_addr:08X}", "comment": "Procedure call"})
                idx += 5
            elif b0 == 0xE9 and idx + 4 < len(code_slice):
                rel = struct.unpack_from("<i", code_slice, idx + 1)[0]
                target_addr = addr + 5 + rel
                raw_hex = " ".join(f"{b:02X}" for b in code_slice[idx:idx+5])
                instructions.append({"address": addr_str, "bytes": raw_hex, "mnemonic": "jmp", "operands": f"0x{target_addr:08X}", "comment": "Unconditional branch"})
                idx += 5
            elif b0 == 0xEB and idx + 1 < len(code_slice):
                rel8 = struct.unpack_from("<b", code_slice, idx + 1)[0]
                target_addr = addr + 2 + rel8
                instructions.append({"address": addr_str, "bytes": f"EB {code_slice[idx+1]:02X}", "mnemonic": "jmp short", "operands": f"0x{target_addr:08X}", "comment": ""})
                idx += 2
            elif b0 in (0x74, 0x75) and idx + 1 < len(code_slice):
                rel8 = struct.unpack_from("<b", code_slice, idx + 1)[0]
                mnem = "je" if b0 == 0x74 else "jne"
                target_addr = addr + 2 + rel8
                instructions.append({"address": addr_str, "bytes": f"{b0:02X} {code_slice[idx+1]:02X}", "mnemonic": mnem, "operands": f"0x{target_addr:08X}", "comment": "Conditional branch"})
                idx += 2
            elif idx + 1 < len(code_slice) and code_slice[idx:idx+2] == b"\x0f\x05":
                instructions.append({"address": addr_str, "bytes": "0F 05", "mnemonic": "syscall", "operands": "", "comment": "Fast system call into kernel"})
                idx += 2
            else:
                instructions.append({"address": addr_str, "bytes": f"{b0:02X}", "mnemonic": "db", "operands": f"0x{b0:02X}", "comment": ""})
                idx += 1

        return {
            "format": "PE_EXE" if is_pe else "ELF" if raw_bytes.startswith(b"\x7fELF") else "BINARY",
            "target": target.name,
            "entry_offset": entry_offset,
            "instructions": instructions,
            "total_instructions": len(instructions),
        }

    def extract_imports_and_exports(self, path: Union[str, Path]) -> Dict[str, Any]:
        """Extract imported dynamic libraries, system calls, and exported functions."""
        target = Path(path)
        if not target.exists() or not target.is_file():
            return {"libraries": [], "imports": [], "exports": []}

        raw_bytes = target.read_bytes()[:1500000]
        text_sample = raw_bytes.decode("ascii", errors="ignore")

        libraries: List[str] = []
        imports: List[Dict[str, str]] = []
        exports: List[str] = []

        # 1. Match DLL names (.dll), shared objects (.so), dylibs (.dylib), and macOS frameworks (.framework)
        dll_matches = re.findall(r"\b([a-zA-Z0-9_\-\.]+\.(?:dll|so(?:\.[0-9]+)?|dylib))\b", text_sample, re.IGNORECASE)
        framework_matches = re.findall(r"\b([A-Za-z0-9_]+\.framework)\b", text_sample)
        libraries = list(dict.fromkeys(dll_matches + framework_matches))[:35]

        # 2. Known Windows, Linux & macOS security-critical API signatures
        known_apis = {
            "VirtualAlloc": ("Memory Allocation", "MEDIUM"),
            "VirtualProtect": ("Memory Permission Change (W^X bypass)", "HIGH"),
            "CreateRemoteThread": ("Process Injection", "HIGH"),
            "WriteProcessMemory": ("Process Memory Modification", "HIGH"),
            "LoadLibraryA": ("Dynamic Module Loading", "LOW"),
            "LoadLibraryW": ("Dynamic Module Loading", "LOW"),
            "GetProcAddress": ("Dynamic Symbol Resolution", "LOW"),
            "CreateProcessW": ("Subprocess Spawning", "MEDIUM"),
            "RegOpenKeyExW": ("Windows Registry Access", "LOW"),
            "RegSetValueExW": ("Windows Registry Modification", "MEDIUM"),
            "WSAStartup": ("Network Socket Initialization", "LOW"),
            "socket": ("Network Communication", "LOW"),
            "connect": ("Remote Network Connect", "MEDIUM"),
            "bind": ("Network Port Binding", "MEDIUM"),
            "listen": ("Network Server Listening", "MEDIUM"),
            "execve": ("Execute Process Image", "MEDIUM"),
            "fork": ("Process Forking", "LOW"),
            "ptrace": ("Process Tracing / Anti-Debugging", "HIGH"),
            "mprotect": ("Memory Protection Modification", "HIGH"),
            "chmod": ("File Permission Modification", "MEDIUM"),
            "setuid": ("Privilege Escalation", "HIGH"),
            "task_for_pid": ("Mach Task Port Hijacking / Code Injection", "HIGH"),
            "mach_vm_write": ("Mach Virtual Memory Write / Code Injection", "HIGH"),
            "mach_vm_protect": ("Mach Memory Permission Change (W^X bypass)", "HIGH"),
            "posix_spawn": ("Process Spawning", "MEDIUM"),
            "sysctlbyname": ("Kernel State Query / Anti-Analysis", "LOW"),
        }

        for api, (desc, severity) in known_apis.items():
            if api in text_sample:
                imports.append({
                    "symbol": api,
                    "description": desc,
                    "severity": severity,
                })

        # 3. For Python scripts, extract imports using AST
        if target.suffix.lower() == ".py":
            import ast
            try:
                tree = ast.parse(raw_bytes.decode("utf-8", errors="replace"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            libraries.append(alias.name)
                            imports.append({"symbol": alias.name, "description": "Python Standard / External Module", "severity": "LOW"})
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        libraries.append(node.module)
                        for alias in node.names:
                            imports.append({"symbol": f"{node.module}.{alias.name}", "description": "Imported Function / Class", "severity": "LOW"})
                    elif isinstance(node, ast.FunctionDef):
                        exports.append(node.name)
            except Exception:
                pass

        libraries = list(dict.fromkeys(libraries))
        return {
            "target": target.name,
            "libraries": libraries,
            "imports": imports,
            "exports": exports[:30],
        }

    def generate_hex_dump(self, path: Union[str, Path], offset: int = 0, length: int = 256) -> Dict[str, Any]:
        """Generate a colorized/formatted hex dump view (offset, 16-hex bytes, ASCII representation)."""
        target = Path(path)
        if not target.exists() or not target.is_file():
            return {"lines": [], "offset": 0, "total_size": 0, "has_more": False}

        file_size = target.stat().st_size
        offset = max(0, min(offset, file_size))
        length = min(length, 4096)

        with target.open("rb") as f:
            f.seek(offset)
            chunk = f.read(length)

        lines: List[Dict[str, Any]] = []
        for i in range(0, len(chunk), 16):
            sub = chunk[i:i+16]
            cur_off = offset + i
            off_str = f"{cur_off:08X}"
            hex_parts = [f"{b:02X}" for b in sub]
            left = " ".join(hex_parts[:8])
            right = " ".join(hex_parts[8:])
            hex_str = f"{left:<23}  {right:<23}".rstrip()
            ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in sub)
            lines.append({
                "offset": cur_off,
                "offset_hex": off_str,
                "hex": hex_str,
                "ascii": ascii_str,
                "raw_bytes": list(sub),
            })

        return {
            "file_name": target.name,
            "offset": offset,
            "length": len(chunk),
            "total_size": file_size,
            "has_more": (offset + len(chunk)) < file_size,
            "next_offset": offset + len(chunk),
            "prev_offset": max(0, offset - length),
            "lines": lines,
        }

    def decompile_code(self, path: Union[str, Path], offset: int = 0, limit_lines: int = 200) -> Dict[str, Any]:
        """Reconstruct high-level C / Python pseudo-code from disassembly, AST, or native opcodes."""
        target = Path(path)
        if not target.exists() or not target.is_file():
            return {
                "target": str(path),
                "format": "UNKNOWN",
                "decompiled_lines": [{"line": 1, "code": "// Error: Target binary or script not found on disk", "type": "comment"}],
                "raw_pseudo_code": "// Error: File not found",
                "functions": [],
                "security_annotations": [],
            }

        raw_bytes = target.read_bytes()
        file_size = len(raw_bytes)

        # 1. Python AST Decompilation & Reconstruction
        if target.suffix.lower() == ".py":
            import ast
            try:
                tree = ast.parse(raw_bytes.decode("utf-8", errors="replace"), filename=target.name)
                lines: List[Dict[str, Any]] = []
                security_annotations: List[Dict[str, str]] = []
                functions: List[str] = []

                lines.append({"line": len(lines) + 1, "code": f"// AquaOS REA Decompiler — Python AST Reconstruction: {target.name}", "type": "comment"})
                lines.append({"line": len(lines) + 1, "code": f"// Target Size: {file_size} bytes | Reconstructed from Source AST", "type": "comment"})
                lines.append({"line": len(lines) + 1, "code": "", "type": "blank"})

                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.Import):
                        for n in node.names:
                            lines.append({"line": len(lines) + 1, "code": f"#include <{n.name}> // import {n.name}", "type": "include"})
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        for n in node.names:
                            lines.append({"line": len(lines) + 1, "code": f"using {node.module}::{n.name};", "type": "include"})
                    elif isinstance(node, ast.FunctionDef):
                        functions.append(node.name)
                        lines.append({"line": len(lines) + 1, "code": "", "type": "blank"})
                        args = [a.arg for a in node.args.args]
                        lines.append({"line": len(lines) + 1, "code": f"any {node.name}({', '.join(f'any {a}' for a in args)}) {{", "type": "fn_start"})
                        
                        # Inspect function body statements
                        for stmt in node.body:
                            if isinstance(stmt, ast.Return):
                                lines.append({"line": len(lines) + 1, "code": "    return result;", "type": "return"})
                            elif isinstance(stmt, ast.Assign):
                                targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                                lines.append({"line": len(lines) + 1, "code": f"    auto {', '.join(targets)} = expression();", "type": "code"})
                            elif isinstance(stmt, ast.If):
                                lines.append({"line": len(lines) + 1, "code": "    if (condition) {", "type": "control"})
                                lines.append({"line": len(lines) + 1, "code": "        // branch body", "type": "comment"})
                                lines.append({"line": len(lines) + 1, "code": "    }", "type": "control"})
                            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                                func_name = stmt.value.func.id if isinstance(stmt.value.func, ast.Name) else "subroutine"
                                if func_name in ("eval", "exec", "system", "popen", "spawn"):
                                    security_annotations.append({
                                        "line": len(lines) + 1,
                                        "severity": "HIGH",
                                        "message": f"Dangerous dynamic execution call: {func_name}()",
                                    })
                                    lines.append({"line": len(lines) + 1, "code": f"    /* [!] SECURITY RISK: {func_name}() */", "type": "risk"})
                                lines.append({"line": len(lines) + 1, "code": f"    {func_name}();", "type": "call"})
                            else:
                                lines.append({"line": len(lines) + 1, "code": "    /* statement */", "type": "code"})
                        lines.append({"line": len(lines) + 1, "code": "}", "type": "fn_end"})

                raw_pseudo = "\n".join(l["code"] for l in lines)
                return {
                    "target": target.name,
                    "format": "PYTHON_AST",
                    "entry_offset": 0,
                    "decompiled_lines": lines[:limit_lines],
                    "raw_pseudo_code": raw_pseudo,
                    "functions": functions,
                    "security_annotations": security_annotations,
                }
            except Exception:
                pass

        # 2. Native Binary (ELF / PE / Mach-O) Opcode Pseudo-Code Decompiler
        disasm = self.disassemble_code(target, offset=offset, count=64)
        instructions = disasm.get("instructions", [])
        fmt = disasm.get("format", "BINARY")
        entry_off = disasm.get("entry_offset", 0)

        lines = []
        security_annotations = []
        functions = [f"sub_{entry_off:08X}"]

        lines.append({"line": len(lines) + 1, "code": f"// AquaOS REA Decompiler — Native Reverse Engineering Reconstructor", "type": "comment"})
        lines.append({"line": len(lines) + 1, "code": f"// Target: {target.name} | Format: {fmt} | Entry Offset: 0x{entry_off:08X}", "type": "comment"})
        lines.append({"line": len(lines) + 1, "code": f"// Generated by REA Decompiler Engine (64-bit calling conventions)", "type": "comment"})
        lines.append({"line": len(lines) + 1, "code": "", "type": "blank"})

        # Scan for imported security APIs from gatekeeper
        imp_data = self.extract_imports_and_exports(target)
        known_sec_symbols = {item["symbol"]: item for item in imp_data.get("imports", [])}

        lines.append({"line": len(lines) + 1, "code": f"// --- High-Level Procedure Reconstruction ---", "type": "comment"})
        lines.append({"line": len(lines) + 1, "code": f"uint64_t sub_{entry_off:08X}(uint64_t rdi_arg0, uint64_t rsi_arg1) {{", "type": "fn_start"})
        lines.append({"line": len(lines) + 1, "code": "    uint64_t rax_result = 0;", "type": "code"})
        lines.append({"line": len(lines) + 1, "code": "    uint8_t  stack_frame[64];", "type": "code"})

        in_condition = False
        for instr in instructions:
            mnem = instr.get("mnemonic", "").lower()
            operands = instr.get("operands", "")
            addr = instr.get("address", "")

            if mnem == "push":
                lines.append({"line": len(lines) + 1, "code": f"    // [{addr}] preserve register: {operands}", "type": "comment"})
            elif mnem == "sub" and "rsp" in operands:
                lines.append({"line": len(lines) + 1, "code": f"    // [{addr}] allocate local frame: {operands}", "type": "comment"})
            elif mnem == "mov":
                lines.append({"line": len(lines) + 1, "code": f"    {operands.replace(',', ' =')} /* [{addr}] */;", "type": "code"})
            elif mnem == "xor" and ("eax, eax" in operands or "rax, rax" in operands):
                lines.append({"line": len(lines) + 1, "code": f"    rax_result = 0; // return status 0 (SUCCESS)", "type": "code"})
            elif mnem == "call":
                target_proc = operands
                # Check if target is a known security API
                matched_sec = next((s for s in known_sec_symbols if s.lower() in target_proc.lower()), None)
                if matched_sec:
                    sec_info = known_sec_symbols[matched_sec]
                    security_annotations.append({
                        "line": len(lines) + 1,
                        "severity": sec_info["severity"],
                        "message": f"Critical API Call: {matched_sec} ({sec_info['description']})",
                    })
                    lines.append({"line": len(lines) + 1, "code": f"    /* [!] SECURITY RISK: Invoking {matched_sec} */", "type": "risk"})
                    lines.append({"line": len(lines) + 1, "code": f"    rax_result = {matched_sec}(rdi_arg0, rsi_arg1);", "type": "call"})
                else:
                    lines.append({"line": len(lines) + 1, "code": f"    rax_result = call_proc({target_proc}) /* [{addr}] */;", "type": "call"})
            elif mnem in ("je", "jne", "jg", "jl"):
                cond_sym = "==" if mnem == "je" else ("!=" if mnem == "jne" else (">" if mnem == "jg" else "<"))
                lines.append({"line": len(lines) + 1, "code": f"    if (condition {cond_sym} 0) {{ // branch to {operands}", "type": "control"})
                in_condition = True
            elif mnem in ("jmp", "jmp short"):
                if in_condition:
                    lines.append({"line": len(lines) + 1, "code": "    }", "type": "control"})
                    in_condition = False
                lines.append({"line": len(lines) + 1, "code": f"    goto loc_{operands.replace('0x', '')};", "type": "jump"})
            elif mnem == "syscall":
                security_annotations.append({
                    "line": len(lines) + 1,
                    "severity": "HIGH",
                    "message": "Raw kernel fast syscall (bypasses libc wrapper functions)",
                })
                lines.append({"line": len(lines) + 1, "code": f"    /* [!] Fast System Call */ rax_result = kernel_syscall(rax_result, rdi_arg0, rsi_arg1);", "type": "risk"})
            elif mnem == "ret":
                if in_condition:
                    lines.append({"line": len(lines) + 1, "code": "    }", "type": "control"})
                    in_condition = False
                lines.append({"line": len(lines) + 1, "code": f"    return rax_result; // procedure return", "type": "return"})

        if in_condition:
            lines.append({"line": len(lines) + 1, "code": "    }", "type": "control"})
        lines.append({"line": len(lines) + 1, "code": "}", "type": "fn_end"})

        raw_pseudo = "\n".join(l["code"] for l in lines)
        return {
            "target": target.name,
            "format": fmt,
            "entry_offset": entry_off,
            "decompiled_lines": lines[:limit_lines],
            "raw_pseudo_code": raw_pseudo,
            "functions": functions,
            "security_annotations": security_annotations,
        }



