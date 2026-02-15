# Projection Mapper - Architektur (v4.0)

## Neues Layer-Konzept

```
MEDIA LAYER              POLYGON                 OUTPUT LAYER
(Quelle)                 (Vermittler)            (Beamer)
┌──────────────┐         ┌─────────────┐         ┌──────────────┐
│ Media 1      │◄────────│ Polygon A   │────────►│ Beamer 1     │
│ (Video)      │         │             │         │ (Monitor 0)  │
└──────────────┘    ┌────│ Polygon B   │────┐    └──────────────┘
                    │    └─────────────┘    │
┌──────────────┐    │    ┌─────────────┐    │    ┌──────────────┐
│ Media 2      │◄───┴────│ Polygon C   │────┴───►│ Beamer 2     │
│ (Bild)       │         │             │         │ (Monitor 1)  │
└──────────────┘         └─────────────┘         └──────────────┘
```

**Many-to-Many Beziehung:**
- Ein Media Layer kann von mehreren Polygonen "angezapft" werden
- Ein Output Layer kann Inhalte von mehreren Polygonen erhalten
- Die Verbindung entsteht NUR durch Polygone

---

## Begriffe

| Begriff | Beschreibung |
|---------|--------------|
| **Media Layer** | Eine Quelle (Input). Hat ein Medium (Video, Bild, Kamera, Testpattern) zugewiesen. Kann von beliebig vielen Polygonen "angezapft" werden. |
| **Output Layer** | Ein Ziel (Output). Entspricht einem physischen Beamer/Monitor. Kann Inhalte von beliebig vielen Polygonen empfangen. |
| **Polygon** | Ein Vermittler. Definiert welcher Bereich eines Media Layers wohin auf einem Output Layer projiziert wird. Hat `source_points` (Ausschnitt aus Media) und `output_points` (Position auf Output). |
| **Media Item** | Ein Element im Media Pool (Datei, Kamera, etc). Wird einem Media Layer zugewiesen. |

---

## Beziehungen

```
MediaItem ──1:n──► MediaLayer ──m:n──► Polygon ──m:n──► OutputLayer
   │                   │                  │                 │
   │                   │                  │                 │
Datei/Kamera      Quelle mit         Verbindung        Beamer/Monitor
im Pool           sichtbar/unsichtbar zwischen beiden   mit Index
```

- **MediaItem → MediaLayer:** Ein MediaItem kann mehreren MediaLayern zugewiesen werden
- **MediaLayer → Polygon:** Ein MediaLayer kann von mehreren Polygonen referenziert werden
- **Polygon → OutputLayer:** Ein Polygon zeigt auf genau einen OutputLayer
- **OutputLayer → Polygone:** Ein OutputLayer kann mehrere Polygone darstellen

---

## Datenstruktur

### Polygon

```python
@dataclass
class Polygon:
    id: str
    name: str = "Polygon"
    media_layer_id: Optional[str] = None   # VON welchem Media Layer
    output_layer_id: Optional[str] = None  # AUF welchen Output Layer
    source_points: List[List[float]]       # Ausschnitt aus Media
    output_points: List[List[float]]       # Position auf Output
```

### MediaLayer

```python
@dataclass
class MediaLayer:
    id: str
    name: str = "Media 1"
    media_id: Optional[str] = None  # Verweis auf MediaItem im Pool
    visible: bool = True
```

### OutputLayer

```python
@dataclass
class OutputLayer:
    id: str
    name: str = "Output 1"
    monitor_index: int = 0
```

### Project

```python
@dataclass
class Project:
    version: str = "4.0"
    name: str = "Neues Projekt"
    media_layers: List[MediaLayer]    # Quellen
    output_layers: List[OutputLayer]  # Beamer
    polygons: List[Polygon]           # Verbindungen
    media: List[MediaItem]            # Media Pool
```

---

## Beispiel-Szenario

**Setup:**
- 2 Videos (Avatar, Star Wars)
- 2 Beamer (Links, Rechts)

