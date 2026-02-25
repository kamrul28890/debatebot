"""
src/audio/xtts_speaker.py

XTTS v2 voice cloning engine with pre-generation cache.

Two modes:
  1. pregenerate(texts, persona) — run OFFLINE before demo to cache WAV files
  2. speak(text, persona) — during demo, plays cached WAV (zero latency)
                            falls back to live synthesis if not cached
                            falls back to Azure TTS if XTTS unavailable

Pre-generation workflow:
  python src/audio/xtts_speaker.py --pregenerate trump
  python src/audio/xtts_speaker.py --pregenerate biden
  (run the night before the demo on any machine, then copy cache to both Macs)
"""

import os
import sys
import json
import hashlib
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# ── XTTS availability check ────────────────────────────────────────────────────
XTTS_AVAILABLE = False
try:
    import torch
    import torchaudio
    import soundfile as sf
    from TTS.api import TTS as CoquiTTS

    # Monkey-patch for Windows/Mac audio loading issues
    def _safe_load_wav(filepath, **kwargs):
        data, sr = sf.read(filepath)
        import numpy as np
        tensor = torch.FloatTensor(data)
        if len(tensor.shape) == 1:
            tensor = tensor.unsqueeze(0)
        else:
            tensor = tensor.transpose(0, 1)
        return tensor, sr

    torchaudio.load = _safe_load_wav
    XTTS_AVAILABLE = True
except ImportError as e:
    pass  # Graceful degradation — Azure TTS will be used instead


# ── Cache config ───────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CACHE_DIR  = os.path.join(BASE_DIR, "data", "xtts_cache")
XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
CACHE_FORMAT_VERSION = "xtts_clone_v2"


def _ref_fingerprint(persona: str) -> str:
    """Fingerprint ref.wav so cache invalidates when reference audio changes."""
    ref = _ref_wav(persona)
    if not os.path.exists(ref):
        return "missing_ref"
    stat = os.stat(ref)
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _text_hash(persona: str, text: str) -> str:
    """Hash that includes text + persona + cache version + ref.wav fingerprint."""
    normalized = text.strip().lower()
    payload = f"{CACHE_FORMAT_VERSION}|{persona}|{_ref_fingerprint(persona)}|{normalized}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:10]


def _cache_path(persona: str, text: str) -> str:
    return os.path.join(CACHE_DIR, persona, f"{_text_hash(persona, text)}.wav")


def _ref_wav(persona: str) -> str:
    return os.path.join(BASE_DIR, "data", f"raw_{persona}", "ref.wav")


# ── XTTSSpeaker ────────────────────────────────────────────────────────────────

