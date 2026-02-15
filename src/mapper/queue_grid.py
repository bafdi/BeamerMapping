"""Queue Grid UI - MadMapper-Style Queue/Cue Grid."""

from __future__ import annotations
import base64
from typing import Optional, List, TYPE_CHECKING, Callable

import numpy as np
import cv2

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPaintEvent
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QMenu, QInputDialog, QMessageBox,
    QDialog, QComboBox, QSpinBox, QSlider, QFormLayout, QDialogButtonBox,
    QSizePolicy
)

from .models import Queue, QueueTransition

if TYPE_CHECKING:
    from .queue_manager import QueueManager


class QueueEditDialog(QDialog):
    """Dialog zum Bearbeiten einer Queue."""

    def __init__(self, queue: Optional[Queue] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Queue" if queue else "Save Queue")
        self.setMinimumWidth(300)

        self.queue = queue

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Name
        self.name_input = QComboBox()
        self.name_input.setEditable(True)
        default_names = [
            "Intro", "Verse 1", "Chorus", "Verse 2", "Bridge", "Outro",
            "Scene 1", "Scene 2", "Scene 3", "Blackout", "Full", "Logo"
        ]
        self.name_input.addItems(default_names)
        if queue:
            self.name_input.setCurrentText(queue.name)
        form.addRow("Name:", self.name_input)

        # Transition Mode
        self.transition_combo = QComboBox()
        self.transition_combo.addItems(["instant", "dissolve", "fade"])
        if queue:
            idx = self.transition_combo.findText(queue.transition.mode)
            if idx >= 0:
                self.transition_combo.setCurrentIndex(idx)
        form.addRow("Transition:", self.transition_combo)

        # Duration
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 10000)
        self.duration_spin.setSuffix(" ms")
        self.duration_spin.setValue(queue.transition.duration_ms if queue else 500)
        form.addRow("Duration:", self.duration_spin)

        # Easing
        self.easing_combo = QComboBox()
        self.easing_combo.addItems(["linear", "ease-in", "ease-out", "ease-in-out"])
        if queue:
            idx = self.easing_combo.findText(queue.transition.easing)
            if idx >= 0:
                self.easing_combo.setCurrentIndex(idx)
        form.addRow("Easing:", self.easing_combo)

        # Overlap Slider
        overlap_container = QHBoxLayout()
        self.overlap_slider = QSlider(Qt.Orientation.Horizontal)
        self.overlap_slider.setRange(0, 100)
        self.overlap_slider.setValue(int((queue.transition.overlap if queue else 0.5) * 100))
        self.overlap_slider.setToolTip("0% = Dip-to-Black, 50% = Standard, 100% = Additive")
        self.overlap_label = QLabel(f"{self.overlap_slider.value()}%")
        self.overlap_label.setFixedWidth(35)
        self.overlap_slider.valueChanged.connect(
            lambda v: self.overlap_label.setText(f"{v}%"))
        overlap_container.addWidget(self.overlap_slider)
        overlap_container.addWidget(self.overlap_label)
        self.overlap_row_label = QLabel("Overlap:")
        form.addRow(self.overlap_row_label, overlap_container)

        # Overlap nur sichtbar wenn Transition != "instant"
        self._update_overlap_visibility(self.transition_combo.currentText())
        self.transition_combo.currentTextChanged.connect(self._update_overlap_visibility)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_overlap_visibility(self, mode: str) -> None:
        """Zeige/Verstecke Overlap-Slider basierend auf Transition-Modus."""
        visible = mode != "instant"
        self.overlap_slider.setVisible(visible)
        self.overlap_label.setVisible(visible)
        self.overlap_row_label.setVisible(visible)

    def get_name(self) -> str:
        return self.name_input.currentText()

    def get_transition(self) -> QueueTransition:
        return QueueTransition(
            mode=self.transition_combo.currentText(),
            duration_ms=self.duration_spin.value(),
            easing=self.easing_combo.currentText(),
            overlap=self.overlap_slider.value() / 100.0,
        )


