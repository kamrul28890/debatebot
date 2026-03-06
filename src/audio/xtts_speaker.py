"""
src/audio/xtts_speaker.py

XTTS v2 voice cloning engine with pre-generation cache.

Two modes:
  1. pregenerate(texts, persona) â€” run OFFLINE before demo to cache WAV files
  2. speak(text, persona) â€” during demo, plays cached WAV (zero latency)
                            falls back to live synthesis if not cached
                            falls back to Azure TTS if XTTS unavailable

Pre-generation workflow:
  python src/audio/xtts_speaker.py --pregenerate trump
  python src/audio/xtts_speaker.py --pregenerate biden
  (run the night before the demo on any machine, then copy cache to both Macs)
"""

import os
import json
import hashlib
import logging
import threading

logger = logging.getLogger(__name__)

# â”€â”€ XTTS availability check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
XTTS_AVAILABLE = False
XTTS_IMPORT_ERROR = ""
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
except Exception as e:
    XTTS_IMPORT_ERROR = str(e)
    logger.debug("[XTTS] Optional local runtime unavailable. Azure fallback remains active.")
    logger.debug("[XTTS] Runtime import detail: %s", e)


def _apply_transformers_compat_patch() -> None:
    """
    Coqui XTTS 0.22 still imports BeamSearchScorer from `transformers` top-level.
    Newer transformers versions removed that export, so we restore it when needed.
    """
    try:
        import transformers
        if hasattr(transformers, "BeamSearchScorer"):
            return
        from transformers.generation.beam_search import BeamSearchScorer
        transformers.BeamSearchScorer = BeamSearchScorer
        logger.info("[XTTS] Applied transformers compatibility shim for BeamSearchScorer")
    except Exception as e:
        logger.debug("[XTTS] Transformers compatibility shim skipped: %s", e)


