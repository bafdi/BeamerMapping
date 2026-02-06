"""Test-Patterns fuer Kalibrierung."""

import numpy as np
import cv2


def create_grid_pattern(width: int = 1920, height: int = 1080,
                        grid_size: int = 100, color: tuple = (255, 255, 255)) -> np.ndarray:
    """Erstelle ein Grid-Pattern."""
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Vertikale Linien
    for x in range(0, width, grid_size):
        cv2.line(img, (x, 0), (x, height), color, 1)

    # Horizontale Linien
    for y in range(0, height, grid_size):
        cv2.line(img, (0, y), (width, y), color, 1)

    # Dickere Linien fuer Mitte
    cv2.line(img, (width // 2, 0), (width // 2, height), color, 2)
    cv2.line(img, (0, height // 2), (width, height // 2), color, 2)

    return img


def create_edge_pattern(width: int = 1920, height: int = 1080,
                        border: int = 50, color: tuple = (255, 255, 255)) -> np.ndarray:
    """Erstelle ein Edge-Pattern mit Rahmen und Diagonalen."""
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Aeusserer Rahmen
    cv2.rectangle(img, (border, border), (width - border, height - border), color, 2)

    # Innerer Rahmen
    inner = border * 2
    cv2.rectangle(img, (inner, inner), (width - inner, height - inner), color, 1)

    # Diagonalen
    cv2.line(img, (0, 0), (width, height), color, 1)
    cv2.line(img, (width, 0), (0, height), color, 1)

    # Mittelkreuz
    cv2.line(img, (width // 2, 0), (width // 2, height), color, 1)
    cv2.line(img, (0, height // 2), (width, height // 2), color, 1)

    # Eck-Marker
    marker_size = 30
    for x, y in [(border, border), (width - border, border),
                 (border, height - border), (width - border, height - border)]:
        cv2.line(img, (x - marker_size, y), (x + marker_size, y), (0, 255, 0), 2)
        cv2.line(img, (x, y - marker_size), (x, y + marker_size), (0, 255, 0), 2)

    return img


def create_color_bars(width: int = 1920, height: int = 1080) -> np.ndarray:
    """Erstelle Farb-Balken."""
    img = np.zeros((height, width, 3), dtype=np.uint8)

    colors = [
        (255, 255, 255),  # Weiss
        (0, 255, 255),    # Gelb (BGR)
        (255, 255, 0),    # Cyan
        (0, 255, 0),      # Gruen
        (255, 0, 255),    # Magenta
        (0, 0, 255),      # Rot
        (255, 0, 0),      # Blau
        (0, 0, 0),        # Schwarz
    ]

    bar_width = width // len(colors)
    for i, color in enumerate(colors):
        x1 = i * bar_width
        x2 = (i + 1) * bar_width if i < len(colors) - 1 else width
        img[:, x1:x2] = color

    return img


def create_white(width: int = 1920, height: int = 1080) -> np.ndarray:
    """Erstelle weisses Bild."""
    return np.ones((height, width, 3), dtype=np.uint8) * 255


def create_black(width: int = 1920, height: int = 1080) -> np.ndarray:
    """Erstelle schwarzes Bild."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def create_gradient(width: int = 1920, height: int = 1080) -> np.ndarray:
    """Erstelle Gradienten von schwarz zu weiss."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(width):
        value = int(255 * x / width)
        img[:, x] = (value, value, value)
    return img


# Dictionary aller verfuegbaren Test-Patterns
TEST_PATTERNS = {
    "Grid": create_grid_pattern,
    "Edges": create_edge_pattern,
    "Color Bars": create_color_bars,
    "White": create_white,
    "Black": create_black,
    "Gradient": create_gradient,
}


def get_test_pattern(name: str, width: int = 1920, height: int = 1080) -> np.ndarray:
    """Hole ein Test-Pattern nach Name."""
    if name in TEST_PATTERNS:
        return TEST_PATTERNS[name](width, height)
    return create_grid_pattern(width, height)
