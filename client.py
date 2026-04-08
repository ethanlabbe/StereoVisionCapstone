import numpy as np
import cv2
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from PIL import Image, ImageTk
import threading
import queue
import time
import os

# Attempt to load sv_ttk for a modern dark theme, fallback to standard ttk styling
try:
    import sv_ttk
    HAS_SV_TTK = True
except ImportError:
    HAS_SV_TTK = False

from image_transfer import ImageClient
from stereo_class import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error

class StereoClientDevice:
    def __init__(self, server_host='localhost', server_port=8080, calibrating=False, calibraton_params_file="calibration_params.npz"):
        self.client = ImageClient(server_host, server_port)
        self.server_host = server_host
        self.server_port = server_port
        self.calibrating = calibrating
        self.calibration_path = calibraton_params_file
        
        self.reinit_stereo(block_size=3, num_disp=16*15, wls_lambda=8000.0)

    def reinit_stereo(self, block_size, num_disp, wls_lambda):
        self.stereo = StereoSystem(block_size=block_size, num_disp=num_disp, wls_lambda=wls_lambda)
        if not self.calibrating:
            try:
                self.stereo.load_calibration_parameters(self.calibration_path)
                
                # --- BUG FIX: OpenCV Warm-Up Frame ---
                # flush internal cost buffers 
                dummy_img = np.zeros((1520, 2028, 3), dtype=np.uint8)
                rect_L, rect_R = self.stereo.rectify_pair(dummy_img, dummy_img)
                self.stereo.compute_disparity(rect_L, rect_R)
                # -------------------------------------
                
            except Exception as e:
                print(f"No initial calibration found or loaded: {e}")

    def reconstruct(self, bytes_data, image_height=1520, image_width=2028, channels=4):
        expected = image_height * image_width * channels
        if len(bytes_data) != expected:
            raise ValueError(f"Expected {expected} bytes, got {len(bytes_data)}")
        arr = np.frombuffer(bytes_data, dtype=np.uint8)
        arr = arr.reshape((image_height, image_width, channels))
        rgb = arr[:, :, :3]
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

