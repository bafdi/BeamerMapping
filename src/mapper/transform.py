"""Hochoptimierte Bild-Transformation mit Homographie und Caching."""

import logging
from typing import List, Tuple, Optional, Dict
from functools import lru_cache
import cv2
import numpy as np

logger = logging.getLogger(__name__)

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

# Pre-allocated arrays fuer haeufige Operationen (Thread-local wuerde hier helfen bei Multi-Threading)
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


def warp_image(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """
    Hochoptimiertes Warping mit perspektivischer Transformation.
    Nutzt Caching fuer Homographie-Matrizen.
    """
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    try:
        img_h, img_w = image.shape[:2]
        out_w, out_h = output_size

        # Cache-Key aus Punkten erstellen (gerundet fuer besseres Caching)
        src_key = tuple(round(p[i], 4) for p in source_points for i in (0, 1))
        dst_key = tuple(round(p[i], 4) for p in output_points for i in (0, 1))

        H = _get_homography_cached(src_key, dst_key, img_w, img_h, out_w, out_h)

        # INTER_LINEAR ist schneller als INTER_CUBIC, BORDER_CONSTANT vermeidet Checks
        return cv2.warpPerspective(
            image, H, (out_w, out_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0)
        )

    except Exception:
        return None


def warp_image_no_cache(
    image: np.ndarray,
    source_points: List[List[float]],
    output_points: List[List[float]],
    output_size: Tuple[int, int]
) -> Optional[np.ndarray]:
    """Warping ohne Caching - fuer sich staendig aendernde Punkte."""
    if image is None or len(source_points) != 4 or len(output_points) != 4:
        return None

    try:
        img_h, img_w = image.shape[:2]
        out_w, out_h = output_size

        # Direkte Array-Erstellung (schneller als List Comprehension)
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


def composite_polygons(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int]
) -> np.ndarray:
    """
    Hochoptimiertes Compositing mehrerer Quads.
    Nutzt Pre-Allocation und minimiert Speicheroperationen.
    """
    out_w, out_h = output_size

    # Pre-allocate result array
    result = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    if not polygons_data:
        return result

    # Pre-allocate mask (wird wiederverwendet)
    mask = np.zeros((out_h, out_w), dtype=np.uint8)
    pts_buffer = np.zeros((4, 2), dtype=np.int32)

    for image, source_points, output_points in polygons_data:
        if image is None or len(source_points) != 4 or len(output_points) != 4:
            continue

        warped = warp_image(image, source_points, output_points, output_size)
        if warped is None:
            continue

        # Maske erstellen - in-place clear und fill
        mask.fill(0)

        # Punkte direkt in Buffer schreiben
        pts_buffer[0, 0] = int(output_points[0][0] * out_w)
        pts_buffer[0, 1] = int(output_points[0][1] * out_h)
        pts_buffer[1, 0] = int(output_points[1][0] * out_w)
        pts_buffer[1, 1] = int(output_points[1][1] * out_h)
        pts_buffer[2, 0] = int(output_points[2][0] * out_w)
        pts_buffer[2, 1] = int(output_points[2][1] * out_h)
        pts_buffer[3, 0] = int(output_points[3][0] * out_w)
        pts_buffer[3, 1] = int(output_points[3][1] * out_h)

        cv2.fillPoly(mask, [pts_buffer], 255)

        # Optimiertes Blending mit copyTo (schneller als np.where)
        np.copyto(result, warped, where=mask[:, :, np.newaxis] > 0)

    return result


def _composite_opencv(
    polygons_data: List[Tuple[np.ndarray, List[List[float]], List[List[float]]]],
    output_size: Tuple[int, int],
    result_buffer: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    CPU-basiertes Compositing mit OpenCV.
    Noch schnellere Version mit externem Buffer (vermeidet Allocation).
    """
    out_w, out_h = output_size

    # Externen Buffer nutzen oder neuen erstellen
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
    Faellt bei OpenGL-Fehler automatisch auf OpenCV zurueck.
    """
    if _renderer_backend == "opengl":
        result = _composite_opengl(polygons_data, output_size, result_buffer)
        if result is not None:
            return result
        # Fallback auf OpenCV
        logger.warning("OpenGL Fallback -> OpenCV")

    return _composite_opencv(polygons_data, output_size, result_buffer)


# Gecachte QImage-Konvertierung
_qimage_cache: Dict[int, 'QImage'] = {}
_QIMAGE_CACHE_MAX = 16


def numpy_to_qimage(image: np.ndarray) -> Optional['QImage']:
    """
    Optimierte Konvertierung numpy BGR zu QImage.
    Nutzt Caching basierend auf Array-ID.
    """
    from PyQt6.QtGui import QImage

    if image is None:
        return None

    # Direkte Konvertierung ohne Zwischen-Array wenn moeglich
    if image.ndim == 3 and image.shape[2] == 3:
        # BGR zu RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w

        # QImage erstellen - .copy() ist wichtig da numpy Array sich aendern kann
        return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()

    elif image.ndim == 3 and image.shape[2] == 4:
        # BGRA zu RGBA
        rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        h, w, ch = rgba.shape
        bytes_per_line = ch * w
        return QImage(rgba.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888).copy()

    elif image.ndim == 2:
        # Grayscale
        h, w = image.shape
        return QImage(image.data, w, h, w, QImage.Format.Format_Grayscale8).copy()

    return None


def numpy_to_qimage_fast(image: np.ndarray, reuse_buffer: Optional[np.ndarray] = None) -> Optional['QImage']:
    """
    Schnellste Konvertierung - nutzt externen Buffer fuer RGB Konvertierung.
    Fuer Echtzeit-Rendering.
    """
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
        # IMREAD_COLOR garantiert 3-Kanal BGR
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
