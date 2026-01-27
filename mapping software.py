import os
# Positionierung muss VOR pygame import passieren (für SDL_VIDEO_WINDOW_POS)
# Wir importieren es später erneut, aber os muss da sein.

import cv2
import numpy as np
import sys
import mss
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# --- PHASE 1: KONFIGURATIONS-KLASSE (TKINTER) ---
class ConfigLauncher:
    def __init__(self):
        self.config = None
        self.root = tk.Tk()
        self.root.title("Mapping Studio")
        self.root.geometry("500x550")

        # Monitor Infos holen (für Input UND Output Auswahl)
        self.monitors = []
        with mss.mss() as sct:
            # Monitor 0 ist "Alle", wir wollen ab 1
            self.monitors = sct.monitors[1:]

        self.build_ui()

    def build_ui(self):
        pad = {'padx': 10, 'pady': 10}

        # --- 1. EINGANGSQUELLE ---
        lbl_in = ttk.LabelFrame(self.root, text="1. Was willst du projizieren? (Input)")
        lbl_in.pack(fill="x", **pad)

        self.source_mode = tk.StringVar(value="file")

        # Datei
        f_frame = ttk.Frame(lbl_in)
        f_frame.pack(fill="x", padx=5, pady=2)
        ttk.Radiobutton(f_frame, text="Videodatei", variable=self.source_mode, value="file",
                        command=self.update_ui).pack(side="left")
        self.file_path = tk.StringVar()
        self.btn_browse = ttk.Button(f_frame, text="Wählen...", command=self.browse_file, state="normal")
        self.btn_browse.pack(side="right")
        self.lbl_file = ttk.Label(f_frame, textvariable=self.file_path, font=("Arial", 8))
        self.lbl_file.pack(side="right", padx=5)

        # Webcam
        c_frame = ttk.Frame(lbl_in)
        c_frame.pack(fill="x", padx=5, pady=2)
        ttk.Radiobutton(c_frame, text="Kamera / Capture Card", variable=self.source_mode, value="cam",
                        command=self.update_ui).pack(side="left")
        self.cam_index = tk.IntVar(value=0)
        self.ent_cam = ttk.Entry(c_frame, textvariable=self.cam_index, width=5, state="disabled")
        self.ent_cam.pack(side="right")
        ttk.Label(c_frame, text="Index:").pack(side="right")

        # Screen Capture
        s_frame = ttk.Frame(lbl_in)
        s_frame.pack(fill="x", padx=5, pady=2)
        ttk.Radiobutton(s_frame, text="Bildschirm abgreifen", variable=self.source_mode, value="screen",
                        command=self.update_ui).pack(side="left")

        # Monitor Liste für Input
        mon_names = [f"Monitor {i + 1} ({m['width']}x{m['height']})" for i, m in enumerate(self.monitors)]
        self.input_mon_combo = ttk.Combobox(s_frame, values=mon_names, state="disabled")
        if mon_names: self.input_mon_combo.current(0)
        self.input_mon_combo.pack(side="right")

        # --- 2. ZIEL DISPLAY ---
        lbl_out = ttk.LabelFrame(self.root, text="2. Wo steht der Beamer? (Output)")
        lbl_out.pack(fill="x", **pad)

        ttk.Label(lbl_out, text="Wähle den Monitor für die Projektion:").pack(anchor="w", padx=5)
        self.output_mon_combo = ttk.Combobox(lbl_out, values=mon_names, state="readonly")
        if len(mon_names) > 1:
            self.output_mon_combo.current(1)  # Standardmäßig 2. Monitor
        elif mon_names:
            self.output_mon_combo.current(0)
        self.output_mon_combo.pack(fill="x", padx=5, pady=5)

        # --- START ---
        ttk.Button(self.root, text="START MAPPING", command=self.on_start).pack(fill="x", padx=20, pady=20)

    def update_ui(self):
        mode = self.source_mode.get()
        # Reset States
        self.btn_browse.config(state="normal" if mode == "file" else "disabled")
        self.ent_cam.config(state="normal" if mode == "cam" else "disabled")
        self.input_mon_combo.config(state="readonly" if mode == "screen" else "disabled")

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv")])
        if f: self.file_path.set(f)

    def on_start(self):
        mode = self.source_mode.get()
        settings = {"mode": mode}

        # Input Validierung
        if mode == "file":
            if not self.file_path.get(): return messagebox.showerror("Error", "Keine Datei gewählt.")
            settings["path"] = self.file_path.get()
        elif mode == "cam":
            settings["cam_idx"] = self.cam_index.get()
        elif mode == "screen":
            idx = self.input_mon_combo.current()
            settings["input_monitor"] = self.monitors[idx]  # Ganzes Dict speichern

        # Output Validierung
        out_idx = self.output_mon_combo.current()
        settings["output_monitor"] = self.monitors[out_idx]

        self.config = settings
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.config


