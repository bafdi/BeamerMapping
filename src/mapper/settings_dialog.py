"""Einstellungs-Dialog fuer Renderer und FPS-Anzeige."""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QCheckBox,
    QDialogButtonBox, QSpinBox
)


SETTINGS_KEY_RENDERER = "renderer_backend"
SETTINGS_KEY_SHOW_FPS = "show_fps"
SETTINGS_KEY_FADE_DURATION = "freeze_blackout_fade_ms"


class SettingsDialog(QDialog):
    """Dialog fuer Anwendungseinstellungen."""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(350)

        layout = QFormLayout(self)

        # Renderer Backend
        self.renderer_combo = QComboBox()
        self.renderer_combo.addItem("OpenCV (CPU)", "opencv")
        self.renderer_combo.addItem("OpenGL (GPU)", "opengl")

        current_backend = self.settings.value(SETTINGS_KEY_RENDERER, "opencv")
        for i in range(self.renderer_combo.count()):
            if self.renderer_combo.itemData(i) == current_backend:
                self.renderer_combo.setCurrentIndex(i)
                break

        layout.addRow("Renderer:", self.renderer_combo)

        # FPS Anzeige
        self.fps_checkbox = QCheckBox("Show FPS in Output")
        self.fps_checkbox.setChecked(
            self.settings.value(SETTINGS_KEY_SHOW_FPS, False, type=bool)
        )
        layout.addRow(self.fps_checkbox)

        # Freeze/Blackout Fade Duration
        self.fade_spin = QSpinBox()
        self.fade_spin.setRange(0, 5000)
        self.fade_spin.setSuffix(" ms")
        self.fade_spin.setValue(
            self.settings.value(SETTINGS_KEY_FADE_DURATION, 500, type=int)
        )
        layout.addRow("Freeze/Blackout Fade:", self.fade_spin)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_accept(self) -> None:
        """Speichere Einstellungen und schliesse Dialog."""
        self.settings.setValue(
            SETTINGS_KEY_RENDERER,
            self.renderer_combo.currentData()
        )
        self.settings.setValue(
            SETTINGS_KEY_SHOW_FPS,
            self.fps_checkbox.isChecked()
        )
        self.settings.setValue(
            SETTINGS_KEY_FADE_DURATION,
            self.fade_spin.value()
        )
        self.accept()

    def get_renderer_backend(self) -> str:
        return self.renderer_combo.currentData()

    def get_show_fps(self) -> bool:
        return self.fps_checkbox.isChecked()
