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
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


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
