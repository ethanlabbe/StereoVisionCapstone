import os
import cv2
import datetime
import threading
import netifaces
import numpy as np

from image_transfer import ImageServerHost
from acquisition import StereoCameraAcquisition
from stereo_class_ethan import StereoSystem

#ui imports
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QGridLayout, QWidget, QLabel, QLineEdit, QHBoxLayout
from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QImage
from picamera2.previews.qt import QGlPicamera2

UI_HEIGHT=600
UI_WIDTH=1024

LBL_STYLE = "background-color: #2b2b2b; color: #ffffff; border: 2px solid #555555; border-radius: 10px; font-size: 18px; font-weight: bold;"

BTN_STYLE = """
QPushButton {
    background-color: #2b2b2b; color: #ffffff; border: 2px solid #555555; border-radius: 10px; font-size: 18px; font-weight: bold;
}
QPushButton:pressed {
    background-color: #555555; border: 2px solid #ffffff; color: #ffffff;
}
"""

BTN_STYLE_LG = """
QPushButton {
    background-color: #2b2b2b; color: #ffffff; border: 2px solid #555555; border-radius: 10px; font-size: 20px; font-weight: bold;
}
QPushButton:pressed {
    background-color: #555555; border: 2px solid #ffffff; color: #ffffff;
}
"""

class TransmissionSignals(QObject):
    update_lights = pyqtSignal(bool, bool, bool, bool)
    update_calib_count = pyqtSignal(int)
    show_depth_map = pyqtSignal(object) # For passing the numpy depth image to the main thread

