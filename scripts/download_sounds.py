"""
scripts/download_sounds.py

Downloads free crowd sound effects for the debate.
All sounds from freesound.org (CC0 / CC-BY licensed).

Run once before first demo:
    python scripts/download_sounds.py
"""

import os
import sys
import urllib.request

SOUNDS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "crowd_sounds")
os.makedirs(SOUNDS_DIR, exist_ok=True)

# These are royalty-free sounds from freesound.org
# You may need to manually download if direct links change.
# Instructions included for manual download.

SOUND_SOURCES = {
    "applause.wav": {
        "description": "Crowd applause",
        "freesound_id": "456360",
        "manual": "Search freesound.org for 'crowd applause short' — download as WAV",
    },
    "laugh.wav": {
        "description": "Audience laughter",
        "freesound_id": "523782",
        "manual": "Search freesound.org for 'audience laughter' — download as WAV",
    },
    "boo.wav": {
        "description": "Crowd booing",
        "freesound_id": "277020",
        "manual": "Search freesound.org for 'crowd booing' — download as WAV",
    },
    "buzzer.wav": {
        "description": "Game show wrong answer buzzer",
        "freesound_id": "331912",
        "manual": "Search freesound.org for 'wrong buzzer' — download as WAV",
    },
    "ding.wav": {
        "description": "Correct answer ding",
        "freesound_id": "341695",
        "manual": "Search freesound.org for 'correct ding bell' — download as WAV",
    },
    "fanfare.wav": {
        "description": "Fanfare / opening trumpet",
        "freesound_id": "456144",
        "manual": "Search freesound.org for 'fanfare short' — download as WAV",
    },
    "crickets.wav": {
        "description": "Awkward silence / crickets",
        "freesound_id": "211079",
        "manual": "Search freesound.org for 'crickets' — download as WAV",
    },
    "drumroll.wav": {
        "description": "Drum roll",
        "freesound_id": "400163",
        "manual": "Search freesound.org for 'drum roll short' — download as WAV",
    },
}


def print_manual_instructions():
    """Print instructions for manually downloading sounds."""
    print("\n" + "="*60)
    print("SOUND FILES — MANUAL DOWNLOAD INSTRUCTIONS")
    print("="*60)
    print(f"\nPlace WAV files in: {SOUNDS_DIR}\n")
    
    for filename, info in SOUND_SOURCES.items():
        path = os.path.join(SOUNDS_DIR, filename)
        if os.path.exists(path):
            print(f"  ✅ {filename} (already exists)")
        else:
            print(f"  ❌ {filename}: {info['description']}")
            print(f"     → freesound.org/s/{info['freesound_id']}/")
            print(f"     → {info['manual']}")
    
    print("\nAlternatively, use any short WAV files you find.")
    print("The system will work without sounds — just silently skips.")
    print("="*60 + "\n")


def generate_silence_placeholders():
    """
    Generate silent WAV files as placeholders so the system doesn't crash.
    Requires numpy.
    """
    try:
        import numpy as np
        import soundfile as sf
        
        print("Generating silent placeholder WAV files...")
        sample_rate = 44100
        duration = 1.0  # 1 second of silence
        silence = np.zeros(int(sample_rate * duration), dtype=np.float32)
        
        for filename in SOUND_SOURCES:
            path = os.path.join(SOUNDS_DIR, filename)
            if not os.path.exists(path):
                sf.write(path, silence, sample_rate)
                print(f"  ✅ Created placeholder: {filename}")
        
        print("\n✅ Placeholder sounds created.")
        print("   Replace them with real sounds for full effect!\n")
        
    except ImportError:
        print("⚠️  numpy/soundfile not available — skipping placeholder generation")
        print("   Sound effects will be silently skipped during debate.\n")


if __name__ == "__main__":
    print_manual_instructions()
    
    response = input("Generate silent placeholder WAV files? (y/n): ").strip().lower()
    if response == "y":
        generate_silence_placeholders()
    else:
        print("\nSkipping placeholder generation. Add real WAV files manually.")