def _best_torch_device() -> str:
    """Pick fastest available backend for local XTTS synthesis."""
    requested = os.getenv("DEBATE_XTTS_DEVICE", "auto").strip().lower()
    if requested in {"cpu", "mps", "cuda"}:
        if requested == "cuda" and torch.cuda.is_available():
            return "cuda"
        if requested == "mps" and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        if requested == "cpu":
            return "cpu"
        logger.warning("[XTTS] Requested device '%s' unavailable. Falling back to auto selection.", requested)

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# â”€â”€ Cache config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ XTTSSpeaker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    _shared_tts = None
    _shared_device = None
    _shared_lock = threading.Lock()
    _torch_patch_applied = False
    _transformers_patch_applied = False

    def __init__(self, persona: str):
        self.persona = persona
        self._tts = None
        self._latents = {}
        self._ready = False
        self._stop_requested = False
        os.makedirs(os.path.join(CACHE_DIR, persona), exist_ok=True)

        if not XTTS_AVAILABLE:
            logger.info("[XTTS] Local runtime unavailable. Use Azure voice or install XTTS dependencies.")
            return

        self._load_model()

    @property
    def device_name(self) -> str:
        return str(XTTSSpeaker._shared_device or "cpu")

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
        self._stop_requested = False

        full_cache = _cache_path(self.persona, text)

        # Exact full-text cache hit.
        if os.path.exists(full_cache):
            logger.info("[XTTS] backend=XTTS(cache) persona=%s", self.persona)
            logger.debug("[XTTS] Cache hit - playing %s", os.path.basename(full_cache))
            return self._play_wav(full_cache)

        if not self._ready:
            return False

        logger.info("[XTTS] backend=XTTS(live) persona=%s", self.persona)
        chunks = self._split_text_for_synthesis(text)
        if len(chunks) > 1:
            logger.info("[XTTS] Chunking long text into %s segments", len(chunks))

        for idx, chunk in enumerate(chunks, start=1):
            if self._stop_requested:
                logger.info("[XTTS] Stop requested before chunk %s/%s", idx, len(chunks))
                return False
            chunk_cache = _cache_path(self.persona, chunk)
            if os.path.exists(chunk_cache):
                logger.debug("[XTTS] Chunk %s/%s cache hit", idx, len(chunks))
                if not self._play_wav(chunk_cache):
                    return False
                continue

            logger.info("[XTTS] Synthesizing chunk %s/%s", idx, len(chunks))
            try:
                self._synthesize(chunk, chunk_cache)
            except Exception as e:
                logger.error("[XTTS] Synthesis error on chunk %s: %s", idx, e)
                return False

            if self._stop_requested:
                logger.info("[XTTS] Stop requested after synthesis %s/%s", idx, len(chunks))
                return False

            if not self._play_wav(chunk_cache):
                return False

        return True

    def stop(self) -> None:
        """Best-effort stop for ongoing XTTS playback."""
        self._stop_requested = True

        # Stop pygame playback when available.
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except Exception:
            pass

        # Stop winsound playback on Windows.
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

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

    def pregenerate(self, texts: list, show_progress: bool = True, progress_callback=None):
        """
        Pre-generate WAV files for a list of texts.
        Run this offline before the demo.

        progress_callback signature:
            callback(index, total, text, done, skipped)
        """
        if not self._ready:
            logger.warning("[XTTS] Cannot pre-generate - model not loaded")
            return

        logger.info("[XTTS] Pre-generating %s audio files for %s", len(texts), self.persona)
        done, skipped = 0, 0

        for i, text in enumerate(texts):
            cache = _cache_path(self.persona, text)
            if os.path.exists(cache):
                skipped += 1
                if progress_callback:
                    try:
                        progress_callback(i + 1, len(texts), text, done, skipped)
                    except Exception:
                        pass
                continue

            if show_progress:
                logger.info("[XTTS] [%s/%s] %s...", i + 1, len(texts), text[:60])

            try:
                self._synthesize(text, cache)
                done += 1
            except Exception as e:
                logger.warning("[XTTS] Pre-generation failed: %s", e)

            if progress_callback:
                try:
                    progress_callback(i + 1, len(texts), text, done, skipped)
                except Exception:
                    pass

        logger.info("[XTTS] Pre-generation done: %s new files, %s already cached", done, skipped)
        logger.info("[XTTS] Cache dir: %s", os.path.join(CACHE_DIR, self.persona))

    def cache_size(self) -> int:
        """Number of cached audio files for this persona."""
        d = os.path.join(CACHE_DIR, self.persona)
        if not os.path.exists(d):
            return 0
        return len([f for f in os.listdir(d) if f.endswith(".wav")])

    def is_cached(self, text: str) -> bool:
        return os.path.exists(_cache_path(self.persona, text))

    # â”€â”€ Internal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _load_model(self):
        logger.info("[XTTS] Preparing model (%s)...", XTTS_MODEL)
        try:
            with XTTSSpeaker._shared_lock:
                if XTTSSpeaker._shared_tts is None:
                    logger.info("[XTTS] Loading shared model (first run may download ~1.5GB)")

                    if not XTTSSpeaker._transformers_patch_applied:
                        _apply_transformers_compat_patch()
                        XTTSSpeaker._transformers_patch_applied = True

                    if not XTTSSpeaker._torch_patch_applied:
                        _orig = torch.load

                        def _patched(*args, **kwargs):
                            kwargs.setdefault("weights_only", False)
                            return _orig(*args, **kwargs)

                        torch.load = _patched
                        XTTSSpeaker._torch_patch_applied = True

                    device = _best_torch_device()
                    XTTSSpeaker._shared_tts = CoquiTTS(model_name=XTTS_MODEL).to(device)
                    XTTSSpeaker._shared_device = device
                    logger.info("[XTTS] Shared model loaded on %s", device)
                else:
                    logger.info("[XTTS] Reusing shared model on %s", XTTSSpeaker._shared_device)

            self._tts = XTTSSpeaker._shared_tts

            # Pre-compute voice latents from ref.wav
            ref = _ref_wav(self.persona)
            if not os.path.exists(ref):
                logger.error("[XTTS] ref.wav not found at %s", ref)
                logger.error("[XTTS] Cannot initialize XTTS for %s without reference audio", self.persona)
                self._ready = False
                return

            # Optional optimization. Cloning works even if this fails because
            # synthesis uses speaker_wav directly.
            try:
                logger.info("[XTTS] Computing voice fingerprint from %s", ref)
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
                logger.info("[XTTS] Voice fingerprint cached for %s", self.persona)
            except Exception as e:
                logger.warning("[XTTS] Voice fingerprint step failed; continuing with speaker_wav clone (%s)", e)
            
            self._ready = True
            logger.info("[XTTS] %s ready for synthesis (model + ref.wav)", self.persona)
        except Exception as e:
            logger.error("[XTTS] Model load failed: %s", e)
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
        logger.debug("[XTTS] Synthesis path: speaker_wav clone for %s (%s)", self.persona, os.path.basename(ref))

    @staticmethod
    def _play_wav(path: str) -> bool:
        """Play a WAV file â€” cross-platform (Mac, Windows, Linux)."""
        from src.utils.platform import play_wav_blocking
        success = play_wav_blocking(path)
        if not success:
            logger.warning("[XTTS] Could not play audio: %s", path)
        return success