class QueueButton(QFrame):
    """Einzelner Queue-Button im Grid mit Thumbnail-Preview."""

    queue_triggered = pyqtSignal(str)       # queue_id
    queue_save_requested = pyqtSignal(int)  # grid_index
    queue_edit_requested = pyqtSignal(int)  # grid_index
    queue_delete_requested = pyqtSignal(int)  # grid_index

    def __init__(self, index: int, queue: Optional[Queue] = None, parent=None):
        super().__init__(parent)
        self.index = index
        self.queue: Optional[Queue] = None
        self._transition_progress: float = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(80, 60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        # Thumbnail Label
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumHeight(40)
        self.thumbnail_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.thumbnail_label)

        # Name Label
        self.name_label = QLabel(f"Q{self.index + 1}")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("color: #888; font-size: 9px; background: transparent;")
        layout.addWidget(self.name_label)

        self.set_queue(queue)

    def set_queue(self, queue: Optional[Queue]) -> None:
        """Setze die Queue fuer diesen Button."""
        self.queue = queue
        self._update_display()

    def _update_display(self) -> None:
        """Aktualisiere Button-Anzeige."""
        if self.queue:
            name = self.queue.name
            if len(name) > 10:
                name = name[:9] + "..."
            self.name_label.setText(name)
            self.name_label.setStyleSheet("color: #ddd; font-size: 9px; font-weight: bold; background: transparent;")

            # Thumbnail laden falls vorhanden
            if self.queue.thumbnail:
                try:
                    img_data = base64.b64decode(self.queue.thumbnail)
                    img_array = np.frombuffer(img_data, dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        h, w = img_rgb.shape[:2]
                        qimg = QImage(img_rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
                        pixmap = QPixmap.fromImage(qimg)
                        self.thumbnail_label.setPixmap(pixmap.scaled(
                            self.thumbnail_label.width() - 4,
                            self.thumbnail_label.height() - 4,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        ))
                except Exception:
                    self.thumbnail_label.setText("")
            else:
                self.thumbnail_label.setText("")

            # Farbcodierung basierend auf Transition
            if self.queue.transition.mode == "instant":
                border_color = "#4a8a4a"  # Gruen
            elif self.queue.transition.mode == "dissolve":
                border_color = "#4a4a8a"  # Blau
            else:  # fade
                border_color = "#8a4a8a"  # Lila

            self.setStyleSheet(f"""
                QueueButton {{
                    background-color: #2a2a2a;
                    border: 2px solid {border_color};
                    border-radius: 6px;
                }}
                QueueButton:hover {{
                    border-color: #0af;
                    background-color: #333;
                }}
            """)
        else:
            self.name_label.setText(f"Q{self.index + 1}")
            self.name_label.setStyleSheet("color: #555; font-size: 9px; background: transparent;")
            self.thumbnail_label.clear()
            self.thumbnail_label.setText("")
            self.setStyleSheet("""
                QueueButton {
                    background-color: #1a1a1a;
                    border: 1px dashed #333;
                    border-radius: 6px;
                }
                QueueButton:hover {
                    border-color: #555;
                    background-color: #222;
                }
            """)

    def set_transition_progress(self, progress: float) -> None:
        """Setze Transition-Fortschritt (0.0-1.0)."""
        self._transition_progress = progress
        self.update()

    def resizeEvent(self, event) -> None:
        """Update thumbnail size on resize."""
        super().resizeEvent(event)
        if self.queue and self.queue.thumbnail:
            # Re-scale thumbnail
            self._update_display()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Zeichne Button + Fortschrittsbalken."""
        super().paintEvent(event)
        if self._transition_progress > 0:
            painter = QPainter(self)
            bar_h = 4
            bar_w = int(self.width() * self._transition_progress)
            painter.fillRect(0, self.height() - bar_h, bar_w, bar_h,
                             QColor(0, 170, 255, 220))
            painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.queue:
                self.queue_triggered.emit(self.queue.id)
            else:
                # Leerer Slot - speichern
                self.queue_save_requested.emit(self.index)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())
        else:
            super().mousePressEvent(event)

    def _show_context_menu(self, pos) -> None:
        """Zeige Kontextmenue."""
        menu = QMenu(self)

        if self.queue:
            recall_action = menu.addAction("Recall")
            recall_action.triggered.connect(lambda: self.queue_triggered.emit(self.queue.id))

            edit_action = menu.addAction("Edit...")
            edit_action.triggered.connect(lambda: self.queue_edit_requested.emit(self.index))

            menu.addSeparator()

            overwrite_action = menu.addAction("Overwrite")
            overwrite_action.triggered.connect(lambda: self.queue_save_requested.emit(self.index))

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self.queue_delete_requested.emit(self.index))
        else:
            save_action = menu.addAction("Save here")
            save_action.triggered.connect(lambda: self.queue_save_requested.emit(self.index))

        menu.exec(self.mapToGlobal(pos))


class QueueGridWidget(QWidget):
    """Grid von Queue-Buttons - MadMapper Style, volle Breite."""

    queue_recalled = pyqtSignal(str)  # queue_id

    def __init__(self, queue_manager: 'QueueManager', parent=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self.buttons: List[QueueButton] = []
        self.num_columns = 8
        self.num_rows = 4
        self._capture_thumbnail_callback: Optional[Callable[[], Optional[np.ndarray]]] = None
        self._active_transition_index: int = -1
        self._setup_ui()

    def set_capture_callback(self, callback: Callable[[], Optional[np.ndarray]]) -> None:
        """Setze Callback um Thumbnail von erster Output-Ebene zu capturen."""
        self._capture_thumbnail_callback = callback

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Grid Layout - volle Breite
        grid_layout = QGridLayout()
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        # Buttons erstellen (8x4 = 32 Slots)
        for row in range(self.num_rows):
            for col in range(self.num_columns):
                index = row * self.num_columns + col
                btn = QueueButton(index)
                btn.queue_triggered.connect(self._on_queue_triggered)
                btn.queue_save_requested.connect(self._on_save_requested)
                btn.queue_edit_requested.connect(self._on_edit_requested)
                btn.queue_delete_requested.connect(self._on_delete_requested)
                grid_layout.addWidget(btn, row, col)
                self.buttons.append(btn)

        # Spalten gleichmaessig verteilen
        for col in range(self.num_columns):
            grid_layout.setColumnStretch(col, 1)

        main_layout.addLayout(grid_layout)

        # Initial update
        self._update_buttons()

    def _capture_thumbnail(self) -> Optional[str]:
        """Capture Thumbnail als Base64-String."""
        if not self._capture_thumbnail_callback:
            return None

        try:
            frame = self._capture_thumbnail_callback()
            if frame is None:
                return None

            # Resize fuer Thumbnail (klein halten)
            h, w = frame.shape[:2]
            max_size = 120
            scale = min(max_size / w, max_size / h)
            new_w, new_h = int(w * scale), int(h * scale)
            thumbnail = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Encode als JPEG
            _, buffer = cv2.imencode('.jpg', thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            print(f"Thumbnail capture error: {e}")
            return None

    def _update_buttons(self) -> None:
        """Aktualisiere alle Buttons basierend auf Projekt-Queues."""
        # Alle Buttons zuruecksetzen
        for btn in self.buttons:
            btn.set_queue(None)

        # Queues aus Projekt laden
        for queue in self.queue_manager.project.queues:
            if 0 <= queue.index < len(self.buttons):
                self.buttons[queue.index].set_queue(queue)

    def refresh(self) -> None:
        """Extern aufrufbar um Grid zu aktualisieren."""
        self._update_buttons()

    def set_transition_progress(self, progress: float) -> None:
        """Setze Transition-Fortschritt am aktiven Button."""
        if self._active_transition_index >= 0 and self._active_transition_index < len(self.buttons):
            btn = self.buttons[self._active_transition_index]
            if progress <= 0 or progress >= 1.0:
                btn.set_transition_progress(0.0)
                self._active_transition_index = -1
            else:
                btn.set_transition_progress(progress)

    def _on_queue_triggered(self, queue_id: str) -> None:
        """Handle Queue-Abruf."""
        queue = self.queue_manager.project.get_queue_by_id(queue_id)
        if queue:
            # Vorherigen Transition-Button zuruecksetzen
            if self._active_transition_index >= 0 and self._active_transition_index < len(self.buttons):
                self.buttons[self._active_transition_index].set_transition_progress(0.0)
            self._active_transition_index = queue.index
            self.queue_manager.recall_queue(queue)
            self.queue_recalled.emit(queue_id)

    def _on_save_requested(self, index: int) -> None:
        """Handle Queue-Speichern."""
        # Dialog oeffnen
        existing_queue = self.queue_manager.project.get_queue_by_index(index)
        dialog = QueueEditDialog(existing_queue, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_name()
            transition = dialog.get_transition()

            queue = self.queue_manager.save_queue(
                index=index,
                name=name,
                transition=transition
            )

            # Thumbnail capturen
            thumbnail = self._capture_thumbnail()
            if thumbnail:
                queue.thumbnail = thumbnail

            self._update_buttons()

    def _on_edit_requested(self, index: int) -> None:
        """Handle Queue-Bearbeiten."""
        queue = self.queue_manager.project.get_queue_by_index(index)
        if not queue:
            return

        dialog = QueueEditDialog(queue, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            queue.name = dialog.get_name()
            queue.transition = dialog.get_transition()
            self._update_buttons()

    def _on_delete_requested(self, index: int) -> None:
        """Handle Queue-Loeschen."""
        queue = self.queue_manager.project.get_queue_by_index(index)
        if not queue:
            return

        reply = QMessageBox.question(
            self,
            "Delete Queue",
            f"Delete queue '{queue.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.queue_manager.delete_queue(index)
            self._update_buttons()
