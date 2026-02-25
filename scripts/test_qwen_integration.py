#!/usr/bin/env python3
"""
scripts/test_qwen_integration.py

Test script to validate Qwen integration before full training and app usage.

Usage:
    python scripts/test_qwen_integration.py
"""

import sys
from pathlib import Path

# Allow running the script from any working directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    # Avoid Windows cp1252 print crashes on unicode.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def test_qwen_brain() -> bool:
    """Test Qwen brain loading and basic inference."""
    try:
        try:
            from src.brain.qwen_brain import QwenBrain
        except ImportError as e:
            print(f"[WARN] Qwen brain import failed: {e}")
            print("   This is expected if PEFT/transformers versions are incompatible")
            return False

        print("[INFO] Testing Qwen brain initialization...")
        brain = QwenBrain(persona="trump")

        test_prompt = "Why are your policies better?"
        response = brain.generate_response(test_prompt)

        print(f"[OK] Qwen brain working. Response: {response[:200]}...")
        return True

    except Exception as e:
        print(f"[FAIL] Qwen brain test failed: {e}")
        return False


def test_model_loading() -> bool:
    """Test if required libraries are available."""
    required_libs = ["transformers", "accelerate", "datasets", "huggingface_hub", "peft"]

    passed = 0
    total = len(required_libs)

    for lib in required_libs:
        try:
            __import__(lib)
            print(f"[OK] {lib} available")
            passed += 1
        except ImportError:
            print(f"[FAIL] {lib} missing - required for Qwen")

    return passed == total


def test_huggingface_access() -> bool:
    """Test HuggingFace access to the public base model."""
    try:
        from huggingface_hub import HfApi

        api = HfApi()
        info = api.model_info("Qwen/Qwen2.5-0.5B")
        sha = getattr(info, "sha", "unknown")
        print(f"[OK] HuggingFace access working. Base model sha: {sha}")
        return True
    except Exception as e:
        print(f"[FAIL] HuggingFace access failed: {e}")
        return False


def main() -> None:
    print("Testing Qwen Integration\n")

    tests = [
        ("Library imports", test_model_loading),
        ("HuggingFace access", test_huggingface_access),
        ("Qwen brain functionality", test_qwen_brain),
    ]

    passed = 0
    total = len(tests)

    for name, test_func in tests:
        print(f"\n[TEST] {name}...")
        if test_func():
            passed += 1
        else:
            print(f"[WARN] {name} test failed - check setup")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("All tests passed. Ready for training/inference.")
    else:
        print("Some tests failed. Please fix issues before training.")
        print("\nCommon fixes:")
        print("- Install missing packages: pip install -r requirements.txt")
        print("- Set HF_TOKEN environment variable for private HuggingFace access")
        print("- Check internet connection for model downloads")


if __name__ == "__main__":
    main()
