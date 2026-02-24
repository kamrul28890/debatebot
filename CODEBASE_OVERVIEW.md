# Debate Night — Codebase Overview

## Project Summary

**Debate Night** is an AI-powered presidential debate simulator built for Purdue ECE course (Spring 2026). Two AI personas (Trump or Biden) engage in a live debate with:
- Speech-to-text (Azure STT)
- GPT-4 response generation with RAG (Retrieval-Augmented Generation)
- Text-to-speech (Azure TTS or Coqui XTTS voice cloning)
- PyQt6 GUI with South Park cartoon aesthetic
- Professor Siskind moderator with scripted interjections
- Fact-checking system with sound effects
- Crowd reactions and echo suppression

---

## Architecture

### Core Components

#### 1. **Brain Module** (`src/brain/`)
- **`model.py`** — `DebateBrain` class
  - Uses Azure OpenAI (GPT-4) for response generation
  - Loads persona-specific character prompts from `personas/` directory
  - Manages conversation history (last 8 turns)
  - Auto-rotates debate topics every 4 turns
  - Tracks turn count and topic progression
  - **RAG Integration**: Injects relevant historical quotes into context
  
- **`rag.py`** — `RAGRetriever` class (Retrieval-Augmented Generation)
  - Loads scraped speech data from `data/raw_{persona}/speeches.txt`
  - Embeds all sentences using `sentence-transformers` (all-MiniLM-L6-v2 model)
  - Retrieves top-K semantically similar quotes at query time using cosine similarity
  - Runs entirely locally (no API cost)
  - Graceful degradation: if RAG fails for ANY reason, silently returns [] and continues
  - Cache built once at startup in `.rag_cache/`
  
- **`fact_checker.py`** — `FactChecker` class
  - Async fact-checking of opponent claims
  - Returns verdict: TRUE, FALSE, MISLEADING, or UNVERIFIABLE
  - Triggers sound effects based on verdict
  
- **`personas/`** — Character prompt files
  - `trump.txt` — Detailed Trump persona (speech patterns, phrases, debate behavior, positions)
  - `biden.txt` — Detailed Biden persona

#### 2. **Audio Module** (`src/audio/`)
- **`listener.py`** — `DebateListener` class
  - Azure Speech-to-Text (STT) with 1.5s silence timeout
  - Echo suppression: mutes microphone after our own TTS fires
  - Configurable silence detection thresholds
  
- **`xtts_speaker.py`** — `XTTSSpeaker` + `DualSpeaker` classes
  - Coqui XTTS v2 voice cloning (multilingual, instant synthesis)
  - Pre-generation cache: stores WAV files by text hash + persona + ref fingerprint
  - Supports offline pre-generation (run night before) and live synthesis fallback
  - Fallback chain: cached WAV → live XTTS → Azure TTS
  - Cache invalidates automatically if `ref.wav` changes
  - `DualSpeaker` wraps both XTTS and Azure with smart mode selection
  
- **`sound_effects.py`** — `SoundEffectsEngine` class
  - Plays crowd reactions
  - Fact-check pass/fail sounds
  - Speech-triggered sound effects based on content
  - Loads crowd sounds from `data/crowd_sounds/`
  
- **`speaker.py`** — Legacy speaker (less used, see `xtts_speaker.py` instead)

#### 3. **GUI Module** (`src/gui/`)
- **`dashboard.py`** — `DebateDashboard` class (PyQt6)
  - South Park cartoon aesthetic: paper-cutout style, flat colors, thick black outlines
  - Split screen: Trump (left, red) vs Biden (right, blue) with Siskind in center
  - Status indicators: LISTENING (green), THINKING (yellow), SPEAKING (red)
  - Scrolling ticker at bottom: live transcript, fact-check results, commentary
  - Fact-check overlay: full-screen flash (green/red/orange) with verdict
  - Crowd reaction meter: animated progress bar
  - Color palette: red/blue political colors, yellow stage lights, black outlines
  
- **`voice_selector.py`** — `VoiceModeSelector` class
  - Startup dialog to choose voice mode: XTTS (fast, pre-cached) or AZURE (always works)

