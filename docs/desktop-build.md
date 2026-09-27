# Desktop Build

The Windows desktop shell uses pywebview with the EdgeChromium/WebView2 renderer and a local authenticated Coven service.

## Development Browser

```powershell
python -m coven.desktop --browser
```

The command prints a one-time unlock token and opens the authenticated browser path.

## Desktop Shell

```powershell
python -m pip install -e ".[desktop]"
python -m coven.desktop
```

On Windows, Coven checks for the WebView2 Evergreen Runtime and asks the user to install it if missing. The app keeps its state under LocalAppData.

## Desktop Self-Test

```powershell
python -m coven.desktop --self-test
```

The self-test runs in isolated demo mode, starts the local authenticated service, creates a session through the desktop auth path, checks the app shell for the approved-reference UI markers, verifies seeded Quest Journal data, validates first-run setup and voice status boundaries, and validates the approved reference image plus static cache headers. It exits without opening pywebview.

The PowerShell launcher can run the same source-tree smoke:

```powershell
.\scripts\start-coven.ps1 -Desktop -SelfTest
```

## Portable Bundle

```powershell
.\scripts\build-windows.ps1 -Clean
```

Expected output:

```text
dist\Coven\Coven.exe
```

The build script verifies that the executable, bundled public assets and approved reference image are present. It then runs:

```powershell
dist\Coven\Coven.exe --self-test
```

Use `-SkipSmoke` only when debugging a packaging failure before the executable can boot.

Hermes, Ollama, whisper.cpp runtime binaries and model files are not bundled. They are explicit onboarding prerequisites.

Local voice expects a reviewed Windows x64 `whisper-server.exe` in the configured voice runtime directory and a verified English model file in the configured voice model directory. See `docs/local-voice.md` for the manifest and privacy boundary.

## Installer

The Inno Setup script is at `packaging/installer/Coven.iss`. It expects the PyInstaller bundle to exist at `dist\Coven`.

```powershell
.\scripts\build-windows.ps1 -Clean
.\scripts\build-installer.ps1
```

Expected output:

```text
dist\installer\Coven-Setup-x64.exe
dist\installer\Coven-Setup-x64.exe.sha256
```

The GitHub Actions Windows workflow installs Inno Setup, compiles this installer, writes the SHA-256 checksum, installs the installer into a disposable per-user directory with a path containing spaces/non-ASCII text, runs the installed executable self-test, uninstalls it, and uploads `Coven-Windows-Installer` after those gates pass. That is still unattended installer smoke, not a full clean-machine interactive acceptance gate.

After both Windows jobs pass on a main push, `publish-main` downloads those exact tested artifacts. It verifies their build identity/checksums, adds a portable ZIP and a release manifest, publishes the `windows-main` rolling prerelease, and downloads the assets again to verify their bytes. It never rebuilds during promotion. Branch and pull-request runs cannot publish; superseded main runs skip publishing. Publication is serialized. This is a public beta channel, with source commit and workflow links in its release notes.

`build-info.json` is created alongside `Coven.exe` before installer compilation, so both distributions identify the same Git commit and executable hash. `Coven-build-info.json` on the release additionally records the installer and portable ZIP hashes.

Manual versioned draft releases use `.github/workflows/windows-release-draft.yml` with an explicitly selected ref. Those archival releases do not replace the current `windows-main` download.

Unsigned beta builds must be labeled unsigned. Do not ask users to disable Windows security.
