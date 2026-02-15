# BeamerMapping

Projection Mapping Software for mapping media onto arbitrary surfaces via projectors. Built with PyQt6 and OpenCV.

## Features

- **Media Pool** — Images, Videos, Screen Capture, Cameras, Test Patterns
- **Media Layers** — Assign media sources, toggle visibility
- **Output Layers** — One per projector/monitor, multi-monitor support
- **Polygons** — Map regions from source media to output positions (many-to-many)
- **Queue System** — Save/recall state snapshots with transitions (instant, dissolve, fade)
- **Side-by-Side Editing** — Source and output canvas with drag-to-map workflow
- **Point Snapping** — Snap polygon vertices to edges/corners
- **Drag & Drop** — Move polygons between layers
- **Video Playback** — With audio sync (optimized for smooth 60 FPS output)
- **Project Files** — Save/load as JSON, auto-restore last session

## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install PyQt6 opencv-python numpy mss
```

## Usage

```bash
python run_mapper.py
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save project |
| `Ctrl+O` | Open project |
| `Ctrl+N` | New project |
| `F5` | Open output window |
| `F11` | Output fullscreen |
| `Delete` | Delete selected element |
| `Enter` | Rename selected element |
| `M` | Toggle edit mode (output window) |
| `F` | Toggle fullscreen (output window) |
| `Q` | Close output window |

## Architecture

```
Media Layer ──► Polygon ──► Output Layer
(Source)        (Mapping)    (Projector)
```

Polygons connect media sources to output targets. Each polygon defines a source region (where to read from the media) and an output region (where to project). Multiple polygons can share the same media or output layer.

## Performance

The application is optimized for smooth real-time video mapping:

- **60 FPS Output** — Projector output updates at 60 Hz for smooth video playback
- **Tight Audio Sync** — Audio/video synchronization checked every 100ms with 50ms drift threshold
- **Efficient Rendering** — Buffer reuse and optimized compositing pipeline
- **Low Latency** — Live sources (cameras, screen capture) with minimal delay

## License

MIT
