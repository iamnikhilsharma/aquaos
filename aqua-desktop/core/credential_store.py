"""Lock-screen credential store for AquaOS.

Security design notes
---------------------
- Passwords are persisted ONLY as salted PBKDF2-HMAC-SHA256 credentials in a
  dedicated `credentials.json` inside the AquaOS config directory. They never
  pass through `AquaConfig` (whose `as_dict()` is serialized verbatim by
  `/api/state` and `/api/settings/get`), so no hash material is ever exposed by
  an API response.
- `set_password()` never stores the plaintext; `verify_password()` recomputes
  the digest with the stored salt and compares in constant time.
- Credentials must be set by a first-run flow through the backend; there is no
  default credential and none is ever shipped in UI source.
- Verification failures are safe-fail: any malformed or unknown-algorithm
  stored credential simply never matches (no crash, no exception path opened
  to an attacker-supplied store file).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 72
SALT_BYTES = 16

# Sanity bounds for injected iteration counts (the DEFAULT stays at the OWASP-
# recommended 600k; the low floor only allows fast test/injection hooks — the
# backend always sets credentials through `set_password` -> DEFAULT_ITERATIONS)
_MIN_ITERATIONS = 100
_MAX_ITERATIONS = 10_000_000


def default_credentials_path() -> Path:
    """`credentials.json` next to settings.json (honours AQUAOS_CONFIG_DIR)."""
    config_dir = Path(os.environ.get("AQUAOS_CONFIG_DIR", Path.home() / ".config" / "aquaos"))
    return config_dir / "credentials.json"


def validate_password(raw: Any, *, field: str = "password") -> str:
    """Validate a plaintext password and return it unchanged.

    Raises ValueError for non-string values or lengths outside
    [MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH]. Exact characters are preserved
    (no stripping/normalisation) — credentials must match byte-for-byte.
    """
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be a string")
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"{field} must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(raw) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"{field} must be at most {MAX_PASSWORD_LENGTH} characters")
    return raw


def hash_password(password: str, *, salt_bytes: Optional[bytes] = None, iterations: Optional[int] = None) -> Dict[str, Any]:
    """Compute a salted PBKDF2-HMAC-SHA256 credential record (never persists anything).

    The returned dict carries only derived material: algorithm, iteration count,
    random salt (hex) and digest (hex). `salt_bytes`/`iterations` are injectable
    so verification recomputes with the stored salt and tests can lower the cost.
    """
    if salt_bytes is None:
        salt_bytes = secrets.token_bytes(SALT_BYTES)
    elif len(salt_bytes) < SALT_BYTES:
        raise ValueError("salt must be at least 16 bytes")
    if iterations is None:
        iterations = DEFAULT_ITERATIONS
    elif not isinstance(iterations, int) or not _MIN_ITERATIONS <= iterations <= _MAX_ITERATIONS:
        raise ValueError(f"iterations must be an int in [{_MIN_ITERATIONS}, {_MAX_ITERATIONS}]")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return {
        "algorithm": ALGORITHM,
        "iterations": iterations,
        "salt_hex": salt_bytes.hex(),
        "hash_hex": digest.hex(),
    }


def credential_matches(password: str, credential: Any) -> bool:
    """Constant-time verification of `password` against a stored credential record.

    Malformed records, wrong algorithms, non-hex fields and out-of-range
    iteration counts are all treated as "no match" — never an exception.
    """
    if not isinstance(password, str) or not isinstance(credential, dict):
        return False
    if credential.get("algorithm") != ALGORITHM:
        return False
    try:
        salt_hex = credential["salt_hex"]
        hash_hex = credential["hash_hex"]
        iterations = credential["iterations"]
        if not isinstance(salt_hex, str) or not isinstance(hash_hex, str) or not isinstance(iterations, int):
            return False
        salt = bytes.fromhex(salt_hex)
        stored = bytes.fromhex(hash_hex)
        if len(salt) < SALT_BYTES or len(stored) != hashlib.sha256().digest_size:
            return False
        if not _MIN_ITERATIONS <= iterations <= _MAX_ITERATIONS:
            return False
        recomputed = hash_password(password, salt_bytes=salt, iterations=iterations)
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(recomputed["hash_hex"], stored.hex())


class CredentialStore:
    """Persists one PBKDF2 credential in a dedicated JSON file (atomic writes)."""

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self.store_path = Path(store_path) if store_path is not None else default_credentials_path()

    def get_credential(self) -> Optional[Dict[str, Any]]:
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    def has_credential(self) -> bool:
        return self.get_credential() is not None

    def set_password(self, password: str) -> Dict[str, Any]:
        """Validate, hash, and atomically persist a new credential (plaintext never hits disk)."""
        password = validate_password(password)
        credential = hash_password(password)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.store_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(credential, indent=2), encoding="utf-8")
        tmp_path.replace(self.store_path)
        try:
            os.chmod(self.store_path, 0o600)
        except OSError:
            pass  # best-effort POSIX hardening; Windows/NTFS ignores chmod
        return credential

    def verify_password(self, password: str) -> bool:
        credential = self.get_credential()
        if credential is None:
            return False
        return credential_matches(password, credential)