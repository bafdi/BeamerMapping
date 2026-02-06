"""Queue Manager - Verwaltet Queue-Operationen und Transitions."""

from __future__ import annotations
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .models import (
    Project, Queue, MediaLayerState, PolygonState, QueueTransition
)

if TYPE_CHECKING:
    from .video_player import VideoPlayerWidget


class QueueManager:
    """Verwaltet Queue-Operationen und Transitions."""

    def __init__(self, project: Project, video_player: 'VideoPlayerWidget'):
        self.project = project
        self.video_player = video_player

        # Transition state
        self._active_transition: Optional[QueueTransition] = None
        self._transition_start_time: float = 0
        self._transition_from_state: Optional[Queue] = None
        self._transition_to_state: Optional[Queue] = None

        # Callback for UI updates during transitions
        self._on_transition_update: Optional[callable] = None

    def set_project(self, project: Project) -> None:
        """Setze das aktive Projekt."""
        self.project = project

    def set_on_transition_update(self, callback: callable) -> None:
        """Setze Callback fuer Transition-Updates."""
        self._on_transition_update = callback

    # === Snapshot erstellen ===

    def capture_current_state(self, name: Optional[str] = None, index: int = 0) -> Queue:
        """Erstellt Snapshot des aktuellen Zustands."""
        queue = Queue(
            name=name or f"Queue {index + 1}",
            index=index,
            created_at=datetime.now().isoformat(),
        )

        # Media Layer States
        for ml in self.project.media_layers:
            state = MediaLayerState(
                media_layer_id=ml.id,
                media_id=ml.media_id,
                visible=ml.visible,
            )

            # Video-spezifisch
            if ml.media_id and ml.media_id in self.video_player.decoders:
                decoder = self.video_player.decoders[ml.media_id]
                state.current_time = decoder.current_time
                state.playing = decoder.playing
                state.looping = decoder.looping
                state.volume = self.video_player._volumes.get(ml.media_id, 0.7)
                state.muted = self.video_player._muted.get(ml.media_id, False)

            queue.media_layer_states.append(state)

        # Polygon States
        for poly in self.project.polygons:
            state = PolygonState(
                polygon_id=poly.id,
                media_layer_id=poly.media_layer_id,
                output_layer_id=poly.output_layer_id,
                source_points=[p.copy() for p in poly.source_points],
                output_points=[p.copy() for p in poly.output_points],
            )
            queue.polygon_states.append(state)

        return queue

    # === Queue abrufen ===

    def recall_queue(self, queue: Queue) -> None:
        """Ruft Queue ab mit UID-basiertem Merge."""
        if queue.transition.mode == "instant":
            self._apply_state_instant(queue)
        else:
            self._start_transition(queue)

    def _apply_state_instant(self, queue: Queue) -> None:
        """Wendet State sofort an (kein Fade)."""
        # Media Layer States
        for mls in queue.media_layer_states:
            ml = self.project.get_media_layer_by_id(mls.media_layer_id)
            if not ml:
                continue  # UID nicht gefunden -> ueberspringen

            ml.media_id = mls.media_id
            ml.visible = mls.visible

            # Video Playback
            if mls.media_id and mls.media_id in self.video_player.decoders:
                decoder = self.video_player.decoders[mls.media_id]
                decoder.seek(mls.current_time)
                decoder.looping = mls.looping
                self.video_player._volumes[mls.media_id] = mls.volume
                self.video_player._muted[mls.media_id] = mls.muted

                # Audio Player aktualisieren
                if mls.media_id in self.video_player.audio_players:
                    _, audio_output = self.video_player.audio_players[mls.media_id]
                    audio_output.setVolume(mls.volume)
                    audio_output.setMuted(mls.muted)

                if mls.playing and not decoder.playing:
                    decoder.start()
                    if mls.media_id in self.video_player.audio_players:
                        player, _ = self.video_player.audio_players[mls.media_id]
                        player.setPosition(int(mls.current_time * 1000))
                        player.play()
                elif not mls.playing and decoder.playing:
                    decoder.pause()
                    if mls.media_id in self.video_player.audio_players:
                        player, _ = self.video_player.audio_players[mls.media_id]
                        player.pause()

        # Polygon States (UID-Match)
        for ps in queue.polygon_states:
            poly = self.project.get_polygon_by_id(ps.polygon_id)
            if not poly:
                continue  # UID nicht gefunden -> ueberspringen

            poly.media_layer_id = ps.media_layer_id
            poly.output_layer_id = ps.output_layer_id
            poly.source_points = [p.copy() for p in ps.source_points]
            poly.output_points = [p.copy() for p in ps.output_points]

    # === Transitions ===

    def _start_transition(self, queue: Queue) -> None:
        """Startet eine animierte Transition."""
        self._transition_from_state = self.capture_current_state()
        self._transition_to_state = queue
        self._transition_start_time = time.time()
        self._active_transition = queue.transition

    def update_transition(self) -> bool:
        """Update Transition (aufrufen im Timer). Returns True wenn aktiv."""
        if not self._active_transition:
            return False

        elapsed = (time.time() - self._transition_start_time) * 1000
        progress = min(1.0, elapsed / self._active_transition.duration_ms)
        progress = self._apply_easing(progress, self._active_transition.easing)

        # Interpoliere States
        self._interpolate_states(progress)

        # Callback fuer UI Update
        if self._on_transition_update:
            self._on_transition_update()

        if progress >= 1.0:
            # Transition fertig - finalen State anwenden
            self._apply_state_instant(self._transition_to_state)
            self._active_transition = None
            self._transition_from_state = None
            self._transition_to_state = None
            return False

        return True

    def is_transitioning(self) -> bool:
        """Gibt zurueck ob eine Transition aktiv ist."""
        return self._active_transition is not None

    def _interpolate_states(self, t: float) -> None:
        """Interpoliert zwischen from_state und to_state."""
        if not self._transition_from_state or not self._transition_to_state:
            return

        # Polygon Points interpolieren
        for to_ps in self._transition_to_state.polygon_states:
            poly = self.project.get_polygon_by_id(to_ps.polygon_id)
            if not poly:
                continue

            # Finde from_state
            from_ps = None
            for ps in self._transition_from_state.polygon_states:
                if ps.polygon_id == to_ps.polygon_id:
                    from_ps = ps
                    break

            if not from_ps:
                continue

            # Lineare Interpolation der Punkte
            for i in range(min(4, len(poly.source_points), len(from_ps.source_points), len(to_ps.source_points))):
                poly.source_points[i][0] = self._lerp(
                    from_ps.source_points[i][0],
                    to_ps.source_points[i][0],
                    t
                )
                poly.source_points[i][1] = self._lerp(
                    from_ps.source_points[i][1],
                    to_ps.source_points[i][1],
                    t
                )

            for i in range(min(4, len(poly.output_points), len(from_ps.output_points), len(to_ps.output_points))):
                poly.output_points[i][0] = self._lerp(
                    from_ps.output_points[i][0],
                    to_ps.output_points[i][0],
                    t
                )
                poly.output_points[i][1] = self._lerp(
                    from_ps.output_points[i][1],
                    to_ps.output_points[i][1],
                    t
                )

        # Volume interpolieren (fuer Dissolve-Effekt)
        if self._active_transition.mode == "dissolve":
            for to_mls in self._transition_to_state.media_layer_states:
                from_mls = None
                for mls in self._transition_from_state.media_layer_states:
                    if mls.media_layer_id == to_mls.media_layer_id:
                        from_mls = mls
                        break

                if from_mls and to_mls.media_id:
                    new_vol = self._lerp(from_mls.volume, to_mls.volume, t)
                    self.video_player._volumes[to_mls.media_id] = new_vol

                    if to_mls.media_id in self.video_player.audio_players:
                        _, audio_output = self.video_player.audio_players[to_mls.media_id]
                        audio_output.setVolume(new_vol)

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        """Lineare Interpolation."""
        return a + t * (b - a)

    @staticmethod
    def _apply_easing(t: float, easing: str) -> float:
        """Wendet Easing-Kurve an."""
        if easing == "ease-in":
            return t * t
        elif easing == "ease-out":
            return 1 - (1 - t) * (1 - t)
        elif easing == "ease-in-out":
            return t * t * (3 - 2 * t)
        return t  # linear

    # === Utility ===

    def save_queue(self, index: int, name: Optional[str] = None,
                   transition: Optional[QueueTransition] = None) -> Queue:
        """Speichere aktuellen State als Queue am gegebenen Index."""
        queue = self.capture_current_state(name=name, index=index)
        if transition:
            queue.transition = transition
        self.project.add_queue(queue)
        return queue

    def delete_queue(self, index: int) -> bool:
        """Loesche Queue am gegebenen Index."""
        queue = self.project.get_queue_by_index(index)
        if queue:
            self.project.remove_queue(queue)
            return True
        return False
