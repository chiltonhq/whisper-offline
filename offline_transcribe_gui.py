#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, QThread, Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QComboBox,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from first_run import start_first_run_setup
from offline_transcribe import (
    DEFAULT_QUALITY,
    SUPPORTED_EXTS,
    load_model,
    model_dir_for_quality,
    process_audio_files,
    processing_device_summary,
    runtime_base_dir,
)

THEME_DARK = "#0B0F14"
THEME_PANEL = "#111926"
THEME_BLUE = "#012169"
THEME_BLUE_LIGHT = "#1E4FA3"
THEME_BLUE_BRIGHT = "#3B6FCC"
THEME_TEXT = "#E8EEF7"
THEME_MUTED = "#9FB0CC"
PROGRESS_GREEN = "#2EBD6B"
PROGRESS_TRACK = "#1A2436"
BORDER = "#2E3C57"

PROGRESS_RE = re.compile(r"Progress:\s*(\d+)\s*%")
TRANSCRIBING_RE = re.compile(r"^Transcribing:\s*(.+)$")
FINISHED_RE = re.compile(r"^Finished:\s*(.+)$")


def _app_icon_path() -> Path | None:
    base = runtime_base_dir()
    for candidate in (base / "assets" / "app_icon.png", base.parent / "assets" / "app_icon.png"):
        if candidate.exists():
            return candidate
    return None


def _format_eta(seconds: float) -> str:
    if seconds <= 0:
        return ""
    if seconds < 60:
        return "less than 1 min remaining"
    minutes = int(round(seconds / 60))
    return f"about {minutes} min remaining" if minutes != 1 else "about 1 min remaining"


