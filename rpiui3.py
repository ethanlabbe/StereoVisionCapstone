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
from PyQt5.QtCore import Qt
from picamera2.previews.qt import QGlPicamera2


class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False
        self.ipaddress = netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
        # bind to a local IP address reachable on your network
        self.server = ImageServerHost(host=self.ipaddress, port=8080)
        self.stereo_system = StereoCameraAcquisition()
        self.folder_path=""

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

        if self.server.connected:
            try:
                print("Sending images to client...")
                self.server.send_images(imgL, imgR)
            except Exception as e:
                print("Failed to send images:", e)
                self.save_images_locally(imgL, imgR)
        else:
            self.save_images_locally(imgL, imgR)


    def UI_start(self):

            self.app = QApplication(sys.argv)
            rpiUI= QMainWindow()
            rpiUI.setWindowTitle("Stereo Vision Capstone")
            # Set window to full screen
            rpiUI.setGeometry(0, 0, 1024, 600)

            # Picamera2 preview widget
            qpicamera2 = QGlPicamera2(self.stereo_system.left_camera, width=1024, height=600, keep_ar=True)

            self.stereo_system.start()

            # Transparent buttons
            self.server_button = QPushButton(text="Start Server", parent=None)
            self.server_button.clicked.connect(self.toggle_server)
            self.server_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 24px; font-weight: bold;")

            capture_button = QPushButton(text="Capture", parent=None)
            capture_button.clicked.connect(self.image_capture)
            capture_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 24px; font-weight: bold;")

            quit_button = QPushButton(text="Quit", parent=None)
            quit_button.clicked.connect(self.quitting)
            quit_button.setStyleSheet("background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px; font-size: 18px; font-weight: bold;")

            #ip address label
            ip_label = QLabel(f"IP: {self.ipaddress}", parent=None)
            ip_label.setStyleSheet("background: rgba(0,0,0,0.3); color: white; font-size: 18px; font-weight: bold;")


            # Use QWidget as central widget for absolute positioning
            central_widget = QWidget()
            central_widget.setStyleSheet("background: transparent;")
            rpiUI.setCentralWidget(central_widget)

            # Picamera display as background
            qpicamera2.setParent(central_widget)
            qpicamera2.setGeometry(0, 0, 1024, 600)

            # Button sizes
            self.server_button.setFixedSize(200, 80)
            capture_button.setFixedSize(200, 80)
            quit_button.setFixedSize(100, 40)

            # Absolute positioning for buttons
            self.server_button.setParent(central_widget)
            self.server_button.move(20, 600 - 80 - 20)  # Bottom-left

            capture_button.setParent(central_widget)
            capture_button.move(1024 - 200 - 20, 600 - 80 - 20)  # Bottom-right

            quit_button.setParent(central_widget)
            quit_button.move(1024 - 100 - 20, 20)  # Top-right

            # IP label movement and sizing
            ip_label.setFixedSize(150, 80)
            ip_label.setParent(central_widget)
            ip_label.move(20, 20)  # Top-left

            # Show UI
            rpiUI.show()
            self.app.exec()


if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()
