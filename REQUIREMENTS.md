# Projection Mapper - Requirements v3

## Architektur

### Hierarchie (NEU)
```
Projekt
  +-- Media Pool
  |     +-- Bild 1
  |     +-- Video 1
  |     +-- Live: Screen Capture
  |     +-- Live: Kamera 1
  |     +-- Test: Grid
  |     +-- Test: Edges
  |
  +-- Media Layer 1 (verwendet Bild 1)
  |     +-- Polygon A
  |     +-- Rechteck B
  |     +-- Polygon C (kann A ueberlappen)
  |
  +-- Media Layer 2 (verwendet Video 1)
  |     +-- Polygon D
  |
  +-- Output 1 (Projektor 1)
  |     zeigt: alle Layer kombiniert
  |
  +-- Output 2 (Projektor 2)
        zeigt: alle Layer kombiniert
```

### Konzepte

**Media Pool:**
- Bilder (PNG, JPG)
- Videos (MP4, MOV)
- Live-Quellen: Screen Capture, Kameras
- Test-Patterns: Grid, Edges, Farben

**Media Layer:**
- Jedes Medium aus dem Pool kann eine Media Layer haben
- Pro Layer: mehrere Shapes (Polygone, Rechtecke)
- Shapes koennen sich ueberlappen
- Shapes koennen aneinander snappen

**Shapes:**
- Polygon (N-Eck, beliebig viele Punkte)
- Rechteck (4 Punkte, rechte Winkel)
- Jeder Shape hat Source-Punkte und Output-Punkte
- Gesamten Shape verschieben moeglich
- Fuer Output: Seitenlaengen/Winkel angeben moeglich

**Output:**
- Separates Fenster pro Projektor
- KEIN Rahmen, KEIN Text - komplett clean
- Zeigt alle Layer kombiniert

---

## UI-Layout

```
+------------------------------------------------------------------+
|  File  Edit  View  Output                                         |
+------------------------------------------------------------------+
|          |                              |                         |
| LAYERS   |   [Source] [Output] [Both]   |      MEDIA POOL         |
| & SHAPES |                              |                         |
|          | +----------+ +----------+    | [+ Import Image]        |
| Layer 1  | |  MEDIA   | |  OUTPUT  |    | [+ Import Video]        |
|  ShapeA  | |  LAYER   | |  LAYER   |    | [+ Live Source]         |
|  ShapeB  | |          | |          |    | [+ Test Pattern]        |
| Layer 2  | | (Source) | | (Dest)   |    |-----------------------  |
|  ShapeC  | +----------+ +----------+    | img1.jpg                |
|          |                              | video.mp4               |
| [+Layer] | [Move] [Rotate] [Scale]      | Screen Capture          |
| [+Shape] |                              | Grid Pattern            |
|          +-------------------------------------------------+      |
|          |              CUE SYSTEM                         |      |
|          |  [Cue 1] [Cue 2] [Cue 3] [+]                   |      |
+------------------------------------------------------------------+
```

### UI Details

**Titel-Leiste ueber Canvas:**
- Klein und kompakt
- Toggle-Buttons: [Source] [Output] [Both]
- "Both" = Side-by-Side (default)

**Canvas-Bereich:**
- Punkte ziehen
- Gesamten Shape verschieben (Mitte ziehen)
- Shapes snappen aneinander

**Cue System (unten):**
- Speichert Konfigurationen
- Schnelles Wechseln zwischen Setups

---

## Shape-Typen

### Polygon
- Beliebige Anzahl Punkte (min 3)
- Punkte hinzufuegen/entfernen
- Freie Form

### Rechteck
- 4 Punkte
- Rechte Winkel beibehalten
- Breite/Hoehe einstellbar

### Output-Shape Eigenschaften
- Seitenlaengen angeben (in cm oder relativ)
- Winkel angeben
- System berechnet fehlende Parameter
- Warnung bei Ueberbestimmung

---

## Features

### F1: Media Pool
- [ ] Bilder importieren (PNG, JPG, TIFF)
- [ ] Videos importieren (MP4, MOV, AVI)
- [ ] Live: Screen Capture
- [ ] Live: Kamera-Auswahl (alle verbundenen)
- [ ] Test: Grid Pattern
- [ ] Test: Edge Pattern
- [ ] Test: Solid Colors
- [ ] Thumbnails anzeigen

### F2: Media Layer
- [ ] Layer erstellen (Medium zuweisen)
- [ ] Layer umbenennen
- [ ] Layer loeschen
- [ ] Layer Reihenfolge aendern
- [ ] Layer ein/ausblenden

### F3: Shapes
- [ ] Polygon hinzufuegen
- [ ] Rechteck hinzufuegen
- [ ] Shape loeschen
- [ ] Shape duplizieren
- [ ] Punkte verschieben (Drag)
- [ ] Gesamten Shape verschieben
- [ ] Shapes snappen aneinander
- [ ] Punkt hinzufuegen (Polygon)
- [ ] Punkt entfernen (Polygon)

### F4: Canvas-Ansicht
- [ ] Source-Ansicht
- [ ] Output-Ansicht
- [ ] Side-by-Side (Both)
- [ ] Kompakte Titel

### F5: Output-Fenster
- [ ] KEIN Rahmen
- [ ] KEIN Text/Overlay im normalen Modus
- [ ] Edit-Mode mit Overlay (Toggle)
- [ ] Fullscreen
- [ ] Multi-Monitor

### F6: Cue System
- [ ] Cue erstellen
- [ ] Cue benennen
- [ ] Cue aktivieren
- [ ] Cue loeschen

### F7: Projekt
- [ ] Speichern (JSON)
- [ ] Laden
- [ ] Auto-Save

---

## Keyboard Shortcuts

| Shortcut | Aktion |
|----------|--------|
| `Ctrl+S` | Speichern |
| `Ctrl+O` | Oeffnen |
| `Delete` | Ausgewaehltes loeschen |
| `F5` | Output-Fenster |
| `F11` | Fullscreen |
| `M` | Edit-Mode Toggle (im Output) |
| `1` | Source-Ansicht |
| `2` | Output-Ansicht |
| `3` | Side-by-Side |
| `G` | Grid anzeigen |
| `S` | Snap an/aus |

---

## Priorisierung

### Sofort fixen:
1. Titel kleiner machen
2. Output-Fenster: kein Rahmen, kein Text
3. View-Toggle (Source/Output/Both)

### Phase 1:
4. Gesamten Shape verschieben
5. Test-Patterns (Grid, Edges)
6. Live-Quellen (Screen Capture, Kamera)

### Phase 2:
7. Rechteck als Shape-Typ
8. Snapping zwischen Shapes
9. Cue System

### Phase 3:
10. Seitenlaengen/Winkel fuer Output
11. Video-Playback
