"""
Runtime configuration loader.

Priority:
1. Environment variables
2. Local keys.py (backward compatibility)
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Optional


def _load_keys_module():
    try:
        return importlib.import_module("keys")
    except Exception:
        return None


_KEYS = _load_keys_module()


def _from_keys(attr: str) -> Optional[str]:
    if _KEYS is None:
        return None
    return getattr(_KEYS, attr, None)


def _read(*env_names: str, keys_attr: Optional[str] = None, default: Optional[str] = None) -> Optional[str]:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value:
            return value
    if keys_attr:
        value = _from_keys(keys_attr)
        if value:
            return value
    return default


@dataclass(frozen=True)
class RuntimeConfig:
    azure_openai_key: Optional[str]
    azure_openai_endpoint: Optional[str]
    azure_openai_api_version: str
    azure_openai_deployment: Optional[str]
    azure_openai_fast_deployment: Optional[str]
    azure_speech_key: Optional[str]
    azure_speech_region: Optional[str]
    azure_tts_voice_trump: Optional[str]
    azure_tts_voice_biden: Optional[str]
    azure_tts_voice_siskind: Optional[str]

    def require_openai(self) -> None:
        missing = []
        if not self.azure_openai_key:
            missing.append("AZURE_OPENAI_KEY")
        if not self.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.azure_openai_deployment:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing Azure OpenAI configuration: {joined}")

    def require_speech(self) -> None:
        missing = []
        if not self.azure_speech_key:
            missing.append("AZURE_SPEECH_KEY")
        if not self.azure_speech_region:
            missing.append("AZURE_SPEECH_REGION")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing Azure Speech configuration: {joined}")


settings = RuntimeConfig(
    azure_openai_key=_read("AZURE_OPENAI_KEY", keys_attr="azure_openai_key"),
    azure_openai_endpoint=_read("AZURE_OPENAI_ENDPOINT", keys_attr="azure_openai_endpoint"),
    azure_openai_api_version=_read(
        "AZURE_OPENAI_API_VERSION",
        keys_attr="azure_openai_api_version",
        default="2024-08-01-preview",
    ),
    azure_openai_deployment=_read("AZURE_OPENAI_DEPLOYMENT", keys_attr="azure_openai_deployment"),
    azure_openai_fast_deployment=_read(
        "AZURE_OPENAI_FAST_DEPLOYMENT",
        keys_attr="azure_openai_fast_deployment",
    ),
    azure_speech_key=_read("AZURE_SPEECH_KEY", keys_attr="azure_key"),
    azure_speech_region=_read("AZURE_SPEECH_REGION", keys_attr="azure_region"),
    azure_tts_voice_trump=_read("AZURE_TTS_VOICE_TRUMP", keys_attr="azure_tts_voice_trump"),
    azure_tts_voice_biden=_read("AZURE_TTS_VOICE_BIDEN", keys_attr="azure_tts_voice_biden"),
    azure_tts_voice_siskind=_read("AZURE_TTS_VOICE_SISKIND", keys_attr="azure_tts_voice_siskind"),
)
