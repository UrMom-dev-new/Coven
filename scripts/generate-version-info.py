"""Generate PyInstaller Windows version metadata from VERSION."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
match = re.match(r"^(\d+)\.(\d+)\.(\d+)", VERSION)
if not match:
    raise SystemExit(f"VERSION must begin with major.minor.patch, got {VERSION!r}")
major, minor, patch = (int(part) for part in match.groups())
file_version = f"{major}.{minor}.{patch}.0"

content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'HermesAvatar'),
          StringStruct('FileDescription', 'Coven Agent Workspace'),
          StringStruct('FileVersion', '{file_version}'),
          StringStruct('InternalName', 'Coven'),
          StringStruct('OriginalFilename', 'Coven.exe'),
          StringStruct('ProductName', 'Coven Agent Workspace'),
          StringStruct('ProductVersion', '{VERSION}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

(ROOT / "packaging" / "version_info.txt").write_text(content, encoding="utf-8")
print(f"Generated packaging/version_info.txt for {VERSION}")
