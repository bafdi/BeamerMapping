import os
import cv2
import numpy as np
import pygame
import sys
import mss
import json  # WICHTIG: Für Save/Load
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# --- STATE CLASS ---
class MappingState:
    def __init__(self):
        # Wir speichern Punkte relativ (0.0 bis 1.0)
        self.norm_points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        self.selected_point = None
        self.output_res = (800, 600)


state = MappingState()


class ProjectionStudio:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mapping Studio V5.1 (Save/Load)")
        self.root.geometry("1100x700")

        self.is_projecting = False
        self.cap = None
        self.sct = mss.mss()
        try:
            self.monitors = self.sct.monitors[1:]
        except Exception:
            self.monitors = []

        self.current_mode = None

        # State Variable für Sichtbarkeit der Hilfslinien
        self.show_overlays = tk.BooleanVar(value=True)

        self.build_ui()

    def build_ui(self):
        left_panel = ttk.Frame(self.root, padding=10)
        left_panel.pack(side="left", fill="y", padx=5)

        right_panel = ttk.LabelFrame(self.root, text="Interaktive Vorschau", padding=10)
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # --- SETTINGS ---
        ttk.Label(left_panel, text="1. INPUT QUELLE", font=("Arial", 10, "bold")).pack(anchor="w")
        self.source_mode = tk.StringVar(value="file")
        ttk.Radiobutton(left_panel, text="Videodatei", variable=self.source_mode, value="file").pack(anchor="w")
        ttk.Radiobutton(left_panel, text="Screen Capture", variable=self.source_mode, value="screen").pack(anchor="w")
        ttk.Radiobutton(left_panel, text="Webcam", variable=self.source_mode, value="cam").pack(anchor="w")

        self.file_path = tk.StringVar()
        ttk.Button(left_panel, text="Datei wählen...", command=self.browse_file).pack(fill="x", pady=5)
        ttk.Label(left_panel, textvariable=self.file_path, font=("Arial", 8), foreground="gray").pack(fill="x")

        # Input Monitor Combo
        self.mon_names = [f"Monitor {i + 1} ({m['width']}x{m['height']})" for i, m in enumerate(self.monitors)]
        self.cb_input_mon = ttk.Combobox(left_panel, values=self.mon_names, state="readonly")
        if self.mon_names: self.cb_input_mon.current(0)
        self.cb_input_mon.pack(fill="x", pady=(5, 15))

        ttk.Separator(left_panel, orient="horizontal").pack(fill="x", pady=10)

        ttk.Label(left_panel, text="2. OUTPUT ZIEL", font=("Arial", 10, "bold")).pack(anchor="w")
        self.cb_output_mon = ttk.Combobox(left_panel, values=self.mon_names, state="readonly")
        if len(self.mon_names) > 1:
            self.cb_output_mon.current(1)
        elif self.mon_names:
            self.cb_output_mon.current(0)
        self.cb_output_mon.pack(fill="x", pady=5)

        # --- VIEW OPTIONS ---
        ttk.Label(left_panel, text="3. ANSICHT & PRESETS", font=("Arial", 10, "bold")).pack(anchor="w", pady=(15, 5))

        self.use_fullscreen = tk.BooleanVar(value=True)
        ttk.Checkbutton(left_panel, text="Vollbild (Menüleiste ausblenden)", variable=self.use_fullscreen).pack(
            anchor="w")

        # Edit Mode Toggle
        ttk.Checkbutton(left_panel, text="Editier-Modus (Gitter anzeigen)", variable=self.show_overlays).pack(
            anchor="w", pady=5)

        # --- NEU: SAVE & LOAD BUTTONS ---
        save_frame = ttk.Frame(left_panel)
        save_frame.pack(fill="x", pady=10)

        ttk.Button(save_frame, text="💾 Einstellungen speichern", command=self.save_settings).pack(fill="x", pady=2)
        ttk.Button(save_frame, text="📂 Einstellungen laden", command=self.load_settings).pack(fill="x", pady=2)
        # --------------------------------

        ttk.Button(left_panel, text="Punkte Reset (Seitenverhältnis)", command=self.reset_points_aspect).pack(fill="x",
                                                                                                              pady=(20,
                                                                                                                    5))

        self.btn_start = ttk.Button(left_panel, text="PROJEKTION STARTEN", command=self.toggle_projection)
        self.btn_start.pack(fill="x", pady=10)

        # --- CANVAS ---
        self.canvas = tk.Canvas(right_panel, bg="black", width=500, height=400, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f: self.file_path.set(f)

    # --- SAVE / LOAD LOGIC ---
    def save_settings(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")]
        )
        if not filename: return

        data = {
            "norm_points": state.norm_points,
            "source_mode": self.source_mode.get(),
            "file_path": self.file_path.get(),
            "fullscreen": self.use_fullscreen.get(),
            "show_overlays": self.show_overlays.get()
        }

        try:
            with open(filename, "w") as f:
                json.dump(data, f, indent=4)
            messagebox.showinfo("Gespeichert", f"Einstellungen gespeichert in:\n{os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def load_settings(self):
        filename = filedialog.askopenfilename(
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")]
        )
        if not filename: return

        try:
            with open(filename, "r") as f:
                data = json.load(f)

            # Werte wiederherstellen
            if "norm_points" in data:
                state.norm_points = data["norm_points"]
            if "source_mode" in data:
                self.source_mode.set(data["source_mode"])
            if "file_path" in data:
                self.file_path.set(data["file_path"])
            if "fullscreen" in data:
                self.use_fullscreen.set(data["fullscreen"])
            if "show_overlays" in data:
                self.show_overlays.set(data["show_overlays"])

            self.update_preview()
            messagebox.showinfo("Geladen", "Einstellungen erfolgreich geladen!")

        except Exception as e:
            messagebox.showerror("Fehler", f"Laden fehlgeschlagen:\n{e}")

    # -------------------------

    def toggle_projection(self):
        if not self.is_projecting:
            self.start_projection()
        else:
            self.stop_projection()

    def reset_points_aspect(self):
        if self.vid_w > 0 and self.vid_h > 0:
            aspect = self.vid_w / self.vid_h
            w = 0.8
            screen_aspect = self.w / self.h
            h = w * (screen_aspect / aspect)
            x0 = (1.0 - w) / 2
            y0 = (1.0 - h) / 2

            state.norm_points = [
                [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]
            ]
            self.update_preview()

    def start_projection(self):
        self.current_mode = self.source_mode.get()
        if self.current_mode == "file" and not self.file_path.get():
            messagebox.showerror("Fehler", "Bitte Datei wählen!")
            return

        out_idx = self.cb_output_mon.current()
        if self.monitors:
            target_w = self.monitors[out_idx]['width']
            target_h = self.monitors[out_idx]['height']
        else:
            target_w, target_h = 800, 600

        pygame.init()
        self.w, self.h = target_w, target_h
        self.clock = pygame.time.Clock()

        flags = pygame.DOUBLEBUF
        if self.use_fullscreen.get():
            flags |= pygame.FULLSCREEN
        else:
            flags |= pygame.RESIZABLE

        # Fenster Erstellung
        if self.use_fullscreen.get():
            try:
                self.screen = pygame.display.set_mode((self.w, self.h), flags, display=out_idx)
            except TypeError:
                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{self.monitors[out_idx]['left']},{self.monitors[out_idx]['top']}"
                self.screen = pygame.display.set_mode((self.w, self.h), flags)
        else:
            self.w, self.h = 800, 600
            self.screen = pygame.display.set_mode((self.w, self.h), flags)

        state.output_res = (self.w, self.h)
        pygame.display.set_caption("Mapping Output")

        # Quelle öffnen
        if self.current_mode == "screen":
            if self.monitors:
                in_idx = self.cb_input_mon.current()
                self.input_rect = self.monitors[in_idx]
                self.vid_w, self.vid_h = self.input_rect["width"], self.input_rect["height"]
            else:
                return
        else:
            src = self.file_path.get() if self.current_mode == "file" else 0
            self.cap = cv2.VideoCapture(src)
            if not self.cap.isOpened(): return
            self.vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.src_points = np.float32([[0, 0], [self.vid_w, 0], [self.vid_w, self.vid_h], [0, self.vid_h]])

        # WICHTIG: Beim Starten nicht resetten, falls geladene Punkte da sind!
        # Nur resetten, wenn es noch die Standardwerte sind
        if state.norm_points == [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]:
            self.reset_points_aspect()

        self.is_projecting = True
        self.btn_start.config(text="STOP")
        self.projection_loop()

    def stop_projection(self):
        self.is_projecting = False
        if self.cap: self.cap.release()
        pygame.quit()
        self.btn_start.config(text="PROJEKTION STARTEN")
        self.canvas.delete("all")

    # --- CANVAS ---
    def on_canvas_click(self, event):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        min_dist = 1000
        sel_idx = None
        for i, (nx, ny) in enumerate(state.norm_points):
            px, py = nx * cw, ny * ch
            dist = np.hypot(px - event.x, py - event.y)
            if dist < 20 and dist < min_dist:
                min_dist = dist
                sel_idx = i
        state.selected_point = sel_idx

    def on_canvas_drag(self, event):
        if state.selected_point is not None:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            state.norm_points[state.selected_point] = [
                max(0, min(event.x, cw)) / cw,
                max(0, min(event.y, ch)) / ch
            ]

    def on_canvas_release(self, event):
        state.selected_point = None

    # --- LOOP ---
    def projection_loop(self):
        if not self.is_projecting: return

        # Check: Sind wir im Edit Mode?
        is_edit_mode = self.show_overlays.get()

        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop_projection();
                return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q: self.stop_projection(); return

                # Taste M toggled jetzt die Checkbox im GUI
                if event.key == pygame.K_m:
                    self.show_overlays.set(not is_edit_mode)

            # Maus Interaktion NUR wenn Edit Mode aktiv ist
            elif event.type == pygame.MOUSEBUTTONDOWN and is_edit_mode:
                if event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    nmx, nmy = mx / self.w, my / self.h
                    dists = [np.hypot(p[0] - nmx, p[1] - nmy) for p in state.norm_points]
                    if min(dists) < 0.05: state.selected_point = np.argmin(dists)

            elif event.type == pygame.MOUSEMOTION and state.selected_point is not None:
                if pygame.mouse.get_pressed()[0] and is_edit_mode:
                    mx, my = pygame.mouse.get_pos()
                    state.norm_points[state.selected_point] = [mx / self.w, my / self.h]

            elif event.type == pygame.MOUSEBUTTONUP:
                state.selected_point = None

        # Wenn Edit-Mode aus ist, Mauszeiger verstecken
        pygame.mouse.set_visible(is_edit_mode)

        # Render
        frame = None
        if self.current_mode == "screen":
            img = np.array(self.sct.grab(self.input_rect))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        elif self.cap:
            ret, frame = self.cap.read()
            if not ret and self.current_mode == "file":
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()

        if frame is not None:
            dst_pixels = np.float32([[p[0] * self.w, p[1] * self.h] for p in state.norm_points])
            M = cv2.getPerspectiveTransform(self.src_points, dst_pixels)

            warped = cv2.warpPerspective(frame, M, (self.w, self.h), flags=cv2.INTER_LANCZOS4)

            warped_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
            warped_rgb = cv2.transpose(warped_rgb)
            surf = pygame.surfarray.make_surface(warped_rgb)
            self.screen.blit(surf, (0, 0))

            # UI Overlay (Nur zeichnen, wenn Haken gesetzt)
            if is_edit_mode:
                pts = [(int(p[0]), int(p[1])) for p in dst_pixels]
                pygame.draw.lines(self.screen, (0, 255, 255), True, pts, 3)
                for i, p in enumerate(pts):
                    col = (255, 0, 0) if i == state.selected_point else (0, 255, 0)
                    pygame.draw.circle(self.screen, col, p, 12)

            pygame.display.flip()

        self.update_preview()
        self.root.after(16, self.projection_loop)

    def update_preview(self):
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        poly_pts = []
        for i, (nx, ny) in enumerate(state.norm_points):
            px, py = nx * cw, ny * ch
            poly_pts.extend([px, py])
            col = "red" if i == state.selected_point else "#00ff00"
            self.canvas.create_oval(px - 6, py - 6, px + 6, py + 6, fill=col, outline="black")

        if len(poly_pts) == 8:
            self.canvas.create_polygon(poly_pts, outline="cyan", fill="", width=2, dash=(5, 3))

        self.canvas.create_text(10, 10, anchor="nw", text="Output Preview", fill="white")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ProjectionStudio()
    app.run()