class TranscribeWorker(QThread):
    log = Signal(str)
    done = Signal()

    def __init__(
        self,
        files: list[Path],
        quality: str,
        processed_dir: Path,
        translate: bool = False,
        drop_dirs: tuple[Path, ...] = (),
    ):
        super().__init__()
        self.files = files
        self.quality = quality
        self.processed_dir = processed_dir
        self.translate = translate
        self.drop_dirs = drop_dirs

    def _should_move_audio(self, audio_path: Path) -> bool:
        # Only audio that came from DropAudioHere is moved out (so it isn't
        # queued again next launch). Files the user picked stay where they are.
        return audio_path.resolve().parent in self.drop_dirs

    def run(self) -> None:
        try:
            model_dir = model_dir_for_quality(self.quality)
            if not model_dir:
                self.log.emit(f"Model folder for '{self.quality}' is missing in this package.")
                return

            self.log.emit(f"Loading model ({self.quality}) from: {model_dir}")
            model = load_model(model_dir, logger=self.log.emit)
            process_audio_files(
                model=model,
                audio_files=self.files,
                processed_dir=self.processed_dir,
                language=None,
                logger=self.log.emit,
                task="translate" if self.translate else "transcribe",
                move_audio=self._should_move_audio,
            )
            self.log.emit("All queued files finished.")
        except Exception as exc:
            self.log.emit(f"Error: {exc}")
        finally:
            self.done.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper Offline")
        self.resize(1100, 760)

        self.base_dir = runtime_base_dir()
        self.settings = QSettings("WhisperOffline", "Whisper Offline")
        self.drop_dirs = tuple(
            d.resolve()
            for d in (self.base_dir / "DropAudioHere", self.base_dir.parent / "DropAudioHere")
            if d.is_dir()
        )
        self.processed_dir, self._output_log_message = self._resolve_processed_dir()

        self.file_paths: list[Path] = []
        self.worker: TranscribeWorker | None = None
        self._file_t_start: float = 0.0
        self._current_file_name: str = ""

        self._build_ui()
        self._apply_theme()
        if self._output_log_message:
            self._log(self._output_log_message)
        self._load_startup_files()

    def _resolve_processed_dir(self) -> tuple[Path, str]:
        """Pick where transcripts go, first usable of:

        1. the folder the user chose with "Change..." (remembered)
        2. a path in output_path.txt next to the app (for IT-managed installs)
        3. Documents\\Whisper Offline
        4. a "processed" folder inside the app folder, as a last resort
        """
        candidates: list[tuple[Path, str]] = []

        saved = self.settings.value("output_dir", "", type=str)
        if saved:
            candidates.append((Path(saved), "your saved choice"))

        for config_path in (self.base_dir / "output_path.txt", self.base_dir.parent / "output_path.txt"):
            try:
                text = config_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                candidates.append((Path(text), config_path.name))
                break

        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if documents:
            candidates.append((Path(documents) / "Whisper Offline", "default"))
        candidates.append((self.base_dir / "processed", "fallback"))

        problems: list[str] = []
        for folder, source in candidates:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                problems.append(f"{folder} ({source}) is unavailable: {exc}")
                continue
            message = f"Transcripts will be saved to: {folder}"
            if problems:
                message += "\n  " + "\n  ".join(problems)
            return folder, message

        # Every candidate failed; report the last one and let saving surface the error.
        return candidates[-1][0], "Could not create an output folder:\n  " + "\n  ".join(problems)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)

        icon_path = _app_icon_path()
        if icon_path is not None:
            icon_label = QLabel()
            pix = QPixmap(str(icon_path)).scaled(
                56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon_label.setPixmap(pix)
            icon_label.setFixedSize(56, 56)
            header.addWidget(icon_label, 0, Qt.AlignVCenter)

        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title_block.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Whisper Offline")
        title.setObjectName("title")
        subtitle = QLabel("Private, offline audio transcription")
        subtitle.setObjectName("subtitle")

        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block, 1)

        version = QLabel("v1.0")
        version.setObjectName("version")
        version.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        header.addWidget(version, 0)

        root.addLayout(header)

        separator = QFrame()
        separator.setObjectName("headerSep")
        separator.setFrameShape(QFrame.HLine)
        root.addWidget(separator)

        top_controls = QHBoxLayout()
        quality_label = QLabel("Model:")
        top_controls.addWidget(quality_label)
        self.quality = QComboBox()
        self.quality.addItem("Large — most accurate, slower", "large")
        self.quality.addItem("Medium — faster, a little less accurate", "medium")
        self.quality.setCurrentIndex(self.quality.findData(DEFAULT_QUALITY))
        top_controls.addWidget(self.quality)
        top_controls.addSpacing(20)
        self.translate_checkbox = QCheckBox("Translate non-English speech to English")
        self.translate_checkbox.setToolTip(
            "Writes the transcript in English. English speech is kept as is.\n"
            "Works with either model; Large gives the best translations."
        )
        top_controls.addWidget(self.translate_checkbox)
        top_controls.addStretch(1)
        self.device_label = QLabel(f"Runs on: {processing_device_summary()}")
        self.device_label.setObjectName("device")
        self.device_label.setToolTip(
            "Whisper Offline uses an NVIDIA GPU when the optional GPU add-on is\n"
            "installed (a 'gpu' folder next to WhisperOffline.exe). Otherwise it uses the CPU."
        )
        top_controls.addWidget(self.device_label)
        root.addLayout(top_controls)

        output_row = QHBoxLayout()
        output_row.setSpacing(10)
        output_row.addWidget(QLabel("Save transcripts to:"))
        self.output_label = QLabel()
        self.output_label.setObjectName("outputPath")
        self.output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Let a long path be clipped instead of forcing the window wider.
        self.output_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        output_row.addWidget(self.output_label, 1)
        self.change_output_btn = QPushButton("Change…")
        self.open_output_btn = QPushButton("Open")
        self.change_output_btn.clicked.connect(self._change_output_folder)
        self.open_output_btn.clicked.connect(self._open_output_folder)
        output_row.addWidget(self.change_output_btn)
        output_row.addWidget(self.open_output_btn)
        root.addLayout(output_row)
        self._show_output_dir()

        queued_label = QLabel("Queued files")
        queued_label.setObjectName("section")
        root.addWidget(queued_label)
        self.file_list = QListWidget()
        root.addWidget(self.file_list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.add_files_btn = QPushButton("Add Files")
        self.add_folder_btn = QPushButton("Add Folder")
        self.clear_btn = QPushButton("Clear")
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("startBtn")

        self.add_files_btn.clicked.connect(self._pick_files)
        self.add_folder_btn.clicked.connect(self._pick_folder)
        self.clear_btn.clicked.connect(self._clear_files)
        self.start_btn.clicked.connect(self._start)

        buttons.addWidget(self.add_files_btn)
        buttons.addWidget(self.add_folder_btn)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.start_btn)
        root.addLayout(buttons)

        # Progress panel (hidden until a run starts)
        self.progress_panel = QWidget()
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 6, 0, 0)
        progress_layout.setSpacing(6)

        progress_header = QHBoxLayout()
        self.current_file_label = QLabel("")
        self.current_file_label.setObjectName("currentFile")
        self.eta_label = QLabel("")
        self.eta_label.setObjectName("eta")
        self.eta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_header.addWidget(self.current_file_label, 1)
        progress_header.addWidget(self.eta_label, 0)
        progress_layout.addLayout(progress_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        progress_layout.addWidget(self.progress_bar)

        self.progress_panel.setVisible(False)
        root.addWidget(self.progress_panel)

        log_label = QLabel("Progress log")
        log_label.setObjectName("section")
        root.addWidget(log_label)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background: {THEME_DARK};
                color: {THEME_TEXT};
                font-family: "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
                font-size: 14px;
            }}
            QLabel#title {{
                font-size: 36px;
                font-weight: 800;
                color: {THEME_BLUE_BRIGHT};
                padding: 0;
                margin: 0;
                letter-spacing: 0.5px;
            }}
            QLabel#version {{
                font-size: 11px;
                color: {THEME_MUTED};
                letter-spacing: 1px;
                padding-bottom: 2px;
            }}
            QFrame#headerSep {{
                background: {BORDER};
                max-height: 1px;
                border: 0;
                margin: 4px 0 8px 0;
            }}
            QCheckBox {{
                color: {THEME_TEXT};
                font-size: 13px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {BORDER};
                background: {THEME_PANEL};
            }}
            QCheckBox::indicator:checked {{
                background: {PROGRESS_GREEN};
                border: 1px solid {PROGRESS_GREEN};
            }}
            QLabel#subtitle {{
                font-size: 13px;
                color: {THEME_MUTED};
                padding: 0;
                margin: 0;
            }}
            QLabel#section {{
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1px;
                color: {THEME_MUTED};
                text-transform: uppercase;
                padding-top: 4px;
            }}
            QLabel#currentFile {{
                font-size: 13px;
                color: {THEME_TEXT};
                font-weight: 600;
            }}
            QLabel#eta {{
                font-size: 13px;
                color: {THEME_MUTED};
            }}
            QLabel#device {{
                font-size: 12px;
                color: {THEME_MUTED};
            }}
            QLabel#outputPath {{
                color: {THEME_TEXT};
                font-weight: 600;
            }}
            QPushButton {{
                background: {THEME_BLUE_LIGHT};
                color: {THEME_TEXT};
                border: 0;
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {THEME_BLUE_BRIGHT};
            }}
            QPushButton:disabled {{
                background: #2b3342;
                color: #6b7a93;
            }}
            QPushButton#startBtn {{
                background: {THEME_BLUE_BRIGHT};
                color: {THEME_TEXT};
                font-weight: 600;
            }}
            QPushButton#startBtn:hover {{
                background: #5A8DD4;
            }}
            QPushButton#startBtn:disabled {{
                background: #2b3342;
                color: #6b7a93;
            }}
            QListWidget, QPlainTextEdit, QComboBox {{
                background: {THEME_PANEL};
                color: {THEME_TEXT};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 4px 2px;
            }}
            QListWidget::item:selected {{
                background: {THEME_BLUE};
                border-radius: 4px;
            }}
            QComboBox {{
                padding: 6px 10px;
            }}
            QComboBox:disabled {{
                color: {THEME_MUTED};
                background: {THEME_DARK};
                border: 1px dashed {BORDER};
            }}
            QProgressBar {{
                background: {PROGRESS_TRACK};
                border: 1px solid {BORDER};
                border-radius: 10px;
                height: 24px;
                text-align: center;
                color: {THEME_TEXT};
                font-size: 13px;
                font-weight: 600;
            }}
            QProgressBar::chunk {{
                background: {PROGRESS_GREEN};
                border-radius: 9px;
            }}
            """
        )

    def _log(self, message: str) -> None:
        self.log.appendPlainText(message)
        self._update_progress_from_log(message)

    def _update_progress_from_log(self, message: str) -> None:
        stripped = message.strip()

        m = TRANSCRIBING_RE.match(stripped)
        if m:
            name = m.group(1).strip()
            self._current_file_name = name
            self._file_t_start = time.monotonic()
            self.progress_panel.setVisible(True)
            self.current_file_label.setText(f"Current file: {name}")
            self.eta_label.setText("calculating…")
            self.progress_bar.setValue(0)
            return

        m = FINISHED_RE.match(stripped)
        if m:
            self.progress_bar.setValue(100)
            self.eta_label.setText("done")
            return

        m = PROGRESS_RE.search(stripped)
        if m:
            pct = max(0, min(100, int(m.group(1))))
            self.progress_bar.setValue(pct)
            if pct <= 0 or self._file_t_start <= 0:
                self.eta_label.setText("calculating…")
                return
            elapsed = time.monotonic() - self._file_t_start
            if elapsed < 1.0:
                self.eta_label.setText("calculating…")
                return
            remaining = elapsed * (100 - pct) / max(pct, 1)
            self.eta_label.setText(f"{pct}% — {_format_eta(remaining)}")

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select audio files",
            "",
            "Audio files (*.mp3 *.mp4 *.mpeg *.mpga *.m4a *.wav *.webm);;All files (*.*)",
        )
        if files:
            self._add_paths([Path(p) for p in files])

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder containing audio files")
        if not folder:
            return
        files = [p for p in sorted(Path(folder).iterdir()) if p.is_file()]
        self._add_paths(files)

    def _add_paths(self, paths: list[Path]) -> None:
        for p in paths:
            if not p.exists() or not p.is_file():
                continue
            ext = p.suffix.lower().lstrip(".")
            if ext not in SUPPORTED_EXTS:
                continue
            if p in self.file_paths:
                continue
            self.file_paths.append(p)
            self.file_list.addItem(str(p))

    def _clear_files(self) -> None:
        self.file_paths.clear()
        self.file_list.clear()

    def _open_output_folder(self) -> None:
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.processed_dir)))

    def _show_output_dir(self) -> None:
        self.output_label.setText(str(self.processed_dir))
        self.output_label.setToolTip(str(self.processed_dir))

    def _change_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose where to save transcripts", str(self.processed_dir)
        )
        if not folder:
            return
        self.processed_dir = Path(folder)
        self.settings.setValue("output_dir", str(self.processed_dir))
        self._show_output_dir()
        self._log(f"Transcripts will be saved to: {self.processed_dir}")

    def _set_busy(self, busy: bool) -> None:
        self.add_files_btn.setDisabled(busy)
        self.add_folder_btn.setDisabled(busy)
        self.clear_btn.setDisabled(busy)
        self.start_btn.setDisabled(busy)
        self.quality.setDisabled(busy)
        self.translate_checkbox.setDisabled(busy)
        self.change_output_btn.setDisabled(busy)

    def _start(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.file_paths:
            QMessageBox.information(self, "No Files", "Add at least one audio file first.")
            return

        translate = self.translate_checkbox.isChecked()
        quality = self.quality.currentData()
        model_dir = model_dir_for_quality(quality)
        if not model_dir:
            self._log(f"Model folder for '{quality}' is missing in this package.")
            QMessageBox.critical(self, "Model Missing", f"Could not find bundled model for '{quality}'.")
            return

        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.current_file_label.setText("Preparing…")
        self.eta_label.setText("")
        self.progress_panel.setVisible(True)
        self.worker = TranscribeWorker(
            list(self.file_paths),
            quality,
            self.processed_dir,
            translate=translate,
            drop_dirs=self.drop_dirs,
        )
        self.worker.log.connect(self._log)
        self.worker.done.connect(self._finish_run)
        self.worker.start()

    def _finish_run(self) -> None:
        self._set_busy(False)
        self.progress_panel.setVisible(False)
        self._file_t_start = 0.0
        self._current_file_name = ""
        self._clear_files()

    def _load_startup_files(self) -> None:
        for folder in self.drop_dirs:
            self._add_paths([p for p in sorted(folder.iterdir()) if p.is_file()])


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Whisper Offline")

    icon_path = _app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if icon_path is not None:
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    start_first_run_setup()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
