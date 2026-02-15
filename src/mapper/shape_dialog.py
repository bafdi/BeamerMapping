"""Edit Shape Dialog - Polygon-Form ueber Seitenlaengen, Winkel und Orientierung definieren."""

import math
from typing import Optional, List, Dict, Any, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QComboBox, QPushButton, QCheckBox,
    QDialogButtonBox
)

from .models import Polygon


def _compute_side_lengths(points: List[List[float]]) -> List[float]:
    """Berechne euklidische Seitenlaengen (normalisiert)."""
    n = len(points)
    lengths = []
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        lengths.append(math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))
    return lengths


def _compute_angles(points: List[List[float]]) -> List[float]:
    """Berechne Innenwinkel in Grad.

    Erkennt automatisch die Windungsrichtung (CW/CCW) und berechnet
    korrekte Innenwinkel unabhaengig davon.
    """
    n = len(points)
    # Windungsrichtung bestimmen (Shoelace-Formel)
    # Shoelace: positiv = CCW (math-standard), negativ = CW
    signed_area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        signed_area += x1 * y2 - x2 * y1
    clockwise = signed_area < 0

    angles = []
    for i in range(n):
        p_prev = points[(i - 1) % n]
        p_curr = points[i]
        p_next = points[(i + 1) % n]

        dx1 = p_prev[0] - p_curr[0]
        dy1 = p_prev[1] - p_curr[1]
        dx2 = p_next[0] - p_curr[0]
        dy2 = p_next[1] - p_curr[1]

        # Kreuzprodukt und Skalarprodukt
        cross = dx1 * dy2 - dy1 * dx2
        dot = dx1 * dx2 + dy1 * dy2
        len1 = math.sqrt(dx1 ** 2 + dy1 ** 2)
        len2 = math.sqrt(dx2 ** 2 + dy2 ** 2)

        if len1 < 1e-10 or len2 < 1e-10:
            angles.append(180.0)
            continue

        cos_angle = max(-1.0, min(1.0, dot / (len1 * len2)))
        angle = math.acos(cos_angle)

        # Kreuzprodukt von (prev-curr) x (next-curr):
        # Bei CCW-Polygon: cross < 0 = konvex (< 180), cross > 0 = reflex (> 180)
        # Bei CW-Polygon: cross > 0 = konvex (< 180), cross < 0 = reflex (> 180)
        if clockwise:
            if cross < 0:
                angle = 2 * math.pi - angle
        else:
            if cross > 0:
                angle = 2 * math.pi - angle

        angles.append(round(math.degrees(angle), 2))
    return angles


def construct_polygon(sides: List[float], angles: List[float]) -> Tuple[Optional[List[List[float]]], float]:
    """Konstruiere Polygon aus Seitenlaengen und Winkeln.

    Returns: (vertices, closure_error)
        vertices: Liste von [x, y] Koordinaten oder None bei Fehler
        closure_error: Abstand zwischen letztem berechneten Punkt und Ursprung
    """
    n = len(sides)
    if n != len(angles):
        return None, float('inf')

    vertices = [[0.0, 0.0]]
    direction = 0.0  # Kante 0 in +X Richtung

    for i in range(n - 1):
        x = vertices[-1][0] + math.cos(direction) * sides[i]
        y = vertices[-1][1] + math.sin(direction) * sides[i]
        vertices.append([x, y])

        # Aussenwinkel = pi - Innenwinkel
        exterior = math.pi - math.radians(angles[(i + 1) % n])
        direction += exterior

    # Closure-Check
    expected_x = vertices[-1][0] + math.cos(direction) * sides[-1]
    expected_y = vertices[-1][1] + math.sin(direction) * sides[-1]
    closure_error = math.sqrt(expected_x ** 2 + expected_y ** 2)

    perimeter = sum(sides)
    if perimeter > 0:
        closure_error_rel = closure_error / perimeter
    else:
        closure_error_rel = float('inf')

    return vertices, closure_error_rel


