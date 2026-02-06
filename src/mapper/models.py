"""Datenmodelle fuer Projection Mapper."""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


# === Queue/Cue System Data Structures ===

@dataclass
class MediaLayerState:
    """Playback-State eines Media Layers fuer Queue-Snapshot."""
    media_layer_id: str
    media_id: Optional[str] = None
    visible: bool = True
    # Playback (nur fuer Videos)
    current_time: float = 0.0
    playing: bool = False
    looping: bool = True
    # Audio
    volume: float = 0.7
    muted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'media_layer_id': self.media_layer_id,
            'media_id': self.media_id,
            'visible': self.visible,
            'current_time': self.current_time,
            'playing': self.playing,
            'looping': self.looping,
            'volume': self.volume,
            'muted': self.muted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaLayerState':
        return cls(
            media_layer_id=data.get('media_layer_id', ''),
            media_id=data.get('media_id'),
            visible=data.get('visible', True),
            current_time=data.get('current_time', 0.0),
            playing=data.get('playing', False),
            looping=data.get('looping', True),
            volume=data.get('volume', 0.7),
            muted=data.get('muted', False),
        )


@dataclass
class PolygonState:
    """Transform-State eines Polygons fuer Queue-Snapshot."""
    polygon_id: str
    media_layer_id: Optional[str] = None
    output_layer_id: Optional[str] = None
    source_points: List[List[float]] = field(default_factory=lambda: [
        [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]
    ])
    output_points: List[List[float]] = field(default_factory=lambda: [
        [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'polygon_id': self.polygon_id,
            'media_layer_id': self.media_layer_id,
            'output_layer_id': self.output_layer_id,
            'source_points': self.source_points,
            'output_points': self.output_points,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PolygonState':
        return cls(
            polygon_id=data.get('polygon_id', ''),
            media_layer_id=data.get('media_layer_id'),
            output_layer_id=data.get('output_layer_id'),
            source_points=data.get('source_points', [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]),
            output_points=data.get('output_points', [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]),
        )


@dataclass
class QueueTransition:
    """Uebergangs-Konfiguration fuer eine Queue."""
    mode: str = "instant"  # "instant", "dissolve", "fade"
    duration_ms: int = 500
    easing: str = "linear"  # "linear", "ease-in", "ease-out", "ease-in-out"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode,
            'duration_ms': self.duration_ms,
            'easing': self.easing,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueTransition':
        return cls(
            mode=data.get('mode', 'instant'),
            duration_ms=data.get('duration_ms', 500),
            easing=data.get('easing', 'linear'),
        )


@dataclass
class Queue:
    """Eine einzelne Queue/Cue mit State-Snapshot."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Queue"
    index: int = 0

    # State Snapshot
    media_layer_states: List[MediaLayerState] = field(default_factory=list)
    polygon_states: List[PolygonState] = field(default_factory=list)

    # Transition
    transition: QueueTransition = field(default_factory=QueueTransition)

    # Metadaten
    created_at: str = ""
    thumbnail: Optional[str] = None  # Base64 encoded preview (optional)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'index': self.index,
            'media_layer_states': [mls.to_dict() for mls in self.media_layer_states],
            'polygon_states': [ps.to_dict() for ps in self.polygon_states],
            'transition': self.transition.to_dict(),
            'created_at': self.created_at,
            'thumbnail': self.thumbnail,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Queue':
        queue = cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Queue'),
            index=data.get('index', 0),
            created_at=data.get('created_at', ''),
            thumbnail=data.get('thumbnail'),
        )
        queue.media_layer_states = [
            MediaLayerState.from_dict(mls) for mls in data.get('media_layer_states', [])
        ]
        queue.polygon_states = [
            PolygonState.from_dict(ps) for ps in data.get('polygon_states', [])
        ]
        if 'transition' in data:
            queue.transition = QueueTransition.from_dict(data['transition'])
        return queue


@dataclass
class Polygon:
    """Vermittler zwischen Media Layer und Output Layer.

    Definiert welcher Bereich eines Media Layers wohin auf einem Output Layer
    projiziert wird.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Polygon"
    media_layer_id: Optional[str] = None   # VON welchem Media Layer
    output_layer_id: Optional[str] = None  # AUF welchen Output Layer

    # Normalisierte Koordinaten (0.0 - 1.0)
    source_points: List[List[float]] = field(default_factory=lambda: [
        [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]
    ])
    output_points: List[List[float]] = field(default_factory=lambda: [
        [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'media_layer_id': self.media_layer_id,
            'output_layer_id': self.output_layer_id,
            'source_points': self.source_points,
            'output_points': self.output_points,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Polygon:
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Polygon'),
            media_layer_id=data.get('media_layer_id') or data.get('layer_id'),  # Backward compat
            output_layer_id=data.get('output_layer_id'),
            source_points=data.get('source_points', [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]),
            output_points=data.get('output_points', [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]),
        )

    def copy(self) -> Polygon:
        """Erstelle eine Kopie des Polygons."""
        return Polygon(
            id=str(uuid.uuid4()),
            name=f"{self.name} (Copy)",
            media_layer_id=self.media_layer_id,
            output_layer_id=self.output_layer_id,
            source_points=[p.copy() for p in self.source_points],
            output_points=[p.copy() for p in self.output_points],
        )


@dataclass
class MediaLayer:
    """Quelle - hat ein Medium (Video/Bild/etc) zugewiesen.

    Kann von beliebig vielen Polygonen "angezapft" werden.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Media 1"
    media_id: Optional[str] = None  # Verweis auf MediaItem im Pool
    visible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'media_id': self.media_id,
            'visible': self.visible,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaLayer':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Media 1'),
            media_id=data.get('media_id'),
            visible=data.get('visible', True),
        )


@dataclass
class OutputLayer:
    """Ziel - entspricht einem physischen Beamer/Monitor.

    Kann Inhalte von beliebig vielen Polygonen empfangen.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Output 1"
    monitor_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'monitor_index': self.monitor_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OutputLayer':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Output 1'),
            monitor_index=data.get('monitor_index', 0),
        )


@dataclass
class MediaItem:
    """Ein Media-Element (Bild oder Video) im Pool."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    name: str = ""
    media_type: str = "image"  # "image", "video", "screen", "camera", "test"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'path': self.path,
            'name': self.name,
            'media_type': self.media_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MediaItem:
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            path=data.get('path', ''),
            name=data.get('name', ''),
            media_type=data.get('media_type', 'image'),
        )


@dataclass
class Project:
    """Ein Projekt mit Media Layers, Output Layers, Polygonen und Media Pool.

    Neue Architektur (v4.1):
    - media_layers: Quellen (haben Media zugewiesen)
    - output_layers: Beamer/Monitore
    - polygons: Verbindungen zwischen Media und Output
    - media: Pool aller Medien
    - queues: Queue/Cue-System fuer State-Snapshots
    - session: Gespeicherter UI-Zustand
    """

    version: str = "4.1"
    name: str = "Neues Projekt"
    media_layers: List[MediaLayer] = field(default_factory=list)
    output_layers: List[OutputLayer] = field(default_factory=list)
    polygons: List[Polygon] = field(default_factory=list)
    media: List[MediaItem] = field(default_factory=list)
    queues: List[Queue] = field(default_factory=list)

    # Session State (wird mitgespeichert)
    selected_polygon_id: Optional[str] = None
    selected_media_layer_id: Optional[str] = None
    selected_output_layer_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'version': self.version,
            'name': self.name,
            'media_layers': [ml.to_dict() for ml in self.media_layers],
            'output_layers': [ol.to_dict() for ol in self.output_layers],
            'polygons': [p.to_dict() for p in self.polygons],
            'media': [m.to_dict() for m in self.media],
            'queues': [q.to_dict() for q in self.queues],
            # Session State
            'selected_polygon_id': self.selected_polygon_id,
            'selected_media_layer_id': self.selected_media_layer_id,
            'selected_output_layer_id': self.selected_output_layer_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Project:
        version = data.get('version', '3.0')

        # Migration von alten Versionen
        if version < '4.0':
            return cls._migrate_from_v3(data)

        project = cls(
            version='4.1',  # Upgrade to latest version
            name=data.get('name', 'Neues Projekt'),
        )
        project.media_layers = [MediaLayer.from_dict(ml) for ml in data.get('media_layers', [])]
        project.output_layers = [OutputLayer.from_dict(ol) for ol in data.get('output_layers', [])]
        project.polygons = [Polygon.from_dict(p) for p in data.get('polygons', [])]
        project.media = [MediaItem.from_dict(m) for m in data.get('media', [])]
        project.queues = [Queue.from_dict(q) for q in data.get('queues', [])]

        # Session State wiederherstellen
        project.selected_polygon_id = data.get('selected_polygon_id')
        project.selected_media_layer_id = data.get('selected_media_layer_id')
        project.selected_output_layer_id = data.get('selected_output_layer_id')

        return project

    @classmethod
    def _migrate_from_v3(cls, data: Dict[str, Any]) -> Project:
        """Migriere von v3.0 Projektformat zu v4.0."""
        project = cls(
            version='4.0',
            name=data.get('name', 'Migriertes Projekt'),
        )

        # Media Pool uebernehmen
        project.media = [MediaItem.from_dict(m) for m in data.get('media', [])]

        # Alte "layers" (MediaLayer mit eingebetteten Polygonen) -> Neue MediaLayers
        old_layers = data.get('layers', [])
        for old_layer_data in old_layers:
            media_layer = MediaLayer(
                id=old_layer_data.get('id', str(uuid.uuid4())),
                name=old_layer_data.get('name', 'Media Layer'),
                media_id=old_layer_data.get('media_id'),
                visible=old_layer_data.get('visible', True),
            )
            project.media_layers.append(media_layer)

            # Polygone aus altem Layer extrahieren
            for old_poly_data in old_layer_data.get('polygons', []):
                polygon = Polygon.from_dict(old_poly_data)
                polygon.media_layer_id = media_layer.id
                # output_layer_id wird spaeter gesetzt wenn wir Outputs haben
                project.polygons.append(polygon)

        # Alte "outputs" -> Neue OutputLayers
        old_outputs = data.get('outputs', [])
        default_output_id = None

        for old_output_data in old_outputs:
            output_layer = OutputLayer(
                id=old_output_data.get('id', str(uuid.uuid4())),
                name=old_output_data.get('name', 'Output'),
                monitor_index=old_output_data.get('monitor_index', 0),
            )
            project.output_layers.append(output_layer)

            if default_output_id is None:
                default_output_id = output_layer.id

        # Falls kein Output existiert, einen erstellen
        if not project.output_layers:
            default_output = OutputLayer(name="Output 1")
            project.output_layers.append(default_output)
            default_output_id = default_output.id

        # Allen Polygonen ohne output_layer_id den ersten Output zuweisen
        for polygon in project.polygons:
            if polygon.output_layer_id is None:
                polygon.output_layer_id = default_output_id

        return project

    def save(self, filepath: str) -> None:
        """Speichere das Projekt als JSON."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> Project:
        """Lade ein Projekt aus einer JSON-Datei."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    # === Media Layer Management ===

    def add_media_layer(self, name: Optional[str] = None, media_id: Optional[str] = None) -> MediaLayer:
        """Fuege einen neuen Media Layer hinzu."""
        layer = MediaLayer(
            name=name or f"Media {len(self.media_layers) + 1}",
            media_id=media_id
        )
        self.media_layers.append(layer)
        return layer

    def remove_media_layer(self, layer: MediaLayer) -> None:
        """Entferne einen Media Layer und alle seine Polygone."""
        if layer in self.media_layers:
            self.media_layers.remove(layer)
            # Zugehoerige Polygone entfernen
            self.polygons = [p for p in self.polygons if p.media_layer_id != layer.id]

    def get_media_layer_by_id(self, layer_id: str) -> Optional[MediaLayer]:
        """Finde einen Media Layer anhand seiner ID."""
        for layer in self.media_layers:
            if layer.id == layer_id:
                return layer
        return None

    def get_polygons_for_media_layer(self, layer_id: str) -> List[Polygon]:
        """Hole alle Polygone die zu einem Media Layer gehoeren."""
        return [p for p in self.polygons if p.media_layer_id == layer_id]

    # === Output Layer Management ===

    def add_output_layer(self, name: Optional[str] = None, monitor_index: int = 0) -> OutputLayer:
        """Fuege einen neuen Output Layer hinzu."""
        layer = OutputLayer(
            name=name or f"Output {len(self.output_layers) + 1}",
            monitor_index=monitor_index
        )
        self.output_layers.append(layer)
        return layer

    def remove_output_layer(self, layer: OutputLayer) -> None:
        """Entferne einen Output Layer. Polygone werden nicht geloescht."""
        if layer in self.output_layers:
            self.output_layers.remove(layer)
            # Polygone behalten, aber output_layer_id auf None setzen
            for poly in self.polygons:
                if poly.output_layer_id == layer.id:
                    poly.output_layer_id = None

    def get_output_layer_by_id(self, layer_id: str) -> Optional[OutputLayer]:
        """Finde einen Output Layer anhand seiner ID."""
        for layer in self.output_layers:
            if layer.id == layer_id:
                return layer
        return None

    def get_polygons_for_output_layer(self, layer_id: str) -> List[Polygon]:
        """Hole alle Polygone die auf einem Output Layer angezeigt werden."""
        return [p for p in self.polygons if p.output_layer_id == layer_id]

    # === Polygon Management ===

    def add_polygon(
        self,
        name: Optional[str] = None,
        media_layer_id: Optional[str] = None,
        output_layer_id: Optional[str] = None
    ) -> Polygon:
        """Fuege ein neues Polygon hinzu."""
        polygon = Polygon(
            name=name or f"Polygon {len(self.polygons) + 1}",
            media_layer_id=media_layer_id,
            output_layer_id=output_layer_id
        )
        self.polygons.append(polygon)
        return polygon

    def remove_polygon(self, polygon: Polygon) -> None:
        """Entferne ein Polygon."""
        if polygon in self.polygons:
            self.polygons.remove(polygon)

    def get_polygon_by_id(self, polygon_id: str) -> Optional[Polygon]:
        """Finde ein Polygon anhand seiner ID."""
        for poly in self.polygons:
            if poly.id == polygon_id:
                return poly
        return None

    # === Media Pool Management ===

    def add_media(self, filepath: str) -> MediaItem:
        """Fuege ein Medium hinzu."""
        path = Path(filepath)
        media = MediaItem(
            path=str(path),
            name=path.name,
            media_type="video" if path.suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv'] else "image"
        )
        self.media.append(media)
        return media

    def get_media_by_id(self, media_id: str) -> Optional[MediaItem]:
        """Finde ein Medium anhand seiner ID."""
        for m in self.media:
            if m.id == media_id:
                return m
        return None

    # === Legacy Compatibility ===
    # Diese Methoden sind fuer Rueckwaertskompatibilitaet waehrend der Migration

    @property
    def layers(self) -> List[MediaLayer]:
        """Legacy: Zugriff auf media_layers."""
        return self.media_layers

    @property
    def outputs(self) -> List[OutputLayer]:
        """Legacy: Zugriff auf output_layers."""
        return self.output_layers

    def add_layer(self, name: Optional[str] = None, media_id: Optional[str] = None) -> MediaLayer:
        """Legacy: Alias fuer add_media_layer."""
        return self.add_media_layer(name, media_id)

    def remove_layer(self, layer: MediaLayer) -> None:
        """Legacy: Alias fuer remove_media_layer."""
        self.remove_media_layer(layer)

    def get_layer_by_id(self, layer_id: str) -> Optional[MediaLayer]:
        """Legacy: Alias fuer get_media_layer_by_id."""
        return self.get_media_layer_by_id(layer_id)

    def add_output(self, name: Optional[str] = None) -> OutputLayer:
        """Legacy: Alias fuer add_output_layer."""
        return self.add_output_layer(name)

    def remove_output(self, output: OutputLayer) -> None:
        """Legacy: Alias fuer remove_output_layer."""
        self.remove_output_layer(output)

    def get_output_by_id(self, output_id: str) -> Optional[OutputLayer]:
        """Legacy: Alias fuer get_output_layer_by_id."""
        return self.get_output_layer_by_id(output_id)

    def get_all_polygons(self) -> List[Polygon]:
        """Hole alle Polygone."""
        return self.polygons

    # === Queue Management ===

    def get_queue_by_id(self, queue_id: str) -> Optional[Queue]:
        """Finde eine Queue anhand ihrer ID."""
        for queue in self.queues:
            if queue.id == queue_id:
                return queue
        return None

    def get_queue_by_index(self, index: int) -> Optional[Queue]:
        """Finde eine Queue anhand ihres Grid-Index."""
        for queue in self.queues:
            if queue.index == index:
                return queue
        return None

    def add_queue(self, queue: Queue) -> None:
        """Fuege eine Queue hinzu oder ersetze existierende am gleichen Index."""
        # Entferne existierende Queue am gleichen Index
        self.queues = [q for q in self.queues if q.index != queue.index]
        self.queues.append(queue)
        # Sortiere nach Index
        self.queues.sort(key=lambda q: q.index)

    def remove_queue(self, queue: Queue) -> None:
        """Entferne eine Queue."""
        if queue in self.queues:
            self.queues.remove(queue)
