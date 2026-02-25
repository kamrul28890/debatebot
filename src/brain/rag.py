"""
src/brain/rag.py

RAG (Retrieval-Augmented Generation) engine for debate personas.

Architecture:
- Loads scraped speech data from data/raw_{persona}/speeches.txt
- Embeds all sentences using sentence-transformers (runs locally, no API cost)
- At query time: embeds opponent's statement → cosine similarity → top-K matches
- Returns real quotes to inject into GPT context

Design principles:
- NEVER degrades existing behavior: if RAG fails for ANY reason, returns [] silently
- Index is built once at startup and cached in memory
- Falls back gracefully if sentence-transformers not installed
- Works with the curated phrases even if scraper hasn't been run yet

Usage:
    rag = RAGRetriever("trump")
    quotes = rag.retrieve("What about the economy?", k=3)
    # quotes = ["We had the greatest economy...", "The jobs numbers were incredible...", ...]
"""

import os
import re
import pickle
import hashlib
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# We try to import the heavy ML libs, but gracefully handle if missing
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SBERT_AVAILABLE = True
except ImportError:
    SBERT_AVAILABLE = False


# ── Constants ──────────────────────────────────────────────────────────────────
SBERT_MODEL = "all-MiniLM-L6-v2"   # 80MB, fast on CPU, great quality
MIN_SENTENCE_LEN = 15               # ignore very short fragments
MAX_SENTENCE_LEN = 300              # ignore very long passages
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".rag_cache")


class RAGRetriever:
    """
    Retrieves the most relevant real quotes for a given persona
    based on semantic similarity to the opponent's statement.
    """

    def __init__(self, persona: str):
        self.persona = persona
        self._sentences: List[str] = []
        self._embeddings = None   # numpy array [N, D]
        self._model = None
        self._ready = False

        if not NUMPY_AVAILABLE or not SBERT_AVAILABLE:
            missing = []
            if not NUMPY_AVAILABLE: missing.append("numpy")
            if not SBERT_AVAILABLE: missing.append("sentence-transformers")
            logger.warning("[RAG] Missing: %s - RAG disabled, using normal prompting", ", ".join(missing))
            return

        self._load()

    # ── Public API ─────────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int = 4) -> List[str]:
        """
        Find the k most semantically similar quotes to the query.
        Returns [] if RAG is unavailable or fails — never raises.
        """
        if not self._ready or not self._sentences:
            return []

        try:
            query_emb = self._model.encode([query], normalize_embeddings=True)
            # Cosine similarity (embeddings are normalized, so dot product = cosine)
            scores = np.dot(self._embeddings, query_emb.T).flatten()
            # Get top-k indices, sorted descending
            top_indices = np.argsort(scores)[::-1][:k]
            results = [self._sentences[i] for i in top_indices if scores[i] > 0.2]
            return results[:k]
        except Exception as e:
            logger.warning("[RAG] Retrieve error (non-fatal): %s", e)
            return []

    def is_ready(self) -> bool:
        return self._ready

    def corpus_size(self) -> int:
        return len(self._sentences)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load(self):
        """Load corpus, build or restore embeddings index."""
        corpus = self._load_corpus()
        if not corpus:
            logger.warning("[RAG] No speech data found for %s. Run scraper_%s.py first.", self.persona, self.persona)
            return

        self._sentences = corpus
        logger.info("[RAG] Loaded %s sentences for %s", len(corpus), self.persona)

        # Try to load cached embeddings
        cache_path = self._cache_path(corpus)
        if os.path.exists(cache_path):
            logger.info("[RAG] Loading cached embeddings")
            try:
                with open(cache_path, "rb") as f:
                    self._embeddings = pickle.load(f)
                logger.info("[RAG] Cache hit - %s embeddings loaded", self._embeddings.shape[0])
                self._load_model()
                self._ready = True
                return
            except Exception as e:
                logger.warning("[RAG] Cache load failed (%s), rebuilding", e)

        # Build embeddings from scratch
        self._build_index(corpus, cache_path)

    def _load_corpus(self) -> List[str]:
        """Load and clean sentences from the speech data file."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        speech_file = os.path.join(base_dir, "data", f"raw_{self.persona}", "speeches.txt")

        if not os.path.exists(speech_file):
            return []

        sentences = []
        with open(speech_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and headers
                if line.startswith("#") or line.startswith("##") or not line:
                    continue
                # Clean and validate
                cleaned = self._clean(line)
                if MIN_SENTENCE_LEN <= len(cleaned) <= MAX_SENTENCE_LEN:
                    sentences.append(cleaned)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for s in sentences:
            key = s.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique

    def _load_model(self):
        """Load the sentence transformer model (cached by HuggingFace after first download)."""
        if self._model is None:
            logger.info("[RAG] Loading embedding model (%s)", SBERT_MODEL)
            self._model = SentenceTransformer(SBERT_MODEL)
            logger.info("[RAG] Model ready")

    def _build_index(self, corpus: List[str], cache_path: str):
        """Encode all sentences and cache the result."""
        logger.info("[RAG] Building embeddings for %s sentences (one-time build)", len(corpus))
        self._load_model()

        try:
            self._embeddings = self._model.encode(
                corpus,
                normalize_embeddings=True,
                show_progress_bar=True,
                batch_size=32,
            )
            # Cache to disk
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(self._embeddings, f)
            logger.info("[RAG] Embeddings built and cached (%s)", self._embeddings.shape)
            self._ready = True
        except Exception as e:
            logger.warning("[RAG] Build failed (non-fatal): %s", e)
            self._ready = False

    def _cache_path(self, corpus: List[str]) -> str:
        """Deterministic cache path based on corpus content hash."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        corpus_hash = hashlib.md5("\n".join(corpus[:100]).encode()).hexdigest()[:8]
        return os.path.join(CACHE_DIR, f"{self.persona}_{corpus_hash}.pkl")

    @staticmethod
    def _clean(text: str) -> str:
        """Basic text cleaning."""
        text = re.sub(r'\s+', ' ', text)
        text = text.strip('" \t')
        return text


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time

    for persona in ["trump", "biden"]:
        print(f"\n{'='*50}")
        print(f"Testing RAG for: {persona.upper()}")
        print('='*50)

        rag = RAGRetriever(persona)

        if not rag.is_ready():
            print(f"RAG not ready for {persona} — run scraper first")
            continue

        print(f"Corpus size: {rag.corpus_size()} sentences\n")

        queries = [
            "The economy is doing terribly under your watch.",
            "What about immigration and the border?",
            "You failed to handle the COVID pandemic.",
        ]

        for q in queries:
            print(f"Query: '{q}'")
            t0 = time.time()
            results = rag.retrieve(q, k=3)
            elapsed = time.time() - t0
            print(f"Retrieved in {elapsed:.3f}s:")
            for i, r in enumerate(results, 1):
                print(f"  {i}. {r}")
            print()
