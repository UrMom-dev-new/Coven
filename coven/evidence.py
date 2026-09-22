"""Trusted artifact inspection for model-reported outputs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def validate_artifacts(artifacts: list[Any], *, allowed_roots: tuple[Path, ...]) -> list[dict[str, Any]]:
    """Inspect artifact claims without trusting model-returned existence flags."""

    validated: list[dict[str, Any]] = []
    for raw in artifacts[:20]:
        claim = _claim_from(raw)
        record: dict[str, Any] = {
            "state": "reported",
            "claim": claim,
            "path": claim.get("path", ""),
            "name": claim.get("name", ""),
            "notes": [],
        }
        path = claim.get("path")
        if not path:
            record["notes"].append("No local path was supplied for inspection.")
            validated.append(record)
            continue
        if not allowed_roots:
            record["notes"].append("No permitted workspace roots are configured for local artifact inspection.")
            validated.append(record)
            continue
        try:
            resolved = Path(path).expanduser().resolve()
        except OSError as exc:
            record["notes"].append(f"Path could not be resolved: {exc}")
            validated.append(record)
            continue
        record["path"] = str(resolved)
        if not _is_allowed(resolved, allowed_roots):
            record["notes"].append("Path is outside configured permitted workspace roots.")
            validated.append(record)
            continue
        if not resolved.exists() or not resolved.is_file():
            record["notes"].append("File was not found during independent inspection.")
            validated.append(record)
            continue
        stat = resolved.stat()
        digest = _sha256(resolved)
        record.update(
            {
                "state": "inspected",
                "size": stat.st_size,
                "sha256": digest,
                "suffix": resolved.suffix.lower(),
            }
        )
        expected_hash = claim.get("expectedSha256") or claim.get("sha256")
        expected_size = claim.get("expectedSize") or claim.get("size")
        if expected_hash or expected_size is not None:
            hash_ok = not expected_hash or str(expected_hash).lower() == digest
            try:
                size_ok = expected_size is None or int(expected_size) == stat.st_size
            except (TypeError, ValueError):
                size_ok = False
            if hash_ok and size_ok:
                record["state"] = "validated"
            else:
                record["notes"].append("Inspected file did not match expected hash or size.")
        validated.append(record)
    return validated


def _claim_from(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return {"path": raw}
    if isinstance(raw, dict):
        return dict(raw)
    return {"name": str(raw)}


def _is_allowed(path: Path, allowed_roots: tuple[Path, ...]) -> bool:
    if not allowed_roots:
        return False
    for root in allowed_roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
