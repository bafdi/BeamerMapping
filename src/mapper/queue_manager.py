"""Queue Manager - Verwaltet Queue-Operationen und Transitions."""

from __future__ import annotations
import math
import time
from datetime import datetime
from typing import Optional, Dict, Set, TYPE_CHECKING

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
        self._transition_to_state: Optional[Queue] = None
        self._transition_progress: float = 0.0

        # Audio-Volumes vom Zustand vor dem Wechsel (media_id -> volume)
        self._transition_from_audio: Dict[str, float] = {}

        # Videos die waehrend Transition weiterlaufen muessen
        self._transition_keep_alive: Set[str] = set()

        # Callbacks
        self._on_transition_update: Optional[callable] = None
        self._on_pre_transition: Optional[callable] = None

    def set_project(self, project: Project) -> None:
        """Setze das aktive Projekt."""
        self.project = project

    def set_on_transition_update(self, callback: callable) -> None:
        """Setze Callback fuer Transition-Updates."""
        self._on_transition_update = callback

    def set_on_pre_transition(self, callback: callable) -> None:
        """Setze Callback der VOR dem State-Wechsel aufgerufen wird (fuer Snapshot)."""
        self._on_pre_transition = callback

    @property
    def transition_progress(self) -> float:
        """Aktueller Transition-Fortschritt (0.0-1.0)."""
        return self._transition_progress

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

    def _apply_state_instant(self, queue: Queue,
                             keep_videos_alive: Optional[Set[str]] = None) -> None:
        """Wendet State sofort an.

        Args:
            keep_videos_alive: Set von media_ids deren Decoder nicht gestoppt/
                               geseeked werden sollen (fuer Crossfade mit laufendem Video).
        """
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

                if keep_videos_alive and mls.media_id in keep_videos_alive:
                    # Transition: altes Video weiterlaufen lassen
                    # Nur neue Videos starten, kein Seek/Pause
                    if mls.playing and not decoder.playing:
                        decoder.start()
                        if mls.media_id in self.video_player.audio_players:
                            player, _ = self.video_player.audio_players[mls.media_id]
                            player.play()
                    continue

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
        """Startet eine animierte Transition mit Output-Level Crossfade."""
        # 1. Audio-From-State capturen (Volumes vor dem Wechsel)
        self._transition_from_audio.clear()
        for media_id, volume in self.video_player._volumes.items():
            self._transition_from_audio[media_id] = volume

        # 2. Laufende Videos tracken (muessen fuer Crossfade weiterlaufen)
        self._transition_keep_alive.clear()
        for ml in self.project.media_layers:
            if ml.media_id and ml.media_id in self.video_player.decoders:
                if self.video_player.decoders[ml.media_id].playing:
                    self._transition_keep_alive.add(ml.media_id)

        # 3. Pre-Transition Callback (Renderer captured "from" state)
        if self._on_pre_transition:
            self._on_pre_transition()

        # 4. State sofort anwenden ABER alte Videos weiterlaufen lassen
        self._apply_state_instant(queue, keep_videos_alive=self._transition_keep_alive)

        # 5. Timer-Variablen setzen
        self._transition_to_state = queue
        self._transition_start_time = time.time()
        self._active_transition = queue.transition
        self._transition_progress = 0.0

    def update_transition(self) -> bool:
        """Update Transition (aufrufen im Timer). Returns True wenn aktiv."""
        if not self._active_transition:
            return False

        elapsed = (time.time() - self._transition_start_time) * 1000
        duration = max(1, self._active_transition.duration_ms)
        raw_progress = min(1.0, elapsed / duration)
        progress = self._apply_easing(raw_progress, self._active_transition.easing)

        self._transition_progress = progress

        # Audio-Volume interpolieren bei "dissolve"
        if self._active_transition.mode == "dissolve" and self._transition_to_state:
            for to_mls in self._transition_to_state.media_layer_states:
                if not to_mls.media_id:
                    continue
                from_vol = self._transition_from_audio.get(to_mls.media_id, 0.0)
                to_vol = to_mls.volume
                new_vol = self._lerp(from_vol, to_vol, progress)
                self.video_player._volumes[to_mls.media_id] = new_vol

                if to_mls.media_id in self.video_player.audio_players:
                    _, audio_output = self.video_player.audio_players[to_mls.media_id]
                    audio_output.setVolume(new_vol)

        # Callback fuer UI Update
        if self._on_transition_update:
            self._on_transition_update()

        if raw_progress >= 1.0:
            # Transition fertig - aufgeschobene Video-States anwenden
            self._apply_deferred_video_states()
            self._transition_progress = 0.0
            self._active_transition = None
            self._transition_to_state = None
            self._transition_from_audio.clear()
            self._transition_keep_alive.clear()
            return False

        return True

    def is_transitioning(self) -> bool:
        """Gibt zurueck ob eine Transition aktiv ist."""
        return self._active_transition is not None

    def _apply_deferred_video_states(self) -> None:
        """Wende aufgeschobene Video-States an (nach Transition-Ende)."""
        if not self._transition_to_state or not self._transition_keep_alive:
            return

        for mls in self._transition_to_state.media_layer_states:
            if not mls.media_id or mls.media_id not in self._transition_keep_alive:
                continue
            if mls.media_id not in self.video_player.decoders:
                continue

            decoder = self.video_player.decoders[mls.media_id]
            decoder.seek(mls.current_time)
            decoder.looping = mls.looping
            self.video_player._volumes[mls.media_id] = mls.volume
            self.video_player._muted[mls.media_id] = mls.muted

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

    @staticmethod
    def compute_blend_alphas(t: float, overlap: float) -> tuple[float, float]:
        """Berechne Blend-Alphas fuer Crossfade mit Power-Curve.

        Returns: (from_alpha, to_alpha)
        """
        if overlap <= 0.0:
            p = 20.0
        else:
            p = math.log(overlap) / math.log(0.5)
        from_alpha = (1.0 - t) ** p
        to_alpha = t ** p
        return from_alpha, to_alpha

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
