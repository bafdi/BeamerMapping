# BeamerMapping

Projection Mapping Software for mapping media onto arbitrary surfaces via projectors. Built with PyQt6 and OpenCV/OpenGL.

## Features

- **Media Pool** — Images, Videos, Screen Capture, Cameras, Test Patterns
- **Media Layers** — Assign media sources, toggle visibility
- **Output Layers** — One per projector/monitor, multi-monitor support
- **Polygons** — Map regions from source media to output positions (many-to-many)
- **Queue System** — Save/recall state snapshots with transitions (instant, dissolve, fade)
- **Side-by-Side Editing** — Source and output canvas with drag-to-map workflow
- **Point Snapping** — Snap polygon vertices to edges/corners
- **Drag & Drop** — Move polygons between layers
- **Video Playback** — With audio sync
- **Project Files** — Save/load as JSON, auto-restore last session
- **GPU Rendering** — OpenGL-backend via moderngl fuer GPU-beschleunigtes Compositing
- **Freeze & Blackout** — Output einfrieren oder schwarz schalten, mit konfigurierbarem Fade (0–5000ms)
- **FPS Counter** — Optionale FPS-Anzeige im Output-Canvas und Output-Fenster
- **Settings Dialog** — Renderer-Auswahl (OpenCV/OpenGL), FPS-Toggle, Fade-Duration unter Preferences

## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Abhaengigkeiten

| Paket | Zweck |
|-------|-------|
| `PyQt6` | GUI-Framework |
| `opencv-python` | Bildverarbeitung, Homographie, CPU-Compositing |
| `numpy` | Array-Operationen |
| `mss` | Screen Capture |
| `moderngl` | GPU-beschleunigtes Compositing (OpenGL-Backend) |

## Usage

```bash
python run_mapper.py
```

## Renderer

BeamerMapping unterstuetzt zwei Compositing-Backends, umschaltbar unter **File > Preferences** (`Ctrl+,`):

| Backend | Beschreibung |
|---------|-------------|
| **OpenCV (CPU)** | Standard. Nutzt `cv2.warpPerspective` mit gecachten Homographie-Matrizen. Stabil und kompatibel. |
| **OpenGL (GPU)** | GPU-beschleunigt via `moderngl`. Per-Pixel Inverse-Homographie im Fragment-Shader. Deutlich schneller bei vielen/grossen Polygonen. Automatischer Fallback auf OpenCV bei Fehlern. |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save project |
| `Ctrl+O` | Open project |
| `Ctrl+N` | New project |
| `Ctrl+,` | Preferences (Renderer, FPS) |
| `F5` | Open output window |
| `F11` | Output fullscreen |
| `Delete` | Delete selected element |
| `Enter` | Rename selected element |
| `F` | Toggle freeze (with fade) |
| `Shift+F` | Toggle freeze (instant) |
| `B` | Toggle blackout (with fade) |
| `Shift+B` | Toggle blackout (instant) |
| `M` | Toggle edit mode (output window) |
| `F` | Toggle fullscreen (output window) |
| `Q` | Close output window |

## Architecture

```
Media Layer ──► Polygon ──► Output Layer
(Source)        (Mapping)    (Projector)
```

Polygons connect media sources to output targets. Each polygon defines a source region (where to read from the media) and an output region (where to project). Multiple polygons can share the same media or output layer.

The rendering pipeline dispatches compositing to the selected backend:

```
composite_polygons_fast()
  ├── OpenCV: warpPerspective + mask-based blending (CPU)
  └── OpenGL: inverse-homography fragment shader (GPU, via moderngl)
```

## License

MIT
