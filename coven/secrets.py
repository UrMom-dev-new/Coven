"""User-scoped secret storage for setup credentials.

On Windows this uses DPAPI through CryptProtectData/CryptUnprotectData and
stores only encrypted blobs in Coven's app data. Non-Windows development builds
use a restricted local file fallback so tests can run without pretending it is
the shipping Windows protection boundary.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import stat
from typing import Any


class SecretStoreError(RuntimeError):
    """Raised when a secret cannot be saved or read."""


class SecretStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "secrets.json"

    def put(self, name: str, secret: str) -> None:
        if not name or any(char in name for char in "\\/\r\n"):
            raise SecretStoreError("Secret name is invalid.")
        if not secret:
            raise SecretStoreError("Secret value is required.")
        self.root.mkdir(parents=True, exist_ok=True)
        payload = self._read()
        payload[name] = _protect(secret)
        _atomic_write_json(self.path, payload)
        try:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def get(self, name: str) -> str:
        payload = self._read()
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise SecretStoreError("Secret was not found.")
        return _unprotect(value)

    def delete(self, name: str) -> None:
        payload = self._read()
        payload.pop(name, None)
        _atomic_write_json(self.path, payload)

    def has(self, name: str) -> bool:
        payload = self._read()
        return isinstance(payload.get(name), str) and bool(payload.get(name))

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError) as exc:
            raise SecretStoreError("Secret store could not be read.") from exc
        return data if isinstance(data, dict) else {}


def _protect(secret: str) -> str:
    raw = secret.encode("utf-8")
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_crypt_protect_data(raw)).decode("ascii")
    return "dev:" + base64.b64encode(raw).decode("ascii")


def _unprotect(value: str) -> str:
    if value.startswith("dpapi:"):
        raw = _crypt_unprotect_data(base64.b64decode(value.removeprefix("dpapi:")))
        return raw.decode("utf-8")
    if value.startswith("dev:"):
        return base64.b64decode(value.removeprefix("dev:")).decode("utf-8")
    raise SecretStoreError("Secret format is unsupported.")


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array[Any]]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _crypt_protect_data(data: bytes) -> bytes:  # pragma: no cover - Windows only
    blob_in, _buffer = _blob_from_bytes(data)
    blob_out = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "Coven user secret",
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise SecretStoreError("Windows DPAPI could not protect the secret.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _crypt_unprotect_data(data: bytes) -> bytes:  # pragma: no cover - Windows only
    blob_in, _buffer = _blob_from_bytes(data)
    blob_out = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise SecretStoreError("Windows DPAPI could not read the secret.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
