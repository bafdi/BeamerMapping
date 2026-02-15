"""Hochoptimierte Bild-Transformation mit Mesh-Warping fuer Kanten-Kontinuitaet."""

from typing import List, Tuple, Optional, Dict
import cv2
import numpy as np

# Grid-Qualität: 8x8 ist der Sweetspot.
# Hoch genug, dass das Bild im Inneren nicht "knickt".
# Niedrig genug, dass die Performance flüssig bleibt (64 Zellen vs 400 früher).
GRID_ROWS = 8
GRID_COLS = 8

def _get_bilinear_grid(points: List[List[float]], steps_x: int, steps_y: int) -> np.ndarray:
    """Berechnet Gitter-Punkte mittels bilinearer Interpolation."""
    p0 = np.array(points[0])
    p1 = np.array(points[1])
    p2 = np.array(points[2])
    p3 = np.array(points[3])

    ug = np.linspace(0, 1, steps_x + 1)
    vg = np.linspace(0, 1, steps_y + 1)
    u, v = np.meshgrid(ug, vg)

    # Vektorisierte Berechnung des Gitters
    term1 = ((1 - u) * (1 - v))[..., np.newaxis] * p0
    term2 = (u * (1 - v))[..., np.newaxis] * p1
    term3 = (u * v)[..., np.newaxis] * p2
    term4 = ((1 - u) * v)[..., np.newaxis] * p3

    return term1 + term2 + term3 + term4

def warp_triangle_affine_roi(
    img: np.ndarray,
    src_tri: np.ndarray,
    dst_tri: np.ndarray,
    out_w: int,
    out_h: int,
    result_buffer: np.ndarray
) -> None:
    """Warpt ein kleines Dreieck (ROI-Optimiert)."""
    # Bounding Box berechnen
    min_x = int(np.floor(np.min(dst_tri[:, 0])))
    min_y = int(np.floor(np.min(dst_tri[:, 1])))
    max_x = int(np.ceil(np.max(dst_tri[:, 0])))
    max_y = int(np.ceil(np.max(dst_tri[:, 1])))

    # Clipping am Ausgabebild
    x = max(0, min_x)
    y = max(0, min_y)
    w = min(out_w, max_x) - x
    h = min(out_h, max_y) - y

    if w <= 0 or h <= 0:
        return

    # Koordinaten relativ zur ROI verschieben
    dst_tri_shifted = np.array([[p[0]-x, p[1]-y] for p in dst_tri], dtype=np.float32)

    # Affine Matrix berechnen (Linear! Das garantiert, dass Kanten passen)
    M = cv2.getAffineTransform(src_tri, dst_tri_shifted)

    # Nur den kleinen Ausschnitt warpen
    warped_roi = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    # Dreiecks-Maske erstellen
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst_tri_shifted.astype(np.int32), 255)

    # In den Result-Buffer kopieren
    roi_target = result_buffer[y:y+h, x:x+w]

    # Sicherheitscheck fuer Dimensionen
    h_c, w_c = min(warped_roi.shape[0], roi_target.shape[0]), min(warped_roi.shape[1], roi_target.shape[1])

    if h_c > 0 and w_c > 0:
        # Maskiertes Kopieren
        np.copyto(
            roi_target[:h_c, :w_c],
            warped_roi[:h_c, :w_c],
            where=mask[:h_c, :w_c, np.newaxis] > 0
        )

def warp_image(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """
    Führt das Mesh-Warping durch.
    Wir nutzen hier BEWUSST kein warpPerspective, damit die Kanten linear bleiben.
    """
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    out_w, out_h = output_size
    img_h, img_w = image.shape[:2]

    # Ergebnis-Buffer
    result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    try:
        # Gitter berechnen (8x8)
        src_grid = _get_bilinear_grid(source_points, GRID_COLS, GRID_ROWS)
        dst_grid = _get_bilinear_grid(output_points, GRID_COLS, GRID_ROWS)

        # Auf Bilddimensionen skalieren
        src_grid[..., 0] *= img_w
        src_grid[..., 1] *= img_h
        dst_grid[..., 0] *= out_w
        dst_grid[..., 1] *= out_h

        src_grid = src_grid.astype(np.float32)
        dst_grid = dst_grid.astype(np.float32)

        # Jede Zelle als 2 Dreiecke warpen
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                # Punkte holen
                s_p0, s_p1 = src_grid[r, c], src_grid[r, c+1]
                s_p2, s_p3 = src_grid[r+1, c+1], src_grid[r+1, c]

                d_p0, d_p1 = dst_grid[r, c], dst_grid[r, c+1]
                d_p2, d_p3 = dst_grid[r+1, c+1], dst_grid[r+1, c]

                # Dreieck 1 (Oben-Links)
                warp_triangle_affine_roi(
                    image,
                    np.array([s_p0, s_p1, s_p3]),
                    np.array([d_p0, d_p1, d_p3]),
                    out_w, out_h, result
                )

                # Dreieck 2 (Unten-Rechts)
                warp_triangle_affine_roi(
                    image,
                    np.array([s_p1, s_p2, s_p3]),
                    np.array([d_p1, d_p2, d_p3]),
                    out_w, out_h, result
                )

        return result

    except Exception as e:
        print(f"Mesh Warp Error: {e}")
        return None

def composite_polygons_fast(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int],
    result_buffer: Optional[np.ndarray] = None
) -> np.ndarray:
    """Rendering Loop."""
    out_w, out_h = output_size

    if result_buffer is not None and result_buffer.shape == (out_h, out_w, 3):
        result = result_buffer
        result.fill(0)
    else:
        result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    if not polygons_data:
        return result

    for image, source_points, output_points in polygons_data:
        if image is None: continue

        # Mesh Warp aufrufen
        warped = warp_image(image, source_points, output_points, output_size)

        if warped is None:
            continue

        # Overlay Blending (Nicht-schwarze Pixel kopieren)
        if warped.shape == result.shape:
             mask = np.any(warped > 0, axis=2)
             result[mask] = warped[mask]
        else:
             h_c, w_c = min(warped.shape[0], out_h), min(warped.shape[1], out_w)
             if h_c > 0 and w_c > 0:
                 mask = np.any(warped[:h_c, :w_c] > 0, axis=2)
                 result[:h_c, :w_c][mask] = warped[:h_c, :w_c][mask]

    return result

# --- Helper & Boilerplate ---

def composite_polygons(polygons_data, output_size):
    return composite_polygons_fast(polygons_data, output_size)

def numpy_to_qimage(image: np.ndarray) -> Optional['QImage']:
    from PyQt6.QtGui import QImage
    if image is None: return None
    try:
        h, w = image.shape[:2]
        if image.ndim == 3:
            if image.shape[2] == 3:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
            elif image.shape[2] == 4:
                rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
                return QImage(rgba.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
    except: pass
    return None

def load_image(filepath: str) -> Optional[np.ndarray]:
    try: return cv2.imread(filepath, cv2.IMREAD_COLOR)
    except: return None

def clear_homography_cache(): pass