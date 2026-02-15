# Feature-Vergleich: BeamerMapping vs. MadMapper

Basierend auf MadMapper's "Introduction to the User Interface" Dokumentation.

---

## Bereits vorhanden

| Feature | Modul |
|---------|-------|
| Media Pool (Images, Videos, Cameras, Screen Capture, Test Patterns) | `main_window.py` |
| Input/Output Side-by-Side Views | `canvas.py` |
| Quad-Surfaces (4-Punkt Polygone) | `models.py`, `canvas.py` |
| Punkt-Manipulation (Drag, Move, Rotate, Scale) | `canvas.py` |
| View-Modes (Source / Output / Both) | `main_window.py` |
| Snapping (Ecke-zu-Ecke, Ecke-zu-Kante) | `canvas.py` |
| Zoom & Pan | `canvas.py` |
| Multiple Projectors (Output Layers + Monitor-Auswahl) | `output_window.py` |
| Scenes/Cues System (Queue-System mit Crossfade-Transitions) | `queue_manager.py`, `queue_grid.py` |
| Freeze & Blackout (mit konfigurierbarem Fade) | `main_window.py`, `output_window.py` |
| Video Playback mit Audio | `video_player.py` |
| FPS Counter | `canvas.py`, `output_window.py` |
| GPU-Rendering (OpenGL Backend) | `gl_renderer.py`, `transform.py` |
| Drag & Drop (Polygone zwischen Layern verschieben) | `main_window.py` |
| Projekt Save/Load (JSON) | `models.py`, `main_window.py` |

---

## Fehlend — Hoch (Kern-Mapping-Features)

### Undo/Redo

MadMapper hat Undo/Redo Buttons in der Toolbar. Essentiell fuer produktives Arbeiten — ein falscher Klick kann sonst Polygon-Positionen zerstoeren.

**Umsetzung:** Command-Pattern mit QUndoStack (PyQt6 built-in). Jede Punkt-Aenderung, Layer-Operation und Polygon-Erstellung als QUndoCommand kapseln.

### Opacity per Surface

Transparenz (0–100%) pro Polygon/Surface. In MadMapper Teil des Surface Inspectors.

**Umsetzung:** `opacity: float` Attribut auf `Polygon` Model. Im Compositing als Alpha-Faktor anwenden.

### Blend Modes

Additiv, Multiply, Screen etc. pro Surface. MadMapper bietet dies im Surface Inspector.

**Umsetzung:** Blend-Mode Attribut auf Polygon. Im OpenCV-Backend als numpy-Operation, im OpenGL-Backend als Fragment-Shader Variante.

### Soft-Edge / Feathering

Weiche Kanten an Polygon-Raendern. Kernfeature fuer Edge-Blending bei Multi-Projektor-Setups — ohne das sind harte Kanten zwischen Projektoren sichtbar.

**Umsetzung:** Gradient-Maske entlang der Polygon-Kanten generieren und als Alpha im Compositing anwenden.

### Mesh Warping

Grid-basiertes Verformen einer Surface mit beliebig vielen Control Points. Ermoeglicht Projection Mapping auf gekruemmte Oberflaechen.

**Umsetzung:** Subdivide Polygon in Grid, jeder Grid-Punkt verschiebbar. Bilineare Interpolation fuer Zwischen-Punkte.

### Bezier Mesh Warping

Bezier-Kurven statt linearem Grid fuer noch komplexere Oberflaechen.

**Umsetzung:** Aufbauend auf Mesh Warping, Bezier-Kontrollpunkte pro Kante.

### Masken (Alpha Mask)

Eigenstaendige Masken-Surfaces die Teile der Projektion ausblenden. In MadMapper als eigener Surface-Typ.

**Umsetzung:** Neuer Polygon-Typ "Mask" ohne Media-Zuordnung. Im Compositing als subtraktive Alpha-Maske.

### Surface Groups

Mehrere Surfaces gruppieren, gemeinsam verschieben/skalieren/rotieren. In MadMapper per Drag in Gruppe oder Shift+Klick auf Group-Icon.

**Umsetzung:** `PolygonGroup` Model mit children-Liste. Transform-Operationen auf Gruppe propagieren zu allen Kindern.

### Lock Surface

Sperren einzelner Surfaces gegen versehentliches Editieren. In MadMapper per Lock-Icon in der Surface-Liste.

**Umsetzung:** `locked: bool` Attribut auf Polygon. Canvas ignoriert Interaktion mit gesperrten Polygonen.

---

## Fehlend — Mittel (Workflow & Produktivitaet)

### Media Inspector

Detail-Panel mit Preview, Info (Resolution, Codec, Duration, Framerate) und Parametern pro Medium. MadMapper zeigt dies unterhalb des Media Bins.

