"""Canvas-Widgets fuer Polygon-Bearbeitung."""

from typing import Optional, List, Tuple, Dict, Callable
from enum import Enum, auto
import math
import numpy as np

from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QBrush, QColor,
    QMouseEvent, QPaintEvent, QKeyEvent, QWheelEvent, QPolygon,
    QCursor
)
from PyQt6.QtWidgets import QWidget, QSizePolicy

from .models import Polygon, MediaLayer, Project
from .transform import numpy_to_qimage, warp_image, composite_polygons_fast


class HandleType(Enum):
    """Typen von Polygon-Handles."""
    NONE = auto()
    POINT = auto()      # Eck-Punkt verschieben
    CORNER = auto()     # Ecke skalieren
    ROTATE = auto()     # Rotation
    CENTER = auto()     # Ganzes Polygon verschieben


class PolygonCanvas(QWidget):
    """Canvas zum Bearbeiten von Polygon-Punkten."""

    points_changed = pyqtSignal()
    polygon_selected = pyqtSignal(object)  # (polygon)

    # Feste Aspect Ratio fuer Output (16:9)
    OUTPUT_ASPECT_RATIO = 16 / 9

    def __init__(self, mode: str = "source", parent=None):
        """
        Args:
            mode: "source" fuer Media-Ebene, "output" fuer Output-Ebene
        """
        super().__init__(parent)
        self.mode = mode

        # Aktuelles Polygon
        self.current_polygon: Optional[Polygon] = None

        # Alle Polygone fuer Snapping und Anzeige
        self.all_polygons: List[Polygon] = []

        # Project und Images fuer Rendering
        self.project: Optional[Project] = None
        self.all_images: Dict[str, np.ndarray] = {}  # media_id -> image

        # Einzelnes Bild (fuer Source-Canvas)
        self.image: Optional[np.ndarray] = None
        self.pixmap: Optional[QPixmap] = None

        # Punkt-Auswahl und Dragging
        self.selected_point: Optional[int] = None
        self.dragging = False
        self.dragging_shape = False  # Ganzen Shape verschieben
        self.drag_start: Optional[Tuple[float, float]] = None
        self.point_radius = 10
        self.hit_radius = 18

        # Handle-System
        self.active_handle: HandleType = HandleType.NONE
        self.hovered_handle: HandleType = HandleType.NONE
        self.hovered_corner: int = -1  # Welche Ecke fuer CORNER handle
        self.active_corner: int = -1
        self.handle_radius = 8
        self.rotation_handle_distance = 40  # Pixel oberhalb des Polygons
        self.drag_start_points: Optional[List[List[float]]] = None  # Punkte bei Drag-Start
        self.drag_start_center: Optional[Tuple[float, float]] = None
        self.drag_start_angle: float = 0.0
        self.maintain_aspect_ratio = False  # Shift gedrueckt

        # Snapping
        self.snapping_enabled = True
        self.snap_distance = 0.02  # Normalisierte Distanz fuer Snapping

        # Zoom und Pan
        self.zoom_level = 1.0
        self.pan_offset = [0.0, 0.0]  # Normalisiert
        self.panning = False
        self.pan_start: Optional[QPointF] = None
        self.pan_start_offset: Optional[List[float]] = None

        # UI Setup
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Performance: Reusable render buffer
        self._render_buffer: Optional[np.ndarray] = None
        self._last_render_size: tuple = (0, 0)

    def set_snapping(self, enabled: bool) -> None:
        """Aktiviere/Deaktiviere Snapping."""
        self.snapping_enabled = enabled

    def set_current_polygon(self, polygon: Optional[Polygon]) -> None:
        """Setze das aktuell ausgewaehlte Polygon (wird hervorgehoben)."""
        self.current_polygon = polygon
        self.selected_point = None
        self.update()

    def set_polygon(self, polygon: Optional[Polygon]) -> None:
        """Legacy: Setze das aktive Polygon."""
        self.current_polygon = polygon
        self.selected_point = None
        self.update()

    def set_image(self, image: Optional[np.ndarray]) -> None:
        """Setze das Hintergrundbild."""
        self.image = image
        self._update_pixmap()
        self.update()

    def set_all_polygons(self, polygons: List[Polygon]) -> None:
        """Setze alle Polygone fuer Snapping und Anzeige."""
        self.all_polygons = polygons
        self.update()

    def set_all_data(self, project: Project, images: Dict[str, np.ndarray]) -> None:
        """Setze Project und Images fuer Rendering."""
        self.project = project
        self.all_images = images
        self.update()

    # Legacy methods for compatibility
    def set_layer(self, layer: Optional[MediaLayer]) -> None:
        """Legacy: Wird nicht mehr verwendet."""
        pass

    def set_all_layers(self, layers: List[MediaLayer]) -> None:
        """Legacy: Wird nicht mehr verwendet."""
        pass

    def set_all_images(self, images: Dict[str, np.ndarray]) -> None:
        """Legacy: Setze alle Bilder."""
        self.all_images = images
        self.update()

    def _update_pixmap(self) -> None:
        """Aktualisiere das QPixmap vom Bild."""
        if self.image is not None:
            qimg = numpy_to_qimage(self.image)
            if qimg:
                self.pixmap = QPixmap.fromImage(qimg)
            else:
                self.pixmap = None
        else:
            self.pixmap = None

    def _get_aspect_ratio(self) -> float:
        """Hole Aspect Ratio - Output immer 16:9, Source vom Bild."""
        if self.mode == "output":
            return self.OUTPUT_ASPECT_RATIO
        # Source: Aspect Ratio vom Bild
        if self.image is not None:
            h, w = self.image.shape[:2]
            if h > 0:
                return w / h
        return 16 / 9  # Default

    def get_points(self) -> List[List[float]]:
        """Hole die aktuellen Punkte basierend auf dem Modus."""
        if not self.current_polygon:
            return []
        return self.current_polygon.source_points if self.mode == "source" else self.current_polygon.output_points

    def _calc_canvas_rect(self) -> Tuple[int, int, int, int]:
        """Berechne Canvas-Bereich mit korrekter Aspect Ratio."""
        w = self.width()
        h = self.height()
        aspect = self._get_aspect_ratio()

        # Berechne Groesse mit Aspect Ratio
        canvas_w = w
        canvas_h = int(w / aspect)

        if canvas_h > h:
            canvas_h = h
            canvas_w = int(h * aspect)

        # Zentrieren
        x = (w - canvas_w) // 2
        y = (h - canvas_h) // 2

        return (x, y, canvas_w, canvas_h)

    def _norm_to_pixel(self, nx: float, ny: float) -> Tuple[int, int]:
        """Konvertiere normalisierte Koordinaten zu Pixel (mit Zoom/Pan)."""
        x, y, w, h = self._calc_canvas_rect()

        # Zoom und Pan anwenden
        zoomed_nx = (nx - 0.5) * self.zoom_level + 0.5 - self.pan_offset[0]
        zoomed_ny = (ny - 0.5) * self.zoom_level + 0.5 - self.pan_offset[1]

        return int(x + zoomed_nx * w), int(y + zoomed_ny * h)

    def _pixel_to_norm(self, px: int, py: int) -> Tuple[float, float]:
        """Konvertiere Pixel zu normalisierten Koordinaten (mit Zoom/Pan)."""
        x, y, w, h = self._calc_canvas_rect()
        w = max(1, w)
        h = max(1, h)

        # Relative Position im Canvas
        rel_x = (px - x) / w
        rel_y = (py - y) / h

        # Zoom und Pan rueckrechnen
        nx = (rel_x + self.pan_offset[0] - 0.5) / self.zoom_level + 0.5
        ny = (rel_y + self.pan_offset[1] - 0.5) / self.zoom_level + 0.5

        return nx, ny

    def _find_point_at(self, x: int, y: int) -> Optional[int]:
        """Finde einen Punkt des aktuellen Polygons an der gegebenen Position."""
        points = self.get_points()
        for i, (nx, ny) in enumerate(points):
            px, py = self._norm_to_pixel(nx, ny)
            dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if dist <= self.hit_radius:
                return i
        return None

    def _find_polygon_at(self, x: int, y: int) -> Optional[Polygon]:
        """Finde ein Polygon an der gegebenen Position."""
        norm_x, norm_y = self._pixel_to_norm(x, y)

        # Zuerst aktuelles Polygon pruefen
        if self.current_polygon:
            if self._point_in_polygon(norm_x, norm_y, self.current_polygon):
                return self.current_polygon

        # Dann alle anderen Polygone
        for poly in self.all_polygons:
            if poly == self.current_polygon:
                continue
            if self._point_in_polygon(norm_x, norm_y, poly):
                return poly

        return None

    def _point_in_polygon(self, nx: float, ny: float, polygon: Polygon) -> bool:
        """Pruefe ob Punkt im Polygon liegt."""
        points = polygon.source_points if self.mode == "source" else polygon.output_points
        if len(points) < 3:
            return False

        n = len(points)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = points[i]
            xj, yj = points[j]
            if ((yi > ny) != (yj > ny)) and (nx < (xj - xi) * (ny - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def _get_polygon_center(self, points: List[List[float]]) -> Tuple[float, float]:
        """Berechne Zentrum eines Polygons (Durchschnitt aller Punkte)."""
        if not points:
            return 0.5, 0.5
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        return cx, cy

    def _get_rotation_handle_pos(self, points: List[List[float]]) -> Tuple[int, int]:
        """Berechne Position des Rotations-Handles (oberhalb des Polygons)."""
        if not points:
            return 0, 0

        # Finde obersten Punkt
        min_y = min(p[1] for p in points)
        cx, _ = self._get_polygon_center(points)

        # Handle oberhalb des obersten Punkts
        px, py = self._norm_to_pixel(cx, min_y)
        py -= self.rotation_handle_distance
        return px, py

    def _get_corner_handle_positions(self, points: List[List[float]]) -> List[Tuple[int, int]]:
        """Berechne Positionen der Eck-Handles (zum Skalieren)."""
        positions = []
        for p in points:
            px, py = self._norm_to_pixel(p[0], p[1])
            positions.append((px, py))
        return positions

    def _get_center_handle_pos(self, points: List[List[float]]) -> Tuple[int, int]:
        """Berechne Position des Center-Handles."""
        cx, cy = self._get_polygon_center(points)
        return self._norm_to_pixel(cx, cy)

    def _find_handle_at(self, x: int, y: int) -> Tuple[HandleType, int]:
        """
        Finde welcher Handle an der Position ist.
        Returns: (HandleType, corner_index) wobei corner_index nur fuer CORNER/POINT relevant ist.
        """
        points = self.get_points()
        if not points or not self.current_polygon:
            return HandleType.NONE, -1

        # Rotation Handle (hoechste Prioritaet)
        rx, ry = self._get_rotation_handle_pos(points)
        if ((x - rx) ** 2 + (y - ry) ** 2) ** 0.5 <= self.handle_radius + 5:
            return HandleType.ROTATE, -1

        # Corner/Point Handles
        corner_positions = self._get_corner_handle_positions(points)
        for i, (px, py) in enumerate(corner_positions):
            dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if dist <= self.hit_radius:
                return HandleType.POINT, i

        # Center Handle
        cx, cy = self._get_center_handle_pos(points)
        if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= self.handle_radius + 5:
            return HandleType.CENTER, -1

        # Im Polygon drin = auch Center (verschieben)
        if self._is_inside_shape(x, y):
            return HandleType.CENTER, -1

        return HandleType.NONE, -1

    def _get_cursor_for_handle(self, handle_type: HandleType, corner: int = -1) -> QCursor:
        """Hole passenden Cursor fuer Handle-Typ."""
        if handle_type == HandleType.ROTATE:
            # Rotation: CrossCursor als Platzhalter (idealerweise custom)
            return QCursor(Qt.CursorShape.CrossCursor)
        elif handle_type == HandleType.POINT:
            return QCursor(Qt.CursorShape.CrossCursor)
        elif handle_type == HandleType.CORNER:
            # Diagonal resize basierend auf Ecke
            if corner in [0, 2]:  # TL, BR
                return QCursor(Qt.CursorShape.SizeFDiagCursor)
            else:  # TR, BL
                return QCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle_type == HandleType.CENTER:
            return QCursor(Qt.CursorShape.SizeAllCursor)
        return QCursor(Qt.CursorShape.ArrowCursor)

    def _rotate_point(self, px: float, py: float, cx: float, cy: float, angle: float) -> Tuple[float, float]:
        """Rotiere einen Punkt um ein Zentrum."""
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx = px - cx
        dy = py - cy
        new_x = cx + dx * cos_a - dy * sin_a
        new_y = cy + dx * sin_a + dy * cos_a
        return new_x, new_y

    def _scale_points(self, points: List[List[float]], center: Tuple[float, float],
                      scale_x: float, scale_y: float) -> List[List[float]]:
        """Skaliere Punkte um ein Zentrum."""
        cx, cy = center
        result = []
        for px, py in points:
            new_x = cx + (px - cx) * scale_x
            new_y = cy + (py - cy) * scale_y
            # Clamp auf [0, 1]
            new_x = max(0.0, min(1.0, new_x))
            new_y = max(0.0, min(1.0, new_y))
            result.append([new_x, new_y])
        return result

    def _get_all_snap_points(self) -> List[Tuple[float, float]]:
        """Hole alle Punkte aller Polygone fuer Snapping (ausser aktueller Punkt)."""
        snap_points = []

        for poly in self.all_polygons:
            points = poly.source_points if self.mode == "source" else poly.output_points
            for i, (px, py) in enumerate(points):
                # Aktuellen Punkt ausschliessen
                if poly == self.current_polygon and i == self.selected_point:
                    continue
                snap_points.append((px, py))

        return snap_points

    def _apply_snapping(self, nx: float, ny: float) -> Tuple[float, float]:
        """Wende Snapping an falls aktiviert."""
        if not self.snapping_enabled:
            return nx, ny

        snap_points = self._get_all_snap_points()
        min_dist = float('inf')
        snapped_x, snapped_y = nx, ny

        for sx, sy in snap_points:
            dist = ((nx - sx) ** 2 + (ny - sy) ** 2) ** 0.5
            if dist < min_dist and dist < self.snap_distance:
                min_dist = dist
                snapped_x, snapped_y = sx, sy

        return snapped_x, snapped_y

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hintergrund
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        # Canvas-Bereich mit Aspect Ratio
        cx, cy, cw, ch = self._calc_canvas_rect()

        # Canvas-Hintergrund
        painter.fillRect(cx, cy, cw, ch, QColor(50, 50, 50))

        # Clipping auf Canvas-Bereich
        painter.setClipRect(cx, cy, cw, ch)

        if self.mode == "source":
            self._draw_source_view(painter)
        else:
            self._draw_output_view(painter)

        painter.setClipping(False)

        # Kleine Labels
        painter.setPen(QColor(150, 150, 150))
        label = "Source" if self.mode == "source" else "Output"
        if self.zoom_level != 1.0:
            label += f" ({self.zoom_level:.1f}x)"
        if self.snapping_enabled:
            label += " [Snap]"
        painter.drawText(cx + 5, cy + 15, label)

        # Handle-Hints
        if self.current_polygon:
            hints = []
            if self.active_handle == HandleType.ROTATE or self.hovered_handle == HandleType.ROTATE:
                hints.append("Rotate")
            elif self.active_handle == HandleType.CENTER or self.hovered_handle == HandleType.CENTER:
                hints.append("Move")
            elif self.active_handle == HandleType.POINT or self.hovered_handle == HandleType.POINT:
                if self.maintain_aspect_ratio:
                    hints.append("Scale (uniform)")
                else:
                    hints.append("Drag point | Shift: Scale")

            if hints:
                hint_text = " | ".join(hints)
                painter.setPen(QColor(200, 200, 100))
                painter.drawText(cx + 5, cy + ch - 10, hint_text)

        painter.end()

    def _draw_source_view(self, painter: QPainter) -> None:
        """Zeichne Source-Ansicht mit Bild und allen Polygonen."""
        cx, cy, cw, ch = self._calc_canvas_rect()

        # Bild zeichnen
        if self.pixmap:
            # Skalieren auf Canvas-Groesse und Zoom anwenden
            scaled_w = int(cw * self.zoom_level)
            scaled_h = int(ch * self.zoom_level)

            if scaled_w > 0 and scaled_h > 0:
                scaled = self.pixmap.scaled(
                    scaled_w, scaled_h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

                # Position mit Pan
                img_x = cx + int(-self.pan_offset[0] * cw)
                img_y = cy + int(-self.pan_offset[1] * ch)

                # Zentrieren bei Zoom
                img_x += int((cw - scaled_w) / 2)
                img_y += int((ch - scaled_h) / 2)

                painter.drawPixmap(img_x, img_y, scaled)

        # Alle Polygone zeichnen
        self._draw_all_polygons(painter)

        # Kein Polygon-Hinweis
        if not self.all_polygons:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Kein Polygon ausgewaehlt")

    def _draw_output_view(self, painter: QPainter) -> None:
        """Zeichne Output-Ansicht als Live-Preview."""
        cx, cy, cw, ch = self._calc_canvas_rect()

        # Composite aller Polygone rendern
        self._draw_composite_preview(painter)

        # Dann Edit-Overlay fuer alle Polygone
        self._draw_all_polygons(painter)

        # Kein Polygon-Hinweis
        if not self.all_polygons:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Kein Polygon ausgewaehlt")

    def _draw_composite_preview(self, painter: QPainter) -> None:
        """Zeichne Composite-Preview - optimiert mit Buffer-Reuse."""
        cx, cy, cw, ch = self._calc_canvas_rect()

        if cw <= 0 or ch <= 0 or not self.project:
            return

        # Composite-Groesse anpassen fuer Zoom
        render_w = int(cw * self.zoom_level)
        render_h = int(ch * self.zoom_level)

        if render_w <= 0 or render_h <= 0:
            return

        # Buffer bei Groessenaenderung neu erstellen
        if self._last_render_size != (render_w, render_h):
            self._render_buffer = np.zeros((render_h, render_w, 3), dtype=np.uint8)
            self._last_render_size = (render_w, render_h)

        polygons_data = []

        for poly in self.all_polygons:
            if not poly.media_layer_id:
                continue

            media_layer = self.project.get_media_layer_by_id(poly.media_layer_id)
            if not media_layer or not media_layer.visible or not media_layer.media_id:
                continue

            image = self.all_images.get(media_layer.media_id)
            if image is not None:
                polygons_data.append((image, poly.source_points, poly.output_points))

        if polygons_data:
            composite = composite_polygons_fast(polygons_data, (render_w, render_h), self._render_buffer)
            qimg = numpy_to_qimage(composite)
            if qimg:
                img_x = cx + int(-self.pan_offset[0] * cw) + int((cw - render_w) / 2)
                img_y = cy + int(-self.pan_offset[1] * ch) + int((ch - render_h) / 2)
                painter.drawImage(img_x, img_y, qimg)

    def _draw_all_polygons(self, painter: QPainter) -> None:
        """Zeichne alle Polygone."""
        # Zuerst nicht-aktive Polygone (grau)
        for poly in self.all_polygons:
            if poly == self.current_polygon:
                continue
            self._draw_polygon(painter, poly, is_current=False)

        # Dann aktuelles Polygon
        if self.current_polygon:
            self._draw_polygon(painter, self.current_polygon, is_current=True)

    def _draw_polygon(self, painter: QPainter, polygon: Polygon, is_current: bool) -> None:
        """Zeichne ein einzelnes Polygon mit Punkten und Kanten."""
        if self.mode == "source":
            points = polygon.source_points
        else:
            points = polygon.output_points

        if not points:
            return

        pixel_points = [self._norm_to_pixel(p[0], p[1]) for p in points]

        # Diagonalen (Hilfslinien) bei 4 Punkten - nur fuer aktuelles Polygon
        if len(pixel_points) >= 4 and is_current:
            painter.setPen(QPen(QColor(0, 100, 100, 150), 1, Qt.PenStyle.DashLine))
            painter.drawLine(pixel_points[0][0], pixel_points[0][1],
                             pixel_points[2][0], pixel_points[2][1])
            painter.drawLine(pixel_points[1][0], pixel_points[1][1],
                             pixel_points[3][0], pixel_points[3][1])

        # Gefuelltes Polygon (halbtransparent)
        if is_current:
            painter.setBrush(QBrush(QColor(0, 150, 255, 40)))
        else:
            painter.setBrush(QBrush(QColor(100, 100, 100, 25)))
        painter.setPen(Qt.PenStyle.NoPen)
        qpoly = QPolygon([QPoint(p[0], p[1]) for p in pixel_points])
        painter.drawPolygon(qpoly)

        # Kanten
        if is_current:
            painter.setPen(QPen(QColor(0, 200, 255), 2))
        else:
            painter.setPen(QPen(QColor(150, 150, 150), 1))

        for i in range(len(pixel_points)):
            p1 = pixel_points[i]
            p2 = pixel_points[(i + 1) % len(pixel_points)]
            painter.drawLine(p1[0], p1[1], p2[0], p2[1])

        # Punkte und Handles
        if is_current:
            # Eck-Punkte mit Nummern
            for i, (px, py) in enumerate(pixel_points):
                is_hovered = (self.hovered_handle == HandleType.POINT and self.hovered_corner == i)
                is_selected = (i == self.selected_point)
                is_active = (self.active_handle == HandleType.POINT and self.active_corner == i)

                if is_selected or is_active:
                    painter.setBrush(QBrush(QColor(255, 80, 80)))
                    painter.setPen(QPen(QColor(255, 255, 255), 3))
                    radius = self.point_radius + 4
                elif is_hovered:
                    painter.setBrush(QBrush(QColor(100, 255, 150)))
                    painter.setPen(QPen(QColor(255, 255, 255), 2))
                    radius = self.point_radius + 2
                else:
                    painter.setBrush(QBrush(QColor(0, 200, 100)))
                    painter.setPen(QPen(QColor(255, 255, 255), 2))
                    radius = self.point_radius

                painter.drawEllipse(QPoint(px, py), radius, radius)

                # Punkt-Nummer
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(px - 4, py + 4, str(i + 1))

            # Center Handle (Move Icon)
            cx, cy = self._get_center_handle_pos(points)
            is_center_hovered = self.hovered_handle == HandleType.CENTER
            is_center_active = self.active_handle == HandleType.CENTER

            if is_center_active:
                painter.setBrush(QBrush(QColor(255, 200, 80)))
            elif is_center_hovered:
                painter.setBrush(QBrush(QColor(255, 255, 150)))
            else:
                painter.setBrush(QBrush(QColor(200, 200, 200, 180)))
            painter.setPen(QPen(QColor(50, 50, 50), 2))
            painter.drawEllipse(QPoint(cx, cy), self.handle_radius, self.handle_radius)

            # Move-Kreuz im Center
            painter.setPen(QPen(QColor(50, 50, 50), 2))
            cross_size = 4
            painter.drawLine(cx - cross_size, cy, cx + cross_size, cy)
            painter.drawLine(cx, cy - cross_size, cx, cy + cross_size)

            # Rotation Handle
            rx, ry = self._get_rotation_handle_pos(points)
            is_rotate_hovered = self.hovered_handle == HandleType.ROTATE
            is_rotate_active = self.active_handle == HandleType.ROTATE

            # Linie vom Polygon zum Rotation Handle
            top_y = min(p[1] for p in pixel_points)
            painter.setPen(QPen(QColor(150, 150, 255, 150), 1, Qt.PenStyle.DashLine))
            painter.drawLine(cx, int(top_y), rx, ry)

            # Rotation Handle Kreis
            if is_rotate_active:
                painter.setBrush(QBrush(QColor(150, 150, 255)))
            elif is_rotate_hovered:
                painter.setBrush(QBrush(QColor(200, 200, 255)))
            else:
                painter.setBrush(QBrush(QColor(100, 100, 200, 180)))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(QPoint(rx, ry), self.handle_radius, self.handle_radius)

            # Rotation Icon (gebogener Pfeil)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            # Einfacher Bogen
            from PyQt6.QtCore import QRect
            arc_rect = QRect(rx - 4, ry - 4, 8, 8)
            painter.drawArc(arc_rect, 0, 270 * 16)  # 270 Grad Bogen

        else:
            # Nicht-aktuelles Polygon: Kleine Punkte
            for px, py in pixel_points:
                painter.setBrush(QBrush(QColor(150, 150, 150)))
                painter.setPen(QPen(QColor(200, 200, 200), 1))
                painter.drawEllipse(QPoint(px, py), 5, 5)

            # Name in der Mitte
            if pixel_points:
                center_x = sum(p[0] for p in pixel_points) // len(pixel_points)
                center_y = sum(p[1] for p in pixel_points) // len(pixel_points)
                painter.setPen(QColor(180, 180, 180))
                painter.drawText(center_x - 20, center_y, polygon.name)

    def _is_inside_shape(self, x: int, y: int) -> bool:
        """Pruefe ob Punkt innerhalb des aktuellen Shapes liegt."""
        points = self.get_points()
        if len(points) < 3:
            return False

        # Ray casting algorithm
        nx, ny = self._pixel_to_norm(x, y)
        n = len(points)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = points[i]
            xj, yj = points[j]

            if ((yi > ny) != (yj > ny)) and (nx < (xj - xi) * (ny - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            # Pan starten
            self.panning = True
            self.pan_start = event.position()
            self.pan_start_offset = self.pan_offset.copy()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            x, y = int(event.position().x()), int(event.position().y())

            # Shift-Taste pruefen fuer Aspect Ratio Lock
            self.maintain_aspect_ratio = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            # Handle finden
            handle_type, corner = self._find_handle_at(x, y)

            if handle_type != HandleType.NONE and self.current_polygon:
                points = self.get_points()
                self.active_handle = handle_type
                self.active_corner = corner
                self.drag_start = self._pixel_to_norm(x, y)
                self.drag_start_points = [p.copy() for p in points]
                self.drag_start_center = self._get_polygon_center(points)

                if handle_type == HandleType.ROTATE:
                    # Start-Winkel berechnen
                    cx, cy = self.drag_start_center
                    nx, ny = self._pixel_to_norm(x, y)
                    self.drag_start_angle = math.atan2(ny - cy, nx - cx)

                if handle_type == HandleType.POINT:
                    self.selected_point = corner
                    self.dragging = True
                    self.dragging_shape = False
                elif handle_type == HandleType.CENTER:
                    self.selected_point = None
                    self.dragging = False
                    self.dragging_shape = True
                else:
                    self.selected_point = None
                    self.dragging = False
                    self.dragging_shape = False
            else:
                # Pruefen ob anderes Polygon angeklickt wurde
                poly = self._find_polygon_at(x, y)
                if poly is not None and poly != self.current_polygon:
                    # Anderes Polygon auswaehlen - Signal senden
                    self.polygon_selected.emit(poly)
                self.active_handle = HandleType.NONE
                self.active_corner = -1
                self.selected_point = None
                self.dragging = False
                self.dragging_shape = False

            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x, y = int(event.position().x()), int(event.position().y())

        # Shift-Taste pruefen
        self.maintain_aspect_ratio = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if self.panning and self.pan_start and self.pan_start_offset:
            # Pan durchfuehren
            cx, cy, cw, ch = self._calc_canvas_rect()
            if cw > 0 and ch > 0:
                dx = (event.position().x() - self.pan_start.x()) / cw
                dy = (event.position().y() - self.pan_start.y()) / ch
                self.pan_offset[0] = self.pan_start_offset[0] - dx
                self.pan_offset[1] = self.pan_start_offset[1] - dy
                self.update()
            return

        nx, ny = self._pixel_to_norm(x, y)

        # Aktiver Handle - Interaktion laeuft
        if self.active_handle != HandleType.NONE and self.current_polygon and self.drag_start_points:
            if self.active_handle == HandleType.POINT:
                if self.maintain_aspect_ratio and self.drag_start_center:
                    # Shift gedrueckt: Uniform scaling vom Zentrum
                    cx, cy = self.drag_start_center
                    orig_corner = self.drag_start_points[self.active_corner]

                    # Urspruengliche Distanz zum Zentrum
                    orig_dist = math.sqrt((orig_corner[0] - cx) ** 2 + (orig_corner[1] - cy) ** 2)
                    if orig_dist > 0.001:
                        # Neue Distanz zum Zentrum
                        new_dist = math.sqrt((nx - cx) ** 2 + (ny - cy) ** 2)
                        scale = new_dist / orig_dist

                        # Alle Punkte skalieren
                        new_points = self._scale_points(self.drag_start_points, (cx, cy), scale, scale)

                        if self.mode == "source":
                            self.current_polygon.source_points = new_points
                        else:
                            self.current_polygon.output_points = new_points
                else:
                    # Einzelnen Punkt verschieben
                    nx = max(0.0, min(1.0, nx))
                    ny = max(0.0, min(1.0, ny))
                    nx, ny = self._apply_snapping(nx, ny)

                    if self.mode == "source":
                        self.current_polygon.source_points[self.active_corner] = [nx, ny]
                    else:
                        self.current_polygon.output_points[self.active_corner] = [nx, ny]

            elif self.active_handle == HandleType.CENTER:
                # Ganzes Polygon verschieben
                start_nx, start_ny = self.drag_start
                dx = nx - start_nx
                dy = ny - start_ny

                new_points = []
                for px, py in self.drag_start_points:
                    new_x = max(0.0, min(1.0, px + dx))
                    new_y = max(0.0, min(1.0, py + dy))
                    new_points.append([new_x, new_y])

                if self.mode == "source":
                    self.current_polygon.source_points = new_points
                else:
                    self.current_polygon.output_points = new_points

            elif self.active_handle == HandleType.ROTATE:
                # Rotation um Zentrum
                cx, cy = self.drag_start_center
                current_angle = math.atan2(ny - cy, nx - cx)
                delta_angle = current_angle - self.drag_start_angle

                new_points = []
                for px, py in self.drag_start_points:
                    new_x, new_y = self._rotate_point(px, py, cx, cy, delta_angle)
                    new_x = max(0.0, min(1.0, new_x))
                    new_y = max(0.0, min(1.0, new_y))
                    new_points.append([new_x, new_y])

                if self.mode == "source":
                    self.current_polygon.source_points = new_points
                else:
                    self.current_polygon.output_points = new_points

            self.update()
            self.points_changed.emit()
            return

        # Kein aktiver Handle - Hover-Feedback aktualisieren
        if self.current_polygon:
            old_hovered = self.hovered_handle
            old_corner = self.hovered_corner
            self.hovered_handle, self.hovered_corner = self._find_handle_at(x, y)

            if self.hovered_handle != old_hovered or self.hovered_corner != old_corner:
                # Cursor aktualisieren
                self.setCursor(self._get_cursor_for_handle(self.hovered_handle, self.hovered_corner))
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.panning = False
            self.pan_start = None
            self.pan_start_offset = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.dragging_shape = False
            self.drag_start = None
            self.active_handle = HandleType.NONE
            self.active_corner = -1
            self.drag_start_points = None
            self.drag_start_center = None
            self.drag_start_angle = 0.0

            # Cursor zuruecksetzen auf Hover-Status
            x, y = int(event.position().x()), int(event.position().y())
            self.hovered_handle, self.hovered_corner = self._find_handle_at(x, y)
            self.setCursor(self._get_cursor_for_handle(self.hovered_handle, self.hovered_corner))
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Doppelklick: Zoom zuruecksetzen."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Pruefen ob Klick auf leeren Bereich
            x, y = int(event.position().x()), int(event.position().y())
            if self._find_point_at(x, y) is None and not self._is_inside_shape(x, y):
                self.zoom_level = 1.0
                self.pan_offset = [0.0, 0.0]
                self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Mausrad: Zoomen."""
        delta = event.angleDelta().y()
        if delta == 0:
            return

        # Zoom-Faktor
        zoom_factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = self.zoom_level * zoom_factor
        new_zoom = max(0.5, min(5.0, new_zoom))

        if new_zoom != self.zoom_level:
            # Zoom zentriert auf Mausposition
            pos = event.position()
            cx, cy, cw, ch = self._calc_canvas_rect()

            if cw > 0 and ch > 0:
                # Position relativ zum Canvas-Zentrum
                rel_x = (pos.x() - cx) / cw - 0.5
                rel_y = (pos.y() - cy) / ch - 0.5

                # Pan anpassen um auf Mausposition zu zoomen
                scale_change = new_zoom / self.zoom_level
                self.pan_offset[0] += rel_x * (1 - scale_change) / new_zoom
                self.pan_offset[1] += rel_y * (1 - scale_change) / new_zoom

            self.zoom_level = new_zoom
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Tastatureingaben: Pfeiltasten fuer Punkt-Verschiebung."""
        if self.selected_point is None or not self.current_polygon:
            return

        # Schrittgroesse
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            step = 0.02  # Groesserer Schritt mit Shift
        else:
            step = 0.005  # Kleiner Schritt

        points = self.get_points()
        if not points or self.selected_point >= len(points):
            return

        px, py = points[self.selected_point]
        moved = False

        if event.key() == Qt.Key.Key_Left:
            px = max(0.0, px - step)
            moved = True
        elif event.key() == Qt.Key.Key_Right:
            px = min(1.0, px + step)
            moved = True
        elif event.key() == Qt.Key.Key_Up:
            py = max(0.0, py - step)
            moved = True
        elif event.key() == Qt.Key.Key_Down:
            py = min(1.0, py + step)
            moved = True

        if moved:
            points[self.selected_point] = [px, py]
            self.update()
            self.points_changed.emit()
