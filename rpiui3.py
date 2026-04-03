import os
from image_transfer import ImageServerHost
from acquisition import StereoCameraAcquisition
import cv2
import datetime
import threading
import netifaces

#ui imports
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QGridLayout, QWidget, QLabel
from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from picamera2.previews.qt import QGlPicamera2

UI_HEIGHT=600
UI_WIDTH=1024

BTN_STYLE = "background-color: #2b2b2b; color: #ffffff; border: 2px solid #555555; border-radius: 10px; font-size: 18px; font-weight: bold;"
BTN_STYLE_LG = "background-color: #2b2b2b; color: #ffffff; border: 2px solid #555555; border-radius: 10px; font-size: 20px; font-weight: bold;"

class TransmissionSignals(QObject):
    update_text = pyqtSignal(str)

class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False
        self.ipaddress = netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
        # bind to a local IP address reachable on your network
        self.server = ImageServerHost(host=self.ipaddress, port=8080)
        self.stereo_system = StereoCameraAcquisition()
        self.folder_path=""
        self.img_number = 0
        self.last_tx_msg = "Idle"

        self.signals = TransmissionSignals()
        self.signals.update_text.connect(self._update_label_safe)
        self.server.on_send_start = lambda: self._set_tx_msg(f"Sending #{self.img_number}...")
        self.server.on_send_complete = lambda: self._set_tx_msg(f"Sent #{self.img_number}")

    def _set_tx_msg(self, msg):
        self.last_tx_msg = msg
        self.update_transmission_status()

    def _update_label_safe(self, text):
        self.transmission_info.setText(text)
        self.transmission_info.parent().update(self.transmission_info.geometry())

    def update_transmission_status(self):
        client_status = "Connected" if getattr(self.server, 'connected', False) else "Disconnected"
        server_status = "Running" if getattr(self.server, '_running', False) else "Stopped"
        
        # Formatted for vertical sidebar
        text = (f"Transmission Info\n\n"
                f"Server Status:\n  {server_status}\n\n"
                f"Client Status:\n  {client_status}\n\n"
                f"Last Action:\n  {self.last_tx_msg}")
        self.signals.update_text.emit(text)

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
        self.update_transmission_status()

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
        capture_thread = threading.Thread(target=self._do_capture)
        capture_thread.start()

    def _do_capture(self):
        imgL, imgR = self.stereo_system.capture_stereo_image()
        self.img_number += 1
        current_id = self.img_number 

        if self.server.connected:
            try:
                self._set_tx_msg(f"Queuing #{current_id}...")
                print(f"Queuing image {current_id} to client...")
                self.server.send_images(imgL, imgR)
            except Exception as e:
                print("Failed to queue images:", e)
                self.save_images_locally(imgL, imgR)
                self._set_tx_msg(f"Failed sending #{current_id}, saved locally")
        else:
            self.save_images_locally(imgL, imgR)
            self._set_tx_msg(f"Saved #{current_id} locally (no client)")

    def change_fps(self):
        print("Change FPS button clicked - functionality not implemented yet")

    def toggle_transmission_info(self):
        if self.transmission_info.isVisible():
            self.transmission_info.hide()
        else:
            self.transmission_info.raise_()
            self.transmission_info.show()

    def fake_quitting(self):
        self.stereo_system.stop()
        self.server.stop_server()
        if self.settings_panel.isVisible():
            self.toggle_settings() # ensure settings menu is closed
            
        self.transmission_info.hide()
        self.capture_button.hide()
        self.settings_button.hide()
        self.qpicamera2.hide()

        self.logo_label.show()
        self.calibrate_btn.show()
        self.start_capture_btn.show()
        self.run_locally_btn.show()
        self.quit_button.show()

    def real_quitting(self):
        self.app.quit()

    def init_settingui(self):
        # Settings Dropdown Panel Background
        self.settings_panel = QWidget(self.central_widget)
        self.settings_panel.setObjectName("settingsPanel")
        self.settings_panel.setStyleSheet("QWidget#settingsPanel { background-color: rgba(25, 25, 25, 240); border: 2px solid #555555; border-radius: 15px; }")
        self.settings_panel.setGeometry(int((UI_WIDTH-350)/2), 60, 350, 480)
        self.settings_panel.hide()

        self.ip_label = QLabel(f"IP: {self.ipaddress}", parent=self.settings_panel)
        self.ip_label.setStyleSheet(BTN_STYLE)
        self.ip_label.setAlignment(Qt.AlignCenter)
        self.ip_label.setFixedSize(250, 60)
        self.ip_label.move(50, 20) 

        self.fps_select = QPushButton(text="Change FPS", parent=self.settings_panel)
        self.fps_select.clicked.connect(self.change_fps)
        self.fps_select.setStyleSheet(BTN_STYLE)
        self.fps_select.setFixedSize(250, 60)
        self.fps_select.move(50, 100)

        self.show_transmission_info = QPushButton(text="Toggle Transmission Info", parent=self.settings_panel)
        self.show_transmission_info.clicked.connect(self.toggle_transmission_info)
        self.show_transmission_info.setStyleSheet(BTN_STYLE)
        self.show_transmission_info.setFixedSize(250, 60)
        self.show_transmission_info.move(50, 180)
        
        self.server_button = QPushButton(text="Start Server", parent=self.settings_panel)
        self.server_button.clicked.connect(self.toggle_server)
        self.server_button.setStyleSheet(BTN_STYLE)
        self.server_button.setFixedSize(250, 60)
        self.server_button.move(50, 260) 

        self.capture_quit_button = QPushButton(text="Back to Start", parent=self.settings_panel)
        self.capture_quit_button.clicked.connect(self.fake_quitting)
        self.capture_quit_button.setStyleSheet(BTN_STYLE)
        self.capture_quit_button.setFixedSize(150, 50)
        self.capture_quit_button.move(100, 340) 

        self.close_settings_btn = QPushButton(text="Close Settings", parent=self.settings_panel)
        self.close_settings_btn.clicked.connect(self.toggle_settings)
        self.close_settings_btn.setStyleSheet(BTN_STYLE)
        self.close_settings_btn.setFixedSize(150, 40)
        self.close_settings_btn.move(100, 410)

        # Vertical transmission info sidebar
        self.transmission_info = QLabel("Transmission Info: N/A", parent=self.central_widget)
        self.transmission_info.setStyleSheet("background-color: rgba(18, 18, 18, 200); color: #4CAF50; font-size: 14px; font-weight: bold; border-right: 2px solid #4CAF50; padding: 15px;")
        self.transmission_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.transmission_info.setFixedSize(220, UI_HEIGHT)
        self.transmission_info.move(0, 0) 
        self.transmission_info.hide() 

    def toggle_settings(self):
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
            self.capture_button.show()
        else:
            self.settings_panel.raise_() # Forces the settings panel to be on top of everything
            self.settings_panel.show()
            self.capture_button.hide()

    def init_capture_ui(self):
        self.qpicamera2 = QGlPicamera2(self.stereo_system.left_camera, width=UI_WIDTH, height=UI_HEIGHT, keep_ar=True)
        self.stereo_system.start()

        self.qpicamera2.setParent(self.central_widget)
        self.qpicamera2.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)
        self.qpicamera2.hide() 

        self.capture_button = QPushButton(text="Capture", parent=None)
        self.capture_button.clicked.connect(self.image_capture)
        self.capture_button.setStyleSheet(BTN_STYLE_LG)
        self.capture_button.setFixedSize(200, 80)
        self.capture_button.setParent(self.central_widget)
        self.capture_button.move(UI_WIDTH - 200 - 20, UI_HEIGHT - 80 - 20) 
        self.capture_button.hide() 

        self.settings_button = QPushButton(parent=None)
        self.settings_button.clicked.connect(self.toggle_settings)
        self.settings_button.setStyleSheet("background-color: #2b2b2b; border: 2px solid #555555; border-radius: 25px;")
        self.settings_button.setIcon(QIcon("UI/gear_icon.png"))
        self.settings_button.setIconSize(QSize(30, 30))
        self.settings_button.setFixedSize(50, 50)
        self.settings_button.setParent(self.central_widget)
        self.settings_button.move(UI_WIDTH - 70, 20) 
        self.settings_button.hide() 

    def calibration_ui(self):
        print("Calibration button clicked - functionality not implemented yet")

    def run_locally(self):
        print("Run locally button clicked - functionality not implemented yet")

    def capture_ui(self):
        self.logo_label.hide()
        self.calibrate_btn.hide()
        self.start_capture_btn.hide()
        self.run_locally_btn.hide()
        self.quit_button.hide()

        self.qpicamera2.show() 
        self.capture_button.show()
        
        self.settings_button.raise_()
        self.settings_button.show()
        
        self.transmission_info.raise_()
        self.transmission_info.show() # Transmission info on by default

    def UI_start(self):
        self.app = QApplication(sys.argv)
        rpiUI= QMainWindow()
        rpiUI.setWindowTitle("Stereo Vision Capstone")
        rpiUI.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)

        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("background-color: #121212;")
        rpiUI.setCentralWidget(self.central_widget)

        # Placed at the top so it renders at the bottom of the Z-index stack
        self.logo_label = QLabel(self.central_widget)
        self.logo_label.setPixmap(QPixmap("UI/stereo_vision_logo.png"))
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setGeometry(int((UI_WIDTH - 600)/2), 20, 600, 350)

        # 3 Start screen buttons arranged horizontally (smaller and lower)
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
        self.run_locally_btn.clicked.connect(self.run_locally)
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

        # Timer to continuously fetch connection status and update the info panel
        self.status_timer = QTimer(self.central_widget)
        self.status_timer.timeout.connect(self.update_transmission_status)
        self.status_timer.start(1000)

        rpiUI.show()
        self.app.exec()

if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()