# --- PHASE 2: PROJECTION ENGINE ---
class ProjectionEngine:
    def __init__(self, config):
        self.config = config

        # 1. Positionierung des Fensters VOR pygame.init()
        # SDL_VIDEO_WINDOW_POS erwartet "x,y"
        out_mon = config["output_monitor"]
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{out_mon['left']},{out_mon['top']}"

        import pygame  # Import hier, damit Environment Variable greift
        pygame.init()

        # Setup Screen
        # Wir nehmen die exakte Größe des Zielmonitors
        self.w, self.h = out_mon['width'], out_mon['height']

        # NOFRAME ist oft besser für Mapping als FULLSCREEN, da es Multimonitor-Probleme vermeidet
        self.screen = pygame.display.set_mode((self.w, self.h), pygame.NOFRAME | pygame.DOUBLEBUF)
        pygame.display.set_caption("Mapping Output")
        self.clock = pygame.time.Clock()

        # 2. Quelle öffnen
        if config["mode"] == "screen":
            self.sct = mss.mss()
            self.input_rect = config["input_monitor"]
            # Fix für MSS width/height doubles bei Retina Displays oft nicht nötig, aber beachten
            self.vid_w = self.input_rect["width"]
            self.vid_h = self.input_rect["height"]

        else:
            src = config["path"] if config["mode"] == "file" else config["cam_idx"]
            self.cap = cv2.VideoCapture(src)
            self.vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 3. Mapping Punkte (Start leicht eingerückt)
        self.src_points = np.float32([[0, 0], [self.vid_w, 0], [self.vid_w, self.vid_h], [0, self.vid_h]])

        m = 100
        self.dst_points = [
            [m, m], [self.w - m, m], [self.w - m, self.h - m], [m, self.h - m]
        ]

        self.selected_point = None
        self.show_ui = True
        self.running = True

    def get_frame(self):
        if self.config["mode"] == "screen":
            # MSS Grab
            img = np.array(self.sct.grab(self.input_rect))
            return True, cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            ret, frame = self.cap.read()
            if not ret and self.config["mode"] == "file":
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            return ret, frame

    def run(self):
        import pygame  # Sicherstellen dass wir pygame namespace haben
        while self.running:
            # Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_m:
                        self.show_ui = not self.show_ui
                        pygame.mouse.set_visible(self.show_ui)

                elif event.type == pygame.MOUSEBUTTONDOWN and self.show_ui:
                    if event.button == 1:
                        m_pos = pygame.mouse.get_pos()
                        # Simple Distanzmessung
                        pts = np.array(self.dst_points)
                        dist = np.linalg.norm(pts - m_pos, axis=1)
                        if np.min(dist) < 30: self.selected_point = np.argmin(dist)

                elif event.type == pygame.MOUSEBUTTONUP:
                    self.selected_point = None

            # Dragging
            if self.selected_point is not None:
                self.dst_points[self.selected_point] = list(pygame.mouse.get_pos())

            # Logic
            ret, frame = self.get_frame()
            if ret:
                # Warp
                M = cv2.getPerspectiveTransform(self.src_points, np.float32(self.dst_points))
                warped = cv2.warpPerspective(frame, M, (self.w, self.h))

                # Convert for Pygame
                warped = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
                warped = cv2.transpose(warped)
                surf = pygame.surfarray.make_surface(warped)

                self.screen.blit(surf, (0, 0))

            # UI Overlay
            if self.show_ui:
                pygame.draw.lines(self.screen, (0, 255, 255), True, self.dst_points, 2)
                for p in self.dst_points:
                    pygame.draw.circle(self.screen, (0, 255, 0), (int(p[0]), int(p[1])), 10)

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        if hasattr(self, 'cap') and self.cap: self.cap.release()
        sys.exit()


if __name__ == "__main__":
    launcher = ConfigLauncher()
    config = launcher.run()

    if config:
        try:
            app = ProjectionEngine(config)
            app.run()
        except Exception as e:
            print(f"Error: {e}")