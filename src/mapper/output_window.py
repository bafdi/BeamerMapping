"""Output-Fenster fuer Projektor - Performance-optimiert."""

from typing import Optional, Dict, List
import numpy as np

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QKeyEvent,
    QMouseEvent, QPaintEvent, QImage
)
from PyQt6.QtWidgets import QWidget

from .models import OutputLayer, Polygon, MediaLayer, Project
from .transform import composite_polygons_fast, numpy_to_qimage


class OutputWindow(QWidget):
    """Separates Output-Fenster fuer einen Output Layer (Projektor/Beamer)."""

    points_changed = pyqtSignal()

    def __init__(
        self,
        output_layer: OutputLayer,
        project: Optional[Project] = None,
        images: Optional[Dict[str, np.ndarray]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.output_layer = output_layer
        self.project = project
        self.images: Dict[str, np.ndarray] = images or {}  # media_id -> image

        self.setWindowTitle(f"Output: {output_layer.name}")
        self.setStyleSheet("background-color: black;")
        self.setMinimumSize(640, 480)

        # Frameless window fuer clean output
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint
        )

        # Edit-Mode - default OFF fuer clean output
        self.edit_mode = False
        self.selected_polygon: Optional[Polygon] = None
        self.selected_point: Optional[int] = None
        self.dragging = False
        self.point_radius = 12
        self.hit_radius = 20

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)

        # Performance: Reusable render buffer
        self._render_buffer: Optional[np.ndarray] = None
        self._last_size: tuple = (0, 0)
        
        # Performance: Track which media IDs this output displays
        self._displayed_media_ids: set = set()

    def set_output_layer(self, output_layer: OutputLayer) -> None:
        """Setze den Output Layer."""
        self.output_layer = output_layer
        self.setWindowTitle(f"Output: {output_layer.name}")
        self._displayed_media_ids = set()  # Cache invalidieren
        self.update()

    def set_project(self, project: Project) -> None:
        """Setze das Projekt."""
        self.project = project
        self._displayed_media_ids = set()  # Cache invalidieren
        self.update()

    def set_images(self, images: Dict[str, np.ndarray]) -> None:
        """Setze alle Bilder."""
        self.images = images
        self.update()

    # Legacy methods for compatibility
    def set_output(self, output: OutputLayer) -> None:
        """Legacy: Alias fuer set_output_layer."""
        self.set_output_layer(output)

    def set_layers(self, layers: List[MediaLayer]) -> None:
        """Legacy: Wird nicht mehr verwendet."""
        self._displayed_media_ids = set()  # Cache invalidieren

    def set_image_for_media(self, media_id: str, image: np.ndarray) -> None:
        """Legacy: Setze ein Bild fuer eine Media-ID."""
        self.images[media_id] = image
        self.update()

    def set_edit_mode(self, enabled: bool) -> None:
        """Schalte Edit-Mode um."""
        self.edit_mode = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.BlankCursor)
        self.update()

    def _norm_to_pixel(self, nx: float, ny: float) -> tuple[int, int]:
        return int(nx * self.width()), int(ny * self.height())

    def _pixel_to_norm(self, px: int, py: int) -> tuple[float, float]:
        return px / max(1, self.width()), py / max(1, self.height())

    def _get_polygons_for_this_output(self) -> List[Polygon]:
        """Hole alle Polygone die auf diesem Output Layer angezeigt werden."""
        if not self.project or not self.output_layer:
            return []
        return self.project.get_polygons_for_output_layer(self.output_layer.id)
    
    def get_displayed_media_ids(self) -> set:
        """Hole alle Media-IDs die auf diesem Output angezeigt werden (cached)."""
        # Cache leeren wenn sich Projekt geaendert hat
        media_ids = set()
        if not self.project:
            self._displayed_media_ids = media_ids
            return media_ids
        
        for poly in self._get_polygons_for_this_output():
            if poly.media_layer_id:
                media_layer = self.project.get_media_layer_by_id(poly.media_layer_id)
                if media_layer and media_layer.visible and media_layer.media_id:
                    media_ids.add(media_layer.media_id)
        
        self._displayed_media_ids = media_ids
        return media_ids
    
    def invalidate_media_cache(self) -> None:
        """Invalidiere den Cache der angezeigten Media-IDs."""
        self._displayed_media_ids = set()
    
    def update_if_displays_media(self, media_id: str) -> None:
        """Update nur wenn dieses Media auf diesem Output angezeigt wird."""
        # Verwende cached Set wenn vorhanden, sonst neu berechnen
        if not self._displayed_media_ids:
            self._displayed_media_ids = self.get_displayed_media_ids()
        
        if media_id in self._displayed_media_ids:
            self.update()

    def _get_all_polygons_with_images(self) -> List[tuple[Polygon, Optional[np.ndarray]]]:
        """Hole alle Polygone dieses Outputs mit ihren Bildern."""
        result = []
        media_ids = set()

        if not self.project:
            self._displayed_media_ids = media_ids
            return result

        for poly in self._get_polygons_for_this_output():
            # Bild vom zugehoerigen Media Layer holen
            image = None
            if poly.media_layer_id:
                media_layer = self.project.get_media_layer_by_id(poly.media_layer_id)
                if media_layer and media_layer.visible and media_layer.media_id:
                    image = self.images.get(media_layer.media_id)
                    media_ids.add(media_layer.media_id)  # Cache waehrend Iteration

            result.append((poly, image))
        
        # Cache aktualisieren wenn wir polygons durchlaufen haben
        self._displayed_media_ids = media_ids
        return result

    def _find_point_at(self, x: int, y: int) -> tuple[Optional[Polygon], Optional[int]]:
        """Finde einen Punkt an der Position."""
        for poly, _ in self._get_all_polygons_with_images():
            for i, (nx, ny) in enumerate(poly.output_points):
                px, py = self._norm_to_pixel(nx, ny)
                dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                if dist <= self.hit_radius:
                    return poly, i
        return None, None

    def paintEvent(self, event: QPaintEvent) -> None:
        # Optimierung: Skip rendering wenn Fenster nicht sichtbar
        if not self.isVisible():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Schwarzer Hintergrund
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # Alle Polygone rendern
        w, h = self.width(), self.height()
        if w > 0 and h > 0:
            self._render_all_polygons(painter)

        # Edit-Overlay nur wenn aktiviert
        if self.edit_mode:
            self._draw_edit_overlay(painter)

        painter.end()

    def _render_all_polygons(self, painter: QPainter) -> None:
        """Rendere alle Polygone dieses Output Layers - optimiert mit Buffer-Reuse."""
        w, h = self.width(), self.height()

        # Buffer bei Groessenaenderung neu erstellen
        if self._last_size != (w, h):
            self._render_buffer = np.zeros((h, w, 3), dtype=np.uint8)
            self._last_size = (w, h)

        polygons_data = []

        for poly, image in self._get_all_polygons_with_images():
            if image is not None:
                polygons_data.append((image, poly.source_points, poly.output_points))

        if polygons_data:
            composite = composite_polygons_fast(polygons_data, (w, h), self._render_buffer)
            qimg = numpy_to_qimage(composite)
            if qimg:
                painter.drawImage(0, 0, qimg)

    def _draw_edit_overlay(self, painter: QPainter) -> None:
        """Zeichne Edit-Overlay mit allen Polygonen."""
        for poly, _ in self._get_all_polygons_with_images():
            is_selected = (poly == self.selected_polygon)
            self._draw_polygon_overlay(painter, poly, is_selected)

        # Hinweis nur im Edit-Mode
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(10, 20, "EDIT MODE | M=Toggle | F=Fullscreen | Esc=Exit")

    def _draw_polygon_overlay(self, painter: QPainter, poly: Polygon, is_selected: bool) -> None:
        """Zeichne Overlay fuer ein Polygon."""
        points = poly.output_points
        pixel_points = [self._norm_to_pixel(p[0], p[1]) for p in points]

        # Kanten
        color = QColor(255, 200, 0) if is_selected else QColor(0, 255, 255)
        painter.setPen(QPen(color, 3 if is_selected else 2))

        for i in range(len(pixel_points)):
            p1 = pixel_points[i]
            p2 = pixel_points[(i + 1) % len(pixel_points)]
            painter.drawLine(p1[0], p1[1], p2[0], p2[1])

        # Punkte
        for i, (px, py) in enumerate(pixel_points):
            is_point_selected = (is_selected and i == self.selected_point)

            if is_point_selected:
                painter.setBrush(QBrush(QColor(255, 50, 50)))
                painter.setPen(QPen(QColor(255, 255, 255), 3))
                radius = self.point_radius + 5
            else:
                painter.setBrush(QBrush(QColor(0, 255, 100)))
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                radius = self.point_radius

            painter.drawEllipse(QPoint(px, py), radius, radius)

            # Nummer
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(px - 4, py + 4, str(i + 1))

        # Polygon-Name
        if pixel_points:
            cx = sum(p[0] for p in pixel_points) // len(pixel_points)
            cy = sum(p[1] for p in pixel_points) // len(pixel_points)
            painter.setPen(color)
            painter.drawText(cx - 30, cy, poly.name)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            x, y = int(event.position().x()), int(event.position().y())
            poly, point_idx = self._find_point_at(x, y)

            if poly is not None and point_idx is not None:
                self.selected_polygon = poly
                self.selected_point = point_idx
                self.dragging = True
            else:
                self.selected_polygon = None
                self.selected_point = None

            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode:
            return

        if self.dragging and self.selected_polygon and self.selected_point is not None:
            x, y = int(event.position().x()), int(event.position().y())
            nx, ny = self._pixel_to_norm(x, y)
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))

            self.selected_polygon.output_points[self.selected_point] = [nx, ny]
            self.update()
            self.points_changed.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        if key == Qt.Key.Key_M:
            self.set_edit_mode(not self.edit_mode)
        elif key == Qt.Key.Key_F or key == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif key == Qt.Key.Key_Q:
            self.close()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update()
