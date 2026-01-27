import os
import cv2
import numpy as np
import pygame
import sys
import mss
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# --- STATE CLASS (Datenhaltung) ---
class MappingState:
    def __init__(self):
        # Wir speichern Punkte relativ (0.0 bis 1.0), damit sie unabhängig von der Auflösung sind
        # Das macht das Umschalten zwischen Preview und Beamer viel leichter
        self.norm_points = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        self.selected_point = None
        self.output_res = (800, 600)


state = MappingState()


class ProjectionStudio:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mapping Studio V3")
        self.root.geometry("1000x550")

        self.is_projecting = False
        self.cap = None
        self.sct = mss.mss()
        try:
            self.monitors = self.sct.monitors[1:]  # Monitor 1+
        except Exception:
            self.monitors = []  # Fallback falls mss failt

        self.current_mode = None
        self.build_ui()

    def build_ui(self):
        # Layout Split
        left_panel = ttk.Frame(self.root, padding=10)
        left_panel.pack(side="left", fill="y", padx=5)

        right_panel = ttk.LabelFrame(self.root, text="Interaktive Vorschau (Hier ziehen!)", padding=10)
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # --- SETTINGS ---
        ttk.Label(left_panel, text="1. QUELLER (INPUT)", font=("Arial", 10, "bold")).pack(anchor="w")
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

        ttk.Label(left_panel, text="2. ZIEL (OUTPUT)", font=("Arial", 10, "bold")).pack(anchor="w")
        self.cb_output_mon = ttk.Combobox(left_panel, values=self.mon_names, state="readonly")
        if len(self.mon_names) > 1:
            self.cb_output_mon.current(1)
        elif self.mon_names:
            self.cb_output_mon.current(0)
        self.cb_output_mon.pack(fill="x", pady=5)

        # Fullscreen Checkbox
        self.use_fullscreen = tk.BooleanVar(value=True)
        ttk.Checkbutton(left_panel, text="Vollbild Modus", variable=self.use_fullscreen).pack(anchor="w", pady=5)

        self.btn_start = ttk.Button(left_panel, text="PROJEKTION STARTEN", command=self.toggle_projection)
        self.btn_start.pack(fill="x", pady=20)

        # --- PREVIEW CANVAS ---
        self.canvas = tk.Canvas(right_panel, bg="black", width=500, height=400, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # Canvas Events für Maus-Interaktion
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f: self.file_path.set(f)

    def toggle_projection(self):
        if not self.is_projecting:
            self.start_projection()
        else:
            self.stop_projection()

    def start_projection(self):
        self.current_mode = self.source_mode.get()

        # Validierung
        if self.current_mode == "file" and not self.file_path.get():
            messagebox.showerror("Fehler", "Bitte Datei wählen!")
            return

        # Output Monitor Setup
        if self.monitors:
            out_idx = self.cb_output_mon.current()
            out_mon = self.monitors[out_idx]
            # Fensterposition setzen (wichtig für Multimonitor)
            os.environ['SDL_VIDEO_WINDOW_POS'] = f"{out_mon['left']},{out_mon['top']}"
            target_w, target_h = out_mon['width'], out_mon['height']
        else:
            target_w, target_h = 800, 600  # Fallback

        # Pygame Init
        pygame.init()

        if self.use_fullscreen.get():
            # Vollbild / Rahmenlos auf Zielmonitor
            self.w, self.h = target_w, target_h
            self.screen = pygame.display.set_mode((self.w, self.h), pygame.NOFRAME | pygame.DOUBLEBUF)
        else:
            # Fenstermodus (kleiner zum Testen)
            self.w, self.h = 800, 600
            self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE | pygame.DOUBLEBUF)

        state.output_res = (self.w, self.h)
        pygame.display.set_caption("Beamer Output")
        self.clock = pygame.time.Clock()

        # Quelle öffnen
        if self.current_mode == "screen":
            if self.monitors:
                in_idx = self.cb_input_mon.current()
                self.input_rect = self.monitors[in_idx]
                self.vid_w, self.vid_h = self.input_rect["width"], self.input_rect["height"]
            else:
                messagebox.showerror("Error", "Keine Monitore gefunden für Screen Capture")
                return
        else:
            src = self.file_path.get() if self.current_mode == "file" else 0
            self.cap = cv2.VideoCapture(src)
            if not self.cap.isOpened():
                messagebox.showerror("Error", "Videoquelle defekt")
                pygame.quit()
                return
            self.vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.src_points = np.float32([[0, 0], [self.vid_w, 0], [self.vid_w, self.vid_h], [0, self.vid_h]])

        self.is_projecting = True
        self.btn_start.config(text="STOP")
        self.show_ui = True

        # Start Loop
        self.projection_loop()

    def stop_projection(self):
        self.is_projecting = False
        if self.cap: self.cap.release()
        pygame.quit()
        self.btn_start.config(text="PROJEKTION STARTEN")
        self.canvas.delete("all")

    # --- CANVAS INTERAKTION (TKINTER) ---
    def on_canvas_click(self, event):
        # Finde nächsten Punkt im Canvas
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        click_x, click_y = event.x, event.y

        min_dist = 1000
        sel_idx = None

        for i, (nx, ny) in enumerate(state.norm_points):
            # Rechne normalisierte Punkte (0-1) auf Canvas Größe um
            px = nx * cw
            py = ny * ch
            dist = np.hypot(px - click_x, py - click_y)
            if dist < 20:  # Fangradius
                if dist < min_dist:
                    min_dist = dist
                    sel_idx = i

        state.selected_point = sel_idx

    def on_canvas_drag(self, event):
        if state.selected_point is not None:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            # Begrenze auf Canvas
            ex = max(0, min(event.x, cw))
            ey = max(0, min(event.y, ch))

            # Speichere als normalisierte Koordinate (0.0 - 1.0)
            state.norm_points[state.selected_point] = [ex / cw, ey / ch]

    def on_canvas_release(self, event):
        state.selected_point = None

    # --- MAIN LOOP ---
    def projection_loop(self):
        if not self.is_projecting: return

        # 1. PYGAME EVENTS (Maus auf Beamer Fenster)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop_projection(); return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q: self.stop_projection(); return
                if event.key == pygame.K_m: self.show_ui = not self.show_ui

            # Maus Interaktion im Pygame Fenster
            elif event.type == pygame.MOUSEBUTTONDOWN and self.show_ui:
                if event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    # Umrechnen in normalisierte Koordinaten für den Vergleich
                    nmx, nmy = mx / self.w, my / self.h

                    dists = [np.hypot(p[0] - nmx, p[1] - nmy) for p in state.norm_points]
                    if min(dists) < 0.05:  # Toleranz relativ zur Größe
                        state.selected_point = np.argmin(dists)

            elif event.type == pygame.MOUSEMOTION and state.selected_point is not None:
                # Nur wenn Maus im Pygame Fenster gedrückt ist
                if pygame.mouse.get_pressed()[0]:
                    mx, my = pygame.mouse.get_pos()
                    state.norm_points[state.selected_point] = [mx / self.w, my / self.h]

            elif event.type == pygame.MOUSEBUTTONUP:
                state.selected_point = None

        # 2. BILD VERARBEITUNG
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
            # Berechne Absolute Pixel Koordinaten aus den normalisierten Werten
            dst_pixels = np.float32([[p[0] * self.w, p[1] * self.h] for p in state.norm_points])

            M = cv2.getPerspectiveTransform(self.src_points, dst_pixels)
            warped = cv2.warpPerspective(frame, M, (self.w, self.h))

            # Display
            warped_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
            warped_rgb = cv2.transpose(warped_rgb)
            surf = pygame.surfarray.make_surface(warped_rgb)
            self.screen.blit(surf, (0, 0))

            if self.show_ui:
                # Zeichne UI
                pts = [(int(p[0]), int(p[1])) for p in dst_pixels]
                pygame.draw.lines(self.screen, (0, 255, 255), True, pts, 2)
                for i, p in enumerate(pts):
                    color = (255, 0, 0) if i == state.selected_point else (0, 255, 0)
                    pygame.draw.circle(self.screen, color, p, 10)

            pygame.display.flip()

        # 3. PREVIEW UPDATE (TKINTER)
        self.update_preview()
        self.root.after(16, self.projection_loop)

    def update_preview(self):
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()

        # Umrechnen: Normalisiert -> Canvas Pixel
        poly_pts = []
        for i, (nx, ny) in enumerate(state.norm_points):
            px, py = nx * cw, ny * ch
            poly_pts.extend([px, py])

            # Eckpunkt
            col = "red" if i == state.selected_point else "#00ff00"
            self.canvas.create_oval(px - 5, py - 5, px + 5, py + 5, fill=col, outline="black")

        # Form füllen
        if len(poly_pts) == 8:
            self.canvas.create_polygon(poly_pts, outline="cyan", fill="", width=2, dash=(5, 3))

        # Info Text
        self.canvas.create_text(10, 10, anchor="nw", text="Output Preview", fill="white")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ProjectionStudio()
    app.run()