**Konfiguration:**
```
Media Layer "Avatar"     → Polygon A → Output Layer "Beamer Links"
                        → Polygon B → Output Layer "Beamer Rechts"

Media Layer "Star Wars"  → Polygon C → Output Layer "Beamer Links"
                        → Polygon D → Output Layer "Beamer Rechts"
```

**Ergebnis:**
- Beamer Links zeigt: Avatar (Polygon A) + Star Wars (Polygon C)
- Beamer Rechts zeigt: Avatar (Polygon B) + Star Wars (Polygon D)

---

## Aktionen

| Aktion | Effekt |
|--------|--------|
| Polygon von Output A nach Output B verschieben | Inhalt verschwindet von A, erscheint auf B |
| Polygon von Media A nach Media B verschieben | Polygon zeigt nun Inhalt von B statt A |
| Media Layer unsichtbar machen | Alle zugehoerigen Polygone verschwinden auf allen Outputs |
| Output Layer oeffnen | Neues Fenster mit allen zugehoerigen Polygonen |

---

## UI-Struktur (Linkes Panel)

```
┌─────────────────────────┐
│ MEDIA LAYERS            │
├─────────────────────────┤
│ ▼ Media 1 [video.mp4]   │
│   • Polygon A -> Out 1  │
│   • Polygon B -> Out 2  │
│ ▼ Media 2 [bild.png]    │
│   • Polygon C -> Out 1  │
├─────────────────────────┤
│ [+ Media Layer]         │
├─────────────────────────┤
│ OUTPUT LAYERS           │
├─────────────────────────┤
│ ▼ Output 1 (Monitor 0)  │
│   • Polygon A <- Med 1  │
│   • Polygon C <- Med 2  │
│ ▼ Output 2 (Monitor 1)  │
│   • Polygon B <- Med 1  │
├─────────────────────────┤
│ [+ Output Layer] [Open] │
└─────────────────────────┘
```

Polygone erscheinen in **beiden** Listen:
- Unter ihrem Media Layer (Quelle)
- Unter ihrem Output Layer (Ziel)

---

## Workflow

1. **Media Layer erstellen** → Quelle definieren (Video/Bild zuweisen)
2. **Output Layer erstellen** → Beamer zuweisen (Monitor auswaehlen)
3. **Polygon erstellen** → Wird automatisch mit aktuellem Media + Output verknuepft
4. **Source Points anpassen** → Welcher Ausschnitt vom Media
5. **Output Points anpassen** → Wo auf dem Beamer

---

## Hilfsmethoden

```python
# Alle Polygone eines Media Layers
project.get_polygons_for_media_layer(layer_id)

# Alle Polygone eines Output Layers
project.get_polygons_for_output_layer(layer_id)
```

---

## Tastenkuerzel

| Taste | Funktion |
|-------|----------|
| Enter | Ausgewaehltes Element umbenennen |
| Delete | Ausgewaehltes Element loeschen |
| Ctrl+, | Einstellungen oeffnen |
| F / Shift+F | Freeze mit Fade / instant |
| B / Shift+B | Blackout mit Fade / instant |
| F5 | Ausgewaehlten Output oeffnen |
| F11 | Output Fullscreen |
| Doppelklick auf Media Layer | Sichtbarkeit umschalten |
| Doppelklick auf Output Layer | Output-Fenster oeffnen |

---

## Rendering-Pipeline

### Backend-Dispatch

`composite_polygons_fast()` in `transform.py` waehlt zur Laufzeit zwischen zwei Backends:

```
composite_polygons_fast(polygons_data, output_size, result_buffer)
    │
    ├─ renderer_backend == "opencv"
    │   └─ _composite_opencv()
    │       Pro Polygon:
    │         1. cv2.getPerspectiveTransform (gecacht per lru_cache)
    │         2. cv2.warpPerspective (INTER_LINEAR)
    │         3. cv2.fillPoly (Maske) + np.copyto (Blending)
    │
    └─ renderer_backend == "opengl"
        └─ _composite_opengl()  →  GLCompositor.composite()
            │  Bei Fehler: automatischer Fallback auf OpenCV
            │
            1. moderngl standalone context (headless, kein Fenster)
            2. Pro Polygon: Full-screen Quad rendern
            3. Fragment-Shader: inverse Homographie pro Pixel
            4. FBO auslesen → numpy array
```

