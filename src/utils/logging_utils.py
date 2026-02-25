"""Logging helpers for Debate Night."""

from __future__ import annotations

import logging
import os


DEFAULT_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: str | int | None = None) -> None:
    """Initialize process-wide logging once.

    The level can be passed explicitly or controlled with `DEBATE_LOG_LEVEL`.
    """
    resolved_level = level or os.getenv("DEBATE_LOG_LEVEL", DEFAULT_LOG_LEVEL)
    if isinstance(resolved_level, str):
        numeric_level = getattr(logging, resolved_level.upper(), logging.INFO)
    else:
        numeric_level = resolved_level

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=numeric_level, format=LOG_FORMAT)
    else:
        root.setLevel(numeric_level)

    # Keep noisy third-party libs quieter by default.
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
