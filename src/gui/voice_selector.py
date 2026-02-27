"""
src/gui/voice_selector.py

Compact startup selector focused on 4 deployable modules.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.cache.deterministic import load_script, script_fingerprint
from src.config import settings


COLORS = {
    "bg": "#0f1318",
    "panel": "#171d25",
    "panel2": "#1f2732",
    "line": "#334152",
    "text": "#f3f5f8",
    "muted": "#b8c1ce",
    "warn": "#ffb14a",
    "ok": "#58d78f",
    "button": "#cf3d3d",
    "button_hover": "#e65151",
    "button_pressed": "#b42f2f",
}


COMBOS = {
    "azure_robotic": {
        "brain": "azure",
        "voice": "azure",
        "title": "Azure + Robotic Voice",
        "summary": "Cloud GPT-4 + Azure Neural TTS. Most stable.",
    },
    "qwen_robotic": {
        "brain": "qwen",
        "voice": "azure",
        "title": "Qwen + Robotic Voice",
        "summary": "Local Qwen + Azure TTS. Cheaper brain, reliable audio.",
    },
    "azure_cloned": {
        "brain": "azure",
        "voice": "xtts",
        "title": "Azure + Cloned Voice",
        "summary": "Cloud GPT-4 + local XTTS cloned voice.",
    },
    "qwen_cloned": {
        "brain": "qwen",
        "voice": "xtts",
        "title": "Qwen + Cloned Voice",
        "summary": "Fully local-style path (Qwen local + XTTS cache).",
    },
}


class DebateModeSelector(QWidget):
    """Startup selector for persona + 4 module combinations."""

    mode_selected = pyqtSignal(str, str, str, str)  # persona, brain_mode, voice_mode, run_mode

    def __init__(self, persona: str):
        super().__init__()
        self.project_root = Path(__file__).resolve().parents[2]
        self.persona = persona if persona in ("trump", "biden") else "trump"

        self._selected_combo = "azure_robotic"
        self._selected_brain = COMBOS[self._selected_combo]["brain"]
        self._selected_voice = COMBOS[self._selected_combo]["voice"]

        self._availability: dict = {}
        self._task_process: QProcess | None = None
        self._task_name: str | None = None
        self._cancel_requested = False
        self._warned_once = False
        self._task_tracks_progress = False
        self._qwen_runtime_probe_cache: tuple[float, bool, str] | None = None
        self._qwen_runtime_probe_ttl_sec = 8.0
        self._xtts_runtime_probe_cache: tuple[float, bool, str] | None = None
        self._xtts_runtime_probe_ttl_sec = 8.0

        self.setWindowTitle("Debate Night - Mode Selector")
        self.resize(860, 560)
        self.setMinimumSize(620, 420)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

        self._build_ui()
        self._set_persona(self.persona)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        left = QFrame()
        left.setStyleSheet(
            f"QFrame {{ background: {COLORS['panel']}; border: 1px solid {COLORS['line']}; border-radius: 8px; }}"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        right = QFrame()
        right.setStyleSheet(
            f"QFrame {{ background: {COLORS['panel2']}; border: 1px solid {COLORS['line']}; border-radius: 8px; }}"
        )
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        root.addWidget(left, stretch=3)
        root.addWidget(right, stretch=2)

        title = QLabel("DEBATE MODE SELECTOR")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: 18px; font-weight: 900;")
        left_layout.addWidget(title)

        self.subtitle = QLabel("")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
        left_layout.addWidget(self.subtitle)

        persona_row = QHBoxLayout()
        persona_row.setSpacing(8)
        persona_lbl = QLabel("Persona")
        persona_lbl.setStyleSheet(f"color: {COLORS['text']}; font-size: 12px; font-weight: 700;")
        persona_row.addWidget(persona_lbl)

        self.btn_trump = QPushButton("Trump")
        self.btn_biden = QPushButton("Biden")
        for btn in (self.btn_trump, self.btn_biden):
            btn.setCheckable(True)
            btn.setMinimumWidth(100)
            btn.clicked.connect(self._on_persona_button_clicked)
            persona_row.addWidget(btn)
        persona_row.addStretch()
        left_layout.addLayout(persona_row)

        modules_lbl = QLabel("Modules (4 combinations)")
        modules_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        modules_lbl.setStyleSheet(f"color: {COLORS['text']}; font-size: 13px; font-weight: 700;")
        left_layout.addWidget(modules_lbl)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        self.combo_group = QButtonGroup(self)
        self.combo_group.setExclusive(True)
        self.combo_buttons: dict[str, QPushButton] = {}
        for idx, (key, meta) in enumerate(COMBOS.items()):
            btn = QPushButton(f"{meta['title']}\n{meta['summary']}")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(54)
            btn.setStyleSheet(self._combo_button_style(checked=False, available=True))
            btn.clicked.connect(lambda _checked, k=key: self._on_combo_selected(k))
            self.combo_group.addButton(btn)
            self.combo_buttons[key] = btn
            row, col = divmod(idx, 2)
            grid.addWidget(btn, row, col)

        left_layout.addLayout(grid)

        self.module_note = QLabel("")
        self.module_note.setWordWrap(True)
        self.module_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.module_note.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
        left_layout.addWidget(self.module_note)

        self.brain_note = QLabel("")
        self.voice_note = QLabel("")
        self.cache_note = QLabel("")
        for note in (self.brain_note, self.voice_note, self.cache_note):
            note.setWordWrap(True)
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
            left_layout.addWidget(note)

        left_layout.addStretch()

        start_row = QHBoxLayout()
        start_row.setSpacing(8)

        self.start_live_btn = QPushButton("Start Debate (Live)")
        self.start_live_btn.setMinimumHeight(38)
        self.start_live_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_live_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['button']};
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton:hover {{ background-color: {COLORS['button_hover']}; }}
            QPushButton:pressed {{ background-color: {COLORS['button_pressed']}; }}
            QPushButton:disabled {{ background-color: #5d3030; color: #ccb9b9; }}
            """
        )
        self.start_live_btn.clicked.connect(lambda: self._on_start("live"))
        start_row.addWidget(self.start_live_btn, stretch=1)

        self.start_cached_btn = QPushButton("Start Debate (Cached)")
        self.start_cached_btn.setMinimumHeight(38)
        self.start_cached_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_cached_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2d5f97;
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 13px;
                font-weight: 800;
            }
            QPushButton:hover { background-color: #3c74b3; }
            QPushButton:pressed { background-color: #285386; }
            QPushButton:disabled { background-color: #31485f; color: #b7c1cc; }
            """
        )
        self.start_cached_btn.clicked.connect(lambda: self._on_start("cached"))
        start_row.addWidget(self.start_cached_btn, stretch=1)
        left_layout.addLayout(start_row)

        setup_title = QLabel("Setup & Status")
        setup_title.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: 800;")
        right_layout.addWidget(setup_title)

        self.status_panel = QLabel("")
        self.status_panel.setWordWrap(True)
        self.status_panel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_panel.setStyleSheet(
            "QLabel { background: #f7f8fb; color: #101317; border: 1px solid #c8d0dd; border-radius: 6px; padding: 8px; font-size: 10px; }"
        )
        right_layout.addWidget(self.status_panel)

        self.install_btn = QPushButton("Install Missing")
        self.install_btn.clicked.connect(self._install_missing)
        right_layout.addWidget(self.install_btn)

        self.train_btn = QPushButton("Train Qwen (Selected Persona)")
        self.train_btn.clicked.connect(self._train_qwen)
        right_layout.addWidget(self.train_btn)

        self.cache_btn = QPushButton("Prepare XTTS Cache (Persona + Siskind)")
        self.cache_btn.clicked.connect(self._prepare_xtts_cache)
        right_layout.addWidget(self.cache_btn)

        self.doctor_btn = QPushButton("Run Doctor")
        self.doctor_btn.clicked.connect(self._run_doctor)
        right_layout.addWidget(self.doctor_btn)

        self.local_mode_btn = QPushButton("Build Full Local Cached Mode (All)")
        self.local_mode_btn.clicked.connect(self._build_local_mode)
        right_layout.addWidget(self.local_mode_btn)

        self.auto_setup_btn = QPushButton("Auto Setup Selected Module (Recommended)")
        self.auto_setup_btn.clicked.connect(self._auto_setup_selected)
        right_layout.addWidget(self.auto_setup_btn)

        self.prepare_selected_cache_btn = QPushButton("Prepare Cache For Selected Module")
        self.prepare_selected_cache_btn.clicked.connect(self._prepare_selected_cache)
        right_layout.addWidget(self.prepare_selected_cache_btn)

        self.cancel_task_btn = QPushButton("Stop Current Task")
        self.cancel_task_btn.clicked.connect(self._cancel_task)
        right_layout.addWidget(self.cancel_task_btn)

        setup_btn_style = """
            QPushButton {
                background-color: #2a3340;
                color: #f2f6fb;
                border: 1px solid #4e5d70;
                border-radius: 6px;
                padding: 6px 9px;
                font-size: 10px;
                font-weight: 700;
                text-align: left;
            }
            QPushButton:hover { background-color: #334154; }
            QPushButton:pressed { background-color: #273445; }
            QPushButton:disabled {
                background-color: #1c232d;
                color: #7f8a97;
                border: 1px solid #384352;
            }
        """
        for btn in (
            self.install_btn,
            self.train_btn,
            self.cache_btn,
            self.doctor_btn,
            self.local_mode_btn,
            self.auto_setup_btn,
            self.prepare_selected_cache_btn,
            self.cancel_task_btn,
        ):
            btn.setStyleSheet(setup_btn_style)

        self.cancel_task_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #46252a;
                color: #ffe9e9;
                border: 1px solid #7b3d45;
                border-radius: 6px;
                padding: 6px 9px;
                font-size: 10px;
                font-weight: 700;
                text-align: left;
            }
            QPushButton:hover { background-color: #5b2e35; }
            QPushButton:pressed { background-color: #3b1d22; }
            QPushButton:disabled {
                background-color: #2a1f21;
                color: #8a7678;
                border: 1px solid #4a3739;
            }
            """
        )

        self.auto_setup_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #274a2b;
                color: #eff9f0;
                border: 1px solid #4f8a57;
                border-radius: 6px;
                padding: 6px 9px;
                font-size: 10px;
                font-weight: 800;
                text-align: left;
            }
            QPushButton:hover { background-color: #2f5a34; }
            QPushButton:pressed { background-color: #244528; }
            QPushButton:disabled {
                background-color: #1e2c20;
                color: #829388;
                border: 1px solid #3a4c3d;
            }
            """
        )

        self.task_log = QPlainTextEdit()
        self.task_log.setReadOnly(True)
        self.task_log.setMinimumHeight(100)
        self.task_log.setStyleSheet(
            "QPlainTextEdit { background: #f7f8fb; color: #111111; border: 1px solid #c8d0dd; font-size: 11px; }"
        )
        right_layout.addWidget(self.task_log, stretch=1)

        self.task_progress_label = QLabel("No task running")
        self.task_progress_label.setStyleSheet("color: #d5dfed; font-size: 10px;")
        right_layout.addWidget(self.task_progress_label)

        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress.setFormat("%p%")
        self.task_progress.setTextVisible(True)
        self.task_progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #4b5c72;
                border-radius: 5px;
                background: #101722;
                color: #edf2f8;
                text-align: center;
                height: 16px;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #2f6fb2;
                border-radius: 4px;
            }
            """
        )
        right_layout.addWidget(self.task_progress)

    def showEvent(self, event):
        super().showEvent(event)
        if self._warned_once:
            return
        self._warned_once = True
        QTimer.singleShot(250, self._maybe_prompt_install)

    def _on_persona_button_clicked(self) -> None:
        if self.sender() is self.btn_trump:
            self._set_persona("trump")
        elif self.sender() is self.btn_biden:
            self._set_persona("biden")

    def _set_persona(self, persona: str) -> None:
        self.persona = persona
        self.btn_trump.setChecked(persona == "trump")
        self.btn_biden.setChecked(persona == "biden")
        self._style_persona_buttons()

        self.subtitle.setText(f"Persona: {self.persona.upper()} | Choose one module and start")
        self._refresh_availability()
        self._sync_visual_selection()

    def _style_persona_buttons(self) -> None:
        trump_selected = self.btn_trump.isChecked()
        biden_selected = self.btn_biden.isChecked()

        self.btn_trump.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {'#b12c2c' if trump_selected else '#1e2630'};
                color: {'white' if trump_selected else '#c5ceda'};
                border: 1px solid {'#ff7a7a' if trump_selected else '#445161'};
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )
        self.btn_biden.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {'#2853a8' if biden_selected else '#1e2630'};
                color: {'white' if biden_selected else '#c5ceda'};
                border: 1px solid {'#7eb2ff' if biden_selected else '#445161'};
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )

    def _refresh_availability(self, force_probe: bool = False) -> None:
        qwen_info = self._qwen_state(force_probe=force_probe)
        xtts_info = self._xtts_state(force_probe=force_probe)
        script_payload = load_script(self.project_root)
        deterministic_ready = bool(script_payload)
        deterministic_fingerprint = ""
        if script_payload:
            try:
                deterministic_fingerprint = script_fingerprint(script_payload)[:12]
            except Exception:
                deterministic_fingerprint = ""

        azure_brain_ready = bool(
            settings.azure_openai_key and settings.azure_openai_endpoint and settings.azure_openai_deployment
        )
        azure_voice_ready = bool(settings.azure_speech_key and settings.azure_speech_region)

        self._availability = {
            "azure_brain_ready": azure_brain_ready,
            "azure_voice_ready": azure_voice_ready,
            "deterministic_cache_ready": deterministic_ready,
            "deterministic_fingerprint": deterministic_fingerprint,
            **qwen_info,
            **xtts_info,
        }

        self._update_notes()
        self._update_status_panel()
        self._update_setup_buttons()

    def _qwen_state(self, force_probe: bool = False) -> dict:
        model_dir = self.project_root / "data" / "models" / f"qwen-2.5-0.5b-finetuned-{self.persona}"
        local_ready = model_dir.exists()
        hf_token = bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"))

        deps_missing = self._missing_modules(
            ["torch", "transformers", "peft", "datasets", "accelerate", "huggingface_hub"]
        )
        runtime_ok = False
        runtime_detail = ""
        if not deps_missing:
            runtime_ok, runtime_detail = self._probe_qwen_runtime(force=force_probe)

        issues: list[str] = []
        if deps_missing:
            issues.append(f"dependencies missing ({', '.join(deps_missing)})")
        if not deps_missing and not runtime_ok:
            issues.append(runtime_detail)
        if not local_ready and not hf_token:
            issues.append("no local adapter and no HF token fallback")

        return {
            "qwen_local_ready": local_ready,
            "qwen_hf_token": hf_token,
            "qwen_deps_missing": deps_missing,
            "qwen_runtime_ready": runtime_ok,
            "qwen_runtime_detail": runtime_detail,
            "qwen_ready": len(issues) == 0,
            "qwen_issues": issues,
        }

    def _probe_qwen_runtime(self, force: bool = False) -> tuple[bool, str]:
        now = time.monotonic()
        if (
            not force
            and self._qwen_runtime_probe_cache is not None
            and (now - self._qwen_runtime_probe_cache[0]) < self._qwen_runtime_probe_ttl_sec
        ):
            return self._qwen_runtime_probe_cache[1], self._qwen_runtime_probe_cache[2]

        probe_code = (
            "import json\n"
            "payload={'ready': False, 'error': ''}\n"
            "try:\n"
            "    import torch\n"
            "    from PyQt6.QtWidgets import QApplication\n"
            "    import transformers\n"
            "    import peft\n"
            "    import src.brain.qwen_brain\n"
            "    payload['ready'] = True\n"
            "except Exception as exc:\n"
            "    payload['error'] = str(exc)\n"
            "print(json.dumps(payload))\n"
        )

        ready = False
        detail = "Qwen runtime probe failed"
        try:
            completed = subprocess.run(
                [sys.executable, "-c", probe_code],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=45,
            )
            if completed.returncode != 0:
                error_text = (completed.stderr or completed.stdout or "").strip()
                if error_text:
                    error_text = error_text.replace("\n", " ").strip()
                    if len(error_text) > 140:
                        error_text = error_text[:137] + "..."
                    detail = f"Qwen runtime import failed: {error_text}"
                else:
                    detail = f"Qwen runtime probe failed (exit {completed.returncode})"
            else:
                lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
                payload = json.loads(lines[-1]) if lines else {}
                ready = bool(payload.get("ready", False))
                if ready:
                    detail = ""
                else:
                    error_text = str(payload.get("error", "") or "").strip()
                    detail = "Qwen runtime import failed"
                    if error_text:
                        if len(error_text) > 140:
                            error_text = error_text[:137] + "..."
                        detail = f"{detail}: {error_text}"
        except Exception as exc:
            detail = f"Qwen runtime probe failed ({type(exc).__name__})"

        self._qwen_runtime_probe_cache = (time.monotonic(), ready, detail)
        return ready, detail

    def _xtts_state(self, force_probe: bool = False) -> dict:
        deps_missing = self._missing_modules(["torch", "torchaudio", "TTS", "soundfile"])
        runtime_ok = False
        runtime_detail = ""

        ref_selected = self.project_root / "data" / f"raw_{self.persona}" / "ref.wav"
        ref_siskind = self.project_root / "data" / "raw_siskind" / "ref.wav"

        selected_ref_ready = ref_selected.exists()
        siskind_ref_ready = ref_siskind.exists()

        cache_selected_dir = self.project_root / "data" / "xtts_cache" / self.persona
        cache_siskind_dir = self.project_root / "data" / "xtts_cache" / "siskind"
        selected_cache_count = len(list(cache_selected_dir.glob("*.wav"))) if cache_selected_dir.is_dir() else 0
        siskind_cache_count = len(list(cache_siskind_dir.glob("*.wav"))) if cache_siskind_dir.is_dir() else 0

        issues: list[str] = []
        if deps_missing:
            issues.append(f"dependencies missing ({', '.join(deps_missing)})")
        else:
            runtime_ok, runtime_detail = self._probe_xtts_runtime(force=force_probe)
            if not runtime_ok:
                issues.append(runtime_detail)
        if not selected_ref_ready:
            issues.append(f"missing ref.wav for {self.persona}")
        if not siskind_ref_ready:
            issues.append("missing ref.wav for siskind")

        xtts_ready = len(issues) == 0
        cache_profile_ready = xtts_ready and selected_cache_count > 0 and siskind_cache_count > 0

        return {
            "xtts_deps_missing": deps_missing,
            "xtts_ready": xtts_ready,
            "xtts_issues": issues,
            "xtts_ref_selected_ready": selected_ref_ready,
            "xtts_ref_siskind_ready": siskind_ref_ready,
            "xtts_cache_selected_count": selected_cache_count,
            "xtts_cache_siskind_count": siskind_cache_count,
            "xtts_runtime_ready": runtime_ok,
            "xtts_runtime_detail": runtime_detail,
            "cache_profile_ready": cache_profile_ready,
        }

    def _probe_xtts_runtime(self, force: bool = False) -> tuple[bool, str]:
        now = time.monotonic()
        if (
            not force
            and self._xtts_runtime_probe_cache is not None
            and (now - self._xtts_runtime_probe_cache[0]) < self._xtts_runtime_probe_ttl_sec
        ):
            return self._xtts_runtime_probe_cache[1], self._xtts_runtime_probe_cache[2]

        probe_code = (
            "import json\n"
            "import torch\n"
            "from PyQt6.QtWidgets import QApplication\n"
            "from src.audio import xtts_speaker as m\n"
            "print(json.dumps({'ready': bool(getattr(m, 'XTTS_AVAILABLE', False)), "
            "'error': str(getattr(m, 'XTTS_IMPORT_ERROR', '') or '')}))\n"
        )

        ready = False
        detail = "XTTS runtime probe failed"
        try:
            completed = subprocess.run(
                [sys.executable, "-c", probe_code],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=45,
            )
            if completed.returncode != 0:
                error_text = (completed.stderr or completed.stdout or "").strip()
                if error_text:
                    error_text = error_text.replace("\n", " ").strip()
                    if len(error_text) > 140:
                        error_text = error_text[:137] + "..."
                    detail = f"XTTS runtime import failed: {error_text}"
                else:
                    detail = f"XTTS runtime probe failed (exit {completed.returncode})"
            else:
                lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
                payload = json.loads(lines[-1]) if lines else {}
                ready = bool(payload.get("ready", False))
                if ready:
                    detail = ""
                else:
                    error_text = str(payload.get("error", "") or "").strip()
                    detail = "XTTS runtime import failed"
                    if error_text:
                        if len(error_text) > 140:
                            error_text = error_text[:137] + "..."
                        detail = f"{detail}: {error_text}"
        except Exception as exc:
            detail = f"XTTS runtime probe failed ({type(exc).__name__})"

        self._xtts_runtime_probe_cache = (time.monotonic(), ready, detail)
        return ready, detail

    @staticmethod
    def _missing_modules(modules: list[str]) -> list[str]:
        importlib.invalidate_caches()
        missing: list[str] = []
        for mod in modules:
            if importlib.util.find_spec(mod) is None:
                missing.append(mod)
        return missing

    def _update_notes(self) -> None:
        if self._availability["qwen_ready"]:
            source = "local adapter" if self._availability["qwen_local_ready"] else "HF fallback"
            self.brain_note.setText(f"Qwen: ready ({source})")
            self.brain_note.setStyleSheet(f"color: {COLORS['ok']}; font-size: 10px;")
        else:
            self.brain_note.setText("Qwen: unavailable - " + "; ".join(self._availability["qwen_issues"]))
            self.brain_note.setStyleSheet(f"color: {COLORS['warn']}; font-size: 10px;")

        if self._availability["xtts_ready"]:
            self.voice_note.setText(
                f"XTTS: ready ({self._availability['xtts_cache_selected_count']} {self.persona} cache, "
                f"{self._availability['xtts_cache_siskind_count']} siskind cache)"
            )
            self.voice_note.setStyleSheet(f"color: {COLORS['ok']}; font-size: 10px;")
        else:
            self.voice_note.setText("XTTS: unavailable - " + "; ".join(self._availability["xtts_issues"]))
            self.voice_note.setStyleSheet(f"color: {COLORS['warn']}; font-size: 10px;")

        deterministic_ready = self._availability.get("deterministic_cache_ready", False)
        fingerprint = self._availability.get("deterministic_fingerprint", "")
        if deterministic_ready and self._availability["cache_profile_ready"] and self._availability["qwen_local_ready"]:
            self.cache_note.setText(
                "Cached profile ready (deterministic script + XTTS cache + local Qwen). "
                f"Sync ID: {fingerprint or 'n/a'}"
            )
            self.cache_note.setStyleSheet(f"color: {COLORS['ok']}; font-size: 10px;")
        elif deterministic_ready:
            self.cache_note.setText(
                "Deterministic cached script is ready. Prepare XTTS cache for zero-latency cloned voice. "
                f"Sync ID: {fingerprint or 'n/a'}"
            )
            self.cache_note.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
        else:
            self.cache_note.setText("Cached script not prepared yet. Use 'Prepare Cache For Selected Module'.")
            self.cache_note.setStyleSheet(f"color: {COLORS['warn']}; font-size: 10px;")

    def _update_status_panel(self) -> None:
        rows = [
            ("Azure OpenAI", self._availability.get("azure_brain_ready", False)),
            ("Azure Speech", self._availability.get("azure_voice_ready", False)),
            (f"Qwen model ({self.persona})", self._availability.get("qwen_local_ready", False)),
            ("Qwen dependencies", len(self._availability.get("qwen_deps_missing", [])) == 0),
            ("Qwen runtime", self._availability.get("qwen_runtime_ready", False)),
            (f"XTTS ref ({self.persona})", self._availability.get("xtts_ref_selected_ready", False)),
            ("XTTS ref (siskind)", self._availability.get("xtts_ref_siskind_ready", False)),
            ("XTTS dependencies", len(self._availability.get("xtts_deps_missing", [])) == 0),
            ("XTTS runtime", self._availability.get("xtts_runtime_ready", False)),
            ("Deterministic script cache", self._availability.get("deterministic_cache_ready", False)),
            (
                "XTTS cache profile",
                self._availability.get("cache_profile_ready", False),
            ),
        ]

        lines = []
        for name, ok in rows:
            lines.append(f"[{'OK' if ok else 'MISSING'}] {name}")

        fingerprint = self._availability.get("deterministic_fingerprint", "")
        if fingerprint:
            lines.append(f"[INFO] Session sync fingerprint: {fingerprint}")
            lines.append("[INFO] For dual-laptop debates, both machines should show the same fingerprint.")

        self.status_panel.setText("\n".join(lines))

    def _update_setup_buttons(self) -> None:
        running = self._is_task_running()

        self.install_btn.setEnabled(not running)
        self.train_btn.setEnabled(not running)
        self.cache_btn.setEnabled(not running)
        self.doctor_btn.setEnabled(not running)
        self.local_mode_btn.setEnabled(not running)
        self.auto_setup_btn.setEnabled(not running)
        self.prepare_selected_cache_btn.setEnabled(not running)
        self.cancel_task_btn.setEnabled(running and not self._cancel_requested)
        self.start_live_btn.setEnabled(not running)
        self.start_cached_btn.setEnabled(not running)

    def _is_task_running(self) -> bool:
        return (
            self._task_process is not None
            and self._task_process.state() != QProcess.ProcessState.NotRunning
        )

    def _combo_button_style(self, checked: bool, available: bool) -> str:
        if checked and not available:
            bg = "#3a2b1d"
            border = "#d8a35d"
            text = "#fff4df"
        elif not available:
            bg = "#161c24"
            border = "#3a4452"
            text = "#788392"
        elif checked:
            bg = "#263341"
            border = "#73b2ff"
            text = "#f4f8ff"
        else:
            bg = "#1b2330"
            border = "#4b5869"
            text = "#d0d8e3"

        return f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 6px 8px;
                text-align: left;
                font-size: 10px;
                font-weight: 700;
            }}
            QPushButton:pressed {{ background-color: #233140; }}
        """

    def _combo_unavailable_reasons(self, key: str) -> list[str]:
        reasons: list[str] = []
        if key == "azure_robotic":
            if not self._availability.get("azure_brain_ready"):
                reasons.append("Azure OpenAI not configured")
            if not self._availability.get("azure_voice_ready"):
                reasons.append("Azure Speech not configured")
        elif key == "qwen_robotic":
            if not self._availability.get("qwen_ready"):
                reasons.append("Qwen not ready")
            if not self._availability.get("azure_voice_ready"):
                reasons.append("Azure Speech not configured")
        elif key == "azure_cloned":
            if not self._availability.get("azure_brain_ready"):
                reasons.append("Azure OpenAI not configured")
            if not self._availability.get("xtts_ready"):
                reasons.append("XTTS not ready")
        elif key == "qwen_cloned":
            if not self._availability.get("qwen_local_ready"):
                reasons.append("Local Qwen adapter missing")
            if not self._availability.get("xtts_ready"):
                reasons.append("XTTS not ready")
            if not self._availability.get("cache_profile_ready"):
                reasons.append("XTTS cache profile incomplete")
        return reasons

    def _is_combo_available(self, key: str) -> bool:
        return len(self._combo_unavailable_reasons(key)) == 0

    def _sync_visual_selection(self) -> None:
        for key, btn in self.combo_buttons.items():
            available = self._is_combo_available(key)
            btn.setChecked(key == self._selected_combo)
            btn.setStyleSheet(self._combo_button_style(btn.isChecked(), available))
            if available:
                btn.setToolTip(COMBOS[key]["summary"])
            else:
                btn.setToolTip("; ".join(self._combo_unavailable_reasons(key)))

        self._selected_brain = COMBOS[self._selected_combo]["brain"]
        self._selected_voice = COMBOS[self._selected_combo]["voice"]
        self.module_note.setText(COMBOS[self._selected_combo]["summary"])
        self.auto_setup_btn.setText(
            f"Auto Setup ({COMBOS[self._selected_combo]['title']})"
        )
        self.prepare_selected_cache_btn.setText(
            f"Prepare Cache ({COMBOS[self._selected_combo]['title']})"
        )

    def _on_combo_selected(self, combo_key: str) -> None:
        if combo_key not in COMBOS:
            return
        self._selected_combo = combo_key
        self._sync_visual_selection()

    def _cached_unavailable_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self._availability.get("deterministic_cache_ready", False):
            reasons.append("deterministic script cache is missing")
        if self._selected_voice == "xtts" and not self._availability.get("cache_profile_ready", False):
            reasons.append("XTTS cache profile is incomplete")
        return reasons

    def _on_start(self, run_mode: str) -> None:
        if self._is_task_running():
            self._show_warning("Task Running", "Wait for the setup task to finish before starting.")
            return

        reasons = self._combo_unavailable_reasons(self._selected_combo)
        if reasons:
            self._show_error(
                "Configuration Unavailable",
                "Cannot start selected module:\n- " + "\n- ".join(reasons),
            )
            return

        if run_mode == "cached":
            cache_reasons = self._cached_unavailable_reasons()
            if cache_reasons:
                proceed = self._ask_yes_no(
                    "Cached Assets Incomplete",
                    "Cached mode may fall back to live generation because:\n- "
                    + "\n- ".join(cache_reasons)
                    + "\n\nPrepare cache now for low-latency runs.",
                    yes_label="Start Anyway",
                    no_label="Cancel",
                )
                if not proceed:
                    return

        self.mode_selected.emit(self.persona, self._selected_brain, self._selected_voice, run_mode)
        self.close()

    def _message_box(self, icon: QMessageBox.Icon, title: str, text: str) -> QMessageBox:
        msg = QMessageBox()
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
        msg.setTextFormat(Qt.TextFormat.PlainText)
        msg.setStyleSheet(
            """
            QWidget { background-color: #f6f7f9; color: #111111; }
            QLabel#qt_msgbox_label, QLabel#qt_msgbox_informativelabel { color: #111111; min-width: 460px; }
            QMessageBox QPushButton {
                background-color: #f2f4f8;
                color: #111111;
                border: 1px solid #b6c0cf;
                border-radius: 5px;
                padding: 6px 10px;
                min-width: 96px;
            }
            QMessageBox QPushButton:hover { background-color: #e7ebf2; }
            """
        )
        return msg

    def _show_info(self, title: str, text: str) -> None:
        msg = self._message_box(QMessageBox.Icon.Information, title, text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _show_warning(self, title: str, text: str) -> None:
        msg = self._message_box(QMessageBox.Icon.Warning, title, text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _show_error(self, title: str, text: str) -> None:
        msg = self._message_box(QMessageBox.Icon.Critical, title, text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _ask_yes_no(self, title: str, text: str, yes_label: str = "Yes", no_label: str = "No") -> bool:
        msg = self._message_box(QMessageBox.Icon.Question, title, text)
        yes_btn = msg.addButton(yes_label, QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(no_label, QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        return msg.clickedButton() is yes_btn

    def _maybe_prompt_install(self) -> None:
        missing_parts = []
        if self._availability.get("qwen_deps_missing"):
            missing_parts.append("Qwen dependencies")
        elif not self._availability.get("qwen_runtime_ready", False):
            missing_parts.append("Qwen runtime")
        if self._availability.get("xtts_deps_missing"):
            missing_parts.append("XTTS dependencies")
        elif not self._availability.get("xtts_runtime_ready", False):
            missing_parts.append("XTTS runtime")

        if not missing_parts:
            return

        msg = self._message_box(
            QMessageBox.Icon.Warning,
            "Missing Optional Dependencies",
            "Detected missing components: "
            + ", ".join(missing_parts)
            + ".\nInstall now or continue with available modules.",
        )
        install_btn = msg.addButton("Install Now", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Ignore", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() is install_btn:
            self._install_missing()

    def _install_missing(self) -> None:
        self._qwen_runtime_probe_cache = None
        self._xtts_runtime_probe_cache = None
        self._refresh_availability(force_probe=True)

        args = [str(self.project_root / "scripts" / "bootstrap.py")]
        if self._availability.get("qwen_deps_missing") or not self._availability.get("qwen_runtime_ready", False):
            args.append("--qwen")
        if self._availability.get("xtts_deps_missing") or not self._availability.get("xtts_runtime_ready", False):
            args.append("--xtts")
        args.append("--doctor")

        if len(args) == 2:
            self._show_info("Nothing To Install", "No missing optional dependencies detected.")
            return

        self._run_task("Install Missing Dependencies", args)

    def _train_qwen(self) -> None:
        if self._availability.get("qwen_deps_missing") or not self._availability.get("qwen_runtime_ready", False):
            install = self._ask_yes_no(
                "Qwen Runtime Not Ready",
                "Qwen dependencies/runtime are not ready. Install/repair now?",
                yes_label="Install Now",
                no_label="Continue Anyway",
            )
            if install:
                self._run_task(
                    "Install Qwen Dependencies",
                    [str(self.project_root / "scripts" / "bootstrap.py"), "--qwen", "--doctor"],
                )
                return

        dataset = self.project_root / "data" / f"{self.persona}_train.jsonl"
        if not dataset.exists():
            self._show_warning(
                "Dataset Missing",
                f"Expected dataset not found: {dataset.name}.\nPlace it under data/ then retry.",
            )
            return

        self._run_task(
            f"Train Qwen ({self.persona})",
            [str(self.project_root / "scripts" / "finetune_qwen.py"), "--persona", self.persona],
        )

    def _prepare_xtts_cache(self) -> None:
        if self._availability.get("xtts_deps_missing") or not self._availability.get("xtts_runtime_ready", False):
            install = self._ask_yes_no(
                "XTTS Runtime Not Ready",
                "XTTS dependencies/runtime are not ready. Install/repair now?",
                yes_label="Install Now",
                no_label="Continue Anyway",
            )
            if install:
                self._run_task(
                    "Install XTTS Dependencies",
                    [str(self.project_root / "scripts" / "bootstrap.py"), "--xtts", "--doctor"],
                )
                return

        ref_selected = self.project_root / "data" / f"raw_{self.persona}" / "ref.wav"
        ref_siskind = self.project_root / "data" / "raw_siskind" / "ref.wav"
        if not ref_selected.exists() or not ref_siskind.exists():
            self._show_warning(
                "Reference Voice Missing",
                "Missing ref.wav for selected persona or siskind.\nAdd both files first.",
            )
            return

        self._run_task(
            f"Prepare XTTS Cache ({self.persona} + siskind)",
            [
                str(self.project_root / "scripts" / "build_local_mode.py"),
                "--persona",
                self.persona,
                "--skip-install",
                "--skip-train",
            ],
        )

    def _run_doctor(self) -> None:
        self._run_task(
            "Doctor Check",
            [str(self.project_root / "scripts" / "doctor.py"), "--rag", "--qwen", "--xtts"],
        )

    def _build_local_mode(self) -> None:
        self._run_task(
            "Build Full Local Cached Mode (All Personas)",
            [str(self.project_root / "scripts" / "build_local_mode.py"), "--persona", "all"],
        )

    def _auto_setup_selected(self) -> None:
        if self._is_task_running():
            self._show_warning("Task Running", "Wait for the current task to finish first.")
            return

        combo = self._selected_combo
        needs_qwen = COMBOS[combo]["brain"] == "qwen"
        needs_xtts = COMBOS[combo]["voice"] == "xtts"

        if needs_qwen and not self._availability.get("qwen_local_ready", False):
            dataset = self.project_root / "data" / f"{self.persona}_train.jsonl"
            hf_fallback = self._availability.get("qwen_hf_token", False)
            if not dataset.exists() and not hf_fallback:
                self._show_warning(
                    "Qwen Training Data Missing",
                    f"Selected module requires Qwen. Missing dataset: {dataset.name}\n"
                    "Add dataset or configure HF token fallback, then retry.",
                )
                return

        if needs_xtts:
            ref_selected = self.project_root / "data" / f"raw_{self.persona}" / "ref.wav"
            ref_siskind = self.project_root / "data" / "raw_siskind" / "ref.wav"
            if not ref_selected.exists() or not ref_siskind.exists():
                self._show_warning(
                    "Reference Voice Missing",
                    "Selected module uses XTTS and needs ref.wav for selected persona and siskind.",
                )
                return

        self._run_task(
            f"Auto Setup ({COMBOS[self._selected_combo]['title']})",
            [
                str(self.project_root / "scripts" / "setup_selected_mode.py"),
                "--persona",
                self.persona,
                "--combo",
                self._selected_combo,
            ],
            track_progress=True,
        )

    def _prepare_selected_cache(self) -> None:
        if self._selected_voice == "xtts":
            if self._availability.get("xtts_deps_missing") or not self._availability.get("xtts_runtime_ready", False):
                install = self._ask_yes_no(
                    "XTTS Runtime Not Ready",
                    "XTTS dependencies/runtime are not ready. Install/repair now?",
                    yes_label="Install Now",
                    no_label="Cancel",
                )
                if install:
                    self._run_task(
                        "Install XTTS Dependencies",
                        [str(self.project_root / "scripts" / "bootstrap.py"), "--xtts", "--doctor"],
                    )
                return

            ref_selected = self.project_root / "data" / f"raw_{self.persona}" / "ref.wav"
            ref_siskind = self.project_root / "data" / "raw_siskind" / "ref.wav"
            if not ref_selected.exists() or not ref_siskind.exists():
                self._show_warning(
                    "Reference Voice Missing",
                    "Missing ref.wav for selected persona or siskind.\nAdd both files first.",
                )
                return

        self._run_task(
            f"Prepare Cache ({COMBOS[self._selected_combo]['title']})",
            [
                str(self.project_root / "scripts" / "prepare_debate_cache.py"),
                "--persona",
                self.persona,
                "--voice",
                self._selected_voice,
            ],
            track_progress=True,
        )

    def _cancel_task(self) -> None:
        if not self._is_task_running():
            self._show_info("No Active Task", "No setup task is currently running.")
            return

        self._cancel_requested = True
        self._append_log("=== Cancel requested: stopping current task... ===")
        self.task_progress_label.setText("Stopping task...")
        self._update_setup_buttons()

        assert self._task_process is not None
        self._task_process.terminate()
        QTimer.singleShot(2500, self._force_kill_task_if_needed)

    def _force_kill_task_if_needed(self) -> None:
        if self._is_task_running() and self._task_process is not None:
            self._append_log("=== Task still running, force-killing process ===")
            self._task_process.kill()

    def _run_task(self, name: str, script_args: list[str], track_progress: bool = False) -> None:
        if self._is_task_running():
            self._show_warning("Task Running", "A setup task is already running.")
            return

        self._qwen_runtime_probe_cache = None
        self._xtts_runtime_probe_cache = None
        self._task_name = name
        self._cancel_requested = False
        self._task_tracks_progress = track_progress
        self._append_log(f"\n=== {name} ===")
        self._append_log("$ " + " ".join([sys.executable] + script_args))
        if track_progress:
            self.task_progress.setRange(0, 100)
            self.task_progress.setValue(0)
            self.task_progress_label.setText("Task progress: 0%")
        else:
            self.task_progress.setRange(0, 0)
            self.task_progress_label.setText(f"Running: {name}")

        process = QProcess(self)
        process.setWorkingDirectory(str(self.project_root))
        process.setProgram(sys.executable)
        process.setArguments(script_args)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_process_output)
        process.finished.connect(self._on_task_finished)
        process.errorOccurred.connect(self._on_task_error)
        process.start()

        self._task_process = process
        self._update_setup_buttons()

    def _read_process_output(self) -> None:
        if self._task_process is None:
            return
        data = bytes(self._task_process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        if not data:
            return

        for line in data.splitlines():
            self._append_log(line.rstrip())
            self._parse_progress_line(line)

    def _parse_progress_line(self, line: str) -> None:
        raw = (line or "").strip()
        if not raw.startswith("PROGRESS:"):
            return

        # Format: PROGRESS:<percent>:<message>
        parts = raw.split(":", 2)
        if len(parts) != 3:
            return
        try:
            percent = max(0, min(100, int(parts[1])))
        except ValueError:
            return

        self._task_tracks_progress = True
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(percent)
        self.task_progress_label.setText(parts[2].strip() or f"Task progress: {percent}%")

    def _on_task_error(self, err) -> None:
        task = self._task_name or "Task"
        self._append_log(f"=== {task} process error: {int(err)} ===")
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress_label.setText("Task process error")

    def _on_task_finished(self, exit_code: int, _status) -> None:
        task = self._task_name or "Task"
        if self._cancel_requested:
            self._append_log(f"=== {task} stopped by user (exit code {exit_code}) ===")
        else:
            self._append_log(f"=== {task} finished with exit code {exit_code} ===")

        if self._task_tracks_progress:
            self.task_progress.setRange(0, 100)
            if self._cancel_requested:
                self.task_progress_label.setText("Task cancelled")
                self.task_progress.setValue(0)
            elif exit_code == 0:
                self.task_progress_label.setText("Task completed")
                self.task_progress.setValue(100)
            else:
                self.task_progress_label.setText("Task failed")
                self.task_progress.setValue(0)
        else:
            self.task_progress.setRange(0, 100)
            self.task_progress.setValue(0)
            self.task_progress_label.setText("No task running")

        self._task_process = None
        self._task_name = None
        self._cancel_requested = False
        self._task_tracks_progress = False
        self._qwen_runtime_probe_cache = None
        self._xtts_runtime_probe_cache = None

        self._refresh_availability(force_probe=True)
        self._sync_visual_selection()
        self._update_setup_buttons()

    def _append_log(self, text: str) -> None:
        self.task_log.appendPlainText(text)
        cursor = self.task_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.task_log.setTextCursor(cursor)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    def on_mode(persona: str, brain_mode: str, voice_mode: str, run_mode: str):
        print(f"Selected persona={persona}, brain={brain_mode}, voice={voice_mode}, run={run_mode}")
        app.quit()

    selector = DebateModeSelector("trump")
    selector.mode_selected.connect(on_mode)
    selector.show()

    sys.exit(app.exec())
