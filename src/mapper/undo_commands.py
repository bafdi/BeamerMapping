"""QUndoCommand-Subklassen fuer Undo/Redo."""

from typing import List, Tuple, Callable, Optional, Any

from PyQt6.QtGui import QUndoCommand

from .models import Polygon, MediaLayer, Project


class PointsMoveCommand(QUndoCommand):
    """Einzelnes Polygon, ein Drag-Vorgang (Press->Release)."""

    def __init__(self, polygon: Polygon, mode: str,
                 old_points: List[List[float]], new_points: List[List[float]],
                 refresh_callback: Callable, description: str = "Move points"):
        super().__init__(description)
        self.polygon = polygon
        self.mode = mode
        self.old_points = old_points
        self.new_points = new_points
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        if self.mode == "source":
            self.polygon.source_points = [p.copy() for p in self.new_points]
        else:
            self.polygon.output_points = [p.copy() for p in self.new_points]
        self.refresh_cb()

    def undo(self) -> None:
        if self.mode == "source":
            self.polygon.source_points = [p.copy() for p in self.old_points]
        else:
            self.polygon.output_points = [p.copy() for p in self.old_points]
        self.refresh_cb()


class MultiPointsMoveCommand(QUndoCommand):
    """Mehrere Polygone gleichzeitig bewegt/rotiert/skaliert."""

    def __init__(self, entries: List[Tuple[Polygon, str, List[List[float]], List[List[float]]]],
                 refresh_callback: Callable, description: str = "Move polygons"):
        super().__init__(description)
        self.entries = entries  # [(polygon, mode, old_points, new_points), ...]
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        for polygon, mode, _old, new in self.entries:
            if mode == "source":
                polygon.source_points = [p.copy() for p in new]
            else:
                polygon.output_points = [p.copy() for p in new]
        self.refresh_cb()

    def undo(self) -> None:
        for polygon, mode, old, _new in self.entries:
            if mode == "source":
                polygon.source_points = [p.copy() for p in old]
            else:
                polygon.output_points = [p.copy() for p in old]
        self.refresh_cb()


class PolygonPropertyCommand(QUndoCommand):
    """Generisch fuer media_layer_id oder output_layer_id Aenderungen."""

    def __init__(self, polygon: Polygon, attr_name: str,
                 old_value: Any, new_value: Any,
                 refresh_callback: Callable, description: str = "Change property"):
        super().__init__(description)
        self.polygon = polygon
        self.attr_name = attr_name
        self.old_value = old_value
        self.new_value = new_value
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        setattr(self.polygon, self.attr_name, self.new_value)
        self.refresh_cb()

    def undo(self) -> None:
        setattr(self.polygon, self.attr_name, self.old_value)
        self.refresh_cb()


class MultiPolygonPropertyCommand(QUndoCommand):
    """Mehrere Polygone: z.B. alle auf eine Media-Ebene zuweisen."""

    def __init__(self, entries: List[Tuple[Polygon, str, Any, Any]],
                 refresh_callback: Callable, description: str = "Change properties"):
        super().__init__(description)
        self.entries = entries  # [(polygon, attr_name, old_value, new_value), ...]
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        for polygon, attr_name, _old, new in self.entries:
            setattr(polygon, attr_name, new)
        self.refresh_cb()

    def undo(self) -> None:
        for polygon, attr_name, old, _new in self.entries:
            setattr(polygon, attr_name, old)
        self.refresh_cb()


class AddPolygonCommand(QUndoCommand):
    """Polygon hinzufuegen."""

    def __init__(self, project: Project, polygon: Polygon,
                 refresh_callback: Callable, description: str = "Add polygon"):
        super().__init__(description)
        self.project = project
        self.polygon = polygon
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        if self.polygon not in self.project.polygons:
            self.project.polygons.append(self.polygon)
        self.refresh_cb()

    def undo(self) -> None:
        if self.polygon in self.project.polygons:
            self.project.polygons.remove(self.polygon)
        self.refresh_cb()


class RemovePolygonCommand(QUndoCommand):
    """Polygon entfernen."""

    def __init__(self, project: Project, polygon: Polygon, index: int,
                 refresh_callback: Callable, description: str = "Remove polygon"):
        super().__init__(description)
        self.project = project
        self.polygon = polygon
        self.index = index
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        if self.polygon in self.project.polygons:
            self.project.polygons.remove(self.polygon)
        self.refresh_cb()

    def undo(self) -> None:
        if self.polygon not in self.project.polygons:
            self.project.polygons.insert(self.index, self.polygon)
        self.refresh_cb()


class ReorderPolygonCommand(QUndoCommand):
    """Fuer Z-Order (move front/back)."""

    def __init__(self, project: Project, old_index: int, new_index: int,
                 refresh_callback: Callable, description: str = "Reorder polygon"):
        super().__init__(description)
        self.project = project
        self.old_index = old_index
        self.new_index = new_index
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        polygons = self.project.polygons
        poly = polygons.pop(self.old_index)
        polygons.insert(self.new_index, poly)
        self.refresh_cb()

    def undo(self) -> None:
        polygons = self.project.polygons
        poly = polygons.pop(self.new_index)
        polygons.insert(self.old_index, poly)
        self.refresh_cb()


class MediaLayerMediaCommand(QUndoCommand):
    """Medium auf Layer ersetzen."""

    def __init__(self, media_layer: MediaLayer,
                 old_media_id: Optional[str], new_media_id: Optional[str],
                 refresh_callback: Callable, description: str = "Change layer media"):
        super().__init__(description)
        self.media_layer = media_layer
        self.old_media_id = old_media_id
        self.new_media_id = new_media_id
        self.refresh_cb = refresh_callback

    def redo(self) -> None:
        self.media_layer.media_id = self.new_media_id
        self.refresh_cb()

    def undo(self) -> None:
        self.media_layer.media_id = self.old_media_id
        self.refresh_cb()
