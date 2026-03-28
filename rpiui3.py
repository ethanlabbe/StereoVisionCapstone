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
from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from picamera2.previews.qt import QGlPicamera2

UI_HEIGHT=600
UI_WIDTH=1024
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

        self.signals = TransmissionSignals()
        self.signals.update_text.connect(self._update_label_safe)
        self.server.on_send_start = lambda: self.signals.update_text.emit(f"Transmission Info: Sending #{self.img_number}...")
        self.server.on_send_complete = lambda: self.signals.update_text.emit(f"Transmission Info: Sent #{self.img_number} to client")

    def _update_label_safe(self, text):
        self.transmission_info.setText(text)
        self.transmission_info.parent().update(self.transmission_info.geometry())

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

    def run(self):
        self.running = True
        self.stereo_system.initialize_cameras()
        
        # start server in background (non-blocking)

        self.folder_path = "rpi/desktop/images/" + 'temp'
        if not os.path.exists(self.folder_path):
            try:
                os.makedirs(self.folder_path)
            except Exception as e:
                print("Failed to create folder:", e)
                self.folder_path = "rpi/desktop/images/"

        #self.stereo_system.display_preview()

    def quitting(self):
        self.stereo_system.stop()
        self.server.stop_server()
        self.app.quit()


    def image_capture(self):
        capture_thread = threading.Thread(target=self._do_capture)
        capture_thread.start()

    def _do_capture(self):
        imgL, imgR = self.stereo_system.capture_stereo_image()
        self.img_number += 1
        current_id = self.img_number 
        
        if self.server.connected:
            try:
                # Tell the UI it's queued
                self.signals.update_text.emit(f"Transmission Info: Queuing #{current_id}...")
                print(f"Queuing image {current_id} to client...")
                
                # Pass the ID to the server
                self.server.send_images(imgL, imgR)
            except Exception as e:
                print("Failed to queue images:", e)
                self.save_images_locally(imgL, imgR)
                self.signals.update_text.emit(f"Transmission Info: Failed sending #{current_id}, saved locally")
        else:
            self.save_images_locally(imgL, imgR)
            self.signals.update_text.emit(f"Transmission Info: Saved #{current_id} locally (no client)")

    def change_fps(self):
        # Placeholder for changing FPS logic
        print("Change FPS button clicked - functionality not implemented yet")

    def toggle_transmission_info(self):
        if self.transmission_info.isVisible():
            self.transmission_info.hide()
        else:
            self.transmission_info.show()

    def init_settingui(self):
            #ip address label
            self.ip_label = QLabel(f"IP: {self.ipaddress}", parent=None)
            self.ip_label.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 18px; font-weight: bold;")
            self.ip_label.setFixedSize(150, 80)
            self.ip_label.setParent(self.central_widget)
            self.ip_label.move(int((UI_WIDTH-150)/2), 20)  # Top-middle
            self.ip_label.hide()  # Hide IP label by default

            self.fps_select = QPushButton(text="Change FPS", parent=None)
            self.fps_select.clicked.connect(self.change_fps)
            self.fps_select.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 18px; font-weight: bold;")
            self.fps_select.setFixedSize(150, 80)
            self.fps_select.setParent(self.central_widget)
            self.fps_select.move(int((UI_WIDTH-150)/2), 120)  # below ip label
            self.fps_select.hide()  # Hide FPS button by default

            self.show_transmission_info = QPushButton(text="Show Transmission Info", parent=None)
            self.show_transmission_info.clicked.connect(self.toggle_transmission_info)
            self.show_transmission_info.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 18px; font-weight: bold;")
            self.show_transmission_info.setFixedSize(250, 80)
            self.show_transmission_info.setParent(self.central_widget)
            self.show_transmission_info.move(int((UI_WIDTH-250)/2), 220)  # below fps button
            self.show_transmission_info.hide()  # Hide transmission info button by default

            self.quit_button = QPushButton(text="Quit", parent=None)
            self.quit_button.clicked.connect(self.quitting)
            self.quit_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 18px; font-weight: bold;")
            self.quit_button.setFixedSize(100, 50)
            self.quit_button.setParent(self.central_widget)
            self.quit_button.move(int((UI_WIDTH-100)/2), UI_HEIGHT - 70)  # middle bottom
            self.quit_button.hide()  # Hide quit button by default

            self.transmission_info = QLabel("Transmission Info: N/A", parent=None)
            self.transmission_info.setStyleSheet("background: rgb(0,0,0); color: white; border: 2px solid white; border-radius: 10px; font-size: 14px; font-weight: bold;")
            self.transmission_info.setFixedSize(300, 60)
            self.transmission_info.setParent(self.central_widget)
            self.transmission_info.move(20,20)  #top-left
            self.transmission_info.hide()  # Hide transmission info label by default

    def toggle_settings(self):
        # Toggle visibility of settings UI elements
        if self.ip_label.isVisible():
            self.ip_label.hide()
            self.fps_select.hide()
            self.show_transmission_info.hide()
            self.quit_button.hide()

            self.server_button.show()
            self.capture_button.show()
            
        else:
            self.ip_label.show()
            self.fps_select.show()
            self.show_transmission_info.show()
            self.quit_button.show()

            self.server_button.hide()
            self.capture_button.hide()


    def UI_start(self):

            self.app = QApplication(sys.argv)
            rpiUI= QMainWindow()
            rpiUI.setWindowTitle("Stereo Vision Capstone")
            # Set window to full screen
            rpiUI.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)

            # Use QWidget as central widget for absolute positioning
            self.central_widget = QWidget()
            self.central_widget.setStyleSheet("background: transparent;")
            rpiUI.setCentralWidget(self.central_widget)

            # Picamera2 preview widget
            qpicamera2 = QGlPicamera2(self.stereo_system.left_camera, width=UI_WIDTH, height=UI_HEIGHT, keep_ar=True)

            self.stereo_system.start()

            # Transparent buttons
            self.server_button = QPushButton(text="Start Server", parent=None)
            self.server_button.clicked.connect(self.toggle_server)
            self.server_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 24px; font-weight: bold;")

            self.capture_button = QPushButton(text="Capture", parent=None)
            self.capture_button.clicked.connect(self.image_capture)
            self.capture_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 24px; font-weight: bold;")



            #settings button with gear icon
            self.settings_button = QPushButton(parent=None)
            self.settings_button.clicked.connect(self.toggle_settings)
            self.settings_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 18px; font-weight: bold;")
            self.settings_button.setIcon(QIcon("gear.png"))
            self.settings_button.setIconSize(QSize(40, 40))

            # Picamera display as background
            qpicamera2.setParent(self.central_widget)
            qpicamera2.setGeometry(0, 0, UI_WIDTH, UI_HEIGHT)

            # Button sizes
            self.server_button.setFixedSize(200, 80)
            self.capture_button.setFixedSize(200, 80)
            self.settings_button.setFixedSize(50, 50)

            # Absolute positioning for buttons
            self.server_button.setParent(self.central_widget)
            self.server_button.move(20, UI_HEIGHT - 80 - 20)  # Bottom-left

            self.capture_button.setParent(self.central_widget)
            self.capture_button.move(UI_WIDTH - 200 - 20, UI_HEIGHT - 80 - 20)  # Bottom-right

            self.settings_button.setParent(self.central_widget)
            self.settings_button.move(UI_WIDTH - 70, 20) # Top-right

            self.init_settingui()

            # Show UI
            rpiUI.show()
            self.app.exec()


if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()