#### 4. **Moderator Module** (`src/moderator/`)
- **`siskind.py`** — `SiskindModerator` class
  - Professor Siskind (real Purdue professor) as moderator
  - Dry, academic personality with slight exasperation
  - Pre-written topic introductions, time warnings, interjections
  - Uses GPT to generate custom interjections if needed
  - Avoids deadlock: speaks via moderator callback, not two-way conversation

#### 5. **Utils Module** (`src/utils/`)
- **`scraper_trump.py`**, **`scraper_biden.py`** — Web scrapers
  - Collect speech transcripts and debates
  - Store in `data/raw_{persona}/speeches.txt` for RAG
  - Run once, output used by RAG for semantic indexing
  
- **`platform.py`** — Cross-platform helpers
  - Windows console color support
  - Font resolution for macOS/Linux/Windows
  - Platform info printing

---

## Data Structure

```
data/
  raw_trump/
    ref.wav                    # Reference voice sample for Trump (required)
    idle.png, talking.png, listening.png   # Optional avatar images
    speeches.txt              # Scraped speech corpus (RAG index)
  
  raw_biden/
    ref.wav                    # Reference voice sample for Biden (required)
    idle.png, talking.png, listening.png   # Optional avatar images
    speeches.txt              # Scraped speech corpus (RAG index)
  
  raw_siskind/
    ref.wav                    # Reference voice sample for moderator (required)
  
  crowd_sounds/
    applause.wav, boos.wav, etc.   # Optional crowd reactions
  
  xtts_cache/                  # Auto-generated at runtime
    trump/                     # Cached WAV files by text hash
    biden/
    siskind/
  
  SOURCES.md                   # Data attribution
```

---

## Main Entry Point

### `src/main.py` — Application orchestration

**Core Classes:**
- **`DebateWorker(QThread)`** — Background debate loop
  - Listen → Think (brain + RAG) → Speak cycle
  - Fact-check async
  - Sound effects triggered by content
  - Qt signals to update GUI
  - Keyboard controls: SPACE (force open), M (moderator), F (fact-checker toggle), C (crowd), R (reset), ESC (quit)
  
- **`DebateNight(QMainWindow)`** — Main Qt application window
  - Integrates all components
  - Handles keyboard events and UI updates

**Initialization:**
1. Load persona from `PERSONA` environment variable (`trump` or `biden`)
2. Show voice selector dialog (XTTS vs Azure)
3. Initialize `DebateBrain` with RAG
4. Initialize `DualSpeaker` (voice mode selected)
5. Initialize `DebateListener`, `SoundEffectsEngine`, `FactChecker`, `SiskindModerator`
6. Start GUI and background worker thread
7. Moderator opens debate, introduces first topic

---

## How It Works

### Debate Loop (per turn)

1. **Listen** — `DebateListener.listen_for_turn()` captures opponent speech
2. **Think** — `DebateBrain.generate_response(opponent_text)`
   - Embedds opponent text
   - RAG retrieves top-4 relevant quotes from `raw_{persona}/speeches.txt`
   - Injects RAG quotes into system prompt
   - Calls GPT-4 with rich persona + RAG + conversation history
3. **Fact-Check (async)** — `FactChecker.check_async()` verifies opponent claims
4. **Speak** — `DualSpeaker.speak(reply)`
   - Checks cache for pre-generated WAV
   - Falls back to live XTTS synthesis
   - Falls back to Azure TTS if XTTS unavailable
   - Mutes microphone while speaking (echo suppression)
5. **Sound Effects** — `SoundEffectsEngine.react_to_speech()` plays crowd reactions

### RAG Workflow

- **Index Phase (startup):** Load all sentences from `speeches.txt`, embed with `sentence-transformers`
- **Query Phase (each turn):** Embed opponent's statement, find top-K matches via cosine similarity
- **Injection:** Format as "Here's how you have spoken about this before:" block in system prompt
- **Fallback:** If RAG unavailable or fails, continue with normal prompting (zero degradation)

### Voice Cloning (XTTS)

- **Pre-generation (offline):** 
  ```bash
  python src/audio/xtts_speaker.py --pregenerate trump
  ```
  - Stores cached WAVs in `data/xtts_cache/{persona}/`
  - Cache key includes text hash + persona + ref.wav fingerprint