### OpenGL Fragment-Shader

Der Shader fuehrt fuer jeden Output-Pixel folgende Schritte aus:

1. **Bounding-Box Test** — Frueher Ausschluss von Pixeln ausserhalb des Polygons
2. **Polygon-Containment** — Winding-Test ob Pixel im Quad liegt
3. **Inverse Homographie** — `output_pixel * H_inv → source_pixel`
4. **Textur-Sampling** — Bilineares Sampling der Quell-Textur

Vorteile gegenueber OpenCV:
- Kein separater Warp + Mask-Schritt noetig
- Massiv parallelisiert auf GPU
- Besonders schnell bei vielen/grossen Polygonen

### Einstellungen

Gesteuert ueber QSettings (persistent):

| Key | Typ | Default | Beschreibung |
|-----|-----|---------|-------------|
| `renderer_backend` | string | `"opencv"` | `"opencv"` oder `"opengl"` |
| `show_fps` | bool | `false` | FPS-Anzeige im Output-Canvas und Output-Fenster |
| `freeze_blackout_fade_ms` | int | `500` | Fade-Dauer in ms fuer Freeze/Blackout (0 = instant) |
| `last_project_path` | string | `""` | Pfad zum zuletzt geoeffneten Projekt |

### Freeze & Blackout

Freeze und Blackout unterstuetzen konfigurierbare Fade-Uebergaenge:

- **Klick / Taste (F/B):** Toggle mit Fade (konfigurierte Dauer aus Preferences)
- **Shift+Klick / Shift+Taste:** Toggle instant (sofort, kein Fade)
- **`_fb_alpha`** (0.0–1.0): Blend-Wert auf jedem OutputWindow
  - 0.0 = Live-Output, 1.0 = voll eingefroren/schwarz
  - Fade-Animation wird vom 60Hz Transition-Timer gesteuert
- **Gegenseitige Exklusivitaet:** Aktivierung von Freeze stoppt Blackout und umgekehrt
- **Canvas-Border:** Output-Canvas zeigt farbigen Rahmen (cyan=Freeze, rot=Blackout) mit Opacity proportional zum Alpha
- **Blending in `_render_all_polygons()`:**
  - Blackout: `composite * (1 - alpha)` (Richtung schwarz)
  - Freeze: `cv2.addWeighted(live, 1-alpha, frozen, alpha, 0)` (Blend mit eingefrorenem Frame)

### FPS-Counter

- Zaehlt Paint-Events pro Sekunde (1s Fenster, `time.monotonic()`)
- Anzeige oben rechts mit halbtransparentem Hintergrund
- Verfuegbar im Output-Canvas (`canvas.py`) und im Output-Fenster (`output_window.py`)
- Aktivierung ueber File > Preferences

---

## Dateistruktur

```
src/mapper/
├── __init__.py
├── main_window.py       # Hauptfenster, Menues, Settings-Integration
├── canvas.py            # PolygonCanvas (Source/Output Bearbeitung)
├── output_window.py     # Frameless Output-Fenster (Projektor)
├── transform.py         # Homographie, Compositing, Backend-Dispatch
├── gl_renderer.py       # GPU-Compositing via moderngl
├── settings_dialog.py   # Einstellungs-Dialog (Renderer, FPS)
├── models.py            # Datenmodelle (Project, Polygon, Layer)
├── queue_manager.py     # Queue/Cue-System
├── queue_grid.py        # Queue-Grid Widget
├── video_player.py      # Video-Playback mit Audio
├── live_sources.py      # Kamera- und Screen-Capture
└── test_patterns.py     # Test-Pattern Generator
```

---

## Migration von v3.0

Alte Projekte (v3.0) werden automatisch migriert:

1. Alte "layers" (MediaLayer mit eingebetteten Polygonen) → Neue MediaLayers (ohne Polygone)
2. Polygone werden extrahiert und erhalten `media_layer_id`
3. Alte "outputs" → Neue OutputLayers
4. Allen Polygonen wird der erste OutputLayer zugewiesen
