"""Publish tested artifacts from this main run; never rebuild during promotion."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


TAG = "windows-main"
MARKER = "<!-- coven-main-build -->"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_assets(root, output, commit, run_id, repository):
    bundle = root / "portable" / "Coven"
    installer = root / "installer" / "Coven-Setup-x64.exe"
    info = json.loads((bundle / "build-info.json").read_text(encoding="utf-8-sig"))
    if (info["commit"] != commit or str(info["runId"]) != str(run_id)
            or info["repository"] != repository or sha256(bundle / "Coven.exe") != info["executableSha256"]):
        raise ValueError("Portable artifact provenance does not match this main workflow run.")
    recorded = (installer.parent / (installer.name + ".sha256")).read_text().split()
    if recorded != [sha256(installer), installer.name]:
        raise ValueError("Installer checksum does not match the tested artifact.")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(installer, output / installer.name)
    portable = output / "Coven-Portable-x64.zip"
    with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(bundle.parent).as_posix())
    assets = [output / installer.name, portable]
    hashes = {path.name: sha256(path) for path in assets}
    for path in list(assets):
        checksum = output / (path.name + ".sha256")
        checksum.write_text(f"{hashes[path.name]}  {path.name}\n", encoding="ascii")
        assets.append(checksum)
    manifest = output / "Coven-build-info.json"
    manifest.write_text(json.dumps({**info, "artifacts": hashes,
        "workflowUrl": f"https://github.com/{repository}/actions/runs/{run_id}"}, indent=2) + "\n", encoding="utf-8")
    assets.append(manifest)
    return info, assets


def gh(*args, check=True):
    return subprocess.run(["gh", *args], text=True, capture_output=True, check=check)


def main():
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Only a main push can publish these downloads.")
    repo, commit, run_id = (os.environ[key] for key in ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID"))
    current = json.loads(gh("api", f"repos/{repo}/git/ref/heads/main").stdout)["object"]["sha"]
    if current != commit:
        print("A newer main commit exists. This superseded run will not publish.")
        return
    info, assets = prepare_assets(Path("release-input"), Path("release-output"), commit, run_id, repo)
    notes = Path("release-output/notes.md")
    notes.write_text(f"""{MARKER}
Coven {info['version']} — Windows x64 beta built from current main.

Source commit: `{commit}`
Verified workflow: https://github.com/{repo}/actions/runs/{run_id}

Download **Coven-Setup-x64.exe** and double-click it. No command line is needed.
For portable use, extract **Coven-Portable-x64.zip** completely and open `Coven/Coven.exe`; keep its accompanying files.

Includes easier Hermes/voice setup, Office app links, and a persistent GovDash browser profile.
Office/GovDash agent automation and real-account acceptance remain separate work.

The Windows test suite, Edge Settings/layout checks, real CPU transcription,
packaged browser persistence/forget checks, and installer install/self-test/uninstall passed.
Checksums and `Coven-build-info.json` identify these exact downloads. The installed
and portable app folders also contain `build-info.json` with the source commit.

Unsigned beta: Windows may show a reputation warning. Live account/MFA, microphone,
and interactive acceptance on the target PC remain to be checked.

This rolling prerelease is updated after successful main builds. Older versioned
releases remain historical snapshots and are not the current download.
""", encoding="utf-8")
    existing = gh("api", f"repos/{repo}/releases/tags/{TAG}", check=False)
    if existing.returncode:
        if "HTTP 404" not in existing.stderr:
            raise RuntimeError("Unable to inspect the current Windows release.")
        tag = gh("api", f"repos/{repo}/git/ref/tags/{TAG}", check=False)
        if tag.returncode:
            if "HTTP 404" not in tag.stderr:
                raise RuntimeError("Unable to inspect the Windows release tag.")
            gh("api", f"repos/{repo}/git/refs", "--method", "POST", "-f", f"ref=refs/tags/{TAG}", "-f", f"sha={commit}")
        elif json.loads(tag.stdout)["object"]["sha"] != commit:
            raise RuntimeError("An unrelated windows-main tag already exists.")
        gh("release", "create", TAG, "--repo", repo, "--target", commit,
           "--title", f"Coven {info['version']} — current Windows build", "--notes-file", str(notes), "--draft", "--prerelease")
    elif MARKER not in (json.loads(existing.stdout).get("body") or ""):
        raise RuntimeError("Refusing to replace an unrelated release at windows-main.")
    gh("release", "upload", TAG, *(str(path) for path in assets), "--repo", repo, "--clobber")
    # Read the uploaded bytes back before reporting a successful publication.
    with tempfile.TemporaryDirectory(prefix="coven-release-verify-") as directory:
        gh("release", "download", TAG, "--repo", repo, "--dir", directory, "--pattern", "Coven-*")
        for path in assets:
            if sha256(Path(directory) / path.name) != sha256(path):
                raise RuntimeError(f"Published asset verification failed: {path.name}")
    gh("api", f"repos/{repo}/git/refs/tags/{TAG}", "--method", "PATCH", "-f", f"sha={commit}", "-F", "force=true")
    gh("release", "edit", TAG, "--repo", repo, "--target", commit, "--draft=false", "--prerelease",
       "--title", f"Coven {info['version']} — current Windows build", "--notes-file", str(notes), "--latest=false")
    print(f"Verified Windows downloads from {commit}: https://github.com/{repo}/releases/tag/{TAG}")


if __name__ == "__main__":
    main()