- **Live playback:** 
  - Check cache first (instant playback)
  - Fall back to live synthesis (~5-15s on CPU)
  - Fall back to Azure TTS (~1-2s)

---

## Configuration

### `keys.py` (filled from `keys_template.py`)
- Azure OpenAI credentials: `azure_openai_key`, `azure_openai_endpoint`, `azure_openai_api_version`, `azure_openai_deployment`
- Azure Speech credentials: `azure_key`, `azure_region`

### Environment Variables
- `PERSONA` — Set to `trump` or `biden` (default: `trump`)

### Constants (in source)
- Debate topics (auto-rotate): `DEBATE_TOPICS` in `model.py`
- Interjections (persona-specific): `INTERJECTIONS` in `model.py`
- Silence timeout: 1500ms (configurable in `listener.py`)
- RAG top-K: 4 quotes (configurable in `model.py`)

---

## Running the Application

### Setup
```bash
# Activate venv
source venv/bin/activate    # macOS/Linux
# or
.\venv\Scripts\Activate.ps1  # Windows PowerShell

# Install dependencies
python -m pip install -r requirements.txt

# Configure keys
cp keys_template.py keys.py
# Edit keys.py with Azure credentials

# Add required voice references
# Place ref.wav files in data/raw_{trump,biden,siskind}/
```

### Run
```bash
# Trump instance
PERSONA=trump python src/main.py

# Biden instance
PERSONA=biden python src/main.py
```

### Optional: Pre-generate voice cache (offline)
```bash
source venv/bin/activate
PERSONA=trump python src/audio/xtts_speaker.py --pregenerate trump
PERSONA=biden python src/audio/xtts_speaker.py --pregenerate biden
```

---

## Key Features

1. **RAG for Historical Context** — Debates grounded in real quotes
2. **Voice Cloning (XTTS)** — Instant synthesis from cached audio
3. **Graceful Degradation** — All components have fallbacks; if one fails, system continues
4. **Cross-Platform** — Windows, macOS, Linux via PyQt6, Azure Cloud, Python 3.10+
5. **Fact-Checking** — Real-time verification with visual feedback
6. **South Park Aesthetic** — Cartoon GUI with character avatars and crowd reactions
7. **Keyboard Controls** — SPACE, M, F, C, R, ESC for live interaction
8. **Echo Suppression** — Mutes microphone after own speech to prevent feedback loops

---

## Dependencies (at a Glance)

| Category | Packages |
|----------|----------|
| **LLM** | openai, azure-cognitiveservices-speech |
| **RAG** | sentence-transformers, numpy, transformers |
| **GUI** | PyQt6 |
| **Audio I/O** | sounddevice, soundfile, pygame |
| **Voice Cloning** | TTS (Coqui), torch, torchaudio |
| **Text Processing** | spacy, encodec, umap-learn |
| **Web Scraping** | requests, beautifulsoup4, lxml |
| **Utilities** | tqdm |

---

## Status & Next Steps

✅ **Complete:**
- Dual-persona debate with RAG
- XTTS voice cloning with cache
- Azure TTS fallback
- Fact-checking system
- South Park GUI
- Siskind moderator
- Cross-platform support

🔄 **Optional Enhancements:**
- Pre-generate XTTS cache for faster demo startup
- Add more avatar images for richer GUI
- Scrape additional speech corpora for better RAG
- Tune silence detection thresholds for different microphones

---

## Troubleshooting

### XTTS not generating audio?
- Verify `data/raw_{persona}/ref.wav` exists (10-30 sec clean speech)
- Check `torch` and `torchaudio` installed: `python -m pip show TTS torch torchaudio`
- If CPU, synthesis may take 10-30s per turn; consider pre-generation

### No microphone input?
- Check system audio input device in OS settings
- Test Azure STT: `python -c "import azure.cognitiveservices.speech as sdk; print('OK')"`

### No speaker output?
- Check system audio output volume and device
- Test with: `python -c "import sounddevice as sd; sd.play([0]*1000, 44100)"`

### RAG not working?
- Ensure `sentence-transformers` installed: `python -m pip install sentence-transformers`
- Check `data/raw_{persona}/speeches.txt` exists and has content
- RAG silently degrades if unavailable — normal operation continues
