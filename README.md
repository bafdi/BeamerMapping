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
- **Video Playback** — With audio sync
- **Project Files** — Save/load as JSON, auto-restore last session

## Installation

### Option 1: Download Pre-built Executable (Recommended)

For most users, we recommend downloading the pre-built executables from GitHub:

1. Go to the [Actions](../../actions) tab
2. Click on the latest successful workflow run
3. Download the artifact for your platform:
   - **macOS**: `BeamerMapper-macos-app.zip` (contains `.app` bundle)
   - **Windows**: `BeamerMapper-windows-exe.zip` (contains `.exe` file)

**macOS**: Extract the zip and drag `BeamerMapper.app` to your Applications folder.  
**Windows**: Extract the zip and run `BeamerMapper.exe`.

### Option 2: Run from Source

If you want to run from source or contribute to development:

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Running the Executable
- **macOS**: Double-click `BeamerMapper.app`
- **Windows**: Double-click `BeamerMapper.exe`

### Running from Source
```bash
python run_mapper.py
```

## Building Executables

Want to build the executables yourself? See [PACKAGING.md](PACKAGING.md) for detailed instructions on:
- Building for macOS (.app via py2app)
- Building for Windows (.exe via PyInstaller)
- Using GitHub Actions for automated builds

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

## License

MIT
