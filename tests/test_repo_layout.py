from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_core_files_exist() -> None:
    required = [
        ROOT / "src" / "main.py",
        ROOT / "src" / "core" / "debate_orchestrator.py",
        ROOT / "src" / "services" / "runtime.py",
        ROOT / "src" / "infra" / "metrics.py",
        ROOT / "src" / "brain" / "model.py",
        ROOT / "scripts" / "doctor.py",
        ROOT / "scripts" / "finetune_qwen.py",
        ROOT / "scripts" / "setup_selected_mode.py",
        ROOT / "requirements.txt",
        ROOT / "requirements-qwen.txt",
        ROOT / "requirements-xtts.txt",
        ROOT / "requirements-rag.txt",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"Missing required files: {missing}"


def test_persona_prompts_exist() -> None:
    for persona in ("trump", "biden"):
        prompt_file = ROOT / "src" / "brain" / "personas" / f"{persona}.txt"
        assert prompt_file.exists(), f"Missing persona prompt: {prompt_file.relative_to(ROOT)}"
