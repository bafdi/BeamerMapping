"""Hauptfenster der Anwendung."""

from typing import Optional, Dict, Callable
from pathlib import Path
import json
import numpy as np

from PyQt6.QtCore import Qt, QTimer, QEvent, QPoint, QMimeData, pyqtSignal, QSettings
from PyQt6.QtGui import QAction, QKeySequence, QDrag, QMouseEvent, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QFrame, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QStatusBar, QApplication, QComboBox, QInputDialog, QGridLayout,
    QDialog, QScrollArea
)
from PyQt6.QtGui import QImage, QPixmap

# Settings Keys
SETTINGS_ORG = "ProjectionMapper"
SETTINGS_APP = "BeamerMapping"
SETTINGS_LAST_PROJECT = "last_project_path"

from .models import Project, OutputLayer, Polygon, MediaItem, MediaLayer


class DraggableTreeWidget(QTreeWidget):
    """TreeWidget mit Drag & Drop Support fuer Polygone."""

    polygon_dropped = pyqtSignal(str, str)  # polygon_id, target_layer_id

    def __init__(self, layer_type: str = "media", parent=None):
        super().__init__(parent)
        self.layer_type = layer_type  # "media" oder "output"
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_item: Optional[QTreeWidgetItem] = None
        self.setAcceptDrops(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == "polygon":
                    self._drag_start_pos = event.pos()
                    self._drag_item = item
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (self._drag_start_pos is not None and
            self._drag_item is not None and
            event.buttons() & Qt.MouseButton.LeftButton):
            # Check if moved far enough to start drag
            if (event.pos() - self._drag_start_pos).manhattanLength() > 10:
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        self._drag_item = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        if not self._drag_item:
            return

        data = self._drag_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "polygon":
            return

        polygon_id = data[1]

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"polygon:{polygon_id}")
        drag.setMimeData(mime_data)

        drag.exec(Qt.DropAction.MoveAction)

        self._drag_start_pos = None
        self._drag_item = None

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText() and event.mimeData().text().startswith("polygon:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasText() and event.mimeData().text().startswith("polygon:"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if not mime.hasText() or not mime.text().startswith("polygon:"):
            event.ignore()
            return

        polygon_id = mime.text().replace("polygon:", "")

        # Find target layer
        item = self.itemAt(event.position().toPoint())
        if not item:
            event.ignore()
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            event.ignore()
            return

        target_layer_id = None
        layer_key = "media_layer" if self.layer_type == "media" else "output_layer"

        if data[0] == layer_key:
            target_layer_id = data[1]
        elif data[0] == "polygon":
            # Dropped on polygon - use parent item for layer
            parent = item.parent()
            if parent:
                parent_data = parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_data and parent_data[0] == layer_key:
                    target_layer_id = parent_data[1]

        if target_layer_id:
            self.polygon_dropped.emit(polygon_id, target_layer_id)
            event.acceptProposedAction()
        else:
            event.ignore()


class CameraPreviewDialog(QDialog):
    """Dialog mit Live-Preview aller verfuegbaren Kameras."""

    def __init__(self, cameras: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kamera auswählen")
        self.setMinimumSize(640, 400)

        self.cameras = cameras  # [(idx, name), ...]
        self.selected_camera: Optional[tuple] = None
        self.captures: Dict[int, any] = {}  # camera_idx -> cv2.VideoCapture
        self.preview_labels: Dict[int, QLabel] = {}

        self._setup_ui()
        self._start_previews()

        # Timer fuer Live-Updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_previews)
        self.update_timer.start(66)  # ~15 FPS fuer Preview

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info Label
        info = QLabel("Klicke auf eine Kamera um sie auszuwählen:")
        info.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(info)

        # Scroll Area fuer Kamera-Previews
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setSpacing(10)

        # Kameras in Grid anordnen (2 pro Zeile)
        for i, (cam_idx, cam_name) in enumerate(self.cameras):
            row, col = i // 2, i % 2

            frame = QFrame()
            frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
            frame.setStyleSheet("""
                QFrame {
                    background: #2a2a2a;
                    border: 2px solid #444;
                    border-radius: 8px;
                }
                QFrame:hover { border-color: #0af; }
            """)
            frame.setCursor(Qt.CursorShape.PointingHandCursor)
            frame.mousePressEvent = lambda e, idx=cam_idx, name=cam_name: self._select_camera(idx, name)

            frame_layout = QVBoxLayout(frame)

            # Preview Label
            preview = QLabel()
            preview.setFixedSize(280, 180)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setStyleSheet("background: #1a1a1a; border-radius: 4px;")
            preview.setText("Lade...")
            self.preview_labels[cam_idx] = preview
            frame_layout.addWidget(preview)

            # Kamera Name
            name_label = QLabel(cam_name)
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setStyleSheet("color: #ccc; font-weight: bold;")
            frame_layout.addWidget(name_label)

            self.grid.addWidget(frame, row, col)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _start_previews(self) -> None:
        """Starte alle Kamera-Captures."""
        import cv2
        for cam_idx, _ in self.cameras:
            try:
                cap = cv2.VideoCapture(cam_idx)
                if cap.isOpened():
                    self.captures[cam_idx] = cap
            except Exception:
                pass

    def _update_previews(self) -> None:
        """Aktualisiere alle Previews."""
        import cv2
        for cam_idx, cap in self.captures.items():
            if cam_idx not in self.preview_labels:
                continue

            ret, frame = cap.read()
            if ret and frame is not None:
                # Resize fuer Preview
                h, w = frame.shape[:2]
                scale = min(280 / w, 180 / h)
                new_w, new_h = int(w * scale), int(h * scale)
                frame = cv2.resize(frame, (new_w, new_h))

                # BGR -> RGB -> QPixmap
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg)
                self.preview_labels[cam_idx].setPixmap(pixmap)
            else:
                self.preview_labels[cam_idx].setText("Kein Signal")

    def _select_camera(self, cam_idx: int, cam_name: str) -> None:
        """Kamera ausgewaehlt."""
        self.selected_camera = (cam_idx, cam_name)
        self.accept()

    def closeEvent(self, event) -> None:
        """Aufraumen beim Schliessen."""
        self.update_timer.stop()
        for cap in self.captures.values():
            cap.release()
        self.captures.clear()
        super().closeEvent(event)

    def reject(self) -> None:
        """Abbrechen."""
        self.update_timer.stop()
        for cap in self.captures.values():
            cap.release()
        self.captures.clear()
        super().reject()


from .canvas import PolygonCanvas
from .output_window import OutputWindow
from .transform import load_image
from .test_patterns import TEST_PATTERNS, get_test_pattern
from .live_sources import LiveSourceManager, CameraCapture
from .video_player import VideoPlayerWidget
from .queue_manager import QueueManager
from .queue_grid import QueueGridWidget


class MainWindow(QMainWindow):
    """Hauptfenster mit Side-by-Side Layout."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Projection Mapper v4")
        self.setGeometry(100, 100, 1400, 800)

        # State
        self.project = Project()
        self.project_path: Optional[str] = None
        self.current_media_layer: Optional[MediaLayer] = None
        self.current_output_layer: Optional[OutputLayer] = None
        self.current_polygon: Optional[Polygon] = None
        self.images: Dict[str, np.ndarray] = {}  # media_id -> image
        self.output_windows: Dict[str, OutputWindow] = {}  # output_layer_id -> window
        self.live_source_manager = LiveSourceManager()

        # Snapping State
        self._snapping_enabled = True

        # Selection State: True wenn Media Layer selbst ausgewaehlt (nicht Polygon)
        self._media_layer_selected = False

        # UI erstellen
        self._create_menus()
        self._create_ui()
        self._create_statusbar()

        # Timer fuer Output Window Updates (schnell)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_output_windows)
        self.update_timer.start(33)  # ~30 FPS

        # Separater Timer fuer Live-Quellen (langsamer - Kameras sind teuer)
        self.live_source_timer = QTimer()
        self.live_source_timer.timeout.connect(self._update_live_sources_and_canvas)
        self.live_source_timer.start(100)  # 10 FPS fuer Kameras

        # Timer fuer Queue-Transitions
        self.transition_timer = QTimer()
        self.transition_timer.timeout.connect(self._update_transition)
        self.transition_timer.start(16)  # ~60 FPS fuer smooth transitions

        # Settings
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

        # Auto-Load letztes Projekt oder neues erstellen
        self._auto_load_or_create()

    def _create_menus(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Output Menu
        output_menu = menubar.addMenu("&Output")

        open_output_action = QAction("Open Output &Window", self)
        open_output_action.setShortcut(QKeySequence("F5"))
        open_output_action.triggered.connect(self._open_current_output_window)
        output_menu.addAction(open_output_action)

        fullscreen_action = QAction("Output &Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._output_fullscreen)
        output_menu.addAction(fullscreen_action)

    def _create_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Hauptsplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # === LINKE SPALTE: Media Layers & Output Layers ===
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # === RECHTE SPALTE: Media Pool (vor Middle wegen video_player Dependency) ===
        right_panel = self._create_right_panel()

        # === MITTE: Side-by-Side Canvas (braucht video_player fuer Queue-System) ===
        middle_panel = self._create_middle_panel()
        splitter.addWidget(middle_panel)

        # Rechtes Panel jetzt einfuegen
        splitter.addWidget(right_panel)

        # Splitter Groessen
        splitter.setSizes([240, 900, 200])

    def _create_left_panel(self) -> QFrame:
        """Erstelle linkes Panel mit Media Layers und Output Layers."""
        panel = QFrame()
        panel.setFixedWidth(240)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # === MEDIA LAYERS ===
        layout.addWidget(QLabel("<b>MEDIA LAYERS</b>"))

        self.media_tree = DraggableTreeWidget(layer_type="media")
        self.media_tree.setHeaderHidden(True)
        self.media_tree.itemClicked.connect(self._on_media_tree_clicked)
        self.media_tree.itemDoubleClicked.connect(self._on_media_tree_double_clicked)
        self.media_tree.polygon_dropped.connect(self._on_polygon_dropped_to_media)
        self.media_tree.installEventFilter(self)
        self.media_tree.setMaximumHeight(200)
        layout.addWidget(self.media_tree)

        # Media Layer Buttons
        ml_btn_row = QHBoxLayout()
        add_ml_btn = QPushButton("+ Media Layer")
        add_ml_btn.setFixedHeight(22)
        add_ml_btn.clicked.connect(self._add_media_layer)
        ml_btn_row.addWidget(add_ml_btn)
        layout.addLayout(ml_btn_row)

        # === OUTPUT LAYERS ===
        layout.addWidget(QLabel("<b>OUTPUT LAYERS</b>"))

        self.output_tree = DraggableTreeWidget(layer_type="output")
        self.output_tree.setHeaderHidden(True)
        self.output_tree.itemClicked.connect(self._on_output_tree_clicked)
        self.output_tree.itemDoubleClicked.connect(self._on_output_tree_double_clicked)
        self.output_tree.polygon_dropped.connect(self._on_polygon_dropped_to_output)
        self.output_tree.installEventFilter(self)
        self.output_tree.setMaximumHeight(200)
        layout.addWidget(self.output_tree)

        # Output Layer Buttons
        ol_btn_row = QHBoxLayout()
        add_ol_btn = QPushButton("+ Output Layer")
        add_ol_btn.setFixedHeight(22)
        add_ol_btn.clicked.connect(self._add_output_layer)
        self.open_output_btn = QPushButton("Open (F5)")
        self.open_output_btn.setFixedHeight(22)
        self.open_output_btn.clicked.connect(self._open_current_output_window)
        ol_btn_row.addWidget(add_ol_btn)
        ol_btn_row.addWidget(self.open_output_btn)
        layout.addLayout(ol_btn_row)

        # Monitor-Auswahl fuer aktuellen Output Layer
        layout.addWidget(QLabel("Monitor:"))
        self.monitor_combo = QComboBox()
        self.monitor_combo.setFixedHeight(22)
        self._update_monitor_combo()
        self.monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        layout.addWidget(self.monitor_combo)

        # === POLYGON CONTROLS ===
        layout.addWidget(QLabel("<b>POLYGON</b>"))

        poly_btn_row = QHBoxLayout()
        add_poly_btn = QPushButton("+ Polygon")
        add_poly_btn.setFixedHeight(22)
        add_poly_btn.clicked.connect(self._add_polygon)
        delete_btn = QPushButton("Delete")
        delete_btn.setFixedHeight(22)
        delete_btn.clicked.connect(self._delete_selected)
        poly_btn_row.addWidget(add_poly_btn)
        poly_btn_row.addWidget(delete_btn)
        layout.addLayout(poly_btn_row)

        poly_btn_row2 = QHBoxLayout()
        rename_btn = QPushButton("Rename")
        rename_btn.setFixedHeight(22)
        rename_btn.clicked.connect(self._rename_selected)
        poly_btn_row2.addWidget(rename_btn)
        layout.addLayout(poly_btn_row2)

        # Polygon Layer-Zuweisung
        layout.addWidget(QLabel("<small>Polygon zuweisen:</small>"))

        # Media Layer Combo fuer Polygon
        self.poly_media_combo = QComboBox()
        self.poly_media_combo.setFixedHeight(22)
        self.poly_media_combo.currentIndexChanged.connect(self._on_poly_media_changed)
        layout.addWidget(self.poly_media_combo)

        # Output Layer Combo fuer Polygon
        self.poly_output_combo = QComboBox()
        self.poly_output_combo.setFixedHeight(22)
        self.poly_output_combo.currentIndexChanged.connect(self._on_poly_output_changed)
        layout.addWidget(self.poly_output_combo)

        # Z-Order Buttons
        z_btn_row = QHBoxLayout()
        move_back_btn = QPushButton("To Back")
        move_back_btn.setFixedHeight(22)
        move_back_btn.clicked.connect(self._move_polygon_back)
        move_back_btn.setToolTip("Polygon nach hinten (niedrigerer Index)")
        move_front_btn = QPushButton("To Front")
        move_front_btn.setFixedHeight(22)
        move_front_btn.clicked.connect(self._move_polygon_front)
        move_front_btn.setToolTip("Polygon nach vorne (hoeherer Index)")
        z_btn_row.addWidget(move_back_btn)
        z_btn_row.addWidget(move_front_btn)
        layout.addLayout(z_btn_row)

        layout.addStretch()

        return panel

    def _create_middle_panel(self) -> QFrame:
        """Erstelle mittleres Panel mit Side-by-Side Canvas und Queues."""
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Kompakte Toolbar mit View-Toggle
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        # View Mode Buttons
        self.view_source_btn = QPushButton("Source")
        self.view_source_btn.setCheckable(True)
        self.view_source_btn.setFixedHeight(24)
        self.view_source_btn.clicked.connect(lambda: self._set_view_mode("source"))

        self.view_output_btn = QPushButton("Output")
        self.view_output_btn.setCheckable(True)
        self.view_output_btn.setFixedHeight(24)
        self.view_output_btn.clicked.connect(lambda: self._set_view_mode("output"))

        self.view_both_btn = QPushButton("Both")
        self.view_both_btn.setCheckable(True)
        self.view_both_btn.setChecked(True)
        self.view_both_btn.setFixedHeight(24)
        self.view_both_btn.clicked.connect(lambda: self._set_view_mode("both"))

        toolbar.addWidget(self.view_source_btn)
        toolbar.addWidget(self.view_output_btn)
        toolbar.addWidget(self.view_both_btn)

        # Snapping Toggle
        self.snap_btn = QPushButton("Snap")
        self.snap_btn.setCheckable(True)
        self.snap_btn.setChecked(True)
        self.snap_btn.setFixedHeight(24)
        self.snap_btn.setFixedWidth(50)
        self.snap_btn.clicked.connect(self._toggle_snapping)
        self.snap_btn.setStyleSheet("""
            QPushButton:checked { background-color: #2a6e2a; }
        """)
        toolbar.addWidget(self.snap_btn)

        toolbar.addStretch()

        # Reset Buttons
        reset_source_btn = QPushButton("Reset Src")
        reset_source_btn.setFixedHeight(24)
        reset_source_btn.clicked.connect(lambda: self._reset_points("source"))
        reset_output_btn = QPushButton("Reset Out")
        reset_output_btn.setFixedHeight(24)
        reset_output_btn.clicked.connect(lambda: self._reset_points("output"))
        toolbar.addWidget(reset_source_btn)
        toolbar.addWidget(reset_output_btn)

        layout.addLayout(toolbar)

        # Vertikaler Splitter: Canvas oben, Queues unten
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)

        # Side-by-Side Canvas Splitter
        self.canvas_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Source Canvas (Media-Ebene)
        self.source_canvas = PolygonCanvas(mode="source")
        self.source_canvas.points_changed.connect(self._on_points_changed)
        self.source_canvas.polygon_selected.connect(self._on_canvas_polygon_selected)
        self.canvas_splitter.addWidget(self.source_canvas)

        # Output Canvas (Output-Ebene)
        self.output_canvas = PolygonCanvas(mode="output")
        self.output_canvas.points_changed.connect(self._on_points_changed)
        self.output_canvas.polygon_selected.connect(self._on_canvas_polygon_selected)
        self.canvas_splitter.addWidget(self.output_canvas)

        self.canvas_splitter.setSizes([450, 450])
        self.vertical_splitter.addWidget(self.canvas_splitter)

        # Queues Panel
        queues_panel = self._create_queues_panel()
        self.vertical_splitter.addWidget(queues_panel)

        # Splitter-Groessen: Canvas gross, Queues klein
        self.vertical_splitter.setSizes([500, 100])

        layout.addWidget(self.vertical_splitter)

        # View mode state
        self.current_view_mode = "both"

        return panel

    def _toggle_snapping(self) -> None:
        """Toggle Snapping on/off."""
        self._snapping_enabled = self.snap_btn.isChecked()
        self.source_canvas.set_snapping(self._snapping_enabled)
        self.output_canvas.set_snapping(self._snapping_enabled)
        status = "aktiviert" if self._snapping_enabled else "deaktiviert"
        self.statusbar.showMessage(f"Snapping {status}")

    def _on_canvas_polygon_selected(self, polygon: Polygon) -> None:
        """Handle Polygon-Auswahl aus dem Canvas."""
        self.current_polygon = polygon
        self._media_layer_selected = False
        # Media Layer und Output Layer vom Polygon aktualisieren
        if polygon.media_layer_id:
            self.current_media_layer = self.project.get_media_layer_by_id(polygon.media_layer_id)
        if polygon.output_layer_id:
            self.current_output_layer = self.project.get_output_layer_by_id(polygon.output_layer_id)
        self._update_canvas()
        self._update_polygon_combos()
        self._select_polygon_in_trees(polygon)
        self.statusbar.showMessage(f"Polygon '{polygon.name}' ausgewaehlt")

    def _move_polygon_back(self) -> None:
        """Verschiebe Polygon nach hinten (niedrigerer Index)."""
        if not self.current_polygon:
            return

        idx = self.project.polygons.index(self.current_polygon) if self.current_polygon in self.project.polygons else -1

        if idx > 0:
            polygons = self.project.polygons
            polygons[idx], polygons[idx - 1] = polygons[idx - 1], polygons[idx]
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()
            self.statusbar.showMessage(f"'{self.current_polygon.name}' nach hinten verschoben")

    def _move_polygon_front(self) -> None:
        """Verschiebe Polygon nach vorne (hoeherer Index)."""
        if not self.current_polygon:
            return

        polygons = self.project.polygons
        idx = polygons.index(self.current_polygon) if self.current_polygon in polygons else -1

        if idx >= 0 and idx < len(polygons) - 1:
            polygons[idx], polygons[idx + 1] = polygons[idx + 1], polygons[idx]
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()
            self.statusbar.showMessage(f"'{self.current_polygon.name}' nach vorne verschoben")

    def _create_queues_panel(self) -> QWidget:
        """Erstelle Queues-Panel mit QueueGridWidget."""
        # QueueManager erstellen (VideoPlayer muss bereits existieren)
        self.queue_manager = QueueManager(self.project, self.video_player)
        self.queue_manager.set_on_transition_update(self._on_transition_update)

        # QueueGridWidget erstellen
        self.queue_grid = QueueGridWidget(self.queue_manager)
        self.queue_grid.queue_recalled.connect(self._on_queue_recalled)
        self.queue_grid.setStyleSheet("background-color: #1e1e1e;")

        # Thumbnail-Capture Callback setzen
        self.queue_grid.set_capture_callback(self._capture_output_thumbnail)

        return self.queue_grid

    def _capture_output_thumbnail(self) -> Optional[np.ndarray]:
        """Capture Thumbnail von erster Output-Ebene."""
        from .transform import composite_polygons

        # Finde ersten Output Layer
        if not self.project.output_layers:
            return None

        output_layer = self.project.output_layers[0]

        # Sammle alle Polygone fuer diesen Output
        polygons = self.project.get_polygons_for_output_layer(output_layer.id)
        if not polygons:
            return None

        # Thumbnail-Groesse (16:9)
        canvas_size = (480, 270)

        # Polygon-Daten sammeln
        polygons_data = []
        for poly in polygons:
            if not poly.media_layer_id:
                continue

            ml = self.project.get_media_layer_by_id(poly.media_layer_id)
            if not ml or not ml.visible or not ml.media_id:
                continue

            if ml.media_id not in self.images:
                continue

            image = self.images[ml.media_id]
            if image is None:
                continue

            polygons_data.append((image, poly.source_points, poly.output_points))

        if not polygons_data:
            return None

        try:
            return composite_polygons(polygons_data, canvas_size)
        except Exception:
            return None

    def _on_video_frame_ready(self, media_id: str, frame: np.ndarray) -> None:
        """Handle neues Video-Frame."""
        self.images[media_id] = frame
        self._update_canvas()
        self._update_output_windows()

    def _update_transition(self) -> None:
        """Update Queue-Transitions (60 FPS Timer)."""
        if hasattr(self, 'queue_manager') and self.queue_manager.update_transition():
            # Transition aktiv - UI updaten
            self._update_canvas()
            self._update_output_windows()

    def _on_transition_update(self) -> None:
        """Callback vom QueueManager waehrend Transitions."""
        self._update_canvas()
        self._update_output_windows()

    def _on_queue_recalled(self, queue_id: str) -> None:
        """Handle Queue-Abruf."""
        queue = self.project.get_queue_by_id(queue_id)
        if queue:
            self.statusbar.showMessage(f"Queue '{queue.name}' abgerufen")
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()

    def _set_view_mode(self, mode: str) -> None:
        """Setze View-Modus (source, output, both)."""
        self.current_view_mode = mode

        # Update button states
        self.view_source_btn.setChecked(mode == "source")
        self.view_output_btn.setChecked(mode == "output")
        self.view_both_btn.setChecked(mode == "both")

        # Show/hide canvases
        if mode == "source":
            self.source_canvas.show()
            self.output_canvas.hide()
        elif mode == "output":
            self.source_canvas.hide()
            self.output_canvas.show()
        else:  # both
            self.source_canvas.show()
            self.output_canvas.show()

    def _create_right_panel(self) -> QFrame:
        """Erstelle rechtes Panel mit Media Pool und Video Player."""
        panel = QFrame()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # === MEDIA POOL ===
        layout.addWidget(QLabel("<b>MEDIA POOL</b>"))

        # Import Buttons Row
        import_row = QHBoxLayout()
        import_img_btn = QPushButton("Image")
        import_img_btn.setFixedHeight(22)
        import_img_btn.clicked.connect(self._import_image)
        import_video_btn = QPushButton("Video")
        import_video_btn.setFixedHeight(22)
        import_video_btn.clicked.connect(self._import_video)
        import_row.addWidget(import_img_btn)
        import_row.addWidget(import_video_btn)
        layout.addLayout(import_row)

        # Live Sources Row
        live_row = QHBoxLayout()
        screen_btn = QPushButton("Screen")
        screen_btn.setFixedHeight(22)
        screen_btn.clicked.connect(self._add_screen_capture)
        camera_btn = QPushButton("Camera")
        camera_btn.setFixedHeight(22)
        camera_btn.clicked.connect(self._add_camera)
        live_row.addWidget(screen_btn)
        live_row.addWidget(camera_btn)
        layout.addLayout(live_row)

        # Test Patterns Row
        test_row = QHBoxLayout()
        test_combo = QComboBox()
        test_combo.addItems(TEST_PATTERNS.keys())
        test_combo.setFixedHeight(22)
        add_test_btn = QPushButton("+")
        add_test_btn.setFixedWidth(30)
        add_test_btn.setFixedHeight(22)
        add_test_btn.clicked.connect(lambda: self._add_test_pattern(test_combo.currentText()))
        test_row.addWidget(test_combo)
        test_row.addWidget(add_test_btn)
        layout.addLayout(test_row)
        self.test_pattern_combo = test_combo

        # Media List
        self.media_list = QListWidget()
        self.media_list.itemDoubleClicked.connect(self._assign_media_to_layer)
        self.media_list.installEventFilter(self)
        layout.addWidget(self.media_list)

        # Delete Media Button
        delete_media_btn = QPushButton("Ausgewähltes Medium löschen")
        delete_media_btn.clicked.connect(self._delete_selected_media)
        layout.addWidget(delete_media_btn)

        layout.addWidget(QLabel("<small>Doppelklick: Medium zuweisen | Delete: Löschen</small>"))

        # === VIDEO PLAYER ===
        layout.addWidget(QLabel("<b>VIDEO PLAYER</b>"))

        self.video_player = VideoPlayerWidget()
        self.video_player.frame_ready.connect(self._on_video_frame_ready)
        layout.addWidget(self.video_player)

        return panel

    def _create_statusbar(self) -> None:
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Bereit")

    def _update_monitor_combo(self) -> None:
        """Aktualisiere Monitor-Auswahl."""
        self.monitor_combo.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            self.monitor_combo.addItem(f"Monitor {i + 1}: {geo.width()}x{geo.height()}")

    def _update_trees(self) -> None:
        """Aktualisiere beide Baum-Ansichten."""
        self._update_media_tree()
        self._update_output_tree()
        self._update_polygon_combos()

    def _on_polygon_dropped_to_media(self, polygon_id: str, layer_id: str) -> None:
        """Handle Polygon-Drop auf Media Layer."""
        polygon = self.project.get_polygon_by_id(polygon_id)
        layer = self.project.get_media_layer_by_id(layer_id)
        if polygon and layer and polygon.media_layer_id != layer_id:
            polygon.media_layer_id = layer_id
            self.current_polygon = polygon
            self.current_media_layer = layer
            self._media_layer_selected = False
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()
            self.statusbar.showMessage(f"Polygon '{polygon.name}' -> Media Layer '{layer.name}'")

    def _on_polygon_dropped_to_output(self, polygon_id: str, layer_id: str) -> None:
        """Handle Polygon-Drop auf Output Layer."""
        polygon = self.project.get_polygon_by_id(polygon_id)
        layer = self.project.get_output_layer_by_id(layer_id)
        if polygon and layer and polygon.output_layer_id != layer_id:
            polygon.output_layer_id = layer_id
            self.current_polygon = polygon
            self.current_output_layer = layer
            self._media_layer_selected = False
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()
            self.statusbar.showMessage(f"Polygon '{polygon.name}' -> Output Layer '{layer.name}'")

    def _select_polygon_in_trees(self, polygon: Polygon) -> None:
        """Selektiere ein Polygon in beiden Trees ohne sie neu aufzubauen."""
        # Media Tree durchsuchen
        for i in range(self.media_tree.topLevelItemCount()):
            ml_item = self.media_tree.topLevelItem(i)
            ml_item.setSelected(False)
            for j in range(ml_item.childCount()):
                child = ml_item.child(j)
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == "polygon" and data[1] == polygon.id:
                    child.setSelected(True)
                    self.media_tree.scrollToItem(child)
                else:
                    child.setSelected(False)

        # Output Tree durchsuchen
        for i in range(self.output_tree.topLevelItemCount()):
            ol_item = self.output_tree.topLevelItem(i)
            ol_item.setSelected(False)
            for j in range(ol_item.childCount()):
                child = ol_item.child(j)
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == "polygon" and data[1] == polygon.id:
                    child.setSelected(True)
                    self.output_tree.scrollToItem(child)
                else:
                    child.setSelected(False)

    def _update_media_tree(self) -> None:
        """Aktualisiere den Media Layers Baum."""
        # Expanded-State speichern
        expanded_ids = set()
        for i in range(self.media_tree.topLevelItemCount()):
            item = self.media_tree.topLevelItem(i)
            if item and item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data:
                    expanded_ids.add(data[1])

        self.media_tree.clear()

        for ml in self.project.media_layers:
            # Media Layer Name mit Media-Info
            media_name = ""
            if ml.media_id:
                media = self.project.get_media_by_id(ml.media_id)
                if media:
                    media_name = f" [{media.name}]"

            vis_icon = "V " if ml.visible else "H "
            ml_item = QTreeWidgetItem([f"{vis_icon}{ml.name}{media_name}"])
            ml_item.setData(0, Qt.ItemDataRole.UserRole, ("media_layer", ml.id))
            # Expanded-State wiederherstellen (default: expanded bei neuen Items)
            ml_item.setExpanded(ml.id in expanded_ids or len(expanded_ids) == 0)

            # Polygone dieses Media Layers
            for poly in self.project.get_polygons_for_media_layer(ml.id):
                # Zeige auch auf welchen Output
                output_name = ""
                if poly.output_layer_id:
                    ol = self.project.get_output_layer_by_id(poly.output_layer_id)
                    if ol:
                        output_name = f" -> {ol.name}"

                poly_item = QTreeWidgetItem([f"  {poly.name}{output_name}"])
                poly_item.setData(0, Qt.ItemDataRole.UserRole, ("polygon", poly.id))

                # Hervorheben wenn ausgewaehlt
                if poly == self.current_polygon:
                    poly_item.setSelected(True)

                ml_item.addChild(poly_item)

            self.media_tree.addTopLevelItem(ml_item)

    def _update_output_tree(self) -> None:
        """Aktualisiere den Output Layers Baum."""
        # Expanded-State speichern
        expanded_ids = set()
        for i in range(self.output_tree.topLevelItemCount()):
            item = self.output_tree.topLevelItem(i)
            if item and item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data:
                    expanded_ids.add(data[1])

        self.output_tree.clear()

        for ol in self.project.output_layers:
            monitor_info = f" (Monitor {ol.monitor_index})"
            ol_item = QTreeWidgetItem([f"{ol.name}{monitor_info}"])
            ol_item.setData(0, Qt.ItemDataRole.UserRole, ("output_layer", ol.id))
            # Expanded-State wiederherstellen (default: expanded bei neuen Items)
            ol_item.setExpanded(ol.id in expanded_ids or len(expanded_ids) == 0)

            # Polygone auf diesem Output Layer
            for poly in self.project.get_polygons_for_output_layer(ol.id):
                # Zeige auch von welchem Media Layer
                media_name = ""
                if poly.media_layer_id:
                    ml = self.project.get_media_layer_by_id(poly.media_layer_id)
                    if ml:
                        media_name = f" <- {ml.name}"

                poly_item = QTreeWidgetItem([f"  {poly.name}{media_name}"])
                poly_item.setData(0, Qt.ItemDataRole.UserRole, ("polygon", poly.id))

                # Hervorheben wenn ausgewaehlt
                if poly == self.current_polygon:
                    poly_item.setSelected(True)

                ol_item.addChild(poly_item)

            self.output_tree.addTopLevelItem(ol_item)

    def _update_media_list(self) -> None:
        """Aktualisiere die Media-Liste."""
        self.media_list.clear()
        for media in self.project.media:
            item = QListWidgetItem(media.name)
            item.setData(Qt.ItemDataRole.UserRole, media.id)
            self.media_list.addItem(item)

    def _on_media_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle Klick auf Media Tree Item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data[0] == "media_layer":
            layer_id = data[1]
            self.current_media_layer = self.project.get_media_layer_by_id(layer_id)
            self._media_layer_selected = True  # Media Layer selbst ausgewaehlt
            # Kein Polygon auswaehlen - nur der Layer
            self.current_polygon = None

        elif data[0] == "polygon":
            polygon_id = data[1]
            self._media_layer_selected = False  # Polygon ausgewaehlt, nicht Layer
            self.current_polygon = self.project.get_polygon_by_id(polygon_id)
            if self.current_polygon:
                if self.current_polygon.media_layer_id:
                    self.current_media_layer = self.project.get_media_layer_by_id(
                        self.current_polygon.media_layer_id
                    )
                if self.current_polygon.output_layer_id:
                    self.current_output_layer = self.project.get_output_layer_by_id(
                        self.current_polygon.output_layer_id
                    )

        self._update_canvas()
        self._update_polygon_combos()  # Nur Combos, nicht Trees!
        self._update_video_player()

    def _on_media_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle Doppelklick auf Media Tree Item - Toggle Visibility oder Rename."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data[0] == "media_layer":
            layer_id = data[1]
            layer = self.project.get_media_layer_by_id(layer_id)
            if layer:
                layer.visible = not layer.visible
                self._update_trees()
                self._update_canvas()
                self._update_output_windows()
                status = "sichtbar" if layer.visible else "versteckt"
                self.statusbar.showMessage(f"Media Layer '{layer.name}' ist nun {status}")

    def _on_output_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle Klick auf Output Tree Item."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        # Output Tree Klick - Media Layer Selektion zuruecksetzen
        self._media_layer_selected = False

        if data[0] == "output_layer":
            layer_id = data[1]
            self.current_output_layer = self.project.get_output_layer_by_id(layer_id)
            # Kein Polygon auswaehlen - nur der Layer
            self.current_polygon = None
            self._update_monitor_selection()

        elif data[0] == "polygon":
            polygon_id = data[1]
            self.current_polygon = self.project.get_polygon_by_id(polygon_id)
            if self.current_polygon:
                if self.current_polygon.media_layer_id:
                    self.current_media_layer = self.project.get_media_layer_by_id(
                        self.current_polygon.media_layer_id
                    )
                if self.current_polygon.output_layer_id:
                    self.current_output_layer = self.project.get_output_layer_by_id(
                        self.current_polygon.output_layer_id
                    )

        self._update_canvas()
        self._update_polygon_combos()  # Nur Combos, nicht Trees!
        self._update_video_player()

    def _on_output_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle Doppelklick auf Output Tree Item - Oeffne Output Window."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data[0] == "output_layer":
            layer_id = data[1]
            layer = self.project.get_output_layer_by_id(layer_id)
            if layer:
                self.current_output_layer = layer
                self._open_output_window(layer)

    def _update_canvas(self) -> None:
        """Aktualisiere beide Canvas."""
        # Aktuelles Polygon und zugehoeriger Media Layer
        self.source_canvas.set_current_polygon(self.current_polygon)
        self.output_canvas.set_current_polygon(self.current_polygon)

        # Bild und Polygone bestimmen
        image = None
        source_polygons = []
        output_polygons = []
        current_media_layer_id = None
        current_output_layer_id = None

        if self.current_polygon:
            # Fall 1: Polygon ausgewaehlt
            current_media_layer_id = self.current_polygon.media_layer_id
            current_output_layer_id = self.current_polygon.output_layer_id

        elif self._media_layer_selected and self.current_media_layer:
            # Fall 2: Nur Media Layer ausgewaehlt (kein Polygon)
            current_media_layer_id = self.current_media_layer.id

            # Finde Output Layer mit niedrigstem Index der ein Polygon von diesem Media Layer hat
            layer_polygons = self.project.get_polygons_for_media_layer(current_media_layer_id)
            if layer_polygons:
                # Sortiere nach Output Layer monitor_index
                best_output = None
                best_index = float('inf')
                for poly in layer_polygons:
                    if poly.output_layer_id:
                        ol = self.project.get_output_layer_by_id(poly.output_layer_id)
                        if ol and ol.monitor_index < best_index:
                            best_index = ol.monitor_index
                            best_output = poly.output_layer_id
                current_output_layer_id = best_output

        # Bild vom Media Layer holen
        if current_media_layer_id:
            ml = self.project.get_media_layer_by_id(current_media_layer_id)
            if ml and ml.media_id and ml.media_id in self.images:
                image = self.images[ml.media_id]

        self.source_canvas.set_image(image)
        self.output_canvas.set_image(image)

        # Gefilterte Polygone sammeln
        for poly in self.project.polygons:
            # Source: Gleicher Media Layer
            if poly.media_layer_id == current_media_layer_id:
                source_polygons.append(poly)
            # Output: Gleicher Output Layer
            if poly.output_layer_id == current_output_layer_id:
                output_polygons.append(poly)

        self.source_canvas.set_all_polygons(source_polygons)
        self.source_canvas.set_all_data(self.project, self.images)
        self.output_canvas.set_all_polygons(output_polygons)
        self.output_canvas.set_all_data(self.project, self.images)

    def _update_monitor_selection(self) -> None:
        """Aktualisiere Monitor-Auswahl basierend auf aktuellem Output Layer."""
        if self.current_output_layer:
            idx = self.current_output_layer.monitor_index
            if idx < self.monitor_combo.count():
                self.monitor_combo.setCurrentIndex(idx)

    def _update_polygon_combos(self) -> None:
        """Aktualisiere die ComboBoxen fuer Polygon-Zuweisung."""
        # Block signals waehrend Update
        self.poly_media_combo.blockSignals(True)
        self.poly_output_combo.blockSignals(True)

        # Media Layer Combo
        self.poly_media_combo.clear()
        for ml in self.project.media_layers:
            media_name = ""
            if ml.media_id:
                media = self.project.get_media_by_id(ml.media_id)
                if media:
                    media_name = f" [{media.name}]"
            self.poly_media_combo.addItem(f"{ml.name}{media_name}", ml.id)

        # Output Layer Combo
        self.poly_output_combo.clear()
        for ol in self.project.output_layers:
            self.poly_output_combo.addItem(f"{ol.name} (Mon {ol.monitor_index})", ol.id)

        # Aktuelle Auswahl setzen
        if self.current_polygon:
            # Media Layer
            for i in range(self.poly_media_combo.count()):
                if self.poly_media_combo.itemData(i) == self.current_polygon.media_layer_id:
                    self.poly_media_combo.setCurrentIndex(i)
                    break

            # Output Layer
            for i in range(self.poly_output_combo.count()):
                if self.poly_output_combo.itemData(i) == self.current_polygon.output_layer_id:
                    self.poly_output_combo.setCurrentIndex(i)
                    break

        # Combos nur aktivieren wenn Polygon ausgewaehlt
        enabled = self.current_polygon is not None
        self.poly_media_combo.setEnabled(enabled)
        self.poly_output_combo.setEnabled(enabled)

        self.poly_media_combo.blockSignals(False)
        self.poly_output_combo.blockSignals(False)

    def _on_poly_media_changed(self, index: int) -> None:
        """Handle Media Layer Aenderung fuer Polygon."""
        if not self.current_polygon or index < 0:
            return

        new_media_layer_id = self.poly_media_combo.itemData(index)
        if new_media_layer_id and new_media_layer_id != self.current_polygon.media_layer_id:
            self.current_polygon.media_layer_id = new_media_layer_id
            self.current_media_layer = self.project.get_media_layer_by_id(new_media_layer_id)
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()
            self.statusbar.showMessage(
                f"Polygon '{self.current_polygon.name}' -> {self.current_media_layer.name}"
            )

    def _on_poly_output_changed(self, index: int) -> None:
        """Handle Output Layer Aenderung fuer Polygon."""
        if not self.current_polygon or index < 0:
            return

        new_output_layer_id = self.poly_output_combo.itemData(index)
        if new_output_layer_id and new_output_layer_id != self.current_polygon.output_layer_id:
            self.current_polygon.output_layer_id = new_output_layer_id
            self.current_output_layer = self.project.get_output_layer_by_id(new_output_layer_id)
            self._update_trees()
            self._update_canvas()
            self._update_output_windows()
            self.statusbar.showMessage(
                f"Polygon '{self.current_polygon.name}' -> {self.current_output_layer.name}"
            )

    def _on_monitor_changed(self, index: int) -> None:
        """Handle Monitor-Auswahl-Aenderung."""
        if self.current_output_layer:
            self.current_output_layer.monitor_index = index
            self._update_trees()

    def _on_points_changed(self) -> None:
        """Handle Punkt-Aenderungen."""
        self.source_canvas.update()
        self.output_canvas.update()
        self._update_output_windows()

    def _reset_points(self, mode: str) -> None:
        """Reset Punkte auf Standard."""
        if not self.current_polygon:
            return

        default = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        if mode == "source":
            self.current_polygon.source_points = [p.copy() for p in default]
        else:
            self.current_polygon.output_points = [p.copy() for p in default]

        self._update_canvas()

    # === MEDIA LAYER MANAGEMENT ===

    def _add_media_layer(self) -> None:
        """Fuege neuen Media Layer hinzu."""
        layer = self.project.add_media_layer()
        self.current_media_layer = layer

        # Wenn es noch keine Output Layer gibt, einen erstellen
        if not self.project.output_layers:
            self._add_output_layer()

        # Erstes Polygon fuer diesen Layer erstellen
        if self.project.output_layers:
            poly = self.project.add_polygon(
                media_layer_id=layer.id,
                output_layer_id=self.project.output_layers[0].id
            )
            self.current_polygon = poly
            self.current_output_layer = self.project.output_layers[0]

        self._update_trees()
        self._update_canvas()
        self.statusbar.showMessage(f"Media Layer '{layer.name}' erstellt")

    # === OUTPUT LAYER MANAGEMENT ===

    def _add_output_layer(self) -> None:
        """Fuege neuen Output Layer hinzu."""
        layer = self.project.add_output_layer()
        layer.monitor_index = min(1, len(QApplication.screens()) - 1)

        self.current_output_layer = layer
        self._update_trees()
        self._update_monitor_selection()
        self.statusbar.showMessage(f"Output Layer '{layer.name}' erstellt")

    # === POLYGON MANAGEMENT ===

    def _add_polygon(self) -> None:
        """Fuege neues Polygon hinzu."""
        # Media Layer und Output Layer muessen vorhanden sein
        if not self.project.media_layers:
            self._add_media_layer()
            return

        if not self.project.output_layers:
            self._add_output_layer()

        # Verwende aktuellen Media Layer oder ersten
        media_layer_id = None
        if self.current_media_layer:
            media_layer_id = self.current_media_layer.id
        elif self.project.media_layers:
            media_layer_id = self.project.media_layers[0].id
            self.current_media_layer = self.project.media_layers[0]

        # Verwende aktuellen Output Layer oder ersten
        output_layer_id = None
        if self.current_output_layer:
            output_layer_id = self.current_output_layer.id
        elif self.project.output_layers:
            output_layer_id = self.project.output_layers[0].id
            self.current_output_layer = self.project.output_layers[0]

        poly = self.project.add_polygon(
            media_layer_id=media_layer_id,
            output_layer_id=output_layer_id
        )
        self.current_polygon = poly

        self._update_trees()
        self._update_canvas()
        self.statusbar.showMessage(f"Polygon '{poly.name}' erstellt")

    def _delete_selected(self) -> None:
        """Loesche ausgewaehltes Element (Polygon, Media Layer oder Output Layer)."""
        # Fall 1: Media Layer ist ausgewaehlt (nicht ein Polygon)
        if self._media_layer_selected and self.current_media_layer:
            layer_name = self.current_media_layer.name
            self.project.remove_media_layer(self.current_media_layer)
            self.current_media_layer = None
            self.current_polygon = None
            # Naechsten Media Layer auswaehlen
            if self.project.media_layers:
                self.current_media_layer = self.project.media_layers[0]
            self._update_trees()
            self._update_canvas()
            self.statusbar.showMessage(f"Media Layer '{layer_name}' geloescht")
            return

        # Fall 2: Polygon ist ausgewaehlt
        if self.current_polygon:
            poly_name = self.current_polygon.name
            self.project.remove_polygon(self.current_polygon)
            # Naechstes Polygon auswaehlen
            if self.project.polygons:
                self.current_polygon = self.project.polygons[0]
            else:
                self.current_polygon = None
            self._update_trees()
            self._update_canvas()
            self.statusbar.showMessage(f"Polygon '{poly_name}' geloescht")
            return

        # Fall 3: Output Layer ausgewaehlt (ueber Output Tree)
        # Wird nur geloescht wenn kein Polygon ausgewaehlt
        if self.current_output_layer and len(self.project.output_layers) > 1:
            layer_name = self.current_output_layer.name
            self.project.remove_output_layer(self.current_output_layer)
            self.current_output_layer = self.project.output_layers[0] if self.project.output_layers else None
            self._update_trees()
            self._update_canvas()
            self.statusbar.showMessage(f"Output Layer '{layer_name}' geloescht")

    def _rename_selected(self) -> None:
        """Benenne ausgewaehltes Element um."""
        if self.current_polygon:
            name, ok = QInputDialog.getText(
                self, "Umbenennen", "Neuer Name:",
                text=self.current_polygon.name
            )
            if ok and name:
                self.current_polygon.name = name
                self._update_trees()

    # === MEDIA MANAGEMENT ===

    def _import_image(self) -> None:
        """Importiere ein Bild."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff);;All Files (*)"
        )
        if filepath:
            media = self.project.add_media(filepath)
            image = load_image(filepath)
            if image is not None:
                self.images[media.id] = image
                self._update_media_list()
                self.statusbar.showMessage(f"Importiert: {media.name}")
            else:
                self.project.media.remove(media)
                QMessageBox.warning(self, "Fehler", f"Konnte Bild nicht laden: {filepath}")

    def _import_video(self) -> None:
        """Importiere ein Video."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Video", "",
            "Videos (*.mp4 *.mov *.avi *.mkv);;All Files (*)"
        )
        if filepath:
            media = self.project.add_media(filepath)
            media.media_type = "video"
            # Lade erstes Frame als Vorschau
            import cv2
            cap = cv2.VideoCapture(filepath)
            ret, frame = cap.read()
            cap.release()
            if ret:
                self.images[media.id] = frame
                self._update_media_list()
                self.statusbar.showMessage(f"Video importiert: {media.name}")
            else:
                self.project.media.remove(media)
                QMessageBox.warning(self, "Fehler", f"Konnte Video nicht laden: {filepath}")

    def _add_screen_capture(self) -> None:
        """Fuege Screen Capture hinzu."""
        screens = QApplication.screens()
        items = [f"Monitor {i+1}: {s.geometry().width()}x{s.geometry().height()}"
                 for i, s in enumerate(screens)]

        item, ok = QInputDialog.getItem(
            self, "Screen Capture", "Monitor auswaehlen:", items, 0, False
        )
        if ok and item:
            idx = items.index(item)
            media = MediaItem(
                path=f"screen:{idx}",
                name=f"Screen {idx + 1}",
                media_type="screen"
            )
            self.project.media.append(media)

            # Capture erstes Frame
            frame = self.live_source_manager.capture_screen(idx)
            if frame is not None:
                self.images[media.id] = frame

            self._update_media_list()
            self.statusbar.showMessage(f"Screen Capture hinzugefuegt: {media.name}")

    def _add_camera(self) -> None:
        """Fuege Kamera hinzu mit Live-Preview Dialog."""
        cameras = CameraCapture.list_cameras()
        if not cameras:
            QMessageBox.warning(self, "Fehler", "Keine Kameras gefunden!")
            return

        # Preview Dialog oeffnen
        dialog = CameraPreviewDialog(cameras, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_camera:
            camera_idx, camera_name = dialog.selected_camera

            media = MediaItem(
                path=f"camera:{camera_idx}",
                name=camera_name,
                media_type="camera"
            )
            self.project.media.append(media)

            # Capture erstes Frame
            frame = self.live_source_manager.capture_camera(camera_idx)
            if frame is not None:
                self.images[media.id] = frame

            self._update_media_list()
            self.statusbar.showMessage(f"Kamera hinzugefuegt: {media.name}")

    def _add_test_pattern(self, pattern_name: str) -> None:
        """Fuege Test-Pattern hinzu."""
        media = MediaItem(
            path=f"test:{pattern_name}",
            name=f"Test: {pattern_name}",
            media_type="test"
        )
        self.project.media.append(media)

        # Generiere Pattern
        pattern = get_test_pattern(pattern_name)
        self.images[media.id] = pattern

        self._update_media_list()
        self.statusbar.showMessage(f"Test-Pattern hinzugefuegt: {pattern_name}")

    def _delete_selected_media(self) -> None:
        """Loesche das ausgewaehlte Medium aus dem Pool."""
        current_item = self.media_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "Kein Medium", "Bitte waehle ein Medium zum Loeschen aus.")
            return

        media_id = current_item.data(Qt.ItemDataRole.UserRole)
        media = self.project.get_media_by_id(media_id)
        if not media:
            return

        # Pruefe ob Medium von einem Media Layer verwendet wird
        layers_using = [ml for ml in self.project.media_layers if ml.media_id == media_id]

        if layers_using:
            layer_names = ", ".join(ml.name for ml in layers_using)
            reply = QMessageBox.question(
                self,
                "Medium wird verwendet",
                f"'{media.name}' wird von folgenden Layern verwendet:\n{layer_names}\n\n"
                f"Trotzdem loeschen? (Layer behalten ihre Polygone, aber ohne Medium)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            # Medium-Referenz aus Layern entfernen
            for ml in layers_using:
                ml.media_id = None

        # Medium aus Pool entfernen
        self.project.media = [m for m in self.project.media if m.id != media_id]

        # Bild aus Cache entfernen
        if media_id in self.images:
            del self.images[media_id]

        # Video-Decoder aufräumen falls vorhanden
        if hasattr(self, 'video_player') and media_id in self.video_player.decoders:
            self.video_player.decoders[media_id].release()
            del self.video_player.decoders[media_id]
            if media_id in self.video_player.audio_players:
                player, _ = self.video_player.audio_players[media_id]
                player.stop()
                del self.video_player.audio_players[media_id]

        # Kamera/Screen Capture aufräumen falls vorhanden
        if media.media_type == "camera":
            try:
                camera_idx = int(media.path.replace("camera:", ""))
                self.live_source_manager.close_camera(camera_idx)
            except (ValueError, Exception):
                pass
        elif media.media_type == "screen":
            try:
                monitor_idx = int(media.path.replace("screen:", ""))
                self.live_source_manager.close_screen(monitor_idx)
            except (ValueError, Exception):
                pass

        self._update_media_list()
        self._update_trees()
        self._update_canvas()
        self._update_output_windows()
        self.statusbar.showMessage(f"Medium geloescht: {media.name}")

    def _assign_media_to_layer(self, item: QListWidgetItem) -> None:
        """Weise Medium zu - Verhalten haengt von Selektion ab.

        Fall 1: Media Layer ist ausgewaehlt (_media_layer_selected=True)
                -> Medium wird dem Media Layer zugewiesen (ersetzt)
                -> Alle Polygone behalten ihre Positionen, nur neues Medium

        Fall 2: Polygon ist ausgewaehlt (current_polygon is not None)
                -> Suche Media Layer mit diesem Medium
                -> Falls gefunden: Polygon wird dem Layer zugewiesen
                -> Falls nicht: Neuer Media Layer wird erstellt und Polygon zugewiesen
        """
        media_id = item.data(Qt.ItemDataRole.UserRole)
        media = self.project.get_media_by_id(media_id)
        if not media:
            return

        if self._media_layer_selected and self.current_media_layer:
            # Fall 1: Media Layer ist ausgewaehlt - Medium ersetzen
            self.current_media_layer.media_id = media_id
            self.statusbar.showMessage(
                f"'{media.name}' zugewiesen an Media Layer '{self.current_media_layer.name}'"
            )

        elif self.current_polygon:
            # Fall 2: Polygon ist ausgewaehlt
            # Suche existierenden Media Layer mit diesem Medium
            existing_layer = None
            for ml in self.project.media_layers:
                if ml.media_id == media_id:
                    existing_layer = ml
                    break

            if existing_layer:
                # Layer gefunden - Polygon diesem Layer zuweisen
                self.current_polygon.media_layer_id = existing_layer.id
                self.current_media_layer = existing_layer
                self.statusbar.showMessage(
                    f"Polygon '{self.current_polygon.name}' -> Media Layer '{existing_layer.name}'"
                )
            else:
                # Kein Layer mit diesem Medium - neuen erstellen
                new_layer = self.project.add_media_layer(
                    name=media.name,
                    media_id=media_id
                )
                self.current_polygon.media_layer_id = new_layer.id
                self.current_media_layer = new_layer
                self.statusbar.showMessage(
                    f"Neuer Media Layer '{new_layer.name}' erstellt fuer Polygon '{self.current_polygon.name}'"
                )

        else:
            # Weder Media Layer noch Polygon ausgewaehlt
            # Neuen Media Layer erstellen
            new_layer = self.project.add_media_layer(
                name=media.name,
                media_id=media_id
            )
            self.current_media_layer = new_layer
            self._media_layer_selected = True
            self.statusbar.showMessage(
                f"Neuer Media Layer '{new_layer.name}' erstellt"
            )

        self._update_canvas()
        self._update_trees()
        self._update_video_player()

    def _update_video_player(self) -> None:
        """Aktualisiere Video Player - auch wenn nur Media Layer ausgewaehlt."""
        # Media Layer kann direkt ausgewaehlt sein ODER ueber ein Polygon
        if not self.current_media_layer:
            self.video_player.set_active_media(None, None)
            return

        if not self.current_media_layer.media_id:
            self.video_player.set_active_media(None, None)
            return

        media = self.project.get_media_by_id(self.current_media_layer.media_id)
        if not media or media.media_type != "video":
            self.video_player.set_active_media(None, None)
            return

        self.video_player.set_active_media(media.id, media.path)

    # === OUTPUT WINDOW ===

    def _open_current_output_window(self) -> None:
        """Oeffne Output-Fenster fuer aktuellen Output Layer."""
        if not self.current_output_layer:
            if self.project.output_layers:
                self.current_output_layer = self.project.output_layers[0]
            else:
                QMessageBox.warning(self, "Fehler", "Kein Output Layer vorhanden!")
                return

        self._open_output_window(self.current_output_layer)

    def _open_output_window(self, output_layer: OutputLayer) -> None:
        """Oeffne oder bringe Output-Fenster in den Vordergrund."""
        if output_layer.id not in self.output_windows:
            window = OutputWindow(output_layer, self.project, self.images)
            window.points_changed.connect(self._on_points_changed)
            self.output_windows[output_layer.id] = window

        window = self.output_windows[output_layer.id]
        window.set_output_layer(output_layer)
        window.set_project(self.project)
        window.set_images(self.images)

        # Auf richtigem Monitor positionieren
        screens = QApplication.screens()
        if output_layer.monitor_index < len(screens):
            screen = screens[output_layer.monitor_index]
            geo = screen.geometry()
            window.setGeometry(geo.x() + 50, geo.y() + 50, 800, 600)

        window.show()
        window.raise_()

    def _output_fullscreen(self) -> None:
        """Schalte Output-Fenster auf Fullscreen."""
        if not self.current_output_layer:
            return

        self._open_output_window(self.current_output_layer)
        window = self.output_windows.get(self.current_output_layer.id)
        if window:
            # Auf richtigen Monitor verschieben und dann Fullscreen
            screens = QApplication.screens()
            if self.current_output_layer.monitor_index < len(screens):
                screen = screens[self.current_output_layer.monitor_index]
                window.setGeometry(screen.geometry())
            window.showFullScreen()

    def _update_output_windows(self) -> None:
        """Aktualisiere alle offenen Output-Fenster - optimiert."""
        # Nur images updaten (die sich bei Video aendern), dann repaint
        for output_id, window in self.output_windows.items():
            if window.isVisible():
                window.images = self.images  # Direkt setzen ohne Methoden-Overhead
                window.update()  # Nur repaint triggern

    def _update_live_sources_and_canvas(self) -> None:
        """Aktualisiere Live-Quellen (Kameras, Screens) - separater langsamer Timer."""
        has_live = self._update_live_sources()
        if has_live:
            self._update_canvas()

    def _update_live_sources(self) -> bool:
        """Aktualisiere Kamera- und Screen-Capture-Frames. Returns True wenn Live-Quellen aktiv."""
        # Finde welche Media-IDs tatsaechlich angezeigt werden
        active_media_ids = set()

        # Sammle Media-IDs von sichtbaren Layern die Polygone haben
        for layer in self.project.media_layers:
            if layer.visible and layer.media_id:
                # Pruefe ob dieser Layer Polygone hat
                polygons = self.project.get_polygons_for_media_layer(layer.id)
                if polygons:
                    active_media_ids.add(layer.media_id)

        # Track welche Kameras/Screens wirklich gebraucht werden
        active_cameras: set = set()
        active_screens: set = set()

        # Nur aktive Live-Quellen updaten
        has_live = False
        for media in self.project.media:
            # Skip wenn nicht aktiv angezeigt
            if media.id not in active_media_ids:
                continue

            if media.media_type == "camera":
                has_live = True
                try:
                    camera_idx = int(media.path.replace("camera:", ""))
                    active_cameras.add(camera_idx)
                    frame = self.live_source_manager.capture_camera(camera_idx)
                    if frame is not None:
                        self.images[media.id] = frame
                except (ValueError, Exception):
                    pass

            elif media.media_type == "screen":
                has_live = True
                try:
                    monitor_idx = int(media.path.replace("screen:", ""))
                    active_screens.add(monitor_idx)
                    frame = self.live_source_manager.capture_screen(monitor_idx)
                    if frame is not None:
                        self.images[media.id] = frame
                except (ValueError, Exception):
                    pass

        # Cleanup: Schliesse Kameras/Screens die nicht mehr gebraucht werden
        self.live_source_manager.cleanup_inactive(active_cameras, active_screens)

        return has_live

    # === PROJECT MANAGEMENT ===

    def _new_project(self) -> None:
        """Neues Projekt erstellen."""
        if self.project.polygons:
            reply = QMessageBox.question(
                self, "Neues Projekt",
                "Aktuelles Projekt verwerfen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Alle Output-Fenster schliessen
        for window in self.output_windows.values():
            window.close()
        self.output_windows.clear()

        self.project = Project()
        self.project_path = None
        self.current_media_layer = None
        self.current_output_layer = None
        self.current_polygon = None
        self.images.clear()

        # Queue Manager aktualisieren
        if hasattr(self, 'queue_manager'):
            self.queue_manager.set_project(self.project)
        if hasattr(self, 'queue_grid'):
            self.queue_grid.refresh()

        self._update_trees()
        self._update_media_list()
        self._update_canvas()

        self._add_media_layer()
        self._add_output_layer()
        self.statusbar.showMessage("Neues Projekt erstellt")

    def _open_project(self) -> None:
        """Projekt oeffnen."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Projekt oeffnen", "",
            "Project Files (*.json);;All Files (*)"
        )
        if filepath:
            try:
                self._load_project_from_path(filepath)
                # Settings aktualisieren
                self.settings.setValue(SETTINGS_LAST_PROJECT, filepath)
                self.statusbar.showMessage(f"Geladen: {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Fehler beim Laden: {e}")

    def _save_project(self) -> None:
        """Projekt speichern."""
        if self.project_path:
            self._do_save(self.project_path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        """Projekt speichern unter."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Projekt speichern", "",
            "Project Files (*.json);;All Files (*)"
        )
        if filepath:
            if not filepath.endswith('.json'):
                filepath += '.json'
            self._do_save(filepath)

    def _do_save(self, filepath: str) -> None:
        """Speichere Projekt mit Session-State."""
        try:
            # Session-State ins Projekt schreiben
            self.project.selected_polygon_id = self.current_polygon.id if self.current_polygon else None
            self.project.selected_media_layer_id = self.current_media_layer.id if self.current_media_layer else None
            self.project.selected_output_layer_id = self.current_output_layer.id if self.current_output_layer else None

            self.project.save(filepath)
            self.project_path = filepath

            # Letzten Projektpfad in Settings speichern
            self.settings.setValue(SETTINGS_LAST_PROJECT, filepath)

            self.statusbar.showMessage(f"Gespeichert: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Speichern: {e}")

    def _auto_load_or_create(self) -> None:
        """Lade letztes Projekt automatisch oder erstelle neues."""
        last_path = self.settings.value(SETTINGS_LAST_PROJECT, "")

        if last_path and Path(last_path).exists():
            try:
                self._load_project_from_path(last_path)
                self.statusbar.showMessage(f"Projekt geladen: {last_path}")
                return
            except Exception as e:
                print(f"Auto-load failed: {e}")

        # Kein Projekt gefunden - neues erstellen
        self._add_media_layer()
        self._add_output_layer()

    def _load_project_from_path(self, filepath: str) -> None:
        """Lade Projekt aus Pfad und stelle Session-State wieder her."""
        self.project = Project.load(filepath)
        self.project_path = filepath

        # Queue Manager aktualisieren
        if hasattr(self, 'queue_manager'):
            self.queue_manager.set_project(self.project)
        if hasattr(self, 'queue_grid'):
            self.queue_grid.refresh()

        # Alle Bilder laden - fehlende Dateien tracken
        self.images.clear()
        missing_files: list[str] = []

        for media in self.project.media:
            if media.media_type == "image":
                if not Path(media.path).exists():
                    missing_files.append(f"{media.name} ({media.path})")
                    continue
                image = load_image(media.path)
                if image is not None:
                    self.images[media.id] = image
                else:
                    missing_files.append(f"{media.name} (Laden fehlgeschlagen: {media.path})")

            elif media.media_type == "video":
                if not Path(media.path).exists():
                    missing_files.append(f"{media.name} ({media.path})")
                    continue
                # Erstes Frame mit VideoCapture laden (nicht imread)
                import cv2
                cap = cv2.VideoCapture(media.path)
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    self.images[media.id] = frame
                # Kein Fehler wenn Frame-Extraktion fehlschlaegt - Video Player koennte trotzdem funktionieren

            elif media.media_type == "test":
                pattern_name = media.path.replace("test:", "")
                self.images[media.id] = get_test_pattern(pattern_name)

        self._update_trees()
        self._update_media_list()

        # Session-State wiederherstellen
        self.current_polygon = None
        self.current_media_layer = None
        self.current_output_layer = None

        if self.project.selected_polygon_id:
            self.current_polygon = self.project.get_polygon_by_id(self.project.selected_polygon_id)

        if self.project.selected_media_layer_id:
            self.current_media_layer = self.project.get_media_layer_by_id(self.project.selected_media_layer_id)
        elif self.project.media_layers:
            self.current_media_layer = self.project.media_layers[0]

        if self.project.selected_output_layer_id:
            self.current_output_layer = self.project.get_output_layer_by_id(self.project.selected_output_layer_id)
        elif self.project.output_layers:
            self.current_output_layer = self.project.output_layers[0]

        # Falls kein Polygon ausgewaehlt aber vorhanden, erstes nehmen
        if not self.current_polygon and self.project.polygons:
            self.current_polygon = self.project.polygons[0]

        self._update_canvas()
        self._update_polygon_combos()

        # Videos starten
        for media in self.project.media:
            if media.media_type == "video" and Path(media.path).exists():
                self.video_player.load_video(media.id, media.path)

        # Warnung bei fehlenden Dateien anzeigen
        if missing_files:
            QMessageBox.warning(
                self,
                "Fehlende Mediendateien",
                f"Folgende Dateien konnten nicht geladen werden:\n\n" +
                "\n".join(missing_files[:10]) +
                (f"\n\n... und {len(missing_files) - 10} weitere" if len(missing_files) > 10 else "")
            )

    def eventFilter(self, obj, event) -> bool:
        """Event Filter fuer Trees und Media List - Keyboard Events."""
        if not hasattr(self, 'media_tree') or not hasattr(self, 'output_tree'):
            return super().eventFilter(obj, event)

        # Keyboard Events auf Trees
        if (obj in (self.media_tree, self.output_tree) and
                event.type() == QEvent.Type.KeyPress):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._rename_selected()
                return True
            elif event.key() == Qt.Key.Key_Delete:
                self._delete_selected()
                return True

        # Keyboard Events auf Media List
        if (hasattr(self, 'media_list') and obj == self.media_list and
                event.type() == QEvent.Type.KeyPress):
            if event.key() == Qt.Key.Key_Delete:
                self._delete_selected_media()
                return True

        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        """Handle Fenster schliessen."""
        self.update_timer.stop()
        self.live_source_timer.stop()
        self.transition_timer.stop()
        for window in self.output_windows.values():
            window.close()
        self.live_source_manager.close_all()
        self.video_player.cleanup()
        event.accept()
