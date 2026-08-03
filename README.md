# OpenAI TTS GUI

## Description

OpenAI TTS GUI is a desktop and command-line text-to-speech client for OpenAI's API.
It splits long text into chunks, generates audio, and joins the audio automatically.
It also keeps reproducible metadata.

<img width="550" alt="image" src="https://github.com/user-attachments/assets/10e89dab-f929-4483-b942-03e8fe05d950" />

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- Generate speech with OpenAI TTS models, voices, formats, and speed controls.
- Use `gpt-4o-mini-tts` instructions and reusable presets for tone and pacing.
- Paste long scripts. The app splits them into chunks, generates audio, and joins the audio automatically with ffmpeg.
- View the live character count, chunk count, worker status, and estimated cost before running.
- Keep reproducible sidecar metadata. Copy OpenAI request IDs for support.
- Store API keys in the OS keyring, local fallback, or environment variables.
- Use the CLI.

## Requirements

- **Python 3.14** ([download](https://www.python.org/downloads/))
- **ffmpeg** ([download](https://ffmpeg.org/download.html)), which must be on PATH
- **OpenAI API key** ([get one](https://platform.openai.com/api-keys))

## Installation

### Option A: Download the installer (Windows)

Download and run `OpenAI-TTS-Setup.exe` from the [latest release](https://github.com/sm18lr88/OpenAI_TTS_GUI/releases/latest). ffmpeg must still be on PATH.

### Option B: Run from source

```bash
git clone https://github.com/sm18lr88/OpenAI_TTS_GUI.git
cd OpenAI_TTS_GUI
```

**With [uv](https://docs.astral.sh/uv/) (recommended):**

```bash
uv sync
uv run python -m openai_tts_gui
```

Or use the launch script:

```bash
# Windows
scripts\launch\run_gui.bat

# macOS / Linux
./scripts/launch/run_gui.sh
```

**With pip:**

```bash
pip install .
python -m openai_tts_gui
```

## Setting Your API Key

1. **Environment variable** (highest priority): set `OPENAI_API_KEY`
2. **GUI**: launch the app → `API Key` menu → `Set/Update API Key...` (stored in OS keyring)
3. **Custom endpoint**: set `OPENAI_BASE_URL` for self-hosted or compatible APIs

## Usage

```bash
openai-tts --in input.txt --out output.mp3 --model tts-1 --voice alloy --format mp3 --speed 1.0
openai-tts --in input.txt --out output.wav --model gpt-4o-mini-tts --voice nova --format wav --speed 1.25 --instructions "speak warmly"
openai-tts --help
openai-tts --version
```

The CLI supports the core TTS settings: `--model`, `--voice`, `--format`, `--speed`,
`--instructions`, and `--retain-files`, in addition to `--in` and `--out`.

## Development

```bash
uv sync --extra dev         # install with dev deps
make lint                    # Ruff lint/format checks and type checking
make test                    # tests (uses .pytest_tmp for temp files)
make coverage                # tests plus independent coverage thresholds
make install-hooks           # install the repository pre-commit hook
```

### Building

```bash
uv run pyinstaller --noconfirm packaging/pyinstaller/openai_tts.spec   # .exe in dist/
"C:\Program Files (x86)\NSIS\makensis.exe" packaging/windows/installer.nsi   # Windows installer in dist/
```

First, build the app bundle in `dist/OpenAI-TTS/`. Then, the NSIS step packages that directory as `dist/OpenAI-TTS-Setup.exe`.

## Project Structure

```
src/openai_tts_gui/
  config/      Settings (pure Python) + Qt theme
  core/        Text chunking, audio concat, ffmpeg, sidecar metadata
  tts/         TTS service (pure Python, no Qt dependency)
  keystore/    API key storage (keyring + encrypted file)
  presets/     Instruction preset persistence
  gui/         PyQt6 UI (main window, dialogs, worker thread, layout)
  errors.py    Domain error hierarchy
  cli.py       CLI entry point
  main.py      GUI entry point
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for module boundaries and conventions.

## Contributing

Before you open a pull request, install the development dependencies with
`uv sync --extra dev`. Then run `make lint`, `make test`, and `make coverage`. Keep core
and service modules Qt-free. Import package interfaces instead of private modules. Preserve
the compatibility contracts in [ARCHITECTURE.md](ARCHITECTURE.md).

## License

This project uses a custom attribution and honor-system commercial license. If
you use this code, give credit to "OpenAI TTS GUI by Leo Riera / sm18lr88".

Non-commercial use is encouraged. If the project helps you, gifts of any amount
are appreciated at [paypal.me/LeoRiera](https://paypal.me/LeoRiera).

Commercial use requires buying a USD $5 honor-system commercial license at
[paypal.me/LeoRiera](https://paypal.me/LeoRiera). See [LICENSE](LICENSE) for the
full terms.

## Support, Privacy, and Trust

Show appreciation at [paypal.me/LeoRiera](https://paypal.me/LeoRiera) if this
app helps you. The app does not verify PayPal donations, does not add DRM, and
does not track support clicks.

Privacy and trust notes:

The app sends text for speech generation to OpenAI or to the compatible endpoint
configured with `OPENAI_BASE_URL`. It reads API keys from `OPENAI_API_KEY`, the OS
keyring, or the local fallback file shown in the app data directory. It stores presets,
settings, logs, and sidecar metadata locally under the data path shown in `Help` -> `About`.
Delete those files to remove local app data. Sidecar files may include request IDs that help
with OpenAI support.

Release artifacts include checksum files. The public release workflow builds them. The Windows
installer supports standard-user installation and safe uninstall checks. The project tracks
Windows App Certification Kit and Microsoft Store MSI/EXE readiness. It does not claim certification
until an actual Windows SDK/App Certification Kit or Store submission report passes.

## Troubleshooting

- **ffmpeg not found**: Make sure it is on PATH. The app checks at startup.
- **API key issues**: Try setting the `OPENAI_API_KEY` environment variable directly.
- **Logs**: Check the log file path shown in `Help` → `About`.

## Tips

- Speed adjustments far from 1.0x may affect quality. For better results, use `gpt-4o-mini-tts` with instructions such as "speak slowly".
- Instruction examples at [openai.fm](https://openai.fm).
- `api_key.enc` is obfuscated, not encrypted. Prefer OS keyring or environment variables.