class StereoApp:
    def __init__(self, root, device):
        self.root = root
        self.root.title("Stereo Vision Client")
        self.root.geometry("1200x850")
        self.root.minsize(900, 700)
        self.fullscreen = False

        if HAS_SV_TTK:
            sv_ttk.set_theme("dark")
        else:
            self.apply_fallback_dark_theme()

        self.root.bind("<Escape>", self.exit_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)

        self.device = device
        self.is_running = False
        self.is_connected = False

        self.frame_queue = queue.Queue(maxsize=2)  
        
        # State tracking
        self.current_images = {"left": None, "right": None, "depth": None}
        self.current_data = {"raw_depth": None, "disp_filtered": None, "dispL": None, "dispR": None, "ts": None} 
        self.cached_tk_images = {"left": None, "right": None, "depth": None}
        self.last_sizes = {"main": (0, 0), "thumb1": (0, 0), "thumb2": (0, 0)}
        
        self.last_raw_L = None
        self.last_raw_R = None
        self._resize_job = None
        self._recolor_job = None
        self.is_prompting_save = False
        
        # ROI Drawing State
        self.roi_mode_active = False
        self.roi_start = None
        self.roi_rect_id = None

        # UI Variables
        self.app_mode = tk.StringVar(value="Depth")
        self.vmin_var = tk.DoubleVar(value=10.0)
        self.vmax_var = tk.DoubleVar(value=90.0)
        self.block_size_var = tk.IntVar(value=3)
        self.num_disp_var = tk.IntVar(value=240)
        self.wls_lambda_var = tk.DoubleVar(value=8000.0)
        self.calib_target_var = tk.IntVar(value=40)
        
        self.save_images_var = tk.BooleanVar(value=False)
        self.save_dir_var = tk.StringVar(value="")
        
        self.settings_visible = False
        
        self.setup_ui()

    def apply_fallback_dark_theme(self):
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure(".", background="#2d2d2d", foreground="#ffffff")
        style.configure("TButton", background="#444", foreground="white")
        style.map("TButton", background=[("active", "#555")])
        self.root.configure(bg="#2d2d2d")

    def setup_ui(self):
        # Top connection frame
        self.control_frame = ttk.Frame(self.root)
        self.control_frame.pack(fill=tk.X, pady=5, padx=10)

        # Configurable IP Input
        ttk.Label(self.control_frame, text="IP:").pack(side=tk.LEFT, padx=(0, 2))
        self.ip_var = tk.StringVar(value=self.device.server_host)
        self.ip_entry = ttk.Entry(self.control_frame, textvariable=self.ip_var, width=14)
        self.ip_entry.pack(side=tk.LEFT, padx=(0, 5))

        self.connect_btn = ttk.Button(self.control_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.status_lbl = ttk.Label(self.control_frame, text="Disconnected", foreground="gray")
        self.status_lbl.pack(side=tk.LEFT, padx=5)

        # Mode controls
        self.mode_btn = ttk.Button(self.control_frame, text="Mode: Depth", command=self.toggle_app_mode)
        self.mode_btn.pack(side=tk.LEFT, padx=5)

        self.settings_btn = ttk.Button(self.control_frame, text="Settings \u25BC", command=self.toggle_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=5)

        self.validate_btn = ttk.Button(self.control_frame, text="Select ROI", command=self.toggle_roi_mode)
        self.validate_btn.pack(side=tk.LEFT, padx=5)
        
        self.hover_depth_lbl = ttk.Label(self.control_frame, text="Hover: --", foreground="#00bfff", font=("Arial", 10, "bold"))
        self.hover_depth_lbl.pack(side=tk.LEFT, padx=10)

        self.metrics_lbl = ttk.Label(self.control_frame, text="Metrics: N/A", foreground="#00e676", font=("Arial", 10, "bold"))
        self.metrics_lbl.pack(side=tk.LEFT, padx=5)

        # Settings Master Container
        self.settings_frame = tk.Frame(self.root, bg="#2a2a2a", bd=1, relief=tk.SUNKEN)
        self.settings_frame.columnconfigure(0, weight=1)

        # 1. DEPTH SETTINGS (Vmin, Vmax, Stereo Params)
        self.depth_settings_frame = tk.Frame(self.settings_frame, bg="#2a2a2a")
        self.depth_settings_frame.columnconfigure(1, weight=1)
        
        self.vmin_lbl = tk.Label(self.depth_settings_frame, text="Vmin: 10.0%", bg="#2a2a2a", fg="white", width=20, anchor="w")
        self.vmin_lbl.grid(row=0, column=0, padx=10, pady=5)
        self.vmin_slider = ttk.Scale(self.depth_settings_frame, from_=0, to=100, variable=self.vmin_var, command=self.on_slider_change)
        self.vmin_slider.grid(row=0, column=1, sticky="ew", padx=10)
        
        self.vmax_lbl = tk.Label(self.depth_settings_frame, text="Vmax: 90.0%", bg="#2a2a2a", fg="white", width=20, anchor="w")
        self.vmax_lbl.grid(row=1, column=0, padx=10, pady=5)
        self.vmax_slider = ttk.Scale(self.depth_settings_frame, from_=0, to=100, variable=self.vmax_var, command=self.on_slider_change)
        self.vmax_slider.grid(row=1, column=1, sticky="ew", padx=10)
        
        stereo_params_frame = tk.Frame(self.depth_settings_frame, bg="#2a2a2a")
        stereo_params_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        ttk.Label(stereo_params_frame, text="Block Size:", background="#2a2a2a", foreground="white").pack(side=tk.LEFT, padx=(10, 5))
        self.bs_cb = ttk.Combobox(stereo_params_frame, textvariable=self.block_size_var, values=[3, 5, 7, 9, 11, 15, 21], width=5, state="readonly")
        self.bs_cb.pack(side=tk.LEFT, padx=5)
        ttk.Label(stereo_params_frame, text="Num Disp:", background="#2a2a2a", foreground="white").pack(side=tk.LEFT, padx=(20, 5))
        self.nd_cb = ttk.Combobox(stereo_params_frame, textvariable=self.num_disp_var, values=[16*i for i in range(1, 21)], width=5, state="readonly")
        self.nd_cb.pack(side=tk.LEFT, padx=5)
        ttk.Label(stereo_params_frame, text="WLS Lambda:", background="#2a2a2a", foreground="white").pack(side=tk.LEFT, padx=(20, 5))
        self.wls_entry = ttk.Entry(stereo_params_frame, textvariable=self.wls_lambda_var, width=8)
        self.wls_entry.pack(side=tk.LEFT, padx=5)
        
        self.update_stereo_btn = ttk.Button(stereo_params_frame, text="Update Map", command=self.apply_stereo_settings)
        self.update_stereo_btn.pack(side=tk.LEFT, padx=15)
        
        # Load Calib Button (moved to depth settings)
        self.load_calib_btn = ttk.Button(stereo_params_frame, text="Load Calib", command=self.load_calibration_file)
        self.load_calib_btn.pack(side=tk.LEFT, padx=5)

        # 2. CALIBRATION SETTINGS
        self.calib_settings_frame = tk.Frame(self.settings_frame, bg="#2a2a2a")
        ttk.Label(self.calib_settings_frame, text="Calib Targets:", background="#2a2a2a", foreground="white").pack(side=tk.LEFT, padx=(20, 5), pady=10)
        self.calib_entry = ttk.Entry(self.calib_settings_frame, textvariable=self.calib_target_var, width=5)
        self.calib_entry.pack(side=tk.LEFT, padx=5, pady=10)

        # 3. LOGGING SETTINGS (Always Visible inside settings)
        self.logging_frame = tk.Frame(self.settings_frame, bg="#2a2a2a")
        ttk.Checkbutton(self.logging_frame, text="Save Raw Images", variable=self.save_images_var, style="Dark.TCheckbutton").pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Label(self.logging_frame, text="Dir:", background="#2a2a2a", foreground="white").pack(side=tk.LEFT, pady=5)
        self.logging_entry = ttk.Entry(self.logging_frame, textvariable=self.save_dir_var, width=40)
        self.logging_entry.pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(self.logging_frame, text="Browse", command=self.browse_save_dir).pack(side=tk.LEFT, padx=5, pady=5)

        # Default UI State
        self.depth_settings_frame.grid(row=0, column=0, sticky="ew")
        self.logging_frame.grid(row=1, column=0, sticky="ew")

        # Main Layout
        self.content_frame = tk.Frame(self.root, bg="#1e1e1e")
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 10))
        self.content_frame.columnconfigure(0, weight=3) 
        self.content_frame.columnconfigure(1, weight=1) 
        self.content_frame.rowconfigure(0, weight=1)
        self.content_frame.rowconfigure(1, weight=1)

        self.canvases = {}
        for c_id, row, col, rowspan in [("main", 0, 0, 2), ("thumb1", 0, 1, 1), ("thumb2", 1, 1, 1)]:
            c = tk.Canvas(self.content_frame, bg="#111", highlightthickness=0, cursor="hand2" if "thumb" in c_id else "crosshair")
            c.grid(row=row, column=col, rowspan=rowspan, sticky="nsew", padx=5, pady=5)
            c.bind("<Configure>", self.on_resize)
            c.bind("<Motion>", lambda e, vid=c_id: self.on_hover(e, vid))
            c.bind("<ButtonPress-1>", lambda e, vid=c_id: self.on_canvas_press(e, vid))
            c.bind("<B1-Motion>", lambda e, vid=c_id: self.on_canvas_drag(e, vid))
            c.bind("<ButtonRelease-1>", lambda e, vid=c_id: self.on_canvas_release(e, vid))
            self.canvases[c_id] = c

        self.view_keys = {"main": "depth", "thumb1": "left", "thumb2": "right"}

    def browse_save_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.save_dir_var.set(d)

    def toggle_app_mode(self):
        if self.app_mode.get() == "Depth":
            self.app_mode.set("Calibration")
            self.mode_btn.config(text="Mode: Calibration")
            self.device.calibrating = True
            self.validate_btn.config(state=tk.DISABLED)
            
            if hasattr(self.device.stereo, 'corners_L'):
                self.device.stereo.corners_L = []
                self.device.stereo.corners_R = []
                self.device.stereo.objpoints = []
                self.device.stereo.imgpoints_L = []
                self.device.stereo.imgpoints_R = []
            
            self.canvases["main"].grid_remove()
            self.content_frame.columnconfigure(0, weight=1)
            self.content_frame.columnconfigure(1, weight=1)
            self.canvases["thumb1"].grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)
            self.canvases["thumb2"].grid(row=0, column=1, rowspan=2, sticky="nsew", padx=5, pady=5)
            
            self.view_keys["thumb1"] = "left"
            self.view_keys["thumb2"] = "right"
            
            self.depth_settings_frame.grid_remove()
            self.calib_settings_frame.grid(row=0, column=0, sticky="ew")
            
            self.metrics_lbl.config(text="Calibration Mode: Ready")
            self.current_images["depth"] = None
            self.cached_tk_images["depth"] = None
            self.update_all_images()
        else:
            self.app_mode.set("Depth")
            self.mode_btn.config(text="Mode: Depth")
            self.device.calibrating = False
            self.validate_btn.config(state=tk.NORMAL)
            self.metrics_lbl.config(text="Metrics: N/A")
            
            self.content_frame.columnconfigure(0, weight=3)
            self.content_frame.columnconfigure(1, weight=1)
            self.canvases["main"].grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)
            self.canvases["thumb1"].grid(row=0, column=1, rowspan=1, sticky="nsew", padx=5, pady=5)
            self.canvases["thumb2"].grid(row=1, column=1, rowspan=1, sticky="nsew", padx=5, pady=5)
            
            self.view_keys["main"] = "depth"
            self.view_keys["thumb1"] = "left"
            self.view_keys["thumb2"] = "right"
            
            self.calib_settings_frame.grid_remove()
            self.depth_settings_frame.grid(row=0, column=0, sticky="ew")
            
            self.update_all_images()

    def load_calibration_file(self):
        filepath = filedialog.askopenfilename(title="Select Calibration File", filetypes=[("NPZ Files", "*.npz"), ("All Files", "*.*")])
        if filepath:
            try:
                self.device.stereo.load_calibration_parameters(filepath)
                self.device.calibration_path = filepath
                self.device.calibrating = False
                if self.app_mode.get() == "Calibration":
                    self.toggle_app_mode()
                messagebox.showinfo("Success", f"Calibration loaded:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load calibration:\n{e}")

    def apply_stereo_settings(self):
        if self.app_mode.get() == "Calibration": return
        try:
            bs = self.block_size_var.get()
            nd = self.num_disp_var.get()
            wls_val = float(self.wls_lambda_var.get())
        except (ValueError, tk.TclError):
            messagebox.showwarning("Invalid Input", "Please enter valid numeric values for stereo settings.")
            return
            
        try:
            self.device.reinit_stereo(block_size=bs, num_disp=nd, wls_lambda=wls_val)
        except Exception as e:
            messagebox.showwarning("Initialization Error", f"Could not apply settings.\nDetails: {e}")
            return
            
        if self.last_raw_L is not None and self.last_raw_R is not None:
            with self.frame_queue.mutex:
                self.frame_queue.queue.clear()
            self.frame_queue.put((self.last_raw_L, self.last_raw_R, int(time.time() * 1000)))

    def toggle_settings(self):
        if self.settings_visible:
            self.settings_frame.pack_forget()
            self.settings_btn.config(text="Settings \u25BC")
        else:
            self.settings_frame.pack(fill=tk.X, padx=10, after=self.control_frame)
            self.settings_btn.config(text="Settings \u25B2")
            self.update_slider_labels()
        self.settings_visible = not self.settings_visible

    def on_slider_change(self, *args):
        self.update_slider_labels()
        if self._recolor_job:
            self.root.after_cancel(self._recolor_job)
        self._recolor_job = self.root.after(100, self.recolor_depth_map)

    def update_slider_labels(self):
        v_min_p = self.vmin_var.get()
        v_max_p = self.vmax_var.get()
        
        depth = self.current_data["raw_depth"]
        if depth is not None:
            valid_mask = np.isfinite(depth) & (depth > 0)
            if np.any(valid_mask):
                vmin_m = np.percentile(depth[valid_mask], v_min_p)
                vmax_m = np.percentile(depth[valid_mask], v_max_p)
                self.vmin_lbl.config(text=f"Vmin: {v_min_p:.1f}% ({vmin_m:.2f}m)")
                self.vmax_lbl.config(text=f"Vmax: {v_max_p:.1f}% ({vmax_m:.2f}m)")
                return
                
        self.vmin_lbl.config(text=f"Vmin: {v_min_p:.1f}% (--m)")
        self.vmax_lbl.config(text=f"Vmax: {v_max_p:.1f}% (--m)")

    def canvas_to_raw(self, cx, cy, view_id):
        img_key = self.view_keys.get(view_id)
        if img_key is None or self.current_images.get(img_key) is None: 
            return 0, 0
            
        cv_img = self.current_images[img_key]
        canvas = self.canvases[view_id]
        w, h = canvas.winfo_width(), canvas.winfo_height()
        img_h, img_w = cv_img.shape[:2]
        
        scale = min(w / img_w, h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        pad_x = (w - new_w) // 2
        pad_y = (h - new_h) // 2
        
        raw_x = int((cx - pad_x) / scale)
        raw_y = int((cy - pad_y) / scale)
        
        return max(0, min(img_w - 1, raw_x)), max(0, min(img_h - 1, raw_y))

    def on_canvas_press(self, event, view_id):
        if self.app_mode.get() == "Calibration": return
        if not self.roi_mode_active or self.view_keys[view_id] != "depth":
            if "thumb" in view_id:
                self.swap_main_view(view_id)
            return
            
        self.roi_start = (event.x, event.y)
        canvas = self.canvases[view_id]
        canvas.delete("roi") 
        self.roi_rect_id = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#00ff00", width=2, tags="roi")

    def on_canvas_drag(self, event, view_id):
        if self.roi_mode_active and self.roi_start and self.view_keys[view_id] == "depth":
            self.canvases[view_id].coords(self.roi_rect_id, self.roi_start[0], self.roi_start[1], event.x, event.y)

    def on_canvas_release(self, event, view_id):
        if self.roi_mode_active and self.roi_start and self.view_keys[view_id] == "depth":
            x1, y1 = self.roi_start
            x2, y2 = event.x, event.y
            self.roi_start = None
            
            rx1, ry1 = self.canvas_to_raw(x1, y1, view_id)
            rx2, ry2 = self.canvas_to_raw(x2, y2, view_id)
            
            x = min(rx1, rx2)
            y = min(ry1, ry2)
            w = abs(rx2 - rx1)
            h = abs(ry2 - ry1)
            
            if w > 0 and h > 0:
                self.process_roi(x, y, w, h)
                
            self.toggle_roi_mode() 
            self.canvases[view_id].delete("roi")

    def toggle_roi_mode(self):
        if self.current_data["raw_depth"] is None or self.app_mode.get() == "Calibration":
            messagebox.showwarning("Warning", "No depth map available to validate.")
            return

        self.roi_mode_active = not self.roi_mode_active
        if self.roi_mode_active:
            self.validate_btn.config(text="Cancel ROI")
            self.root.config(cursor="crosshair")
        else:
            self.validate_btn.config(text="Select ROI")
            self.root.config(cursor="")
            for c in self.canvases.values(): c.delete("roi")

    def process_roi(self, x, y, w, h):
        actual_depth = simpledialog.askfloat("Actual Depth", "Enter actual depth (meters):", parent=self.root)
        if actual_depth is None: return

        raw_depth = self.current_data["raw_depth"]
        dispL = self.current_data["dispL"]
        dispR = self.current_data["dispR"]

        roi_depth = raw_depth[y:y+h, x:x+w]
        roi_dispL = dispL[y:y+h, x:x+w]
        roi_dispR = dispR[y:y+h, x:x+w]

        try:
            rmse = depth_rmse(roi_depth, actual_depth)
            noise = spatial_noise(roi_depth)
            lr = median_lr_consistency_error(roi_dispL, roi_dispR)
            
            self.metrics_lbl.config(text=f"RMSE: {rmse*1000:.2f}mm | Noise: {noise*1000:.2f}mm | LR Error: {lr:.2f}px")
        except Exception as e:
            messagebox.showerror("Error", f"Failed calculating metrics.\nDetails: {e}")

    def recolor_depth_map(self):
        if self.current_data["raw_depth"] is None or self.app_mode.get() == "Calibration": return

        depth = self.current_data["raw_depth"]
        valid_mask = np.isfinite(depth) & (depth > 0)
        
        if np.any(valid_mask):
            vmin_val = np.percentile(depth[valid_mask], self.vmin_var.get())
            vmax_val = np.percentile(depth[valid_mask], self.vmax_var.get())
        else:
            vmin_val, vmax_val = 0, 255
            
        self.update_slider_labels()
        
        norm_depth = np.zeros_like(depth, dtype=np.uint8)
        
        if vmax_val > vmin_val and np.any(valid_mask):
            clipped_valid = np.clip(depth[valid_mask], vmin_val, vmax_val)
            norm_depth[valid_mask] = ((clipped_valid - vmin_val) / (vmax_val - vmin_val) * 255).astype(np.uint8)
            
        depth_color = cv2.applyColorMap(norm_depth, cv2.COLORMAP_TURBO)
        depth_color[~valid_mask] = [0, 0, 0] 
        
        self.draw_colorbar(depth_color, vmin_val, vmax_val)

        # Attempt to save Depth map if setting is toggled
        if self.save_images_var.get() and self.save_dir_var.get():
            try:
                save_d = self.save_dir_var.get()
                if os.path.isdir(save_d):
                    # Use synchronized timestamp from network frame
                    ts = self.current_data.get("ts", int(time.time() * 1000))
                    # Save both colorized PNG and raw NPY array for post-processing
                    np.save(os.path.join(save_d, f"DepthRaw_{ts}.npy"), depth)
            except Exception as e:
                print(f"Failed logging depth map: {e}")

        self.current_images["depth"] = depth_color
        self.cached_tk_images["depth"] = None 
        self.update_all_images()

    def draw_colorbar(self, image, vmin_val, vmax_val):
        h, w = image.shape[:2]
        cb_w = max(20, int(w * 0.03))
        cb_h = int(h * 0.6)
        cb_x = w - cb_w - 20
        cb_y = (h - cb_h) // 2
        
        gradient = np.linspace(255, 0, cb_h, dtype=np.uint8)
        gradient = np.tile(gradient, (cb_w, 1)).T
        gradient_col = cv2.applyColorMap(gradient, cv2.COLORMAP_TURBO)
        
        image[cb_y:cb_y+cb_h, cb_x:cb_x+cb_w] = gradient_col
        cv2.rectangle(image, (cb_x, cb_y), (cb_x + cb_w, cb_y + cb_h), (255, 255, 255), 1)

        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 1.25, 2
        for val, y_pos in [(vmax_val, cb_y - 15), (vmin_val, cb_y + 35 + cb_h)]:
            text = f"{val:.2f}m"
            cv2.putText(image, text, (cb_x - 65, y_pos), font, scale, (0, 0, 0), thick + 2)
            cv2.putText(image, text, (cb_x - 65, y_pos), font, scale, (255, 255, 255), thick)

    def on_hover(self, event, view_id):
        # Fix: Safely check if current depth map exists before attempting shape operations
        if self.view_keys.get(view_id) != "depth" or self.current_data.get("raw_depth") is None or self.app_mode.get() == "Calibration":
            self.hover_depth_lbl.config(text="Hover: --")
            return
            
        cv_img = self.current_images.get("depth")
        if cv_img is None:
            self.hover_depth_lbl.config(text="Hover: --")
            return
            
        rx, ry = self.canvas_to_raw(event.x, event.y, view_id)
        img_w, img_h = cv_img.shape[1], cv_img.shape[0]
        
        if 0 <= rx < img_w and 0 <= ry < img_h:
            depth_val = self.current_data["raw_depth"][ry, rx]
            if np.isfinite(depth_val) and depth_val > 0:
                self.hover_depth_lbl.config(text=f"Hover: {depth_val:.3f} m")
                return
                
        self.hover_depth_lbl.config(text="Hover: Invalid")

    def swap_main_view(self, clicked_thumb_id):
        if self.app_mode.get() == "Calibration": return
        current_main = self.view_keys["main"]
        self.view_keys["main"] = self.view_keys[clicked_thumb_id]
        self.view_keys[clicked_thumb_id] = current_main
        
        for c in self.canvases.values(): c.delete("roi")
        self.last_sizes = {"main": (0,0), "thumb1": (0,0), "thumb2": (0,0)}
        self.update_all_images()

    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes('-fullscreen', self.fullscreen)

    def exit_fullscreen(self, event=None):
        self.fullscreen = False
        self.root.attributes('-fullscreen', False)

    def toggle_connection(self):
        if not self.is_running:
            new_ip = self.ip_var.get()
            self.device.server_host = new_ip
            self.device.client = ImageClient(new_ip, self.device.server_port)
            
            self.connect_btn.config(state=tk.DISABLED, text="Connecting...")
            self.ip_entry.config(state=tk.DISABLED) 
            
            self.is_running = True
            threading.Thread(target=self.network_receive_loop, daemon=True).start()
            threading.Thread(target=self.stereo_processing_loop, daemon=True).start()
        else:
            self.is_running = False
            if self.is_connected:
                try:
                    self.device.client.disconnect()
                except Exception as e:
                    print(f"Error calling disconnect: {e}")
            
            self.connect_btn.config(text="Connect", state=tk.NORMAL)
            self.ip_entry.config(state=tk.NORMAL)
            self.status_lbl.config(text="Disconnected", foreground="gray")
            self.is_connected = False

    def network_receive_loop(self):
        while self.is_running:
            try:
                if not self.is_connected:
                    self.device.client.connect()
                    self.is_connected = True
                    self.root.after(0, lambda: self.connect_btn.config(text="Disconnect", state=tk.NORMAL))
                    self.root.after(0, lambda: self.status_lbl.config(text="Connected", foreground="#00ff00"))
                
                imgL_bytes, imgR_bytes = self.device.client.receive_images()
                imgL = self.device.reconstruct(imgL_bytes)
                imgR = self.device.reconstruct(imgR_bytes)
                
                self.last_raw_L = imgL.copy()
                self.last_raw_R = imgR.copy()
                
                ts = int(time.time() * 1000)
                if self.save_images_var.get() and self.save_dir_var.get():
                    try:
                        save_d = self.save_dir_var.get()
                        if self.app_mode.get() == "Calibration":
                            save_d = os.path.join(save_d, "received_calibration")
                        else:
                            save_d = os.path.join(save_d, "received_depth")
                            
                        if os.path.isdir(save_d):
                            pass
                        else:
                            os.makedirs(save_d, exist_ok=True)
                            
                        cv2.imwrite(os.path.join(save_d, f"left_image_{ts}.png"), self.last_raw_L)
                        cv2.imwrite(os.path.join(save_d, f"right_image_{ts}.png"), self.last_raw_R)
                    except Exception as e:
                        print(f"Failed logging images: {e}")

                imgL_disp = imgL.copy()
                imgR_disp = imgR.copy()
                
                cv2.putText(imgL_disp, "L", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 4, (0, 255, 0), 5)
                cv2.putText(imgR_disp, "R", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 4, (0, 255, 0), 5)

                self.current_images["left"] = imgL_disp
                self.current_images["right"] = imgR_disp
                
                self.cached_tk_images["left"] = None 
                self.cached_tk_images["right"] = None 
                self.root.after(0, self.update_all_images)
                
                if not self.frame_queue.full() and not self.is_prompting_save:
                    self.frame_queue.put((self.last_raw_L, self.last_raw_R, ts))
                    
            except Exception as e:
                if self.is_running:
                    self.is_connected = False
                    self.root.after(0, lambda: self.status_lbl.config(text="Connection lost...", foreground="orange"))
                    time.sleep(2)
                else:
                    break

        self.is_connected = False
        self.root.after(0, lambda: self.connect_btn.config(text="Connect", state=tk.NORMAL))
        self.root.after(0, lambda: self.ip_entry.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.status_lbl.config(text="Disconnected", foreground="gray"))

    def stereo_processing_loop(self):
        while self.is_running:
            if self.is_prompting_save:
                time.sleep(0.1)
                continue
                
            try:
                queue_item = self.frame_queue.get(timeout=1)
                if len(queue_item) == 3:
                    imgL, imgR, ts = queue_item
                else:
                    imgL, imgR = queue_item
                    ts = int(time.time() * 1000)
                
                # --- CALIBRATION MODE ---
                if self.app_mode.get() == "Calibration":
                    target_num = self.calib_target_var.get()
                    current_count = len(getattr(self.device.stereo, 'corners_L', []))
                    
                    if current_count < target_num:
                        retL, cornersL, retR, cornersR = self.device.stereo.find_calibration_corners(imgL, imgR, display=False)
                        if retL or retR:
                            current_count = len(self.device.stereo.corners_L)
                            msg = f"Calibrating: Found pair {current_count}/{target_num}"
                            print(msg)
                            self.root.after(0, lambda m=msg: self.metrics_lbl.config(text=m, foreground="#00e676"))
                            
                            imgL_disp = self.current_images["left"].copy()
                            imgR_disp = self.current_images["right"].copy()
                            
                            pattern_size = getattr(self.device.stereo, 'chessboard_size')
                            print(f"Pattern size for corner drawing: {pattern_size}")
                            if retL:
                                print("drawing corners on left image")
                                cv2.drawChessboardCorners(imgL_disp, pattern_size, cornersL, retL)
                            if retR:
                                print("drawing corners on right image")
                                cv2.drawChessboardCorners(imgR_disp, pattern_size, cornersR, retR)
                                
                            self.current_images["left"] = imgL_disp
                            self.current_images["right"] = imgR_disp
                            self.cached_tk_images["left"] = None 
                            self.cached_tk_images["right"] = None
                            self.root.after(0, self.update_all_images)
                            
                            if current_count >= target_num:
                                self.is_prompting_save = True
                                with self.frame_queue.mutex:
                                    self.frame_queue.queue.clear()
                                self.root.after(0, self.finalize_calibration)
                                
                        else:
                            msg = f"Calibrating: {current_count}/{target_num} (No corners found)"
                            self.root.after(0, lambda m=msg: self.metrics_lbl.config(text=m, foreground="orange"))
                            
                    elif not self.is_prompting_save:
                        self.is_prompting_save = True
                        with self.frame_queue.mutex:
                            self.frame_queue.queue.clear()
                        self.root.after(0, self.finalize_calibration)
                        
                # --- DEPTH MODE ---
                elif not self.device.calibrating:
                    rectified_L, rectified_R = self.device.stereo.rectify_pair(imgL, imgR)
                    disp_filtered, dispL, dispR = self.device.stereo.compute_disparity(rectified_L, rectified_R)
                    depth = self.device.stereo.disparity_to_depth(disp_filtered)
                    
                    self.current_data["raw_depth"] = depth
                    self.current_data["disp_filtered"] = disp_filtered
                    self.current_data["dispL"] = dispL
                    self.current_data["dispR"] = dispR
                    self.current_data["ts"] = ts
                    
                    self.root.after(0, self.recolor_depth_map)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing error: {e}")

    def finalize_calibration(self):
        """Runs the math-heavy calibration function and prompts the user to save"""
        self.metrics_lbl.config(text="Calculating... Please wait.", foreground="yellow")
        self.root.update()
        
        try:
            self.device.stereo.calibrate_stereo_system()
            self.device.stereo.generate_rectification_maps()
            
            baseline = 1.0 / self.device.stereo.Q[3, 2] if hasattr(self.device.stereo, 'Q') else 0
            retL = getattr(self.device.stereo, 'retL', 0)
            retR = getattr(self.device.stereo, 'retR', 0)
            stereo_ret = getattr(self.device.stereo, 'stereo_ret', 0)
            
            print(f"Baseline: {baseline*100:.2f} centimeters")
            print(f"Left reprojection error: {retL:.2f}px")
            print(f"Right reprojection error: {retR:.2f}px")
            print(f"Stereo reprojection error: {stereo_ret:.2f}px")
            
            filename = simpledialog.askstring(
                "Save Calibration", 
                f"Calibration Complete!\nBaseline: {baseline*100:.2f}cm\nStereo Error: {stereo_ret:.2f}px\n\nEnter save filename:", 
                initialvalue="calibration_params.npz", 
                parent=self.root
            )
            
            if filename:
                if not filename.endswith('.npz'):
                    filename += '.npz'
                self.device.stereo.save_calibration_parameters(filename)
                self.device.calibration_path = filename
                messagebox.showinfo("Saved", f"Calibration successfully saved to:\n{filename}")
                
        except Exception as e:
            messagebox.showerror("Calibration Error", f"Failed to compute calibration:\n{e}")
        finally:
            self.is_prompting_save = False
            if self.app_mode.get() == "Calibration":
                self.toggle_app_mode() 

    def update_all_images(self):
        for view_id, img_key in self.view_keys.items():
            if view_id not in self.canvases or self.canvases[view_id].winfo_manager() == "":
                continue 
                
            canvas = self.canvases[view_id]
            cv_img = self.current_images.get(img_key)
            
            w, h = canvas.winfo_width(), canvas.winfo_height()
            
            if cv_img is not None and w > 10 and h > 10:
                last_w, last_h = self.last_sizes[view_id]
                
                if abs(w - last_w) > 5 or abs(h - last_h) > 5 or self.cached_tk_images.get(img_key) is None:
                    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                    img_h, img_w = rgb_img.shape[:2]
                    scale = min(w / img_w, h / img_h)
                    new_dim = (max(1, int(img_w * scale)), max(1, int(img_h * scale)))
                    
                    resized = cv2.resize(rgb_img, new_dim, interpolation=cv2.INTER_AREA)
                    pil_img = Image.fromarray(resized)
                    self.cached_tk_images[img_key] = ImageTk.PhotoImage(image=pil_img)
                    self.last_sizes[view_id] = (w, h)
                
                canvas.delete("img")
                canvas.create_image(w//2, h//2, anchor=tk.CENTER, image=self.cached_tk_images[img_key], tags="img")
                canvas.tag_lower("img") 

    def on_resize(self, event):
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(100, self.update_all_images)


if __name__ == "__main__":
    device = StereoClientDevice(server_host='192.168.137.79', calibrating=False, calibraton_params_file="calibration_parameters/calibration_params_60mm.npz")
    root = tk.Tk()
    app = StereoApp(root, device)

    def on_closing():
        app.is_running = False
        if app.is_connected:
            try:
                device.client.disconnect()
            except:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()