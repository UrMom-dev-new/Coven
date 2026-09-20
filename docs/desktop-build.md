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

## Portable Bundle

```powershell
.\scripts\build-windows.ps1 -Clean
```

Expected output:

```text
dist\Coven\Coven.exe
```

Hermes, Ollama and model files are not bundled. They are explicit onboarding prerequisites.

## Installer

The Inno Setup script is at `packaging/installer/Coven.iss`. It expects the PyInstaller bundle to exist at `dist\Coven`.

Unsigned beta builds must be labeled unsigned. Do not ask users to disable Windows security.
