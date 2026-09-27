# Connect Hermes and set up voice

Open **Settings → Guided setup** in Coven. Configuration and installed voice files live in Coven’s user data, outside its application folder, and survive application updates.

## Use a separate Hermes runtime

1. **Browse** to `hermes.exe` in the separate installation. You can also paste its installation folder; Coven recognizes `venv` and `.venv` layouts.
2. To start it from Coven, select the existing Hermes **data folder** for this project (the folder containing its `config.yaml` and `.env`). This is distinct from its program folder. Its provider credentials and tool configuration remain managed by Hermes.
3. Keep the local server address `http://127.0.0.1:8642`, or enter the port for this Hermes instance. Only loopback addresses are accepted.
4. If Hermes is already running, enter its **server key** and choose **Save & test connection**. This key is different from an OpenAI API key.
5. Alternatively, choose **Start selected Hermes**. Coven starts `hermes gateway` in the background with the selected data folder and enables its local API. It generates a server key if needed. Choose **Test saved connection** after startup.

The key is protected with user-scoped Windows DPAPI; it is never returned to the renderer. A blank key field preserves the saved key. Changing the address requires entering the key for the new endpoint. Coven does not install Hermes, modify its files, or stop a server started elsewhere. A runtime started from Coven is stopped when Coven closes; use **Start selected Hermes** again next time. Stop it using **Stop Hermes started here** before changing its paths.

Connection success requires an authenticated Hermes API with run submission and run status capabilities, not just a responding health endpoint. Provider readiness is reported separately by Hermes. Configure the model/provider in that runtime; the optional Coven credential-storage form does not configure an external runtime. Finish or cancel pending live work before switching runtimes. Different runtime selections use separate remote chat-session identities.

## Install local speech recognition

1. Choose **Standard** (57 MB English model) or **Lightweight** (31 MB, faster on modest CPUs).
2. Click **Install local voice**. Windows x64 setup downloads the pinned CPU whisper.cpp runtime and model, verifies their hashes, then activates them. Allow 400 MB free disk space. Progress and cancellation appear in Settings.
3. Click **Find microphones**, allow Windows microphone access, select a device, and **Save voice settings**. The system default also works without enumeration.
4. Click **Test microphone**, say a short sentence, then **Finish test**. A successful test displays the recognized text without creating tasks, changing the view, or sending anything to Hermes.

After setup, transcription is local and does not need an API key or network. Sending a transcript to Hermes can use that runtime’s configured cloud provider. Windows microphone permission is still required.

To use existing components, expand **Use an existing whisper.cpp installation**, browse to `whisper-server.exe`, and select the folder containing the exact model selected above (`ggml-base.en-q5_1.bin` or `ggml-tiny.en-q5_1.bin`). Keep the runtime’s DLLs beside its executable. Save and test. Other platforms use this manual path; automatic installation is Windows x64 only.

Reinstall from the same button to repair components. Failed or cancelled downloads preserve the previous setup. Downloads use new directories so an active runtime is never overwritten. Voice settings cannot change during a recording or transcription. Old installed versions are retained; automatic cleanup is not implemented.

If a test fails, check the selected device, Windows microphone permissions, the model profile, and whether `whisper-server.exe` can run on the computer’s CPU. “Voice files are ready” indicates verified files; only the microphone test verifies the capture-to-transcript path on that machine.
