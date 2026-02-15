"""Hochoptimierte Bild-Transformation mit Bilinearem Mesh-Warping (High-Res)."""

from typing import List, Tuple, Optional, Dict
from functools import lru_cache
import cv2
import numpy as np

# Grid-Qualität: 20x20 = 400 Zellen = 800 Dreiecke.
# Das macht die Verzerrung extrem weich ("Smooth") und minimiert Artefakte.
GRID_ROWS = 20
GRID_COLS = 20

def _get_bilinear_grid(points: List[List[float]], steps_x: int, steps_y: int) -> np.ndarray:
    """
    Berechnet Gitter-Punkte mittels bilinearer Interpolation.
    Das garantiert, dass die Außenkanten linear (gleichmäßig) unterteilt werden.
    """
    # Eckpunkte (TL, TR, BR, BL)
    p0 = np.array(points[0])
    p1 = np.array(points[1])
    p2 = np.array(points[2])
    p3 = np.array(points[3])

    # Gitter-Koordinaten (0..1)
    ug = np.linspace(0, 1, steps_x + 1)
    vg = np.linspace(0, 1, steps_y + 1)
    u, v = np.meshgrid(ug, vg)

    # Bilineare Formel (Vektorisiert)
    # P = (1-u)(1-v)P0 + u(1-v)P1 + uvP2 + (1-u)vP3
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
    """
    Warpt ein kleines Dreieck und blendet es in den Buffer.
    """
    # 1. Bounding Box (ROI) berechnen
    # Wir runden großzügig, um Lücken (Black Lines) zu vermeiden
    min_x = int(np.floor(np.min(dst_tri[:, 0])))
    min_y = int(np.floor(np.min(dst_tri[:, 1])))
    max_x = int(np.ceil(np.max(dst_tri[:, 0])))
    max_y = int(np.ceil(np.max(dst_tri[:, 1])))

    # Clipping
    x = max(0, min_x)
    y = max(0, min_y)
    w = min(out_w, max_x) - x
    h = min(out_h, max_y) - y

    if w <= 0 or h <= 0:
        return

    # 2. Koordinaten relativ zur ROI verschieben
    dst_tri_shifted = np.array([[p[0]-x, p[1]-y] for p in dst_tri], dtype=np.float32)

    # 3. Affine Matrix (Linear!)
    # Affine Transformationen erzeugen KEINE perspektivische Verzerrung innerhalb des Dreiecks.
    # Da das Dreieck winzig ist, wirkt das Gesamtbild glatt.
    M = cv2.getAffineTransform(src_tri, dst_tri_shifted)

    # 4. Warping (nur ROI)
    warped_roi = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    # 5. Maske (nur ROI)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst_tri_shifted.astype(np.int32), 255)

    # 6. Blenden
    roi_target = result_buffer[y:y+h, x:x+w]

    # Dimensions-Check
    h_src, w_src = warped_roi.shape[:2]
    h_dst, w_dst = roi_target.shape[:2]
    h_c, w_c = min(h_src, h_dst), min(w_src, w_dst)

    if h_c > 0 and w_c > 0:
        # Copy mit Maske - schnellste Methode
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
    Bilineares Mesh-Warping (20x20).
    Erzeugt ein sehr feines Gitter. Berechnet Punkte bilinear (lineare Kanten!).
    Warpt jedes Gitter-Segment als 2 affine Dreiecke.
    """
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    out_w, out_h = output_size
    img_h, img_w = image.shape[:2]

    result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    try:
        # 1. Gitter berechnen (Bilinear)
        src_grid = _get_bilinear_grid(source_points, GRID_COLS, GRID_ROWS)
        dst_grid = _get_bilinear_grid(output_points, GRID_COLS, GRID_ROWS)

        # Skalieren
        src_grid[..., 0] *= img_w
        src_grid[..., 1] *= img_h
        dst_grid[..., 0] *= out_w
        dst_grid[..., 1] *= out_h

        src_grid = src_grid.astype(np.float32)
        dst_grid = dst_grid.astype(np.float32)

        # 2. Über alle Zellen iterieren
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                # Punkte der Zelle holen (TL, TR, BR, BL)
                s_p0 = src_grid[r, c]
                s_p1 = src_grid[r, c+1]
                s_p2 = src_grid[r+1, c+1]
                s_p3 = src_grid[r+1, c]

                d_p0 = dst_grid[r, c]
                d_p1 = dst_grid[r, c+1]
                d_p2 = dst_grid[r+1, c+1]
                d_p3 = dst_grid[r+1, c]

                # Wir teilen das Viereck in 2 Dreiecke

                # Dreieck 1: TL-TR-BL (0-1-3)
                warp_triangle_affine_roi(
                    image,
                    np.array([s_p0, s_p1, s_p3]),
                    np.array([d_p0, d_p1, d_p3]),
                    out_w, out_h, result
                )

                # Dreieck 2: TR-BR-BL (1-2-3)
                warp_triangle_affine_roi(
                    image,
                    np.array([s_p1, s_p2, s_p3]),
                    np.array([d_p1, d_p2, d_p3]),
                    out_w, out_h, result
                )

        return result

    except Exception as e:
        print(f"Mesh Warp Error: {e}")
        # Fallback
        try:
            src = np.array([[p[0]*img_w, p[1]*img_h] for p in source_points], dtype=np.float32)
            dst = np.array([[p[0]*out_w, p[1]*out_h] for p in output_points], dtype=np.float32)
            M = cv2.getPerspectiveTransform(src, dst)
            return cv2.warpPerspective(image, M, (out_w, out_h))
        except:
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

        warped = warp_image(image, source_points, output_points, output_size)

        if warped is None:
            continue

        # Simple Overlay Blending
        mask_indices = np.any(warped > 0, axis=2)
        result[mask_indices] = warped[mask_indices]

    return result

# --- Helper & Boilerplate ---

def composite_polygons(polygons_data, output_size):
    return composite_polygons_fast(polygons_data, output_size)

def numpy_to_qimage(image: np.ndarray) -> Optional['QImage']:
    from PyQt6.QtGui import QImage
    if image is None: return None
    try:
        if image.ndim == 3 and image.shape[2] == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        elif image.ndim == 3 and image.shape[2] == 4:
            rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
            h, w, ch = rgba.shape
            return QImage(rgba.data, w, h, ch * w, QImage.Format.Format_RGBA8888).copy()
        elif image.ndim == 2:
             h, w = image.shape
             return QImage(image.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    except: pass
    return None

def load_image(filepath: str) -> Optional[np.ndarray]:
    try: return cv2.imread(filepath, cv2.IMREAD_COLOR)
    except: return None

def clear_homography_cache(): pass