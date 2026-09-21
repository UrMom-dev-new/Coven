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

The self-test runs in isolated demo mode, starts the local authenticated service, creates a session through the desktop auth path, checks the app shell for the approved-reference UI markers, verifies seeded Quest Journal data, and validates the approved reference image plus static cache headers. It exits without opening pywebview.

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

Hermes, Ollama and model files are not bundled. They are explicit onboarding prerequisites.

## Installer

The Inno Setup script is at `packaging/installer/Coven.iss`. It expects the PyInstaller bundle to exist at `dist\Coven`.

```powershell
.\scripts\build-windows.ps1 -Clean
.\scripts\build-installer.ps1
```

Expected output:

```text
dist\installer\CovenSetup-0.2.0-beta.exe
```

The GitHub Actions Windows workflow installs Inno Setup, compiles this installer, and uploads it as `Coven-Windows-Installer` after the packaged executable self-test succeeds. That is an installer compile gate, not a clean-machine install/upgrade/uninstall acceptance gate.

Unsigned beta builds must be labeled unsigned. Do not ask users to disable Windows security.
