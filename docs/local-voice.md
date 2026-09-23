# Local Voice

Coven voice input is local-only. The browser/WebView records microphone audio, encodes a bounded 16 kHz mono WAV in the UI, and sends it to the authenticated loopback service. The service validates the WAV, checks a local `whisper-server` runtime and a verified model file, then turns the transcript into either an explicit local command or an editable draft.

There is no cloud speech fallback. `voice.allowApiTranscription` and `voice.allowApiSpeech` must remain `false`; configuration loading rejects either value when set to `true`.

## Runtime Layout

Default Windows locations:

```text
%LOCALAPPDATA%\Coven\voice\runtime\whisper-server.exe
%LOCALAPPDATA%\Coven\voice\models\ggml-base.en-q5_1.bin
```

The paths can be overridden in `config/coven.example.json` with `voice.runtimeExecutable`, `voice.runtimeDir` and `voice.modelDir`.

The repository ships a manifest at `packaging/voice/whispercpp-runtime.json`, but it does not bundle or sign whisper.cpp binaries. Install only a reviewed Windows x64 CPU server runtime into the app-owned runtime directory.

When transcription starts, Coven launches the app-owned server on `127.0.0.1` with a random request-path prefix, posts to the private `/inference` route, and reuses that loaded model for later utterances until the app exits or the worker restarts.

## Supported Models

The default profile is `base.en-q5_1` because the official tiny/base English quantized files currently publish Q5_1 variants in the checked model card:

| Profile | File | Size | SHA1 |
| --- | --- | --- | --- |
| `base.en-q5_1` | `ggml-base.en-q5_1.bin` | 57 MiB | `d26d7ce5a1b6e57bea5d0431b9c20ae49423c94a` |
| `tiny.en-q5_1` | `ggml-tiny.en-q5_1.bin` | 31 MiB | `3fb92ec865cbbc769f08137f22470d6b66e071b6` |

`base.en-q5_0` and `tiny.en-q5_0` are reserved import-only profile names in code. They are not marked ready because this branch did not verify official distributed tiny/base Q5_0 files and pinned hashes.

## Commands

Explicit local commands execute without contacting Hermes:

- `Select Circe`
- `Show Circe's tasks`
- `Open the journal`
- `Open settings`
- `Stop speaking`

Requests that could create work are always staged for review first:

- `Circe, draft a compliance matrix from this solicitation` creates an editable Circe task draft.
- `Update this document in GovDash` creates an editable task draft with an integration hint.
- `Dictation hello there` forces literal message-draft behavior.

The user must still send the message or submit the task. A transcript sent to Hermes may leave the device through the configured Hermes/provider route.

## Acceptance Gates

Source coverage verifies command routing, WAV validation, cancellation, stale transcription results and cloud-speech rejection. Windows acceptance still requires:

- Installing a reviewed whisper.cpp Windows x64 runtime.
- Installing one of the verified model files and matching the SHA1 hash.
- Confirming WebView2 microphone permission and audio capture.
- Measuring transcription latency/accuracy on the target Dell-class hardware.
- Checking installed speech synthesis voice quality.

References:

- whisper.cpp CLI documentation: `https://github.com/ggml-org/whisper.cpp/blob/master/examples/cli/README.md`
- whisper.cpp model manifest: `https://huggingface.co/ggerganov/whisper.cpp/blob/main/README.md`
