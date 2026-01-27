import os
import cv2
import numpy as np
import pygame
import sys
import mss
import json
import glob
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

# --- MODERNE UI LIBRARY ---
import customtkinter as ctk

# Settings für High-DPI Displays (Mac Retina Support)
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"


# --- STATE CLASS ---
class MappingState:
    def __init__(self):
        self.norm_points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        self.selected_point = None
        self.output_res = (800, 600)


state = MappingState()


class ProjectionStudio(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mapping Studio Pro")
        self.geometry("1200x800")

        # State
        self.is_projecting = False
        self.cap = None
        self.sct = mss.mss()
        try:
            self.monitors = self.sct.monitors[1:]
        except Exception:
            self.monitors = []

        self.monitor_names = [f"Monitor {i + 1} ({m['width']}x{m['height']})" for i, m in enumerate(self.monitors)]
        if not self.monitor_names: self.monitor_names = ["Kein Monitor gefunden"]

        self.preset_dir = os.path.join(os.getcwd(), "presets")
        if not os.path.exists(self.preset_dir): os.makedirs(self.preset_dir)

        # UI Aufbauen
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        self.build_main_area()

        # Initiale Preset Liste laden
        self.refresh_preset_list()

    def build_sidebar(self):
        # --- SIDEBAR FRAME ---
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)  # Spacer vor Presets

        # HEADER
        logo = ctk.CTkLabel(self.sidebar, text="MAPPING STUDIO", font=ctk.CTkFont(size=20, weight="bold"))
        logo.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # 1. INPUT SECTION
        ctk.CTkLabel(self.sidebar, text="EINGANGSQUELLE", text_color="gray", font=("Arial", 11, "bold")).grid(row=1,
                                                                                                              column=0,
                                                                                                              padx=20,
                                                                                                              pady=(10,
                                                                                                                    0),
                                                                                                              sticky="w")

        # Tabs für Input Mode (File / Screen / Cam)
        self.input_tabs = ctk.CTkSegmentedButton(self.sidebar, values=["Datei", "Screen", "Webcam"],
                                                 command=self.update_input_ui)
        self.input_tabs.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.input_tabs.set("Datei")

        # Container für dynamische Input-Elemente
        self.input_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.input_container.grid(row=3, column=0, padx=20, sticky="ew")

        # Initiale UI Elemente erstellen (werden in update_input_ui sichtbar gemacht)
        self.btn_file = ctk.CTkButton(self.input_container, text="Video wählen...", command=self.browse_file)
        self.lbl_file = ctk.CTkLabel(self.input_container, text="Keine Datei", font=("Arial", 10), text_color="gray")

        self.combo_screens = ctk.CTkComboBox(self.input_container, values=self.monitor_names)

        self.entry_cam = ctk.CTkEntry(self.input_container, placeholder_text="Cam Index (z.B. 0)")
        self.entry_cam.insert(0, "0")

        self.update_input_ui("Datei")  # Initialer Aufruf

        # 2. OUTPUT SECTION
        ctk.CTkLabel(self.sidebar, text="OUTPUT ZIEL", text_color="gray", font=("Arial", 11, "bold")).grid(row=4,
                                                                                                           column=0,
                                                                                                           padx=20,
                                                                                                           pady=(20, 0),
                                                                                                           sticky="w")

        self.combo_output = ctk.CTkComboBox(self.sidebar, values=self.monitor_names)
        if len(self.monitor_names) > 1: self.combo_output.set(self.monitor_names[1])
        self.combo_output.grid(row=5, column=0, padx=20, pady=(5, 10), sticky="ew")

        # Switches
        self.switch_fullscreen = ctk.CTkSwitch(self.sidebar, text="Vollbild Modus")
        self.switch_fullscreen.select()
        self.switch_fullscreen.grid(row=6, column=0, padx=20, pady=5, sticky="w")

        self.switch_grid = ctk.CTkSwitch(self.sidebar, text="Gitter anzeigen")
        self.switch_grid.select()
        self.switch_grid.grid(row=7, column=0, padx=20, pady=5, sticky="w")

        # 3. PRESET LISTE (Scrollbar)
        ctk.CTkLabel(self.sidebar, text="PRESETS", text_color="gray", font=("Arial", 11, "bold")).grid(row=8, column=0,
                                                                                                       padx=20,
                                                                                                       pady=(20, 0),
                                                                                                       sticky="sw")

        # Scrollable Frame statt Tabelle (Sieht viel moderner aus)
        self.preset_frame = ctk.CTkScrollableFrame(self.sidebar, height=200, label_text="Gespeicherte Setups")
        self.preset_frame.grid(row=9, column=0, padx=20, pady=(5, 10), sticky="nsew")

        # Footer Buttons für Presets
        preset_actions = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        preset_actions.grid(row=10, column=0, padx=20, pady=10, sticky="ew")

        ctk.CTkButton(preset_actions, text="+ Neu", width=80, command=self.save_new_preset).pack(side="left",
                                                                                                 padx=(0, 5))
        ctk.CTkButton(preset_actions, text="↻ Refresh", width=80, fg_color="transparent", border_width=1,
                      command=self.refresh_preset_list).pack(side="right")

    def build_main_area(self):
        # MAIN AREA
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Header Buttons Main
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.btn_start = ctk.CTkButton(header, text="PROJEKTION STARTEN", height=40, font=("Arial", 13, "bold"),
                                       fg_color="#00C853", hover_color="#009624", command=self.toggle_projection)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(header, text="Reset Form", height=40, fg_color="#455A64", hover_color="#37474F",
                      command=self.reset_points_aspect).pack(side="right")

        # PREVIEW CANVAS
        # Wir betten das klassische Canvas in einen CTK Frame ein
        canvas_container = ctk.CTkFrame(self.main_frame)
        canvas_container.grid(row=1, column=0, sticky="nsew")

        self.canvas = tk.Canvas(canvas_container, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)

        # Canvas Events
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        self.canvas.create_text(20, 20, anchor="nw", text="LIVE VORSCHAU", fill="white", font=("Arial", 12, "bold"))

    def update_input_ui(self, mode):
        # Alte Widgets entfernen (pack_forget)
        self.btn_file.pack_forget()
        self.lbl_file.pack_forget()
        self.combo_screens.pack_forget()
        self.entry_cam.pack_forget()

        if mode == "Datei":
            self.btn_file.pack(fill="x")
            self.lbl_file.pack(pady=5)
        elif mode == "Screen":
            self.combo_screens.pack(fill="x")
        elif mode == "Webcam":
            self.entry_cam.pack(fill="x")

    def refresh_preset_list(self):
        # Liste leeren
        for widget in self.preset_frame.winfo_children():
            widget.destroy()

        files = glob.glob(os.path.join(self.preset_dir, "*.json"))
        # Sortieren nach Datum (neu oben)
        files.sort(key=os.path.getmtime, reverse=True)

        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            ts = os.path.getmtime(f)
            date_str = datetime.fromtimestamp(ts).strftime('%d.%m.%y')

            # Row Card erstellen
            card = ctk.CTkFrame(self.preset_frame, fg_color=("gray85", "gray25"))
            card.pack(fill="x", pady=2, padx=2)

            # Label Name
            ctk.CTkLabel(card, text=name, font=("Arial", 12, "bold")).pack(side="left", padx=10, pady=5)
            # Label Date
            ctk.CTkLabel(card, text=date_str, font=("Arial", 10), text_color="gray").pack(side="left", padx=5)

            # Load Button (Pfeil)
            btn = ctk.CTkButton(card, text="▶", width=30, height=30, fg_color="transparent", border_width=1,
                                command=lambda path=f: self.load_preset(path))
            btn.pack(side="right", padx=5, pady=5)

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.avi")])
        if f:
            self.lbl_file.configure(text=os.path.basename(f))
            self.lbl_file.filepath = f  # Speichern im Widget Property

    def save_new_preset(self):
        dialog = ctk.CTkInputDialog(text="Name für das Preset:", title="Speichern")
        name = dialog.get_input()
        if not name: return

        # Daten sammeln
        mode = self.input_tabs.get()
        path = getattr(self.lbl_file, 'filepath', "")

        data = {
            "norm_points": state.norm_points,
            "mode": mode,
            "file_path": path,
            "screen_idx": self.combo_screens.get(),
            "cam_idx": self.entry_cam.get(),
            "fullscreen": self.switch_fullscreen.get(),
            "grid": self.switch_grid.get()
        }

        filepath = os.path.join(self.preset_dir, f"{name}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
            self.refresh_preset_list()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def load_preset(self, filepath):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            # UI Update
            state.norm_points = data.get("norm_points", state.norm_points)

            # Input Controls setzen
            mode = data.get("mode", "Datei")
            self.input_tabs.set(mode)
            self.update_input_ui(mode)

            if "file_path" in data and data["file_path"]:
                self.lbl_file.configure(text=os.path.basename(data["file_path"]))
                self.lbl_file.filepath = data["file_path"]

            if "screen_idx" in data: self.combo_screens.set(data["screen_idx"])
            if "cam_idx" in data:
                self.entry_cam.delete(0, "end")
                self.entry_cam.insert(0, data["cam_idx"])

            if "fullscreen" in data:
                self.switch_fullscreen.select() if data["fullscreen"] else self.switch_fullscreen.deselect()

            self.update_preview()
            print(f"Geladen: {filepath}")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # --- PROJECTION LOGIC ---
    def toggle_projection(self):
        if not self.is_projecting:
            self.start_projection()
        else:
            self.stop_projection()

    def reset_points_aspect(self):
        # Fallback Aspect Ratio
        state.norm_points = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        self.update_preview()

    def start_projection(self):
        mode = self.input_tabs.get()

        # Output Index ermitteln
        out_sel = self.combo_output.get()
        out_idx = self.monitor_names.index(out_sel) if out_sel in self.monitor_names else 0

        if self.monitors:
            t_w = self.monitors[out_idx]['width']
            t_h = self.monitors[out_idx]['height']
        else:
            t_w, t_h = 800, 600

        # Pygame Init
        pygame.init()
        self.w, self.h = t_w, t_h
        self.clock = pygame.time.Clock()

        flags = pygame.DOUBLEBUF
        if self.switch_fullscreen.get():
            flags |= pygame.FULLSCREEN
        else:
            flags |= pygame.RESIZABLE

        # Fenster positionieren
        try:
            self.screen = pygame.display.set_mode((self.w, self.h), flags, display=out_idx)
        except TypeError:
            if self.monitors:
                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{self.monitors[out_idx]['left']},{self.monitors[out_idx]['top']}"
            self.screen = pygame.display.set_mode((self.w, self.h), flags)

        state.output_res = (self.w, self.h)

        # Quelle öffnen
        if mode == "Screen":
            in_sel = self.combo_screens.get()
            in_idx = self.monitor_names.index(in_sel) if in_sel in self.monitor_names else 0
            self.input_rect = self.monitors[in_idx]
            self.vid_w, self.vid_h = self.input_rect["width"], self.input_rect["height"]

        elif mode == "Webcam":
            try:
                cam_id = int(self.entry_cam.get())
            except:
                cam_id = 0
            self.cap = cv2.VideoCapture(cam_id)
            if not self.cap.isOpened(): return
            self.vid_w = int(self.cap.get(3))
            self.vid_h = int(self.cap.get(4))

        else:  # Datei
            path = getattr(self.lbl_file, 'filepath', "")
            if not path: return messagebox.showerror("Fehler", "Keine Datei gewählt")
            self.cap = cv2.VideoCapture(path)
            if not self.cap.isOpened(): return
            self.vid_w = int(self.cap.get(3))
            self.vid_h = int(self.cap.get(4))

        self.src_points = np.float32([[0, 0], [self.vid_w, 0], [self.vid_w, self.vid_h], [0, self.vid_h]])

        self.is_projecting = True
        self.btn_start.configure(text="STOP", fg_color="#D32F2F", hover_color="#B71C1C")
        self.projection_loop()

    def stop_projection(self):
        self.is_projecting = False
        if self.cap: self.cap.release()
        pygame.quit()
        self.btn_start.configure(text="PROJEKTION STARTEN", fg_color="#00C853", hover_color="#009624")
        self.canvas.delete("all")
        self.update_preview()  # Canvas Text wiederherstellen

    def on_canvas_click(self, event):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        min_dist = 1000
        sel_idx = None
        for i, (nx, ny) in enumerate(state.norm_points):
            px, py = nx * cw, ny * ch
            dist = np.hypot(px - event.x, py - event.y)
            if dist < 20 and dist < min_dist:
                min_dist, sel_idx = dist, i
        state.selected_point = sel_idx

    def on_canvas_drag(self, event):
        if state.selected_point is not None:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            state.norm_points[state.selected_point] = [max(0, min(event.x, cw)) / cw, max(0, min(event.y, ch)) / ch]

    def on_canvas_release(self, event):
        state.selected_point = None

    def projection_loop(self):
        if not self.is_projecting: return
        is_edit = self.switch_grid.get()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop_projection(); return
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q: self.stop_projection(); return
                if event.key == pygame.K_m:
                    self.switch_grid.toggle()

            if is_edit:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    nmx, nmy = mx / self.w, my / self.h
                    dists = [np.hypot(p[0] - nmx, p[1] - nmy) for p in state.norm_points]
                    if min(dists) < 0.05: state.selected_point = np.argmin(dists)
                elif event.type == pygame.MOUSEMOTION and state.selected_point is not None and \
                        pygame.mouse.get_pressed()[0]:
                    mx, my = pygame.mouse.get_pos()
                    state.norm_points[state.selected_point] = [mx / self.w, my / self.h]
                elif event.type == pygame.MOUSEUP:
                    state.selected_point = None

        pygame.mouse.set_visible(is_edit)

        frame = None
        if self.input_tabs.get() == "Screen":
            img = np.array(self.sct.grab(self.input_rect))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        elif self.cap:
            ret, frame = self.cap.read()
            if not ret and self.input_tabs.get() == "Datei":
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()

        if frame is not None:
            dst = np.float32([[p[0] * self.w, p[1] * self.h] for p in state.norm_points])
            M = cv2.getPerspectiveTransform(self.src_points, dst)
            warped = cv2.warpPerspective(frame, M, (self.w, self.h), flags=cv2.INTER_LANCZOS4)

            surf = pygame.surfarray.make_surface(cv2.transpose(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)))
            self.screen.blit(surf, (0, 0))

            if is_edit:
                pts = [(int(p[0]), int(p[1])) for p in dst]
                pygame.draw.lines(self.screen, (0, 255, 255), True, pts, 3)
                for i, p in enumerate(pts):
                    col = (255, 0, 0) if i == state.selected_point else (0, 255, 0)
                    pygame.draw.circle(self.screen, col, p, 12)
            pygame.display.flip()

        self.update_preview()
        self.after(16, self.projection_loop)

    def update_preview(self):
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        poly = []
        for i, (nx, ny) in enumerate(state.norm_points):
            px, py = nx * cw, ny * ch
            poly.extend([px, py])
            col = "#00C853" if i == state.selected_point else "#29B6F6"
            self.canvas.create_oval(px - 6, py - 6, px + 6, py + 6, fill=col, outline="white")
        if len(poly) == 8:
            self.canvas.create_polygon(poly, outline="#29B6F6", fill="", width=2, dash=(5, 3))

        if not self.is_projecting:
            self.canvas.create_text(20, 20, anchor="nw", text="LIVE VORSCHAU", fill="white", font=("Arial", 12, "bold"))


if __name__ == "__main__":
    app = ProjectionStudio()
    app.mainloop()