### Media Thumbnails

Thumbnail-Ansicht im Media Pool statt reiner Textliste. MadMapper erlaubt Umschalten zwischen Thumbnail- und List-View mit konfigurierbarer Thumbnail-Groesse.

### Weitere Surface-Typen

MadMapper unterstuetzt neben Quads auch:
- **Linien** — Klick-fuer-Klick Erstellung, Enter zum Abschliessen
- **Dreiecke** — 3-Punkt Surfaces
- **Kreise** — 4 Handle-Punkte + Center fuer Perspektive

### View Only Selected

Nur ausgewaehlte Surfaces im View anzeigen, alle anderen ausblenden. Nuetzlich bei komplexen Projekten mit vielen ueberlappenden Polygonen.

### Zoom to Fit Selection

Zoom auf ausgewaehlte Surfaces statt nur globaler Reset. MadMapper hat separates "Zoom to fit selected" neben "Fit to window".

### Background Image per Projector

Hintergrundbild im Output-View zur Orientierung beim Mapping (wird nicht projiziert). Hilfreich z.B. fuer ein Foto der Buehne.

### Output Mask per Projector

PNG-Maske pro Projektor die im Output angewendet wird (wird projiziert). Nuetzlich zum Ausblenden von Bereichen.

### Test Pattern per Projector

Test-Pattern direkt pro Output aktivierbar, nicht als Media im Pool.

### Surface FX / Effects

Per-Surface Effekte wie Color-Correction, Hue/Saturation, Brightness/Contrast. MadMapper bietet eine FX-Chain im Surface Inspector.

---

## Fehlend — Niedrig (Erweiterte/Spezial-Features)

### Syphon/Spout/NDI

Texture-Sharing zwischen Applikationen. Input: andere Apps als Live-Quelle. Output: MadMapper-Output an andere Apps streamen.

### Materials / GLSL Shaders

Generative Shader als Media-Typ. MadMapper hat einen integrierten Code-Editor fuer GLSL (bis Version 4.1 Mac / 4.5 Windows). Materials werden direkt auf der Output-Destination gerendert.

### ISF (Interactive Shader Format)

GLSL Fragment-Shader im ISF-Format (https://isf.video). Community-Standard fuer austauschbare visuelle Effekte.

### Image Folder Watchdog

Ordner als Media-Quelle mit automatischem Update wenn Bilder hinzugefuegt/geaendert werden.

### 3D Surface (.OBJ Import)

Import und Kalibrierung von 3D-Objekten im .OBJ Format. Eigenstaendiger Surface-Typ mit Wireframe-Ansicht, Lighting und UV-Editor.

### Control Mapping (MIDI/OSC/Keyboard)

Beliebige Parameter an MIDI-Controller, OSC-Nachrichten oder Keyboard binden. MadMapper hat ein Learn-System: "Learn" aktivieren, Parameter anklicken, Controller bedienen.

### DMX / ArtNet / Light Fixtures

Licht-Steuerung mit DMX-Fixtures, Universen, Dip-Switch-Konfiguration. Separater Anwendungsbereich (Light Mapping).

### Module System

Erweiterbare Module: Audio Player, Calendar Scheduler, Cue Scheduler, DMX Router, MIDI Out, OSC Out, Oscillator, MiniMad Controller.

### Master Controls

Globale Master-Regler: Master Opacity, Video Master, DMX Master, Audio Master. Master Speed mit BPM-Sync (Ableton Link, Audio-Analyse).

---

## Empfohlene Reihenfolge

| Prioritaet | Feature | Aufwand | Impact |
|------------|---------|---------|--------|
| 1 | Undo/Redo | Mittel | Sehr hoch — verhindert Datenverlust |
| 2 | Opacity per Surface | Niedrig | Hoch — einfach, grosser kreativer Effekt |
| 3 | Lock Surface | Niedrig | Mittel — verhindert Unfaelle bei komplexen Projekten |
| 4 | Surface Groups | Mittel | Hoch — essentiell fuer groessere Projekte |
| 5 | Soft-Edge / Feathering | Mittel | Sehr hoch — Kernfeature fuer Multi-Projektor |
| 6 | Mesh Warping | Hoch | Sehr hoch — ermoeglicht komplexe Oberflaechen |
| 7 | Blend Modes | Mittel | Mittel — kreative Moeglichkeiten |
| 8 | Masken | Mittel | Mittel — wichtig fuer saubere Projektionen |
| 9 | Media Thumbnails | Niedrig | Mittel — bessere UX |
| 10 | Background Image per Projector | Niedrig | Mittel — hilft beim Mapping-Setup |
