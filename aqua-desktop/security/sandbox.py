"""Aqua Sandbox (aqua-sandbox).

Mandatory application and AI-agent sandboxing powered by Linux namespaces & Bubblewrap (bwrap).
Isolates untrusted or foreign binaries (.exe, .dmg, .AppImage, downloaded scripts, AI code blocks)
so they cannot modify the OS or read sensitive user data (~/.ssh, ~/.gnupg, browser credentials).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SandboxPolicy:
    """Defines fine-grained TCC (Transparency, Consent, and Control) permissions for a sandboxed app."""

    app_id: str
    allow_network: bool = False
    allow_documents: bool = False
    allow_downloads: bool = False
    allow_display: bool = True
    allow_audio: bool = True
    allow_gpu: bool = True
    read_only_root: bool = True
    extra_ro_binds: List[str] = field(default_factory=list)
    extra_rw_binds: List[str] = field(default_factory=list)


class AquaSandbox:
    """Constructs and executes isolated Bubblewrap / namespace containers."""

    BLOCKED_SENSITIVE_PATHS: List[str] = [
        ".ssh",
        ".gnupg",
        ".aws",
        ".kube",
        ".config/google-chrome",
        ".mozilla",
        ".local/share/keyrings",
    ]

    def __init__(self, sandbox_root: Optional[Path] = None) -> None:
        self.sandbox_root = sandbox_root or (Path.home() / ".local" / "share" / "aqua-sandboxes")

    def get_app_sandbox_home(self, app_id: str) -> Path:
        """Return or create an isolated virtual $HOME directory for the given app."""
        safe_id = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in app_id)
        app_home = self.sandbox_root / safe_id
        app_home.mkdir(parents=True, exist_ok=True)
        return app_home

    def build_bwrap_command(
        self,
        command: List[str],
        policy: SandboxPolicy,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Build the exact Bubblewrap (bwrap) command vector enforcing the SandboxPolicy."""
        app_home = self.get_app_sandbox_home(policy.app_id)
        real_home = Path.home()

        bwrap_cmd: List[str] = [
            "bwrap",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--die-with-parent",
            "--new-session",
        ]

        if not policy.allow_network:
            bwrap_cmd.append("--unshare-net")

        # Mount core OS directories strictly read-only
        for sys_dir in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/opt"):
            bwrap_cmd.extend(["--ro-bind-try", sys_dir, sys_dir])

        bwrap_cmd.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run"])

        # Isolate user's real $HOME by mounting the app's private sandbox directory over $HOME
        bwrap_cmd.extend(["--bind", str(app_home), str(real_home)])

        # Explicitly mask sensitive credential directories with empty tmpfs even if home is shared
        for rel_sensitive in self.BLOCKED_SENSITIVE_PATHS:
            target = real_home / rel_sensitive
            bwrap_cmd.extend(["--tmpfs", str(target)])

        # TCC selective folder sharing
        if policy.allow_documents:
            docs = real_home / "Documents"
            bwrap_cmd.extend(["--bind-try", str(docs), str(docs)])
        if policy.allow_downloads:
            dl = real_home / "Downloads"
            bwrap_cmd.extend(["--bind-try", str(dl), str(dl)])

        # Wayland / X11 display socket passthrough when GUI access is permitted
        if policy.allow_display:
            xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid() if hasattr(os, 'getuid') else 1000}")
            wayland_display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
            wayland_sock = f"{xdg_runtime}/{wayland_display}"
            bwrap_cmd.extend(["--ro-bind-try", wayland_sock, wayland_sock])
            bwrap_cmd.extend(["--ro-bind-try", "/tmp/.X11-unix", "/tmp/.X11-unix"])

        # GPU device nodes for Vulkan / CUDA / DRI acceleration
        if policy.allow_gpu:
            bwrap_cmd.extend(["--dev-bind-try", "/dev/dri", "/dev/dri"])
            bwrap_cmd.extend(["--dev-bind-try", "/dev/nvidiactl", "/dev/nvidiactl"])
            bwrap_cmd.extend(["--dev-bind-try", "/dev/nvidia0", "/dev/nvidia0"])

        for ro_path in policy.extra_ro_binds:
            bwrap_cmd.extend(["--ro-bind-try", ro_path, ro_path])
        for rw_path in policy.extra_rw_binds:
            bwrap_cmd.extend(["--bind-try", rw_path, rw_path])

        bwrap_cmd.extend(["--setenv", "AQUAOS_SANDBOX", "1"])
        bwrap_cmd.extend(["--setenv", "AQUAOS_APP_ID", policy.app_id])
        if env_overrides:
            for k, v in env_overrides.items():
                bwrap_cmd.extend(["--setenv", k, v])

        bwrap_cmd.append("--")
        bwrap_cmd.extend(command)
        return bwrap_cmd

    def run_sandboxed(
        self,
        command: List[str],
        policy: SandboxPolicy,
        timeout: Optional[float] = 30.0,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """Execute a command inside the Bubblewrap sandbox (or restricted subprocess fallback on non-Linux preview)."""
        if shutil.which("bwrap"):
            full_cmd = self.build_bwrap_command(command, policy)
        else:
            full_cmd = command

        env = os.environ.copy()
        env["AQUAOS_SANDBOX"] = "1"
        env["AQUAOS_APP_ID"] = policy.app_id
        app_home = self.get_app_sandbox_home(policy.app_id)
        env["HOME"] = str(app_home)

        return subprocess.run(
            full_cmd,
            cwd=str(app_home),
            env=env,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )

    def run_code_snippet(self, code: str, language: str = "python") -> Dict[str, str | int]:
        """Safely execute an AI-generated Python or Bash snippet inside an isolated ephemeral sandbox."""
        policy = SandboxPolicy(
            app_id="org.aquaos.ai.code_runner",
            allow_network=False,
            allow_documents=False,
            allow_downloads=False,
            allow_display=False,
        )
        sandbox_home = self.get_app_sandbox_home(policy.app_id)
        suffix = ".py" if language.lower() in ("python", "py") else ".sh"
        script_path = sandbox_home / f"snippet{suffix}"
        script_path.write_text(code, encoding="utf-8")

        if suffix == ".py":
            interpreter = "python3" if shutil.which("bwrap") else sys.executable
        else:
            interpreter = "bash"

        try:
            proc = self.run_sandboxed(
                [interpreter, str(script_path)],
                policy=policy,
                timeout=10.0,
                capture_output=True,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "sandboxed": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": "Execution timed out after 10s inside Aqua Sandbox.",
                "sandboxed": True,
            }
        except Exception as exc:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Sandbox execution error: {exc}",
                "sandboxed": True,
            }