class XTTSSpeaker:
    """
    Voice-cloning speaker using XTTS v2.

    Usage during demo (zero latency):
        speaker = XTTSSpeaker("trump")
        speaker.speak("Nobody builds chatbots better than us.")

    Pre-generation (run night before):
        speaker = XTTSSpeaker("trump")
        speaker.pregenerate(["line 1", "line 2", ...])
    """

    def __init__(self, persona: str):
        self.persona = persona
        self._tts = None
        self._latents = {}
        self._ready = False
        os.makedirs(os.path.join(CACHE_DIR, persona), exist_ok=True)

        if not XTTS_AVAILABLE:
            print(f"[XTTS] WARNING: XTTS not available - install: pip install TTS torch torchaudio")
            return

        self._load_model()

    def speak(self, text: str) -> bool:
        """
        Play audio for text.
        1. Tries cache (zero latency)
        2. Falls back to live XTTS synthesis on cache miss
        Returns True if audio actually played.
        """
        text = (text or "").strip()
        if not text:
            return False

        full_cache = _cache_path(self.persona, text)

        # Exact full-text cache hit.
        if os.path.exists(full_cache):
            print(f"[XTTS] backend=XTTS(cache) persona={self.persona}")
            print(f"[XTTS] Cache hit - playing {os.path.basename(full_cache)}")
            return self._play_wav(full_cache)

        if not self._ready:
            return False

        print(f"[XTTS] backend=XTTS(live) persona={self.persona}")
        chunks = self._split_text_for_synthesis(text)
        if len(chunks) > 1:
            print(f"[XTTS] Chunking long text into {len(chunks)} segments for faster first audio")

        for idx, chunk in enumerate(chunks, start=1):
            chunk_cache = _cache_path(self.persona, chunk)
            if os.path.exists(chunk_cache):
                print(f"[XTTS] Chunk {idx}/{len(chunks)} cache hit")
                if not self._play_wav(chunk_cache):
                    return False
                continue

            print(f"[XTTS] Synthesizing chunk {idx}/{len(chunks)}...")
            try:
                self._synthesize(chunk, chunk_cache)
            except Exception as e:
                print(f"[XTTS] Synthesis error on chunk {idx}: {e}")
                return False

            if not self._play_wav(chunk_cache):
                return False

        return True

    @staticmethod
    def _split_text_for_synthesis(text: str, max_chars: int = 80) -> list[str]:
        """Split long utterances into small sentence-first chunks."""
        import re

        parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', text) if p.strip()]
        if not parts:
            return [text]

        chunks = []
        for part in parts:
            if len(part) <= max_chars:
                chunks.append(part)
            else:
                # Hard split very long single sentences.
                for i in range(0, len(part), max_chars):
                    piece = part[i:i + max_chars].strip()
                    if piece:
                        chunks.append(piece)
        return chunks if chunks else [text]

    def pregenerate(self, texts: list, show_progress: bool = True):
        """
        Pre-generate WAV files for a list of texts.
        Run this offline before the demo.
        """
        if not self._ready:
            print("[XTTS] Cannot pregenerate - model not loaded")
            return

        print(f"\n[XTTS] Pre-generating {len(texts)} audio files for {self.persona}...")
        done, skipped = 0, 0

        for i, text in enumerate(texts):
            cache = _cache_path(self.persona, text)
            if os.path.exists(cache):
                skipped += 1
                continue

            if show_progress:
                print(f"  [{i+1}/{len(texts)}] {text[:60]}...")

            try:
                self._synthesize(text, cache)
                done += 1
            except Exception as e:
                print(f"  WARNING: Failed: {e}")

        print(f"[XTTS] Pre-generation done: {done} new files, {skipped} already cached")
        print(f"   Cache dir: {os.path.join(CACHE_DIR, self.persona)}")

    def cache_size(self) -> int:
        """Number of cached audio files for this persona."""
        d = os.path.join(CACHE_DIR, self.persona)
        if not os.path.exists(d):
            return 0
        return len([f for f in os.listdir(d) if f.endswith(".wav")])

    def is_cached(self, text: str) -> bool:
        return os.path.exists(_cache_path(self.persona, text))

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load_model(self):
        print(f"[XTTS] Loading model ({XTTS_MODEL})... (first time downloads ~1.5GB)")
        try:
            # Compatibility patch for newer PyTorch
            _orig = torch.load
            def _patched(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return _orig(*args, **kwargs)
            torch.load = _patched

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._tts = CoquiTTS(model_name=XTTS_MODEL).to(device)
            print(f"[XTTS] Model loaded on {device}")

            # Pre-compute voice latents from ref.wav
            ref = _ref_wav(self.persona)
            if not os.path.exists(ref):
                print(f"[XTTS] ERROR: ref.wav not found at {ref}")
                print(f"[XTTS] Cannot initialize XTTS for {self.persona} without reference audio")
                self._ready = False
                return

            # Optional optimization. Cloning works even if this fails because
            # synthesis uses speaker_wav directly.
            try:
                print(f"[XTTS] Computing voice fingerprint from {ref}...")
                from TTS.tts.configs.xtts_config import XttsConfig
                torch.serialization.add_safe_globals([XttsConfig])
                gpt_latent, speaker_emb = (
                    self._tts.synthesizer.tts_model
                    .get_conditioning_latents(audio_path=[ref])
                )
                self._latents[self.persona] = {
                    "gpt_cond_latent": gpt_latent,
                    "speaker_embedding": speaker_emb,
                }
                print(f"[XTTS] Voice fingerprint cached for {self.persona}")
            except Exception as e:
                print(f"[XTTS] Voice fingerprint step failed; continuing with speaker_wav clone ({e})")
            
            self._ready = True
            print(f"[XTTS] {self.persona} ready for synthesis (model + ref.wav)")
        except Exception as e:
            print(f"[XTTS] Model load failed: {e}")
            import traceback
            traceback.print_exc()
            self._ready = False

    def _synthesize(self, text: str, output_path: str):
        """Synthesize text to WAV from persona reference audio."""
        ref = _ref_wav(self.persona)
        self._tts.tts_to_file(
            text=text,
            speaker_wav=ref,
            language="en",
            file_path=output_path,
        )
        print(f"[XTTS] Synthesis path: speaker_wav clone for {self.persona} ({os.path.basename(ref)})")

    @staticmethod
    def _play_wav(path: str) -> bool:
        """Play a WAV file — cross-platform (Mac, Windows, Linux)."""
        from src.utils.platform import play_wav_blocking
        success = play_wav_blocking(path)
        if not success:
            print(f"[XTTS] Could not play audio: {path}")
        return success


# ── DualSpeaker: XTTS with Azure fallback ─────────────────────────────────────

class DualSpeaker:
    """
    Smart speaker that uses XTTS if mode='xtts', Azure if mode='azure'.
    Also falls back from XTTS -> Azure automatically on any error.
    """

    def __init__(self, persona: str, mode: str = "azure"):
        if mode not in ("xtts", "azure"):
            raise ValueError(f"Unknown mode: {mode}")
        self.persona = persona
        self.mode = mode

        # Always initialize Azure (fast, reliable)
        from src.audio.speaker import DebateSpeaker
        self.azure_speaker = DebateSpeaker(persona)

        # Initialize XTTS only if requested
        self.xtts_speaker = None
        if mode == "xtts":
            if XTTS_AVAILABLE:
                print(f"[DualSpeaker:{persona}] Initializing XTTS...")
                self.xtts_speaker = XTTSSpeaker(persona)
                if self.xtts_speaker._ready:
                    cached_files = self.xtts_speaker.cache_size()
                    print(f"[DualSpeaker:{persona}] XTTS ready - {cached_files} files cached")
                else:
                    print(f"[DualSpeaker:{persona}] WARNING: XTTS initialization failed - falling back to Azure TTS")
                    self.xtts_speaker = None
                    self.mode = "azure"
            else:
                print(f"[DualSpeaker:{persona}] WARNING: XTTS not available (check: pip install TTS torch torchaudio) - using Azure TTS")
                self.mode = "azure"

    def speak(self, text: str):
        """Speak text using configured mode, with Azure fallback."""
        if self.mode == "xtts" and self.xtts_speaker is not None:
            success = self.xtts_speaker.speak(text)
            if success:
                print(f"[DualSpeaker:{self.persona}] backend=XTTS")
                return
            print(f"[DualSpeaker:{self.persona}] XTTS failed - backend=AZURE fallback")

        # Azure path (primary or fallback)
        print(f"[DualSpeaker:{self.persona}] backend=AZURE")
        self.azure_speaker.speak(text)

    def estimate_cache_coverage(self, texts: list) -> float:
        """What fraction of texts are already cached?"""
        if self.xtts_speaker is None:
            return 0.0
        cached = sum(1 for t in texts if self.xtts_speaker.is_cached(t))
        return cached / len(texts) if texts else 0.0


# ── CLI for pre-generation ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="XTTS pre-generation tool")
    parser.add_argument("--pregenerate", metavar="PERSONA",
                        help="Pre-generate audio for a persona (trump or biden)")
    parser.add_argument("--test", metavar="PERSONA",
                        help="Test XTTS with a sample line")
    args = parser.parse_args()

    if args.pregenerate:
        persona = args.pregenerate
        # Load common debate lines to pre-generate
        common_lines = [
            # Trump
            "Nobody builds walls better than me, believe me.",
            "We had the greatest economy in the history of our country.",
            "It's a disaster. A total disaster.",
            "Wrong. That's just wrong.",
            "Fake news. Total fake news.",
            "We're going to win so much, you're going to be so sick and tired of winning.",
            "The border is a catastrophe. A total catastrophe.",
            "China is ripping us off. They've been doing it for years.",
            # Biden
            "Look, here's the deal.",
            "Not a joke. I'm being serious.",
            "C'mon, man. That's just not true.",
            "My dad used to say: a job is about a lot more than a paycheck.",
            "We're going to build this country back better.",
            "No malarkey. That's my promise.",
            "Here's what I'll do — I'll tell you the truth.",
            "The middle class built this country. Not the wealthy.",
        ]

        speaker = XTTSSpeaker(persona)
        if speaker._ready:
            speaker.pregenerate(common_lines)
        else:
            print(f"XTTS not ready for {persona}")

    elif args.test:
        persona = args.test
        test_lines = {
            "trump": "Nobody builds debate systems better than us. It's true.",
            "biden": "Look folks, here's the deal — this voice sounds pretty good. Not a joke.",
        }
        speaker = XTTSSpeaker(persona)
        if speaker._ready:
            print(f"Testing {persona}...")
            speaker.speak(test_lines.get(persona, "Hello from the debate stage."))
        else:
            print(f"XTTS not ready. Check: pip install TTS torch torchaudio")


