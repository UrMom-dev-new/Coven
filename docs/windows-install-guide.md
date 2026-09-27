# Windows Install Guide

The [current Windows beta](https://github.com/UrMom-dev-new/Coven/releases/tag/windows-main) is distributed as one installer:

```text
Coven-Setup-x64.exe
Coven-Setup-x64.exe.sha256
```

Download [Coven-Setup-x64.exe](https://github.com/UrMom-dev-new/Coven/releases/download/windows-main/Coven-Setup-x64.exe) from this public repository. No GitHub login or command line is required for the released installer. Workflow artifacts are for development; use the release download for normal installation.

The `windows-main` prerelease contains the latest successfully tested main build. Its notes and `Coven-build-info.json` give the exact source commit, workflow run, and SHA-256 checksums. Older versioned releases remain historical snapshots. The installed application folder contains the matching `build-info.json`.

For portable use, download `Coven-Portable-x64.zip`, extract the entire ZIP, and double-click `Coven/Coven.exe`. Keep its accompanying files; copying only the executable will not work.

## Install

1. Open the approved GitHub release or workflow artifact link.
2. Download `Coven-Setup-x64.exe` and `Coven-Setup-x64.exe.sha256`.
3. Double-click `Coven-Setup-x64.exe`.
4. Install for the current user.
5. Keep `Launch Coven` selected.

The installer writes application files under LocalAppData Programs. User settings, credentials, conversations, models, and work folders stay outside the installed application directory so upgrades do not overwrite them.

Unsigned beta builds may show a Windows reputation warning. The normal path is to use a signed build once publisher credentials are configured; do not ask users to disable Windows security.

## First Run

Open `Settings -> Guided setup`.

1. Check this computer: verifies the supported Windows/runtime boundary and reports disk space.
2. Connect your AI provider: enter your own API credential and model. The renderer sends the key once to the authenticated local backend; it is stored with user-scoped protection and is not written to setup JSON, logs, browser storage, or diagnostics.
3. Choose your work folder: use the desktop folder picker when running the installed app, or paste a folder path in browser fallback mode. Coven verifies that the folder exists and is writable.
4. Enable local voice: optional. Text chat can be completed before voice components are installed.
5. Finish setup: only marks setup complete when live prerequisites and workspace selection are ready, or when the user explicitly chooses Explore demo.

`Explore demo` opens isolated demo data and must not be counted as live Hermes proof.

## Components

- WebView2: Coven checks the Microsoft Evergreen runtime before creating the web window. If missing, the user sees a native Windows notice before the app exits.
- Hermes: Coven records the pinned upstream release target `v2026.9.21` and app-owned runtime location. Native runtime installation and live API verification still require Windows acceptance.
- Voice: Coven expects `whisper-server.exe` plus verified `base.en-q5_1` or `tiny.en-q5_1` model files. Voice remains optional for text setup.

## Repair And Updates

In `Settings -> Guided setup`:

- `Repair components` marks app-owned components for verification without deleting work.
- `Check updates` opens the current Windows beta release page.
- `Export diagnostics` writes a redacted local support bundle with readiness and version data only. It excludes secrets, conversations, raw audio, and business documents.

## Uninstall

Use Windows Apps settings or the Start menu uninstaller. Ordinary uninstall removes application files only. User work and app data are preserved unless a future explicit data-removal option is selected.

## Acceptance Not Yet Proven Here

The following require a clean Windows x64 VM or real PC:

- Install and launch by clicking only.
- Complete setup with a real provider credential.
- Start the app-owned Hermes API and receive a live provider-backed response.
- Assign a task and independently verify an output artifact.
- Install local voice through the UI and transcribe a microphone recording.
- Upgrade, uninstall, and reinstall while preserving user data.
- Exercise missing WebView2, denied microphone permission, invalid credentials, unavailable network, and interrupted component installation.
