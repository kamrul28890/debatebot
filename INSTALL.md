# Installation Guide

This guide is for a clean setup of `debate_night`.

## 1. Python and venv

Use Python 3.10.

Windows PowerShell:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
```

## 2. Install packages

```bash
python -m pip install -r requirements.txt
```

Core packages expected:
- `PyQt6`
- `openai`
- `azure-cognitiveservices-speech`
- `sentence-transformers`
- `TTS`
- `torch`
- `torchaudio`
- `pygame`
- `sounddevice`
- `soundfile`

## 3. Configure credentials

```bash
copy keys_template.py keys.py    # Windows
# or
cp keys_template.py keys.py      # macOS/Linux
```

Set valid keys in `keys.py`.

## 4. Add required voice references

Add these files:
- `data/raw_trump/ref.wav`
- `data/raw_biden/ref.wav`
- `data/raw_siskind/ref.wav`

Use clean speech, 10-30 seconds, minimal noise/music.

## 5. Optional assets

- Crowd sounds: `python scripts/download_sounds.py`
- Speech corpus refresh:
  - `python src/utils/scraper_trump.py`
  - `python src/utils/scraper_biden.py`

## 6. Validate install

```bash
python -m compileall -q src
python -c "from src.audio.xtts_speaker import XTTS_AVAILABLE; print('XTTS_AVAILABLE=', XTTS_AVAILABLE)"
```

If XTTS is unavailable, verify:
- `python -m pip show TTS torch torchaudio`

## 7. Run app

Windows PowerShell:
```powershell
$env:PERSONA="trump"
python src/main.py
```

Switch persona:
```powershell
$env:PERSONA="biden"
python src/main.py
```

## Audio Notes

- First XTTS run downloads model files and may take time.
- CPU synthesis can be slow for long lines.
- If there is no output sound, verify system output device and volume.

