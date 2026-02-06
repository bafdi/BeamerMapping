"""Live-Quellen: Screen Capture und Kameras."""

from typing import Optional, List, Tuple
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


class ScreenCapture:
    """Screen Capture fuer einen Monitor."""

    def __init__(self, monitor_index: int = 0):
        self.monitor_index = monitor_index
        self.sct = None
        if HAS_MSS:
            self.sct = mss.mss()

    def get_monitors(self) -> List[dict]:
        """Liste aller Monitore."""
        if not self.sct:
            return []
        return list(self.sct.monitors[1:])  # Skip "all monitors" entry

    def capture(self) -> Optional[np.ndarray]:
        """Capture aktuellen Frame."""
        if not self.sct:
            return None

        try:
            monitors = self.sct.monitors
            if self.monitor_index + 1 >= len(monitors):
                return None

            monitor = monitors[self.monitor_index + 1]
            screenshot = self.sct.grab(monitor)

            # Konvertiere zu numpy array (BGRA -> BGR)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return img

        except Exception as e:
            print(f"Screen capture error: {e}")
            return None

    def close(self) -> None:
        """Schliesse Screen Capture."""
        if self.sct:
            self.sct.close()
            self.sct = None


class CameraCapture:
    """Kamera-Capture."""

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = None
        if HAS_CV2:
            self.cap = cv2.VideoCapture(camera_index)

    @staticmethod
    def list_cameras(max_cameras: int = 5) -> List[Tuple[int, str]]:
        """Liste verfuegbare Kameras - stoppt nach 2 Fehlschlaegen."""
        cameras = []
        if not HAS_CV2:
            return cameras

        consecutive_failures = 0
        for i in range(max_cameras):
            # Schnellerer Check mit AVFoundation auf macOS
            cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
            if not cap.isOpened():
                # Fallback
                cap = cv2.VideoCapture(i)

            if cap.isOpened():
                consecutive_failures = 0
                name = f"Camera {i}"
                cameras.append((i, name))
                cap.release()
            else:
                consecutive_failures += 1
                cap.release()
                # Nach 2 Fehlschlaegen abbrechen
                if consecutive_failures >= 2:
                    break

        return cameras

    def is_opened(self) -> bool:
        """Pruefe ob Kamera geoeffnet."""
        return self.cap is not None and self.cap.isOpened()

    def capture(self) -> Optional[np.ndarray]:
        """Capture aktuellen Frame."""
        if not self.cap or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if ret:
            return frame
        return None

    def close(self) -> None:
        """Schliesse Kamera."""
        if self.cap:
            self.cap.release()
            self.cap = None


class LiveSourceManager:
    """Manager fuer alle Live-Quellen."""

    def __init__(self):
        self.screen_captures: dict = {}  # monitor_idx -> ScreenCapture
        self.cameras: dict = {}  # camera_idx -> CameraCapture
        self._active_cameras: set = set()  # Aktuell benoetigte Kameras
        self._active_screens: set = set()  # Aktuell benoetigte Screens

    def get_screen_capture(self, monitor_index: int) -> ScreenCapture:
        """Hole oder erstelle Screen Capture."""
        if monitor_index not in self.screen_captures:
            self.screen_captures[monitor_index] = ScreenCapture(monitor_index)
        return self.screen_captures[monitor_index]

    def get_camera(self, camera_index: int) -> CameraCapture:
        """Hole oder erstelle Kamera Capture."""
        if camera_index not in self.cameras:
            self.cameras[camera_index] = CameraCapture(camera_index)
        return self.cameras[camera_index]

    def capture_screen(self, monitor_index: int) -> Optional[np.ndarray]:
        """Capture Screen."""
        self._active_screens.add(monitor_index)
        sc = self.get_screen_capture(monitor_index)
        return sc.capture()

    def capture_camera(self, camera_index: int) -> Optional[np.ndarray]:
        """Capture Kamera."""
        self._active_cameras.add(camera_index)
        cam = self.get_camera(camera_index)
        return cam.capture()

    def close_camera(self, camera_index: int) -> None:
        """Schliesse eine spezifische Kamera."""
        if camera_index in self.cameras:
            self.cameras[camera_index].close()
            del self.cameras[camera_index]
        self._active_cameras.discard(camera_index)

    def close_screen(self, monitor_index: int) -> None:
        """Schliesse einen spezifischen Screen Capture."""
        if monitor_index in self.screen_captures:
            self.screen_captures[monitor_index].close()
            del self.screen_captures[monitor_index]
        self._active_screens.discard(monitor_index)

    def cleanup_inactive(self, active_camera_indices: set, active_screen_indices: set) -> None:
        """Schliesse alle Kameras/Screens die nicht mehr aktiv sind."""
        # Kameras die nicht mehr gebraucht werden schliessen
        cameras_to_close = set(self.cameras.keys()) - active_camera_indices
        for cam_idx in cameras_to_close:
            self.close_camera(cam_idx)

        # Screens die nicht mehr gebraucht werden schliessen
        screens_to_close = set(self.screen_captures.keys()) - active_screen_indices
        for screen_idx in screens_to_close:
            self.close_screen(screen_idx)

    def reset_active_tracking(self) -> None:
        """Reset aktive Tracking-Sets fuer neuen Frame-Zyklus."""
        self._active_cameras.clear()
        self._active_screens.clear()

    def close_all(self) -> None:
        """Schliesse alle Quellen."""
        for sc in self.screen_captures.values():
            sc.close()
        self.screen_captures.clear()

        for cam in self.cameras.values():
            cam.close()
        self.cameras.clear()
