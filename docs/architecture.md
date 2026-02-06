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
| F5 | Ausgewaehlten Output oeffnen |
| F11 | Output Fullscreen |
| Doppelklick auf Media Layer | Sichtbarkeit umschalten |
| Doppelklick auf Output Layer | Output-Fenster oeffnen |

---

## Migration von v3.0

Alte Projekte (v3.0) werden automatisch migriert:

1. Alte "layers" (MediaLayer mit eingebetteten Polygonen) → Neue MediaLayers (ohne Polygone)
2. Polygone werden extrahiert und erhalten `media_layer_id`
3. Alte "outputs" → Neue OutputLayers
4. Allen Polygonen wird der erste OutputLayer zugewiesen
