"""
token_manager.py
----------------
Encrypted at-rest storage for Schwab OAuth tokens.

Schwab issues:
  - access_token  (good for ~30 min, used on every API call)
  - refresh_token (good for 7 days, used to get a fresh access token)

schwab-py refreshes the access token automatically as long as the refresh
token is still valid.  Our job here is to:
  1. Persist the token blob across runs of your script so you're not
     re-doing the full OAuth login every time.
  2. Encrypt the token file with a passphrase so a casual reader who
     grabs the file off disk can't replay your tokens.

We expose two functions, `read_token()` and `write_token(token)`, that
plug directly into schwab-py's `client_from_access_functions` API.

Encryption: Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from
your passphrase via PBKDF2-HMAC-SHA256 (200k iterations).  Salt is
stored in the file header so re-derivation works across runs.

File format (all binary):
    [4 bytes magic "SWB1"]
    [16 bytes salt]
    [Fernet-encrypted JSON payload]
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import struct
from pathlib import Path
from typing import Any, Callable, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

log = logging.getLogger(__name__)

MAGIC = b"SWB1"
SALT_LEN = 16
KDF_ITERATIONS = 200_000


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key (32 url-safe-b64 bytes) from a passphrase."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    raw = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


# ---------------------------------------------------------------------------
# Low-level encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt_blob(passphrase: str, payload: bytes) -> bytes:
    salt = secrets.token_bytes(SALT_LEN)
    key = _derive_key(passphrase, salt)
    ciphertext = Fernet(key).encrypt(payload)
    return MAGIC + salt + ciphertext


def decrypt_blob(passphrase: str, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Bad token file: missing magic header")
    salt = blob[len(MAGIC) : len(MAGIC) + SALT_LEN]
    ciphertext = blob[len(MAGIC) + SALT_LEN :]
    key = _derive_key(passphrase, salt)
    try:
        return Fernet(key).decrypt(ciphertext)
    except InvalidToken as e:
        raise ValueError(
            "Failed to decrypt token file. Wrong passphrase, or the file "
            "is corrupt / from a different project."
        ) from e


# ---------------------------------------------------------------------------
# TokenManager - the thing the rest of the app uses
# ---------------------------------------------------------------------------

class TokenManager:
    def __init__(self, token_path: str | Path, passphrase: str):
        self.token_path = Path(token_path)
        self._passphrase = passphrase

    # ---- public API used by schwab-py via access functions ----

    def read_token(self) -> dict[str, Any]:
        """Return the persisted token dict, or raise FileNotFoundError."""
        if not self.token_path.exists():
            raise FileNotFoundError(
                "No saved token at " + str(self.token_path) +
                ". Run `python auth_server.py` to authenticate."
            )

        blob = self.token_path.read_bytes()

        # Backwards compat: allow loading a plain JSON token file that an
        # earlier version of this project (or schwab-py's easy_client) may
        # have left behind, then auto-upgrade to encrypted storage.
        if blob.lstrip().startswith(b"{"):
            log.warning(
                "Found plain-JSON token file at %s.  Re-encrypting on save.",
                self.token_path,
            )
            record = json.loads(blob.decode("utf-8"))
        else:
            plaintext = decrypt_blob(self._passphrase, blob)
            record = json.loads(plaintext.decode("utf-8"))

        # Normalize: if 'expires_at' is missing on the inner token (older
        # auth_server runs didn't compute it), derive it from the
        # creation_timestamp + expires_in.  Without this, authlib can't tell
        # the access token has expired and won't auto-refresh.
        tok = record.get("token")
        if isinstance(tok, dict) and "expires_at" not in tok:
            created = record.get("creation_timestamp")
            expires_in = tok.get("expires_in")
            if created is not None and expires_in is not None:
                tok["expires_at"] = int(created) + int(expires_in)

        return record

    def write_token(self, token: dict[str, Any], *args, **kwargs) -> None:
        """Persist `token` encrypted at rest.

        schwab-py may pass extra positional/keyword args (e.g. metadata about
        why the write is happening); we accept and ignore them for forward
        compatibility.
        """
        payload = json.dumps(token, indent=2, sort_keys=True).encode("utf-8")
        blob = encrypt_blob(self._passphrase, payload)
        # Write atomically: write to a temp file, then rename.
        tmp = self.token_path.with_suffix(self.token_path.suffix + ".tmp")
        tmp.write_bytes(blob)
        # On Windows, replace() will overwrite an existing target.
        os.replace(tmp, self.token_path)
        log.debug("Token written to %s (%d bytes encrypted).",
                  self.token_path, len(blob))

    # ---- convenience helpers ----

    def has_token(self) -> bool:
        return self.token_path.exists()

    def token_age_days(self) -> Optional[float]:
        """Days since the saved token was last refreshed, or None."""
        try:
            tok = self.read_token()
        except Exception:
            return None
        # schwab-py stores creation time at the top level under
        # `creation_timestamp` (seconds since epoch).
        ts = tok.get("creation_timestamp")
        if ts is None:
            return None
        import time
        return (time.time() - float(ts)) / 86400.0

    def delete_token(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()
            log.info("Deleted token file %s", self.token_path)

    # ---- factory helpers ----

    def as_access_functions(self) -> tuple[Callable[[], dict], Callable[[dict], None]]:
        """Return (read_func, write_func) for schwab-py's
        `client_from_access_functions`.
        """
        return self.read_token, self.write_token