# â”€â”€ DualSpeaker: XTTS with Azure fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
                logger.info("[DualSpeaker:%s] Initializing XTTS...", persona)
                self.xtts_speaker = XTTSSpeaker(persona)
                if self.xtts_speaker._ready:
                    cached_files = self.xtts_speaker.cache_size()
                    logger.info(
                        "[DualSpeaker:%s] XTTS ready - %s files cached | device=%s",
                        persona,
                        cached_files,
                        self.xtts_speaker.device_name,
                    )
                else:
                    logger.info("[DualSpeaker:%s] XTTS init failed - using Azure TTS", persona)
                    self.xtts_speaker = None
                    self.mode = "azure"
            else:
                logger.info(
                    "[DualSpeaker:%s] XTTS unavailable - using Azure TTS",
                    persona,
                )
                self.mode = "azure"

    def speak(self, text: str):
        """Speak text using configured mode, with Azure fallback."""
        if self.mode == "xtts" and self.xtts_speaker is not None:
            success = self.xtts_speaker.speak(text)
            if success:
                logger.info("[DualSpeaker:%s] backend=XTTS", self.persona)
                return
            logger.warning("[DualSpeaker:%s] XTTS failed - backend=AZURE fallback", self.persona)

        # Azure path (primary or fallback)
        logger.info("[DualSpeaker:%s] backend=AZURE", self.persona)
        self.azure_speaker.speak(text)

    def stop(self) -> None:
        """Stop any ongoing speech output."""
        try:
            self.azure_speaker.stop()
        except Exception:
            pass

        if self.xtts_speaker is not None:
            try:
                self.xtts_speaker.stop()
            except Exception:
                pass

    def estimate_cache_coverage(self, texts: list) -> float:
        """What fraction of texts are already cached?"""
        if self.xtts_speaker is None:
            return 0.0
        cached = sum(1 for t in texts if self.xtts_speaker.is_cached(t))
        return cached / len(texts) if texts else 0.0


# â”€â”€ CLI for pre-generation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    import argparse

    def _pregenerate_lines(persona: str) -> list[str]:
        trump_lines = [
            "Nobody builds walls better than me, believe me.",
            "We had the greatest economy in the history of our country.",
            "It's a disaster. A total disaster.",
            "Wrong. That's just wrong.",
            "Fake news. Total fake news.",
            "We're going to win so much, you're going to be so sick and tired of winning.",
            "The border is a catastrophe. A total catastrophe.",
            "China is ripping us off. They've been doing it for years.",
        ]
        biden_lines = [
            "Look, here's the deal.",
            "Not a joke. I'm being serious.",
            "C'mon, man. That's just not true.",
            "My dad used to say: a job is about a lot more than a paycheck.",
            "We're going to build this country back better.",
            "No malarkey. That's my promise.",
            "Here's what I'll do - I'll tell you the truth.",
            "The middle class built this country. Not the wealthy.",
        ]
        siskind_lines = [
            "Good evening. I'm Professor Jeffrey Siskind from Purdue University's ECE department. Let's begin.",
            "Our first topic tonight is the economy and inflation. Mr. Trump, you have 30 seconds.",
            "Moving on - we'll discuss immigration and border security. Mr. Biden, your response.",
            "Next topic: foreign policy and America's role in NATO. Mr. Trump.",
            "Gentlemen, we turn to healthcare and social security. Mr. Biden.",
            "Our next topic is crime and public safety. I expect coherent responses. Mr. Trump.",
            "We'll now discuss climate change and energy policy. Mr. Biden.",
            "The topic is democracy and election integrity. Mr. Trump.",
            "Final topic: U.S.-China relations and trade. Mr. Biden, you may begin.",
            "Fifteen seconds remaining, gentlemen.",
            "Time, please. Wrap up your thought.",
            "That's time. We're moving on whether you're finished or not.",
            "Gentlemen. Gentlemen. This is not helpful.",
            "One at a time. This is a debate, not a neural network diverging.",
            "As I said in lecture - structure matters. Please use some.",
        ]

        if persona == "trump":
            return trump_lines
        if persona == "biden":
            return biden_lines
        if persona == "siskind":
            return siskind_lines
        return trump_lines + biden_lines

    parser = argparse.ArgumentParser(description="XTTS pre-generation tool")
    parser.add_argument(
        "--pregenerate",
        metavar="PERSONA",
        help="Pre-generate audio for a persona (trump, biden, or siskind)",
    )
    parser.add_argument("--test", metavar="PERSONA", help="Test XTTS with a sample line")
    args = parser.parse_args()

    if args.pregenerate:
        persona = args.pregenerate
        speaker = XTTSSpeaker(persona)
        if speaker._ready:
            speaker.pregenerate(_pregenerate_lines(persona))
        else:
            print(f"XTTS not ready for {persona}")

    elif args.test:
        persona = args.test
        test_lines = {
            "trump": "Nobody builds debate systems better than us. It's true.",
            "biden": "Look folks, here's the deal - this voice sounds pretty good. Not a joke.",
            "siskind": "Gentlemen, please. Let's keep this debate on track.",
        }
        speaker = XTTSSpeaker(persona)
        if speaker._ready:
            print(f"Testing {persona}...")
            speaker.speak(test_lines.get(persona, "Hello from the debate stage."))
        else:
            print("XTTS not ready. Check: pip install TTS torch torchaudio")