class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False
        self.ipaddress = netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
        self.server = ImageServerHost(host=self.ipaddress, port=8080)
        self.stereo_system = StereoCameraAcquisition()
        self.folder_path=""
        self.img_number = 0
        
        # Local Stereo processing system
        self.local_stereo = None
        self.local_stereo = StereoSystem(block_size=3, num_disp=16*15, wls_lambda=8000.0)
        try:
            self.local_stereo.load_calibration_parameters("calibration_parameters/calibration_params_60mm.npz")
        except Exception as e:
            print(f"No local calibration found: {e}")

        # State variables for modes and status lights
        self.current_mode = None
        self.calibration_count = 0
        self.is_capturing = False
        self.is_transferring = False

        self.signals = TransmissionSignals()
        self.signals.update_lights.connect(self._update_lights_safe)
        self.signals.update_calib_count.connect(self._update_calib_count_safe)
        self.signals.show_depth_map.connect(self._display_depth_map_safe)
        
        self.server.on_send_start = self._handle_send_start
        self.server.on_send_complete = self._handle_send_complete

    def _handle_send_start(self):
        self.is_transferring = True
        self.emit_lights_update()

    def _handle_send_complete(self):
        self.is_transferring = False
        self.emit_lights_update()

    def _update_lights_safe(self, server_on, client_on, capture_on, transfer_on):
        green = "background-color: #4CAF50; border-radius: 7px; border: 1px solid #222;"
        red = "background-color: #F44336; border-radius: 7px; border: 1px solid #222;"
        gray = "background-color: #555555; border-radius: 7px; border: 1px solid #222;"
        yellow = "background-color: #FFC107; border-radius: 7px; border: 1px solid #222;"
        blue = "background-color: #2196F3; border-radius: 7px; border: 1px solid #222;"

        self.led_server.setStyleSheet(green if server_on else red)
        self.led_client.setStyleSheet(green if client_on else red)
        self.led_capture.setStyleSheet(yellow if capture_on else gray)
        self.led_transfer.setStyleSheet(blue if transfer_on else gray)

    def _update_calib_count_safe(self, count):
        self.calibration_counter_label.setText(f"Calibration Images: {count}")

    def emit_lights_update(self):
        server_status = getattr(self.server, '_running', False)
        client_status = getattr(self.server, 'connected', False)
        self.signals.update_lights.emit(server_status, client_status, self.is_capturing, self.is_transferring)

    def save_images_locally(self, left_image, right_image, left_filename="left_image.jpg", right_filename="right_image.jpg", folder="simonspi/Desktop/images"):
        time_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(folder + "/" + left_filename + "_" + time_stamp, cv2.cvtColor(left_image, cv2.COLOR_RGB2BGR))
        cv2.imwrite(folder + "/" + right_filename + "_" + time_stamp, cv2.cvtColor(right_image, cv2.COLOR_RGB2BGR))
        print(f"Images saved locally")

    def toggle_server(self):
        if self.server._running:
            self.server.stop_server()
            self.server_button.setText("Start Server")
        else:
            self.server.start_server()
            self.server_button.setText("Stop Server")
        self.emit_lights_update()

    def run(self):
        self.running = True
        self.stereo_system.initialize_cameras()

        self.folder_path = "rpi/desktop/images/" + 'temp'
        if not os.path.exists(self.folder_path):
            try:
                os.makedirs(self.folder_path)
            except Exception as e:
                print("Failed to create folder:", e)
                self.folder_path = "rpi/desktop/images/"

    def image_capture(self):
        self.capture_button.hide() # Disable capture until complete
        capture_thread = threading.Thread(target=self._do_capture)
        capture_thread.start()

    def _do_capture(self):
        self.is_capturing = True
        self.emit_lights_update()
        
        imgL, imgR = self.stereo_system.capture_stereo_image()
        self.img_number += 1
        current_id = self.img_number 
        
        if self.current_mode == 'calibration':
            self.calibration_count += 1
            self.signals.update_calib_count.emit(self.calibration_count)
            self.capture_button.show()
            
        elif self.current_mode == 'local':
            self._compute_local_depth(imgL, imgR)
            
        elif self.current_mode == 'capture':
            if self.server.connected:
                try:
                    print(f"Queuing image {current_id} to client...")
                    self.server.send_images(imgL, imgR)
                except Exception as e:
                    print("Failed to queue images:", e)
                    self.save_images_locally(imgL, imgR)
            else:
                self.save_images_locally(imgL, imgR)
            self.capture_button.show()
            
        self.is_capturing = False
        self.emit_lights_update()

    def _compute_local_depth(self, imgL, imgR):
        if not self.local_stereo:
            print("StereoSystem not loaded.")
            return

        try:
            # Get settings from local settings UI
            bs = int(self.bs_input.text()) if self.bs_input.text().isdigit() else 3
            nd = int(self.nd_input.text()) if self.nd_input.text().isdigit() else 240
            wls = float(self.wls_input.text()) if self.wls_input.text().replace('.','',1).isdigit() else 8000.0
            vmin = float(self.vmin_input.text()) if self.vmin_input.text().replace('.','',1).isdigit() else 10.0
            vmax = float(self.vmax_input.text()) if self.vmax_input.text().replace('.','',1).isdigit() else 90.0

            # Re-init system with custom settings if necessary (Assuming you have a method for this, otherwise defaults)
            self.local_stereo.block_size = bs
            self.local_stereo.num_disp = nd
            self.local_stereo.wls_lambda = wls

            # Compute depth pipeline
            rectifiedL, rectifiedR = self.local_stereo.rectify_pair(imgL, imgR)
            disp_filtered, dispL, dispR = self.local_stereo.compute_disparity(rectifiedL, rectifiedR)
            depth = self.local_stereo.disparity_to_depth(disp_filtered)

            # Apply Colormap based on vmin/vmax
            valid_mask = np.isfinite(depth) & (depth > 0)
            norm_depth = np.zeros_like(depth, dtype=np.uint8)
            
            if vmax > vmin and np.any(valid_mask):
                clipped = np.clip(depth[valid_mask], vmin, vmax)
                norm_depth[valid_mask] = ((clipped - vmin) / (vmax - vmin) * 255).astype(np.uint8)
            
            depth_color = cv2.applyColorMap(norm_depth, cv2.COLORMAP_JET)
            depth_color[~valid_mask] = [0, 0, 0] # Make invalid pixels black
            
            # Send the resulting color image to the main UI thread safely
            self.signals.show_depth_map.emit(depth_color)
            
        except Exception as e:
            print(f"Error computing local depth: {e}")
            self.capture_button.show() # Reset capture button on failure

    def _display_depth_map_safe(self, depth_image_bgr):
        # Hide live feeds
        self.qpicamera2.hide()
        self.qpicamera_right.hide()
        
        # Convert cv2 BGR image to QPixmap
        rgb_image = cv2.cvtColor(depth_image_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)

        # Scale to fit UI while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(UI_WIDTH, UI_HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.depth_view_label.setPixmap(scaled_pixmap)
        self.depth_view_label.show()
        
        # Hide settings and show the 'Done' button
        if self.local_settings_panel.isVisible():
            self.toggle_local_settings()
            
        self.settings_button.hide()
        self.done_button.raise_()
        self.done_button.show()

    def close_depth_viewer(self):
        self.depth_view_label.hide()
        self.done_button.hide()
        self.settings_button.show()
        self.capture_button.show()
        
        # Restore camera preview
        self.qpicamera2.show()

    def change_fps(self):
        print("Change FPS button clicked - functionality not implemented yet")

    def fake_quitting(self):
        self.current_mode = None
            
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
        if self.local_settings_panel.isVisible():
            self.local_settings_panel.hide()
            
        self.status_panel.hide()
        self.capture_button.hide()
        self.settings_button.hide()
        self.qpicamera2.hide()
        self.qpicamera_right.hide()
        self.calibration_counter_label.hide()
        self.depth_view_label.hide()
        self.done_button.hide()

        self.logo_label.show()
        self.calibrate_btn.show()
        self.start_capture_btn.show()
        self.run_locally_btn.show()
        self.quit_button.show()
        
        self.central_widget.repaint()

    def real_quitting(self):
        self.stereo_system.stop()
        self.server.stop_server()
        self.app.quit()

    def _create_input_row(self, parent, label_text, default_val):
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 0, 10, 0)
        
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        lbl.setFixedWidth(120)
        
        entry = QLineEdit(str(default_val))
        entry.setStyleSheet("background-color: #333; color: white; border: 1px solid #555; border-radius: 5px; padding: 5px; font-size: 16px;")
        
        layout.addWidget(lbl)
        layout.addWidget(entry)
        return row, entry

    def init_settingui(self):
        # ---------------- Server Mode Settings ----------------
        self.settings_panel = QWidget(self.central_widget)
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setStyleSheet("QWidget#settingsPanel { background-color: rgba(25, 25, 25, 240); border: 2px solid #555555; border-radius: 15px; }")
        self.settings_panel.setGeometry(int((UI_WIDTH-350)/2), 100, 350, 400)
        self.settings_panel.hide()

        self.ip_label = QLabel(f"IP: {self.ipaddress}", parent=self.settings_panel)
        self.ip_label.setStyleSheet(LBL_STYLE)
        self.ip_label.setAlignment(Qt.AlignCenter)
        self.ip_label.setFixedSize(250, 60)
        self.ip_label.move(50, 20) 

        self.fps_select = QPushButton(text="Change FPS", parent=self.settings_panel)
        self.fps_select.clicked.connect(self.change_fps)
        self.fps_select.setStyleSheet(BTN_STYLE)
        self.fps_select.setFixedSize(250, 60)
        self.fps_select.move(50, 100)

        self.server_button = QPushButton(text="Start Server", parent=self.settings_panel)
        self.server_button.clicked.connect(self.toggle_server)
        self.server_button.setStyleSheet(BTN_STYLE)
        self.server_button.setFixedSize(250, 60)
        self.server_button.move(50, 180) 

        self.capture_quit_button = QPushButton(text="Back to Start", parent=self.settings_panel)
        self.capture_quit_button.clicked.connect(self.fake_quitting)
        self.capture_quit_button.setStyleSheet(BTN_STYLE)
        self.capture_quit_button.setFixedSize(150, 50)
        self.capture_quit_button.move(100, 260) 

        self.close_settings_btn = QPushButton(text="Close Settings", parent=self.settings_panel)
        self.close_settings_btn.clicked.connect(self.toggle_settings)
        self.close_settings_btn.setStyleSheet(BTN_STYLE)
        self.close_settings_btn.setFixedSize(150, 40)
        self.close_settings_btn.move(100, 330)

        # ---------------- Local Mode Settings ----------------
        self.local_settings_panel = QWidget(self.central_widget)
        self.local_settings_panel.setObjectName("localSettingsPanel")
        self.local_settings_panel.setStyleSheet("QWidget#localSettingsPanel { background-color: rgba(25, 25, 25, 240); border: 2px solid #555555; border-radius: 15px; }")
        self.local_settings_panel.setGeometry(int((UI_WIDTH-350)/2), 60, 350, 480)
        self.local_settings_panel.hide()
        
        lbl_title = QLabel("Local Processing Settings", parent=self.local_settings_panel)
        lbl_title.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setGeometry(50, 15, 250, 30)

        r1, self.bs_input = self._create_input_row(self.local_settings_panel, "Block Size", 3)
        r1.setGeometry(20, 60, 310, 40)
        
        r2, self.nd_input = self._create_input_row(self.local_settings_panel, "Num Disp", 240)
        r2.setGeometry(20, 110, 310, 40)
        
        r3, self.wls_input = self._create_input_row(self.local_settings_panel, "WLS Lambda", 8000.0)
        r3.setGeometry(20, 160, 310, 40)
        
        r4, self.vmin_input = self._create_input_row(self.local_settings_panel, "Vmin", 10.0)
        r4.setGeometry(20, 210, 310, 40)
        
        r5, self.vmax_input = self._create_input_row(self.local_settings_panel, "Vmax", 90.0)
        r5.setGeometry(20, 260, 310, 40)

        self.local_quit_button = QPushButton(text="Back to Start", parent=self.local_settings_panel)
        self.local_quit_button.clicked.connect(self.fake_quitting)
        self.local_quit_button.setStyleSheet(BTN_STYLE)
        self.local_quit_button.setGeometry(100, 330, 150, 50)

        self.close_local_btn = QPushButton(text="Close Settings", parent=self.local_settings_panel)
        self.close_local_btn.clicked.connect(self.toggle_local_settings)
        self.close_local_btn.setStyleSheet(BTN_STYLE)
        self.close_local_btn.setGeometry(100, 400, 150, 40)


    def toggle_settings(self):
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
            self.capture_button.show()
            self.central_widget.repaint() 
        else:
            self.server_button.setText("Stop Server" if getattr(self.server, '_running', False) else "Start Server")
            self.settings_panel.raise_() 
            self.settings_panel.show()
            self.capture_button.hide()

    def toggle_local_settings(self):
        if self.local_settings_panel.isVisible():
            self.local_settings_panel.hide()
            self.capture_button.show()
            self.central_widget.repaint() 
        else:
            self.local_settings_panel.raise_() 
            self.local_settings_panel.show()
            self.capture_button.hide()

    def toggle_active_settings(self):
        if self.current_mode == 'local':
            self.toggle_local_settings()
        else:
            self.toggle_settings()

    def init_status_lights(self):
        self.status_panel = QWidget(self.central_widget)
        self.status_panel.setGeometry(10, 45, 120, 110)
        self.status_panel.setStyleSheet("background-color: transparent;")
        
        def create_indicator(y_pos, text):
            led = QLabel(self.status_panel)
            led.setGeometry(5, y_pos, 14, 14)
            led.setStyleSheet("background-color: #555555; border-radius: 7px; border: 1px solid #222;")
            
            lbl = QLabel(text, self.status_panel)
            lbl.setGeometry(25, y_pos - 3, 90, 20)
            lbl.setStyleSheet("color: white; font-size: 10px; font-weight: bold; background: transparent;")
            return led
            
        self.led_server = create_indicator(10, "Server Status")
        self.led_client = create_indicator(35, "Client Link")
        self.led_capture = create_indicator(60, "Capturing")
        self.led_transfer = create_indicator(85, "Transferring")
        
        self.status_panel.hide()

    def init_capture_ui(self):
        self.qpicamera2 = QGlPicamera2(self.stereo_system.left_camera, width=UI_WIDTH, height=UI_HEIGHT, keep_ar=True)
        self.qpicamera2.setParent(self.central_widget)
        self.qpicamera2.hide() 

        self.qpicamera_right = QGlPicamera2(self.stereo_system.right_camera, width=UI_WIDTH, height=UI_HEIGHT, keep_ar=True)
        self.qpicamera_right.setParent(self.central_widget)
        self.qpicamera_right.hide()

        # Label to hold the generated depth map
        self.depth_view_label = QLabel(self.central_widget)
        self.depth_view_label.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)
        self.depth_view_label.setAlignment(Qt.AlignCenter)
        self.depth_view_label.hide()

        self.stereo_system.start()
        self.init_status_lights()

        self.calibration_counter_label = QLabel(f"Calibration Images: {self.calibration_count}", parent=self.central_widget)
        self.calibration_counter_label.setStyleSheet("background-color: rgba(43, 43, 43, 200); color: #ffffff; border: 2px solid #555555; border-radius: 10px; font-size: 20px; font-weight: bold;")
        self.calibration_counter_label.setAlignment(Qt.AlignCenter)
        self.calibration_counter_label.setFixedSize(250, 50)
        self.calibration_counter_label.move(int((UI_WIDTH - 250) / 2), 20) 
        self.calibration_counter_label.hide()

        self.capture_button = QPushButton(text="Capture", parent=self.central_widget)
        self.capture_button.clicked.connect(self.image_capture)
        self.capture_button.setStyleSheet(BTN_STYLE_LG)
        self.capture_button.setFixedSize(200, 80)
        self.capture_button.move(UI_WIDTH - 200 - 20, UI_HEIGHT - 80 - 20) 
        self.capture_button.hide() 

        self.done_button = QPushButton(text="Done", parent=self.central_widget)
        self.done_button.clicked.connect(self.close_depth_viewer)
        self.done_button.setStyleSheet(BTN_STYLE_LG)
        self.done_button.setFixedSize(200, 80)
        self.done_button.move(UI_WIDTH - 200 - 20, UI_HEIGHT - 80 - 20) 
        self.done_button.hide()

        self.settings_button = QPushButton(parent=self.central_widget)
        self.settings_button.clicked.connect(self.toggle_active_settings)
        self.settings_button.setStyleSheet("""
        QPushButton {
            background-color: #2b2b2b; border: 2px solid #555555; border-radius: 25px;
        }
        QPushButton:pressed {
            background-color: #555555; border: 2px solid #ffffff;
        }
        """)
        self.settings_button.setIcon(QIcon("UI/gear_icon.png"))
        self.settings_button.setIconSize(QSize(30, 30))
        self.settings_button.setFixedSize(50, 50)
        self.settings_button.move(UI_WIDTH - 70, 45) 
        self.settings_button.hide() 

    def calibration_ui(self):
        self.current_mode = 'calibration'
        self.logo_label.hide()
        self.calibrate_btn.hide()
        self.start_capture_btn.hide()
        self.run_locally_btn.hide()
        self.quit_button.hide()

        if not getattr(self.server, '_running', False):
            self.server.start_server()
            self.emit_lights_update()

        half_width = int(UI_WIDTH / 2)
        self.qpicamera2.setGeometry(0, 0, half_width, UI_HEIGHT)
        self.qpicamera_right.setGeometry(half_width, 0, half_width, UI_HEIGHT)
        self.qpicamera2.show()
        self.qpicamera_right.show()

        self.capture_button.show()
        self.settings_button.raise_()
        self.settings_button.show()
        self.status_panel.raise_()
        self.status_panel.show()
        self.calibration_counter_label.raise_()
        self.calibration_counter_label.show()

    def capture_ui(self):
        self.current_mode = 'capture'
        self.logo_label.hide()
        self.calibrate_btn.hide()
        self.start_capture_btn.hide()
        self.run_locally_btn.hide()
        self.quit_button.hide()

        if not getattr(self.server, '_running', False):
            self.server.start_server()
            self.emit_lights_update()

        self.qpicamera2.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)
        self.qpicamera2.show()
        self.qpicamera_right.hide() 
        self.calibration_counter_label.hide()

        self.capture_button.show()
        self.settings_button.raise_()
        self.settings_button.show()
        self.status_panel.raise_()
        self.status_panel.show()

    def run_locally_ui(self):
        self.current_mode = 'local'
        self.logo_label.hide()
        self.calibrate_btn.hide()
        self.start_capture_btn.hide()
        self.run_locally_btn.hide()
        self.quit_button.hide()

        # Turn OFF the server when moving to Local compute mode
        if getattr(self.server, '_running', False):
            self.server.stop_server()
            self.emit_lights_update()

        self.qpicamera2.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)
        self.qpicamera2.show()
        self.qpicamera_right.hide() 
        self.calibration_counter_label.hide()

        self.capture_button.show()
        self.settings_button.raise_()
        self.settings_button.show()
        self.status_panel.raise_()
        self.status_panel.show()

    def UI_start(self):
        self.app = QApplication(sys.argv)
        rpiUI= QMainWindow()
        rpiUI.setWindowTitle("Stereo Vision Capstone")
        rpiUI.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)

        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("background-color: #121212;")
        rpiUI.setCentralWidget(self.central_widget)

        self.logo_label = QLabel(self.central_widget)
        self.logo_label.setPixmap(QPixmap("UI/stereo_vision_logo.png"))
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setGeometry(int((UI_WIDTH - 600)/2), 20, 600, 350)

        btn_width = 200
        btn_height = 60
        spacing = 30
        start_x = int((UI_WIDTH - (3*btn_width + 2*spacing)) / 2)
        btn_y = 420 

        self.calibrate_btn = QPushButton(text="Start Calibration", parent=self.central_widget)
        self.calibrate_btn.clicked.connect(self.calibration_ui)
        self.calibrate_btn.setStyleSheet(BTN_STYLE_LG)
        self.calibrate_btn.setFixedSize(btn_width, btn_height)
        self.calibrate_btn.move(start_x, btn_y)

        self.start_capture_btn = QPushButton(text="Start Capture", parent=self.central_widget)
        self.start_capture_btn.clicked.connect(self.capture_ui)
        self.start_capture_btn.setStyleSheet(BTN_STYLE_LG)
        self.start_capture_btn.setFixedSize(btn_width, btn_height)
        self.start_capture_btn.move(start_x + btn_width + spacing, btn_y) 

        self.run_locally_btn = QPushButton(text="Run Locally", parent=self.central_widget)
        self.run_locally_btn.clicked.connect(self.run_locally_ui)
        self.run_locally_btn.setStyleSheet(BTN_STYLE_LG)
        self.run_locally_btn.setFixedSize(btn_width, btn_height)
        self.run_locally_btn.move(start_x + 2*(btn_width + spacing), btn_y)

        self.quit_button = QPushButton(text="Exit", parent=self.central_widget)
        self.quit_button.clicked.connect(self.real_quitting)
        self.quit_button.setStyleSheet(BTN_STYLE)
        self.quit_button.setFixedSize(100, 50)
        self.quit_button.move(int((UI_WIDTH-100)/2), UI_HEIGHT - 70) 

        self.init_capture_ui()
        self.init_settingui()

        self.status_timer = QTimer(self.central_widget)
        self.status_timer.timeout.connect(self.emit_lights_update)
        self.status_timer.start(1000)

        rpiUI.show()
        self.app.exec()

if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()