"""Hochoptimierte Bild-Transformation mit Homographie und Bilinearem Mesh-Warping."""

import logging
from typing import List, Tuple, Optional, Dict
from functools import lru_cache
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# --- Warp-Methode Dispatch ---
_warp_method = "perspective"  # "perspective" oder "bilinear_mesh"


def set_warp_method(method: str) -> None:
    """Setze Warp-Methode ('perspective' oder 'bilinear_mesh')."""
    global _warp_method
    if method not in ("perspective", "bilinear_mesh"):
        raise ValueError(f"Unbekannte Warp-Methode: {method}")
    _warp_method = method
    logger.info(f"Warp-Methode: {method}")


def get_warp_method() -> str:
    """Hole aktuelle Warp-Methode."""
    return _warp_method


# --- Renderer Backend Dispatch ---
_renderer_backend = "opencv"
_gl_compositor = None  # Lazy singleton


def set_renderer_backend(backend: str) -> None:
    """Setze Renderer-Backend ('opencv' oder 'opengl')."""
    global _renderer_backend
    if backend not in ("opencv", "opengl"):
        raise ValueError(f"Unbekanntes Backend: {backend}")
    _renderer_backend = backend
    logger.info(f"Renderer-Backend: {backend}")


def get_renderer_backend() -> str:
    """Hole aktuelles Renderer-Backend."""
    return _renderer_backend


# =============================================================================
# Perspective Warp (Homographie mit LRU-Cache)
# =============================================================================

# Pre-allocated arrays fuer haeufige Operationen
_POINT_BUFFER_SRC = np.zeros((4, 2), dtype=np.float32)
_POINT_BUFFER_DST = np.zeros((4, 2), dtype=np.float32)


def _points_to_array(points: List[List[float]], width: int, height: int, buffer: np.ndarray) -> np.ndarray:
    """Konvertiere Punkte zu Array - in-place fuer Performance."""
    buffer[0, 0] = points[0][0] * width
    buffer[0, 1] = points[0][1] * height
    buffer[1, 0] = points[1][0] * width
    buffer[1, 1] = points[1][1] * height
    buffer[2, 0] = points[2][0] * width
    buffer[2, 1] = points[2][1] * height
    buffer[3, 0] = points[3][0] * width
    buffer[3, 1] = points[3][1] * height
    return buffer


@lru_cache(maxsize=128)
def _get_homography_cached(
    src_key: Tuple[float, ...],
    dst_key: Tuple[float, ...],
    img_w: int, img_h: int,
    out_w: int, out_h: int
) -> Optional[np.ndarray]:
    """Gecachte Homographie-Berechnung."""
    src_pts = np.array([
        [src_key[0] * img_w, src_key[1] * img_h],
        [src_key[2] * img_w, src_key[3] * img_h],
        [src_key[4] * img_w, src_key[5] * img_h],
        [src_key[6] * img_w, src_key[7] * img_h],
    ], dtype=np.float32)

    dst_pts = np.array([
        [dst_key[0] * out_w, dst_key[1] * out_h],
        [dst_key[2] * out_w, dst_key[3] * out_h],
        [dst_key[4] * out_w, dst_key[5] * out_h],
        [dst_key[6] * out_w, dst_key[7] * out_h],
    ], dtype=np.float32)

    return cv2.getPerspectiveTransform(src_pts, dst_pts)


