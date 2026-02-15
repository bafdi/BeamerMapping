"""Optimierter Video Player - Hybrid: OpenCV (Frames) + QMediaPlayer (Audio)."""

from typing import Optional, Dict
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


def format_time(seconds: float) -> str:
    """Formatiere Sekunden als MM:SS."""
    if seconds < 0:
        seconds = 0
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


class VideoDecoder:
    """Threaded Video Decoder - OpenCV fuer schnelle Frame-Extraktion."""

    __slots__ = (
        'path', 'capture', 'width', 'height', 'fps', 'frame_count', 'duration',
        'playing', 'looping', 'current_frame_num', 'current_time',
        '_decode_thread', '_stop_flag', '_lock', '_current_frame', '_frame_dirty'
    )

    def __init__(self, path: str):
        self.path = path
        self.capture: Optional[cv2.VideoCapture] = None
        self.width = 0
        self.height = 0
        self.fps = 30.0
        self.frame_count = 0
        self.duration = 0.0

        # Playback state
        self.playing = False
        self.looping = True
        self.current_frame_num = 0
        self.current_time = 0.0

        # Threading
        self._decode_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        # Current frame (thread-safe)
        self._current_frame: Optional[np.ndarray] = None
        self._frame_dirty = False  # Neues Frame verfuegbar

        self._load()

    def _load(self) -> bool:
        """Lade Video-Metadaten."""
        try:
            # FFMPEG Backend fuer bessere Performance
            self.capture = cv2.VideoCapture(self.path, cv2.CAP_FFMPEG)
            if not self.capture.isOpened():
                self.capture = cv2.VideoCapture(self.path)
                if not self.capture.isOpened():
                    self.capture = None
                    return False

            self.width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.fps = self.capture.get(cv2.CAP_PROP_FPS) or 30.0
            self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
            self.duration = self.frame_count / self.fps if self.fps > 0 else 0

            # Erstes Frame laden
            ret, frame = self.capture.read()
            if ret:
                self._current_frame = frame
                self._frame_dirty = True
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)

            return True
        except Exception as e:
            print(f"Video load error: {e}")
            self.capture = None
            return False

    def start(self) -> None:
        """Starte Playback."""
        if self.playing or not self.capture:
            return

        self.playing = True
        self._stop_flag.clear()

        if self._decode_thread is None or not self._decode_thread.is_alive():
            self._decode_thread = threading.Thread(target=self._decode_loop, daemon=True)
            self._decode_thread.start()

    def pause(self) -> None:
        """Pausiere Playback."""
        self.playing = False

    def stop(self) -> None:
        """Stoppe Playback und reset."""
        self.playing = False
        self._stop_flag.set()

        if self._decode_thread and self._decode_thread.is_alive():
            self._decode_thread.join(timeout=0.5)
        self._decode_thread = None

        self.seek(0)

    def seek(self, time_seconds: float) -> None:
        """Springe zu Position."""
        if not self.capture:
            return

        time_seconds = max(0, min(time_seconds, self.duration))

        with self._lock:
            frame_num = int(time_seconds * self.fps)
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = self.capture.read()
            if ret:
                self._current_frame = frame
                self._frame_dirty = True
                self.current_frame_num = frame_num + 1
                self.current_time = time_seconds
            else:
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                self.current_frame_num = frame_num
                self.current_time = time_seconds

    def get_frame(self) -> Optional[np.ndarray]:
        """Hole aktuelles Frame (thread-safe, kein Copy wenn nicht noetig)."""
        with self._lock:
            if self._current_frame is not None:
                # Nur copy wenn dirty, sonst referenz
                if self._frame_dirty:
                    self._frame_dirty = False
                    return self._current_frame.copy()
                return self._current_frame
        return None

    def get_frame_if_new(self) -> Optional[np.ndarray]:
        """Hole Frame nur wenn neu (fuer effiziente Updates)."""
        with self._lock:
            if self._current_frame is not None and self._frame_dirty:
                self._frame_dirty = False
                return self._current_frame.copy()
        return None

    def _decode_loop(self) -> None:
        """Decode-Thread Hauptschleife - optimiert."""
        if not self.capture:
            return

        frame_duration = 1.0 / self.fps if self.fps > 0 else 1.0 / 30
        next_frame_time = time.perf_counter()

        while not self._stop_flag.is_set():
            if not self.playing:
                time.sleep(0.005)
                continue

            now = time.perf_counter()

            # Warte bis naechstes Frame faellig
            if now < next_frame_time:
                sleep_time = next_frame_time - now - 0.001
                if sleep_time > 0:
                    time.sleep(sleep_time)
                continue

            next_frame_time += frame_duration

            # Skip frames wenn zu langsam
            if now - next_frame_time > frame_duration * 2:
                next_frame_time = now + frame_duration

            # Read frame
            with self._lock:
                if not self.capture:
                    break

                ret, frame = self.capture.read()

                if not ret:
                    if self.looping:
                        self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        self.current_frame_num = 0
                        self.current_time = 0.0
                        next_frame_time = time.perf_counter()
                        continue
                    else:
                        self.playing = False
                        break

                self._current_frame = frame
                self._frame_dirty = True
                self.current_frame_num += 1
                self.current_time = self.current_frame_num / self.fps if self.fps > 0 else 0

    def release(self) -> None:
        """Ressourcen freigeben."""
        self.playing = False
        self._stop_flag.set()

        if self._decode_thread and self._decode_thread.is_alive():
            self._decode_thread.join(timeout=0.5)

        with self._lock:
            if self.capture:
                self.capture.release()
                self.capture = None
            self._current_frame = None