def fit_polygon_to_original(
    new_verts: List[List[float]],
    orig_points: List[List[float]],
    orientations: List[Optional[str]],
    new_sides: List[float]
) -> List[List[float]]:
    """Passe konstruiertes Polygon an Original an (Skalierung, Rotation, Translation).

    Args:
        new_verts: Konstruierte Vertices (relativ, ab Ursprung)
        orig_points: Originale normalisierte Polygon-Punkte
        orientations: Kanten-Orientierungen (None, "horizontal", "vertikal")
        new_sides: Seitenlaengen des neuen Polygons
    """
    # Skalierung: Gleicher Umfang wie Original
    orig_sides = _compute_side_lengths(orig_points)
    orig_perimeter = sum(orig_sides)
    new_perimeter = sum(new_sides)

    if new_perimeter > 0:
        scale = orig_perimeter / new_perimeter
    else:
        scale = 1.0

    # Skalieren
    scaled = [[v[0] * scale, v[1] * scale] for v in new_verts]

    # Rotation bestimmen
    rotation = None

    # Orientierungs-Constraints pruefen
    for i, orient in enumerate(orientations):
        if orient is None:
            continue

        # Kanten-Richtung im konstruierten Polygon
        p1 = scaled[i]
        p2 = scaled[(i + 1) % len(scaled)]
        edge_angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])

        if orient == "horizontal":
            # Kante soll horizontal sein -> Rotation so dass edge_angle = 0 oder pi
            # Waehle naechsten Wert
            target = 0.0
            if abs(edge_angle - math.pi) < abs(edge_angle):
                target = math.pi
            if abs(edge_angle + math.pi) < abs(edge_angle - target):
                target = -math.pi
            rotation = -edge_angle + target
        elif orient == "vertikal":
            # Kante soll vertikal sein -> edge_angle = pi/2 oder -pi/2
            target = math.pi / 2
            if abs(edge_angle + math.pi / 2) < abs(edge_angle - math.pi / 2):
                target = -math.pi / 2
            rotation = -edge_angle + target
        break  # Nur erste Orientierung verwenden

    if rotation is None:
        # Keine Orientierung -> Rotation des Originals uebernehmen
        # Kante-0-Winkel matchen
        orig_p0 = orig_points[0]
        orig_p1 = orig_points[1]
        orig_edge_angle = math.atan2(orig_p1[1] - orig_p0[1], orig_p1[0] - orig_p0[0])

        new_p0 = scaled[0]
        new_p1 = scaled[1]
        new_edge_angle = math.atan2(new_p1[1] - new_p0[1], new_p1[0] - new_p0[0])

        rotation = orig_edge_angle - new_edge_angle

    # Rotieren um Schwerpunkt des neuen Polygons
    ncx = sum(v[0] for v in scaled) / len(scaled)
    ncy = sum(v[1] for v in scaled) / len(scaled)

    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    rotated = []
    for v in scaled:
        dx = v[0] - ncx
        dy = v[1] - ncy
        rx = ncx + dx * cos_r - dy * sin_r
        ry = ncy + dx * sin_r + dy * cos_r
        rotated.append([rx, ry])

    # Translation: Neues Zentrum = Original-Zentrum
    orig_cx = sum(p[0] for p in orig_points) / len(orig_points)
    orig_cy = sum(p[1] for p in orig_points) / len(orig_points)
    new_cx = sum(v[0] for v in rotated) / len(rotated)
    new_cy = sum(v[1] for v in rotated) / len(rotated)

    tx = orig_cx - new_cx
    ty = orig_cy - new_cy

    result = [[v[0] + tx, v[1] + ty] for v in rotated]
    return result


