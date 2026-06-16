# Audio2Text

> **Disclaimer:** This README is auto-translated. The author's native language is Ukrainian.
> For the original version, see [README.md](README.md).

Audio transcription to text using WhisperX with alignment and speaker diarization.

## Features

- **WhisperX** — fast transcription with CTranslate2
- **Alignment** — precise timestamps via wav2vec2
- **Diarization** — who speaks when (pyannote.audio)
- **Chunked processing** — parallel processing of long files
- **Resume** — interrupted transcription can be continued
- **GUI** — graphical interface (ttkbootstrap)
- **CLI** — command line
- **Profiles** — saved configuration presets (YAML)
- **File Registry** — quick access to external audio files
- **Cache management** — view/delete cached models

## Installation

```bash
# Python 3.10+
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Or manually:
pip install torch==2.3.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cpu
pip install whisperx ttkbootstrap platformdirs pyyaml python-dotenv sounddevice
```

> **Important:** Use exactly `torch==2.3.0` / `torchaudio==2.3.0` — newer versions are incompatible with whisperx.

## Usage

### GUI

```bash
python main.py
```

Tabs:

- **Transcription** — file selection, token, profile, run + log
- **Log** — progress and transcription output
- **Settings** — theme, auto-download models, profiles, file registry, model cache

### CLI

```bash
# Transcribe a file
python main.py file path/to/audio.m4a

# With profile and model selection
python main.py file audio.m4a --model_name large-v3 --language uk

# Split into chunks for parallel processing
python main.py file audio.m4a --chunk_minutes 10 --max_workers 4

# Skip download confirmation prompt
python main.py file audio.m4a -y

# Interactive picker
python main.py pick
```

### Profiles

Profiles are stored in `~/.config/audio2text/profiles.yaml`.
Built-in profiles are copied there on first run.

Example profile:

```yaml
file:
  large-v3:
    full_uk:
      description: "Full transcription (large-v3) + diarization"
      language: uk
      align: true
      diarize: true
```

**Profile fields:**

| Field           | Type | Description                      |
|-----------------|------|----------------------------------|
| `description`   | str  | Description (shown in GUI)       |
| `language`      | str  | Language code (uk, en, pl, …)    |
| `align`         | bool | Timestamp alignment              |
| `diarize`       | bool | Speaker diarization              |
| `model`         | str  | Model size (large-v3, base, …)   |
| `chunk_minutes` | int  | Chunk split (0 = disabled)       |
| `max_workers`   | int  | Parallel worker threads          |
| `clean_filter`  | str  | Audio filter: full / light / off |

### HuggingFace Token

Diarization requires a HuggingFace token:

1. Register at [huggingface.co](https://huggingface.co)
2. Accept model terms: [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Create a token: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

The token can be saved via GUI or set as `HF_TOKEN` in `.env`.

### External File Registry

Files outside `Audio/` can be added to the registry — they appear in the quick-select
list (GUI: combobox on the transcription tab; CLI: `python main.py pick`).

The registry is stored in `~/.local/share/audio2text/external_registry.json`.

## Directory Structure

```
~/.cache/audio2text/          # Transcription working directories
~/.cache/whisper/             # Whisper model cache (.pt)
~/.cache/huggingface/hub/     # CTranslate2/HF model cache
~/.config/audio2text/         # Settings
  ├── profiles.yaml           # Transcription profiles
  ├── settings.json           # Token, theme
  └── token_storage_mode.txt  # Token storage mode
~/.local/share/audio2text/    # Data
  ├── Audio/                  # Default audio directory
  └── external_registry.json  # External file registry
```

## Credits

- [WhisperX](https://github.com/m-bain/whisperX) — transcription + align + diarization
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) — diarization
- [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) — GUI theme