class VideoPlayerWidget(QFrame):
    """Video Player Widget - Hybrid: OpenCV (Frames) + QMediaPlayer (Audio)."""

    frame_ready = pyqtSignal(str, object)  # media_id, frame (np.ndarray)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoPlayerWidget")

        # State
        self.is_playing = False
        self.looping = True
        self._slider_dragging = False
        self._last_sync_time = 0.0

        # Per-video volume and mute state
        self._volumes: Dict[str, float] = {}  # media_id -> volume (0.0-1.0)
        self._muted: Dict[str, bool] = {}     # media_id -> muted

        # Video decoders (media_id -> decoder) - OpenCV fuer Frames
        self.decoders: Dict[str, VideoDecoder] = {}

        # Audio players (media_id -> (QMediaPlayer, QAudioOutput))
        self.audio_players: Dict[str, tuple] = {}

        # Current active video (for UI controls)
        self.current_media_id: Optional[str] = None
        self.current_path: Optional[str] = None

        # UI
        self._setup_ui()
        self._apply_style()

        # Timer fuer Frame-Updates (60 FPS check, emit nur bei neuen Frames)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_timer)
        self.update_timer.start(16)  # ~60 FPS check

        # Sync Timer (weniger haeufig)
        self.sync_timer = QTimer()
        self.sync_timer.timeout.connect(self._sync_audio_video)
        self.sync_timer.start(500)  # Alle 500ms sync check

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            #VideoPlayerWidget {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
            }
            QLabel { color: #aaa; font-size: 11px; }
            QPushButton {
                background-color: #333;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px 6px;
                color: #ccc;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #555; }
            QPushButton:checked { background-color: #2a6e2a; }
            QPushButton:disabled { color: #666; background-color: #222; }
            QSlider::groove:horizontal {
                height: 4px;
                background: #333;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0af;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #0af;
                border-radius: 2px;
            }
        """)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.filename_label = QLabel("No Video")
        self.filename_label.setStyleSheet("color: #888;")
        layout.addWidget(self.filename_label)

        # Time + Slider
        time_row = QHBoxLayout()
        time_row.setSpacing(4)

        self.time_label = QLabel("00:00")
        self.time_label.setFixedWidth(40)
        time_row.addWidget(self.time_label)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setMinimum(0)
        self.seek_slider.setMaximum(1000)
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        time_row.addWidget(self.seek_slider)

        self.duration_label = QLabel("00:00")
        self.duration_label.setFixedWidth(40)
        time_row.addWidget(self.duration_label)

        layout.addLayout(time_row)

        # Controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(3)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(40)
        self.play_btn.clicked.connect(self._toggle_play)
        ctrl_row.addWidget(self.play_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedWidth(36)
        self.stop_btn.clicked.connect(self._stop)
        ctrl_row.addWidget(self.stop_btn)

        self.loop_btn = QPushButton("Loop")
        self.loop_btn.setFixedWidth(36)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        self.loop_btn.clicked.connect(self._toggle_loop)
        ctrl_row.addWidget(self.loop_btn)

        # Mute button
        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedWidth(28)
        self.mute_btn.setCheckable(True)
        self.mute_btn.clicked.connect(self._toggle_mute)
        ctrl_row.addWidget(self.mute_btn)

        # Volume slider
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(60)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        ctrl_row.addWidget(self.volume_slider)

        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.play_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(enabled)
        self.seek_slider.setEnabled(enabled)
        self.loop_btn.setEnabled(enabled)
        self.mute_btn.setEnabled(enabled)
        self.volume_slider.setEnabled(enabled)

    def _create_audio_player(self, media_id: str, path: str) -> bool:
        """Erstelle QMediaPlayer fuer Audio."""
        if media_id in self.audio_players:
            return True

        # Default volume/mute for new videos
        if media_id not in self._volumes:
            self._volumes[media_id] = 0.7
        if media_id not in self._muted:
            self._muted[media_id] = False

        try:
            audio_output = QAudioOutput()
            audio_output.setVolume(self._volumes[media_id])
            audio_output.setMuted(self._muted[media_id])

            player = QMediaPlayer()
            player.setAudioOutput(audio_output)
            player.setSource(QUrl.fromLocalFile(path))

            # Looping ueber mediaStatusChanged
            player.mediaStatusChanged.connect(
                lambda status, p=player, mid=media_id: self._on_media_status_changed(status, p, mid)
            )

            self.audio_players[media_id] = (player, audio_output)
            return True
        except Exception as e:
            print(f"Audio player error: {e}")
            return False

    def _on_media_status_changed(self, status, player: QMediaPlayer, media_id: str) -> None:
        """Handle media status fuer Looping."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.looping:
            decoder = self.decoders.get(media_id)
            if decoder and decoder.playing:
                player.setPosition(0)
                player.play()

    def load_video(self, media_id: str, path: str) -> bool:
        """Lade Video (OpenCV Decoder + Audio Player)."""
        # OpenCV Decoder
        if media_id not in self.decoders:
            decoder = VideoDecoder(path)
            if decoder.capture is None:
                return False
            decoder.looping = self.looping
            self.decoders[media_id] = decoder

        # Audio Player
        self._create_audio_player(media_id, path)

        return True

    def set_active_media(self, media_id: Optional[str], path: Optional[str]) -> None:
        """Setze aktives Video fuer UI-Controls."""
        self.current_media_id = media_id
        self.current_path = path

        if media_id is None or path is None:
            self._set_controls_enabled(False)
            self.filename_label.setText("No Video")
            self.duration_label.setText("00:00")
            self.time_label.setText("00:00")
            self.seek_slider.setValue(0)
            return

        if not self.load_video(media_id, path):
            self._set_controls_enabled(False)
            self.filename_label.setText("Error")
            return

        decoder = self.decoders[media_id]

        name = Path(path).name
        if len(name) > 20:
            name = name[:17] + "..."
        self.filename_label.setText(name)
        self.duration_label.setText(format_time(decoder.duration))

        self.is_playing = decoder.playing
        self.play_btn.setText("Pause" if self.is_playing else "Play")

        # Update volume/mute UI for this video
        volume = self._volumes.get(media_id, 0.7)
        muted = self._muted.get(media_id, False)
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(volume * 100))
        self.volume_slider.blockSignals(False)
        self.mute_btn.blockSignals(True)
        self.mute_btn.setChecked(muted)
        self.mute_btn.setText("🔇" if muted else "🔊")
        self.mute_btn.blockSignals(False)

        self._set_controls_enabled(True)

    def _on_timer(self) -> None:
        """Timer callback - emit frames fuer alle spielenden Videos."""
        # Emit frames nur wenn neu
        for media_id, decoder in self.decoders.items():
            if decoder.playing:
                frame = decoder.get_frame_if_new()
                if frame is not None:
                    self.frame_ready.emit(media_id, frame)

        # Update UI nur fuer aktuelles Video
        if self.current_media_id and self.current_media_id in self.decoders:
            decoder = self.decoders[self.current_media_id]

            if not self._slider_dragging:
                self.time_label.setText(format_time(decoder.current_time))

                if decoder.duration > 0:
                    pos = int((decoder.current_time / decoder.duration) * 1000)
                    self.seek_slider.setValue(pos)

            if decoder.playing != self.is_playing:
                self.is_playing = decoder.playing
                self.play_btn.setText("Pause" if self.is_playing else "Play")

    def _sync_audio_video(self) -> None:
        """Synchronisiere Audio mit Video (weniger haeufig aufgerufen)."""
        for media_id, decoder in self.decoders.items():
            if not decoder.playing:
                continue

            audio_data = self.audio_players.get(media_id)
            if not audio_data:
                continue

            player, _ = audio_data

            # Sync nur wenn Differenz > 100ms
            video_pos_ms = int(decoder.current_time * 1000)
            audio_pos_ms = player.position()

            diff = abs(video_pos_ms - audio_pos_ms)
            if diff > 150:
                player.setPosition(video_pos_ms)

    def _toggle_play(self) -> None:
        """Play/Pause toggle."""
        if not self.current_media_id:
            return

        decoder = self.decoders.get(self.current_media_id)
        audio_data = self.audio_players.get(self.current_media_id)

        if not decoder:
            return

        if decoder.playing:
            decoder.pause()
            if audio_data:
                audio_data[0].pause()
            self.is_playing = False
            self.play_btn.setText("Play")
        else:
            decoder.start()
            if audio_data:
                audio_data[0].setPosition(int(decoder.current_time * 1000))
                audio_data[0].play()
            self.is_playing = True
            self.play_btn.setText("Pause")

    def _stop(self) -> None:
        """Stop aktuelles Video."""
        if not self.current_media_id:
            return

        decoder = self.decoders.get(self.current_media_id)
        audio_data = self.audio_players.get(self.current_media_id)

        if decoder:
            decoder.stop()
        if audio_data:
            audio_data[0].stop()
            audio_data[0].setPosition(0)

        self.is_playing = False
        self.play_btn.setText("Play")
        self.seek_slider.setValue(0)
        self.time_label.setText("00:00")

    def _toggle_loop(self) -> None:
        """Toggle loop mode."""
        self.looping = self.loop_btn.isChecked()
        for decoder in self.decoders.values():
            decoder.looping = self.looping

    def _toggle_mute(self) -> None:
        """Toggle mute for current video only."""
        if not self.current_media_id:
            return

        muted = self.mute_btn.isChecked()
        self.mute_btn.setText("🔇" if muted else "🔊")

        # Store and apply for current video only
        self._muted[self.current_media_id] = muted
        audio_data = self.audio_players.get(self.current_media_id)
        if audio_data:
            audio_data[1].setMuted(muted)

    def _on_volume_changed(self, value: int) -> None:
        """Handle volume slider change for current video only."""
        if not self.current_media_id:
            return

        volume = value / 100.0

        # Store and apply for current video only
        self._volumes[self.current_media_id] = volume
        audio_data = self.audio_players.get(self.current_media_id)
        if audio_data:
            audio_data[1].setVolume(volume)

    def _on_slider_pressed(self) -> None:
        self._slider_dragging = True

    def _on_slider_released(self) -> None:
        self._slider_dragging = False

        if not self.current_media_id:
            return

        decoder = self.decoders.get(self.current_media_id)
        audio_data = self.audio_players.get(self.current_media_id)

        if not decoder:
            return

        position = (self.seek_slider.value() / 1000.0) * decoder.duration
        decoder.seek(position)

        if audio_data:
            audio_data[0].setPosition(int(position * 1000))

    def _on_slider_moved(self, value: int) -> None:
        if not self.current_media_id or self.current_media_id not in self.decoders:
            return

        decoder = self.decoders[self.current_media_id]
        position = (value / 1000.0) * decoder.duration
        self.time_label.setText(format_time(position))

    def get_frame(self, media_id: str) -> Optional[np.ndarray]:
        """Hole aktuelles Frame fuer ein Medium."""
        decoder = self.decoders.get(media_id)
        if decoder:
            return decoder.get_frame()
        return None

    def start_all_videos(self) -> None:
        """Starte alle geladenen Videos (fuer Autoplay)."""
        for media_id, decoder in self.decoders.items():
            if not decoder.playing:
                decoder.start()
                audio_data = self.audio_players.get(media_id)
                if audio_data:
                    audio_data[0].play()

    def cleanup(self) -> None:
        """Aufraumen."""
        self.update_timer.stop()
        self.sync_timer.stop()

        for decoder in self.decoders.values():
            decoder.release()
        self.decoders.clear()

        for player, audio_output in self.audio_players.values():
            player.stop()
        self.audio_players.clear()
