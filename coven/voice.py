"""Voice service boundary.

The current implementation is intentionally text-first. This module exposes
structured capability information so the UI can be honest until a local or API
transcriber is configured and verified on Windows/WebView2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VoiceStatus:
    recording: str = "browser-permission-required"
    transcription: str = "unconfigured"
    speech: str = "unverified"
    notes: tuple[str, ...] = (
        "Push-to-talk UI is disabled until a transcriber is configured.",
        "Temporary audio retention is disabled by default.",
        "Installed Windows voice enumeration must be verified in the desktop shell.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recording": self.recording,
            "transcription": self.transcription,
            "speech": self.speech,
            "notes": list(self.notes),
        }


class VoiceService:
    def status(self) -> dict[str, Any]:
        return VoiceStatus().to_dict()
