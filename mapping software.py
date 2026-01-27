import os
import cv2
import numpy as np
import pygame
import sys
import mss
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# --- HELPER KLASSE FÜR BI-DIREKTIONALE KOMMUNIKATION ---
class MappingState:
    def __init__(self):
        # Standard Punkte (werden später an Auflösung angepasst)
        self.dst_points = [[100, 100], [400, 100], [400, 400], [100, 400]]
        self.selected_point = None
        self.output_res = (800, 600)  # Platzhalter
        self.monitor_offset = (0, 0)


state = MappingState()


class ProjectionStudio:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Mapping Studio Pro")
        self.root.geometry("900x500")  # Breiter für Preview

        self.is_projecting = False
        self.cap = None
        self.sct = mss.mss()
        self.monitors = self.sct.monitors[1:]  # Monitor 1+

        # --- GUI LAYOUT ---
        # Links: Settings | Rechts: Preview
        left_panel = ttk.Frame(self.root, padding=10)
        left_panel.pack(side="left", fill="y")

        right_panel = ttk.LabelFrame(self.root, text="Live Form Preview", padding=10)
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # --- 1. SETTINGS (LINKS) ---
        ttk.Label(left_panel, text="INPUT QUELLE", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))

        self.source_mode = tk.StringVar(value="file")
        ttk.Radiobutton(left_panel, text="Videodatei", variable=self.source_mode, value="file").pack(anchor="w")
        ttk.Radiobutton(left_panel, text="Screen Capture", variable=self.source_mode, value="screen").pack(anchor="w")
        ttk.Radiobutton(left_panel, text="Webcam", variable=self.source_mode, value="cam").pack(anchor="w")

        self.file_path = tk.StringVar()
        ttk.Button(left_panel, text="Datei wählen...", command=self.browse_file).pack(fill="x", pady=5)
        ttk.Label(left_panel, textvariable=self.file_path, font=("Arial", 8), foreground="gray").pack(fill="x")

        # Monitor Auswahl Input
        ttk.Label(left_panel, text="Input Monitor (für Screen Capture):").pack(anchor="w", pady=(10, 0))
        self.mon_names = [f"Monitor {i + 1} ({m['width']}x{m['height']})" for i, m in enumerate(self.monitors)]
        self.cb_input_mon = ttk.Combobox(left_panel, values=self.mon_names, state="readonly")
        if self.mon_names: self.cb_input_mon.current(0)
        self.cb_input_mon.pack(fill="x")

        ttk.Separator(left_panel, orient="horizontal").pack(fill="x", pady=20)

        ttk.Label(left_panel, text="OUTPUT ZIEL (BEAMER)", font=("Arial", 10, "bold")).pack(anchor="w")
        self.cb_output_mon = ttk.Combobox(left_panel, values=self.mon_names, state="readonly")
        if len(self.mon_names) > 1:
            self.cb_output_mon.current(1)
        elif self.mon_names:
            self.cb_output_mon.current(0)
        self.cb_output_mon.pack(fill="x", pady=5)

        self.btn_start = ttk.Button(left_panel, text="PROJEKTION STARTEN", command=self.toggle_projection)
        self.btn_start.pack(fill="x", pady=20)

        ttk.Label(left_panel, text="Steuerung:\n'M' = Toggle Maus/UI\n'Q' = Stop", foreground="gray").pack(
            side="bottom")

        # --- 2. PREVIEW (RECHTS) ---
        # Canvas zeichnet die Form nach
        self.canvas = tk.Canvas(right_panel, bg="black", width=400, height=300)
        self.canvas.pack(fill="both", expand=True)
        # Wir speichern die Skalierung für die Vorschau
        self.preview_scale_x = 1.0
        self.preview_scale_y = 1.0

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi")])
        if f: self.file_path.set(f)

    def toggle_projection(self):
        if not self.is_projecting:
            self.start_projection()
        else:
            self.stop_projection()

    def start_projection(self):
        # 1. Config lesen
        mode = self.source_mode.get()
        out_idx = self.cb_output_mon.current()
        out_mon = self.monitors[out_idx]

        # Environment Variable für Fensterposition setzen
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{out_mon['left']},{out_mon['top']}"

        # 2. Pygame Init
        pygame.init()
        self.w, self.h = out_mon['width'], out_mon['height']
        state.output_res = (self.w, self.h)

        # Reset Punkte auf Ecken (leicht eingerückt)
        m = 100
        state.dst_points = [
            [m, m], [self.w - m, m], [self.w - m, self.h - m], [m, self.h - m]
        ]

        self.screen = pygame.display.set_mode((self.w, self.h), pygame.NOFRAME | pygame.DOUBLEBUF)
        pygame.display.set_caption("Mapping Output")
        self.clock = pygame.time.Clock()

        # 3. Quelle öffnen
        if mode == "screen":
            in_idx = self.cb_input_mon.current()
            self.input_rect = self.monitors[in_idx]
            self.vid_w, self.vid_h = self.input_rect["width"], self.input_rect["height"]
        else:
            path = self.file_path.get() if mode == "file" else 0
            self.cap = cv2.VideoCapture(path)
            if not self.cap.isOpened():
                messagebox.showerror("Fehler", "Quelle konnte nicht geöffnet werden")
                return
            self.vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.src_points = np.float32([[0, 0], [self.vid_w, 0], [self.vid_w, self.vid_h], [0, self.vid_h]])

        # UI Update
        self.is_projecting = True
        self.btn_start.config(text="STOP")
        self.show_ui = True

        # Start Loop via Tkinter 'after'
        self.projection_loop()

    def stop_projection(self):
        self.is_projecting = False
        if self.cap: self.cap.release()
        pygame.quit()
        self.btn_start.config(text="PROJEKTION STARTEN")
        # Canvas reset
        self.canvas.delete("all")

    def projection_loop(self):
        if not self.is_projecting: return

        # --- A. PYGAME LOGIK ---
        # Input Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop_projection(); return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    self.stop_projection(); return
                elif event.key == pygame.K_m:
                    self.show_ui = not self.show_ui
                    pygame.mouse.set_visible(self.show_ui)

            elif event.type == pygame.MOUSEBUTTONDOWN and self.show_ui:
                if event.button == 1:
                    m_pos = pygame.mouse.get_pos()
                    pts = np.array(state.dst_points)
                    dist = np.linalg.norm(pts - m_pos, axis=1)
                    if np.min(dist) < 40: state.selected_point = np.argmin(dist)

            elif event.type == pygame.MOUSEBUTTONUP:
                state.selected_point = None

        if state.selected_point is not None:
            # Mouse Limitieren auf Screen
            mx, my = pygame.mouse.get_pos()
            mx = max(0, min(mx, self.w))
            my = max(0, min(my, self.h))
            state.dst_points[state.selected_point] = [mx, my]

        # Frame holen
        frame = None
        if self.source_mode.get() == "screen":
            img = np.array(self.sct.grab(self.input_rect))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            ret, frame = self.cap.read()
            if not ret and self.source_mode.get() == "file":
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()

        if frame is not None:
            # Warping
            M = cv2.getPerspectiveTransform(self.src_points, np.float32(state.dst_points))
            warped = cv2.warpPerspective(frame, M, (self.w, self.h))

            # Rendering
            warped = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
            warped = cv2.transpose(warped)
            surf = pygame.surfarray.make_surface(warped)
            self.screen.blit(surf, (0, 0))

            # UI Overlay im Beamer-Fenster
            if self.show_ui:
                pygame.draw.lines(self.screen, (0, 255, 255), True, state.dst_points, 2)
                for i, p in enumerate(state.dst_points):
                    color = (255, 0, 0) if i == state.selected_point else (0, 255, 0)
                    pygame.draw.circle(self.screen, color, (int(p[0]), int(p[1])), 10)

            pygame.display.flip()

        # --- B. TKINTER PREVIEW UPDATE ---
        self.update_preview_canvas()

        # Loop am Leben erhalten (ca. 60 FPS -> 16ms)
        self.root.after(16, self.projection_loop)

    def update_preview_canvas(self):
        """Zeichnet die Form im Tkinter Fenster basierend auf Pygame Koordinaten"""
        self.canvas.delete("all")

        # Berechne Skalierungsfaktor (Canvas Größe / Screen Größe)
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        sw, sh = state.output_res

        # Verhindere Division durch Null beim Start
        if sw == 0 or cw <= 1: return

        scale_x = cw / sw
        scale_y = ch / sh

        # Rahmen des Beamers zeichnen (als Referenz)
        self.canvas.create_rectangle(2, 2, cw, ch, outline="gray", width=1)

        # Mapped Polygon
        poly_points = []
        for p in state.dst_points:
            px = p[0] * scale_x
            py = p[1] * scale_y
            poly_points.extend([px, py])

            # Eckpunkte zeichnen
            self.canvas.create_oval(px - 4, py - 4, px + 4, py + 4, fill="#00ff00", outline="")

        # Polygon füllen (transparent simulieren durch stipple ist in Tkinter schwer, daher nur Outline)
        if len(poly_points) == 8:
            self.canvas.create_polygon(poly_points, outline="#00ccff", fill="", width=2)

            # Optional: Halb-transparentes Füllen (Trick)
            # Tkinter kann keine echte Transparenz, aber wir können ein Gittermuster (stipple) nehmen
            self.canvas.create_polygon(poly_points, fill="cyan", stipple="gray25", outline="")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ProjectionStudio()
    app.run()