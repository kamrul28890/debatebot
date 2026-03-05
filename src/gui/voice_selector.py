"""
src/gui/voice_selector.py

Dual-laptop startup selector:
- Pick local persona (Trump or Biden)
- Pick one of four live modules
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, Qt, pyqtSignal
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
    QVBoxLayout,
    QWidget,
)

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
        "summary": "Most stable cloud path.",
    },
    "qwen_robotic": {
        "brain": "qwen",
        "voice": "azure",
        "title": "Qwen + Robotic Voice",
        "summary": "Local Qwen for selected persona + Azure TTS.",
    },
    "azure_cloned": {
        "brain": "azure",
        "voice": "xtts",
        "title": "Azure + Cloned Voice",
        "summary": "Cloud brain + local XTTS voice cloning.",
    },
    "qwen_cloned": {
        "brain": "qwen",
        "voice": "xtts",
        "title": "Qwen + Cloned Voice",
        "summary": "Local Qwen + local XTTS voice cloning.",
    },
}


PERSONAS = {
    "trump": {
        "title": "Trump Laptop",
        "summary": "This machine runs Trump and waits for Biden remotely.",
        "accent": "#c63a3a",
    },
    "biden": {
        "title": "Biden Laptop",
        "summary": "This machine runs Biden and waits for Trump remotely.",
        "accent": "#355ec6",
    },
}


class DebateModeSelector(QWidget):
    """Selector for dual-laptop live mode."""

    mode_selected = pyqtSignal(str, str, str)  # persona, brain_mode, voice_mode

    def __init__(self):
        super().__init__()
        self.project_root = Path(__file__).resolve().parents[2]

        self._selected_combo = "azure_robotic"
        self._selected_persona: str | None = None

        self._availability: dict[str, object] = {}
        self._task_process: QProcess | None = None
        self._task_name: str | None = None

        self.setWindowTitle("DebateBot - Dual Laptop Selector")
        self.resize(920, 580)
        self.setMinimumSize(760, 460)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")

        self._build_ui()
        self._refresh_availability()
        self._sync_visual_selection()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        left = QFrame()
        left.setStyleSheet(
            f"QFrame {{ background: {COLORS['panel']}; border: 1px solid {COLORS['line']}; border-radius: 8px; }}"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        right = QFrame()
        right.setStyleSheet(
            f"QFrame {{ background: {COLORS['panel2']}; border: 1px solid {COLORS['line']}; border-radius: 8px; }}"
        )
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        root.addWidget(left, stretch=3)
        root.addWidget(right, stretch=2)

        title = QLabel("DUAL-LAPTOP LIVE SELECTOR")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: 19px; font-weight: 900;")
        left_layout.addWidget(title)

        subtitle = QLabel("Select local persona + one of four live modules (no pre-recorded mode).")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
        left_layout.addWidget(subtitle)

        modules_lbl = QLabel("Modules (4 options)")
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
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _checked, k=key: self._on_combo_selected(k))
            self.combo_group.addButton(btn)
            self.combo_buttons[key] = btn
            row, col = divmod(idx, 2)
            grid.addWidget(btn, row, col)

        left_layout.addLayout(grid)

        persona_lbl = QLabel("Choose This Laptop Persona")
        persona_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        persona_lbl.setStyleSheet(f"color: {COLORS['text']}; font-size: 13px; font-weight: 700;")
        left_layout.addWidget(persona_lbl)

        persona_row = QHBoxLayout()
        persona_row.setSpacing(8)

        self.persona_group = QButtonGroup(self)
        self.persona_group.setExclusive(True)
        self.persona_buttons: dict[str, QPushButton] = {}
        for key, meta in PERSONAS.items():
            btn = QPushButton(f"{meta['title']}\n{meta['summary']}")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _checked, p=key: self._on_persona_selected(p))
            persona_row.addWidget(btn)
            self.persona_group.addButton(btn)
            self.persona_buttons[key] = btn

        left_layout.addLayout(persona_row)

        self.persona_note = QLabel("Select Trump or Biden for this laptop.")
        self.persona_note.setWordWrap(True)
        self.persona_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.persona_note.setStyleSheet(f"color: {COLORS['warn']}; font-size: 10px;")
        left_layout.addWidget(self.persona_note)

        self.module_note = QLabel("")
        self.module_note.setWordWrap(True)
        self.module_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.module_note.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
        left_layout.addWidget(self.module_note)

        self.availability_note = QLabel("")
        self.availability_note.setWordWrap(True)
        self.availability_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.availability_note.setStyleSheet(f"color: {COLORS['muted']}; font-size: 10px;")
        left_layout.addWidget(self.availability_note)

        left_layout.addStretch()

        self.start_btn = QPushButton("Start Dual-Laptop Debate")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLORS['button']};
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 13px;
                font-weight: 900;
            }}
            QPushButton:hover {{ background-color: {COLORS['button_hover']}; }}
            QPushButton:pressed {{ background-color: {COLORS['button_pressed']}; }}
            QPushButton:disabled {{ background-color: #5d3030; color: #ccb9b9; }}
            """
        )
        self.start_btn.clicked.connect(self._on_start)
        left_layout.addWidget(self.start_btn)

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

        action_style = (
            "QPushButton { background-color: #2a3340; color: #f2f6fb; border: 1px solid #4e5d70; border-radius: 6px; "
            "padding: 6px 9px; font-size: 10px; font-weight: 700; text-align: left; } "
            "QPushButton:hover { background-color: #334154; } "
            "QPushButton:pressed { background-color: #273445; } "
            "QPushButton:disabled { background-color: #1c232d; color: #7f8a97; border: 1px solid #384352; }"
        )

        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.clicked.connect(self._refresh_availability)
        self.refresh_btn.setStyleSheet(action_style)
        right_layout.addWidget(self.refresh_btn)

        self.install_btn = QPushButton("Install Missing Optional Runtime")
        self.install_btn.clicked.connect(self._install_missing)
        self.install_btn.setStyleSheet(action_style)
        right_layout.addWidget(self.install_btn)

        self.doctor_btn = QPushButton("Run Doctor")
        self.doctor_btn.clicked.connect(self._run_doctor)
        self.doctor_btn.setStyleSheet(action_style)
        right_layout.addWidget(self.doctor_btn)

        self.cancel_task_btn = QPushButton("Stop Current Task")
        self.cancel_task_btn.clicked.connect(self._cancel_task)
        self.cancel_task_btn.setStyleSheet(
            "QPushButton { background-color: #46252a; color: #ffe9e9; border: 1px solid #7b3d45; border-radius: 6px; "
            "padding: 6px 9px; font-size: 10px; font-weight: 700; text-align: left; } "
            "QPushButton:hover { background-color: #5b2e35; } "
            "QPushButton:pressed { background-color: #3b1d22; } "
            "QPushButton:disabled { background-color: #2a1f21; color: #8a7678; border: 1px solid #4a3739; }"
        )
        right_layout.addWidget(self.cancel_task_btn)

        self.task_log = QPlainTextEdit()
        self.task_log.setReadOnly(True)
        self.task_log.setMinimumHeight(120)
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
            "QProgressBar { border: 1px solid #4b5c72; border-radius: 5px; background: #101722; color: #edf2f8; text-align: center; "
            "height: 16px; font-size: 10px; } "
            "QProgressBar::chunk { background-color: #2f6fb2; border-radius: 4px; }"
        )
        right_layout.addWidget(self.task_progress)

        self._update_buttons()

    def _on_combo_selected(self, combo_key: str) -> None:
        if combo_key not in COMBOS:
            return
        self._selected_combo = combo_key
        self._sync_visual_selection()

    def _on_persona_selected(self, persona: str) -> None:
        if persona not in PERSONAS:
            return
        self._selected_persona = persona
        self._refresh_availability()
        self._sync_visual_selection()

    def _sync_visual_selection(self) -> None:
        for key, btn in self.combo_buttons.items():
            available = self._is_combo_available(key)
            checked = key == self._selected_combo
            btn.setChecked(checked)
            btn.setStyleSheet(self._combo_button_style(checked, available))
            if available:
                btn.setToolTip(COMBOS[key]["summary"])
            else:
                btn.setToolTip("; ".join(self._combo_unavailable_reasons(key)))

        for key, btn in self.persona_buttons.items():
            selected = key == self._selected_persona
            btn.setChecked(selected)
            btn.setStyleSheet(self._persona_button_style(selected, PERSONAS[key]["accent"]))

        combo = COMBOS[self._selected_combo]
        self.module_note.setText(f"Selected module: {combo['title']} - {combo['summary']}")

        if self._selected_persona is None:
            self.persona_note.setText("Choose the local persona. Set the other laptop to the opposite persona.")
            self.persona_note.setStyleSheet(f"color: {COLORS['warn']}; font-size: 10px;")
        else:
            other = "biden" if self._selected_persona == "trump" else "trump"
            self.persona_note.setText(
                f"This laptop runs {self._selected_persona.upper()}. Set the other laptop to {other.upper()}."
            )
            self.persona_note.setStyleSheet(f"color: {COLORS['ok']}; font-size: 10px;")

        qwen_note = "Qwen ready" if self._availability.get("qwen_ready") else "Qwen unavailable"
        xtts_note = "XTTS ready" if self._availability.get("xtts_ready") else "XTTS unavailable"
        self.availability_note.setText(f"Runtime summary: {qwen_note} | {xtts_note}")
        if self._availability.get("qwen_ready") and self._availability.get("xtts_ready"):
            self.availability_note.setStyleSheet(f"color: {COLORS['ok']}; font-size: 10px;")
        else:
            self.availability_note.setStyleSheet(f"color: {COLORS['warn']}; font-size: 10px;")

        self._update_buttons()

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

        return (
            "QPushButton {"
            f"background-color: {bg}; color: {text}; border: 1px solid {border}; border-radius: 7px; "
            "padding: 6px 8px; text-align: left; font-size: 10px; font-weight: 700;"
            "}"
            "QPushButton:pressed { background-color: #233140; }"
        )

    @staticmethod
    def _persona_button_style(selected: bool, accent: str) -> str:
        bg = accent if selected else "#263240"
        border = accent if selected else "#47586a"
        text = "white" if selected else "#d5e3f0"
        return (
            "QPushButton {"
            f"background-color: {bg}; color: {text}; border: 1px solid {border}; border-radius: 6px; "
            "padding: 6px 8px; font-size: 10px; font-weight: 700; text-align: left;"
            "}"
        )

    def _refresh_availability(self) -> None:
        qwen_info = self._qwen_state()
        xtts_info = self._xtts_state()

        azure_brain_ready = bool(
            settings.azure_openai_key and settings.azure_openai_endpoint and settings.azure_openai_deployment
        )
        azure_voice_ready = bool(settings.azure_speech_key and settings.azure_speech_region)

        self._availability = {
            "azure_brain_ready": azure_brain_ready,
            "azure_voice_ready": azure_voice_ready,
            **qwen_info,
            **xtts_info,
        }

        self._update_status_panel()
        self._sync_visual_selection()

    def _qwen_state(self) -> dict[str, object]:
        models = {
            "trump": (self.project_root / "data" / "models" / "qwen-2.5-0.5b-finetuned-trump").exists(),
            "biden": (self.project_root / "data" / "models" / "qwen-2.5-0.5b-finetuned-biden").exists(),
        }
        hf_token = bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"))

        deps_missing = self._missing_modules(
            ["torch", "transformers", "peft", "datasets", "accelerate", "huggingface_hub"]
        )

        issues: list[str] = []
        if deps_missing:
            issues.append(f"dependencies missing ({', '.join(deps_missing)})")

        selected = self._selected_persona
        if selected is None:
            local_model_ready = all(models.values())
            missing_personas = [p for p, ok in models.items() if not ok]
            if not local_model_ready and not hf_token:
                issues.append("missing local Qwen adapters for " + ", ".join(missing_personas))
                issues.append("set HF_TOKEN/HUGGINGFACE_TOKEN to allow remote fallback")
        else:
            local_model_ready = bool(models.get(selected, False))
            if not local_model_ready and not hf_token:
                issues.append(f"missing local Qwen adapter for selected persona ({selected})")
                issues.append("set HF_TOKEN/HUGGINGFACE_TOKEN to allow remote fallback")

        return {
            "qwen_models": models,
            "qwen_hf_token": hf_token,
            "qwen_deps_missing": deps_missing,
            "qwen_ready": len(issues) == 0,
            "qwen_issues": issues,
        }

    def _xtts_state(self) -> dict[str, object]:
        deps_missing = self._missing_modules(["torch", "torchaudio", "TTS", "soundfile"])

        refs = {
            "trump": (self.project_root / "data" / "raw_trump" / "ref.wav").exists(),
            "biden": (self.project_root / "data" / "raw_biden" / "ref.wav").exists(),
        }

        issues: list[str] = []
        if deps_missing:
            issues.append(f"dependencies missing ({', '.join(deps_missing)})")

        selected = self._selected_persona
        if selected is None:
            for persona in ("trump", "biden"):
                if not refs[persona]:
                    issues.append(f"missing data/raw_{persona}/ref.wav")
        elif not refs[selected]:
            issues.append(f"missing data/raw_{selected}/ref.wav")

        return {
            "xtts_deps_missing": deps_missing,
            "xtts_refs": refs,
            "xtts_ready": len(issues) == 0,
            "xtts_issues": issues,
        }

    @staticmethod
    def _missing_modules(modules: list[str]) -> list[str]:
        importlib.invalidate_caches()
        missing: list[str] = []
        for mod in modules:
            if importlib.util.find_spec(mod) is None:
                missing.append(mod)
        return missing

    def _combo_unavailable_reasons(self, key: str) -> list[str]:
        reasons: list[str] = []
        info = COMBOS[key]

        if info["brain"] == "azure" and not self._availability.get("azure_brain_ready"):
            reasons.append("Azure OpenAI not configured")
        if info["brain"] == "qwen" and not self._availability.get("qwen_ready"):
            reasons.append("Qwen runtime/model not ready for selected persona")

        if info["voice"] == "azure" and not self._availability.get("azure_voice_ready"):
            reasons.append("Azure Speech not configured")
        if info["voice"] == "xtts" and not self._availability.get("xtts_ready"):
            reasons.append("XTTS runtime/ref files not ready for selected persona")

        return reasons

    def _is_combo_available(self, key: str) -> bool:
        return len(self._combo_unavailable_reasons(key)) == 0

    def _on_start(self) -> None:
        if self._is_task_running():
            self._show_warning("Task Running", "Wait for the setup task to finish before starting.")
            return

        if self._selected_persona is None:
            self._show_warning("Persona Required", "Select Trump or Biden for this laptop before starting.")
            return

        reasons = self._combo_unavailable_reasons(self._selected_combo)
        if reasons:
            self._show_error(
                "Configuration Unavailable",
                "Cannot start selected live module:\n- " + "\n- ".join(reasons),
            )
            return

        combo = COMBOS[self._selected_combo]
        self.mode_selected.emit(self._selected_persona, combo["brain"], combo["voice"])
        self.close()

    def _update_status_panel(self) -> None:
        qwen_models = self._availability.get("qwen_models", {})
        xtts_refs = self._availability.get("xtts_refs", {})
        selected = (self._selected_persona or "(not selected)").upper()

        rows = [
            ("Selected persona", True, selected),
            ("Azure OpenAI", self._availability.get("azure_brain_ready", False), ""),
            ("Azure Speech", self._availability.get("azure_voice_ready", False), ""),
            ("Qwen dependencies", len(self._availability.get("qwen_deps_missing", [])) == 0, ""),
            ("Qwen adapter (trump)", bool(qwen_models.get("trump", False)), ""),
            ("Qwen adapter (biden)", bool(qwen_models.get("biden", False)), ""),
            ("HF token fallback", bool(self._availability.get("qwen_hf_token", False)), ""),
            ("XTTS dependencies", len(self._availability.get("xtts_deps_missing", [])) == 0, ""),
            ("XTTS ref (trump)", bool(xtts_refs.get("trump", False)), ""),
            ("XTTS ref (biden)", bool(xtts_refs.get("biden", False)), ""),
        ]

        lines: list[str] = []
        for name, ok, extra in rows:
            if name == "Selected persona":
                lines.append(f"[INFO] {name}: {extra}")
            else:
                lines.append(f"[{'OK' if ok else 'MISSING'}] {name}")

        qwen_issues = self._availability.get("qwen_issues", [])
        xtts_issues = self._availability.get("xtts_issues", [])
        if qwen_issues:
            lines.append("[INFO] Qwen issues: " + "; ".join(qwen_issues))
        if xtts_issues:
            lines.append("[INFO] XTTS issues: " + "; ".join(xtts_issues))

        self.status_panel.setText("\n".join(lines))

    def _update_buttons(self) -> None:
        running = self._is_task_running()
        self.refresh_btn.setEnabled(not running)
        self.install_btn.setEnabled(not running)
        self.doctor_btn.setEnabled(not running)
        self.cancel_task_btn.setEnabled(running)

        can_start = (not running) and (self._selected_persona is not None)
        self.start_btn.setEnabled(can_start)

    def _is_task_running(self) -> bool:
        return self._task_process is not None and self._task_process.state() != QProcess.ProcessState.NotRunning

    def _install_missing(self) -> None:
        args = [str(self.project_root / "scripts" / "bootstrap.py")]
        qwen_missing = bool(self._availability.get("qwen_deps_missing"))
        xtts_missing = bool(self._availability.get("xtts_deps_missing"))

        if qwen_missing:
            args.append("--qwen")
        if xtts_missing:
            args.append("--xtts")
        args.append("--doctor")

        if not qwen_missing and not xtts_missing:
            self._show_info("Nothing To Install", "Optional Qwen/XTTS dependencies appear to be installed.")
            return

        self._run_task("Install Missing Optional Runtime", args)

    def _run_doctor(self) -> None:
        args = [str(self.project_root / "scripts" / "doctor.py")]
        combo = COMBOS[self._selected_combo]
        if combo["brain"] == "qwen":
            args.append("--qwen")
        if combo["voice"] == "xtts":
            args.append("--xtts")
        self._run_task("Doctor Check", args)

    def _cancel_task(self) -> None:
        if not self._is_task_running() or self._task_process is None:
            self._show_info("No Active Task", "No setup task is currently running.")
            return

        self._append_log("=== Cancel requested: stopping current task... ===")
        self.task_progress_label.setText("Stopping task...")
        self._task_process.terminate()

    def _run_task(self, name: str, script_args: list[str]) -> None:
        if self._is_task_running():
            self._show_warning("Task Running", "A setup task is already running.")
            return

        self._task_name = name
        self._append_log(f"\n=== {name} ===")
        self._append_log("$ " + " ".join([sys.executable] + script_args))

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
        self._update_buttons()

    def _read_process_output(self) -> None:
        if self._task_process is None:
            return
        data = bytes(self._task_process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        if not data:
            return

        for line in data.splitlines():
            self._append_log(line.rstrip())

    def _on_task_error(self, err) -> None:
        task = self._task_name or "Task"
        self._append_log(f"=== {task} process error: {int(err)} ===")
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress_label.setText("Task process error")

    def _on_task_finished(self, exit_code: int, _status) -> None:
        task = self._task_name or "Task"
        self._append_log(f"=== {task} finished with exit code {exit_code} ===")

        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress_label.setText("No task running")

        self._task_process = None
        self._task_name = None

        self._refresh_availability()
        self._update_buttons()

    def _append_log(self, text: str) -> None:
        self.task_log.appendPlainText(text)
        cursor = self.task_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.task_log.setTextCursor(cursor)

    def _message_box(self, icon: QMessageBox.Icon, title: str, text: str) -> QMessageBox:
        msg = QMessageBox()
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
        msg.setTextFormat(Qt.TextFormat.PlainText)
        msg.setStyleSheet(
            "QWidget { background-color: #f6f7f9; color: #111111; } "
            "QLabel#qt_msgbox_label, QLabel#qt_msgbox_informativelabel { color: #111111; min-width: 460px; } "
            "QMessageBox QPushButton { background-color: #f2f4f8; color: #111111; border: 1px solid #b6c0cf; "
            "border-radius: 5px; padding: 6px 10px; min-width: 96px; } "
            "QMessageBox QPushButton:hover { background-color: #e7ebf2; }"
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


if __name__ == "__main__":
    app = QApplication(sys.argv)

    def on_mode(persona: str, brain_mode: str, voice_mode: str) -> None:
        print(f"Selected persona={persona}, brain={brain_mode}, voice={voice_mode}")
        app.quit()

    selector = DebateModeSelector()
    selector.mode_selected.connect(on_mode)
    selector.show()

    sys.exit(app.exec())