def _warp_image_perspective(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """Perspektivisches Warping mit gecachter Homographie."""
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    try:
        img_h, img_w = image.shape[:2]
        out_w, out_h = output_size

        # Cache-Key aus Punkten erstellen (gerundet fuer besseres Caching)
        src_key = tuple(round(p[i], 4) for p in source_points for i in (0, 1))
        dst_key = tuple(round(p[i], 4) for p in output_points for i in (0, 1))

        H = _get_homography_cached(src_key, dst_key, img_w, img_h, out_w, out_h)

        return cv2.warpPerspective(
            image, H, (out_w, out_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0)
        )

    except Exception:
        return None


def _warp_image_perspective_no_cache(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """Perspektivisches Warping ohne Caching - fuer Live-Dragging."""
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    try:
        img_h, img_w = image.shape[:2]
        out_w, out_h = output_size

        src_pts = _points_to_array(source_points, img_w, img_h, _POINT_BUFFER_SRC)
        dst_pts = _points_to_array(output_points, out_w, out_h, _POINT_BUFFER_DST)

        H = cv2.getPerspectiveTransform(src_pts, dst_pts)

        return cv2.warpPerspective(
            image, H, (out_w, out_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0)
        )

    except Exception:
        return None


# =============================================================================
# Bilinear Mesh Warp (20x20 Grid, 800 Dreiecke)
# =============================================================================

# Grid-Qualitaet: 20x20 = 400 Zellen = 800 Dreiecke
_GRID_ROWS = 20
_GRID_COLS = 20


def _get_bilinear_grid(points: List[List[float]], steps_x: int, steps_y: int) -> np.ndarray:
    """
    Berechnet Gitter-Punkte mittels bilinearer Interpolation.
    Garantiert lineare (gleichmaessige) Unterteilung der Aussenkanten.
    """
    p0 = np.array(points[0])
    p1 = np.array(points[1])
    p2 = np.array(points[2])
    p3 = np.array(points[3])

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


def _warp_triangle_affine_roi(
    img: np.ndarray,
    src_tri: np.ndarray,
    dst_tri: np.ndarray,
    out_w: int,
    out_h: int,
    result_buffer: np.ndarray
) -> None:
    """Warpt ein kleines Dreieck und blendet es in den Buffer."""
    min_x = int(np.floor(np.min(dst_tri[:, 0])))
    min_y = int(np.floor(np.min(dst_tri[:, 1])))
    max_x = int(np.ceil(np.max(dst_tri[:, 0])))
    max_y = int(np.ceil(np.max(dst_tri[:, 1])))

    x = max(0, min_x)
    y = max(0, min_y)
    w = min(out_w, max_x) - x
    h = min(out_h, max_y) - y

    if w <= 0 or h <= 0:
        return

    dst_tri_shifted = np.array([[p[0] - x, p[1] - y] for p in dst_tri], dtype=np.float32)

    M = cv2.getAffineTransform(src_tri, dst_tri_shifted)

    warped_roi = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst_tri_shifted.astype(np.int32), 255)

    roi_target = result_buffer[y:y + h, x:x + w]

    h_src, w_src = warped_roi.shape[:2]
    h_dst, w_dst = roi_target.shape[:2]
    h_c, w_c = min(h_src, h_dst), min(w_src, w_dst)

    if h_c > 0 and w_c > 0:
        np.copyto(
            roi_target[:h_c, :w_c],
            warped_roi[:h_c, :w_c],
            where=mask[:h_c, :w_c, np.newaxis] > 0
        )


def _warp_image_bilinear_mesh(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """
    Bilineares Mesh-Warping (20x20).
    Erzeugt ein feines Gitter, warpt jedes Segment als 2 affine Dreiecke.
    Qualitativ hochwertiger als Perspective, aber langsamer.
    """
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    out_w, out_h = output_size
    img_h, img_w = image.shape[:2]

    result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    try:
        src_grid = _get_bilinear_grid(source_points, _GRID_COLS, _GRID_ROWS)
        dst_grid = _get_bilinear_grid(output_points, _GRID_COLS, _GRID_ROWS)

        src_grid[..., 0] *= img_w
        src_grid[..., 1] *= img_h
        dst_grid[..., 0] *= out_w
        dst_grid[..., 1] *= out_h

        src_grid = src_grid.astype(np.float32)
        dst_grid = dst_grid.astype(np.float32)

        for r in range(_GRID_ROWS):
            for c in range(_GRID_COLS):
                s_p0 = src_grid[r, c]
                s_p1 = src_grid[r, c + 1]
                s_p2 = src_grid[r + 1, c + 1]
                s_p3 = src_grid[r + 1, c]

                d_p0 = dst_grid[r, c]
                d_p1 = dst_grid[r, c + 1]
                d_p2 = dst_grid[r + 1, c + 1]
                d_p3 = dst_grid[r + 1, c]

                # Dreieck 1: TL-TR-BL (0-1-3)
                _warp_triangle_affine_roi(
                    image,
                    np.array([s_p0, s_p1, s_p3]),
                    np.array([d_p0, d_p1, d_p3]),
                    out_w, out_h, result
                )

                # Dreieck 2: TR-BR-BL (1-2-3)
                _warp_triangle_affine_roi(
                    image,
                    np.array([s_p1, s_p2, s_p3]),
                    np.array([d_p1, d_p2, d_p3]),
                    out_w, out_h, result
                )

        return result

    except Exception as e:
        logger.error(f"Mesh Warp Error: {e}")
        # Fallback auf Perspective
        return _warp_image_perspective(image, source_points, output_points, output_size)


# =============================================================================
# Dispatch-Funktionen
# =============================================================================

def warp_image(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """Dispatch: Waehlt Warp-Methode basierend auf Einstellung."""
    if _warp_method == "bilinear_mesh":
        return _warp_image_bilinear_mesh(image, source_points, output_points, output_size)
    return _warp_image_perspective(image, source_points, output_points, output_size)


def warp_image_no_cache(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """Warping ohne Caching - fuer Live-Dragging."""
    if _warp_method == "bilinear_mesh":
        # Bilinear Mesh hat keinen Cache, direkt aufrufen
        return _warp_image_bilinear_mesh(image, source_points, output_points, output_size)
    return _warp_image_perspective_no_cache(image, source_points, output_points, output_size)


# =============================================================================
# Compositing
# =============================================================================

def composite_polygons(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int]
) -> np.ndarray:
    """Compositing mehrerer Quads."""
    out_w, out_h = output_size
    result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    if not polygons_data:
        return result

    mask = np.zeros((out_h, out_w), dtype=np.uint8)
    pts_buffer = np.zeros((4, 2), dtype=np.int32)

    for image, source_points, output_points in polygons_data:
        if image is None or len(source_points) != 4 or len(output_points) != 4:
            continue

        warped = warp_image(image, source_points, output_points, output_size)
        if warped is None:
            continue

        mask.fill(0)

        pts_buffer[0, 0] = int(output_points[0][0] * out_w)
        pts_buffer[0, 1] = int(output_points[0][1] * out_h)
        pts_buffer[1, 0] = int(output_points[1][0] * out_w)
        pts_buffer[1, 1] = int(output_points[1][1] * out_h)
        pts_buffer[2, 0] = int(output_points[2][0] * out_w)
        pts_buffer[2, 1] = int(output_points[2][1] * out_h)
        pts_buffer[3, 0] = int(output_points[3][0] * out_w)
        pts_buffer[3, 1] = int(output_points[3][1] * out_h)

        cv2.fillPoly(mask, [pts_buffer], 255)
        np.copyto(result, warped, where=mask[:, :, np.newaxis] > 0)

    return result


def _composite_opencv(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int],
    result_buffer: Optional[np.ndarray] = None
) -> np.ndarray:
    """CPU-basiertes Compositing mit OpenCV."""
    out_w, out_h = output_size

    if result_buffer is not None and result_buffer.shape == (out_h, out_w, 3):
        result = result_buffer
        result.fill(0)
    else:
        result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    if not polygons_data:
        return result

    mask = np.zeros((out_h, out_w), dtype=np.uint8)
    pts_buffer = np.zeros((4, 2), dtype=np.int32)

    for image, source_points, output_points in polygons_data:
        if image is None or len(source_points) != 4 or len(output_points) != 4:
            continue

        warped = warp_image(image, source_points, output_points, output_size)
        if warped is None:
            continue

        mask.fill(0)

        pts_buffer[0, 0] = int(output_points[0][0] * out_w)
        pts_buffer[0, 1] = int(output_points[0][1] * out_h)
        pts_buffer[1, 0] = int(output_points[1][0] * out_w)
        pts_buffer[1, 1] = int(output_points[1][1] * out_h)
        pts_buffer[2, 0] = int(output_points[2][0] * out_w)
        pts_buffer[2, 1] = int(output_points[2][1] * out_h)
        pts_buffer[3, 0] = int(output_points[3][0] * out_w)
        pts_buffer[3, 1] = int(output_points[3][1] * out_h)

        cv2.fillPoly(mask, [pts_buffer], 255)
        np.copyto(result, warped, where=mask[:, :, np.newaxis] > 0)

    return result


def _composite_opengl(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int],
    result_buffer: Optional[np.ndarray] = None
) -> Optional[np.ndarray]:
    """GPU-basiertes Compositing mit OpenGL. Returns None bei Fehler."""
    global _gl_compositor

    if _gl_compositor is None:
        from .gl_renderer import GLCompositor
        _gl_compositor = GLCompositor()

    return _gl_compositor.composite(polygons_data, output_size, result_buffer)


def composite_polygons_fast(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int],
    result_buffer: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Dispatch-Funktion: Waehlt Backend basierend auf Einstellung.
    OpenGL nur bei Perspective erlaubt (Shader nutzt inverse Homographie).
    Faellt bei OpenGL-Fehler oder Bilinear Mesh automatisch auf OpenCV zurueck.
    """
    if _renderer_backend == "opengl" and _warp_method == "perspective":
        result = _composite_opengl(polygons_data, output_size, result_buffer)
        if result is not None:
            return result
        logger.warning("OpenGL Fallback -> OpenCV")
    elif _renderer_backend == "opengl" and _warp_method == "bilinear_mesh":
        logger.debug("Bilinear Mesh + OpenGL nicht unterstuetzt, nutze OpenCV")

    return _composite_opencv(polygons_data, output_size, result_buffer)


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def numpy_to_qimage(image: np.ndarray) -> Optional['QImage']:
    """Optimierte Konvertierung numpy BGR zu QImage."""
    from PyQt6.QtGui import QImage

    if image is None:
        return None

    if image.ndim == 3 and image.shape[2] == 3:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

    elif image.ndim == 3 and image.shape[2] == 4:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        h, w, ch = rgba.shape
        bytes_per_line = ch * w
        return QImage(rgba.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888).copy()

    elif image.ndim == 2:
        h, w = image.shape
        return QImage(image.data, w, h, w, QImage.Format.Format_Grayscale8).copy()

    return None


def numpy_to_qimage_fast(image: np.ndarray, reuse_buffer: Optional[np.ndarray] = None) -> Optional['QImage']:
    """Schnellste Konvertierung - nutzt externen Buffer fuer RGB Konvertierung."""
    from PyQt6.QtGui import QImage

    if image is None:
        return None

    h, w = image.shape[:2]

    if reuse_buffer is not None and reuse_buffer.shape == image.shape:
        rgb = reuse_buffer
        cv2.cvtColor(image, cv2.COLOR_BGR2RGB, dst=rgb)
    else:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    ch = rgb.shape[2] if rgb.ndim == 3 else 1
    bytes_per_line = ch * w

    return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()


def load_image(filepath: str) -> Optional[np.ndarray]:
    """Optimiertes Bildladen mit IMREAD_COLOR fuer konsistentes Format."""
    try:
        img = cv2.imread(filepath, cv2.IMREAD_COLOR)
        if img is not None:
            return img
        return None
    except Exception:
        return None


def resize_for_display(image: np.ndarray, max_size: int = 1920) -> np.ndarray:
    """Resize grosser Bilder fuer schnellere Verarbeitung."""
    h, w = image.shape[:2]

    if w <= max_size and h <= max_size:
        return image

    scale = max_size / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def clear_homography_cache():
    """Cache leeren (z.B. bei Projekt-Wechsel)."""
    _get_homography_cached.cache_clear()
