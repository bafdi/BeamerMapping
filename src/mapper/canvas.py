"""Canvas-Widgets fuer Polygon-Bearbeitung."""

import time
from typing import Optional, List, Tuple, Dict, Callable
from enum import Enum, auto
import math
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QBrush, QColor,
    QMouseEvent, QPaintEvent, QKeyEvent, QWheelEvent, QPolygon,
    QCursor, QFont
)
from PyQt6.QtWidgets import QWidget, QSizePolicy, QPushButton, QMenu

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
    polygon_selected = pyqtSignal(object, int)  # (polygon, modifiers)
    reset_points_requested = pyqtSignal()

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

        # Button-Style fuer Overlay-Buttons (unten rechts im Canvas)
        overlay_btn_style = """
            QPushButton {
                background: rgba(80, 80, 80, 180);
                color: white;
                border: 1px solid rgba(150, 150, 150, 120);
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover { background: rgba(120, 120, 120, 220); }
        """

        # Reset-Button (unten rechts im Canvas, links neben Fit)
        reset_label = "\u21BA" # ↺
        reset_tip = "Source-Punkte zurücksetzen" if mode == "source" else "Output-Punkte zurücksetzen"
        self._reset_btn = QPushButton(reset_label, self)
        self._reset_btn.setFixedSize(24, 24)
        self._reset_btn.setToolTip(reset_tip)
        self._reset_btn.clicked.connect(self.reset_points_requested.emit)
        self._reset_btn.setStyleSheet(overlay_btn_style)

        # Fit-Button (unten rechts im Canvas)
        self._fit_btn = QPushButton("\u2922", self)  # ⤢ icon
        self._fit_btn.setFixedSize(24, 24)
        self._fit_btn.setToolTip("Reset zoom/pan")
        self._fit_btn.clicked.connect(self.reset_view)
        self._fit_btn.setStyleSheet(overlay_btn_style)

        # FPS Counter
        self._show_fps = False
        self._fps_frame_count = 0
        self._fps_last_time = time.monotonic()
        self._fps_value = 0.0

        # Performance: Reusable render buffer
        self._render_buffer: Optional[np.ndarray] = None
        self._last_render_size: tuple = (0, 0)

        # Crossfade state (nur fuer Output-Canvas): Live-Rendering
        self._crossfade_from_data: Optional[List[tuple]] = None
        self._crossfade_from_alpha: float = 1.0
        self._crossfade_to_alpha: float = 0.0
        self._crossfade_buffer: Optional[np.ndarray] = None
        self._crossfade_buffer_size: tuple = (0, 0)

        # Border Highlight (Freeze/Blackout Indikator)
        self._border_color: Optional[QColor] = None

        # Multi-Select
        self.selected_polygons: List[Polygon] = []
        self._undo_stack = None
        self._refresh_cb = None
        self._multi_drag_start: Optional[Dict[str, List[List[float]]]] = None

    def reset_view(self) -> None:
        """Setze Zoom und Pan zurueck."""
        self.zoom_level = 1.0
        self.pan_offset = [0.0, 0.0]
        self.update()

    def set_snapping(self, enabled: bool, distance: float = 0.02) -> None:
        """Aktiviere/Deaktiviere Snapping mit optionaler Distanz."""
        self.snapping_enabled = enabled
        self.snap_distance = distance

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

    def set_show_fps(self, enabled: bool) -> None:
        """Aktiviere/Deaktiviere FPS-Anzeige."""
        self._show_fps = enabled
        self._fps_frame_count = 0
        self._fps_last_time = time.monotonic()
        self._fps_value = 0.0
        self.update()

    def capture_crossfade_snapshot(self) -> None:
        """Capture aktuellen Render-State fuer Live-Crossfade.

        Speichert Polygon-Daten (media_id + Punkt-Kopien) statt statischem
        Screenshot, damit laufende Videos im Crossfade weiterlaufen.
        """
        if self.mode != "output":
            return

        self._crossfade_from_data = []
        for poly in self.all_polygons:
            if not poly.media_layer_id:
                continue
            media_layer = self.project.get_media_layer_by_id(poly.media_layer_id)
            if not media_layer or not media_layer.visible or not media_layer.media_id:
                continue
            image = self.all_images.get(media_layer.media_id)
            if image is not None:
                self._crossfade_from_data.append((
                    media_layer.media_id,
                    [p.copy() for p in poly.source_points],
                    [p.copy() for p in poly.output_points],
                ))

    def set_crossfade_alphas(self, from_alpha: float, to_alpha: float) -> None:
        """Setze Blend-Alphas fuer Crossfade."""
        self._crossfade_from_alpha = from_alpha
        self._crossfade_to_alpha = to_alpha
        if to_alpha >= 1.0 and from_alpha <= 0.0:
            self._crossfade_from_data = None
            self._crossfade_buffer = None

    def set_border_highlight(self, color: Optional[QColor], alpha: float = 1.0) -> None:
        """Setze Rahmenfarbe fuer Freeze/Blackout Indikator (None = kein Rahmen)."""
        if color is not None:
            color = QColor(color)
            color.setAlphaF(alpha)
        self._border_color = color
        self.update()

    def set_undo_stack(self, stack) -> None:
        self._undo_stack = stack

    def set_refresh_callback(self, cb) -> None:
        self._refresh_cb = cb

    def set_selected_polygons(self, polygons: List[Polygon]) -> None:
        self.selected_polygons = polygons
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
            return QCursor(Qt.CursorShape.CrossCursor)
        elif handle_type == HandleType.POINT:
            # Gesperrtes Polygon: ForbiddenCursor fuer Eckpunkte (ohne Shift)
            if (self.current_polygon and self.current_polygon.locked
                    and not self.maintain_aspect_ratio):
                return QCursor(Qt.CursorShape.ForbiddenCursor)
            return QCursor(Qt.CursorShape.CrossCursor)
        elif handle_type == HandleType.CORNER:
            if corner in [0, 2]:
                return QCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
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
            result.append([new_x, new_y])
        return result

    def _get_other_snap_data(self) -> Tuple[List[Tuple[float, float]], List[Tuple[Tuple[float, float], Tuple[float, float]]]]:
        """Hole Ecken und Kanten aller anderen Polygone fuer Snapping.

        Returns:
            (corners, edges) wobei edges eine Liste von (p1, p2) Tupeln ist.
        """
        corners = []
        edges = []

        for poly in self.all_polygons:
            if poly == self.current_polygon:
                continue
            points = poly.source_points if self.mode == "source" else poly.output_points
            for i, (px, py) in enumerate(points):
                corners.append((px, py))
                # Kante von diesem Punkt zum naechsten
                nx_p, ny_p = points[(i + 1) % len(points)]
                edges.append(((px, py), (nx_p, ny_p)))

        return corners, edges

    @staticmethod
    def _point_to_edge_snap(px: float, py: float,
                            e1: Tuple[float, float], e2: Tuple[float, float]) -> Tuple[float, float, float]:
        """Berechne naechsten Punkt auf einer Kante und Distanz.

        Returns: (snap_x, snap_y, distance)
        """
        ax, ay = e1
        bx, by = e2
        abx, aby = bx - ax, by - ay
        ab_len_sq = abx * abx + aby * aby
        if ab_len_sq < 1e-12:
            return ax, ay, ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5

        t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab_len_sq))
        snap_x = ax + t * abx
        snap_y = ay + t * aby
        dist = ((px - snap_x) ** 2 + (py - snap_y) ** 2) ** 0.5
        return snap_x, snap_y, dist

    def _apply_snapping(self, nx: float, ny: float) -> Tuple[float, float]:
        """Wende Punkt-Snapping an (Ecke-zu-Ecke, dann Ecke-zu-Kante)."""
        if not self.snapping_enabled:
            return nx, ny

        corners, edges = self._get_other_snap_data()
        best_dist = float('inf')
        snapped_x, snapped_y = nx, ny
        is_corner_snap = False

        # Ecke-zu-Ecke (Prioritaet)
        for sx, sy in corners:
            dist = ((nx - sx) ** 2 + (ny - sy) ** 2) ** 0.5
            if dist < self.snap_distance and dist < best_dist:
                best_dist = dist
                snapped_x, snapped_y = sx, sy
                is_corner_snap = True

        # Ecke-zu-Kante (Fallback)
        if not is_corner_snap:
            for e1, e2 in edges:
                sx, sy, dist = self._point_to_edge_snap(nx, ny, e1, e2)
                if dist < self.snap_distance and dist < best_dist:
                    best_dist = dist
                    snapped_x, snapped_y = sx, sy

        return snapped_x, snapped_y

    def _apply_shape_snapping(self, new_points: List[List[float]]) -> List[List[float]]:
        """Wende Snapping fuer ein ganzes Polygon an.

        Prueft alle Ecken des verschobenen Polygons gegen Ecken und Kanten
        anderer Polygone. Ecke-zu-Ecke hat Prioritaet vor Ecke-zu-Kante.
        """
        if not self.snapping_enabled:
            return new_points

        corners, edges = self._get_other_snap_data()
        if not corners and not edges:
            return new_points

        best_dx, best_dy = 0.0, 0.0
        best_dist = float('inf')
        best_is_corner = False

        for px, py in new_points:
            # Ecke-zu-Ecke
            for sx, sy in corners:
                dist = ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
                if dist < self.snap_distance:
                    # Ecke-zu-Ecke hat Prioritaet
                    if not best_is_corner or dist < best_dist:
                        best_dist = dist
                        best_dx = sx - px
                        best_dy = sy - py
                        best_is_corner = True

            # Ecke-zu-Kante (nur wenn kein Ecke-zu-Ecke gefunden)
            if not best_is_corner:
                for e1, e2 in edges:
                    snap_x, snap_y, dist = self._point_to_edge_snap(px, py, e1, e2)
                    if dist < self.snap_distance and dist < best_dist:
                        best_dist = dist
                        best_dx = snap_x - px
                        best_dy = snap_y - py

        if best_dist < self.snap_distance:
            return [[p[0] + best_dx, p[1] + best_dy] for p in new_points]

        return new_points

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

        # Farbiger Rahmen (Freeze/Blackout Indikator)
        if self._border_color is not None:
            border_pen = QPen(self._border_color, 4)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(cx + 2, cy + 2, cw - 4, ch - 4)

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
            poly_is_locked = self.current_polygon.locked if hasattr(self.current_polygon, 'locked') else False
            if self.active_handle == HandleType.ROTATE or self.hovered_handle == HandleType.ROTATE:
                hints.append("Rotate")
            elif self.active_handle == HandleType.CENTER or self.hovered_handle == HandleType.CENTER:
                hints.append("Move")
            elif self.active_handle == HandleType.POINT or self.hovered_handle == HandleType.POINT:
                if poly_is_locked:
                    if self.maintain_aspect_ratio:
                        hints.append("Scale (uniform)")
                    else:
                        hints.append("Locked | Shift: Scale")
                elif self.maintain_aspect_ratio:
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
                             "No polygon selected")

    def _draw_output_view(self, painter: QPainter) -> None:
        """Zeichne Output-Ansicht als Live-Preview."""
        cx, cy, cw, ch = self._calc_canvas_rect()

        # Composite aller Polygone rendern
        self._draw_composite_preview(painter)

        # Dann Edit-Overlay fuer alle Polygone
        self._draw_all_polygons(painter)

        # FPS Overlay (nur im Output-Canvas)
        if self._show_fps:
            self._draw_fps_overlay(painter)

        # Kein Polygon-Hinweis
        if not self.all_polygons:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No polygon selected")

    def _draw_fps_overlay(self, painter: QPainter) -> None:
        """Zeichne FPS-Overlay oben rechts im Canvas-Bereich."""
        self._fps_frame_count += 1
        now = time.monotonic()
        elapsed = now - self._fps_last_time
        if elapsed >= 1.0:
            self._fps_value = self._fps_frame_count / elapsed
            self._fps_frame_count = 0
            self._fps_last_time = now

        cx, cy, cw, ch = self._calc_canvas_rect()
        text = f"FPS: {self._fps_value:.0f}"
        font = QFont("Monospace", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text) + 10
        th = fm.height() + 6

        x = cx + cw - tw - 6
        y = cy + 6
        painter.setClipping(False)
        painter.fillRect(x, y, tw, th, QColor(0, 0, 0, 160))
        painter.setPen(QColor(0, 255, 80))
        painter.drawText(x + 5, y + fm.ascent() + 3, text)

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

            # Crossfade: "from" State live re-rendern mit aktuellen Video-Frames
            if self._crossfade_from_data is not None:
                if self._crossfade_buffer_size != (render_w, render_h):
                    self._crossfade_buffer = np.zeros((render_h, render_w, 3), dtype=np.uint8)
                    self._crossfade_buffer_size = (render_w, render_h)

                from_polygons = []
                for media_id, src_pts, out_pts in self._crossfade_from_data:
                    image = self.all_images.get(media_id)
                    if image is not None:
                        from_polygons.append((image, src_pts, out_pts))

                if from_polygons:
                    from_composite = composite_polygons_fast(
                        from_polygons, (render_w, render_h), self._crossfade_buffer)
                else:
                    self._crossfade_buffer[:] = 0
                    from_composite = self._crossfade_buffer

                composite = cv2.addWeighted(
                    from_composite, self._crossfade_from_alpha,
                    composite, self._crossfade_to_alpha, 0)

            qimg = numpy_to_qimage(composite)
            if qimg:
                img_x = cx + int(-self.pan_offset[0] * cw) + int((cw - render_w) / 2)
                img_y = cy + int(-self.pan_offset[1] * ch) + int((ch - render_h) / 2)
                painter.drawImage(img_x, img_y, qimg)
        elif self._crossfade_from_data is not None:
            # Kein neuer Content, aber From-Data vorhanden -> From-State ausblenden
            if self._crossfade_buffer_size != (render_w, render_h):
                self._crossfade_buffer = np.zeros((render_h, render_w, 3), dtype=np.uint8)
                self._crossfade_buffer_size = (render_w, render_h)

            from_polygons = []
            for media_id, src_pts, out_pts in self._crossfade_from_data:
                image = self.all_images.get(media_id)
                if image is not None:
                    from_polygons.append((image, src_pts, out_pts))

            if from_polygons:
                from_composite = composite_polygons_fast(
                    from_polygons, (render_w, render_h), self._crossfade_buffer)
                faded = cv2.multiply(from_composite, np.array([self._crossfade_from_alpha]))
                faded = np.clip(faded, 0, 255).astype(np.uint8)
                qimg = numpy_to_qimage(faded)
                if qimg:
                    img_x = cx + int(-self.pan_offset[0] * cw) + int((cw - render_w) / 2)
                    img_y = cy + int(-self.pan_offset[1] * ch) + int((ch - render_h) / 2)
                    painter.drawImage(img_x, img_y, qimg)

    def _draw_all_polygons(self, painter: QPainter) -> None:
        """Zeichne alle Polygone in drei Stufen."""
        selected_set = set(id(p) for p in self.selected_polygons)

        # 1. Nicht-selektiert, nicht-aktuell -> grau
        for poly in self.all_polygons:
            if poly == self.current_polygon:
                continue
            if id(poly) in selected_set:
                continue
            self._draw_polygon(painter, poly, is_current=False, is_selected=False)

        # 2. Selektiert aber nicht primary -> orange
        for poly in self.selected_polygons:
            if poly == self.current_polygon:
                continue
            if poly in self.all_polygons:
                self._draw_polygon(painter, poly, is_current=False, is_selected=True)

        # 3. Primary (current_polygon) -> blau mit Handles
        if self.current_polygon:
            self._draw_polygon(painter, self.current_polygon, is_current=True, is_selected=True)

    def _draw_polygon(self, painter: QPainter, polygon: Polygon,
                      is_current: bool, is_selected: bool = False) -> None:
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
        elif is_selected:
            painter.setBrush(QBrush(QColor(255, 180, 0, 40)))
        else:
            painter.setBrush(QBrush(QColor(100, 100, 100, 25)))
        painter.setPen(Qt.PenStyle.NoPen)
        qpoly = QPolygon([QPoint(p[0], p[1]) for p in pixel_points])
        painter.drawPolygon(qpoly)

        # Kanten
        if is_current:
            painter.setPen(QPen(QColor(0, 200, 255), 2))
        elif is_selected:
            painter.setPen(QPen(QColor(255, 180, 0), 2))
        else:
            painter.setPen(QPen(QColor(150, 150, 150), 1))

        for i in range(len(pixel_points)):
            p1 = pixel_points[i]
            p2 = pixel_points[(i + 1) % len(pixel_points)]
            painter.drawLine(p1[0], p1[1], p2[0], p2[1])

        # Punkte und Handles
        poly_locked = polygon.locked if hasattr(polygon, 'locked') else False

        if is_current:
            # Eck-Punkte mit Nummern
            for i, (px, py) in enumerate(pixel_points):
                is_hovered = (self.hovered_handle == HandleType.POINT and self.hovered_corner == i)
                is_selected_pt = (i == self.selected_point)
                is_active = (self.active_handle == HandleType.POINT and self.active_corner == i)

                if poly_locked:
                    # Gesperrte Punkte: grau
                    painter.setBrush(QBrush(QColor(120, 120, 120)))
                    painter.setPen(QPen(QColor(180, 180, 180), 2))
                    radius = self.point_radius
                elif is_selected_pt or is_active:
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

            # Lock-Icon neben Center Handle
            if poly_locked:
                lock_font = QFont("sans-serif", 12)
                painter.setFont(lock_font)
                painter.setPen(QColor(255, 200, 80))
                painter.drawText(cx + self.handle_radius + 4, cy + 5, "\U0001f512")

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
            if is_selected:
                dot_brush = QBrush(QColor(255, 180, 0))
                dot_pen = QPen(QColor(255, 220, 100), 1)
            else:
                dot_brush = QBrush(QColor(150, 150, 150))
                dot_pen = QPen(QColor(200, 200, 200), 1)
            for px, py in pixel_points:
                painter.setBrush(dot_brush)
                painter.setPen(dot_pen)
                painter.drawEllipse(QPoint(px, py), 5, 5)

            # Name in der Mitte
            if pixel_points:
                center_x = sum(p[0] for p in pixel_points) // len(pixel_points)
                center_y = sum(p[1] for p in pixel_points) // len(pixel_points)
                if is_selected:
                    painter.setPen(QColor(255, 200, 80))
                else:
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

            # Modifier pruefen
            shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.maintain_aspect_ratio = False  # Wird unten ggf. gesetzt

            # Bei Shift: Pruefen ob anderes Polygon angeklickt (Multi-Select)
            if shift_held:
                poly = self._find_polygon_at(x, y)
                if poly is not None and poly != self.current_polygon:
                    self.polygon_selected.emit(poly, int(event.modifiers().value))
                    self.active_handle = HandleType.NONE
                    self.active_corner = -1
                    self.selected_point = None
                    self.dragging = False
                    self.dragging_shape = False
                    self.update()
                    return
                # Shift auf aktuellem Polygon -> Aspect Ratio Lock fuer Drag
                self.maintain_aspect_ratio = True

            # Handle finden
            handle_type, corner = self._find_handle_at(x, y)

            # Lock-Enforcement: Bei gesperrtem Polygon POINT ohne Shift -> CENTER
            if (handle_type == HandleType.POINT
                    and self.current_polygon
                    and self.current_polygon.locked
                    and not shift_held):
                handle_type = HandleType.CENTER
                corner = -1

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

                # Multi-Drag Snapshot
                if len(self.selected_polygons) > 1 and handle_type in (HandleType.CENTER, HandleType.ROTATE, HandleType.POINT):
                    self._multi_drag_start = {}
                    for poly in self.selected_polygons:
                        pts = poly.source_points if self.mode == "source" else poly.output_points
                        self._multi_drag_start[poly.id] = [p.copy() for p in pts]

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
                if poly is not None:
                    # Polygon auswaehlen - Signal senden
                    self.polygon_selected.emit(poly, int(event.modifiers().value))
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
                    # Shift gedrueckt: Uniform scaling
                    alt_held = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
                    orig_corner = self.drag_start_points[self.active_corner]

                    if self._multi_drag_start and len(self.selected_polygons) > 1 and not alt_held:
                        # Multi-Select: Alle Polygone um gemeinsamen Mittelpunkt skalieren
                        all_start_pts = []
                        for pts in self._multi_drag_start.values():
                            all_start_pts.extend(pts)
                        shared_cx = sum(p[0] for p in all_start_pts) / len(all_start_pts)
                        shared_cy = sum(p[1] for p in all_start_pts) / len(all_start_pts)

                        orig_dist = math.sqrt((orig_corner[0] - shared_cx) ** 2 + (orig_corner[1] - shared_cy) ** 2)
                        if orig_dist > 0.001:
                            new_dist = math.sqrt((nx - shared_cx) ** 2 + (ny - shared_cy) ** 2)
                            scale = new_dist / orig_dist

                            for poly in self.selected_polygons:
                                start_pts = self._multi_drag_start.get(poly.id)
                                if not start_pts:
                                    continue
                                scaled = self._scale_points(start_pts, (shared_cx, shared_cy), scale, scale)
                                if self.mode == "source":
                                    poly.source_points = scaled
                                else:
                                    poly.output_points = scaled
                    else:
                        # Einzelnes Polygon oder Alt: Jedes Polygon um eigenen Mittelpunkt
                        cx, cy = self.drag_start_center
                        orig_dist = math.sqrt((orig_corner[0] - cx) ** 2 + (orig_corner[1] - cy) ** 2)
                        if orig_dist > 0.001:
                            new_dist = math.sqrt((nx - cx) ** 2 + (ny - cy) ** 2)
                            scale = new_dist / orig_dist

                            new_points = self._scale_points(self.drag_start_points, (cx, cy), scale, scale)
                            if self.mode == "source":
                                self.current_polygon.source_points = new_points
                            else:
                                self.current_polygon.output_points = new_points

                            # Alt + Multi-Select: Andere Polygone um ihren eigenen Mittelpunkt
                            if self._multi_drag_start and alt_held:
                                for poly in self.selected_polygons:
                                    if poly == self.current_polygon:
                                        continue
                                    start_pts = self._multi_drag_start.get(poly.id)
                                    if not start_pts:
                                        continue
                                    poly_center = self._get_polygon_center(start_pts)
                                    scaled = self._scale_points(start_pts, poly_center, scale, scale)
                                    if self.mode == "source":
                                        poly.source_points = scaled
                                    else:
                                        poly.output_points = scaled
                else:
                    # Einzelnen Punkt verschieben
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

                new_points = [[px + dx, py + dy] for px, py in self.drag_start_points]

                # Shape-Snapping anwenden
                new_points = self._apply_shape_snapping(new_points)

                # Berechne effektiven Delta nach Snapping
                eff_dx = new_points[0][0] - self.drag_start_points[0][0]
                eff_dy = new_points[0][1] - self.drag_start_points[0][1]

                if self.mode == "source":
                    self.current_polygon.source_points = new_points
                else:
                    self.current_polygon.output_points = new_points

                # Multi-Polygon verschieben
                if self._multi_drag_start:
                    for poly in self.selected_polygons:
                        if poly == self.current_polygon:
                            continue
                        start_pts = self._multi_drag_start.get(poly.id)
                        if not start_pts:
                            continue
                        moved = [[p[0] + eff_dx, p[1] + eff_dy] for p in start_pts]
                        if self.mode == "source":
                            poly.source_points = moved
                        else:
                            poly.output_points = moved

            elif self.active_handle == HandleType.ROTATE:
                # Rotation um Zentrum
                if self._multi_drag_start and len(self.selected_polygons) > 1:
                    # Shared Center = Durchschnitt aller Start-Punkte
                    all_pts = []
                    for pts in self._multi_drag_start.values():
                        all_pts.extend(pts)
                    shared_cx = sum(p[0] for p in all_pts) / len(all_pts)
                    shared_cy = sum(p[1] for p in all_pts) / len(all_pts)

                    current_angle = math.atan2(ny - shared_cy, nx - shared_cx)
                    # Recalculate start angle relative to shared center
                    start_nx, start_ny = self.drag_start
                    start_angle = math.atan2(start_ny - shared_cy, start_nx - shared_cx)
                    delta_angle = current_angle - start_angle

                    for poly in self.selected_polygons:
                        start_pts = self._multi_drag_start.get(poly.id)
                        if not start_pts:
                            continue
                        new_pts = []
                        for px, py in start_pts:
                            rx, ry = self._rotate_point(px, py, shared_cx, shared_cy, delta_angle)
                            new_pts.append([rx, ry])
                        if self.mode == "source":
                            poly.source_points = new_pts
                        else:
                            poly.output_points = new_pts
                else:
                    cx, cy = self.drag_start_center
                    current_angle = math.atan2(ny - cy, nx - cx)
                    delta_angle = current_angle - self.drag_start_angle

                    new_points = []
                    for px, py in self.drag_start_points:
                        new_x, new_y = self._rotate_point(px, py, cx, cy, delta_angle)
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
            # Undo-Command pushen wenn Punkte sich geaendert haben
            if self.drag_start_points and self.current_polygon and self._undo_stack:
                current_pts = self.get_points()
                changed = (self.drag_start_points != current_pts)
                if changed:
                    from .undo_commands import PointsMoveCommand, MultiPointsMoveCommand

                    if self._multi_drag_start and len(self.selected_polygons) > 1:
                        # Multi-Select: Eintraege fuer jedes veraenderte Polygon
                        entries = []
                        for poly in self.selected_polygons:
                            old_pts = self._multi_drag_start.get(poly.id)
                            if not old_pts:
                                continue
                            cur = poly.source_points if self.mode == "source" else poly.output_points
                            if old_pts != cur:
                                entries.append((poly, self.mode,
                                                [p.copy() for p in old_pts],
                                                [p.copy() for p in cur]))
                        if entries:
                            cmd = MultiPointsMoveCommand(entries, self._refresh_cb or (lambda: None),
                                                         "Move polygons")
                            self._undo_stack.push(cmd)
                    else:
                        # Single-Select
                        cmd = PointsMoveCommand(
                            self.current_polygon, self.mode,
                            [p.copy() for p in self.drag_start_points],
                            [p.copy() for p in current_pts],
                            self._refresh_cb or (lambda: None),
                            "Move points")
                        self._undo_stack.push(cmd)

            self.dragging = False
            self.dragging_shape = False
            self.drag_start = None
            self.active_handle = HandleType.NONE
            self.active_corner = -1
            self.drag_start_points = None
            self.drag_start_center = None
            self.drag_start_angle = 0.0
            self._multi_drag_start = None

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
        """Pfeiltasten: Punkt oder ganzes Polygon verschieben. Shift = fein."""
        if not self.current_polygon:
            event.ignore()
            return

        key = event.key()
        if key not in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            event.ignore()
            return

        # Shift = fein, normal = grob
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            step = 0.001
        else:
            step = 0.005

        dx, dy = 0.0, 0.0
        if key == Qt.Key.Key_Left:
            dx = -step
        elif key == Qt.Key.Key_Right:
            dx = step
        elif key == Qt.Key.Key_Up:
            dy = -step
        elif key == Qt.Key.Key_Down:
            dy = step

        points = self.get_points()
        if not points:
            event.ignore()
            return

        # Snapshot vor Aenderung
        old_points = [p.copy() for p in points]

        if (self.selected_point is not None and self.selected_point < len(points)
                and not self.current_polygon.locked):
            # Einzelnen Punkt verschieben (nur wenn nicht gesperrt)
            px, py = points[self.selected_point]
            points[self.selected_point] = [px + dx, py + dy]
        elif len(self.selected_polygons) > 1:
            # Multi-Select: Alle selektierten Polygone verschieben
            from .undo_commands import MultiPointsMoveCommand
            entries = []
            for poly in self.selected_polygons:
                pts = poly.source_points if self.mode == "source" else poly.output_points
                old_pts = [p.copy() for p in pts]
                new_pts = [[p[0] + dx, p[1] + dy] for p in pts]
                if self.mode == "source":
                    poly.source_points = new_pts
                else:
                    poly.output_points = new_pts
                entries.append((poly, self.mode, old_pts, [p.copy() for p in new_pts]))
            if entries and self._undo_stack:
                cmd = MultiPointsMoveCommand(entries, self._refresh_cb or (lambda: None), "Arrow move polygons")
                self._undo_stack.push(cmd)
            self.update()
            self.points_changed.emit()
            return
        else:
            # Ganzes Polygon verschieben
            new_points = [[p[0] + dx, p[1] + dy] for p in points]
            if self.mode == "source":
                self.current_polygon.source_points = new_points
            else:
                self.current_polygon.output_points = new_points

        # Undo-Command pushen (single polygon)
        if self._undo_stack:
            from .undo_commands import PointsMoveCommand
            new_pts = self.get_points()
            if old_points != new_pts:
                cmd = PointsMoveCommand(
                    self.current_polygon, self.mode,
                    old_points, [p.copy() for p in new_pts],
                    self._refresh_cb or (lambda: None), "Arrow move")
                self._undo_stack.push(cmd)

        self.update()
        self.points_changed.emit()

    def resizeEvent(self, event) -> None:
        """Positioniere Overlay-Buttons unten rechts."""
        super().resizeEvent(event)
        margin = 6
        gap = 4
        btn_y = self.height() - self._fit_btn.height() - margin
        # Fit-Button ganz rechts
        self._fit_btn.move(
            self.width() - self._fit_btn.width() - margin,
            btn_y
        )
        # Reset-Button links daneben
        self._reset_btn.move(
            self.width() - self._fit_btn.width() - margin - gap - self._reset_btn.width(),
            btn_y
        )

    def contextMenuEvent(self, event) -> None:
        """Rechtsklick-Kontextmenue fuer Polygone (nur Source-Canvas)."""
        if self.mode != "source":
            return

        x, y = int(event.pos().x()), int(event.pos().y())
        poly = self._find_polygon_at(x, y)
        if poly is None:
            return

        # Falls nicht aktuelles Polygon -> zuerst selektieren
        if poly != self.current_polygon:
            self.polygon_selected.emit(poly, 0)

        menu = QMenu(self)

        # Lock / Unlock Toggle
        if poly.locked:
            lock_action = menu.addAction("Unlock")
        else:
            lock_action = menu.addAction("Lock")

        menu.addSeparator()

        # Edit Shape
        edit_shape_action = menu.addAction("Edit Shape...")

        action = menu.exec(event.globalPos())
        if action is None:
            return

        if action == lock_action:
            self._toggle_lock(poly)
        elif action == edit_shape_action:
            self._open_shape_dialog(poly)

    def _toggle_lock(self, polygon: Polygon) -> None:
        """Lock/Unlock Toggle mit Undo."""
        old_val = polygon.locked
        new_val = not old_val

        if self._undo_stack:
            from .undo_commands import PolygonPropertyCommand
            cmd = PolygonPropertyCommand(
                polygon, 'locked', old_val, new_val,
                self._refresh_cb or (lambda: None),
                "Lock polygon" if new_val else "Unlock polygon")
            self._undo_stack.push(cmd)
        else:
            polygon.locked = new_val

        self.update()

    def _open_shape_dialog(self, polygon: Polygon) -> None:
        """Oeffne den Edit Shape Dialog."""
        from .shape_dialog import ShapeDialog

        dlg = ShapeDialog(polygon, self)
        if dlg.exec() != ShapeDialog.DialogCode.Accepted:
            return

        new_points, constraints, auto_lock = dlg.get_result()
        if new_points is None:
            return

        old_points = [p.copy() for p in polygon.source_points]
        old_constraints = polygon.shape_constraints
        old_locked = polygon.locked

        if self._undo_stack:
            from .undo_commands import PointsMoveCommand, PolygonPropertyCommand
            self._undo_stack.beginMacro("Edit Shape")

            # Punkte aendern
            cmd_pts = PointsMoveCommand(
                polygon, "source", old_points, [p.copy() for p in new_points],
                self._refresh_cb or (lambda: None), "Shape points")
            self._undo_stack.push(cmd_pts)

            # Constraints speichern
            cmd_constraints = PolygonPropertyCommand(
                polygon, 'shape_constraints', old_constraints, constraints,
                self._refresh_cb or (lambda: None), "Shape constraints")
            self._undo_stack.push(cmd_constraints)

            # Auto-Lock
            if auto_lock and not old_locked:
                cmd_lock = PolygonPropertyCommand(
                    polygon, 'locked', False, True,
                    self._refresh_cb or (lambda: None), "Auto-lock")
                self._undo_stack.push(cmd_lock)

            self._undo_stack.endMacro()
        else:
            polygon.source_points = new_points
            polygon.shape_constraints = constraints
            if auto_lock:
                polygon.locked = True

        self.update()
        self.points_changed.emit()