class ShapeDialog(QDialog):
    """Dialog zum Bearbeiten der Polygon-Form."""

    def __init__(self, polygon: Polygon, parent=None):
        super().__init__(parent)
        self.polygon = polygon
        self.setWindowTitle("Edit Shape")
        self.setMinimumWidth(420)

        self._side_spins: List[QDoubleSpinBox] = []
        self._angle_spins: List[QDoubleSpinBox] = []
        self._orient_combos: List[QComboBox] = []
        self._auto_lock_check: Optional[QCheckBox] = None
        self._status_label: Optional[QLabel] = None
        self._apply_btn: Optional[QPushButton] = None

        self._result_points: Optional[List[List[float]]] = None
        self._result_constraints: Optional[Dict[str, Any]] = None
        self._result_auto_lock: bool = False

        self._init_ui()
        self._load_values()
        self._validate()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Seiten
        sides_group = QGroupBox("Seiten (Verhaeltnisse)")
        sides_grid = QGridLayout()
        for i in range(4):
            label = QLabel(f"{i+1}\u2192{(i+1) % 4 + 1}:")
            spin = QDoubleSpinBox()
            spin.setRange(0.01, 100.0)
            spin.setSingleStep(0.1)
            spin.setDecimals(3)
            spin.valueChanged.connect(self._validate)
            self._side_spins.append(spin)
            row, col = divmod(i, 2)
            sides_grid.addWidget(label, row, col * 2)
            sides_grid.addWidget(spin, row, col * 2 + 1)
        sides_group.setLayout(sides_grid)
        layout.addWidget(sides_group)

        # Winkel
        angles_group = QGroupBox("Winkel (Grad)")
        angles_grid = QGridLayout()
        for i in range(4):
            label = QLabel(f"\u2220{i+1}:")
            spin = QDoubleSpinBox()
            spin.setRange(1.0, 359.0)
            spin.setSingleStep(0.5)
            spin.setDecimals(1)
            spin.valueChanged.connect(self._validate)
            self._angle_spins.append(spin)
            row, col = divmod(i, 2)
            angles_grid.addWidget(label, row, col * 2)
            angles_grid.addWidget(spin, row, col * 2 + 1)
        angles_group.setLayout(angles_grid)
        layout.addWidget(angles_group)

        # Orientierung
        orient_group = QGroupBox("Orientierung")
        orient_grid = QGridLayout()
        orient_options = ["\u2014", "Horizontal", "Vertikal"]
        for i in range(4):
            label = QLabel(f"Kante {i+1}:")
            combo = QComboBox()
            combo.addItems(orient_options)
            combo.currentIndexChanged.connect(self._validate)
            self._orient_combos.append(combo)
            row, col = divmod(i, 2)
            orient_grid.addWidget(label, row, col * 2)
            orient_grid.addWidget(combo, row, col * 2 + 1)
        orient_group.setLayout(orient_grid)
        layout.addWidget(orient_group)

        # Presets
        presets_layout = QHBoxLayout()
        rect_btn = QPushButton("Rechteck")
        rect_btn.clicked.connect(self._preset_rectangle)
        presets_layout.addWidget(rect_btn)
        square_btn = QPushButton("Quadrat")
        square_btn.clicked.connect(self._preset_square)
        presets_layout.addWidget(square_btn)
        presets_layout.addStretch()
        layout.addLayout(presets_layout)

        # Auto-Lock
        self._auto_lock_check = QCheckBox("Nach Anwenden sperren")
        layout.addWidget(self._auto_lock_check)

        # Status
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._apply_btn = QPushButton("Anwenden")
        self._apply_btn.clicked.connect(self._on_apply)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._apply_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _load_values(self) -> None:
        """Lade Werte aus shape_constraints oder berechne sie vom Polygon."""
        constraints = self.polygon.shape_constraints
        points = self.polygon.source_points

        if constraints:
            sides = constraints.get('side_lengths', _compute_side_lengths(points))
            angles = constraints.get('angles', _compute_angles(points))
            orientations = constraints.get('orientations', [None] * 4)
        else:
            sides = _compute_side_lengths(points)
            angles = _compute_angles(points)
            orientations = [None] * 4

        for i in range(4):
            self._side_spins[i].setValue(sides[i] if i < len(sides) else 1.0)
            self._angle_spins[i].setValue(angles[i] if i < len(angles) else 90.0)

            orient = orientations[i] if i < len(orientations) else None
            if orient == "horizontal":
                self._orient_combos[i].setCurrentIndex(1)
            elif orient == "vertikal":
                self._orient_combos[i].setCurrentIndex(2)
            else:
                self._orient_combos[i].setCurrentIndex(0)

        if self.polygon.locked:
            self._auto_lock_check.setChecked(True)

    def _get_sides(self) -> List[float]:
        return [s.value() for s in self._side_spins]

    def _get_angles(self) -> List[float]:
        return [s.value() for s in self._angle_spins]

    def _get_orientations(self) -> List[Optional[str]]:
        result = []
        for combo in self._orient_combos:
            idx = combo.currentIndex()
            if idx == 1:
                result.append("horizontal")
            elif idx == 2:
                result.append("vertikal")
            else:
                result.append(None)
        return result

    def _validate(self) -> None:
        """Live-Validierung bei jeder Wertaenderung."""
        sides = self._get_sides()
        angles = self._get_angles()
        orientations = self._get_orientations()

        errors = []

        # Winkelsumme pruefen
        angle_sum = sum(angles)
        if abs(angle_sum - 360.0) > 0.5:
            errors.append(f"Winkelsumme = {angle_sum:.1f}\u00b0 (muss 360\u00b0 sein)")

        # Orientierungs-Konflikte
        h_count = sum(1 for o in orientations if o == "horizontal")
        v_count = sum(1 for o in orientations if o == "vertikal")
        if h_count > 1:
            errors.append("Maximal eine horizontale Kante")
        if v_count > 1:
            errors.append("Maximal eine vertikale Kante")

        # Polygon konstruieren
        if not errors:
            verts, closure_err = construct_polygon(sides, angles)
            if verts is None:
                errors.append("Polygon kann nicht konstruiert werden")
            elif closure_err > 0.01:
                errors.append("Seitenlaengen und Winkel ergeben kein geschlossenes Polygon")

        if errors:
            self._status_label.setText("\u274c " + " | ".join(errors))
            self._status_label.setStyleSheet("color: #ff6666;")
            self._apply_btn.setEnabled(False)
        else:
            self._status_label.setText(f"\u2713 Gueltig (\u03a3\u2220 = {angle_sum:.1f}\u00b0)")
            self._status_label.setStyleSheet("color: #66ff66;")
            self._apply_btn.setEnabled(True)

    def _preset_rectangle(self) -> None:
        """Setze Rechteck-Werte: alle Winkel 90, Seitenpaare gleich."""
        # Behalte aktuelle Verhaeltnisse bei, mache nur Winkel 90
        s0 = self._side_spins[0].value()
        s1 = self._side_spins[1].value()
        for spin in self._angle_spins:
            spin.setValue(90.0)
        self._side_spins[0].setValue(s0)
        self._side_spins[1].setValue(s1)
        self._side_spins[2].setValue(s0)  # gegenueber = gleich
        self._side_spins[3].setValue(s1)

    def _preset_square(self) -> None:
        """Setze Quadrat-Werte: alle Winkel 90, alle Seiten gleich."""
        for spin in self._angle_spins:
            spin.setValue(90.0)
        avg = sum(s.value() for s in self._side_spins) / 4
        for spin in self._side_spins:
            spin.setValue(avg)

    def _on_apply(self) -> None:
        """Berechne neue Punkte und schliesse Dialog."""
        sides = self._get_sides()
        angles = self._get_angles()
        orientations = self._get_orientations()

        verts, _ = construct_polygon(sides, angles)
        if verts is None:
            return

        new_points = fit_polygon_to_original(
            verts, self.polygon.source_points, orientations, sides)

        self._result_points = new_points
        self._result_constraints = {
            'side_lengths': sides,
            'angles': angles,
            'orientations': orientations,
        }
        self._result_auto_lock = self._auto_lock_check.isChecked()
        self.accept()

    def get_result(self) -> Tuple[
        Optional[List[List[float]]],
        Optional[Dict[str, Any]],
        bool
    ]:
        """Hole Ergebnis nach accept().

        Returns: (new_points, constraints_dict, auto_lock)
        """
        return self._result_points, self._result_constraints, self._result_auto_lock
